import json
import os
import asyncio
from pathlib import Path
from typing import Any

import aiohttp
from homeassistant.helpers.update_coordinator import UpdateFailed
from .const import DOMAIN


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
    ) -> Any:
        """
        Stáhne JSON z URL, uloží do cache/file.json.
        Při chybě vrátí poslední uložená data.
        """

        cache_dir = Download._get_cache_dir(hass)
        cache_file = cache_dir / f"{file}.json"

        def _write_json(path: Path, data: Any) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            os.replace(tmp, path)  # atomický zápis

        def _read_json(path: Path) -> Any:
            return json.loads(path.read_text(encoding="utf-8"))

        try:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()

            await hass.async_add_executor_job(_write_json, cache_file, data)
            return data, False

        except (aiohttp.ClientError, asyncio.TimeoutError, Exception) as err:
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