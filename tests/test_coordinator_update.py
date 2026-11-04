"""Tests for the coordinator update flow.

Run with: python -m unittest discover -s tests
Requires the integration dependencies and Home Assistant.
"""

from datetime import datetime
import importlib
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch


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
        coordinator.update_interval = coordinator_module.API_UPDATE_INTERVAL
        self.coordinator = coordinator

    async def update(self, hdo_cached, region_cached, error=None):
        results = {
            "hdo": (HDO_DATA, hdo_cached),
            "region": (REGION_DATA, region_cached),
        }

        async def get_json(**kwargs):
            if error:
                raise error
            return results[kwargs["file"]]

        with patch.object(
            coordinator_module, "get_json", side_effect=get_json
        ), patch.object(
            coordinator_module, "async_get_clientsession", return_value=MagicMock()
        ):
            await self.coordinator._async_update_data()

    async def test_cached_hdo_data_is_not_hidden_by_online_region(self):
        await self.update(hdo_cached=True, region_cached=False)

        self.assertTrue(self.coordinator.last_update_cached)
        self.assertIsNone(self.coordinator.last_successful_update)
        self.assertEqual(
            self.coordinator.update_interval, coordinator_module.RETRY_DELAY
        )

    async def test_cached_region_marks_update_as_cached(self):
        await self.update(hdo_cached=False, region_cached=True)

        self.assertTrue(self.coordinator.last_update_cached)
        self.assertIsNone(self.coordinator.last_successful_update)

    async def test_online_update(self):
        await self.update(hdo_cached=False, region_cached=False)

        self.assertFalse(self.coordinator.last_update_cached)
        self.assertEqual(self.coordinator.last_successful_update, NOW)
        self.assertEqual(self.coordinator.cached_filtered, HDO_DATA)

    async def test_online_update_restores_normal_interval(self):
        self.coordinator.update_interval = coordinator_module.RETRY_DELAY

        await self.update(hdo_cached=False, region_cached=False)

        self.assertEqual(
            self.coordinator.update_interval, coordinator_module.API_UPDATE_INTERVAL
        )

    async def test_failed_update_retries_sooner(self):
        with self.assertRaises(coordinator_module.UpdateFailed):
            await self.update(False, False, error=RuntimeError("down"))

        self.assertEqual(
            self.coordinator.update_interval, coordinator_module.RETRY_DELAY
        )


class CoordinatorConfigTests(unittest.TestCase):
    def make(self, data, options=None, currency="CZK"):
        hass = MagicMock()
        hass.config.currency = currency
        entry = SimpleNamespace(entry_id="entry-1", data=data, options=options or {})
        return EGDDistribuceCoordinator(hass, entry)

    def test_options_override_initial_prices_and_colors(self):
        coordinator = self.make(
            {
                const.CONF_CONFIG_TYPE: const.CONFIG_TYPE_HDO_CODES,
                const.CONF_PSC: "58851",
                const.CONF_HDO_CODE: "405,406",
                const.CONF_PRICE_NT: 1.1,
                const.CONF_PRICE_VT: 2.2,
                const.CONF_COLOR_VT: "#111111",
            },
            {const.CONF_PRICE_NT: 3, const.CONF_COLOR_VT: "#222222"},
        )

        self.assertEqual(coordinator.config_type, const.CONFIG_TYPE_HDO_CODES)
        self.assertEqual(coordinator.psc, "58851")
        self.assertEqual(coordinator.hdo_code, "405,406")
        self.assertEqual(coordinator.price_nt, 3.0)
        self.assertEqual(coordinator.price_vt, 2.2)
        self.assertEqual(coordinator.color_vt, "#222222")
        self.assertEqual(coordinator.color_nt, const.DEFAULT_COLOR_NT)
        self.assertEqual(coordinator.entry_id, "entry-1")

    def test_defaults_and_price_unit(self):
        coordinator = self.make({}, currency="EUR")

        self.assertEqual(coordinator.config_type, const.CONFIG_TYPE_CLASSIC)
        self.assertEqual(coordinator.price_nt, const.DEFAULT_PRICE_NT)
        self.assertEqual(coordinator.price_vt, const.DEFAULT_PRICE_VT)
        self.assertEqual(coordinator.price_unit, "EUR/kWh")
        self.assertEqual(self.make({}).price_unit, "Kč/kWh")


class FilterTests(unittest.TestCase):
    def test_hdo_codes_filter_matches_region_and_any_listed_code(self):
        coordinator = object.__new__(EGDDistribuceCoordinator)
        coordinator.hdo_code = "405, 410"
        records = [
            {"region": "ZAPAD", "kodHdo_A": "405"},
            {"region": "ZAPAD", "kodHdo_A": "406"},
            {"region": "VYCHOD", "kodHdo_A": "410"},
            {"region": "ZAPAD", "kodHdo_A": "410"},
        ]

        self.assertEqual(
            coordinator._filter_hdo_codes(records, "ZAPAD"),
            [records[0], records[3]],
        )


if __name__ == "__main__":
    unittest.main()
