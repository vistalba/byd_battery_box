"""Persistence of BYD Battery Box log entries."""

from __future__ import annotations

import csv
import json
import logging
import os
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import slugify

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
LEGACY_LOG_DIR = ("custom_components", DOMAIN, "logs")
LEGACY_LOG_FILE = "byd_log.json"

type LogDict = dict[str, dict[str, Any]]


class BydLogStore:
    """Store BYD log entries in HA storage and export them as CSV.

    Log entries were previously written to ``custom_components/byd_battery_box/logs``,
    which is wiped on every HACS update. They now live in ``.storage`` and a CSV export
    is written to ``<config>/byd_battery_box/``.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str, title: str) -> None:
        """Initialize the log store."""
        self._hass = hass
        self._store: Store[LogDict] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}.log")
        self.export_dir = hass.config.path(DOMAIN)
        self.csv_path = os.path.join(self.export_dir, f"{slugify(title) or DOMAIN}_log.csv")

    async def async_load(self) -> LogDict:
        """Load log entries, migrating the legacy JSON file if needed."""
        data = await self._store.async_load()
        if data is not None:
            return data
        legacy = await self._hass.async_add_executor_job(self._load_legacy)
        if legacy:
            _LOGGER.info("Migrated %s BYD log entries from legacy log file", len(legacy))
            await self._store.async_save(legacy)
        return legacy

    def _load_legacy(self) -> LogDict:
        """Load the legacy JSON log file (blocking)."""
        path = self._hass.config.path(*LEGACY_LOG_DIR, LEGACY_LOG_FILE)
        if not os.path.isfile(path):
            return {}
        try:
            with open(path, encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, ValueError) as err:
            _LOGGER.warning("Failed to read legacy BYD log file %s: %s", path, err)
            return {}
        if not isinstance(data, dict):
            return {}
        return data

    async def async_save(self, log: LogDict, csv_rows: list[list[Any]]) -> None:
        """Save log entries and write the CSV export."""
        await self._store.async_save(log)
        await self._hass.async_add_executor_job(self._write_csv, csv_rows)

    def _write_csv(self, rows: list[list[Any]]) -> None:
        """Write the CSV export (blocking)."""
        try:
            os.makedirs(self.export_dir, exist_ok=True)
            with open(self.csv_path, "w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerows(rows)
        except OSError as err:
            _LOGGER.warning("Failed to write BYD log CSV export %s: %s", self.csv_path, err)

    async def async_remove(self) -> None:
        """Remove stored log entries."""
        await self._store.async_remove()
