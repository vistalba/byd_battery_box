"""Sensor platform for the BYD Battery Box integration."""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    Platform,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import StateType

from .coordinator import BydBoxConfigEntry, BydBoxCoordinator
from .entity import BydBoxEntity

_LOGGER = logging.getLogger(__name__)

# Data is fetched centrally by the coordinator.
PARALLEL_UPDATES = 0

type AttrFn = Callable[[dict[str, Any], str, str], dict[str, Any] | None]


@dataclass(frozen=True, kw_only=True)
class BydBoxSensorEntityDescription(SensorEntityDescription):
    """Describes a BYD Battery Box sensor."""

    # Name used up to version 0.1.x, used to keep the entity ids stable.
    legacy_name: str
    # Returns extra state attributes: (data, bms prefix e.g. "bms1_", data key)
    attr_fn: AttrFn | None = None
    # Restore the last state after a restart (history values)
    restore: bool = False
    # Value is read from the connection health metrics instead of the data
    connection_metric: bool = False


def _attrs(**mapping: str) -> AttrFn:
    """Build an attr_fn returning data values; '{p}' is the bms prefix, '{k}' the data key."""

    def _fn(data: dict[str, Any], prefix: str, key: str) -> dict[str, Any]:
        return {attr: data.get(src.format(p=prefix, k=key)) for attr, src in mapping.items()}

    return _fn


VOLTAGE = {
    "device_class": SensorDeviceClass.VOLTAGE,
    "state_class": SensorStateClass.MEASUREMENT,
    "native_unit_of_measurement": UnitOfElectricPotential.VOLT,
    "icon": "mdi:lightning-bolt",
}
TEMPERATURE = {
    "device_class": SensorDeviceClass.TEMPERATURE,
    "state_class": SensorStateClass.MEASUREMENT,
    "native_unit_of_measurement": UnitOfTemperature.CELSIUS,
    "icon": "mdi:thermometer",
}
ENERGY_TOTAL = {
    "device_class": SensorDeviceClass.ENERGY,
    "state_class": SensorStateClass.TOTAL_INCREASING,
    "native_unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
}
CURRENT = {
    "device_class": SensorDeviceClass.CURRENT,
    "state_class": SensorStateClass.MEASUREMENT,
    "native_unit_of_measurement": UnitOfElectricCurrent.AMPERE,
    "icon": "mdi:lightning-bolt",
}
SOC = {
    "device_class": SensorDeviceClass.BATTERY,
    "state_class": SensorStateClass.MEASUREMENT,
    "native_unit_of_measurement": PERCENTAGE,
    "icon": "mdi:battery",
}
SOH = {
    "state_class": SensorStateClass.MEASUREMENT,
    "native_unit_of_measurement": PERCENTAGE,
    "icon": "mdi:battery",
}
DIAG = {"entity_category": EntityCategory.DIAGNOSTIC}


def _d(key: str, legacy_name: str, **kwargs: Any) -> BydBoxSensorEntityDescription:
    return BydBoxSensorEntityDescription(key=key, translation_key=key.lower(), legacy_name=legacy_name, **kwargs)


BMU_SENSORS: tuple[BydBoxSensorEntityDescription, ...] = (
    _d("inverter", "Inverter", **DIAG),
    _d("bmu_v", "BMU version", **DIAG),
    _d("bmu_v_A", "BMU version A", entity_registry_enabled_default=False, **DIAG),
    _d("bmu_v_B", "BMU version B", entity_registry_enabled_default=False, **DIAG),
    _d("bms_v", "BMS version", **DIAG),
    _d("towers", "Towers", icon="mdi:counter", **DIAG),
    _d("modules", "Modules", icon="mdi:counter", **DIAG),
    _d("application", "Application", **DIAG),
    _d("phase", "Phase", **DIAG),
    _d("errors", "Errors", **DIAG),
    _d(
        "capacity",
        "Total capacity",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        **DIAG,
    ),
    _d("param_t_v", "Param table version", entity_registry_enabled_default=False, **DIAG),
    _d("sensors_t", "Temperature sensors per module", **DIAG),
    _d("cells", "Cells per module", **DIAG),
    _d("soc", "State of charge", **SOC),
    _d("soh", "State of health", **SOH),
    _d("bmu_temp", "BMU temperature", **TEMPERATURE),
    _d("max_cell_temp", "BMU cell temperature max", **TEMPERATURE),
    _d("min_cell_temp", "BMU cell temperature min", **TEMPERATURE),
    _d("max_cell_v", "BMU cell voltage max", **VOLTAGE),
    _d("min_cell_v", "BMU cell voltage min", **VOLTAGE),
    _d("current", "BMU current", **CURRENT),
    _d("bat_voltage", "BMU battery voltage", **VOLTAGE),
    _d("output_voltage", "BMU output voltage", **VOLTAGE),
    _d(
        "power",
        "BMU power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:lightning-bolt",
    ),
    _d("charge_lfte", "Charge total energy", **ENERGY_TOTAL),
    _d("discharge_lfte", "Discharge total energy", **ENERGY_TOTAL),
    _d("efficiency", "Efficiency", native_unit_of_measurement=PERCENTAGE),
    _d("updated", "Updated", device_class=SensorDeviceClass.TIMESTAMP, **DIAG),
    _d("bmu_last_log", "BMU last log", **DIAG),
    _d("log_entries", "Log entries", attr_fn=_attrs(log="log"), **DIAG),
)

CONNECTION_SENSORS: tuple[BydBoxSensorEntityDescription, ...] = (
    _d(
        "connection_quality",
        "Connection Quality",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:connection",
        connection_metric=True,
        **DIAG,
    ),
    _d(
        "last_latency",
        "Last Latency",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        icon="mdi:timer",
        connection_metric=True,
        entity_registry_enabled_default=False,
        **DIAG,
    ),
    _d(
        "avg_latency",
        "Average Latency",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        icon="mdi:timer",
        connection_metric=True,
        **DIAG,
    ),
    _d(
        "consecutive_failures",
        "Consecutive Failures",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:alert-circle",
        connection_metric=True,
        **DIAG,
    ),
    _d("connection_health", "Connection Health", icon="mdi:check-circle", connection_metric=True, **DIAG),
)

_CELL_VOLTAGES = _attrs(
    cell_voltages="{p}cell_voltages",
    cell_voltages_max_history="{p}cell_voltages_max_history",
    cell_voltages_min_history="{p}cell_voltages_min_history",
)

BMS_SENSORS: tuple[BydBoxSensorEntityDescription, ...] = (
    _d("max_c_v", "Cell voltage max", **VOLTAGE),
    _d("min_c_v", "Cell voltage min", **VOLTAGE),
    _d(
        "delta_c_v",
        "Cells voltage delta",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        icon="mdi:delta",
        **DIAG,
    ),
    _d("max_c_v_id", "Cell voltage max number"),
    _d("min_c_v_id", "Cell voltage min number"),
    _d("max_c_t", "Cell temperature max", **TEMPERATURE),
    _d("min_c_t", "Cell temperature min", **TEMPERATURE),
    _d("max_c_t_id", "Cell temperature max number"),
    _d("min_c_t_id", "Cell temperature min number"),
    _d("soh", "State of health", **SOH),
    _d("soc", "State of charge", **SOC),
    _d("current", "Current", **CURRENT),
    _d("bat_voltage", "Battery voltage", **VOLTAGE),
    _d("output_voltage", "Output voltage", **VOLTAGE),
    _d("charge_lfte", "Charge total energy", **ENERGY_TOTAL),
    _d("discharge_lfte", "Discharge total energy", **ENERGY_TOTAL),
    _d("efficiency", "Efficiency", native_unit_of_measurement=PERCENTAGE),
    _d("balancing_qty", "Cells balancing", icon="mdi:counter", attr_fn=_attrs(cell_balancing="{p}cell_balancing")),
    _d("warnings", "Warnings", **DIAG),
    _d("errors", "Errors", **DIAG),
    _d("avg_c_v", "Cells average voltage", attr_fn=_CELL_VOLTAGES, **VOLTAGE),
    _d("avg_c_t", "Cells average temperature", attr_fn=_attrs(cell_temps="{p}cell_temps"), **{**TEMPERATURE, "icon": "mdi:lightning-bolt"}),
    _d(
        "max_history_cell_voltage",
        "Max history cell voltage",
        attr_fn=_attrs(cell_voltages="{k}_cells"),
        restore=True,
        **VOLTAGE,
    ),
    _d(
        "min_history_cell_voltage",
        "Min history cell voltage",
        attr_fn=_attrs(cell_voltages="{k}_cells"),
        restore=True,
        **VOLTAGE,
    ),
    _d("updated", "Updated", device_class=SensorDeviceClass.TIMESTAMP, **DIAG),
    _d("last_log", "Last log", **DIAG),
    _d("b_total", "Balancing total", attr_fn=_attrs(total_cells="{p}b_cells_total")),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: BydBoxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add sensors for passed config_entry in HA."""
    coordinator = config_entry.runtime_data

    entities: list[BydBoxSensor] = [BydBoxSensor(coordinator, d) for d in (*BMU_SENSORS, *CONNECTION_SENSORS)]
    entities.extend(
        BydBoxSensor(coordinator, description, bms_id)
        for bms_id in range(1, coordinator.towers + 1)
        for description in BMS_SENSORS
    )
    async_add_entities(entities)


class BydBoxSensor(BydBoxEntity, SensorEntity, RestoreEntity):
    """Representation of a BYD Battery Box sensor."""

    entity_description: BydBoxSensorEntityDescription

    # Large, frequently changing attributes are not written to the recorder database.
    _unrecorded_attributes = frozenset(
        {
            "log",
            "cell_voltages",
            "cell_voltages_max_history",
            "cell_voltages_min_history",
            "cell_temps",
            "cell_balancing",
            "total_cells",
        }
    )

    def __init__(
        self,
        coordinator: BydBoxCoordinator,
        description: BydBoxSensorEntityDescription,
        bms_id: int | None = None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description, description.legacy_name, Platform.SENSOR, bms_id)

    @property
    def _data(self) -> dict[str, Any]:
        return self.coordinator.client.data

    async def async_added_to_hass(self) -> None:
        """Restore history values."""
        await super().async_added_to_hass()
        if not self.entity_description.restore:
            return
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        with contextlib.suppress(ValueError):
            self._data[self._data_key] = float(last_state.state)
        cells = last_state.attributes.get("cell_voltages")
        if cells is not None:
            self._data[f"{self._data_key}_cells"] = cells

    @property
    def available(self) -> bool:
        """Connection sensors stay available to show the connection problem."""
        if self.entity_description.connection_metric:
            return True
        return super().available

    @property
    def native_value(self) -> StateType | Any:
        """Return the state of the sensor."""
        if self.entity_description.connection_metric:
            return self.coordinator.client.get_connection_metrics().get(self.entity_description.key)
        return self._data.get(self._data_key)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        if self.entity_description.attr_fn is None:
            return None
        return self.entity_description.attr_fn(self._data, self._prefix, self._data_key)
