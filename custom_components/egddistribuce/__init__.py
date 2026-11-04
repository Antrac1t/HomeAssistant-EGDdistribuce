"""The EGD Distribuce integration."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_CORE_CONFIG_UPDATE, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, issue_registry as ir
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.frontend import add_extra_js_url

from .const import DOMAIN
from .coordinator import EGDDistribuceCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the EGD Distribuce component."""
    # Include the card content hash so edits are not hidden by browser caching between releases.
    card_url = "/egddistribuce_card"
    card_path = hass.config.path(f"custom_components/{DOMAIN}/hdo_chart_card.js")
    card_content = await hass.async_add_executor_job(Path(card_path).read_bytes)
    card_hash = hashlib.sha256(card_content).hexdigest()[:12]
    await hass.http.async_register_static_paths([
        StaticPathConfig(
            url_path=f"{card_url}/hdo-chart-card.js",
            path=card_path,
            cache_headers=True,
        ),
        StaticPathConfig(
            url_path=f"{card_url}/hdo_card_translations",
            path=hass.config.path(f"custom_components/{DOMAIN}/hdo_card_translations"),
            cache_headers=False,
        ),
    ])
    add_extra_js_url(hass, f"{card_url}/hdo-chart-card.js?v={card_hash}")

    _LOGGER.debug("Registered HDO Chart Card at %s (v=%s)", card_url, card_hash)
    
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EGD Distribuce from a config entry."""
    # Currency is part of the price unit; a change triggers a reload below
    currency = hass.config.currency
    coordinator = EGDDistribuceCoordinator(hass, entry)

    # Cancel the coordinator's own timers on unload/reload
    entry.async_on_unload(coordinator.async_shutdown)

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload on options change and on Home Assistant currency change
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    @callback
    def _async_core_config_updated(_event: Event) -> None:
        nonlocal currency
        if hass.config.currency == currency:
            return
        # Remember the new currency so repeated events do not reload again
        currency = hass.config.currency
        hass.config_entries.async_schedule_reload(entry.entry_id)

    entry.async_on_unload(
        hass.bus.async_listen(EVENT_CORE_CONFIG_UPDATE, _async_core_config_updated)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the repair issue that belongs to a deleted config entry."""
    ir.async_delete_issue(hass, DOMAIN, f"smart_schedule_{entry.entry_id}")


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)
