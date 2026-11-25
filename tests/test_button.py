"""Tests for the button platform."""

from __future__ import annotations

import pytest
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import async_get_platforms
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .byd_simulator import BydSimulator


async def _press(hass: HomeAssistant, entity_id: str) -> None:
    await hass.services.async_call("button", "press", {"entity_id": entity_id}, blocking=True)
    await hass.async_block_till_done()


async def test_update_log_history(hass: HomeAssistant, setup_entry: MockConfigEntry, sim: BydSimulator) -> None:
    """Test reading the log history of the BMU and a BMS."""
    sim.reset_log_offsets()
    sim.state.writes.clear()
    await _press(hass, "button.update_last_100_log_entries")
    log_requests = [values for address, values in sim.state.writes if address == 0x05A0]
    # 100 entries = up to 5 requests of 20 entries for unit 0
    assert log_requests and all(values[0] == 0 for values in log_requests)
    assert len(log_requests) <= 5

    sim.state.writes.clear()
    await _press(hass, "button.bms_2_update_last_100_log_entries")
    assert all(values[0] == 2 for address, values in sim.state.writes if address == 0x05A0)


async def test_update_log_history_unavailable(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """Test pressing the log button while the battery is unreachable."""
    platform = next(p for p in async_get_platforms(hass, "byd_battery_box") if p.domain == "button")
    entity = platform.entities["button.update_last_100_log_entries"]
    setup_entry.runtime_data.last_update_success = False
    with pytest.raises(HomeAssistantError):
        await entity.async_press()


async def test_reset_history(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """Test resetting the cell voltage history."""
    assert hass.states.get("sensor.bms_1_max_history_cell_voltage").state == "3.331"
    await _press(hass, "button.bms_1_reset_history_cell_voltage")
    assert hass.states.get("sensor.bms_1_max_history_cell_voltage").state == STATE_UNKNOWN
    assert hass.states.get("sensor.bms_2_max_history_cell_voltage").state == "3.341"

    await _press(hass, "button.reset_history_cell_voltage")
    assert hass.states.get("sensor.bms_2_max_history_cell_voltage").state == STATE_UNKNOWN
