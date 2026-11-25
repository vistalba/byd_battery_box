"""Platform for button integration."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import BMU_BUTTON_TYPES, ENTITY_PREFIX
from .coordinator import BydBoxConfigEntry, BydBoxCoordinator
from .entity import BydBoxEntity

_LOGGER = logging.getLogger(__name__)

# Button presses trigger Modbus operations, run them one at a time.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: BydBoxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add buttons for passed config_entry in HA."""
    coordinator = config_entry.runtime_data

    entities: list[BydBoxButton] = [
        BydBoxButton(coordinator, None, info[0], info[1], info[2], info[5], info[6])
        for info in BMU_BUTTON_TYPES.values()
    ]
    for bms_id in range(1, coordinator.towers + 1):
        entities.extend(
            BydBoxButton(coordinator, bms_id, f"BMS {bms_id} {info[0]}", f"bms{bms_id}_{info[1]}", info[2], info[5], info[6])
            for info in BMU_BUTTON_TYPES.values()
        )

    async_add_entities(entities)


class BydBoxButton(BydBoxEntity, ButtonEntity):
    """Representation of a BYD Battery Box button."""

    def __init__(self, coordinator: BydBoxCoordinator, bms_id: int | None, name, key, device_class, icon, entity_category):
        """Initialize the button."""
        super().__init__(coordinator, key, bms_id)
        self._platform_name = ENTITY_PREFIX
        self._name = name
        self._icon = icon
        if device_class is not None:
            self._attr_device_class = device_class
        self._attr_entity_category = entity_category

    async def async_press(self) -> None:
        """Handle the button press."""
        # Key patterns:
        # - [bmsX_]update_log_history_XXX
        # - [bmsX_]reset_history_cell_voltage
        parts = self._key.split('_')
        device_id = self._bms_id or 0

        if self._key.endswith('reset_history_cell_voltage'):
            self.coordinator.reset_history_cell_voltage(device_id)
            return

        # default: update log history buttons
        try:
            log_depth = int(float(parts[-1]) * 0.05)
        except ValueError:
            log_depth = 0
        await self.coordinator.async_start_update_log_history(device_id, log_depth)

    @property
    def name(self):
        """Return the name."""
        return f"{self._name}"

    @property
    def icon(self):
        """Return the button icon."""
        return self._icon

    @property
    def unique_id(self) -> str | None:
        """Return the unique id."""
        return f"{self._platform_name}_{self._key}"
