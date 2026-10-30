"""Tests for the cached JSON download with ETag support.

Run with: python -m unittest discover -s tests
"""

import asyncio
import importlib
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import ModuleType
import unittest
from unittest.mock import patch

import aiohttp

PACKAGE = "_egddistribuce_download_tests"
package = ModuleType(PACKAGE)
package.__path__ = [
    str(Path(__file__).resolve().parents[1] / "custom_components" / "egddistribuce")
]
sys.modules[PACKAGE] = package
download_module = importlib.import_module(f"{PACKAGE}.download")
Download = download_module.Download
UpdateFailed = download_module.UpdateFailed
DOMAIN = download_module.DOMAIN


class FakeConfig:
    def __init__(self, root):
        self._root = root

    def path(self, *parts):
        return str(Path(self._root, *parts))


class FakeHass:
    def __init__(self, root):
        self.config = FakeConfig(root)

    async def async_add_executor_job(self, func, *args):
        return func(*args)


class BlockingWriteHass(FakeHass):
    def __init__(self, root):
        super().__init__(root)
        self.write_started = threading.Event()
        self.release_write = threading.Event()

    async def async_add_executor_job(self, func, *args):
        if func.__name__ == "_write_cache":
            return await asyncio.to_thread(self._blocked_write, func, args)
        return func(*args)

    def _blocked_write(self, func, args):
        self.write_started.set()
        if not self.release_write.wait(timeout=5):
            raise TimeoutError("Timed out waiting to release cache write")
        return func(*args)


class FakeResponse:
    def __init__(self, status, body=None, headers=None, delay=0, activity=None):
        self.status = status
        self._body = body
        self.headers = headers or {}
        self.delay = delay
        self.activity = activity

    async def __aenter__(self):
        if self.activity is not None:
            self.activity["active"] += 1
            self.activity["maximum"] = max(
                self.activity["maximum"], self.activity["active"]
            )
        await asyncio.sleep(self.delay)
        return self

    async def __aexit__(self, *exc):
        if self.activity is not None:
            self.activity["active"] -= 1
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise aiohttp.ClientResponseError(None, (), status=self.status)

    async def json(self):
        return self._body


class FakeSession:
    """Plays back the prepared responses and records the request headers."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.requests = []

    def get(self, url, headers=None):
        self.requests.append(dict(headers or {}))
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class DownloadTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.hass = FakeHass(self._tmp.name)
        self.dir = Path(self._tmp.name, ".storage", DOMAIN)

    async def fetch(self, session, **kwargs):
        return await Download.get_json(self.hass, session, "http://x", "hdo", **kwargs)

    async def test_first_download_saves_data_and_etag_next_to_it(self):
        session = FakeSession(FakeResponse(200, [1, 2], {"ETag": 'W/"a"'}))
        self.assertEqual(await self.fetch(session), ([1, 2], False))
        self.assertEqual(session.requests, [{}])
        self.assertEqual((self.dir / "hdo.json.etag").read_text(), 'W/"a"')
        self.assertTrue((self.dir / "hdo.json").is_file())

    async def test_not_modified_uses_cache(self):
        await self.fetch(FakeSession(FakeResponse(200, [1, 2], {"ETag": 'W/"a"'})))
        session = FakeSession(FakeResponse(304))
        self.assertEqual(await self.fetch(session), ([1, 2], False))
        self.assertEqual(session.requests, [{"If-None-Match": 'W/"a"'}])

    async def test_changed_data_replaces_cache_and_etag(self):
        await self.fetch(FakeSession(FakeResponse(200, [1], {"ETag": 'W/"a"'})))
        session = FakeSession(FakeResponse(200, [3], {"ETag": 'W/"b"'}))
        self.assertEqual(await self.fetch(session), ([3], False))
        self.assertEqual((self.dir / "hdo.json.etag").read_text(), 'W/"b"')
        again = FakeSession(FakeResponse(304))
        self.assertEqual(await self.fetch(again), ([3], False))

    async def test_response_without_etag_removes_stale_etag(self):
        await self.fetch(FakeSession(FakeResponse(200, [1], {"ETag": 'W/"a"'})))
        await self.fetch(FakeSession(FakeResponse(200, [2])))
        self.assertFalse((self.dir / "hdo.json.etag").exists())

    async def test_etag_without_cache_is_not_sent(self):
        self.dir.mkdir(parents=True)
        (self.dir / "hdo.json.etag").write_text('W/"a"')
        session = FakeSession(FakeResponse(200, [1], {"ETag": 'W/"b"'}))
        await self.fetch(session)
        self.assertEqual(session.requests, [{}])

    async def test_invalid_utf8_etag_triggers_unconditional_download(self):
        await self.fetch(FakeSession(FakeResponse(200, [1], {"ETag": 'W/"a"'})))
        (self.dir / "hdo.json.etag").write_bytes(b"\xff")
        session = FakeSession(FakeResponse(200, [2], {"ETag": 'W/"b"'}))

        self.assertEqual(await self.fetch(session), ([2], False))
        self.assertEqual(session.requests, [{}])
        self.assertEqual((self.dir / "hdo.json.etag").read_text(), 'W/"b"')

    async def test_not_modified_with_corrupt_cache_refetches(self):
        await self.fetch(FakeSession(FakeResponse(200, [1], {"ETag": 'W/"a"'})))
        (self.dir / "hdo.json").write_text("{broken")
        session = FakeSession(
            FakeResponse(304), FakeResponse(200, [5], {"ETag": 'W/"c"'})
        )
        self.assertEqual(await self.fetch(session), ([5], False))
        self.assertEqual(session.requests, [{"If-None-Match": 'W/"a"'}, {}])

    async def test_failure_falls_back_to_cache(self):
        await self.fetch(FakeSession(FakeResponse(200, [1], {"ETag": 'W/"a"'})))
        session = FakeSession(aiohttp.ClientError("down"))
        self.assertEqual(await self.fetch(session), ([1], True))

    async def test_failure_without_cache_raises(self):
        with self.assertRaises(UpdateFailed):
            await self.fetch(FakeSession(asyncio.TimeoutError()))

    async def test_failure_without_cache_fallback_raises_even_with_cache(self):
        await self.fetch(FakeSession(FakeResponse(200, [1], {"ETag": 'W/"a"'})))
        with self.assertRaises(UpdateFailed):
            await self.fetch(
                FakeSession(aiohttp.ClientError("down")), use_cache_on_error=False
            )

    async def test_http_error_status_is_a_failure(self):
        with self.assertRaises(UpdateFailed):
            await self.fetch(FakeSession(FakeResponse(500)))

    async def test_cache_write_failure_does_not_hide_downloaded_data(self):
        session = FakeSession(FakeResponse(200, [1], {"ETag": 'W/"a"'}))
        with patch.object(download_module.os, "replace", side_effect=OSError("ro")):
            with self.assertLogs(download_module._LOGGER, "WARNING"):
                self.assertEqual(await self.fetch(session), ([1], False))

    async def test_etag_write_failure_leaves_updated_payload_without_validator(self):
        await self.fetch(FakeSession(FakeResponse(200, [1], {"ETag": 'W/"a"'})))
        session = FakeSession(FakeResponse(200, [2], {"ETag": 'W/"b"'}))
        original_replace = download_module.os.replace

        def fail_etag_write(source, destination):
            if Path(destination) == self.dir / "hdo.json.etag":
                raise OSError("etag write failed")
            return original_replace(source, destination)

        with patch.object(download_module.os, "replace", side_effect=fail_etag_write):
            with self.assertLogs(download_module._LOGGER, "WARNING"):
                self.assertEqual(await self.fetch(session), ([2], False))

        self.assertEqual(
            json.loads((self.dir / "hdo.json").read_text(encoding="utf-8")), [2]
        )
        self.assertFalse((self.dir / "hdo.json.etag").exists())

    async def test_concurrent_downloads_serialize_cache_and_etag_updates(self):
        activity = {"active": 0, "maximum": 0}
        session = FakeSession(
            FakeResponse(200, ["old"], {"ETag": 'W/"a"'}, delay=0.03, activity=activity),
            FakeResponse(200, ["new"], {"ETag": 'W/"b"'}, activity=activity),
        )

        old_result, new_result = await asyncio.gather(
            self.fetch(session),
            self.fetch(session),
        )

        self.assertEqual(old_result, (["old"], False))
        self.assertEqual(new_result, (["new"], False))
        self.assertEqual(activity["maximum"], 1)
        self.assertEqual(
            json.loads((self.dir / "hdo.json").read_text(encoding="utf-8")),
            ["new"],
        )
        self.assertEqual(
            (self.dir / "hdo.json.etag").read_text(encoding="utf-8"), 'W/"b"'
        )

    async def test_cancelled_cache_write_holds_lock_until_executor_finishes(self):
        self.hass = BlockingWriteHass(self._tmp.name)
        first_session = FakeSession(
            FakeResponse(200, ["first"], {"ETag": 'W/"first"'})
        )
        first_download = asyncio.create_task(self.fetch(first_session))
        try:
            started = await asyncio.to_thread(self.hass.write_started.wait, 1)
            self.assertTrue(started)

            first_download.cancel()
            second_session = FakeSession(
                FakeResponse(200, ["second"], {"ETag": 'W/"second"'})
            )
            second_download = asyncio.create_task(self.fetch(second_session))
            await asyncio.sleep(0)

            self.assertFalse(first_download.done())
            self.assertEqual(second_session.requests, [])

            self.hass.release_write.set()
            with self.assertRaises(asyncio.CancelledError):
                await first_download

            self.assertEqual(await second_download, (["second"], False))
            self.assertEqual(
                second_session.requests, [{"If-None-Match": 'W/"first"'}]
            )
            self.assertEqual(
                json.loads((self.dir / "hdo.json").read_text(encoding="utf-8")),
                ["second"],
            )
            self.assertEqual(
                (self.dir / "hdo.json.etag").read_text(encoding="utf-8"),
                'W/"second"',
            )
        finally:
            self.hass.release_write.set()


if __name__ == "__main__":
    unittest.main()
