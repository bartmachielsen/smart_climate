import logging
from typing import Optional

import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant import config_entries
from homeassistant.helpers.selector import selector
from homeassistant.core import callback
from .const import (
    DOMAIN,
    CONF_MAIN_CLIMATE,
    CONF_SECONDARY_CLIMATE,
    CONF_SENSOR,
    CONF_OUTDOOR_SENSOR,
    CONF_TEMP_THRESHOLD_PRIMARY,
    CONF_TEMP_THRESHOLD_SECONDARY,
    CONF_OUTDOOR_HOT_THRESHOLD,
    CONF_PRIMARY_HEATING_OFFSET,
    CONF_PRIMARY_COOLING_OFFSET,
    CONF_SECONDARY_HEATING_OFFSET,
    CONF_SECONDARY_COOLING_OFFSET,
    CONF_MAIN_MIN_TEMP,
    CONF_MAIN_MAX_TEMP,
    CONF_SECONDARY_MIN_TEMP,
    CONF_SECONDARY_MAX_TEMP,
    CONF_SECONDARY_SUPPORTS_COOLING,
    DEFAULT_TEMP_THRESHOLD_PRIMARY,
    DEFAULT_TEMP_THRESHOLD_SECONDARY,
    DEFAULT_OUTDOOR_HOT_THRESHOLD,
    DEFAULT_MAIN_MIN_TEMP,
    DEFAULT_MAIN_MAX_TEMP,
    DEFAULT_SECONDARY_MIN_TEMP,
    DEFAULT_SECONDARY_MAX_TEMP,
    DEFAULT_SECONDARY_SUPPORTS_COOLING, DEFAULT_PRIMARY_HEATING_OFFSET,
    DEFAULT_PRIMARY_COOLING_OFFSET, DEFAULT_SECONDARY_HEATING_OFFSET,
    DEFAULT_SECONDARY_COOLING_OFFSET
)

_LOGGER = logging.getLogger(__name__)


class SmartClimateOptionsFlow(config_entries.OptionsFlow):
    """Handle a simplified options flow for the Smart Climate integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: Optional[dict] = None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        # Fetch the current options
        current_options = self.config_entry.options

        # Build a dynamic schema using the current values as defaults.
        data_schema = vol.Schema({
            vol.Required(CONF_MAIN_CLIMATE, default=current_options.get(CONF_MAIN_CLIMATE)): selector({"entity": {"domain": "climate"}}),
            vol.Optional(CONF_SECONDARY_CLIMATE, default=current_options.get(CONF_SECONDARY_CLIMATE)): selector({"entity": {"domain": "climate"}}),
            vol.Required(CONF_SENSOR, default=current_options.get(CONF_SENSOR)): selector({"entity": {"domain": ["sensor"]}}),
            vol.Optional(CONF_OUTDOOR_SENSOR, default=current_options.get(CONF_OUTDOOR_SENSOR)): selector({"entity": {"domain": ["sensor"]}}),
            vol.Optional(CONF_TEMP_THRESHOLD_PRIMARY, default=current_options.get(CONF_TEMP_THRESHOLD_PRIMARY, DEFAULT_TEMP_THRESHOLD_PRIMARY)): vol.Coerce(float),
            vol.Optional(CONF_TEMP_THRESHOLD_SECONDARY, default=current_options.get(CONF_TEMP_THRESHOLD_SECONDARY, DEFAULT_TEMP_THRESHOLD_SECONDARY)): vol.Coerce(float),
            vol.Optional(CONF_OUTDOOR_HOT_THRESHOLD, default=current_options.get(CONF_OUTDOOR_HOT_THRESHOLD, DEFAULT_OUTDOOR_HOT_THRESHOLD)): vol.Coerce(float),
            vol.Optional(CONF_MAIN_MIN_TEMP, default=current_options.get(CONF_MAIN_MIN_TEMP, DEFAULT_MAIN_MIN_TEMP)): vol.Coerce(float),
            vol.Optional(CONF_MAIN_MAX_TEMP, default=current_options.get(CONF_MAIN_MAX_TEMP, DEFAULT_MAIN_MAX_TEMP)): vol.Coerce(float),
            vol.Optional(CONF_PRIMARY_HEATING_OFFSET, default=current_options.get(CONF_PRIMARY_HEATING_OFFSET)): vol.Coerce(float),
            vol.Optional(CONF_PRIMARY_COOLING_OFFSET, default=current_options.get(CONF_PRIMARY_COOLING_OFFSET)): vol.Coerce(float),
            vol.Optional(CONF_SECONDARY_HEATING_OFFSET, default=current_options.get(CONF_SECONDARY_HEATING_OFFSET)): vol.Coerce(float),
            vol.Optional(CONF_SECONDARY_COOLING_OFFSET, default=current_options.get(CONF_SECONDARY_COOLING_OFFSET)): vol.Coerce(float),
            vol.Optional(CONF_SECONDARY_MIN_TEMP, default=current_options.get(CONF_SECONDARY_MIN_TEMP, DEFAULT_SECONDARY_MIN_TEMP)): vol.Coerce(float),
            vol.Optional(CONF_SECONDARY_MAX_TEMP, default=current_options.get(CONF_SECONDARY_MAX_TEMP, DEFAULT_SECONDARY_MAX_TEMP)): vol.Coerce(float),
            vol.Optional(CONF_SECONDARY_SUPPORTS_COOLING, default=current_options.get(CONF_SECONDARY_SUPPORTS_COOLING, DEFAULT_SECONDARY_SUPPORTS_COOLING)): cv.boolean,
        })

        return self.async_show_form(step_id="init", data_schema=data_schema)


class SmartClimateConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Smart Climate integration."""

    VERSION = 1

    async def async_step_user(self, user_input: Optional[dict] = None):
        errors = {}
        if user_input is not None:
            return self.async_create_entry(title="Smart Climate", data=user_input)

        data_schema = vol.Schema({
            vol.Required(CONF_MAIN_CLIMATE): selector({"entity": {"domain": "climate"}}),
            vol.Optional(CONF_SECONDARY_CLIMATE): selector({"entity": {"domain": "climate"}}),
            vol.Required(CONF_SENSOR): selector({"entity": {"domain": ["sensor"]}}),
            vol.Optional(CONF_OUTDOOR_SENSOR): selector({"entity": {"domain": ["sensor"]}}),
            vol.Optional(CONF_TEMP_THRESHOLD_PRIMARY, default=DEFAULT_TEMP_THRESHOLD_PRIMARY): vol.Coerce(float),
            vol.Optional(CONF_TEMP_THRESHOLD_SECONDARY, default=DEFAULT_TEMP_THRESHOLD_SECONDARY): vol.Coerce(float),
            vol.Optional(CONF_OUTDOOR_HOT_THRESHOLD, default=DEFAULT_OUTDOOR_HOT_THRESHOLD): vol.Coerce(float),
            vol.Optional(CONF_PRIMARY_HEATING_OFFSET, default=DEFAULT_PRIMARY_HEATING_OFFSET): vol.Coerce(float),
            vol.Optional(CONF_PRIMARY_COOLING_OFFSET, default=DEFAULT_PRIMARY_COOLING_OFFSET): vol.Coerce(float),
            vol.Optional(CONF_SECONDARY_HEATING_OFFSET, default=DEFAULT_SECONDARY_HEATING_OFFSET): vol.Coerce(float),
            vol.Optional(CONF_SECONDARY_COOLING_OFFSET, default=DEFAULT_SECONDARY_COOLING_OFFSET): vol.Coerce(float),
            vol.Optional(CONF_MAIN_MIN_TEMP, default=DEFAULT_MAIN_MIN_TEMP): vol.Coerce(float),
            vol.Optional(CONF_MAIN_MAX_TEMP, default=DEFAULT_MAIN_MAX_TEMP): vol.Coerce(float),
            vol.Optional(CONF_SECONDARY_MIN_TEMP, default=DEFAULT_SECONDARY_MIN_TEMP): vol.Coerce(float),
            vol.Optional(CONF_SECONDARY_MAX_TEMP, default=DEFAULT_SECONDARY_MAX_TEMP): vol.Coerce(float),
            vol.Optional(CONF_SECONDARY_SUPPORTS_COOLING, default=DEFAULT_SECONDARY_SUPPORTS_COOLING): cv.boolean,
        })
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_import(self, user_input: dict) -> dict:
        """Import configuration from YAML if present."""
        return await self.async_step_user(user_input)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow for Smart Climate."""
        return SmartClimateOptionsFlow(config_entry)


async def async_get_options_flow(
    config_entry: config_entries.ConfigEntry,
) -> config_entries.OptionsFlow:
    """Get the options flow for Smart Climate."""
    return SmartClimateOptionsFlow(config_entry)
