"""Constants for the BYD Battery Box integration."""

DOMAIN = "byd_battery_box"

DEFAULT_NAME = "BYD Battery Box"
# Prefix of the unique ids used up to version 0.1.x (migrated to the BMU serial)
LEGACY_UNIQUE_ID_PREFIX = "bydb"
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_PORT = 8080
DEFAULT_UNIT_ID = 1
CONF_UNIT_ID = "unit_id"
ATTR_MANUFACTURER = "BYD"
DEFAULT_BMS_SCAN_INTERVAL = 600
DEFAULT_LOG_SCAN_INTERVAL = 600
CONF_BMS_SCAN_INTERVAL = "bms_scan_interval"
CONF_LOG_SCAN_INTERVAL = "log_scan_interval"

MIN_SCAN_INTERVAL = 10
MIN_BMS_SCAN_INTERVAL = 60
MIN_LOG_SCAN_INTERVAL = 120

DEVICE_TYPES = {
    0: "BMU",
    1: "BMS 1",
    2: "BMS 2",
    3: "BMS 3",
}
