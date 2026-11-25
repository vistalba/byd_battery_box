"""Tests for the data update coordinator."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .byd_simulator import BydSimulator


async def test_bms_and_log_intervals(hass: HomeAssistant, setup_entry: MockConfigEntry, sim: BydSimulator) -> None:
    """Test BMS and log data are only read on their own intervals."""
    coordinator = setup_entry.runtime_data
    sim.state.writes.clear()
    await coordinator.async_refresh()
    assert not sim.state.writes  # only BMU data

    coordinator._last_bms_update = 0
    coordinator._last_log_update = 0
    await coordinator.async_refresh()
    addresses = {address for address, _ in sim.state.writes}
    assert addresses == {0x0550, 0x05A0}


async def test_bms_failure_keeps_bmu(hass: HomeAssistant, setup_entry: MockConfigEntry, sim: BydSimulator) -> None:
    """Test a failing BMS read does not make the BMU entities unavailable."""
    coordinator = setup_entry.runtime_data
    coordinator._last_bms_update = 0
    with patch.object(coordinator.client, "update_all_bms_status_data", return_value=False):
        await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert coordinator._last_bms_update == 0


async def test_log_failure(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """Test a failing log read is tolerated."""
    coordinator = setup_entry.runtime_data
    coordinator._last_log_update = 0
    with patch.object(coordinator.client, "update_all_log_data", return_value=False):
        await coordinator.async_refresh()
    assert coordinator.last_update_success


async def test_bmu_exception(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """Test exceptions of the client are handled like failed reads."""
    coordinator = setup_entry.runtime_data
    with patch.object(coordinator.client, "update_bmu_status_data", side_effect=Exception("boom")):
        for _ in range(3):
            await coordinator.async_refresh()
    assert not coordinator.last_update_success


async def test_log_history_failure(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """Test a failing log history read marks the update as failed once."""
    coordinator = setup_entry.runtime_data
    with patch.object(coordinator.client, "update_log_history", side_effect=Exception("boom")):
        await coordinator.async_start_update_log_history(0, 5)
        await hass.async_block_till_done()
    assert not coordinator.last_update_success
    assert coordinator._log_history_request is None or coordinator._log_history_request == (0, 5)


async def test_log_saved(hass: HomeAssistant, setup_entry: MockConfigEntry, sim: BydSimulator) -> None:
    """Test new log entries are stored and exported as CSV."""
    coordinator = setup_entry.runtime_data
    sim.state.log_entries["20991231 10:00:00-4-1"] = {"ts": 4102394400.0, "u": 1, "c": 4, "data": "00" * 23}
    sim.reset_log_offsets()
    coordinator._last_log_update = 0
    with patch.object(coordinator.log_store, "async_save") as save:
        await coordinator.async_refresh()
    save.assert_called_once()
    assert "20991231 10:00:00-4-1" in coordinator.client.log


async def test_delta_without_values(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """Test the cell voltage delta is None without cell voltages."""
    coordinator = setup_entry.runtime_data
    coordinator.client.data.pop("bms1_max_c_v")
    coordinator._compute_delta_c_v()
    assert coordinator.client.data["bms1_delta_c_v"] is None
