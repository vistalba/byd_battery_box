"""Diagnostics support for the BYD Battery Box integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import BydBoxConfigEntry

TO_REDACT = {CONF_HOST, "serial", "unique_id", "title"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: BydBoxConfigEntry) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    client = coordinator.client
    return {
        "entry": async_redact_data(
            {"title": entry.title, "unique_id": entry.unique_id, "data": dict(entry.data), "options": dict(entry.options)},
            TO_REDACT,
        ),
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval": coordinator.update_interval.total_seconds() if coordinator.update_interval else None,
            "bms_scan_interval": coordinator.scan_interval_bms,
            "log_scan_interval": coordinator.scan_interval_log,
            "consecutive_failures": coordinator.consecutive_failures,
        },
        "connection": client.get_connection_metrics(),
        "data": async_redact_data(dict(client.data), TO_REDACT),
        "log": {"entries": len(client.log), "last_entries": client.data.get("log")},
    }
