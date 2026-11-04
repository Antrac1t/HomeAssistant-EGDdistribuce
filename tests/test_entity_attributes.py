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


if __name__ == "__main__":
    unittest.main()
