"""Smoke tests for the smart meter config flow steps.

Run with: python -m unittest discover -s tests
Requires Home Assistant.
"""

import importlib
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

PACKAGE = "_egddistribuce_flow_tests"
package = ModuleType(PACKAGE)
package.__path__ = [
    str(Path(__file__).resolve().parents[1] / "custom_components" / "egddistribuce")
]
sys.modules[PACKAGE] = package
config_flow = importlib.import_module(f"{PACKAGE}.config_flow")

PV = "C45d,D45d-rel\u00e91-PV"
TUV = "C45d,D45d-rel\u00e92-TUV"


def rec(code, *labels):
    return {
        "region": "SM",
        "kodHdo_A": code,
        "sazby": [{"sazba": label, "dny": []} for label in labels],
    }


DATA = [rec("ACd4510", PV, TUV), rec("Cd56", "C56d-rel\u00e91-TUV"), rec("Cd56")]


class SmartFlowTests(unittest.IsolatedAsyncioTestCase):
    def make_flow(self, entries=None):
        flow = config_flow.ConfigFlow()
        flow.hass = SimpleNamespace(
            config_entries=SimpleNamespace(
                async_entries=lambda domain: entries or []
            )
        )
        flow.flow_id = "test"
        flow.context = {}
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = lambda: None
        return flow

    def patch_download(self, **kwargs):
        return patch.object(
            config_flow.Download, "get_json", AsyncMock(**kwargs)
        ), patch.object(config_flow, "async_get_clientsession", lambda hass: None)

    async def test_download_failure_aborts(self):
        flow = self.make_flow()
        get_json, session = self.patch_download(side_effect=RuntimeError("down"))
        with get_json as mocked, session:
            result = await flow.async_step_smart()
        self.assertEqual(result["type"], "abort")
        self.assertEqual(result["reason"], "cannot_connect")
        self.assertFalse(mocked.call_args.kwargs["use_cache_on_error"])

    async def test_code_list_is_a_dropdown_of_smart_codes(self):
        flow = self.make_flow()
        get_json, session = self.patch_download(return_value=(DATA, False))
        with get_json, session:
            result = await flow.async_step_smart()
        self.assertEqual(result["step_id"], "smart")
        schema = result["data_schema"].schema
        self.assertEqual([str(key) for key in schema], [config_flow.CONF_HDO_CODE])
        selector = schema[config_flow.CONF_HDO_CODE]
        self.assertEqual(selector.config["options"], ["ACd4510", "Cd56"])
        # custom value makes the frontend picker searchable
        self.assertTrue(selector.config["custom_value"])

    async def test_unknown_typed_code_shows_error_and_keeps_text(self):
        flow = self.make_flow()
        get_json, session = self.patch_download(return_value=(DATA, False))
        with get_json, session:
            result = await flow.async_step_smart({config_flow.CONF_HDO_CODE: "nope"})
        self.assertEqual(result["step_id"], "smart")
        self.assertEqual(result["errors"], {config_flow.CONF_HDO_CODE: "unknown_code"})
        schema = result["data_schema"]
        self.assertEqual(schema({})[config_flow.CONF_HDO_CODE], "nope")

    async def test_typed_code_is_matched_case_insensitively(self):
        flow = self.make_flow()
        get_json, session = self.patch_download(return_value=(DATA, False))
        with get_json, session:
            result = await flow.async_step_smart({config_flow.CONF_HDO_CODE: " acd4510 "})
        self.assertEqual(result["step_id"], "smart_settings")
        self.assertEqual(flow._smart_input[config_flow.CONF_HDO_CODE], "ACd4510")

    async def test_single_schedule_code_settings_have_no_schedule_field(self):
        flow = self.make_flow()
        get_json, session = self.patch_download(return_value=(DATA, False))
        with get_json, session:
            result = await flow.async_step_smart({config_flow.CONF_HDO_CODE: "Cd56"})
        self.assertEqual(result["step_id"], "smart_settings")
        keys = [str(key) for key in result["data_schema"].schema]
        self.assertNotIn(config_flow.CONF_SCHEDULE, keys)
        self.assertIn(config_flow.CONF_PRICE_VT, keys)
        self.assertIn(config_flow.CONF_COLOR_NT, keys)

        result = await flow.async_step_smart_settings({config_flow.CONF_PRICE_VT: 3.0})
        self.assertEqual(result["type"], "create_entry")
        self.assertNotIn(config_flow.CONF_SCHEDULE, result["data"])
        self.assertEqual(result["data"][config_flow.CONF_PRICE_VT], 3.0)
        self.assertEqual(result["title"], "EGD HDO Smart (Cd56)")
        flow.async_set_unique_id.assert_awaited_with("smart_Cd56")

    async def test_multi_schedule_code_settings_include_schedule_and_prices(self):
        flow = self.make_flow()
        get_json, session = self.patch_download(return_value=(DATA, False))
        with get_json, session:
            result = await flow.async_step_smart(
                {config_flow.CONF_HDO_CODE: "ACd4510"}
            )
        self.assertEqual(result["step_id"], "smart_settings")
        schema = result["data_schema"]
        self.assertIn(config_flow.CONF_SCHEDULE, [str(key) for key in schema.schema])
        self.assertIn(config_flow.CONF_PRICE_NT, [str(key) for key in schema.schema])
        self.assertEqual(schema({})[config_flow.CONF_SCHEDULE], PV)

        result = await flow.async_step_smart_settings(
            {config_flow.CONF_SCHEDULE: TUV, config_flow.CONF_COLOR_VT: "#fff"}
        )
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"][config_flow.CONF_SCHEDULE], TUV)
        self.assertEqual(result["data"][config_flow.CONF_COLOR_VT], "#fff")
        self.assertEqual(result["data"][config_flow.CONF_HDO_CODE], "ACd4510")
        self.assertEqual(result["title"], "EGD HDO Smart (ACd4510, rel\u00e92-TUV)")
        flow.async_set_unique_id.assert_awaited_with(f"smart_ACd4510_{TUV}")

    async def test_default_schedule_aborts_if_legacy_entry_exists(self):
        legacy_entry = SimpleNamespace(unique_id="smart_ACd4510")
        flow = self.make_flow([legacy_entry])
        get_json, session = self.patch_download(return_value=(DATA, False))
        with get_json, session:
            await flow.async_step_smart({config_flow.CONF_HDO_CODE: "ACd4510"})

        result = await flow.async_step_smart_settings(
            {config_flow.CONF_SCHEDULE: PV}
        )
        self.assertEqual(result["type"], "abort")
        self.assertEqual(result["reason"], "already_configured")

    async def test_different_schedule_is_allowed_if_legacy_entry_exists(self):
        legacy_entry = SimpleNamespace(unique_id="smart_ACd4510")
        flow = self.make_flow([legacy_entry])
        get_json, session = self.patch_download(return_value=(DATA, False))
        with get_json, session:
            await flow.async_step_smart({config_flow.CONF_HDO_CODE: "ACd4510"})

        result = await flow.async_step_smart_settings(
            {config_flow.CONF_SCHEDULE: TUV}
        )
        self.assertEqual(result["type"], "create_entry")
        flow.async_set_unique_id.assert_awaited_with(f"smart_ACd4510_{TUV}")


if __name__ == "__main__":
    unittest.main()
