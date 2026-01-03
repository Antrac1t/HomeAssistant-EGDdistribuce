"""The EGD Distribuce integration."""
from __future__ import annotations

import logging
import os

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.components.http import StaticPathConfig

from .const import (
    DOMAIN,
    CONF_PSC,
    CONF_CODE_A,
    CONF_CODE_B,
    CONF_CODE_DP,
    CONF_HDO_CODE,
    CONF_PRICE_NT,
    CONF_PRICE_VT,
    CONF_CONFIG_TYPE,
    CONF_UPDATE_INTERVAL,
    CONF_COLOR_VT,
    CONF_COLOR_NT,
    CONFIG_TYPE_CLASSIC,
    CONFIG_TYPE_HDO_CODES,
    CONFIG_TYPE_SMART,
    DEFAULT_PRICE_NT,
    DEFAULT_PRICE_VT,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_COLOR_VT,
    DEFAULT_COLOR_NT,
)
from .coordinator import EGDDistribuceCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the EGD Distribuce component."""
    # Register custom Lovelace card
    await hass.http.async_register_static_paths([
        StaticPathConfig(
            url_path="/egddistribuce_card/hdo-chart-card.js",
            path=hass.config.path(f"custom_components/{DOMAIN}/hdo_chart_card.js"),
            cache_headers=True,
        )
    ])
    
    _LOGGER.info("Registered HDO Chart Card at /egddistribuce_card/hdo-chart-card.js")
    
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EGD Distribuce from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Get configuration type
    config_type = entry.data.get(CONF_CONFIG_TYPE, CONFIG_TYPE_CLASSIC)
    
    # Get common config
    price_nt = entry.options.get(
        CONF_PRICE_NT,
        entry.data.get(CONF_PRICE_NT, DEFAULT_PRICE_NT)
    )
    price_vt = entry.options.get(
        CONF_PRICE_VT,
        entry.data.get(CONF_PRICE_VT, DEFAULT_PRICE_VT)
    )
    update_interval = entry.options.get(
        CONF_UPDATE_INTERVAL,
        entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    )
    color_vt = entry.options.get(
        CONF_COLOR_VT,
        entry.data.get(CONF_COLOR_VT, DEFAULT_COLOR_VT)
    )
    color_nt = entry.options.get(
        CONF_COLOR_NT,
        entry.data.get(CONF_COLOR_NT, DEFAULT_COLOR_NT)
    )

    # Get type-specific config
    psc = entry.data.get(CONF_PSC)
    code_a = entry.data.get(CONF_CODE_A)
    code_b = entry.data.get(CONF_CODE_B)
    code_dp = entry.data.get(CONF_CODE_DP)
    hdo_code = entry.data.get(CONF_HDO_CODE)

    # Create coordinator
    coordinator = EGDDistribuceCoordinator(
        hass,
        config_type=config_type,
        psc=psc,
        code_a=code_a,
        code_b=code_b,
        code_dp=code_dp,
        hdo_code=hdo_code,
        price_nt=float(price_nt),
        price_vt=float(price_vt),
        update_interval=int(update_interval),
        color_vt=str(color_vt),
        color_nt=str(color_nt),
    )

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Setup options update listener
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)
