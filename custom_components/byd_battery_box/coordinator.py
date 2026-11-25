"""Data update coordinator for the BYD Battery Box integration."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .bydboxclient import BydBoxClient
from .const import (
    CONF_BMS_SCAN_INTERVAL,
    CONF_LOG_SCAN_INTERVAL,
    CONF_UNIT_ID,
    DEFAULT_BMS_SCAN_INTERVAL,
    DEFAULT_LOG_SCAN_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT_ID,
    DEVICE_TYPES,
    DOMAIN,
)
from .log_store import BydLogStore

_LOGGER = logging.getLogger(__name__)

# Number of consecutive failed BMU updates before the entities become unavailable.
# The BYD BMU occasionally drops single requests; a single failure should not
# create gaps in the history.
MAX_CONSECUTIVE_FAILURES = 3

type BydBoxConfigEntry = ConfigEntry[BydBoxCoordinator]


def get_entry_value(entry: ConfigEntry, key: str, default: Any) -> Any:
    """Return a setting from the options, falling back to the entry data."""
    if key in entry.options:
        return entry.options[key]
    return entry.data.get(key, default)


class BydBoxCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll BMU, BMS and log data of a BYD Battery Box."""

    config_entry: BydBoxConfigEntry

    def __init__(self, hass: HomeAssistant, entry: BydBoxConfigEntry, client: BydBoxClient | None = None) -> None:
        """Initialize the coordinator."""
        self._health_task: asyncio.Task[None] | None = None
        scan_interval = int(get_entry_value(entry, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.device_name: str = entry.data.get(CONF_NAME, DEFAULT_NAME)
        self.scan_interval_bms = int(get_entry_value(entry, CONF_BMS_SCAN_INTERVAL, DEFAULT_BMS_SCAN_INTERVAL))
        self.scan_interval_log = int(get_entry_value(entry, CONF_LOG_SCAN_INTERVAL, DEFAULT_LOG_SCAN_INTERVAL))
        self.client = client or BydBoxClient(
            host=entry.data[CONF_HOST],
            port=entry.data[CONF_PORT],
            unit_id=entry.data.get(CONF_UNIT_ID, DEFAULT_UNIT_ID),
            timeout=max(3, scan_interval - 1),
        )
        self.log_store = BydLogStore(hass, entry.entry_id, entry.title)
        self._last_bms_update = 0.0
        self._last_log_update = 0.0
        self._failures = 0
        self._log_history_request: tuple[int, int] | None = None

    # ------------------------------------------------------------------ helpers
    @property
    def serial(self) -> str | None:
        """Return the serial number of the BMU."""
        return self.client.data.get("serial") or None

    @property
    def unique_prefix(self) -> str:
        """Return the prefix of unique ids (BMU serial, entry id as fallback)."""
        return self.serial or self.config_entry.entry_id

    @property
    def towers(self) -> int:
        """Return the number of towers (BMS)."""
        return int(self.client.data.get("towers") or 0)

    def _compute_delta_c_v(self) -> None:
        """Compute cell voltage delta (max - min) in mV for each BMS tower."""
        data = self.client.data
        for bms_id in range(1, self.towers + 1):
            max_v = data.get(f"bms{bms_id}_max_c_v")
            min_v = data.get(f"bms{bms_id}_min_c_v")
            if max_v is not None and min_v is not None:
                data[f"bms{bms_id}_delta_c_v"] = round((max_v - min_v) * 1000)
            else:
                data[f"bms{bms_id}_delta_c_v"] = None

    async def _async_save_log(self) -> None:
        """Persist log entries (retention applied)."""
        self.client.apply_log_retention()
        await self.log_store.async_save(self.client.log, self.client.get_log_csv_rows())

    # ---------------------------------------------------------------- lifecycle
    async def _async_setup(self) -> None:
        """Connect to the battery and read the static information."""
        self.client.load_log(await self.log_store.async_load())
        try:
            await self.client.init_data()
        except Exception as err:
            self.client.close()
            raise UpdateFailed(f"Unable to connect to BYD Battery Box: {err}") from err
        if self._health_task is None:
            self._health_task = self.config_entry.async_create_background_task(
                self.hass,
                self.client.health_monitor.periodic_health_update(),
                f"{DOMAIN}_health_monitor_{self.config_entry.entry_id}",
            )

    async def async_shutdown(self) -> None:
        """Stop polling and close the Modbus connection."""
        await super().async_shutdown()
        if self._health_task is not None:
            self._health_task.cancel()
            self._health_task = None
        await self.client.health_monitor.stop_monitoring()
        self.client.close()

    # ------------------------------------------------------------------- update
    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the battery."""
        if self._log_history_request is not None:
            await self._async_update_log_history(*self._log_history_request)
            self._log_history_request = None
            return self.client.data

        now = time.monotonic()
        if not self._last_log_update or now - self._last_log_update > self.scan_interval_log:
            await self._async_update_log()

        if not self._last_bms_update or now - self._last_bms_update > self.scan_interval_bms:
            if await self.client.update_all_bms_status_data():
                self._last_bms_update = time.monotonic()
            else:
                _LOGGER.warning("Updating BMS status data failed")

        try:
            result = await self.client.update_bmu_status_data()
        except Exception as err:  # library raises generic exceptions
            _LOGGER.debug("Error reading BMU status data: %s", err, exc_info=True)
            result = False

        if not result:
            self._failures += 1
            if self._failures >= MAX_CONSECUTIVE_FAILURES or self.data is None:
                raise UpdateFailed(f"Reading BMU status data failed {self._failures} times in a row")
            _LOGGER.debug("Reading BMU status data failed (%s/%s)", self._failures, MAX_CONSECUTIVE_FAILURES)
            return self.client.data

        self._failures = 0
        self._compute_delta_c_v()
        return self.client.data

    async def _async_update_log(self) -> None:
        """Read the newest log entries of all units."""
        prev_len_log = len(self.client.log)
        result = await self.client.update_all_log_data()
        self._last_log_update = time.monotonic()
        if not result:
            _LOGGER.warning("Updating log data failed")
            return
        if prev_len_log != len(self.client.log):
            await self._async_save_log()
        _LOGGER.debug("Updated log data")

    async def _async_update_log_history(self, unit_id: int, log_depth: int) -> None:
        """Read the log history of one unit."""
        prev_len_log = len(self.client.log)
        _LOGGER.warning(
            "Started loading %s log history; all other data updates will be suspended!",
            DEVICE_TYPES[unit_id],
        )
        try:
            await self.client.update_log_history(unit_id, log_depth=log_depth)
        except Exception as err:
            raise UpdateFailed(f"Failed updating {DEVICE_TYPES[unit_id]} log history: {err}") from err
        self._last_log_update = time.monotonic()
        if prev_len_log != len(self.client.log):
            await self._async_save_log()

    # ------------------------------------------------------------------ actions
    async def async_start_update_log_history(self, unit_id: int, log_depth: int) -> None:
        """Schedule reading of the log history (log_depth * 20 entries)."""
        _LOGGER.info("Scheduled %s log update for up to %s log entries.", DEVICE_TYPES[unit_id], log_depth * 20)
        self._log_history_request = (unit_id, log_depth)
        await self.async_request_refresh()

    def reset_history_cell_voltage(self, unit_id: int) -> None:
        """Reset stored per-cell min/max history for one BMS or all (unit_id=0)."""
        ids = range(1, self.towers + 1) if unit_id == 0 else [unit_id]
        for bms_id in ids:
            for suffix in (
                "_max_history_cell_voltage",
                "_max_history_cell_voltage_cells",
                "_min_history_cell_voltage",
                "_min_history_cell_voltage_cells",
            ):
                self.client.data.pop(f"bms{bms_id}{suffix}", None)
        self.async_update_listeners()
