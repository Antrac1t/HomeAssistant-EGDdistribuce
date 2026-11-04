"""Button platform for EGD Distribuce."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import EGDDistribuceCoordinator
from .entity import device_info, suggest_entity_id


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EGD Distribuce buttons from a config entry."""
    coordinator: EGDDistribuceCoordinator = entry.runtime_data
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
        self.entity_id = suggest_entity_id("button", "refresh_api", entry)
        self._attr_device_info = device_info(entry)

    async def async_press(self) -> None:
        """Download fresh data from the API."""
        await self._coordinator.async_refresh()
