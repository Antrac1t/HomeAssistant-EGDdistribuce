"""Enhanced config flow supporting all HDO types."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
import aiohttp

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv

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
    CONFIG_TYPE_CLASSIC,
    CONFIG_TYPE_HDO_CODES,
    CONFIG_TYPE_SMART,
    DEFAULT_PRICE_NT,
    DEFAULT_PRICE_VT,
)

_LOGGER = logging.getLogger(__name__)

API_REGION_URL = "https://hdo.distribuce24.cz/region"


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input."""
    config_type = data.get(CONF_CONFIG_TYPE, CONFIG_TYPE_CLASSIC)
    
    if config_type == CONFIG_TYPE_SMART:
        # Smart meter - no PSC validation needed
        hdo_code = data.get(CONF_HDO_CODE, "")
        return {"title": f"EGD HDO Smart ({hdo_code})"}
    
    # Classic or HDO codes - validate PSC
    psc = data[CONF_PSC]
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_REGION_URL, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    raise CannotConnect
                
                regions_data = await response.json()
                matching_regions = [x for x in regions_data if x.get('PSC') == psc]
                
                if not matching_regions:
                    raise InvalidPSC
                    
    except aiohttp.ClientError as err:
        _LOGGER.error("Error connecting to EGD API: %s", err)
        raise CannotConnect from err
    except Exception as err:
        _LOGGER.exception("Unexpected exception: %s", err)
        raise CannotConnect from err

    # Generate title
    if config_type == CONFIG_TYPE_CLASSIC:
        title = f"EGD HDO {psc} A{data.get(CONF_CODE_A)}B{data.get(CONF_CODE_B)}P{data.get(CONF_CODE_DP)}"
    else:  # HDO_CODES
        hdo_code = data.get(CONF_HDO_CODE, "")
        title = f"EGD HDO {psc} ({hdo_code})"
        
    return {"title": title}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EGD Distribuce."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - choose configuration type."""
        if user_input is not None:
            # Store config type and proceed to specific step
            self.config_type = user_input[CONF_CONFIG_TYPE]
            
            if self.config_type == CONFIG_TYPE_CLASSIC:
                return await self.async_step_classic()
            elif self.config_type == CONFIG_TYPE_HDO_CODES:
                return await self.async_step_hdo_codes()
            else:  # SMART
                return await self.async_step_smart()
        
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_CONFIG_TYPE, default=CONFIG_TYPE_CLASSIC): vol.In({
                    CONFIG_TYPE_CLASSIC: "Klasické HDO (A+B+DP)",
                    CONFIG_TYPE_HDO_CODES: "Více HDO příkazů (kódy)",
                    CONFIG_TYPE_SMART: "Smart metr (speciální přístroje)",
                }),
            }),
        )

    async def async_step_classic(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure classic HDO with A+B+DP codes."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            user_input[CONF_CONFIG_TYPE] = CONFIG_TYPE_CLASSIC
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidPSC:
                errors["psc"] = "invalid_psc"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                unique_id = f"{user_input[CONF_PSC]}_{user_input[CONF_CODE_A]}_{user_input[CONF_CODE_B]}_{user_input[CONF_CODE_DP]}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(title=info["title"], data=user_input)

        # Dropdown options for A, B, DP
        code_a_options = {str(i): str(i) for i in range(1, 10)}  # 1-9
        code_b_options = {str(i): str(i) for i in range(1, 10)}  # 1-9
        code_dp_options = {str(i).zfill(2): str(i).zfill(2) for i in range(1, 17)}  # 01-16

        return self.async_show_form(
            step_id="classic",
            data_schema=vol.Schema({
                vol.Required(CONF_PSC): cv.string,
                vol.Required(CONF_CODE_A): vol.In(code_a_options),
                vol.Required(CONF_CODE_B): vol.In(code_b_options),
                vol.Required(CONF_CODE_DP): vol.In(code_dp_options),
                vol.Optional(CONF_PRICE_VT, default=DEFAULT_PRICE_VT): cv.positive_float,
                vol.Optional(CONF_PRICE_NT, default=DEFAULT_PRICE_NT): cv.positive_float,
            }),
            errors=errors,
        )

    async def async_step_hdo_codes(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure HDO with multiple codes (e.g., 405, 406, 410)."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            user_input[CONF_CONFIG_TYPE] = CONFIG_TYPE_HDO_CODES
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidPSC:
                errors["psc"] = "invalid_psc"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                unique_id = f"{user_input[CONF_PSC]}_{user_input[CONF_HDO_CODE]}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="hdo_codes",
            data_schema=vol.Schema({
                vol.Required(CONF_PSC): cv.string,
                vol.Required(CONF_HDO_CODE, description={"suggested_value": "405,406,410"}): cv.string,
                vol.Optional(CONF_PRICE_VT, default=DEFAULT_PRICE_VT): cv.positive_float,
                vol.Optional(CONF_PRICE_NT, default=DEFAULT_PRICE_NT): cv.positive_float,
            }),
            errors=errors,
            description_placeholders={
                "hdo_code_example": "Příklad: 405,406,410 nebo jen 405"
            },
        )

    async def async_step_smart(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure smart meter."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            user_input[CONF_CONFIG_TYPE] = CONFIG_TYPE_SMART
            user_input[CONF_PSC] = "smart"  # Set PSC to smart internally
            
            try:
                info = await validate_input(self.hass, user_input)
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                unique_id = f"smart_{user_input[CONF_HDO_CODE]}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="smart",
            data_schema=vol.Schema({
                vol.Required(CONF_HDO_CODE, description={"suggested_value": "Cd56"}): cv.string,
                vol.Optional(CONF_PRICE_VT, default=DEFAULT_PRICE_VT): cv.positive_float,
                vol.Optional(CONF_PRICE_NT, default=DEFAULT_PRICE_NT): cv.positive_float,
            }),
            errors=errors,
            description_placeholders={
                "hdo_code_example": "Příklad: Cd56, d57, ACd56"
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for EGD Distribuce."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_price_vt = self.config_entry.options.get(
            CONF_PRICE_VT, self.config_entry.data.get(CONF_PRICE_VT, DEFAULT_PRICE_VT)
        )
        current_price_nt = self.config_entry.options.get(
            CONF_PRICE_NT, self.config_entry.data.get(CONF_PRICE_NT, DEFAULT_PRICE_NT)
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(CONF_PRICE_VT, default=current_price_vt): cv.positive_float,
                vol.Optional(CONF_PRICE_NT, default=current_price_nt): cv.positive_float,
            }),
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidPSC(HomeAssistantError):
    """Error to indicate the PSC is invalid."""
