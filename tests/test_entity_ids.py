"""Regression tests for new entity IDs and existing registry entries.

Run with: python -m unittest discover -s tests
Requires Home Assistant.
"""

from datetime import timedelta
import importlib
import logging
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import ModuleType
import unittest

from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    device_registry as dr,
    entity as entity_helper,
    entity_registry as er,
    restore_state,
)
from homeassistant.helpers.entity_platform import EntityPlatform

PACKAGE = "_egddistribuce_entity_tests"
package = ModuleType(PACKAGE)
package.__path__ = [
    str(Path(__file__).resolve().parents[1] / "custom_components" / "egddistribuce")
]
sys.modules[PACKAGE] = package
sensor = importlib.import_module(f"{PACKAGE}.sensor")
binary_sensor = importlib.import_module(f"{PACKAGE}.binary_sensor")
button = importlib.import_module(f"{PACKAGE}.button")
coordinator_module = importlib.import_module(f"{PACKAGE}.coordinator")
DOMAIN = "egddistribuce"
ENTITY_TYPES = [
    ("sensor", "current_price", sensor.EGDDistribuceCurrentPriceSensor),
    ("sensor", "next_hdo_change", sensor.EGDDistribuceNextChangeTimeSensor),
    ("sensor", "next_change", sensor.EGDDistribuceNextChangeSensor),
    ("binary_sensor", "hdo_status", binary_sensor.EGDDistribuceBinarySensor),
    (
        "binary_sensor",
        "hdo_times_change",
        binary_sensor.EGDDistribuceTimesChangeBinarySensor,
    ),
    (
        "binary_sensor",
        "update_status",
        binary_sensor.EGDDistribuceUpdateStatusBinarySensor,
    ),
    ("button", "refresh_api", button.EGDDistribuceRefreshButton),
]


class EntityIdTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = TemporaryDirectory()
        self.hass = HomeAssistant(self.directory.name)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        entity_helper.async_setup(self.hass)
        await restore_state.async_load(self.hass)
        await er.async_load(self.hass)
        await dr.async_load(self.hass)
        self.registry = er.async_get(self.hass)
        self.entry = self.make_entry("entry-1", "D\u016fm")
        self.coordinator = coordinator_module.EGDDistribuceCoordinator(
            self.hass, config_type="classic"
        )
        self.coordinator.update_interval = None
        self.coordinator.data = {}
        self.platforms = {}

    async def asyncTearDown(self):
        for platform in self.platforms.values():
            await platform.async_reset()
        await self.hass.async_stop()
        self.directory.cleanup()

    def make_entry(self, entry_id, title):
        entry = ConfigEntry(
            version=1,
            minor_version=1,
            domain=DOMAIN,
            title=title,
            data={},
            source="user",
            entry_id=entry_id,
        )
        self.hass.config_entries._entries[entry.entry_id] = entry
        return entry

    async def add_entity(self, domain, entity_type, entry=None):
        entry = entry or self.entry
        platform_key = (domain, entry.entry_id)
        if platform_key not in self.platforms:
            platform = EntityPlatform(
                hass=self.hass,
                logger=logging.getLogger(__name__),
                domain=domain,
                platform_name=DOMAIN,
                platform=None,
                scan_interval=timedelta(seconds=30),
                entity_namespace=None,
            )
            platform.config_entry = entry
            self.platforms[platform_key] = platform
        entity = entity_type(self.coordinator, entry)
        await self.platforms[platform_key]._async_add_entity(
            entity, False, self.registry
        )
        return entity

    async def test_all_new_entities_have_fixed_prefix_and_title_at_end(self):
        for domain, key, entity_type in ENTITY_TYPES:
            with self.subTest(key=key):
                entity = await self.add_entity(domain, entity_type)
                expected = f"{domain}.egd_{key}_dum"
                self.assertEqual(entity.entity_id, expected)
                self.assertEqual(entity.unique_id, f"{self.entry.entry_id}_{key}")
                self.assertEqual(entity.translation_key, key)
                self.assertTrue(entity.has_entity_name)
                self.assertIsNotNone(self.hass.states.get(expected))
                self.assertIsNotNone(entity.device_entry)
        self.assertEqual(len(self.registry.entities), 7)

    async def test_current_price_supports_long_term_statistics(self):
        self.coordinator.data = {"current_price": 1.5}
        entity = await self.add_entity(
            "sensor", sensor.EGDDistribuceCurrentPriceSensor
        )
        state = self.hass.states.get(entity.entity_id)
        self.assertEqual(state.attributes.get("state_class"), "measurement")
        self.assertNotIn("device_class", state.attributes)
        self.assertEqual(state.attributes.get("icon"), "mdi:currency-eur")
        self.assertEqual(state.attributes.get("unit_of_measurement"), "Kč/kWh")

    async def test_legacy_and_custom_ids_are_not_renamed_or_duplicated(self):
        for domain, key, entity_type in ENTITY_TYPES:
            with self.subTest(key=key):
                old = self.registry.async_get_or_create(
                    domain,
                    DOMAIN,
                    f"{self.entry.entry_id}_{key}",
                    suggested_object_id=f"my_custom_{key}",
                    config_entry=self.entry,
                )
                old = self.registry.async_update_entity(
                    old.entity_id,
                    name=f"Custom {key}",
                    icon="mdi:home",
                    hidden_by=er.RegistryEntryHider.USER,
                )
                entity = await self.add_entity(domain, entity_type)
                self.assertEqual(entity.entity_id, old.entity_id)
                current = self.registry.async_get(old.entity_id)
                self.assertEqual(current.id, old.id)
                self.assertEqual(current.unique_id, old.unique_id)
                self.assertEqual(current.name, old.name)
                self.assertEqual(current.icon, old.icon)
                self.assertEqual(current.hidden_by, old.hidden_by)
                self.assertFalse(
                    self.registry.async_is_registered(
                        f"{domain}.egd_{key}_dum"
                    )
                )
        self.assertEqual(len(self.registry.entities), 7)

    async def test_disabled_entities_keep_their_ids_and_disabled_state(self):
        for domain, key, entity_type in ENTITY_TYPES:
            with self.subTest(key=key):
                old = self.registry.async_get_or_create(
                    domain,
                    DOMAIN,
                    f"{self.entry.entry_id}_{key}",
                    suggested_object_id=f"legacy_{key}",
                    config_entry=self.entry,
                    disabled_by=er.RegistryEntryDisabler.USER,
                )
                entity = await self.add_entity(domain, entity_type)
                self.assertEqual(entity.entity_id, old.entity_id)
                self.assertEqual(
                    self.registry.async_get(old.entity_id).disabled_by,
                    er.RegistryEntryDisabler.USER,
                )
                self.assertIsNone(self.hass.states.get(old.entity_id))
        self.assertEqual(len(self.registry.entities), 7)

    async def test_id_collision_does_not_overwrite_other_entities(self):
        other_entry = self.make_entry("entry-2", self.entry.title)
        for domain, key, entity_type in ENTITY_TYPES:
            with self.subTest(key=key):
                first = await self.add_entity(domain, entity_type)
                second = await self.add_entity(domain, entity_type, other_entry)
                self.assertEqual(second.entity_id, f"{first.entity_id}_2")
                self.assertNotEqual(first.unique_id, second.unique_id)
                self.assertEqual(
                    self.registry.async_get(first.entity_id).unique_id,
                    first.unique_id,
                )
        self.assertEqual(len(self.registry.entities), 14)

    async def test_missing_entity_on_existing_device_uses_new_format(self):
        old = self.registry.async_get_or_create(
            "sensor",
            DOMAIN,
            f"{self.entry.entry_id}_current_price",
            suggested_object_id="legacy_price",
            config_entry=self.entry,
        )
        price = await self.add_entity("sensor", sensor.EGDDistribuceCurrentPriceSensor)
        next_change = await self.add_entity(
            "sensor", sensor.EGDDistribuceNextChangeTimeSensor
        )
        self.assertEqual(price.entity_id, old.entity_id)
        self.assertEqual(
            next_change.entity_id, "sensor.egd_next_hdo_change_dum"
        )
        self.assertEqual(price.device_entry.id, next_change.device_entry.id)
        self.assertEqual(len(self.registry.entities), 2)

    async def test_new_ids_do_not_depend_on_language(self):
        for language in ("cs", "en"):
            self.hass.config.language = language
            entry = self.make_entry(f"entry-{language}", f"Chata {language}")
            for domain, key, entity_type in ENTITY_TYPES:
                with self.subTest(language=language, key=key):
                    entity = await self.add_entity(domain, entity_type, entry)
                    self.assertEqual(
                        entity.entity_id,
                        f"{domain}.egd_{key}_chata_{language}",
                    )

    async def test_entry_title_changes_do_not_rename_registered_entities(self):
        for domain, key, entity_type in ENTITY_TYPES:
            with self.subTest(key=key):
                old = self.registry.async_get_or_create(
                    domain,
                    DOMAIN,
                    f"{self.entry.entry_id}_{key}",
                    suggested_object_id=f"egddistribuce_{key}_puvodni_nazev",
                    config_entry=self.entry,
                )
                entity = await self.add_entity(domain, entity_type)
                self.assertEqual(entity.entity_id, old.entity_id)

    async def test_reload_preserves_new_ids_without_duplicates(self):
        for domain, key, entity_type in ENTITY_TYPES:
            await self.add_entity(domain, entity_type)
        original_ids = set(self.registry.entities)
        for platform in self.platforms.values():
            await platform.async_reset()
        self.platforms.clear()
        for domain, key, entity_type in ENTITY_TYPES:
            with self.subTest(key=key):
                entity = await self.add_entity(domain, entity_type)
                self.assertIn(entity.entity_id, original_ids)
                self.assertIsNotNone(self.hass.states.get(entity.entity_id))
        self.assertEqual(set(self.registry.entities), original_ids)
        self.assertEqual(len(original_ids), 7)

    async def test_generated_smart_title_is_valid_at_end_of_id(self):
        entry = self.make_entry(
            "entry-smart", "EGD HDO Smart (ACd4510, rel\u00e91-PV)"
        )
        for domain, key, entity_type in ENTITY_TYPES:
            with self.subTest(key=key):
                entity = await self.add_entity(domain, entity_type, entry)
                self.assertEqual(
                    entity.entity_id,
                    f"{domain}.egd_{key}_smart_acd4510_rele1_pv",
                )

    async def test_leading_egd_hdo_is_not_repeated_in_name(self):
        cases = {
            "EGD HDO Smart (ACd253)": "smart_acd253",
            "EGD HDO 59101 A1B4P06": "59101_a1b4p06",
            "EGD Chata": "chata",
            "EGD HDO": "egd_hdo",
        }
        for index, (title, name) in enumerate(cases.items()):
            entry = self.make_entry(f"entry-title-{index}", title)
            with self.subTest(title=title):
                entity = await self.add_entity(
                    "binary_sensor", binary_sensor.EGDDistribuceBinarySensor, entry
                )
                self.assertEqual(
                    entity.entity_id, f"binary_sensor.egd_hdo_status_{name}"
                )


if __name__ == "__main__":
    unittest.main()
