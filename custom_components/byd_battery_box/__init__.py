"""The BYD Battery Box integration."""

from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import BydBoxConfigEntry, BydBoxCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: BydBoxConfigEntry) -> bool:
    """Set up BYD Battery Box from a config entry."""
    coordinator = BydBoxCoordinator(hass, entry)
    # Raises ConfigEntryNotReady when the battery cannot be reached.
    await coordinator.async_config_entry_first_refresh()

    _async_set_unique_id(hass, entry, coordinator.serial)

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


def _async_set_unique_id(hass: HomeAssistant, entry: BydBoxConfigEntry, serial: str | None) -> None:
    """Add the BMU serial as unique id to entries created before it was stored."""
    if entry.unique_id is not None or not serial:
        return
    for other in hass.config_entries.async_entries(DOMAIN):
        if other.entry_id != entry.entry_id and other.unique_id == serial:
            _LOGGER.warning("BYD Battery Box %s is configured more than once", serial)
            return
    hass.config_entries.async_update_entry(entry, unique_id=serial)


async def async_unload_entry(hass: HomeAssistant, entry: BydBoxConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_shutdown()
    return unload_ok
