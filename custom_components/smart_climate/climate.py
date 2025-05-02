import json
import logging
from datetime import timedelta

import voluptuous as vol

from homeassistant.components.climate import ClimateEntity, PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv

from homeassistant.components.climate.const import HVACMode, ClimateEntityFeature
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.template import Template
from homeassistant.util.dt import now
from homeassistant.helpers.event import async_track_time_interval  # <-- Import periodic tracker
from homeassistant.helpers.restore_state import RestoreEntity  # <-- Import restore state
from .const import *

_LOGGER = logging.getLogger(__name__)

# Extend the platform schema with our custom configuration.
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_MAIN_CLIMATE): cv.string,
    vol.Optional(CONF_SECONDARY_CLIMATE): cv.string,  # Made optional instead of required
    vol.Required(CONF_SENSOR): cv.string,
    vol.Optional(CONF_OUTDOOR_SENSOR): cv.string,
    vol.Optional(CONF_TEMP_THRESHOLD_PRIMARY, default=DEFAULT_TEMP_THRESHOLD_PRIMARY): vol.Coerce(float),
    vol.Optional(CONF_TEMP_THRESHOLD_SECONDARY, default=DEFAULT_TEMP_THRESHOLD_SECONDARY): vol.Coerce(float),
    vol.Optional(CONF_OUTDOOR_HOT_THRESHOLD, default=DEFAULT_OUTDOOR_HOT_THRESHOLD): vol.Coerce(float),
    vol.Optional(CONF_PRIMARY_OFFSET, default=DEFAULT_PRIMARY_OFFSET): vol.Coerce(float),
    vol.Optional(CONF_SECONDARY_OFFSET, default=DEFAULT_SECONDARY_OFFSET): vol.Coerce(float),
    vol.Optional(CONF_MAIN_MIN_TEMP, default=DEFAULT_MAIN_MIN_TEMP): vol.Coerce(float),
    vol.Optional(CONF_MAIN_MAX_TEMP, default=DEFAULT_MAIN_MAX_TEMP): vol.Coerce(float),
    vol.Optional(CONF_SECONDARY_MIN_TEMP, default=DEFAULT_SECONDARY_MIN_TEMP): vol.Coerce(float),
    vol.Optional(CONF_SECONDARY_MAX_TEMP, default=DEFAULT_SECONDARY_MAX_TEMP): vol.Coerce(float),
    vol.Optional(CONF_SECONDARY_SUPPORTS_COOLING, default=DEFAULT_SECONDARY_SUPPORTS_COOLING): cv.boolean,
    vol.Optional(CONF_HEATING_PRESETS, default=DEFAULT_HEATING_PRESETS): str,
    vol.Optional(CONF_COOLING_PRESETS, default=DEFAULT_COOLING_PRESETS): str,
})


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Smart Climate platform from a config entry."""
    config = config_entry.data
    await async_setup_platform(hass, config, async_add_entities)
    return True


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Smart Climate platform."""
    main_climate = config.get(CONF_MAIN_CLIMATE)
    secondary_climate = config.get(CONF_SECONDARY_CLIMATE)  # May be None
    sensor = config.get(CONF_SENSOR)
    outdoor_sensor = config.get(CONF_OUTDOOR_SENSOR)
    primary_threshold = config.get(CONF_TEMP_THRESHOLD_PRIMARY)
    secondary_threshold = config.get(CONF_TEMP_THRESHOLD_SECONDARY)
    heating_presets = config.get(CONF_HEATING_PRESETS, DEFAULT_HEATING_PRESETS)
    cooling_presets = config.get(CONF_COOLING_PRESETS, DEFAULT_COOLING_PRESETS)
    outdoor_hot_threshold = config.get(CONF_OUTDOOR_HOT_THRESHOLD)
    primary_offset = config.get(CONF_PRIMARY_OFFSET, DEFAULT_PRIMARY_OFFSET)
    secondary_offset = config.get(CONF_SECONDARY_OFFSET, DEFAULT_SECONDARY_OFFSET)
    main_min_temp = config.get(CONF_MAIN_MIN_TEMP, DEFAULT_MAIN_MIN_TEMP)
    main_max_temp = config.get(CONF_MAIN_MAX_TEMP, DEFAULT_MAIN_MAX_TEMP)
    secondary_min_temp = config.get(CONF_SECONDARY_MIN_TEMP, DEFAULT_SECONDARY_MIN_TEMP)
    secondary_max_temp = config.get(CONF_SECONDARY_MAX_TEMP, DEFAULT_SECONDARY_MAX_TEMP)
    secondary_supports_cooling = config.get(CONF_SECONDARY_SUPPORTS_COOLING, DEFAULT_SECONDARY_SUPPORTS_COOLING)

    if isinstance(heating_presets, str):
        heating_presets = json.loads(heating_presets)

    if isinstance(cooling_presets, str):
        cooling_presets = json.loads(cooling_presets)

    async_add_entities([
        SmartClimate(
            hass,
            main_climate,
            secondary_climate,
            sensor,
            outdoor_sensor,
            primary_threshold,
            secondary_threshold,
            heating_presets,
            cooling_presets,
            outdoor_hot_threshold,
            primary_offset,
            secondary_offset,
            main_min_temp,
            main_max_temp,
            secondary_min_temp,
            secondary_max_temp,
            secondary_supports_cooling,
        )
    ])


class SmartClimate(ClimateEntity, RestoreEntity):
    """A smart climate controller that self-manages its subdevices while always reporting 'auto'."""
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = ClimateEntityFeature.PRESET_MODE
    _attr_hvac_modes = [HVACMode.AUTO]

    def __init__(self, hass, main_climate, secondary_climate, sensor, outdoor_sensor,
                 primary_threshold, secondary_threshold, heating_presets, cooling_presets,
                 outdoor_hot_threshold, primary_offset, secondary_offset,
                 main_min_temp, main_max_temp, secondary_min_temp, secondary_max_temp,
                 secondary_supports_cooling):
        self.hass = hass
        self._main_climate = main_climate
        self._secondary_climate = secondary_climate  # May be None if not configured
        self._sensor = sensor
        self._outdoor_sensor = outdoor_sensor
        self._primary_threshold = primary_threshold
        self._secondary_threshold = secondary_threshold
        self._heating_presets = heating_presets
        self._cooling_presets = cooling_presets
        self._outdoor_hot_threshold = outdoor_hot_threshold

        # We'll check actual device states to avoid redundant service calls.

        # Offsets for target temperature.
        self._primary_offset = primary_offset
        self._secondary_offset = secondary_offset

        # Min/max temperatures for both devices
        self._main_min_temp = main_min_temp
        self._main_max_temp = main_max_temp
        self._secondary_min_temp = secondary_min_temp
        self._secondary_max_temp = secondary_max_temp

        # Flag for secondary device cooling support
        self._secondary_supports_cooling = secondary_supports_cooling

        # Attributes shown by Home Assistant.
        self._attr_target_temperature = None
        self._attr_current_temperature = None
        self._attr_hvac_mode = HVACMode.AUTO
        self._attr_preset_mode = "eco"

        self._update_unsub = None

        # Ensure the entity has a unique ID for UI management.
        if self._secondary_climate:
            self._attr_unique_id = f"smart_climate_{main_climate}_{secondary_climate}"
        else:
            self._attr_unique_id = f"smart_climate_{main_climate}"

    @property
    def name(self):
        """Return the name of the smart climate controller."""
        if self._secondary_climate:
            return f"Smart Climate ({self._main_climate} + {self._secondary_climate})"
        return f"Smart Climate ({self._main_climate})"

    @property
    def current_temperature(self):
        """Return the current indoor temperature."""
        return self._attr_current_temperature

    @property
    def target_temperature(self):
        """Return the target temperature."""
        return self._attr_target_temperature

    @property
    def preset_mode(self):
        """Return the current preset mode."""
        return self._attr_preset_mode

    @property
    def preset_modes(self):
        """Return a list of available preset modes."""
        return list({**self._heating_presets, **self._cooling_presets}.keys())

    @property
    def extra_state_attributes(self):
        return {
            "target_temperature": self._attr_target_temperature,
            "preset_mode": self._attr_preset_mode,
            "main_min_temp": self._main_min_temp,
            "main_max_temp": self._main_max_temp,
            "secondary_min_temp": self._secondary_min_temp,
            "secondary_max_temp": self._secondary_max_temp,
            "secondary_supports_cooling": self._secondary_supports_cooling,
        }

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return self._main_min_temp

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return self._main_max_temp

    @property
    def effective_main_device(self):
        """Return the entity_id of the primary climate device."""
        return self._main_climate

    @property
    def effective_secondary_device(self):
        """Return the entity_id of the secondary climate device, if configured."""
        return self._secondary_climate

    async def async_set_preset_mode(self, preset_mode):
        """Set a new preset mode and update the target temperature accordingly.
        """
        if preset_mode not in self._heating_presets and preset_mode not in self._cooling_presets:
            _LOGGER.error("Preset mode %s not recognized", preset_mode)
            return

        self._attr_preset_mode = preset_mode

        _LOGGER.debug("Preset mode set to %s; Target temp: %s", preset_mode, self._attr_target_temperature)
        await self._apply_temperature()
        self.async_write_ha_state()

    async def _apply_temperature(self):
        sensor_state = self.hass.states.get(self._sensor)
        if sensor_state is None or sensor_state.state in ["unknown", "unavailable"]:
            _LOGGER.error("Sensor %s not found or state is unknown/unavailable", self._sensor)
            return

        try:
            self._attr_current_temperature = float(sensor_state.state)
        except Exception as e:
            _LOGGER.error("Error reading sensor %s: %s", self._sensor, e)
            return

        # First check outdoor temperature to determine if it's hot or warm outside
        outdoor_temp = None
        is_hot_outside = False

        # Check if both temperatures are available before calculating the difference
        if self._attr_target_temperature is None or self._attr_current_temperature is None:
            _LOGGER.debug("Cannot calculate temperature difference: target_temp=%s, current_temp=%s", 
                         self._attr_target_temperature, self._attr_current_temperature)
            diff = 0
        else:
            diff = self._attr_target_temperature - self._attr_current_temperature

        effective_mode = HVACMode.OFF

        if self._outdoor_sensor:
            outdoor_state = self.hass.states.get(self._outdoor_sensor)
            if outdoor_state is not None and outdoor_state.state not in ["unknown", "unavailable"]:
                try:
                    outdoor_temp = float(outdoor_state.state)
                    is_hot_outside = outdoor_temp >= self._outdoor_hot_threshold
                except Exception as e:
                    _LOGGER.error("Error reading outdoor sensor %s: %s", self._outdoor_sensor, e)
            else:
                _LOGGER.error("Outdoor sensor %s not found or state is unknown/unavailable", self._outdoor_sensor)

        # Determine effective mode based on the primary threshold and outdoor temperature
        if is_hot_outside:
            if diff < -self._primary_threshold:
                effective_mode = HVACMode.COOL
                _LOGGER.debug(
                    "Using cooling instead of heating because outdoor temperature (%s) is above threshold (%s)",
                    outdoor_temp, self._outdoor_hot_threshold
                )
        else:
            if diff > self._primary_threshold:
                effective_mode = HVACMode.HEAT
                _LOGGER.debug(
                    "Using heating instead of cooling because outdoor temperature (%s) is below threshold (%s)",
                    outdoor_temp, self._outdoor_hot_threshold
                )

        if effective_mode == HVACMode.HEAT:
            self._attr_target_temperature = self._heating_presets.get(self._attr_preset_mode)
        elif effective_mode == HVACMode.COOL:
            self._attr_target_temperature = self._cooling_presets.get(self._attr_preset_mode)
        else:
            self._attr_target_temperature = None
            effective_mode = HVACMode.OFF
            _LOGGER.debug("No effective mode set; target temperature remains None")

        _LOGGER.debug(
            "Current temp: %s, Target temp: %s, Diff: %s, Effective mode: %s, Primary Threshold: %s, Secondary Threshold: %s",
            self._attr_current_temperature, self._attr_target_temperature,
            diff, effective_mode, self._primary_threshold, self._secondary_threshold
        )

        # Signal main climate device only if a change is required.
        main_state = self.hass.states.get(self.effective_main_device)
        if main_state is None:
            _LOGGER.error("Main climate device %s not found", self.effective_main_device)
            return

        if main_state.state != effective_mode:
            await self._set_effective_main_hvac_mode(effective_mode)
        else:
            _LOGGER.debug("Main device HVAC mode remains %s; no update required", effective_mode)

        if effective_mode != HVACMode.OFF and self._attr_target_temperature is not None:
            await self._set_effective_main_temperature(self._attr_target_temperature)

        # Signal secondary device only if configured and a change is required.
        if self._secondary_climate is not None:
            secondary_effective_mode = effective_mode if diff > self._secondary_threshold else HVACMode.OFF
            # Apply the secondary offset here.
            secondary_temp = None
            if secondary_effective_mode != HVACMode.OFF and self._attr_target_temperature is not None:
                secondary_temp = self._attr_target_temperature + self._secondary_offset

            secondary_state = self.hass.states.get(self.effective_secondary_device)
            if secondary_state is None:
                _LOGGER.error("Secondary climate device %s not found", self.effective_secondary_device)
            else:
                current_secondary_mode = secondary_state.state
                current_secondary_temp = secondary_state.attributes.get("temperature") if current_secondary_mode != HVACMode.OFF else None

                if (secondary_effective_mode != current_secondary_mode) or (secondary_temp != current_secondary_temp):
                    await self._set_effective_secondary(secondary_effective_mode, secondary_temp)
                else:
                    _LOGGER.debug("Secondary device state remains unchanged; no update required")

    async def _set_effective_main_temperature(self, temperature):
        # Ensure temperature is within min/max limits
        if temperature < self._main_min_temp:
            temperature = self._main_min_temp
            _LOGGER.debug("Adjusting main device temperature to minimum: %s", temperature)
        elif temperature > self._main_max_temp:
            temperature = self._main_max_temp
            _LOGGER.debug("Adjusting main device temperature to maximum: %s", temperature)

        service_data = {
            "entity_id": self.effective_main_device,
            "temperature": temperature,
        }
        _LOGGER.debug("Setting main device %s to temperature %s", self.effective_main_device, temperature)
        await self.hass.services.async_call("climate", "set_temperature", service_data)

    async def _set_effective_main_hvac_mode(self, hvac_mode):
        service_data = {
            "entity_id": self.effective_main_device,
            "hvac_mode": hvac_mode,
        }
        _LOGGER.debug("Setting main device %s to hvac_mode %s", self.effective_main_device, hvac_mode)
        await self.hass.services.async_call("climate", "set_hvac_mode", service_data)

    async def _set_effective_secondary(self, hvac_mode, temperature=None):
        if self._secondary_climate is None:
            _LOGGER.debug("No secondary device configured, skipping secondary update")
            return

        # Check if cooling is requested but not supported by secondary device
        if hvac_mode == HVACMode.COOL and not self._secondary_supports_cooling:
            _LOGGER.debug("Secondary device does not support cooling, setting to OFF instead")
            hvac_mode = HVACMode.OFF

        if hvac_mode != HVACMode.OFF and temperature is not None:
            # Ensure temperature is within min/max limits
            if temperature < self._secondary_min_temp:
                temperature = self._secondary_min_temp
                _LOGGER.debug("Adjusting secondary device temperature to minimum: %s", temperature)
            elif temperature > self._secondary_max_temp:
                temperature = self._secondary_max_temp
                _LOGGER.debug("Adjusting secondary device temperature to maximum: %s", temperature)

            service_data_temp = {
                "entity_id": self.effective_secondary_device,
                "temperature": temperature,
            }
            _LOGGER.debug("Setting secondary device %s to target temperature %s", self.effective_secondary_device, temperature)
            await self.hass.services.async_call("climate", "set_temperature", service_data_temp)

        service_data_mode = {
            "entity_id": self.effective_secondary_device,
            "hvac_mode": hvac_mode,
        }
        _LOGGER.debug("Setting secondary device %s to hvac_mode %s", self.effective_secondary_device, hvac_mode)
        await self.hass.services.async_call("climate", "set_hvac_mode", service_data_mode)

    async def async_update(self):
        sensor_state = self.hass.states.get(self._sensor)
        if sensor_state is not None and sensor_state.state not in ["unknown", "unavailable"]:
            try:
                self._attr_current_temperature = float(sensor_state.state)
            except Exception as e:
                _LOGGER.error("Error updating sensor %s: %s", self._sensor, e)
        else:
            _LOGGER.error("Sensor %s state is unknown or unavailable during update", self._sensor)

    async def async_added_to_hass(self):
        """Restore preset and target temperature on startup, then start periodic updates."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state:
            self._attr_preset_mode = last_state.attributes.get("preset_mode", "eco")
            self._attr_target_temperature = last_state.attributes.get("target_temperature", self._attr_target_temperature)
            _LOGGER.debug("Restored state: preset_mode=%s, target_temperature=%s", self._attr_preset_mode, self._attr_target_temperature)
        self._update_unsub = async_track_time_interval(
            self.hass, self._periodic_update, timedelta(seconds=60)
        )

    async def async_will_remove_from_hass(self):
        if self._update_unsub:
            self._update_unsub()
            self._update_unsub = None

    async def _periodic_update(self, now_time):
        await self._apply_temperature()
        self.async_write_ha_state()
