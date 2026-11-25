"""Tests for the sensor platform."""

from __future__ import annotations

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, mock_restore_cache

from .conftest import SERIAL


async def test_bmu_sensors(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """Test BMU sensor states, units and classes."""
    state = hass.states.get("sensor.state_of_charge")
    assert state.state == "85"
    assert state.attributes["unit_of_measurement"] == "%"
    assert state.attributes["device_class"] == "battery"
    assert state.attributes["state_class"] == "measurement"
    assert state.attributes["friendly_name"] == "Battery Management Unit State of charge"

    assert hass.states.get("sensor.bmu_power").state == "-781.0"
    assert hass.states.get("sensor.bmu_power").attributes["unit_of_measurement"] == "W"
    assert hass.states.get("sensor.bmu_temperature").attributes["unit_of_measurement"] == "°C"
    assert hass.states.get("sensor.charge_total_energy").attributes["state_class"] == "total_increasing"
    assert hass.states.get("sensor.efficiency").state == "90.0"
    assert hass.states.get("sensor.cells_per_module").state == "16"
    assert hass.states.get("sensor.temperature_sensors_per_module").state == "8"
    assert hass.states.get("sensor.total_capacity").state == "16.56"
    assert hass.states.get("sensor.inverter").state == "Fronius HV"
    assert hass.states.get("sensor.updated").attributes["device_class"] == "timestamp"
    assert hass.states.get("sensor.connection_health").state == "healthy"
    assert float(hass.states.get("sensor.average_latency").state) >= 0
    log_state = hass.states.get("sensor.log_entries")
    assert isinstance(log_state.attributes["log"], list)


async def test_bms_sensors(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """Test per tower sensors and attributes."""
    assert hass.states.get("sensor.bms_1_cell_voltage_max").state == "3.331"
    assert hass.states.get("sensor.bms_1_cells_voltage_delta").state == "21"
    assert hass.states.get("sensor.bms_2_cell_voltage_max").state == "3.341"
    avg = hass.states.get("sensor.bms_1_cells_average_voltage")
    assert len(avg.attributes["cell_voltages"]) == 3
    assert avg.attributes["cell_voltages"][0]["v"][0] == 3310
    assert "cell_voltages_max_history" in avg.attributes
    assert hass.states.get("sensor.bms_1_cells_balancing").attributes["cell_balancing"][0]["b"][:3] == [1, 0, 1]
    assert len(hass.states.get("sensor.bms_1_cells_average_temperature").attributes["cell_temps"]) == 3
    assert hass.states.get("sensor.bms_1_balancing_total").attributes["total_cells"] is not None
    assert hass.states.get("sensor.bms_1_max_history_cell_voltage").attributes["cell_voltages"]
    assert hass.states.get("sensor.bms_3_state_of_charge") is None


async def test_disabled_by_default(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """Test rarely used entities are disabled by default for new installations."""
    ent_reg = er.async_get(hass)
    for entity_id in ("sensor.bmu_version_a", "sensor.param_table_version", "sensor.last_latency"):
        entry = ent_reg.async_get(entity_id)
        assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert ent_reg.async_get("sensor.state_of_charge").unique_id == f"{SERIAL}_soc"
    assert ent_reg.async_get("sensor.bms_1_state_of_charge").unique_id == f"{SERIAL}_bms1_soc"


async def test_unavailable(hass: HomeAssistant, setup_entry: MockConfigEntry, sim) -> None:
    """Test entities become unavailable after repeated failures and recover."""
    coordinator = setup_entry.runtime_data
    sim.state.fail_reads = True
    await coordinator.async_refresh()
    assert hass.states.get("sensor.state_of_charge").state == "85"
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    assert hass.states.get("sensor.state_of_charge").state == STATE_UNAVAILABLE
    # connection sensors stay available
    assert hass.states.get("sensor.connection_health").state != STATE_UNAVAILABLE

    sim.state.fail_reads = False
    sim.state.soc = 42
    await coordinator.async_refresh()
    assert hass.states.get("sensor.state_of_charge").state == "42"


async def test_restore_history(hass: HomeAssistant, mock_entry: MockConfigEntry) -> None:
    """Test the cell voltage history values are restored after a restart."""
    cells = [{"m": 1, "v": [3500] * 16}, {"m": 2, "v": [3500] * 16}, {"m": 3, "v": [3500] * 16}]
    mock_restore_cache(
        hass,
        [
            State("sensor.bms_1_max_history_cell_voltage", "3.5", {"cell_voltages": cells}),
            State("sensor.bms_1_min_history_cell_voltage", "not-a-number"),
        ],
    )
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    data = mock_entry.runtime_data.client.data
    assert data["bms1_max_history_cell_voltage_cells"] == cells
    # values are merged with the next BMS reading
    mock_entry.runtime_data._last_bms_update = 0
    await mock_entry.runtime_data.async_refresh()
    assert hass.states.get("sensor.bms_1_max_history_cell_voltage").state == "3.5"
    assert hass.states.get("sensor.bms_1_min_history_cell_voltage").state not in (STATE_UNKNOWN, "not-a-number")
    await hass.config_entries.async_unload(mock_entry.entry_id)
