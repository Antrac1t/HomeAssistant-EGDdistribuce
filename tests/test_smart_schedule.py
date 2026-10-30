"""Regression tests for smart relay selection.

Run with: python -m unittest discover -s tests
Requires the integration dependencies and Home Assistant.
"""

from copy import deepcopy
from datetime import datetime, timezone
import importlib
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch


# Load the coordinator without running the integration's HTTP setup.
PACKAGE = "_egddistribuce_schedule_tests"
package = ModuleType(PACKAGE)
package.__path__ = [
    str(Path(__file__).resolve().parents[1] / "custom_components" / "egddistribuce")
]
sys.modules[PACKAGE] = package
coordinator_module = importlib.import_module(f"{PACKAGE}.coordinator")
EGDDistribuceCoordinator = coordinator_module.EGDDistribuceCoordinator

PV_WEEKDAY = [
    ("00:00:00", "06:15:00"),
    ("07:15:00", "08:45:00"),
    ("09:45:00", "17:45:00"),
    ("18:45:00", "20:15:00"),
    ("21:15:00", "23:59:00"),
]
PV_WEEKEND = [
    ("00:00:00", "07:15:00"),
    ("08:15:00", "09:45:00"),
    ("10:45:00", "18:15:00"),
    ("19:15:00", "20:45:00"),
    ("21:45:00", "23:59:00"),
]
TUV_WEEKDAY = [("01:45:00", "05:45:00"), ("13:00:00", "17:00:00")]
TUV_WEEKEND = [("03:15:00", "07:15:00"), ("13:30:00", "17:30:00")]


def slots(times):
    return [{"od": start, "do": end} for start, end in times]


def record(label, weekday, weekend):
    """Build the September/October ACd4510 API record."""
    return {
        "region": "SM",
        "kodHdo_A": "ACd4510",
        "od": {"den": "01", "mesic": "09", "rok": "9999"},
        "do": {"den": "31", "mesic": "10", "rok": "9999"},
        "sazby": [{
            "sazba": label,
            "dny": [
                {"denVTydnu": day, "casy": slots(weekday if day < 6 else weekend)}
                for day in range(1, 8)
            ],
        }],
    }


class SmartScheduleTests(unittest.TestCase):
    def setUp(self):
        self.coordinator = object.__new__(EGDDistribuceCoordinator)
        self.coordinator.hdo_code = "ACd4510"
        self.coordinator.cz_holidays = set()
        self.coordinator.price_nt = 1.5
        self.coordinator.price_vt = 2.5
        self.coordinator.schedule = None
        self.coordinator.schedule_status = "ok"
        self.coordinator.active_schedule = None
        self.pv = record("C45d,D45d-rel\u00e91-PV", PV_WEEKDAY, PV_WEEKEND)
        self.tuv = record("C45d,D45d-rel\u00e92-TUV", TUV_WEEKDAY, TUV_WEEKEND)

    def test_issue_80_attributes_and_derived_state_use_only_pv(self):
        now = datetime(2026, 10, 23, 13, 17)
        with patch.object(coordinator_module.dt_util, "DEFAULT_TIME_ZONE", timezone.utc):
            unfiltered = self.coordinator._parse_times([self.pv, self.tuv], now)
            filtered = self.coordinator._filter_smart([self.pv, self.tuv])
            actual = self.coordinator._parse_times(filtered, now)
            expected = self.coordinator._parse_times([self.pv], now)

        self.assertEqual(len(unfiltered["hdo_times_today"]), 7)
        self.assertEqual(actual, expected)
        self.assertEqual(actual["hdo_times_today"], slots(PV_WEEKDAY))
        self.assertEqual(actual["hdo_times_tomorrow"], slots(PV_WEEKEND))
        self.assertTrue(actual["is_active"])
        self.assertEqual(actual["current_price"], 1.5)
        self.assertEqual(actual["next_change"].hour, 17)
        self.assertEqual(actual["next_change"].minute, 45)
        self.assertEqual(len(actual["HDO_HOURLY"]), 192)
        self.assertEqual(
            sum(price == 1.5 for price in actual["HDO_HOURLY"].values()), 160
        )

    def test_separate_tuv_cannot_fill_a_pv_gap(self):
        self.tuv["sazby"][0]["dny"][4]["casy"] = slots(
            [("06:00:00", "08:00:00")]
        )
        filtered = self.coordinator._filter_smart([self.pv, self.tuv])
        with patch.object(coordinator_module.dt_util, "DEFAULT_TIME_ZONE", timezone.utc):
            data = self.coordinator._parse_times(
                filtered, datetime(2026, 10, 23, 6, 30)
            )
        self.assertFalse(data["is_active"])
        self.assertEqual(data["current_price"], 2.5)
        self.assertEqual(
            data["next_change"].replace(tzinfo=None), datetime(2026, 10, 23, 7, 15)
        )
        self.assertEqual(data["HDO_HOURLY"][datetime(2026, 10, 23, 6, 30)], 2.5)

    def test_all_seasonal_pv_records_are_retained(self):
        winter_pv = deepcopy(self.pv)
        winter_tuv = deepcopy(self.tuv)
        for winter_record in (winter_pv, winter_tuv):
            winter_record["od"]["mesic"] = "11"
            winter_record["do"]["mesic"] = "01"
        self.assertEqual(
            self.coordinator._filter_smart(
                [self.pv, self.tuv, winter_pv, winter_tuv]
            ),
            [self.pv, winter_pv],
        )

    def test_mixed_tariffs_are_filtered_without_mutating_api_data(self):
        mixed = deepcopy(self.pv)
        mixed["sazby"].extend(self.tuv["sazby"])
        original = deepcopy(mixed)
        self.assertEqual(self.coordinator._filter_smart([mixed]), [self.pv])
        self.assertEqual(mixed, original)

    def test_combined_pv_labels_are_kept(self):
        for label in (
            "D57d-rel\u00e91-PVTC,PV",
            "C35d,D35d-rel\u00e91-TUV,PV,AKU",
        ):
            with self.subTest(label=label):
                combined = record(label, PV_WEEKDAY, PV_WEEKEND)
                self.assertEqual(
                    self.coordinator._filter_smart([self.tuv, combined]), [combined]
                )

    def test_codes_without_pv_keep_existing_schedules(self):
        for label in (
            "C25d,D25d-rel\u00e92-TUV",
            "C56d,D56d-rel\u00e91-TUV,PVTC",
            "C25d,C26d,D25d,D26d",
            "C46d-rel\u00e91-PT",
        ):
            with self.subTest(label=label):
                other = record(label, TUV_WEEKDAY, TUV_WEEKEND)
                self.assertEqual(self.coordinator._filter_smart([other]), [other])

    def test_pv_for_other_code_does_not_remove_tuv_only_schedule(self):
        self.pv["kodHdo_A"] = "Ad57"
        self.assertEqual(
            self.coordinator._filter_smart([self.pv, self.tuv]), [self.tuv]
        )

    def test_code_matching_remains_case_sensitive(self):
        self.coordinator.hdo_code = "ACD4510"
        self.assertEqual(self.coordinator._filter_smart([self.pv, self.tuv]), [])

    def test_saved_schedule_is_used(self):
        self.coordinator.schedule = self.tuv["sazby"][0]["sazba"]
        self.assertEqual(
            self.coordinator._filter_smart([self.pv, self.tuv]), [self.tuv]
        )
        self.assertEqual(self.coordinator.schedule_status, "ok")
        self.assertEqual(self.coordinator.active_schedule, self.coordinator.schedule)

    def test_default_schedule_is_reported(self):
        self.assertEqual(
            self.coordinator._filter_smart([self.pv, self.tuv]), [self.pv]
        )
        self.assertEqual(self.coordinator.schedule_status, "default")

    def test_single_schedule_is_not_reported(self):
        self.coordinator._filter_smart([self.pv])
        self.assertEqual(self.coordinator.schedule_status, "ok")

    def test_missing_saved_schedule_falls_back_and_is_reported(self):
        self.coordinator.schedule = "gone-rel\u00e93-XYZ"
        self.assertEqual(
            self.coordinator._filter_smart([self.pv, self.tuv]), [self.pv]
        )
        self.assertEqual(self.coordinator.schedule_status, "missing")


if __name__ == "__main__":
    unittest.main()
