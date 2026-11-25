"""Button platform for the BYD Battery Box integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import BydBoxConfigEntry, BydBoxCoordinator
from .entity import BydBoxEntity

_LOGGER = logging.getLogger(__name__)

# Button presses trigger Modbus operations, run them one at a time.
PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class BydBoxButtonEntityDescription(ButtonEntityDescription):
    """Describes a BYD Battery Box button."""

    # Name used up to version 0.1.x, used to keep the entity ids stable.
    legacy_name: str
    # Number of log entries read (0 for the reset button)
    log_entries: int = 0


BUTTONS: tuple[BydBoxButtonEntityDescription, ...] = (
    BydBoxButtonEntityDescription(
        key="update_log_history_100",
        translation_key="update_log_history_100",
        legacy_name="Update last 100 log entries",
        log_entries=100,
    ),
    BydBoxButtonEntityDescription(
        key="update_log_history_500",
        translation_key="update_log_history_500",
        legacy_name="Update last 500 log entries",
        log_entries=500,
        entity_registry_enabled_default=False,
    ),
    BydBoxButtonEntityDescription(
        key="update_log_history_1000",
        translation_key="update_log_history_1000",
        legacy_name="Update last 1000 log entries",
        log_entries=1000,
        entity_registry_enabled_default=False,
    ),
    BydBoxButtonEntityDescription(
        key="update_log_history_2000",
        translation_key="update_log_history_2000",
        legacy_name="Update last 2000 log entries",
        log_entries=2000,
        entity_registry_enabled_default=False,
    ),
    BydBoxButtonEntityDescription(
        key="reset_history_cell_voltage",
        translation_key="reset_history_cell_voltage",
        legacy_name="Reset history cell voltage",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: BydBoxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add buttons for passed config_entry in HA."""
    coordinator = config_entry.runtime_data
    async_add_entities(BydBoxButton(coordinator, description) for description in BUTTONS)

    known_towers: set[int] = set()

    @callback
    def _async_add_towers() -> None:
        """Add the buttons of new towers (also when towers are added later)."""
        new_towers = [i for i in range(1, coordinator.towers + 1) if i not in known_towers]
        if not new_towers:
            return
        known_towers.update(new_towers)
        async_add_entities(
            BydBoxButton(coordinator, description, bms_id) for bms_id in new_towers for description in BUTTONS
        )

    _async_add_towers()
    config_entry.async_on_unload(coordinator.async_add_listener(_async_add_towers))


class BydBoxButton(BydBoxEntity, ButtonEntity):
    """Representation of a BYD Battery Box button."""

    entity_description: BydBoxButtonEntityDescription

    def __init__(
        self,
        coordinator: BydBoxCoordinator,
        description: BydBoxButtonEntityDescription,
        bms_id: int | None = None,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, description, description.legacy_name, Platform.BUTTON, bms_id)

    async def async_press(self) -> None:
        """Handle the button press."""
        unit_id = self._bms_id or 0
        if self.entity_description.log_entries == 0:
            self.coordinator.reset_history_cell_voltage(unit_id)
            return
        if not self.coordinator.last_update_success:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="not_reachable")
        await self.coordinator.async_start_update_log_history(unit_id, self.entity_description.log_entries // 20)
