"""Tests for entity state attributes.

Run with: python -m unittest discover -s tests
Requires the integration dependencies and Home Assistant.
"""

from datetime import datetime
import importlib
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import MagicMock, patch


PACKAGE = "_egddistribuce_attribute_tests"
package = ModuleType(PACKAGE)
package.__path__ = [
    str(Path(__file__).resolve().parents[1] / "custom_components" / "egddistribuce")
]
sys.modules[PACKAGE] = package
binary_sensor = importlib.import_module(f"{PACKAGE}.binary_sensor")
sensor = importlib.import_module(f"{PACKAGE}.sensor")
entity = importlib.import_module(f"{PACKAGE}.entity")


class SlotFormatTests(unittest.TestCase):
    def test_full_hours_keep_minutes(self):
        slots = [
            {"od": "10:00:00", "do": "12:30:00"},
            {"od": "22:00:00", "do": "23:59:00"},
        ]

        self.assertEqual(entity.format_slots(slots), "10:00-12:30, 22:00-23:59")
        self.assertEqual(entity.format_slot(slots[0], " - "), "10:00 - 12:30")
        self.assertEqual(entity.format_slots([]), "Žádné")


class CurrentPriceAttributeTests(unittest.TestCase):
    def test_no_always_empty_hourly_prices_attribute(self):
        entity = object.__new__(sensor.EGDDistribuceCurrentPriceSensor)
        entity.coordinator = MagicMock(
            data={"is_active": True, "HDO_HOURLY": {"x": 1.0}},
            price_nt=1.0,
            price_vt=2.0,
        )

        self.assertNotIn("hourly_prices", entity.extra_state_attributes)


class NextChangeSensorTests(unittest.TestCase):
    INTERVALS = [
        {"od": "2026-11-04T10:00:00", "do": "2026-11-04T12:30:00"},
        {"od": "2026-11-05T06:00:00", "do": "2026-11-05T08:00:00"},
    ]

    def entity_at(self, now):
        entity = object.__new__(sensor.EGDDistribuceNextChangeSensor)
        entity.coordinator = MagicMock(
            data={
                "hdo_intervals": self.INTERVALS,
                "hdo_times_today": [{"od": "10:00:00", "do": "12:30:00"}],
                "hdo_times_tomorrow": [{"od": "06:00:00", "do": "08:00:00"}],
            }
        )
        patcher = patch.object(sensor.dt_util, "now", return_value=now)
        patcher.start()
        self.addCleanup(patcher.stop)
        return entity

    def test_next_slot_today(self):
        entity = self.entity_at(datetime(2026, 11, 4, 9, 0))
        self.assertEqual(entity.native_value, "10:00 - 12:30")
        self.assertFalse(entity.extra_state_attributes["tomorrow"])

    def test_next_slot_tomorrow_has_no_text_prefix(self):
        entity = self.entity_at(datetime(2026, 11, 4, 13, 0))
        self.assertEqual(entity.native_value, "06:00 - 08:00")
        attributes = entity.extra_state_attributes
        self.assertTrue(attributes["tomorrow"])
        self.assertEqual(attributes["all_times_tomorrow"], ["06:00 - 08:00"])

    def test_no_planned_slot_is_unknown(self):
        entity = self.entity_at(datetime(2026, 11, 5, 9, 0))
        self.assertIsNone(entity.native_value)
        self.assertFalse(entity.extra_state_attributes["tomorrow"])


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
