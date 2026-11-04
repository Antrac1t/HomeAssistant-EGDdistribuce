"""Binary sensor platform for EGD Distribuce."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from .coordinator import EGDDistribuceCoordinator
from .entity import EGDBaseEntity, format_slots

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EGD Distribuce binary sensor from a config entry."""
    coordinator: EGDDistribuceCoordinator = entry.runtime_data

    async_add_entities([
        EGDDistribuceBinarySensor(coordinator, entry),
        EGDDistribuceTimesChangeBinarySensor(coordinator, entry),
        EGDDistribuceUpdateStatusBinarySensor(coordinator, entry)
    ])


class EGDDistribuceBinarySensor(EGDBaseEntity, BinarySensorEntity):
    """Representation of an EGD Distribuce HDO binary sensor."""

    _platform = "binary_sensor"
    _attr_translation_key = "hdo_status"
    _attr_device_class = BinarySensorDeviceClass.POWER
    # Large schedule attributes change on every recalculation; keep them out
    # of the recorder database.
    _unrecorded_attributes = frozenset({
        "HDO_HOURLY",
        "hdo_intervals",
        "hdo_times_today_raw",
        "hdo_times_tomorrow_raw",
        "hdo_cas_od",
        "hdo_cas_do",
    })

    @property
    def is_on(self) -> bool:
        """Return true if HDO is active (low tariff)."""
        if self.coordinator.data is None:
            return False
        return self.coordinator.data.get("is_active", False)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        if self.coordinator.data is None:
            return {}

        hdo_times_today = self.coordinator.data.get("hdo_times_today", [])
        hdo_times_tomorrow = self.coordinator.data.get("hdo_times_tomorrow", [])

        next_change = self.coordinator.data.get("next_change")
        attributes = {
            "hdo_times_today": format_slots(hdo_times_today),
            "hdo_times_tomorrow": format_slots(hdo_times_tomorrow),
            "hdo_cas_od": [slot['od'] for slot in hdo_times_today],
            "hdo_cas_do": [slot['do'] for slot in hdo_times_today],
            "next_change": next_change.isoformat() if next_change else None,
            "current_price": self.coordinator.data.get("current_price", 0),
            "region": self.coordinator.data.get("region", "N/A"),
            "price_vt": self.coordinator.price_vt,
            "price_nt": self.coordinator.price_nt,
            "price_unit": self.coordinator.price_unit,
            "color_vt": self.coordinator.color_vt,
            "color_nt": self.coordinator.color_nt,
            "HDO_HOURLY": self.coordinator.data.get("HDO_HOURLY", {}),
        }

        # Add raw time data for automations
        attributes["hdo_times_today_raw"] = hdo_times_today
        attributes["hdo_times_tomorrow_raw"] = hdo_times_tomorrow
        attributes["hdo_intervals"] = self.coordinator.data.get("hdo_intervals", [])

        return attributes



class EGDDistribuceTimesChangeBinarySensor(EGDBaseEntity, BinarySensorEntity):
    """Binary sensor indicating if HDO times change between today and tomorrow."""

    _platform = "binary_sensor"
    _attr_translation_key = "hdo_times_change"

    @property
    def is_on(self) -> bool:
        """Return true if HDO times will change tomorrow."""
        if self.coordinator.data is None:
            return False

        # The coordinator returns both lists sorted by start time
        today = self.coordinator.data.get("hdo_times_today", [])
        tomorrow = self.coordinator.data.get("hdo_times_tomorrow", [])
        return bool(today and tomorrow and today != tomorrow)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        if self.coordinator.data is None:
            return {}

        hdo_times_today = self.coordinator.data.get("hdo_times_today", [])
        hdo_times_tomorrow = self.coordinator.data.get("hdo_times_tomorrow", [])

        return {
            "times_today": format_slots(hdo_times_today),
            "times_tomorrow": format_slots(hdo_times_tomorrow),
        }


class EGDDistribuceUpdateStatusBinarySensor(EGDBaseEntity, BinarySensorEntity):
    """API update status."""

    _platform = "binary_sensor"
    _attr_translation_key = "update_status"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success and not self.coordinator.last_update_cached

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self.coordinator.last_update_success:
            if self.coordinator.last_update_cached:
                state = "cache"
            else:
                state = "online"
        else:
            state = "offline"
        return {
            "status": state,
            "last_update": self.coordinator.last_successful_update,
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return True