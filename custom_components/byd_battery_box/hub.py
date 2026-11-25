"""BYD Battery Box Hub."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval

from .bydboxclient import BydBoxClient
from .const import ATTR_MANUFACTURER, DEVICE_TYPES, DOMAIN
from .log_store import BydLogStore

_LOGGER = logging.getLogger(__name__)

class Hub:
    """Hub for BYD Battery Box Interface"""

    def __init__(self, hass: HomeAssistant, name: str, host: str, port: int, unit_id: int, scan_interval: int, scan_interval_bms: int = 600, scan_interval_log: int = 600, entry: ConfigEntry | None = None) -> None:
        """Init hub."""
        self._hass = hass
        self._entry = entry
        self._log_store = BydLogStore(hass, entry.entry_id, entry.title) if entry is not None else None
        self._name = name
        self._id = f'{name.lower()}_{host.lower().replace('.','')}'
        self._last_full_update = datetime(2000,1,1)
        self._last_log_update = datetime(2000,1,1)
        self._last_update = datetime(2000,1,1)
        self._unsub_interval_method = None
        self._entities = []
        self._min_update_interval = timedelta(seconds=1)
        self._scan_interval = timedelta(seconds=scan_interval)
        self._scan_interval_bms = timedelta(seconds=scan_interval_bms)
        self._scan_interval_log = timedelta(seconds=scan_interval_log)
        self._bydclient = BydBoxClient(host=host, port=port, unit_id=unit_id, timeout=max(3, (scan_interval - 1)))
        self.online = True
        self._lock = asyncio.Lock()
        self._health_task: asyncio.Task | None = None
        self._update_log_history_depth = [0,0]


    @property
    def data(self):
        return self._bydclient.data

    @property
    def device_info_bmu(self) -> dict:
        return {
            "identifiers": {(DOMAIN, f'{self._name}_byd_bmu')},
            "name": 'Battery Management Unit',
            "manufacturer": ATTR_MANUFACTURER,
            "model": self._bydclient.data.get('model'),
            "serial_number": self._bydclient.data.get('serial'),
            "sw_version": self._bydclient.data.get('bmu_v'),
        }

    def get_device_info_bms(self,id) -> dict:
        return {
            "identifiers": {(DOMAIN, f'{self._name}_byd_bms_{id}')},
            "name": f'Battery Management System {id}',
            "manufacturer": ATTR_MANUFACTURER,
            "model": self._bydclient.data.get('model'),
            #"serial_number": self._bydclient.data.get('serial'),
            "sw_version": self._bydclient.data.get('bms_v'),
        }

    @property
    def serial(self) -> str | None:
        """Serial number of the BMU."""
        return self._bydclient.data.get('serial') or None

    @property
    def hub_id(self) -> str:
        """ID for hub."""
        return self._id

    @callback
    def async_add_hub_entity(self, update_callback):
        """Listen for data updates."""
        # This is the first entity, set up interval.
        if not self._entities:
            self._unsub_interval_method = async_track_time_interval(
                self._hass, self.async_update_data, self._scan_interval
            )
        self._entities.append(update_callback)

    @callback
    def async_remove_hub_entity(self, update_callback):
        """Remove data update."""
        self._entities.remove(update_callback)

        if not self._entities:
            """stop the interval timer upon removal of last entity"""
            if self._unsub_interval_method is not None:
                self._unsub_interval_method()
            self._unsub_interval_method = None

    async def init_data(self, close = False):
        async with self._lock:
            if self._log_store is not None:
                self._bydclient.load_log(await self._log_store.async_load())
            await self._bydclient.init_data(close = close)
            # Start connection health monitoring; the task is bound to the config
            # entry and cancelled automatically when the entry is unloaded.
            if self._entry is not None and self._health_task is None:
                self._health_task = self._entry.async_create_background_task(
                    self._hass,
                    self._bydclient.health_monitor.periodic_health_update(),
                    f"{DOMAIN}_health_monitor",
                )
            self._compute_delta_c_v()
            self.update_entities()

    async def _async_save_log(self) -> None:
        """Persist log entries (retention applied)."""
        self._bydclient.apply_log_retention()
        if self._log_store is not None:
            await self._log_store.async_save(self._bydclient.log, self._bydclient.get_log_csv_rows())

    async def async_update_data(self, _now: int | None = None) -> dict:
        """Time to update."""
        if not self._bydclient.initialized:
            return

        if ((datetime.now()-self._last_update) < self._min_update_interval):
            #_LOGGER.debug(f"Skip update give system a break ;-)")
            return

        async with self._lock:
            # update log history
            unit_id = self._update_log_history_depth[0]
            log_depth = self._update_log_history_depth[1]
            if self._update_log_history_depth[1] > 0:
                prev_len_log = len(self._bydclient.log)
                _LOGGER.warning(f"Started loading {DEVICE_TYPES[unit_id]} log history; all other data updates will be suspended!")
                try:
                    await self._bydclient.update_log_history(unit_id, log_depth=log_depth)
                    self._last_log_update = datetime.now()
                    self._last_update = datetime.now()
                except Exception as e:
                    _LOGGER.error(f'Failed updating {DEVICE_TYPES[unit_id]} log history {self._update_log_history_depth} {e}', exc_info=True)
                    return False
                self._update_log_history_depth[1] = 0
                if prev_len_log != len(self._bydclient.log):
                    await self._async_save_log()
                self.update_entities()
                return True

            # update last log data
            if ((datetime.now()-self._last_log_update) > self._scan_interval_log):
                #_LOGGER.debug(f"start update log data")
                prev_len_log = len(self._bydclient.log)
                result = await self._bydclient.update_all_log_data()
                self._last_log_update = datetime.now()
                self._last_update = datetime.now()
                if result:
                    self.update_entities()
                    if prev_len_log != len(self._bydclient.log):
                        await self._async_save_log()
                    _LOGGER.debug("updated log data")
                else:
                    _LOGGER.error("update log data failed")
                    await asyncio.sleep(5)

            # update bms data
            if ((datetime.now()-self._last_full_update) > self._scan_interval_bms):
                #_LOGGER.debug(f"start update BMS status")
                result = await self._bydclient.update_all_bms_status_data()
                if result:
                    self._last_full_update = datetime.now()
                    self._last_update = datetime.now()
                    self._compute_delta_c_v()
                    self.update_entities()
                    _LOGGER.debug("updated BMS status")
                else:
                    _LOGGER.error("update BMS status data failed")
                    await asyncio.sleep(5)

            # update bmu
            try:
                #_LOGGER.debug(f"start update BMU status")
                result = await self._bydclient.update_bmu_status_data()
            except Exception as e:
                _LOGGER.error(f"Error reading BMU status data connection {self._bydclient.connected} error: {e} ", exc_info=True)
                return False
            if result:
                self._last_update = datetime.now()
                self._compute_delta_c_v()
                self.update_entities()
                _LOGGER.debug("updated BMU status")
            else:
                _LOGGER.warning(f"update BMU status data failed {self._bydclient.connected}")
                return False

            return True

    def _compute_delta_c_v(self):
        """Compute cell voltage delta (max - min) for each BMS tower."""
        for bms_id in range(1, self._bydclient._bms_qty + 1):
            max_v = self._bydclient.data.get(f'bms{bms_id}_max_c_v')
            min_v = self._bydclient.data.get(f'bms{bms_id}_min_c_v')
            if max_v is not None and min_v is not None:
                self._bydclient.data[f'bms{bms_id}_delta_c_v'] = round((max_v - min_v) * 1000)
            else:
                self._bydclient.data[f'bms{bms_id}_delta_c_v'] = None

    def update_entities(self):
        for update_callback in self._entities:
            update_callback()

    async def close(self):
        """Disconnect client."""
        if self._unsub_interval_method is not None:
            self._unsub_interval_method()
            self._unsub_interval_method = None
        if self._health_task is not None:
            self._health_task.cancel()
            self._health_task = None
        await self._bydclient.health_monitor.stop_monitoring()
        self._bydclient.close()
        _LOGGER.debug("close hub")

    async def test_connection(self) -> bool:
        """Test connectivity"""
        _LOGGER.debug("test connection")
        try:
            return await self._bydclient.connect()
        except Exception:
            _LOGGER.exception("Error connecting to the device")
            return False

    def start_update_log_history(self, unit_id, log_depth):
         _LOGGER.info(f"Scheduled {DEVICE_TYPES[unit_id]} log update for up to {log_depth*20} log entries.")
         self._update_log_history_depth = [unit_id, log_depth]

    def reset_history_cell_voltage(self, unit_id:int):
         """Reset stored per-cell min/max history for one BMS or all (unit_id=0)."""
         if unit_id == 0:
             ids = range(1, self._bydclient._bms_qty + 1)
         else:
             ids = [unit_id]
         for bms_id in ids:
             for suffix in [
                 '_max_history_cell_voltage',
                 '_max_history_cell_voltage_cells',
                 '_min_history_cell_voltage',
                 '_min_history_cell_voltage_cells',
             ]:
                 key = f'bms{bms_id}{suffix}'
                 if key in self._bydclient.data:
                     try:
                         del self._bydclient.data[key]
                     except Exception:
                         self._bydclient.data[key] = None
         self.update_entities()
