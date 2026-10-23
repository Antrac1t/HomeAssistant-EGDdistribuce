"""Button platform for EGD Distribuce."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import EGDDistribuceCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EGD Distribuce buttons from a config entry."""
    coordinator: EGDDistribuceCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EGDDistribuceRefreshButton(coordinator, entry)])


class EGDDistribuceRefreshButton(ButtonEntity):
    """Button that forces an immediate download of HDO data from the API."""

    _attr_has_entity_name = True
    _attr_translation_key = "refresh_api"
    _attr_icon = "mdi:cloud-refresh"

    def __init__(
        self,
        coordinator: EGDDistribuceCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the button."""
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_refresh_api"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "EGD Distribuce",
            "model": "HDO",
            "entry_type": "service",
        }

    async def async_press(self) -> None:
        """Download fresh data from the API."""
        await self._coordinator.async_refresh()
