DOMAIN = "smart_climate"  # Renamed from dual_thermostat

# Configuration keys for the main and secondary climate devices.
CONF_MAIN_CLIMATE = "main_climate"
CONF_SECONDARY_CLIMATE = "secondary_climate"

# Configuration keys for sensors.
CONF_SENSOR = "sensor"  # Primary indoor sensor.
CONF_OUTDOOR_SENSOR = "outdoor_sensor"  # (Optional) Outdoor sensor.

# Configuration keys for controlling behavior.
# (Now using separate thresholds for primary and secondary devices)
CONF_TEMP_THRESHOLD_PRIMARY = "temp_threshold_primary"
CONF_TEMP_THRESHOLD_SECONDARY = "temp_threshold_secondary"
CONF_OUTDOOR_HOT_THRESHOLD = "outdoor_hot_threshold"  # e.g. 25°C or higher.

# New configuration keys for temperature offsets.
CONF_PRIMARY_OFFSET = "primary_offset"
CONF_SECONDARY_OFFSET = "secondary_offset"

# Configuration keys for min/max temperatures
CONF_MAIN_MIN_TEMP = "main_min_temp"
CONF_MAIN_MAX_TEMP = "main_max_temp"
CONF_SECONDARY_MIN_TEMP = "secondary_min_temp"
CONF_SECONDARY_MAX_TEMP = "secondary_max_temp"
CONF_SECONDARY_SUPPORTS_COOLING = "secondary_supports_cooling"

CONF_HEATING_PRESETS = "heating_presets"
CONF_COOLING_PRESETS = "cooling_presets"

# Default values.
DEFAULT_TEMP_THRESHOLD_PRIMARY = 0.0
DEFAULT_TEMP_THRESHOLD_SECONDARY = 2.0

# Special preset modes
PRESET_MODE_MANUAL = "manual"

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
    "sleep": None,
    "comfort": 24,
    "boost": 22,
    "home": 25,
    "activity": 25
}
DEFAULT_OUTDOOR_HOT_THRESHOLD = DEFAULT_COOLING_PRESETS["home"]

# Default offsets.
DEFAULT_PRIMARY_OFFSET = 1.0
DEFAULT_SECONDARY_OFFSET = 0.0

# Default min/max temperatures
DEFAULT_MAIN_MIN_TEMP = 7.0
DEFAULT_MAIN_MAX_TEMP = 35.0
DEFAULT_SECONDARY_MIN_TEMP = 7.0
DEFAULT_SECONDARY_MAX_TEMP = 35.0
DEFAULT_SECONDARY_SUPPORTS_COOLING = False
