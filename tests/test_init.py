"""Tests for setup, unload and migration."""

from __future__ import annotations

import json
from typing import Any

from homeassistant.config_entries import ConfigEntryDisabler, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .byd_simulator import BydSimulator
from .conftest import DOMAIN, SERIAL

# Entities and devices as registered by version 0.1.34 (subset incl. BMS and buttons)
LEGACY_ENTITIES = {
    "sensor.state_of_charge": ("bydb_soc", "BYD Battery Box_byd_bmu"),
    "sensor.bmu_power": ("bydb_power", "BYD Battery Box_byd_bmu"),
    "sensor.last_latency": ("bydb_last_latency", "BYD Battery Box_byd_bmu"),
    "sensor.bms_1_cells_average_voltage": ("bydb_bms1_avg_c_v", "BYD Battery Box_byd_bms_1"),
    "sensor.bms_2_state_of_charge": ("bydb_bms2_soc", "BYD Battery Box_byd_bms_2"),
    "button.update_last_1000_log_entries": ("bydb_update_log_history_1000", "BYD Battery Box_byd_bmu"),
    "button.bms_1_update_last_100_log_entries": ("bydb_bms1_update_log_history_100", "BYD Battery Box_byd_bms_1"),
}


async def test_setup_and_unload(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """Test setting up and unloading the integration."""
    assert setup_entry.state is ConfigEntryState.LOADED
    assert setup_entry.unique_id == SERIAL
    coordinator = setup_entry.runtime_data
    assert coordinator.client.connected

    assert await hass.config_entries.async_unload(setup_entry.entry_id)
    await hass.async_block_till_done()
    assert setup_entry.state is ConfigEntryState.NOT_LOADED
    assert not coordinator.client.connected


async def test_setup_not_ready(hass: HomeAssistant, mock_entry: MockConfigEntry, sim: BydSimulator) -> None:
    """Test setup is retried when the battery cannot be reached."""
    sim.state.fail_reads = True
    assert not await hass.config_entries.async_setup(mock_entry.entry_id)
    assert mock_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_connection_refused(hass: HomeAssistant, entry_data: dict[str, Any]) -> None:
    """Test setup is retried when nothing listens on the port."""
    entry = MockConfigEntry(domain=DOMAIN, data={**entry_data, "port": 1})
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_unique_id_not_set_twice(
    hass: HomeAssistant, mock_entry: MockConfigEntry, entry_data: dict[str, Any]
) -> None:
    """Test the serial is not set as unique id if another entry already uses it."""
    MockConfigEntry(domain=DOMAIN, unique_id=SERIAL, data={**entry_data, "host": "10.0.0.1"}).add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_entry.unique_id is None
    await hass.config_entries.async_unload(mock_entry.entry_id)


async def test_migrate_legacy_registry(hass: HomeAssistant, mock_entry: MockConfigEntry) -> None:
    """Test unique ids and device identifiers of 0.1.x are migrated, entity ids are kept."""
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    for entity_id, (unique_id, device) in LEGACY_ENTITIES.items():
        dev = dev_reg.async_get_or_create(config_entry_id=mock_entry.entry_id, identifiers={(DOMAIN, device)})
        domain, object_id = entity_id.split(".")
        ent_reg.async_get_or_create(
            domain, DOMAIN, unique_id, suggested_object_id=object_id, config_entry=mock_entry, device_id=dev.id
        )
    # a renamed entity keeps its custom entity id
    ent_reg.async_update_entity("sensor.state_of_charge", new_entity_id="sensor.my_soc")
    # an entity of another config entry is not touched
    other = MockConfigEntry(domain=DOMAIN, disabled_by=ConfigEntryDisabler.USER)
    other.add_to_hass(hass)
    ent_reg.async_get_or_create("sensor", DOMAIN, "bydb_foreign", config_entry=other)

    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    for entity_id, (unique_id, _device) in LEGACY_ENTITIES.items():
        entity_id = "sensor.my_soc" if entity_id == "sensor.state_of_charge" else entity_id
        entry = ent_reg.async_get(entity_id)
        assert entry is not None, entity_id
        assert entry.unique_id == f"{SERIAL}_{unique_id.removeprefix('bydb_')}"
        assert entry.disabled_by is None
    assert hass.states.get("sensor.my_soc").state == "85"
    assert hass.states.get("sensor.state_of_charge") is None
    assert hass.states.get("button.update_last_1000_log_entries") is not None
    assert ent_reg.async_get_entity_id("sensor", DOMAIN, "bydb_foreign")

    identifiers = sorted(i for d in dr.async_entries_for_config_entry(dev_reg, mock_entry.entry_id) for _, i in d.identifiers)
    assert identifiers == sorted([f"{SERIAL}_bmu", f"{SERIAL}_bms_1", f"{SERIAL}_bms_2"])
    # no duplicated entities were created
    assert not [e for e in er.async_entries_for_config_entry(ent_reg, mock_entry.entry_id) if e.entity_id.endswith("_2")]
    await hass.config_entries.async_unload(mock_entry.entry_id)


async def test_migrate_conflict(hass: HomeAssistant, mock_entry: MockConfigEntry) -> None:
    """Test the migration skips entities whose new unique id already exists."""
    ent_reg = er.async_get(hass)
    ent_reg.async_get_or_create("sensor", DOMAIN, "bydb_soc", suggested_object_id="old_soc", config_entry=mock_entry)
    ent_reg.async_get_or_create("sensor", DOMAIN, f"{SERIAL}_soc", suggested_object_id="state_of_charge", config_entry=mock_entry)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    assert ent_reg.async_get("sensor.old_soc").unique_id == "bydb_soc"
    assert ent_reg.async_get("sensor.state_of_charge").unique_id == f"{SERIAL}_soc"
    await hass.config_entries.async_unload(mock_entry.entry_id)


async def test_new_install_entity_ids(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """Test new installations get the entity ids of 0.1.x."""
    for entity_id in (
        "sensor.state_of_charge",
        "sensor.bmu_power",
        "sensor.log_entries",
        "sensor.connection_health",
        "sensor.bms_1_cells_average_voltage",
        "sensor.bms_2_max_history_cell_voltage",
        "button.update_last_100_log_entries",
        "button.bms_2_reset_history_cell_voltage",
    ):
        assert hass.states.get(entity_id) is not None, entity_id


async def test_legacy_log_file_migrated(hass: HomeAssistant, mock_entry: MockConfigEntry, tmp_path: Any) -> None:
    """Test the legacy JSON log file is imported."""
    legacy = {
        "20991231 10:00:00-4-1": {"ts": 4102394400.0, "u": 1, "c": 4, "data": "00" * 23},
    }
    path = hass.config.path("custom_components", DOMAIN, "logs")

    def _write() -> None:
        import os  # noqa: PLC0415

        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, "byd_log.json"), "w", encoding="utf-8") as file:
            json.dump(legacy, file)

    await hass.async_add_executor_job(_write)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = mock_entry.runtime_data
    assert "20991231 10:00:00-4-1" in coordinator.client.log
    await hass.config_entries.async_unload(mock_entry.entry_id)
