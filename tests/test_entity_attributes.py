"""Tests for entity state attributes.

Run with: python -m unittest discover -s tests
Requires the integration dependencies and Home Assistant.
"""

import importlib
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import MagicMock


PACKAGE = "_egddistribuce_attribute_tests"
package = ModuleType(PACKAGE)
package.__path__ = [
    str(Path(__file__).resolve().parents[1] / "custom_components" / "egddistribuce")
]
sys.modules[PACKAGE] = package
binary_sensor = importlib.import_module(f"{PACKAGE}.binary_sensor")
sensor = importlib.import_module(f"{PACKAGE}.sensor")


class CurrentPriceAttributeTests(unittest.TestCase):
    def test_no_always_empty_hourly_prices_attribute(self):
        entity = object.__new__(sensor.EGDDistribuceCurrentPriceSensor)
        entity.coordinator = MagicMock(
            data={"is_active": True, "HDO_HOURLY": {"x": 1.0}},
            price_nt=1.0,
            price_vt=2.0,
        )

        self.assertNotIn("hourly_prices", entity.extra_state_attributes)


class TimesChangeTests(unittest.TestCase):
    def is_on(self, today, tomorrow):
        entity = object.__new__(binary_sensor.EGDDistribuceTimesChangeBinarySensor)
        entity.coordinator = MagicMock(
            data={"hdo_times_today": today, "hdo_times_tomorrow": tomorrow}
        )
        return entity.is_on

    def test_detects_changed_schedule(self):
        same = [{"od": "10:00:00", "do": "12:00:00"}]
        other = [{"od": "10:00:00", "do": "12:15:00"}]

        self.assertFalse(self.is_on(same, list(same)))
        self.assertTrue(self.is_on(same, other))
        self.assertFalse(self.is_on(same, []))
        self.assertFalse(self.is_on([], other))


class RecorderAttributeTests(unittest.TestCase):
    def test_large_hdo_attributes_are_not_recorded(self):
        unrecorded = binary_sensor.EGDDistribuceBinarySensor._unrecorded_attributes

        for name in (
            "HDO_HOURLY",
            "hdo_intervals",
            "hdo_times_today_raw",
            "hdo_times_tomorrow_raw",
            "hdo_cas_od",
            "hdo_cas_do",
        ):
            with self.subTest(name=name):
                self.assertIn(name, unrecorded)


if __name__ == "__main__":
    unittest.main()
