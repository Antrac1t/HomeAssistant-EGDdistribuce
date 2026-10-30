"""Tests for the schedule helpers.

Run with: python -m unittest discover -s tests
"""

import importlib.util
from pathlib import Path
import unittest

_path = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "egddistribuce"
    / "schedules.py"
)
_spec = importlib.util.spec_from_file_location("_egd_schedules", _path)
schedules = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(schedules)

PV = "C45d,D45d-rel\u00e91-PV"
TUV = "C45d,D45d-rel\u00e92-TUV"


def rec(region, code, *labels):
    return {
        "region": region,
        "kodHdo_A": code,
        "sazby": [{"sazba": label, "dny": []} for label in labels],
    }


class SchedulesTests(unittest.TestCase):
    def test_smart_codes_only_from_smart_regions_sorted_unique(self):
        data = [
            rec("SM", "Cd56"),
            rec("TOU", "ACd4510"),
            rec("SM", "ACd4510"),
            rec("VYCHOD", "202"),
            rec("SM", "ad57"),
            {"region": "SM"},
        ]
        self.assertEqual(
            schedules.smart_codes(data), ["ACd4510", "ad57", "Cd56"]
        )

    def test_labels_sorted_by_relay_number(self):
        records = [rec("SM", "X", TUV), rec("SM", "X", PV), rec("SM", "X", PV)]
        self.assertEqual(schedules.schedule_labels(records), [PV, TUV])

    def test_labels_without_relay_go_last(self):
        records = [rec("SM", "X", "C25d,C26d", TUV)]
        self.assertEqual(
            schedules.schedule_labels(records), [TUV, "C25d,C26d"]
        )

    def test_default_prefers_pv_over_relay_order(self):
        self.assertEqual(schedules.default_schedule([TUV, PV]), PV)
        self.assertEqual(
            schedules.default_schedule(["A-rel\u00e91-TUV", "B-rel\u00e92-TUV,PV"]),
            "B-rel\u00e92-TUV,PV",
        )

    def test_default_without_pv_is_first(self):
        self.assertEqual(
            schedules.default_schedule(["A-rel\u00e91-PT", TUV]), "A-rel\u00e91-PT"
        )
        self.assertIsNone(schedules.default_schedule([]))

    def test_pvtc_is_not_pv(self):
        self.assertEqual(
            schedules.default_schedule(["D56-rel\u00e91-TUV,PVTC", TUV]),
            "D56-rel\u00e91-TUV,PVTC",
        )

    def test_match_code_exact_then_unique_casefold(self):
        codes = ["ACd4510", "Cd56", "cd56x", "Ab", "AB"]
        self.assertEqual(schedules.match_code(codes, "Cd56"), "Cd56")
        self.assertEqual(schedules.match_code(codes, " acd4510 "), "ACd4510")
        self.assertEqual(schedules.match_code(codes, "Ab"), "Ab")
        self.assertIsNone(schedules.match_code(codes, "ab"))
        self.assertIsNone(schedules.match_code(codes, "Cd5"))
        self.assertIsNone(schedules.match_code(codes, ""))

    def test_select_schedule_keeps_only_label_without_mutation(self):
        mixed = rec("SM", "X", PV, TUV)
        result = schedules.select_schedule([mixed, rec("SM", "X", TUV)], PV)
        self.assertEqual(len(result), 1)
        self.assertEqual([t["sazba"] for t in result[0]["sazby"]], [PV])
        self.assertEqual(len(mixed["sazby"]), 2)


if __name__ == "__main__":
    unittest.main()
