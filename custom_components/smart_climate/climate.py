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

_LOGGER = logging.getLogger(__name__)

DOMAIN = "smart_climate"  # Renamed from dual_thermostat

# Configuration keys for the main and secondary climate devices.
CONF_MAIN_CLIMATE = "main_climate"
CONF_SECONDARY_CLIMATE = "secondary_climate"

# Configuration keys for sensors.
CONF_SENSOR = "sensor"  # Primary indoor sensor.
CONF_OUTDOOR_SENSOR = "outdoor_sensor"  # (Optional) Outdoor sensor.
CONF_MIN_RUNTIME = "min_runtime_seconds"  # Minimum runtime before turning off

# Configuration keys for controlling behavior.
# (Now using separate thresholds for primary and secondary devices)
CONF_TEMP_THRESHOLD_PRIMARY = "temp_threshold_primary"
CONF_TEMP_THRESHOLD_SECONDARY = "temp_threshold_secondary"
CONF_MODE_SYNC_TEMPLATE = "mode_sync_template"  # Template to force both devices to run in the same mode.
CONF_OUTDOOR_HOT_THRESHOLD = "outdoor_hot_threshold"  # e.g. 25°C or higher.
CONF_OUTDOOR_COLD_THRESHOLD = "outdoor_cold_threshold"  # e.g. 10°C or lower.

# New configuration keys for temperature offsets.
CONF_PRIMARY_OFFSET = "primary_offset"
CONF_SECONDARY_OFFSET = "secondary_offset"

# Default values.
DEFAULT_TEMP_THRESHOLD_PRIMARY = 1.0
DEFAULT_TEMP_THRESHOLD_SECONDARY = 2.0
DEFAULT_HEATING_PRESETS = {
    "none": None,
    "eco": 15,
    "away": 15,
    "sleep": 15,
    "comfort": 20,
    "boost": 24,
    "home": 18,
    "activity": 18
}
DEFAULT_COOLING_PRESETS = {
    "none": None,
    "eco": None,
    "away": None,
    "sleep": 30,
    "comfort": 24,
    "boost": 22,
    "home": 26,
    "activity": 26
}
DEFAULT_OUTDOOR_HOT_THRESHOLD = DEFAULT_COOLING_PRESETS["comfort"]
DEFAULT_OUTDOOR_COLD_THRESHOLD = DEFAULT_HEATING_PRESETS["comfort"]
DEFAULT_MIN_RUNTIME = 300  # 5 minutes

# Default offsets.
DEFAULT_PRIMARY_OFFSET = 1.0
DEFAULT_SECONDARY_OFFSET = 0.0

# Extend the platform schema with our custom configuration.
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_MAIN_CLIMATE): cv.string,
    vol.Optional(CONF_SECONDARY_CLIMATE): cv.string,  # Made optional instead of required
    vol.Required(CONF_SENSOR): cv.string,
    vol.Optional(CONF_OUTDOOR_SENSOR): cv.string,
    vol.Optional(CONF_TEMP_THRESHOLD_PRIMARY, default=DEFAULT_TEMP_THRESHOLD_PRIMARY): vol.Coerce(float),
    vol.Optional(CONF_TEMP_THRESHOLD_SECONDARY, default=DEFAULT_TEMP_THRESHOLD_SECONDARY): vol.Coerce(float),
    vol.Optional(CONF_MODE_SYNC_TEMPLATE): cv.template,
    vol.Optional(CONF_OUTDOOR_HOT_THRESHOLD, default=DEFAULT_OUTDOOR_HOT_THRESHOLD): vol.Coerce(float),
    vol.Optional(CONF_OUTDOOR_COLD_THRESHOLD, default=DEFAULT_OUTDOOR_COLD_THRESHOLD): vol.Coerce(float),
    vol.Optional(CONF_MIN_RUNTIME, default=DEFAULT_MIN_RUNTIME): vol.Coerce(int),
    vol.Optional(CONF_PRIMARY_OFFSET, default=DEFAULT_PRIMARY_OFFSET): vol.Coerce(float),
    vol.Optional(CONF_SECONDARY_OFFSET, default=DEFAULT_SECONDARY_OFFSET): vol.Coerce(float),
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
    heating_presets = DEFAULT_HEATING_PRESETS
    cooling_presets = DEFAULT_COOLING_PRESETS
    outdoor_hot_threshold = config.get(CONF_OUTDOOR_HOT_THRESHOLD)
    outdoor_cold_threshold = config.get(CONF_OUTDOOR_COLD_THRESHOLD)
    min_runtime = config.get(CONF_MIN_RUNTIME, DEFAULT_MIN_RUNTIME)
    primary_offset = config.get(CONF_PRIMARY_OFFSET, DEFAULT_PRIMARY_OFFSET)
    secondary_offset = config.get(CONF_SECONDARY_OFFSET, DEFAULT_SECONDARY_OFFSET)

    mode_sync_template = config.get(CONF_MODE_SYNC_TEMPLATE)
    if mode_sync_template:
        mode_sync_template = Template(mode_sync_template, hass)

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
            mode_sync_template,
            outdoor_hot_threshold,
            outdoor_cold_threshold,
            min_runtime,
            primary_offset,
            secondary_offset,
        )
    ])


class SmartClimate(ClimateEntity, RestoreEntity):
    """A smart climate controller that self-manages its subdevices while always reporting 'auto'."""
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = ClimateEntityFeature.PRESET_MODE
    _attr_hvac_modes = [HVACMode.AUTO]

    def __init__(self, hass, main_climate, secondary_climate, sensor, outdoor_sensor,
                 primary_threshold, secondary_threshold, heating_presets, cooling_presets,
                 mode_sync_template, outdoor_hot_threshold, outdoor_cold_threshold, min_runtime,
                 primary_offset, secondary_offset):
        self.hass = hass
        self._main_climate = main_climate
        self._secondary_climate = secondary_climate  # May be None if not configured
        self._sensor = sensor
        self._outdoor_sensor = outdoor_sensor
        self._primary_threshold = primary_threshold
        self._secondary_threshold = secondary_threshold
        self._heating_presets = heating_presets
        self._cooling_presets = cooling_presets
        self._mode_sync_template = mode_sync_template
        self._outdoor_hot_threshold = outdoor_hot_threshold
        self._outdoor_cold_threshold = outdoor_cold_threshold
        self._min_runtime = timedelta(seconds=min_runtime)
        self._last_switch_time = now() - self._min_runtime  # Allow immediate first switch

        # Track last commands sent to avoid redundant service calls.
        self._last_main_mode = HVACMode.OFF
        self._last_main_temp = None
        self._last_secondary_mode = HVACMode.OFF
        self._last_secondary_temp = None

        # Offsets for target temperature.
        self._primary_offset = primary_offset
        self._secondary_offset = secondary_offset

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
        }

    def _evaluate_mode_sync(self):
        """Evaluate the mode_sync template if provided."""
        if self._mode_sync_template is not None:
            try:
                result = self._mode_sync_template.async_render(parse_result=False)
                if result in ["heat", "cool"]:
                    return result
            except Exception as e:
                _LOGGER.error("Error evaluating mode_sync_template: %s", e)
        return None

    @property
    def effective_main_device(self):
        """Return the entity_id of the primary climate device."""
        return self._main_climate

    @property
    def effective_secondary_device(self):
        """Return the entity_id of the secondary climate device, if configured."""
        return self._secondary_climate

    async def async_set_temperature(self, **kwargs):
        """Set a new target temperature (manual override)."""
        temperature = kwargs.get("temperature")
        if temperature is None:
            return

        self._attr_target_temperature = temperature
        await self._apply_temperature()
        self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode):
        """Set a new preset mode and update the target temperature accordingly.

        When switching presets, the min_runtime requirement is skipped.
        """
        if preset_mode not in self._heating_presets and preset_mode not in self._cooling_presets:
            _LOGGER.error("Preset mode %s not recognized", preset_mode)
            return

        self._attr_preset_mode = preset_mode

        sensor_state = self.hass.states.get(self._sensor)
        current_temp = None
        if sensor_state is not None and sensor_state.state not in ["unknown", "unavailable"]:
            try:
                current_temp = float(sensor_state.state)
            except Exception as e:
                _LOGGER.error("Error reading sensor %s: %s", self._sensor, e)

        if current_temp is not None and preset_mode in self._heating_presets and preset_mode in self._cooling_presets:
            heating_target = self._heating_presets[preset_mode]
            cooling_target = self._cooling_presets[preset_mode]
            if heating_target is None:
                self._attr_target_temperature = cooling_target
            elif cooling_target is None:
                self._attr_target_temperature = heating_target
            else:
                midpoint = (heating_target + cooling_target) / 2
                if current_temp < midpoint:
                    self._attr_target_temperature = heating_target
                else:
                    self._attr_target_temperature = cooling_target
        elif preset_mode in self._heating_presets:
            self._attr_target_temperature = self._heating_presets[preset_mode]
        elif preset_mode in self._cooling_presets:
            self._attr_target_temperature = self._cooling_presets[preset_mode]

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

        if self._attr_target_temperature is None:
            _LOGGER.debug("No target temperature set (preset mode None); turning off HVAC devices")
            if self._last_main_mode != HVACMode.OFF:
                await self._set_effective_main_hvac_mode(HVACMode.OFF)
                self._last_main_mode = HVACMode.OFF
            if self._secondary_climate is not None and self._last_secondary_mode != HVACMode.OFF:
                await self._set_effective_secondary(HVACMode.OFF)
                self._last_secondary_mode = HVACMode.OFF
            return

        now_time = now()

        # Determine effective mode based on the primary threshold.
        if self._attr_current_temperature < self._attr_target_temperature - self._primary_threshold:
            effective_mode = HVACMode.HEAT
            diff = self._attr_target_temperature - self._attr_current_temperature
        elif self._attr_current_temperature > self._attr_target_temperature + self._primary_threshold:
            diff = self._attr_current_temperature - self._attr_target_temperature
            if self._outdoor_sensor:
                outdoor_state = self.hass.states.get(self._outdoor_sensor)
                if outdoor_state is not None and outdoor_state.state not in ["unknown", "unavailable"]:
                    try:
                        outdoor_temp = float(outdoor_state.state)
                    except Exception as e:
                        _LOGGER.error("Error reading outdoor sensor %s: %s", self._outdoor_sensor, e)
                        outdoor_temp = None
                else:
                    _LOGGER.error("Outdoor sensor %s not found or state is unknown/unavailable", self._outdoor_sensor)
                    outdoor_temp = None

                if outdoor_temp is not None and outdoor_temp >= self._outdoor_hot_threshold:
                    effective_mode = HVACMode.COOL
                else:
                    _LOGGER.debug(
                        "Cooling suppressed: outdoor temperature (%s) below threshold (%s)",
                        outdoor_temp, self._outdoor_hot_threshold
                    )
                    effective_mode = HVACMode.OFF
            else:
                effective_mode = HVACMode.COOL
        else:
            effective_mode = HVACMode.OFF
            diff = 0

        _LOGGER.debug(
            "Current temp: %s, Target temp: %s, Diff: %s, Effective mode: %s",
            self._attr_current_temperature, self._attr_target_temperature, diff, effective_mode
        )

        # Signal main climate device only if a change is required.
        if effective_mode != self._last_main_mode:
            await self._set_effective_main_hvac_mode(effective_mode)
            self._last_main_mode = effective_mode
        else:
            _LOGGER.debug("Main device HVAC mode remains %s; no update required", effective_mode)

        if effective_mode != HVACMode.OFF and self._attr_target_temperature is not None:
            # Apply the primary offset here.
            main_target = self._attr_target_temperature + self._primary_offset
            if self._last_main_temp != main_target:
                await self._set_effective_main_temperature(main_target)
                self._last_main_temp = main_target
            else:
                _LOGGER.debug("Main device temperature remains %s; no update required", main_target)

        # Signal secondary device only if configured and a change is required.
        if self._secondary_climate is not None:
            secondary_effective_mode = effective_mode if diff > self._secondary_threshold else HVACMode.OFF
            # Apply the secondary offset here.
            secondary_temp = (self._attr_target_temperature + self._secondary_offset) if secondary_effective_mode != HVACMode.OFF else None
            if (secondary_effective_mode != self._last_secondary_mode) or (secondary_temp != self._last_secondary_temp):
                await self._set_effective_secondary(secondary_effective_mode, secondary_temp)
                self._last_secondary_mode = secondary_effective_mode
                self._last_secondary_temp = secondary_temp
            else:
                _LOGGER.debug("Secondary device state remains unchanged; no update required")

        if effective_mode != HVACMode.OFF:
            self._last_switch_time = now_time

    async def _set_effective_main_temperature(self, temperature):
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
        if hvac_mode != HVACMode.OFF and temperature is not None:
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
