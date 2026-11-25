"""Base entity for the BYD Battery Box integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import ATTR_MANUFACTURER, DOMAIN
from .coordinator import BydBoxCoordinator


def bmu_identifier(coordinator: BydBoxCoordinator) -> tuple[str, str]:
    """Return the device registry identifier of the BMU."""
    return (DOMAIN, f"{coordinator.unique_prefix}_bmu")


def bms_identifier(coordinator: BydBoxCoordinator, bms_id: int) -> tuple[str, str]:
    """Return the device registry identifier of a BMS."""
    return (DOMAIN, f"{coordinator.unique_prefix}_bms_{bms_id}")


def bmu_device_info(coordinator: BydBoxCoordinator) -> DeviceInfo:
    """Return the device info of the battery management unit."""
    data = coordinator.client.data
    return DeviceInfo(
        identifiers={bmu_identifier(coordinator)},
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
        identifiers={bms_identifier(coordinator, bms_id)},
        name=f"Battery Management System {bms_id}",
        manufacturer=ATTR_MANUFACTURER,
        model=data.get("model"),
        sw_version=data.get("bms_v"),
        via_device=bmu_identifier(coordinator),
    )


class BydBoxEntity(CoordinatorEntity[BydBoxCoordinator]):
    """Base entity of the BYD Battery Box integration."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BydBoxCoordinator,
        description: EntityDescription,
        legacy_name: str,
        platform: str,
        bms_id: int | None = None,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._bms_id = bms_id
        self._prefix = "" if bms_id is None else f"bms{bms_id}_"
        self._data_key = f"{self._prefix}{description.key}"
        self._attr_unique_id = f"{coordinator.unique_prefix}_{self._data_key}"
        if bms_id is None:
            self._attr_device_info = bmu_device_info(coordinator)
        else:
            self._attr_device_info = bms_device_info(coordinator, bms_id)
            legacy_name = f"BMS {bms_id} {legacy_name}"
        # Keep the entity ids of version 0.1.x for new installations, so
        # dashboards, cards and automations shared by the community keep working.
        self.entity_id = f"{platform}.{slugify(legacy_name)}"

    @property
    def available(self) -> bool:
        """Entities of towers that are no longer reported are unavailable."""
        if self._bms_id is not None and self._bms_id > self.coordinator.towers:
            return False
        return super().available
