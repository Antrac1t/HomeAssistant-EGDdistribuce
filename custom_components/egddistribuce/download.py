import json
import logging
import os
import asyncio
from pathlib import Path
from typing import Any

import aiohttp
from homeassistant.helpers.update_coordinator import UpdateFailed
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class Download:
    """Sdílená utilita pro stahování JSON dat s cache fallbackem."""

    @staticmethod
    def _get_cache_dir(hass) -> Path:
        """
        Vrátí cestu .storage/<DOMAIN>/ kde se uloží stažené soubory.
        """
        return Path(hass.config.path(".storage", DOMAIN))

    @staticmethod
    async def get_json(
        hass,
        session: aiohttp.ClientSession,
        url: str,
        file: str,
        use_cache_on_error: bool = True,
    ) -> Any:
        """
        Stáhne JSON z URL, uloží do cache/file.json a ETag do cache/file.json.etag.
        Pokud server potvrdí, že se data nezměnila (304), použije se cache.
        Při chybě vrátí poslední uložená data (pokud use_cache_on_error).
        """

        cache_dir = Download._get_cache_dir(hass)
        cache_file = cache_dir / f"{file}.json"
        etag_file = cache_dir / f"{file}.json.etag"

        def _atomic_write(path: Path, text: str) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)  # atomický zápis

        def _write_cache(data: Any, etag: str | None) -> None:
            _atomic_write(
                cache_file,
                json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            )
            # ETag se zapisuje až po datech, aby nikdy nepopisoval starší data
            if etag:
                _atomic_write(etag_file, etag)
            else:
                etag_file.unlink(missing_ok=True)

        def _read_json(path: Path) -> Any:
            return json.loads(path.read_text(encoding="utf-8"))

        def _read_etag() -> str | None:
            # ETag je platný jen společně s existující cache
            if not cache_file.is_file():
                return None
            try:
                return etag_file.read_text(encoding="utf-8").strip() or None
            except OSError:
                return None

        not_modified = object()

        async def _request(headers: dict[str, str]):
            async with session.get(url, headers=headers) as response:
                if response.status == 304:
                    return not_modified, None
                response.raise_for_status()
                return await response.json(), response.headers.get("ETag")

        try:
            etag = await hass.async_add_executor_job(_read_etag)
            data, new_etag = await _request({"If-None-Match": etag} if etag else {})

            if data is not_modified:
                try:
                    return await hass.async_add_executor_job(_read_json, cache_file), False
                except (OSError, ValueError):
                    # Cache zmizela nebo je poškozená - stáhnout znovu bez podmínky
                    data, new_etag = await _request({})
                    if data is not_modified:
                        raise UpdateFailed(f"Server vrátil 304 bez platné cache: {url}")

            try:
                await hass.async_add_executor_job(_write_cache, data, new_etag)
            except OSError as werr:
                # Stažená data jsou platná, jen se nepodařilo uložit cache
                _LOGGER.warning("Nelze uložit cache %s: %s", cache_file, werr)
            else:
                _LOGGER.debug(
                    "Uloženo %s (ETag: %s)", cache_file, new_etag or "server neposlal"
                )
            return data, False

        except (aiohttp.ClientError, asyncio.TimeoutError, Exception) as err:
            if not use_cache_on_error:
                raise UpdateFailed(f"Download selhal: {url}") from err
            try:
                return await hass.async_add_executor_job(_read_json, cache_file), True
            except FileNotFoundError:
                raise UpdateFailed(
                    f"Download selhal a cache neexistuje: {url}"
                ) from err
            except json.JSONDecodeError as jerr:
                raise UpdateFailed(
                    f"Cache je poškozená: {cache_file}"
                ) from jerr