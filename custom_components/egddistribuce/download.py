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
# Probíhající stahování podle souboru cache; souběžní volající sdílí jeden požadavek
_IN_FLIGHT: dict[Path, asyncio.Future] = {}

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

    Souběžná volání pro stejný soubor sdílí jedno stahování, takže na sebe
    nečekají déle než jeden požadavek. Zrušení volajícího stahování nepřeruší.
    """
    cache_file = _cache_dir(hass) / f"{file}.json"
    task = _IN_FLIGHT.get(cache_file)
    if task is None:
        task = asyncio.ensure_future(_download(hass, session, url, cache_file))
        _IN_FLIGHT[cache_file] = task

        def _done(finished: asyncio.Future) -> None:
            if _IN_FLIGHT.get(cache_file) is finished:
                del _IN_FLIGHT[cache_file]
            if not finished.cancelled():
                finished.exception()  # chybu dostanou volající; jinak by asyncio varovalo

        task.add_done_callback(_done)

    data, error = await asyncio.shield(task)
    if error is not None:
        if not use_cache_on_error:
            raise UpdateFailed(f"Download selhal: {url}") from error
        return data, True
    return data, False


async def _download(
    hass, session: aiohttp.ClientSession, url: str, cache_file: Path
) -> tuple[Any, Exception | None]:
    """Stáhnout soubor; vrací (data, None), nebo (data z cache, chyba) při selhání."""
    cache_dir = cache_file.parent
    # ETag se dřív ukládal do samostatného souboru
    legacy_etag_file = cache_dir / f"{cache_file.name}.etag"

    def _write_cache(data: Any, etag: str | None) -> None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"version": CACHE_VERSION, "etag": etag, "data": data},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        # Unikátní dočasný soubor - rozpracovaný zápis nikdy není vidět
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

    async def _request(headers: dict[str, str]):
        async with session.get(url, headers=headers, timeout=REQUEST_TIMEOUT) as response:
            if response.status == 304:
                return not_modified, None
            response.raise_for_status()
            return await response.json(), response.headers.get("ETag")

    cached = None
    try:
        try:
            cached = await hass.async_add_executor_job(_read_cache)
        except (OSError, ValueError) as err:
            _LOGGER.debug("Cache %s nelze použít: %s", cache_file, err)
        etag = cached[1] if cached else None

        data, new_etag = await _request({"If-None-Match": etag} if etag else {})

        if data is not_modified:
            if cached is None:
                raise UpdateFailed(f"Server vrátil 304 bez platné cache: {url}")
            return cached[0], None

        try:
            await hass.async_add_executor_job(_write_cache, data, new_etag)
        except OSError as werr:
            # Stažená data jsou platná, jen se nepodařilo uložit cache
            _LOGGER.warning("Nelze uložit cache %s: %s", cache_file, werr)
        else:
            _LOGGER.debug(
                "Uloženo %s (ETag: %s)", cache_file, new_etag or "server neposlal"
            )
        return data, None

    except Exception as err:
        if cached is None:
            raise UpdateFailed(
                f"Download selhal a platná cache neexistuje: {url}"
            ) from err
        return cached[0], err
