import json
import logging
import os
import asyncio
from pathlib import Path
import tempfile
from typing import Any

import aiohttp
from homeassistant.helpers.update_coordinator import UpdateFailed
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
_CACHE_LOCKS: dict[Path, asyncio.Lock] = {}

# Formát souboru cache: {"version": CACHE_VERSION, "etag": str | None, "data": ...}
CACHE_VERSION = 1
# Limit jednoho požadavku; kratší než timeout volajícího, aby stihl fallback na cache
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)


def _cache_dir(hass) -> Path:
    """Vrátí cestu .storage/<DOMAIN>/ kde se uloží stažené soubory."""
    return Path(hass.config.path(".storage", DOMAIN))


async def get_json(
    hass,
    session: aiohttp.ClientSession,
    url: str,
    file: str,
    use_cache_on_error: bool = True,
) -> tuple[Any, bool]:
    """Stáhne JSON z URL s cache fallbackem; vrací (data, z_cache).

    Data se ukládají spolu s ETagem do .storage/<DOMAIN>/<file>.json.
    Pokud server potvrdí, že se data nezměnila (304), použije se cache.
    Při chybě vrátí poslední uložená data (pokud use_cache_on_error).
    """

    cache_dir = _cache_dir(hass)
    cache_file = cache_dir / f"{file}.json"
    # ETag se dřív ukládal do samostatného souboru
    legacy_etag_file = cache_dir / f"{file}.json.etag"
    cache_lock = _CACHE_LOCKS.setdefault(cache_file, asyncio.Lock())

    def _write_cache(data: Any, etag: str | None) -> None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"version": CACHE_VERSION, "etag": etag, "data": data},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        # Unikátní dočasný soubor - souběžné zápisy si ho nepřepíšou
        fd, tmp = tempfile.mkstemp(
            dir=cache_dir, prefix=f"{cache_file.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                tmp_file.write(payload)
            os.replace(tmp, cache_file)  # atomický zápis
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        legacy_etag_file.unlink(missing_ok=True)

    def _read_cache() -> tuple[Any, str | None]:
        """Vrátí (data, etag); OSError/ValueError pokud cache chybí nebo je neplatná."""
        content = json.loads(cache_file.read_text(encoding="utf-8"))
        if isinstance(content, list):
            # Starší formát: jen data, bez ETagu
            return content, None
        if (
            not isinstance(content, dict)
            or content.get("version") != CACHE_VERSION
            or "data" not in content
        ):
            raise ValueError(f"Neznámý formát cache: {cache_file}")
        return content["data"], content.get("etag")

    not_modified = object()

    async def _write_and_hold_lock(data: Any, etag: str | None) -> None:
        """Zapsat cache; při zrušení počkat na executor, aby starší zápis nepřepsal novější."""
        write = asyncio.ensure_future(
            hass.async_add_executor_job(_write_cache, data, etag)
        )
        try:
            await asyncio.shield(write)
        except asyncio.CancelledError:
            while not write.done():
                try:
                    await asyncio.wait({write})
                except asyncio.CancelledError:
                    continue
            if not write.cancelled() and (err := write.exception()) is not None:
                _LOGGER.warning("Nelze uložit cache %s: %s", cache_file, err)
            raise

    async def _request(headers: dict[str, str]):
        async with session.get(url, headers=headers, timeout=REQUEST_TIMEOUT) as response:
            if response.status == 304:
                return not_modified, None
            response.raise_for_status()
            return await response.json(), response.headers.get("ETag")

    async with cache_lock:
        cached = None
        try:
            try:
                cached = await hass.async_add_executor_job(_read_cache)
            except (OSError, ValueError) as err:
                _LOGGER.debug("Cache %s nelze použít: %s", cache_file, err)
            etag = cached[1] if cached else None

            data, new_etag = await _request(
                {"If-None-Match": etag} if etag else {}
            )

            if data is not_modified:
                if cached is None:
                    raise UpdateFailed(f"Server vrátil 304 bez platné cache: {url}")
                return cached[0], False

            try:
                await _write_and_hold_lock(data, new_etag)
            except OSError as werr:
                # Stažená data jsou platná, jen se nepodařilo uložit cache
                _LOGGER.warning("Nelze uložit cache %s: %s", cache_file, werr)
            else:
                _LOGGER.debug(
                    "Uloženo %s (ETag: %s)",
                    cache_file,
                    new_etag or "server neposlal",
                )
            return data, False

        except Exception as err:
            if not use_cache_on_error:
                raise UpdateFailed(f"Download selhal: {url}") from err
            if cached is None:
                raise UpdateFailed(
                    f"Download selhal a platná cache neexistuje: {url}"
                ) from err
            return cached[0], True
