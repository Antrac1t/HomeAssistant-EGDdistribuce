"""Tests for the coordinator update flow.

Run with: python -m unittest discover -s tests
Requires the integration dependencies and Home Assistant.
"""

from datetime import datetime
import importlib
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


PACKAGE = "_egddistribuce_update_tests"
package = ModuleType(PACKAGE)
package.__path__ = [
    str(Path(__file__).resolve().parents[1] / "custom_components" / "egddistribuce")
]
sys.modules[PACKAGE] = package
coordinator_module = importlib.import_module(f"{PACKAGE}.coordinator")
const = importlib.import_module(f"{PACKAGE}.const")
EGDDistribuceCoordinator = coordinator_module.EGDDistribuceCoordinator

NOW = datetime(2026, 11, 4, 12, 0)
HDO_DATA = [{"region": "ZAPAD", "A": "1", "B": "8", "DP": "06"}]
REGION_DATA = [{"PSC": "58851", "Region": "ZAPAD"}]


class UpdateCachedFlagTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        coordinator = object.__new__(EGDDistribuceCoordinator)
        coordinator.hass = MagicMock()
        coordinator.cz_holidays = set()
        coordinator.config_type = const.CONFIG_TYPE_CLASSIC
        coordinator.psc = "58851"
        coordinator.code_a = "1"
        coordinator.code_b = "8"
        coordinator.code_dp = "06"
        coordinator.data = None
        coordinator.cached_filtered = None
        coordinator.last_update_cached = False
        coordinator.last_successful_update = None
        coordinator._now = lambda: NOW
        coordinator._parse_times = MagicMock(return_value={})
        coordinator._sync_schedule_issue = MagicMock()
        coordinator._schedule_boundary = MagicMock()
        coordinator._schedule_retry = MagicMock()
        coordinator._cancel_retry = MagicMock()
        self.coordinator = coordinator

    async def update(self, hdo_cached, region_cached):
        results = {
            "hdo": (HDO_DATA, hdo_cached),
            "region": (REGION_DATA, region_cached),
        }

        async def get_json(**kwargs):
            return results[kwargs["file"]]

        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        with patch.object(
            coordinator_module, "get_json", side_effect=get_json
        ), patch.object(
            coordinator_module.aiohttp, "ClientSession", return_value=session
        ):
            await self.coordinator._async_update_data()

    async def test_cached_hdo_data_is_not_hidden_by_online_region(self):
        await self.update(hdo_cached=True, region_cached=False)

        self.assertTrue(self.coordinator.last_update_cached)
        self.assertIsNone(self.coordinator.last_successful_update)
        self.coordinator._schedule_retry.assert_called_once()
        self.coordinator._cancel_retry.assert_not_called()

    async def test_cached_region_marks_update_as_cached(self):
        await self.update(hdo_cached=False, region_cached=True)

        self.assertTrue(self.coordinator.last_update_cached)
        self.assertIsNone(self.coordinator.last_successful_update)

    async def test_online_update(self):
        await self.update(hdo_cached=False, region_cached=False)

        self.assertFalse(self.coordinator.last_update_cached)
        self.assertEqual(self.coordinator.last_successful_update, NOW)
        self.coordinator._cancel_retry.assert_called_once()
        self.assertEqual(self.coordinator.cached_filtered, HDO_DATA)


if __name__ == "__main__":
    unittest.main()
