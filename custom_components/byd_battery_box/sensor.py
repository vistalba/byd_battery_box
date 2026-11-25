"""Platform for sensor integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    BMS_SENSOR_TYPES,
    BMU_SENSOR_TYPES,
    CONNECTION_SENSOR_TYPES,
    ENTITY_PREFIX,
)
from .coordinator import BydBoxConfigEntry, BydBoxCoordinator
from .entity import BydBoxEntity

_LOGGER = logging.getLogger(__name__)

# Data is fetched centrally by the coordinator.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: BydBoxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add sensors for passed config_entry in HA."""
    coordinator = config_entry.runtime_data

    entities: list[SensorEntity] = []

    for sensor_info in BMU_SENSOR_TYPES.values():
        entities.append(BydBoxSensor(coordinator, None, *sensor_info))

    # Add connection health monitoring sensors
    for sensor_info in CONNECTION_SENSOR_TYPES.values():
        entities.append(BydBoxConnectionSensor(coordinator, None, *sensor_info))

    for bms_id in range(1, coordinator.towers + 1):
        for sensor_info in BMS_SENSOR_TYPES.values():
            name, key, *rest = sensor_info
            entities.append(BydBoxSensor(coordinator, bms_id, f"BMS {bms_id} {name}", f"bms{bms_id}_{key}", *rest))

    async_add_entities(entities)


class BydBoxSensor(BydBoxEntity, SensorEntity, RestoreEntity):
    """Representation of an BYD Battery Box Modbus sensor."""

    def __init__(self, coordinator: BydBoxCoordinator, bms_id: int | None, name, key, device_class, state_class, unit, icon, entity_category):
        """Initialize the sensor."""
        super().__init__(coordinator, key, bms_id)
        self._platform_name = ENTITY_PREFIX
        self._name = name
        self._unit_of_measurement = unit
        self._icon = icon
        if device_class is not None:
            self._attr_device_class = device_class
        if state_class is not None:
            self._attr_state_class = state_class
        self._attr_entity_category = entity_category

    @property
    def _data(self) -> dict[str, Any]:
        return self.coordinator.client.data

    async def async_added_to_hass(self):
        """Register callbacks."""
        await super().async_added_to_hass()
        # Try to restore last state from HA history for history sensors
        try:
            last_state = await self.async_get_last_state()
        except Exception:
            last_state = None
        if last_state and (
            'max_history_cell_voltage' in self._key or 'min_history_cell_voltage' in self._key
        ):
            # Restore state value
            try:
                val = float(last_state.state)
                self._data[self._key] = val
            except Exception:
                pass
            # Restore per-cell attribute if present
            attrs = getattr(last_state, 'attributes', {}) or {}
            cells = attrs.get('cell_voltages')
            if cells is not None:
                self._data[f'{self._key}_cells'] = cells

    @property
    def name(self):
        """Return the name."""
        return f"{self._name}"

    @property
    def unique_id(self) -> str | None:
        return f"{self._platform_name}_{self._key}"

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit_of_measurement

    @property
    def icon(self):
        """Return the sensor icon."""
        return self._icon

    @property
    def state(self):
        """Return the state of the sensor."""
        if self._key in self._data:
            return self._data.get(self._key)

    @property
    def extra_state_attributes(self):
        if 'balancing_qty' in self._key:
            return {'cell_balancing': self._data.get(f'{self._key[:4]}_cell_balancing')}
        elif 'avg_c_v' in self._key:
            return {
                'cell_voltages': self._data.get(f'{self._key[:4]}_cell_voltages'),
                'cell_voltages_max_history': self._data.get(f'{self._key[:4]}_cell_voltages_max_history'),
                'cell_voltages_min_history': self._data.get(f'{self._key[:4]}_cell_voltages_min_history'),
            }
        elif 'max_history_c_v' in self._key:
            return {
                'cell_voltages_max_history': self._data.get(f'{self._key[:4]}_cell_voltages_max_history'),
                'cell_voltages': self._data.get(f'{self._key[:4]}_cell_voltages'),
            }
        elif 'min_history_c_v' in self._key:
            return {
                'cell_voltages_min_history': self._data.get(f'{self._key[:4]}_cell_voltages_min_history'),
                'cell_voltages': self._data.get(f'{self._key[:4]}_cell_voltages'),
            }
        elif 'avg_c_t' in self._key:
            return {'cell_temps': self._data.get(f'{self._key[:4]}_cell_temps')}
        elif 'log_entries' in self._key:
            return {'log': self._data.get('log')}
        elif 'b_total' in self._key:
            return {'total_cells': self._data.get(f'{self._key[:4]}_b_cells_total')}
        elif 'max_history_cell_voltage' in self._key or 'min_history_cell_voltage' in self._key:
            return {'cell_voltages': self._data.get(f'{self._key}_cells')}

        return None


class BydBoxConnectionSensor(BydBoxEntity, SensorEntity):
    """Representation of a BYD Battery Box connection health sensor."""

    def __init__(self, coordinator: BydBoxCoordinator, bms_id: int | None, name, key, device_class, state_class, unit, icon, entity_category):
        """Initialize the connection sensor."""
        super().__init__(coordinator, key, bms_id)
        self._platform_name = ENTITY_PREFIX
        self._name = name
        self._unit_of_measurement = unit
        self._icon = icon
        if device_class is not None:
            self._attr_device_class = device_class
        if state_class is not None:
            self._attr_state_class = state_class
        self._attr_entity_category = entity_category

    @property
    def name(self):
        """Return the name."""
        return f"{self._name}"

    @property
    def unique_id(self) -> str | None:
        return f"{self._platform_name}_{self._key}"

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit_of_measurement

    @property
    def icon(self):
        """Return the sensor icon."""
        return self._icon

    @property
    def state(self):
        """Return the state of the connection sensor."""
        # Get connection metrics from the client
        metrics = self.coordinator.client.get_connection_metrics()
        return metrics.get(self._key)

    @property
    def available(self) -> bool:
        """Connection sensors stay available to show the connection problem."""
        return True
