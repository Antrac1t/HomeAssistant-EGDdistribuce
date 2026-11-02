"""Enhanced config flow supporting all HDO types."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
import aiohttp

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .download import Download
from .schedules import default_schedule, match_code, schedule_labels, smart_codes
from .const import (
    DOMAIN,
    CONF_PSC,
    CONF_CODE_A,
    CONF_CODE_B,
    CONF_CODE_DP,
    CONF_HDO_CODE,
    CONF_SCHEDULE,
    CONF_PRICE_NT,
    CONF_PRICE_VT,
    CONF_CONFIG_TYPE,
    CONF_COLOR_VT,
    CONF_COLOR_NT,
    CONFIG_TYPE_CLASSIC,
    CONFIG_TYPE_HDO_CODES,
    CONFIG_TYPE_SMART,
    DEFAULT_PRICE_NT,
    DEFAULT_PRICE_VT,
    DEFAULT_COLOR_VT,
    DEFAULT_COLOR_NT,
)

_LOGGER = logging.getLogger(__name__)

API_REGION_URL = "https://hdo.distribuce24.cz/region"
API_HDO_URL = "https://hdo.distribuce24.cz/casy"

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input."""
    config_type = data.get(CONF_CONFIG_TYPE, CONFIG_TYPE_CLASSIC)

    if config_type == CONFIG_TYPE_SMART:
        hdo_code = data.get(CONF_HDO_CODE, "")
        schedule = data.get(CONF_SCHEDULE)
        if schedule:
            # Show relay and purpose, e.g. "C45d,D45d-relé1-PV" -> "relé1-PV"
            return {"title": f"EGD HDO Smart ({hdo_code}, {schedule.split('-', 1)[-1]})"}
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

    def __init__(self) -> None:
        self._hdo_data: list[dict[str, Any]] | None = None
        self._smart_input: dict[str, Any] = {}
        self._schedule_labels: list[str] = []

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
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                CONFIG_TYPE_CLASSIC,
                                CONFIG_TYPE_HDO_CODES,
                                CONFIG_TYPE_SMART,
                            ],
                            translation_key="config_type",
                            mode=SelectSelectorMode.DROPDOWN,
                        )
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
                    vol.Optional(CONF_COLOR_VT, default=DEFAULT_COLOR_VT): cv.string,
                    vol.Optional(CONF_COLOR_NT, default=DEFAULT_COLOR_NT): cv.string,
                }
            ),
            errors=errors,
            description_placeholders={"currency": self.hass.config.currency},
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
                    vol.Optional(CONF_COLOR_VT, default=DEFAULT_COLOR_VT): cv.string,
                    vol.Optional(CONF_COLOR_NT, default=DEFAULT_COLOR_NT): cv.string,
                }
            ),
            errors=errors,
            description_placeholders={"currency": self.hass.config.currency},
        )

    async def async_step_smart(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if self._hdo_data is None:
            try:
                async with asyncio.timeout(30):
                    self._hdo_data, _ = await Download.get_json(
                        hass=self.hass,
                        session=async_get_clientsession(self.hass),
                        url=API_HDO_URL,
                        file="hdo",
                        use_cache_on_error=False,
                    )
            except Exception:
                _LOGGER.exception("Failed to download HDO data")
                return self.async_abort(reason="cannot_connect")

        errors: dict[str, str] = {}
        codes = smart_codes(self._hdo_data)
        typed = ""

        if user_input is not None:
            typed = user_input[CONF_HDO_CODE]
            code = match_code(codes, typed)
            if code is None:
                errors[CONF_HDO_CODE] = "unknown_code"
            else:
                self._smart_input = {
                    CONF_CONFIG_TYPE: CONFIG_TYPE_SMART,
                    CONF_PSC: "smart",
                    CONF_HDO_CODE: code,
                }
                records = [x for x in self._hdo_data if x.get("kodHdo_A") == code]
                self._schedule_labels = schedule_labels(records)
                return await self.async_step_smart_settings()

        return self.async_show_form(
            step_id="smart",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HDO_CODE, default=typed or vol.UNDEFINED
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=codes,
                            # Custom value makes the frontend picker searchable;
                            # the typed code is validated above.
                            custom_value=True,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_smart_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Relay schedule (only for codes that have several) and price/colour settings."""
        if user_input is not None:
            self._smart_input.update(user_input)
            return await self._async_create_smart_entry()

        fields: dict[Any, Any] = {}
        if len(self._schedule_labels) > 1:
            fields[
                vol.Required(
                    CONF_SCHEDULE, default=default_schedule(self._schedule_labels)
                )
            ] = SelectSelector(
                SelectSelectorConfig(
                    options=self._schedule_labels,
                    custom_value=False,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        fields.update(
            {
                vol.Optional(CONF_PRICE_VT, default=DEFAULT_PRICE_VT): cv.positive_float,
                vol.Optional(CONF_PRICE_NT, default=DEFAULT_PRICE_NT): cv.positive_float,
                vol.Optional(CONF_COLOR_VT, default=DEFAULT_COLOR_VT): cv.string,
                vol.Optional(CONF_COLOR_NT, default=DEFAULT_COLOR_NT): cv.string,
            }
        )
        return self.async_show_form(
            step_id="smart_settings",
            data_schema=vol.Schema(fields),
            description_placeholders={
                "code": self._smart_input[CONF_HDO_CODE],
                "currency": self.hass.config.currency,
            },
        )

    async def _async_create_smart_entry(self) -> FlowResult:
        data = self._smart_input
        info = await validate_input(self.hass, data)
        code = data[CONF_HDO_CODE]
        schedule = data.get(CONF_SCHEDULE)
        if schedule == default_schedule(self._schedule_labels) and any(
            entry.unique_id == f"smart_{code}"
            for entry in self.hass.config_entries.async_entries(DOMAIN)
        ):
            return self.async_abort(reason="already_configured")

        await self.async_set_unique_id(
            f"smart_{code}_{schedule}" if schedule else f"smart_{code}"
        )
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=info["title"], data=data)

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
            description_placeholders={"currency": self.hass.config.currency},
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidPSC(HomeAssistantError):
    """Error to indicate the PSC is invalid."""
