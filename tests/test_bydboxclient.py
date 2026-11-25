"""Tests for the Modbus client and the log decoders (no Home Assistant needed)."""

from __future__ import annotations

import csv
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.byd_battery_box.bydbox_const import BMS_LOG_CODES, BMU_LOG_CODES
from custom_components.byd_battery_box.bydboxclient import BydBoxClient

from .byd_simulator import BydSimulator, BydSimulatorState, load_fixture_log, start_simulator

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
async def client_factory(socket_enabled):
    """Create clients connected to a simulator."""
    servers = []
    clients = []

    async def _create(state: BydSimulatorState | None = None) -> tuple[BydBoxClient, BydSimulator]:
        sim = BydSimulator(state or BydSimulatorState(log_entries=load_fixture_log()))
        server, port = await start_simulator(sim)
        servers.append(server)
        client = BydBoxClient("127.0.0.1", port, 1, 3)
        client._min_response_delay = 0.01
        client._retry_delay = 0.01
        client._response_timeout = 0.5
        clients.append(client)
        return client, sim

    yield _create
    for client in clients:
        client.close()
    for server in servers:
        server.close()


# ------------------------------------------------------------------ decoders
async def test_decoded_log_matches_v01() -> None:
    """Decoding the recorded log gives the same descriptions as version 0.1.x."""
    client = BydBoxClient("127.0.0.1", 1, 1, 3)
    client.load_log(load_fixture_log())
    with open(FIXTURES / "byd_logs_decoded_v0.1.csv", encoding="utf-8") as file:
        expected = {(row["unit"], row["code"], row["data"]): (row["description"], row["detail"]) for row in csv.DictReader(file)}
    rows = client.get_log_csv_rows()
    assert rows[0] == ["ts", "unit", "code", "description", "detail", "data"]
    compared = 0
    for _ts, unit, code, description, detail, data in rows[1:]:
        key = (unit, str(code), data)
        assert description
        if key in expected:
            compared += 1
            assert (description, detail) == expected[key], key
    assert compared == len(rows) - 1


@pytest.mark.parametrize("pattern", [b"\x00" * 23, b"\xff" * 23, bytes(range(23)), bytes([1, 1, 2] + [3] * 20), bytes([2, 23, 1, 2] + [5] * 19)])
@pytest.mark.parametrize("unit_id", [0, 1])
async def test_decode_all_codes(unit_id: int, pattern: bytes) -> None:
    """All known log codes decode without raising."""
    client = BydBoxClient("127.0.0.1", 1, 1, 3)
    client._modules = 3
    client._cells = 16
    codes = BMU_LOG_CODES if unit_id == 0 else BMS_LOG_CODES
    for code in [*codes, 127]:
        description, decoded = client.decode_log_data(unit_id, datetime(2025, 1, 1), code, bytearray(pattern))
        assert isinstance(description, str)
        assert isinstance(decoded["desc"], str)


async def test_log_list_and_retention() -> None:
    """Test the log list attribute and the retention."""
    client = BydBoxClient("127.0.0.1", 1, 1, 3)
    assert not client.load_log({})
    log = load_fixture_log()
    recent = {"20991231 10:00:00-4-1": {"ts": time.time(), "u": 1, "c": 4, "data": "00" * 23}}
    assert client.load_log({**log, **recent})
    assert client.data["log_entries"] == len(log) + 1
    log_list = client.data["log"]
    assert len(log_list) == 20
    assert {"ts", "u", "c", "d", "data", "detail", "hexdata"} <= set(log_list[0])
    assert client.apply_log_retention() == len(log)
    assert list(client.log) == list(recent)
    assert client.data["log_entries"] == 1


# ------------------------------------------------------------- live protocol
async def test_read_all(client_factory) -> None:
    """Read all data from the simulator."""
    client, _sim = await client_factory()
    assert await client.init_data()
    assert client.data["serial"] == "P030T020Z2008123456"
    assert client.data["model"] == "HVM"
    assert client.data["bat_type"] == "HV"
    assert client.data["towers"] == 2
    assert client.data["capacity"] == pytest.approx(16.56)
    assert await client.update_bmu_status_data()
    assert client.data["soc"] == 85
    assert client.data["power"] == pytest.approx(-781.0)
    assert client.data["updated"].tzinfo is not None
    assert await client.update_all_bms_status_data()
    assert client.data["bms2_avg_c_v"] == pytest.approx(3.331)
    assert await client.update_all_log_data()
    assert client.data["bmu_last_log"]
    assert client.data["log_entries"] == 60
    # second BMS read updates histories element-wise
    assert await client.update_bms_status_data(1)
    assert client.data["bms1_max_history_cell_voltage"] == pytest.approx(3.331)
    assert await client.update_log_history(1, 3)


@pytest.mark.parametrize(
    ("serial", "model", "bat_type", "towers"),
    [
        ("P030T020Z2008123456X", "HVS", "HV", 2),
        ("P030T020Z2008123456X", "HVL", "HV", 2),
        ("P021T020Z2008123456X", "LVS", "LV", 2),
        ("X000T020Z2008123456X", "HVM", "", 2),
    ],
)
async def test_battery_types(client_factory, serial: str, model: str, bat_type: str, towers: int) -> None:
    """Test detection of the battery type."""
    state = BydSimulatorState(serial=serial, model=model if model != "LVS" else "HVS", towers=towers)
    client, _sim = await client_factory(state)
    assert await client.init_data()
    assert client.data["bat_type"] == bat_type
    if bat_type == "LV":
        assert client.data["model"] == "LVS"
    elif bat_type == "HV":
        assert client.data["model"] == model
    else:
        assert client.data["model"] == "NA"


async def test_hv_unknown_type_and_tower_limit(client_factory) -> None:
    """Test an unknown HV battery type and more than 3 towers."""
    client, sim = await client_factory(BydSimulatorState(towers=5))
    regs = sim.info_registers()
    regs[15] = 7 << 8 | 7  # unknown working areas
    regs[17] = 9 << 8  # unknown battery type / application
    regs[18] = 5 << 8  # unknown phase
    with patch.object(sim, "info_registers", return_value=regs):
        await client.init_data()
    assert client.data["towers"] == 3
    assert client.data["model"] == "NA"
    assert client.data["application"] == "Unknown: 9"
    assert client.data["phase"] == "Unknown: 5"
    assert client.data["bmu_area"] == "Unknown: 7"


async def test_lv_unknown_type(client_factory) -> None:
    """Test an unknown LV battery type."""
    client, sim = await client_factory(BydSimulatorState(serial="P021T020Z2008123456X"))
    regs = sim.info_registers()
    with patch.object(sim, "info_registers", return_value=[*regs[:17], 1 << 8, *regs[18:]]):
        await client.init_data()
    assert client.data["model"] == "NA"
    regs = sim.info_registers()
    client2, sim2 = await client_factory(BydSimulatorState(serial="P021T020Z2008123456X"))
    with patch.object(sim2, "info_registers", return_value=[*regs[:17], 0, *regs[18:]]):
        await client2.init_data()
    assert client2.data["model"] == "LVL"


async def test_read_failures(client_factory) -> None:
    """Test failing reads return False/None."""
    client, sim = await client_factory()
    await client.init_data()
    sim.state.fail_reads = True
    assert not await client.update_bmu_status_data()
    assert not await client.update_info_data()
    assert not await client.update_ext_info_data()
    assert not await client.update_all_bms_status_data()
    assert not await client.update_all_log_data()
    assert await client._read_log_data_unit(0) is None
    assert not await client.update_log_data(0)


async def test_never_ready(client_factory) -> None:
    """Test the timeout while waiting for the BMS response."""
    client, sim = await client_factory()
    await client.init_data()
    sim.state.never_ready = True
    with patch("custom_components.byd_battery_box.bydboxclient.asyncio.sleep", AsyncMock()):
        assert not await client._wait_for_response(0x0551)


async def test_unexpected_ready_response(client_factory) -> None:
    """Test an unexpected value while waiting for the response."""
    client, sim = await client_factory()
    await client.init_data()
    with patch.object(sim, "read", return_value=[0x1234]):
        client._retry_delay = 6
        with patch("custom_components.byd_battery_box.bydboxclient.asyncio.sleep", AsyncMock()):
            assert not await client._wait_for_response(0x0551)


async def test_bms_invalid_data(client_factory) -> None:
    """Test invalid BMS data is rejected."""
    client, sim = await client_factory()
    await client.init_data()
    original = sim.bms_status_registers

    def _bad_voltage(bms_id: int) -> list[int]:
        regs = original(bms_id)
        regs[1] = 6000
        return regs

    with patch.object(sim, "bms_status_registers", side_effect=_bad_voltage):
        assert not await client.update_bms_status_data(1)
    client._modules = 0
    assert not await client.update_bms_status_data(1)


async def test_bms_partial_read(client_factory) -> None:
    """Test a missing chunk of the BMS response."""
    client, sim = await client_factory()
    await client.init_data()
    original = sim.write

    def _write(address: int, values: list[int]) -> bool:
        result = original(address, values)
        sim._fifo = sim._fifo[:2]
        return result

    with patch.object(sim, "write", side_effect=_write):
        assert not await client.update_bms_status_data(1)
        assert await client._read_log_data_unit(0) is None


async def test_health_monitor(client_factory) -> None:
    """Test the connection health monitor."""
    client, sim = await client_factory()
    metrics = client.get_connection_metrics()
    assert metrics["connection_health"] == "unhealthy"
    await client.init_data()
    assert await client.health_monitor.health_check()
    metrics = client.get_connection_metrics()
    assert metrics["connection_health"] == "healthy"
    assert metrics["last_latency"] is not None
    assert await client.health_monitor.measure_latency() is not None
    assert client.health_monitor.avg_latency is not None

    async with client.ClientBusyLock(client):
        assert client.busy
        assert await client.health_monitor.measure_latency() is None

    with patch.object(client, "read_holding_registers", side_effect=Exception("x")):
        assert await client.health_monitor.measure_latency() is None
    assert client.health_monitor.consecutive_failures == 1

    client.health_monitor.update_interval = 0.01
    client.health_monitor.start_monitoring()
    client.health_monitor.start_monitoring()
    await client.health_monitor.stop_monitoring()
    await client.health_monitor.stop_monitoring()


async def test_init_failure(client_factory) -> None:
    """Test init raises when the base info cannot be read."""
    client, _sim = await client_factory()
    with patch.object(client, "update_info_data", side_effect=Exception("x")), pytest.raises(Exception, match="base info"):
        await client.init_data()
    with patch.object(client, "update_ext_info_data", side_effect=Exception("x")), pytest.raises(Exception, match="ext info"):
        await client.init_data()
    assert await client.init_data(close=True)
    assert not client.connected


async def test_log_invalid_dates(client_factory) -> None:
    """Test log entries with invalid dates are handled."""
    client, sim = await client_factory(BydSimulatorState(log_entries={}))
    await client.init_data()

    def _regs(unit_id: int, offset: int) -> list[int]:
        entries = [
            [4 << 8 | 25, 0 << 8 | 0, 10 << 8 | 0, 0, *([0] * 11)],  # month 0 / day 0 fixed
            [4 << 8 | 25, 2 << 8 | 30, 10 << 8 | 0, 0, *([0] * 11)],  # 30 Feb -> error, stop
        ]
        payload = [r for e in entries for r in e]
        payload += [0] * (320 - len(payload))
        return [r for c in range(5) for r in (64, *payload[c * 64 : c * 64 + 64])]

    with patch.object(sim, "log_registers", side_effect=_regs):
        assert await client._read_log_data_unit(0) == 1

    def _year(unit_id: int, offset: int) -> list[int]:
        payload = [4 << 8 | 255, 1 << 8 | 1, 0, 0, *([0] * 11)]
        payload += [0] * (320 - len(payload))
        return [r for c in range(5) for r in (64, *payload[c * 64 : c * 64 + 64])]

    with patch.object(sim, "log_registers", side_effect=_year):
        assert await client._read_log_data_unit(0) == 0
