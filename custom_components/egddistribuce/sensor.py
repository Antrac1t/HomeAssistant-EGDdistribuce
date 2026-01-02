"""Sensor platform for EGD Distribuce."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CURRENCY_EURO
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EGDDistribuceCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EGD Distribuce sensors from a config entry."""
    coordinator: EGDDistribuceCoordinator = hass.data[DOMAIN][entry.entry_id]

    sensors = [
        EGDDistribuceCurrentPriceSensor(coordinator, entry),
        EGDDistribuceRemainingTimeSensor(coordinator, entry),
        EGDDistribuceNextChangeSensor(coordinator, entry),
    ]

    async_add_entities(sensors)


class EGDDistribuceCurrentPriceSensor(CoordinatorEntity[EGDDistribuceCoordinator], SensorEntity):
    """Sensor for current electricity price."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "Kč/kWh"

    def __init__(
        self,
        coordinator: EGDDistribuceCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        
        self._attr_unique_id = f"{entry.entry_id}_current_price"
        self._attr_name = "Aktuální cena"
        
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


class EGDDistribuceRemainingTimeSensor(CoordinatorEntity[EGDDistribuceCoordinator], SensorEntity):
    """Sensor for remaining time until next tariff change."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:clock-outline"

    def __init__(
        self,
        coordinator: EGDDistribuceCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        
        self._attr_unique_id = f"{entry.entry_id}_remaining_time"
        self._attr_name = "Zbývající čas do změny"
        
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "EGD Distribuce",
            "model": "HDO",
            "entry_type": "service",
        }

    @property
    def native_value(self) -> str | None:
        """Return the remaining time."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("remaining_time", "N/A")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        if self.coordinator.data is None:
            return {}
        
        is_active = self.coordinator.data.get("is_active", False)
        return {
            "current_state": "Nízký tarif (NT)" if is_active else "Vysoký tarif (VT)",
            "next_state": "Vysoký tarif (VT)" if is_active else "Nízký tarif (NT)",
        }


class EGDDistribuceNextChangeSensor(CoordinatorEntity[EGDDistribuceCoordinator], SensorEntity):
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
        self._attr_name = "Další HDO čas"
        
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
        
        hdo_times_today = self.coordinator.data.get("hdo_times_today", [])
        current_time = datetime.now().time()
        
        # Find next time slot today
        for slot in hdo_times_today:
            try:
                start_time = datetime.strptime(slot['od'], "%H:%M:%S").time()
                if current_time < start_time:
                    return f"{slot['od'].replace(':00', '')} - {slot['do'].replace(':00', '')}"
            except ValueError:
                continue
        
        # If no more today, show first tomorrow
        hdo_times_tomorrow = self.coordinator.data.get("hdo_times_tomorrow", [])
        if hdo_times_tomorrow:
            first_slot = hdo_times_tomorrow[0]
            return f"Zítra: {first_slot['od'].replace(':00', '')} - {first_slot['do'].replace(':00', '')}"
        
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
