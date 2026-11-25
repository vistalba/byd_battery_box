"""Simulator of a BYD Battery Box BMU speaking Modbus RTU over TCP.

The simulator implements the register protocol used by the integration
(function codes 3 and 16) without any real hardware. It is used by the test
suite and can be started manually to test the integration in a real Home
Assistant instance::

    python tests/byd_simulator.py --port 8080 --towers 2 --modules 3

Then add the integration with the IP address of the machine running the
simulator.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import struct
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)

READY = 0x8801
FIXTURE_LOG = Path(__file__).parent / "fixtures" / "byd_logs.json"

# battery types (register 0x0011 high byte) for HV batteries
HV_TYPES = {"HVL": 0, "HVM": 1, "HVS": 2}
MODULE_CELLS = {"HVL": 0, "HVM": 16, "HVS": 32}
MODULE_TEMPS = {"HVL": 0, "HVM": 8, "HVS": 12}


def crc16(data: bytes) -> int:
    """Return the Modbus CRC16 of data."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def _string_regs(value: str, count: int) -> list[int]:
    raw = value.encode("ascii").ljust(count * 2, b"\x00")[: count * 2]
    return [raw[i] << 8 | raw[i + 1] for i in range(0, len(raw), 2)]


def _u32_little(value: int) -> list[int]:
    """Encode a uint32 with little word order."""
    return [value & 0xFFFF, (value >> 16) & 0xFFFF]


def _i16(value: int) -> int:
    return value & 0xFFFF


@dataclass
class BydSimulatorState:
    """Configurable state of the simulated battery."""

    serial: str = "P030T020Z2008123456X"
    model: str = "HVM"
    towers: int = 2
    modules: int = 3
    inverter_id: int = 0
    application_id: int = 1
    phase_id: int = 1
    soc: int = 85
    soh: int = 99
    current: float = -2.5
    voltage: float = 312.4
    charge_kwh: float = 1234.5
    discharge_kwh: float = 1111.1
    bmu_errors: int = 0
    log_entries: dict[str, dict[str, Any]] = field(default_factory=dict)
    # fault injection
    fail_reads: bool = False
    drop_connection: bool = False
    never_ready: bool = False
    reads: int = 0
    writes: list[tuple[int, list[int]]] = field(default_factory=list)


class BydSimulator:
    """Implements the BYD register protocol."""

    def __init__(self, state: BydSimulatorState | None = None) -> None:
        """Initialize the simulator."""
        self.state = state or BydSimulatorState()
        self._fifo: list[list[int]] = []
        self._ready = {0x0551: 0, 0x05A1: 0}
        self._log_offsets: dict[int, int] = {}

    # ----------------------------------------------------------------- registers
    def info_registers(self) -> list[int]:
        """Return registers 0x0000-0x0013."""
        s = self.state
        regs = _string_regs(s.serial, 10)
        regs += [0, 0]
        regs += [3 << 8 | 22, 3 << 8 | 23, 3 << 8 | 16, 1 << 8 | 1]
        tower_byte = (s.towers - 1 if s.serial.startswith(("P02", "P011")) else s.towers) & 0x0F
        regs.append(s.inverter_id << 8 | tower_byte << 4 | (s.modules & 0x0F))
        regs.append(HV_TYPES.get(s.model, 1) << 8 | 0)
        regs.append(s.phase_id << 8)
        regs.append(0)
        return regs

    def bmu_status_registers(self) -> list[int]:
        """Return registers 0x0500-0x0514."""
        s = self.state
        regs = [
            s.soc,
            335,
            331,
            s.soh,
            _i16(round(s.current * 10)),
            round(s.voltage * 100),
            24,
            21,
            27,
            0,
            792,
            0,
            0,
            s.bmu_errors,
            1 << 8 | 7,
            0,
            round(s.voltage * 100),
        ]
        regs += _u32_little(round(s.charge_kwh * 10))
        regs += _u32_little(round(s.discharge_kwh * 10))
        return regs

    def bms_status_registers(self, bms_id: int) -> list[int]:
        """Return the 260 registers of a BMS status response (4 chunks of 65)."""
        s = self.state
        cells = MODULE_CELLS.get(s.model, 16)
        temps = MODULE_TEMPS.get(s.model, 8)
        regs = [0] * 260
        regs[0] = 130
        regs[1] = 3350 + bms_id
        regs[2] = 3300 + bms_id
        regs[3] = 2 << 8 | 5
        regs[4] = 25
        regs[5] = 20
        regs[6] = 1 << 8 | 3
        for m in range(min(s.modules, 8)):
            regs[7 + m] = 0b101 if m == 0 else 0
        regs[15:17] = _u32_little(round(s.charge_kwh * 1000 / s.towers))
        regs[17:19] = _u32_little(round(s.discharge_kwh * 1000 / s.towers))
        regs[21] = round(s.voltage * 10)
        regs[23] = 1560
        regs[24] = round(s.voltage * 10)
        regs[25] = s.soc * 10
        regs[26] = s.soh
        regs[27] = _i16(round(s.current * 10 / s.towers))
        regs[28] = 0
        regs[29] = 0
        regs[30] = 0
        regs[31:42] = [6659, 7683, 256, 20528, 13104, 21552, 12848, 23090, 12848, 14129, 12593]
        regs[42:44] = [13619, 12920]
        regs[44:48] = [30840, 30840, 270, 270]
        regs[48] = 0
        voltage_slots = list(range(49, 65)) + list(range(66, 130)) + list(range(131, 180))
        temp_slots = list(range(180, 195)) + list(range(196, 213))
        for m in range(s.modules):
            for i in range(min(cells, 16)):
                idx = i + m * 16
                if idx < len(voltage_slots):
                    regs[voltage_slots[idx]] = 3300 + bms_id * 10 + m * 3 + i
            for i in range(round(temps / 2)):
                idx = i + m * 4
                if idx < len(temp_slots):
                    regs[temp_slots[idx]] = (20 + m) << 8 | (21 + i)
        regs[65] = 130
        regs[130] = 130
        regs[195] = 130
        return regs

    def _log_entries_for_unit(self, unit_id: int) -> list[dict[str, Any]]:
        entries = [e for e in self.state.log_entries.values() if int(e["u"]) == unit_id]
        entries.sort(key=lambda e: e["ts"], reverse=True)
        return entries

    def log_registers(self, unit_id: int, offset: int) -> list[int]:
        """Return 5 chunks of 65 registers holding up to 20 log entries."""
        entries = self._log_entries_for_unit(unit_id)[offset : offset + 20]
        payload: list[int] = []
        for entry in entries:
            ts = datetime.fromtimestamp(entry["ts"])
            data = bytes.fromhex(entry["data"]).ljust(23, b"\x00")
            sub = [
                int(entry["c"]) << 8 | (ts.year - 2000),
                ts.month << 8 | ts.day,
                ts.hour << 8 | ts.minute,
                ts.second << 8 | data[0],
            ]
            sub += [data[i] << 8 | data[i + 1] for i in range(1, 23, 2)]
            payload += sub
        payload += [0] * (320 - len(payload))
        regs: list[int] = []
        for chunk in range(5):
            regs += [64, *payload[chunk * 64 : chunk * 64 + 64]]
        return regs

    # ------------------------------------------------------------------ protocol
    def read(self, address: int, count: int) -> list[int] | None:
        """Handle a read holding registers request."""
        self.state.reads += 1
        if self.state.fail_reads:
            return None
        if address in self._ready:
            return [READY if self._ready[address] and not self.state.never_ready else 0] * count
        if address in (0x0558, 0x05A8):
            if not self._fifo:
                return None
            return self._fifo.pop(0)[:count]
        base: dict[int, list[int]] = {
            0x0000: self.info_registers(),
            0x0010: self.info_registers()[16:18],
            0x0500: self.bmu_status_registers(),
        }
        for start, regs in base.items():
            if start <= address and address + count <= start + len(regs):
                return regs[address - start : address - start + count]
        return [0] * count

    def write(self, address: int, values: list[int]) -> bool:
        """Handle a write multiple registers request."""
        self.state.writes.append((address, list(values)))
        if address == 0x0550:
            regs = self.bms_status_registers(values[0])
            self._fifo = [regs[i : i + 65] for i in range(0, 260, 65)]
            self._ready[0x0551] = 1
            return True
        if address == 0x05A0:
            unit_id = values[0]
            offset = self._log_offsets.get(unit_id, 0)
            regs = self.log_registers(unit_id, offset)
            self._log_offsets[unit_id] = offset + 20
            self._fifo = [regs[i : i + 65] for i in range(0, 325, 65)]
            self._ready[0x05A1] = 1
            return True
        return True

    def reset_log_offsets(self) -> None:
        """Start reading logs from the newest entry again."""
        self._log_offsets = {}

    # ----------------------------------------------------------------- transport
    def handle_frame(self, frame: bytes) -> bytes:
        """Handle one RTU frame and return the response frame."""
        device_id, func = frame[0], frame[1]
        if func == 3:
            address, count = struct.unpack(">HH", frame[2:6])
            regs = self.read(address, count)
            if regs is None:
                body = bytes([device_id, 0x83, 0x04])
            else:
                data = b"".join(struct.pack(">H", r & 0xFFFF) for r in regs)
                body = bytes([device_id, 3, len(data)]) + data
        elif func == 16:
            address, qty, _bytecount = struct.unpack(">HHB", frame[2:7])
            values = list(struct.unpack(f">{qty}H", frame[7 : 7 + qty * 2]))
            self.write(address, values)
            body = bytes([device_id, 16]) + struct.pack(">HH", address, qty)
        else:
            body = bytes([device_id, func | 0x80, 0x01])
        crc = crc16(body)
        return body + bytes([crc & 0xFF, crc >> 8])

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Serve one TCP client."""
        try:
            while True:
                header = await reader.readexactly(2)
                func = header[1]
                if func == 3:
                    rest = await reader.readexactly(6)
                elif func == 16:
                    fixed = await reader.readexactly(5)
                    rest = fixed + await reader.readexactly(fixed[4] + 2)
                else:
                    rest = await reader.readexactly(6)
                if self.state.drop_connection:
                    break
                writer.write(self.handle_frame(header + rest[:-2]))
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()


def load_fixture_log() -> dict[str, dict[str, Any]]:
    """Load the recorded log entries shipped with the tests."""
    return json.loads(FIXTURE_LOG.read_text(encoding="utf-8"))


async def start_simulator(
    simulator: BydSimulator, host: str = "127.0.0.1", port: int = 0
) -> tuple[asyncio.Server, int]:
    """Start the simulator and return the server and the bound port."""
    server = await asyncio.start_server(simulator.handle_client, host, port)
    bound_port = server.sockets[0].getsockname()[1]
    return server, bound_port


async def _main() -> None:  # pragma: no cover - manual tool
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--towers", type=int, default=2)
    parser.add_argument("--modules", type=int, default=3)
    parser.add_argument("--model", default="HVM", choices=sorted(HV_TYPES))
    args = parser.parse_args()
    state = BydSimulatorState(towers=args.towers, modules=args.modules, model=args.model, log_entries=load_fixture_log())
    server, port = await start_simulator(BydSimulator(state), args.host, args.port)
    print(f"BYD simulator listening on {args.host}:{port}")  # noqa: T201
    async with server:
        await server.serve_forever()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(_main())
