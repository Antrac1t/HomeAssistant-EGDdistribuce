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

_LOGGER = logging.getLogger(__name__)

API_REGION_URL = "https://hdo.distribuce24.cz/region"


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input."""
    config_type = data.get(CONF_CONFIG_TYPE, CONFIG_TYPE_CLASSIC)

    if config_type == CONFIG_TYPE_SMART:
        hdo_code = data.get(CONF_HDO_CODE, "")
        return {"title": f"EGD HDO Smart ({hdo_code})"}

    psc = data[CONF_PSC]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_REGION_URL, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    raise CannotConnect

                regions_data = await response.json()
                matching_regions = [x for x in regions_data if x.get("PSC") == psc]

                if not matching_regions:
                    raise InvalidPSC

    except aiohttp.ClientError as err:
        _LOGGER.error("Error connecting to EGD API: %s", err)
        raise CannotConnect from err
    except Exception as err:
        _LOGGER.exception("Unexpected exception: %s", err)
        raise CannotConnect from err

    if config_type == CONFIG_TYPE_CLASSIC:
        title = f"EGD HDO {psc} A{data.get(CONF_CODE_A)}B{data.get(CONF_CODE_B)}P{data.get(CONF_CODE_DP)}"
    else:
        hdo_code = data.get(CONF_HDO_CODE, "")
        title = f"EGD HDO {psc} ({hdo_code})"

    return {"title": title}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EGD Distribuce."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self.config_type = user_input[CONF_CONFIG_TYPE]

            if self.config_type == CONFIG_TYPE_CLASSIC:
                return await self.async_step_classic()
            elif self.config_type == CONFIG_TYPE_HDO_CODES:
                return await self.async_step_hdo_codes()
            else:
                return await self.async_step_smart()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CONFIG_TYPE, default=CONFIG_TYPE_CLASSIC
                    ): vol.In(
                        {
                            CONFIG_TYPE_CLASSIC: "Klasické HDO (A+B+DP)",
                            CONFIG_TYPE_HDO_CODES: "Více HDO příkazů (kódy)",
                            CONFIG_TYPE_SMART: "Smart metr (speciální přístroje)",
                        }
                    ),
                }
            ),
        )

    async def async_step_classic(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
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
                unique_id = (
                    f"{user_input[CONF_PSC]}_{user_input[CONF_CODE_A]}_"
                    f"{user_input[CONF_CODE_B]}_{user_input[CONF_CODE_DP]}"
                )
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(title=info["title"], data=user_input)

        code_a_options = {str(i): str(i) for i in range(1, 10)}
        code_b_options = {str(i): str(i) for i in range(1, 10)}
        code_dp_options = {str(i).zfill(2): str(i).zfill(2) for i in range(1, 17)}

        return self.async_show_form(
            step_id="classic",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PSC): cv.string,
                    vol.Required(CONF_CODE_A): vol.In(code_a_options),
                    vol.Required(CONF_CODE_B): vol.In(code_b_options),
                    vol.Required(CONF_CODE_DP): vol.In(code_dp_options),
                    vol.Optional(CONF_PRICE_VT, default=DEFAULT_PRICE_VT): cv.positive_float,
                    vol.Optional(CONF_PRICE_NT, default=DEFAULT_PRICE_NT): cv.positive_float,
                    vol.Optional(
                        CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                    vol.Optional(CONF_COLOR_VT, default=DEFAULT_COLOR_VT): cv.string,
                    vol.Optional(CONF_COLOR_NT, default=DEFAULT_COLOR_NT): cv.string,
                }
            ),
            errors=errors,
        )

    async def async_step_hdo_codes(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
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
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PSC): cv.string,
                    vol.Required(CONF_HDO_CODE): cv.string,
                    vol.Optional(CONF_PRICE_VT, default=DEFAULT_PRICE_VT): cv.positive_float,
                    vol.Optional(CONF_PRICE_NT, default=DEFAULT_PRICE_NT): cv.positive_float,
                    vol.Optional(
                        CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                    vol.Optional(CONF_COLOR_VT, default=DEFAULT_COLOR_VT): cv.string,
                    vol.Optional(CONF_COLOR_NT, default=DEFAULT_COLOR_NT): cv.string,
                }
            ),
            errors=errors,
        )

    async def async_step_smart(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input[CONF_CONFIG_TYPE] = CONFIG_TYPE_SMART
            user_input[CONF_PSC] = "smart"

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
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HDO_CODE): cv.string,
                    vol.Optional(CONF_PRICE_VT, default=DEFAULT_PRICE_VT): cv.positive_float,
                    vol.Optional(CONF_PRICE_NT, default=DEFAULT_PRICE_NT): cv.positive_float,
                    vol.Optional(
                        CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                    vol.Optional(CONF_COLOR_VT, default=DEFAULT_COLOR_VT): cv.string,
                    vol.Optional(CONF_COLOR_NT, default=DEFAULT_COLOR_NT): cv.string,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for EGD Distribuce."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        # IMPORTANT: don't overwrite read-only property in parent
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_price_vt = self._config_entry.options.get(
            CONF_PRICE_VT, self._config_entry.data.get(CONF_PRICE_VT, DEFAULT_PRICE_VT)
        )
        current_price_nt = self._config_entry.options.get(
            CONF_PRICE_NT, self._config_entry.data.get(CONF_PRICE_NT, DEFAULT_PRICE_NT)
        )
        current_color_vt = self._config_entry.options.get(
            CONF_COLOR_VT, self._config_entry.data.get(CONF_COLOR_VT, DEFAULT_COLOR_VT)
        )
        current_color_nt = self._config_entry.options.get(
            CONF_COLOR_NT, self._config_entry.data.get(CONF_COLOR_NT, DEFAULT_COLOR_NT)
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_PRICE_VT, default=current_price_vt): cv.positive_float,
                    vol.Optional(CONF_PRICE_NT, default=current_price_nt): cv.positive_float,
                    vol.Optional(CONF_COLOR_VT, default=current_color_vt): cv.string,
                    vol.Optional(CONF_COLOR_NT, default=current_color_nt): cv.string,
                }
            ),
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidPSC(HomeAssistantError):
    """Error to indicate the PSC is invalid."""
