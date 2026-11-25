"""Tests for diagnostics."""

from __future__ import annotations

import json

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.byd_battery_box.diagnostics import async_get_config_entry_diagnostics

from .conftest import SERIAL


async def test_diagnostics(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """Test the diagnostics are complete and redacted."""
    result = await async_get_config_entry_diagnostics(hass, setup_entry)
    assert result["entry"]["data"]["host"] == "**REDACTED**"
    assert result["entry"]["unique_id"] == "**REDACTED**"
    assert result["data"]["serial"] == "**REDACTED**"
    assert result["data"]["soc"] == 85
    assert result["coordinator"]["last_update_success"] is True
    assert result["connection"]["connection_health"] == "healthy"
    assert result["log"]["entries"] >= 0
    dumped = json.dumps(result, default=str)
    assert SERIAL not in dumped
    assert "127.0.0.1" not in dumped
