"""The BYD Battery Box integration."""

from __future__ import annotations

import logging

from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import DEFAULT_NAME, DOMAIN, LEGACY_UNIQUE_ID_PREFIX
from .coordinator import BydBoxConfigEntry, BydBoxCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: BydBoxConfigEntry) -> bool:
    """Set up BYD Battery Box from a config entry."""
    coordinator = BydBoxCoordinator(hass, entry)
    # Raises ConfigEntryNotReady when the battery cannot be reached.
    await coordinator.async_config_entry_first_refresh()

    _async_set_unique_id(hass, entry, coordinator.serial)
    _async_migrate_registry(hass, entry, coordinator)

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


@callback
def _async_migrate_registry(hass: HomeAssistant, entry: BydBoxConfigEntry, coordinator: BydBoxCoordinator) -> None:
    """Migrate unique ids and device identifiers of version 0.1.x.

    Up to version 0.1.x unique ids were ``bydb_<key>`` (not unique across several
    batteries) and device identifiers were derived from the configured name.
    Both are now based on the BMU serial. Entity ids and history are kept.
    """
    prefix = coordinator.unique_prefix
    ent_reg = er.async_get(hass)
    legacy_prefix = f"{LEGACY_UNIQUE_ID_PREFIX}_"
    for entity_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if not entity_entry.unique_id.startswith(legacy_prefix):
            continue
        new_unique_id = f"{prefix}_{entity_entry.unique_id.removeprefix(legacy_prefix)}"
        if ent_reg.async_get_entity_id(entity_entry.domain, DOMAIN, new_unique_id):
            _LOGGER.warning(
                "Cannot migrate unique id of %s, %s already exists", entity_entry.entity_id, new_unique_id
            )
            continue
        _LOGGER.debug("Migrating unique id of %s to %s", entity_entry.entity_id, new_unique_id)
        ent_reg.async_update_entity(entity_entry.entity_id, new_unique_id=new_unique_id)

    dev_reg = dr.async_get(hass)
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    legacy_ids = {f"{name}_byd_bmu": f"{prefix}_bmu"}
    legacy_ids.update({f"{name}_byd_bms_{i}": f"{prefix}_bms_{i}" for i in range(1, 4)})
    for old, new in legacy_ids.items():
        device = dev_reg.async_get_device(identifiers={(DOMAIN, old)})
        if device is None or entry.entry_id not in device.config_entries:
            continue
        if dev_reg.async_get_device(identifiers={(DOMAIN, new)}) is not None:
            continue
        _LOGGER.debug("Migrating device identifier %s to %s", old, new)
        dev_reg.async_update_device(device.id, new_identifiers={(DOMAIN, new)})


async def async_unload_entry(hass: HomeAssistant, entry: BydBoxConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_shutdown()
    return unload_ok
