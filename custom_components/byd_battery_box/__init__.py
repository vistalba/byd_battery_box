"""The BYD Battery Box integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from . import hub
from .const import (
    CONF_BMS_SCAN_INTERVAL,
    CONF_LOG_SCAN_INTERVAL,
    CONF_UNIT_ID,
    DEFAULT_BMS_SCAN_INTERVAL,
    DEFAULT_LOG_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT_ID,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BUTTON]

type HubConfigEntry = ConfigEntry[hub.Hub]


async def async_setup_entry(hass: HomeAssistant, entry: HubConfigEntry) -> bool:
    """Set up BYD Battery Box from a config entry."""
    name = entry.data[CONF_NAME]
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    unit_id = entry.data.get(CONF_UNIT_ID, DEFAULT_UNIT_ID)
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    scan_interval_bms = entry.data.get(CONF_BMS_SCAN_INTERVAL, DEFAULT_BMS_SCAN_INTERVAL)
    scan_interval_log = entry.data.get(CONF_LOG_SCAN_INTERVAL, DEFAULT_LOG_SCAN_INTERVAL)

    _LOGGER.debug("Setup %s.%s", DOMAIN, name)

    byd_hub = hub.Hub(
        hass=hass,
        name=name,
        host=host,
        port=port,
        unit_id=unit_id,
        scan_interval=scan_interval,
        scan_interval_bms=scan_interval_bms,
        scan_interval_log=scan_interval_log,
        entry=entry,
    )

    try:
        await byd_hub.init_data()
    except Exception as err:
        await byd_hub.close()
        raise ConfigEntryNotReady(f"Unable to connect to BYD Battery Box at {host}:{port}: {err}") from err

    _async_set_unique_id(hass, entry, byd_hub.serial)

    entry.runtime_data = byd_hub
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


def _async_set_unique_id(hass: HomeAssistant, entry: ConfigEntry, serial: str | None) -> None:
    """Add the BMU serial as unique id to entries created before it was stored."""
    if entry.unique_id is not None or not serial:
        return
    for other in hass.config_entries.async_entries(DOMAIN):
        if other.entry_id != entry.entry_id and other.unique_id == serial:
            _LOGGER.warning("BYD Battery Box %s is configured more than once", serial)
            return
    hass.config_entries.async_update_entry(entry, unique_id=serial)


async def async_unload_entry(hass: HomeAssistant, entry: HubConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.close()
    return unload_ok
