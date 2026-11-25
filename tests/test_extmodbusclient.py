"""Tests for the Modbus base client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ConnectionException, ModbusIOException

from custom_components.byd_battery_box.extmodbusclient import ExtModbusClient


@pytest.fixture
async def client() -> ExtModbusClient:
    """Return a client with a mocked pymodbus client."""
    c = ExtModbusClient("127.0.0.1", 1, 1, 1, "rtu")
    c._client = MagicMock()
    c._client.connected = True
    c._client.connect = AsyncMock(return_value=True)
    return c


def _response(registers: list[int], error: bool = False) -> MagicMock:
    resp = MagicMock()
    resp.isError.return_value = error
    resp.registers = registers
    return resp


async def test_conversions(client: ExtModbusClient) -> None:
    """Test the conversion helpers."""
    dt = AsyncModbusTcpClient.DATATYPE
    assert client.convert_from_registers_int8([0x1234]) == [0x12, 0x34]
    assert client.convert_from_registers_int4([0x24]) == [2, 4]
    assert client.convert_from_registers([1, 2], dt.UINT32, word_order="little") == 0x20001
    assert client.convert_from_registers([1, 2, 3, 4], dt.UINT32) == [0x10002, 0x30004]
    assert client.convert_from_registers([0x4142, 0x4300], dt.STRING) == "ABC"
    assert client.convert_from_registers([0x4142], dt.STRING, word_order="little") == "AB"
    assert sum(client.convert_from_registers([0x0001], dt.BITS)) == 1
    with pytest.raises(Exception, match="illegal size"):
        client.convert_from_registers([1], dt.UINT32)
    assert client.calculate_value(1234, -1, 1) == 123.4
    assert client.strip_escapes("a\x01b ") == "ab"
    assert client.strip_escapes(None) is None
    assert client.get_value_from_dict({1: "x"}, 2, "d") == "d"
    assert client.convert_from_byte_uint16(bytearray([1, 2]), 0) == 258
    assert client.convert_from_byte_uint16(bytearray([1, 2]), 0, "LE") == 513
    assert client.convert_from_byte_uint16(bytearray([1]), 0) == 0
    assert client.convert_from_byte_int16(bytearray([0xFF, 0xFE]), 0) == -2
    assert client.convert_from_byte_int16(bytearray([0xFE, 0xFF]), 0, "LE") == -2
    assert client.convert_from_byte_int16(bytearray([1]), 0) == 0
    assert client.bitmask_to_strings(0b101, {0: "a"}) == ["a", "bit 2 undefined"]
    assert client.bitmask_to_string(0, {}, "Normal") == "Normal"
    assert client.validate(5, ">", 1) == 5
    with pytest.raises(ValueError):
        client.validate(0, ">", 1)


async def test_connect(client: ExtModbusClient) -> None:
    """Test connecting with retries."""
    assert await client.connect()
    client._client.connected = False
    client._client.connect = AsyncMock(return_value=False)
    with patch("custom_components.byd_battery_box.extmodbusclient.asyncio.sleep", AsyncMock()), pytest.raises(Exception, match="Failed to connect"):
        await client.connect()
    assert client._client.connect.call_count == 3


async def test_read_retries(client: ExtModbusClient) -> None:
    """Test read retries and error handling."""
    sleep = patch("custom_components.byd_battery_box.extmodbusclient.asyncio.sleep", AsyncMock())
    with sleep:
        client._client.read_holding_registers = AsyncMock(side_effect=[ModbusIOException("x"), _response([1])])
        assert (await client.read_holding_registers(1, 0, 1)).registers == [1]

        client._client.read_holding_registers = AsyncMock(side_effect=ConnectionException("x"))
        assert await client.read_holding_registers(1, 0, 1, retries=1) is None

        client._client.read_holding_registers = AsyncMock(side_effect=RuntimeError("x"))
        assert await client.read_holding_registers(1, 0, 1) is None

        io_error = ModbusIOException("x")
        io_error.isError = lambda: True
        client._client.read_holding_registers = AsyncMock(return_value=io_error)
        assert await client.read_holding_registers(1, 0, 1, retries=0) is None

        client._client.read_holding_registers = AsyncMock(return_value=_response([], error=True))
        assert await client.read_holding_registers(1, 0, 1, retries=0) is None

        client._client.read_holding_registers = AsyncMock(return_value=_response([]))
        assert await client.get_registers(0, 1) is None


async def test_read_exception_response(client: ExtModbusClient) -> None:
    """Test an exception response from the device."""
    from pymodbus import ExceptionResponse  # noqa: PLC0415

    response = ExceptionResponse(3, 4)
    client._client.read_holding_registers = AsyncMock(return_value=response)
    with patch("custom_components.byd_battery_box.extmodbusclient.asyncio.sleep", AsyncMock()):
        assert await client.read_holding_registers(1, 0, 1, retries=0) is None


async def test_reconnect(client: ExtModbusClient) -> None:
    """Test a disconnected client reconnects before reading."""
    client._client.connected = False

    async def _connect() -> bool:
        client._client.connected = True
        return True

    client._client.connect = AsyncMock(side_effect=_connect)
    client._client.read_holding_registers = AsyncMock(return_value=_response([7]))
    assert await client.get_registers(0, 1) == [7]
    client._client.connect.assert_called_once()


@pytest.mark.parametrize(
    ("side_effect", "match"),
    [
        (ModbusIOException("x"), "IO error"),
        (ConnectionException("x"), "no connection"),
        (RuntimeError("x"), "unknown error"),
    ],
)
async def test_write_errors(client: ExtModbusClient, side_effect: Exception, match: str) -> None:
    """Test errors while writing registers."""
    client._client.write_registers = AsyncMock(side_effect=side_effect)
    with pytest.raises(Exception, match=match):
        await client.write_registers(1, 0, [1])


async def test_write_error_response(client: ExtModbusClient) -> None:
    """Test an error response while writing."""
    client._client.write_registers = AsyncMock(return_value=_response([], error=True))
    with pytest.raises(Exception, match="data error"):
        await client.write_registers(1, 0, [1])
    client._client.write_registers = AsyncMock(return_value=_response([]))
    assert await client.write_registers(1, 0, [1])
