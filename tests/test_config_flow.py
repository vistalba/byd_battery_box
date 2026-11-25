"""Tests for the config flow."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .byd_simulator import BydSimulator
from .conftest import DOMAIN, SERIAL


async def _start(hass: HomeAssistant) -> dict[str, Any]:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result


async def test_user_flow(hass: HomeAssistant, entry_data: dict[str, Any]) -> None:
    """Test a successful setup."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], entry_data)
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "BYD Battery Box"
    assert result["data"] == entry_data
    assert result["result"].unique_id == SERIAL
    assert result["result"].state is ConfigEntryState.LOADED
    await hass.config_entries.async_unload(result["result"].entry_id)


async def test_user_flow_default_name(hass: HomeAssistant, entry_data: dict[str, Any]) -> None:
    """Test the default name is used when the name is omitted."""
    result = await _start(hass)
    data = {k: v for k, v in entry_data.items() if k != "name"}
    with patch("custom_components.byd_battery_box.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], data)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "BYD Battery Box"


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"host": "ab"}, "invalid_host"),
        ({"port": 1}, "cannot_connect"),
        ({"scan_interval": 9}, "scan_interval_too_short"),
        ({"bms_scan_interval": 59}, "bms_scan_interval_too_short"),
        ({"log_scan_interval": 119}, "log_scan_interval_too_short"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant, entry_data: dict[str, Any], changes: dict[str, Any], error: str
) -> None:
    """Test validation errors and recovery."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {**entry_data, **changes})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    with patch("custom_components.byd_battery_box.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], entry_data)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_invalid_port(hass: HomeAssistant, entry_data: dict[str, Any]) -> None:
    """Test an invalid port (bypassing the selector)."""
    from custom_components.byd_battery_box.config_flow import InvalidPort, validate_connection  # noqa: PLC0415

    with pytest.raises(InvalidPort):
        await validate_connection({**entry_data, "port": 70000})


async def test_user_flow_unknown_error(hass: HomeAssistant, entry_data: dict[str, Any]) -> None:
    """Test an unexpected error."""
    result = await _start(hass)
    with patch(
        "custom_components.byd_battery_box.config_flow.validate_connection",
        side_effect=RuntimeError("boom"),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], entry_data)
    assert result["errors"] == {"base": "unknown"}


async def test_user_flow_without_serial(hass: HomeAssistant, entry_data: dict[str, Any]) -> None:
    """Test an entry is created without unique id when the BMU reports no serial."""
    result = await _start(hass)
    with (
        patch("custom_components.byd_battery_box.config_flow.validate_connection", return_value=None),
        patch("custom_components.byd_battery_box.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], entry_data)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id is None


async def test_user_flow_duplicate_host(
    hass: HomeAssistant, entry_data: dict[str, Any], mock_entry: MockConfigEntry
) -> None:
    """Test the same host cannot be added twice."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], entry_data)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_duplicate_serial(hass: HomeAssistant, entry_data: dict[str, Any]) -> None:
    """Test the same battery cannot be added twice under another address."""
    MockConfigEntry(domain=DOMAIN, unique_id=SERIAL, data={**entry_data, "host": "10.0.0.1"}).add_to_hass(hass)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], entry_data)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """Test changing the scan intervals."""
    result = await hass.config_entries.options.async_init(setup_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 15, "bms_scan_interval": 30, "log_scan_interval": 600}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "bms_scan_interval_too_short"}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 15, "bms_scan_interval": 300, "log_scan_interval": 900}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert setup_entry.options == {"scan_interval": 15, "bms_scan_interval": 300, "log_scan_interval": 900}
    assert setup_entry.state is ConfigEntryState.LOADED
    coordinator = setup_entry.runtime_data
    assert coordinator.update_interval.total_seconds() == 15
    assert coordinator.scan_interval_bms == 300
    assert coordinator.scan_interval_log == 900


async def _reconfigure(hass: HomeAssistant, entry: MockConfigEntry, data: dict[str, Any]) -> dict[str, Any]:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], data)
    await hass.async_block_till_done()
    return result


async def test_reconfigure(hass: HomeAssistant, setup_entry: MockConfigEntry, entry_data: dict[str, Any]) -> None:
    """Test changing the connection settings."""
    result = await _reconfigure(hass, setup_entry, {"host": "127.0.0.1", "port": entry_data["port"], "unit_id": 2})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert setup_entry.data["unit_id"] == 2
    assert setup_entry.state is ConfigEntryState.LOADED


async def test_reconfigure_cannot_connect(
    hass: HomeAssistant, setup_entry: MockConfigEntry, entry_data: dict[str, Any]
) -> None:
    """Test a failed reconfiguration restores the running entry."""
    result = await _reconfigure(hass, setup_entry, {"host": "127.0.0.1", "port": 1, "unit_id": 1})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert setup_entry.state is ConfigEntryState.LOADED
    assert setup_entry.data["port"] == entry_data["port"]


async def test_reconfigure_wrong_device(
    hass: HomeAssistant, setup_entry: MockConfigEntry, entry_data: dict[str, Any], sim: BydSimulator
) -> None:
    """Test reconfiguring to another battery is refused."""
    sim.state.serial = "P030T020Z2008999999X"
    result = await _reconfigure(hass, setup_entry, {"host": "127.0.0.1", "port": entry_data["port"], "unit_id": 1})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"
    assert setup_entry.unique_id == SERIAL
    assert setup_entry.state is ConfigEntryState.LOADED


async def test_reconfigure_not_loaded(
    hass: HomeAssistant, mock_entry: MockConfigEntry, entry_data: dict[str, Any]
) -> None:
    """Test reconfiguring an entry that is not loaded (e.g. battery moved to a new IP)."""
    result = await _reconfigure(hass, mock_entry, {"host": "127.0.0.1", "port": 1, "unit_id": 1})
    assert result["errors"] == {"base": "cannot_connect"}
    assert mock_entry.state is ConfigEntryState.NOT_LOADED

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "127.0.0.1", "port": entry_data["port"], "unit_id": 1}
    )
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    # 0.1.x entries without unique id get the serial
    assert mock_entry.unique_id == SERIAL
    assert mock_entry.state is ConfigEntryState.LOADED
    await hass.config_entries.async_unload(mock_entry.entry_id)
