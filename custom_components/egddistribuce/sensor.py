"""Sensor platform for EGD Distribuce."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CURRENCY_EURO
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import EGDDistribuceCoordinator
from .entity import EGDBaseEntity, suggest_entity_id

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EGD Distribuce sensors from a config entry."""
    coordinator: EGDDistribuceCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Remove the retired "Time Until Change" entity so it does not linger as unavailable
    registry = er.async_get(hass)
    old_entity_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_remaining_time"
    )
    if old_entity_id:
        registry.async_remove(old_entity_id)

    sensors = [
        EGDDistribuceCurrentPriceSensor(coordinator, entry),
        EGDDistribuceNextChangeTimeSensor(coordinator, entry),
        EGDDistribuceNextChangeSensor(coordinator, entry),
    ]

    async_add_entities(sensors)


class EGDDistribuceCurrentPriceSensor(EGDBaseEntity, SensorEntity):
    """Sensor for current electricity price."""

    _attr_has_entity_name = True
    # Price per kWh is not a monetary amount (HA requires an ISO 4217 unit and
    # state_class TOTAL for MONETARY), so keep no device class to allow
    # MEASUREMENT long-term statistics.
    _attr_device_class = None
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        coordinator: EGDDistribuceCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        
        self._attr_unique_id = f"{entry.entry_id}_current_price"
        self._attr_translation_key = "current_price"
        self.entity_id = suggest_entity_id("sensor", "current_price", entry)
        self._attr_native_unit_of_measurement = coordinator.price_unit
        
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "EGD Distribuce",
            "model": "HDO",
            "entry_type": "service",
        }

    @property
    def native_value(self) -> float | None:
        """Return the current price."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("current_price")

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend."""
        return "mdi:currency-eur"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        if self.coordinator.data is None:
            return {}
        
        is_active = self.coordinator.data.get("is_active", False)
        return {
            "tariff": "Nízký (NT)" if is_active else "Vysoký (VT)",
            "price_nt": self.coordinator.price_nt,
            "price_vt": self.coordinator.price_vt,
            "hourly_prices": self.coordinator.data.get("hourly_prices", {}),
        }


class EGDDistribuceNextChangeTimeSensor(EGDBaseEntity, SensorEntity):
    """Timestamp of the next HDO status change (relative time is rendered by the frontend)."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-end"

    def __init__(
        self,
        coordinator: EGDDistribuceCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self._attr_unique_id = f"{entry.entry_id}_next_hdo_change"
        self._attr_translation_key = "next_hdo_change"
        self.entity_id = suggest_entity_id("sensor", "next_hdo_change", entry)

        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "EGD Distribuce",
            "model": "HDO",
            "entry_type": "service",
        }

    @property
    def native_value(self) -> datetime | None:
        """Return when the HDO status changes next."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("next_change")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        if self.coordinator.data is None:
            return {}

        # Machine-readable tariff codes: "nt" (low) / "vt" (high)
        is_active = self.coordinator.data.get("is_active", False)
        return {
            "current_tariff": "nt" if is_active else "vt",
            "next_tariff": "vt" if is_active else "nt",
        }


class EGDDistribuceNextChangeSensor(EGDBaseEntity, SensorEntity):
    """Sensor for next HDO time slot."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:clock-time-four-outline"

    def __init__(
        self,
        coordinator: EGDDistribuceCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        
        self._attr_unique_id = f"{entry.entry_id}_next_change"
        self._attr_translation_key = "next_change"
        self.entity_id = suggest_entity_id("sensor", "next_change", entry)
        
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "EGD Distribuce",
            "model": "HDO",
            "entry_type": "service",
        }

    @property
    def native_value(self) -> str | None:
        """Return the next HDO time slot."""
        if self.coordinator.data is None:
            return None
        
        from datetime import datetime
        
        now = dt_util.now().replace(tzinfo=None)
        for interval in self.coordinator.data.get("hdo_intervals", []):
            start = datetime.fromisoformat(interval["od"])
            if start <= now:
                continue
            end = datetime.fromisoformat(interval["do"])
            text = f"{start:%H:%M} - {end:%H:%M}"
            if start.date() > now.date():
                return f"Zítra: {text}"
            return text
        
        return "Žádný plánovaný"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        if self.coordinator.data is None:
            return {}
        
        hdo_times_today = self.coordinator.data.get("hdo_times_today", [])
        hdo_times_tomorrow = self.coordinator.data.get("hdo_times_tomorrow", [])
        
        # Format all times
        def format_times(times: list, prefix: str = "") -> list[str]:
            """Format time slots."""
            formatted = []
            for slot in times:
                start = slot['od'].replace(':00', '')
                end = slot['do'].replace(':00', '')
                formatted.append(f"{prefix}{start} - {end}")
            return formatted
        
        all_times_today = format_times(hdo_times_today)
        all_times_tomorrow = format_times(hdo_times_tomorrow, "Zítra ")
        
        return {
            "all_times_today": all_times_today,
            "all_times_tomorrow": all_times_tomorrow,
            "total_slots_today": len(hdo_times_today),
            "total_slots_tomorrow": len(hdo_times_tomorrow),
        }
