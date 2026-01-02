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
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EGDDistribuceCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EGD Distribuce binary sensor from a config entry."""
    coordinator: EGDDistribuceCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([EGDDistribuceBinarySensor(coordinator, entry)])


class EGDDistribuceBinarySensor(CoordinatorEntity[EGDDistribuceCoordinator], BinarySensorEntity):
    """Representation of an EGD Distribuce HDO binary sensor."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.POWER

    def __init__(
        self,
        coordinator: EGDDistribuceCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        
        self._attr_unique_id = f"{entry.entry_id}_hdo_status"
        self._attr_name = "HDO Status"
        
        # Device info for grouping entities
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "EGD Distribuce",
            "model": "HDO",
            "entry_type": "service",
        }

    @property
    def is_on(self) -> bool:
        """Return true if HDO is active (low tariff)."""
        if self.coordinator.data is None:
            return False
        return self.coordinator.data.get("is_active", False)

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend."""
        return "mdi:transmission-tower" if self.is_on else "mdi:transmission-tower-off"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        if self.coordinator.data is None:
            return {}

        hdo_times_today = self.coordinator.data.get("hdo_times_today", [])
        hdo_times_tomorrow = self.coordinator.data.get("hdo_times_tomorrow", [])

        # Format times for display
        def format_times(times: list) -> str:
            """Format time slots for display."""
            if not times:
                return "Žádné"
            formatted = []
            for slot in times:
                start = slot['od'].replace(':00', '')
                end = slot['do'].replace(':00', '')
                formatted.append(f"{start}-{end}")
            return ", ".join(formatted)

        attributes = {
            "hdo_times_today": format_times(hdo_times_today),
            "hdo_times_tomorrow": format_times(hdo_times_tomorrow),
            "hdo_cas_od": [slot['od'] for slot in hdo_times_today],
            "hdo_cas_do": [slot['do'] for slot in hdo_times_today],
            "remaining_time": self.coordinator.data.get("remaining_time", "N/A"),
            "current_price": self.coordinator.data.get("current_price", 0),
            "region": self.coordinator.data.get("region", "N/A"),
            "price_vt": self.coordinator.price_vt,
            "price_nt": self.coordinator.price_nt,
        }

        # Add raw time data for automations
        attributes["hdo_times_today_raw"] = hdo_times_today
        attributes["hdo_times_tomorrow_raw"] = hdo_times_tomorrow

        return attributes

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self.coordinator.data is not None
