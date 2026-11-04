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
get_json = download_module.get_json
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
        self.write_done = threading.Event()

    async def async_add_executor_job(self, func, *args):
        if func.__name__ == "_write_cache":
            return await asyncio.to_thread(self._blocked_write, func, args)
        return func(*args)

    def _blocked_write(self, func, args):
        self.write_started.set()
        try:
            if not self.release_write.wait(timeout=5):
                raise TimeoutError("Timed out waiting to release cache write")
            return func(*args)
        finally:
            self.write_done.set()


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
        self.timeouts = []

    def get(self, url, headers=None, timeout=None):
        self.requests.append(dict(headers or {}))
        self.timeouts.append(timeout)
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
        return await get_json(self.hass, session, "http://x", "hdo", **kwargs)

    def cache(self):
        return json.loads((self.dir / "hdo.json").read_text(encoding="utf-8"))

    def write_legacy_cache(self, data, etag=None):
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "hdo.json").write_text(json.dumps(data), encoding="utf-8")
        if etag is not None:
            (self.dir / "hdo.json.etag").write_text(etag, encoding="utf-8")

    def assert_no_temp_files(self):
        self.assertEqual(list(self.dir.glob("*.tmp")), [])

    async def test_first_download_saves_data_and_etag_in_one_file(self):
        session = FakeSession(FakeResponse(200, [1, 2], {"ETag": 'W/"a"'}))
        self.assertEqual(await self.fetch(session), ([1, 2], False))
        self.assertEqual(session.requests, [{}])
        self.assertEqual(self.cache(), {"version": 1, "etag": 'W/"a"', "data": [1, 2]})
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["hdo.json"])

    async def test_requests_have_a_timeout_below_the_coordinator_timeout(self):
        session = FakeSession(FakeResponse(200, [1]))
        await self.fetch(session)
        self.assertLessEqual(session.timeouts[0].total, 10)

    async def test_not_modified_uses_cache(self):
        await self.fetch(FakeSession(FakeResponse(200, [1, 2], {"ETag": 'W/"a"'})))
        session = FakeSession(FakeResponse(304))
        self.assertEqual(await self.fetch(session), ([1, 2], False))
        self.assertEqual(session.requests, [{"If-None-Match": 'W/"a"'}])

    async def test_changed_data_replaces_cache_and_etag(self):
        await self.fetch(FakeSession(FakeResponse(200, [1], {"ETag": 'W/"a"'})))
        session = FakeSession(FakeResponse(200, [3], {"ETag": 'W/"b"'}))
        self.assertEqual(await self.fetch(session), ([3], False))
        self.assertEqual(self.cache()["etag"], 'W/"b"')
        again = FakeSession(FakeResponse(304))
        self.assertEqual(await self.fetch(again), ([3], False))
        self.assertEqual(again.requests, [{"If-None-Match": 'W/"b"'}])

    async def test_response_without_etag_clears_stale_etag(self):
        await self.fetch(FakeSession(FakeResponse(200, [1], {"ETag": 'W/"a"'})))
        await self.fetch(FakeSession(FakeResponse(200, [2])))
        self.assertEqual(self.cache(), {"version": 1, "etag": None, "data": [2]})
        session = FakeSession(FakeResponse(200, [2]))
        await self.fetch(session)
        self.assertEqual(session.requests, [{}])

    async def test_legacy_cache_is_used_without_etag_and_migrated(self):
        self.write_legacy_cache([1], etag='W/"a"')

        failing = FakeSession(aiohttp.ClientError("down"))
        self.assertEqual(await self.fetch(failing), ([1], True))
        self.assertEqual(failing.requests, [{}])

        session = FakeSession(FakeResponse(200, [2], {"ETag": 'W/"b"'}))
        self.assertEqual(await self.fetch(session), ([2], False))
        self.assertEqual(session.requests, [{}])
        self.assertEqual(self.cache(), {"version": 1, "etag": 'W/"b"', "data": [2]})
        self.assertFalse((self.dir / "hdo.json.etag").exists())

    async def test_corrupt_cache_downloads_without_condition(self):
        self.dir.mkdir(parents=True)
        (self.dir / "hdo.json").write_text("{broken")
        session = FakeSession(FakeResponse(200, [5], {"ETag": 'W/"c"'}))
        self.assertEqual(await self.fetch(session), ([5], False))
        self.assertEqual(session.requests, [{}])
        self.assertEqual(self.cache()["data"], [5])

    async def test_unknown_cache_version_is_ignored(self):
        self.dir.mkdir(parents=True)
        (self.dir / "hdo.json").write_text(
            json.dumps({"version": 99, "etag": 'W/"a"', "data": [1]})
        )
        session = FakeSession(FakeResponse(200, [2]))
        self.assertEqual(await self.fetch(session), ([2], False))
        self.assertEqual(session.requests, [{}])

        with self.assertRaises(UpdateFailed):
            (self.dir / "hdo.json").write_text(
                json.dumps({"version": 99, "etag": None, "data": [1]})
            )
            await self.fetch(FakeSession(aiohttp.ClientError("down")))

    async def test_not_modified_without_cache_is_a_failure(self):
        with self.assertRaises(UpdateFailed):
            await self.fetch(FakeSession(FakeResponse(304)))

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
        self.assertFalse((self.dir / "hdo.json").exists())
        self.assert_no_temp_files()

    async def test_concurrent_downloads_serialize_cache_updates(self):
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
        self.assertEqual(self.cache(), {"version": 1, "etag": 'W/"b"', "data": ["new"]})

    async def test_cancelled_cache_write_holds_lock_until_executor_finishes(self):
        self.hass = BlockingWriteHass(self._tmp.name)
        first = asyncio.create_task(
            self.fetch(FakeSession(FakeResponse(200, ["first"], {"ETag": 'W/"a"'})))
        )
        try:
            started = await asyncio.to_thread(self.hass.write_started.wait, 1)
            self.assertTrue(started)

            first.cancel()
            second_session = FakeSession(FakeResponse(200, ["second"], {"ETag": 'W/"b"'}))
            second = asyncio.create_task(self.fetch(second_session))
            await asyncio.sleep(0)

            # The cancelled download keeps the lock while its write is running
            self.assertFalse(first.done())
            self.assertEqual(second_session.requests, [])

            self.hass.release_write.set()
            with self.assertRaises(asyncio.CancelledError):
                await first
            self.assertEqual(await second, (["second"], False))
        finally:
            self.hass.release_write.set()

        self.assertEqual(second_session.requests, [{"If-None-Match": 'W/"a"'}])
        self.assertEqual(self.cache(), {"version": 1, "etag": 'W/"b"', "data": ["second"]})
        self.assert_no_temp_files()

if __name__ == "__main__":
    unittest.main()
