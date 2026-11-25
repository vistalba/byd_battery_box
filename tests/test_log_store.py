"""Tests for the log store."""

from __future__ import annotations

import os

from homeassistant.core import HomeAssistant

from custom_components.byd_battery_box.log_store import BydLogStore

ENTRY = {"20991231 10:00:00-4-1": {"ts": 4102394400.0, "u": 1, "c": 4, "data": "00" * 23}}


async def test_store_roundtrip(hass: HomeAssistant) -> None:
    """Test saving and loading log entries."""
    store = BydLogStore(hass, "abc", "My Battery")
    assert store.csv_path.endswith("my_battery_log.csv")
    assert await store.async_load() == {}
    await store.async_save(ENTRY, [["ts", "unit"], ["x", "BMU"]])
    assert await BydLogStore(hass, "abc", "My Battery").async_load() == ENTRY
    content = await hass.async_add_executor_job(_read, store.csv_path)
    assert content.splitlines() == ["ts,unit", "x,BMU"]
    await store.async_remove()


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as file:
        return file.read()


def _write_legacy(hass: HomeAssistant, content: str) -> None:
    path = hass.config.path("custom_components", "byd_battery_box", "logs")
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "byd_log.json"), "w", encoding="utf-8") as file:
        file.write(content)


async def test_legacy_invalid(hass: HomeAssistant) -> None:
    """Test invalid legacy files are ignored."""
    store = BydLogStore(hass, "def", "x")
    await hass.async_add_executor_job(_write_legacy, hass, "not json")
    assert await store.async_load() == {}
    await hass.async_add_executor_job(_write_legacy, hass, "[1, 2]")
    assert await store.async_load() == {}


async def test_csv_write_error(hass: HomeAssistant, caplog) -> None:
    """Test a failing CSV export is logged and ignored."""
    store = BydLogStore(hass, "ghi", "x")
    store.export_dir = "/proc/forbidden"
    store.csv_path = "/proc/forbidden/x.csv"
    await store.async_save(ENTRY, [["a"]])
    assert "Failed to write BYD log CSV export" in caplog.text
