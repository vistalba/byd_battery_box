"""Fixtures for the BYD Battery Box tests."""

from __future__ import annotations

import shutil
import sys
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

from byd_simulator import (  # noqa: E402
    BydSimulator,
    BydSimulatorState,
    load_fixture_log,
    start_simulator,
)

DOMAIN = "byd_battery_box"
SERIAL = "P030T020Z2008123456"

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable the custom integration of this repository."""
    import custom_components  # noqa: PLC0415

    path = str(ROOT / "custom_components")
    if path not in list(custom_components.__path__):
        custom_components.__path__ = [path, *custom_components.__path__]


@pytest.fixture(autouse=True)
def cleanup_files(hass: HomeAssistant) -> Generator[None]:
    """Remove files written to the (shared) test config directory."""
    yield
    for path in (hass.config.path("custom_components", DOMAIN), hass.config.path(DOMAIN)):
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def fast_modbus() -> Generator[None]:
    """Speed up the delays of the Modbus protocol."""
    with (
        patch("custom_components.byd_battery_box.bydboxclient.BydBoxClient._min_response_delay", 0.01),
        patch("custom_components.byd_battery_box.bydboxclient.BydBoxClient._retry_delay", 0.01),
    ):
        yield


@pytest.fixture
def simulator_state() -> BydSimulatorState:
    """Return the state of the simulated battery (override to customize)."""
    return BydSimulatorState(log_entries=load_fixture_log())


@pytest.fixture
async def simulator(
    socket_enabled: None, simulator_state: BydSimulatorState
) -> AsyncGenerator[tuple[BydSimulator, int]]:
    """Start a simulated BYD Battery Box on localhost."""
    sim = BydSimulator(simulator_state)
    server, port = await start_simulator(sim)
    yield sim, port
    server.close()


@pytest.fixture
def sim(simulator: tuple[BydSimulator, int]) -> BydSimulator:
    """Return the simulator."""
    return simulator[0]


@pytest.fixture
def entry_data(simulator: tuple[BydSimulator, int]) -> dict[str, Any]:
    """Return config entry data pointing to the simulator."""
    return {
        "name": "BYD Battery Box",
        "host": "127.0.0.1",
        "port": simulator[1],
        "unit_id": 1,
        "scan_interval": 30,
        "bms_scan_interval": 600,
        "log_scan_interval": 600,
    }


@pytest.fixture
def mock_entry(hass: HomeAssistant, entry_data: dict[str, Any]) -> MockConfigEntry:
    """Return a config entry (not set up) without unique id (like 0.1.x)."""
    entry = MockConfigEntry(domain=DOMAIN, title="BYD Battery Box", data=entry_data)
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def setup_entry(hass: HomeAssistant, mock_entry: MockConfigEntry) -> AsyncGenerator[MockConfigEntry]:
    """Set up the integration with the simulator."""
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    yield mock_entry
    if mock_entry.state is ConfigEntryState.LOADED:
        await hass.config_entries.async_unload(mock_entry.entry_id)
        await hass.async_block_till_done()
