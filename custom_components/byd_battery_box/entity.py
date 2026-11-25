"""Base entity for the BYD Battery Box integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_MANUFACTURER, DOMAIN
from .coordinator import BydBoxCoordinator


def bmu_device_info(coordinator: BydBoxCoordinator) -> DeviceInfo:
    """Return the device info of the battery management unit."""
    data = coordinator.client.data
    return DeviceInfo(
        identifiers={(DOMAIN, f"{coordinator.device_name}_byd_bmu")},
        name="Battery Management Unit",
        manufacturer=ATTR_MANUFACTURER,
        model=data.get("model"),
        serial_number=data.get("serial"),
        sw_version=data.get("bmu_v"),
    )


def bms_device_info(coordinator: BydBoxCoordinator, bms_id: int) -> DeviceInfo:
    """Return the device info of a battery management system (tower)."""
    data = coordinator.client.data
    return DeviceInfo(
        identifiers={(DOMAIN, f"{coordinator.device_name}_byd_bms_{bms_id}")},
        name=f"Battery Management System {bms_id}",
        manufacturer=ATTR_MANUFACTURER,
        model=data.get("model"),
        sw_version=data.get("bms_v"),
        via_device=(DOMAIN, f"{coordinator.device_name}_byd_bmu"),
    )


class BydBoxEntity(CoordinatorEntity[BydBoxCoordinator]):
    """Base entity of the BYD Battery Box integration."""

    def __init__(self, coordinator: BydBoxCoordinator, key: str, bms_id: int | None = None) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._key = key
        self._bms_id = bms_id
        self._attr_device_info = (
            bmu_device_info(coordinator) if bms_id is None else bms_device_info(coordinator, bms_id)
        )
