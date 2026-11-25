"""Tests for devices: dynamic towers, stale devices and repair issues."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .byd_simulator import BydSimulator
from .conftest import DOMAIN, SERIAL


async def _remove_device(hass: HomeAssistant, entry: MockConfigEntry, device: dr.DeviceEntry) -> bool:
    from custom_components.byd_battery_box import async_remove_config_entry_device  # noqa: PLC0415

    return await async_remove_config_entry_device(hass, entry, device)


async def test_devices(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """Test the devices of the battery."""
    dev_reg = dr.async_get(hass)
    bmu = dev_reg.async_get_device(identifiers={(DOMAIN, f"{SERIAL}_bmu")})
    assert bmu.name == "Battery Management Unit"
    assert bmu.manufacturer == "BYD"
    assert bmu.model == "HVM"
    assert bmu.serial_number == SERIAL
    assert bmu.sw_version == "3.23"
    bms = dev_reg.async_get_device(identifiers={(DOMAIN, f"{SERIAL}_bms_1")})
    assert bms.via_device_id == bmu.id
    assert not await _remove_device(hass, setup_entry, bmu)
    assert not await _remove_device(hass, setup_entry, bms)


async def test_tower_added_and_removed(hass: HomeAssistant, setup_entry: MockConfigEntry, sim: BydSimulator) -> None:
    """Test towers added after setup get entities; removed towers become unavailable and removable."""
    coordinator = setup_entry.runtime_data
    assert hass.states.get("sensor.bms_3_state_of_charge") is None

    sim.state.towers = 3
    coordinator._last_log_update = 0
    coordinator._last_bms_update = 0
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.towers == 3
    assert hass.states.get("sensor.bms_3_state_of_charge").state == "85.0"
    assert hass.states.get("button.bms_3_reset_history_cell_voltage") is not None

    sim.state.towers = 2
    coordinator._last_log_update = 0
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.bms_3_state_of_charge").state == "unavailable"
    dev_reg = dr.async_get(hass)
    bms3 = dev_reg.async_get_device(identifiers={(DOMAIN, f"{SERIAL}_bms_3")})
    assert await _remove_device(hass, setup_entry, bms3)


async def test_static_data_failure(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """Test a failing re-read of the static data is ignored."""
    from unittest.mock import patch  # noqa: PLC0415

    coordinator = setup_entry.runtime_data
    coordinator._last_log_update = 0
    with patch.object(coordinator.client, "update_static_data", side_effect=Exception("x")):
        await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert coordinator.towers == 2


async def test_duplicate_entry_issue(hass: HomeAssistant, mock_entry: MockConfigEntry, entry_data: dict[str, Any]) -> None:
    """Test a repair issue is raised when the battery is configured twice."""
    other = MockConfigEntry(domain=DOMAIN, unique_id=SERIAL, data={**entry_data, "host": "10.0.0.1"})
    other.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    issue_reg = ir.async_get(hass)
    issue = issue_reg.async_get_issue(DOMAIN, f"duplicate_entry_{mock_entry.entry_id}")
    assert issue is not None
    assert issue.translation_key == "duplicate_entry"

    await hass.config_entries.async_remove(mock_entry.entry_id)
    await hass.async_block_till_done()
    assert issue_reg.async_get_issue(DOMAIN, f"duplicate_entry_{mock_entry.entry_id}") is None
