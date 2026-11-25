"""Config flow for the BYD Battery Box integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
)

from .bydboxclient import BydBoxClient
from .const import (
    CONF_BMS_SCAN_INTERVAL,
    CONF_LOG_SCAN_INTERVAL,
    CONF_UNIT_ID,
    DEFAULT_BMS_SCAN_INTERVAL,
    DEFAULT_LOG_SCAN_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT_ID,
    DOMAIN,
    MIN_BMS_SCAN_INTERVAL,
    MIN_LOG_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .coordinator import get_entry_value

_LOGGER = logging.getLogger(__name__)


def _number(minimum: int, maximum: int, unit: str | None = None) -> vol.All:
    """Return a number selector that stores integers."""
    return vol.All(
        NumberSelector(
            NumberSelectorConfig(
                min=minimum,
                max=maximum,
                step=1,
                mode=NumberSelectorMode.BOX,
                **({"unit_of_measurement": unit} if unit else {}),
            )
        ),
        vol.Coerce(int),
    )


CONNECTION_FIELDS: dict[str, Any] = {
    CONF_HOST: TextSelector(),
    CONF_PORT: _number(1, 65535),
    CONF_UNIT_ID: _number(0, 255),
}
INTERVAL_FIELDS: dict[str, Any] = {
    CONF_SCAN_INTERVAL: _number(1, 86400, "s"),
    CONF_BMS_SCAN_INTERVAL: _number(1, 86400, "s"),
    CONF_LOG_SCAN_INTERVAL: _number(1, 86400, "s"),
}


def _user_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME)): TextSelector(),
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, vol.UNDEFINED)): CONNECTION_FIELDS[CONF_HOST],
            vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): CONNECTION_FIELDS[CONF_PORT],
            vol.Required(CONF_UNIT_ID, default=defaults.get(CONF_UNIT_ID, DEFAULT_UNIT_ID)): CONNECTION_FIELDS[CONF_UNIT_ID],
            vol.Optional(CONF_SCAN_INTERVAL, default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): INTERVAL_FIELDS[CONF_SCAN_INTERVAL],
            vol.Optional(CONF_BMS_SCAN_INTERVAL, default=defaults.get(CONF_BMS_SCAN_INTERVAL, DEFAULT_BMS_SCAN_INTERVAL)): INTERVAL_FIELDS[CONF_BMS_SCAN_INTERVAL],
            vol.Optional(CONF_LOG_SCAN_INTERVAL, default=defaults.get(CONF_LOG_SCAN_INTERVAL, DEFAULT_LOG_SCAN_INTERVAL)): INTERVAL_FIELDS[CONF_LOG_SCAN_INTERVAL],
        }
    )


def _reconfigure_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults[CONF_HOST]): CONNECTION_FIELDS[CONF_HOST],
            vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): CONNECTION_FIELDS[CONF_PORT],
            vol.Required(CONF_UNIT_ID, default=defaults.get(CONF_UNIT_ID, DEFAULT_UNIT_ID)): CONNECTION_FIELDS[CONF_UNIT_ID],
        }
    )


def _options_schema(entry: ConfigEntry) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(key, default=int(get_entry_value(entry, key, default))): INTERVAL_FIELDS[key]
            for key, default in (
                (CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                (CONF_BMS_SCAN_INTERVAL, DEFAULT_BMS_SCAN_INTERVAL),
                (CONF_LOG_SCAN_INTERVAL, DEFAULT_LOG_SCAN_INTERVAL),
            )
        }
    )


def validate_intervals(data: dict[str, Any]) -> None:
    """Validate the scan intervals."""
    if data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL) < MIN_SCAN_INTERVAL:
        raise ScanIntervalTooShort
    if data.get(CONF_BMS_SCAN_INTERVAL, DEFAULT_BMS_SCAN_INTERVAL) < MIN_BMS_SCAN_INTERVAL:
        raise BmsScanIntervalTooShort
    if data.get(CONF_LOG_SCAN_INTERVAL, DEFAULT_LOG_SCAN_INTERVAL) < MIN_LOG_SCAN_INTERVAL:
        raise LogScanIntervalTooShort


async def validate_connection(data: dict[str, Any]) -> str | None:
    """Connect to the battery and return the serial number of the BMU."""
    if len(data[CONF_HOST]) < 3:
        raise InvalidHost
    if not (1 <= data[CONF_PORT] <= 65535):
        raise InvalidPort

    client = BydBoxClient(
        host=data[CONF_HOST],
        port=data[CONF_PORT],
        unit_id=data[CONF_UNIT_ID],
        timeout=max(3, data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL) - 1),
    )
    try:
        await client.init_data(close=True)
    except Exception as err:
        _LOGGER.debug("Cannot connect to BYD Battery Box: %s", err)
        raise CannotConnect from err
    finally:
        # BYD batteries only allow one concurrent connection,
        # so a leaked connection blocks all subsequent attempts.
        client.close()

    await asyncio.sleep(0.1)
    return client.data.get("serial") or None


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    validate_intervals(data)
    serial = await validate_connection(data)
    return {"title": data[CONF_NAME], "serial": serial}


def _error_key(err: Exception) -> str:
    """Return the translation key of a validation error."""
    if isinstance(err, ValidationError):
        return err.key
    _LOGGER.exception("Unexpected exception")
    return "unknown"


class BydBoxConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BYD Battery Box."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> BydBoxOptionsFlow:
        """Return the options flow."""
        return BydBoxOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input.setdefault(CONF_NAME, DEFAULT_NAME)
            # A second connection to an already configured battery would fail
            # (the BMU only accepts one connection), so check the host first.
            self._async_abort_entries_match({CONF_HOST: user_input[CONF_HOST]})
            try:
                info = await validate_input(self.hass, user_input)
            except Exception as err:  # noqa: BLE001
                errors["base"] = _error_key(err)
            else:
                if info["serial"]:
                    await self.async_set_unique_id(info["serial"])
                    self._abort_if_unique_id_configured()
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=_user_schema(user_input or {}), errors=errors
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change the connection settings of an existing entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            # The BMU accepts only one connection: stop the running entry
            # while the new settings are tested.
            was_active = entry.state in (ConfigEntryState.LOADED, ConfigEntryState.SETUP_RETRY)
            if was_active:
                await self.hass.config_entries.async_unload(entry.entry_id)
            data = {**entry.data, **user_input}
            try:
                serial = await validate_connection(data)
            except Exception as err:  # noqa: BLE001
                errors["base"] = _error_key(err)
            else:
                if serial and entry.unique_id and serial != entry.unique_id:
                    if was_active:
                        await self.hass.config_entries.async_setup(entry.entry_id)
                    return self.async_abort(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=entry.unique_id or serial,
                    data_updates=user_input,
                )
            if was_active:
                await self.hass.config_entries.async_setup(entry.entry_id)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_reconfigure_schema({**entry.data, **(user_input or {})}),
            errors=errors,
        )


class BydBoxOptionsFlow(OptionsFlowWithReload):
    """Handle the options (scan intervals) of BYD Battery Box."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                validate_intervals(user_input)
            except ValidationError as err:
                errors["base"] = err.key
            else:
                return self.async_create_entry(data=user_input)

        schema = _options_schema(self.config_entry)
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)


class ValidationError(HomeAssistantError):
    """Base class of validation errors; key is the translation key."""

    key = "unknown"


class CannotConnect(ValidationError):
    """Error to indicate we cannot connect."""

    key = "cannot_connect"


class InvalidHost(ValidationError):
    """Error to indicate there is an invalid hostname."""

    key = "invalid_host"


class InvalidPort(ValidationError):
    """Error to indicate there is an invalid port."""

    key = "invalid_port"


class ScanIntervalTooShort(ValidationError):
    """Error to indicate the scan interval is too short."""

    key = "scan_interval_too_short"


class BmsScanIntervalTooShort(ValidationError):
    """Error to indicate the bms scan interval is too short."""

    key = "bms_scan_interval_too_short"


class LogScanIntervalTooShort(ValidationError):
    """Error to indicate the log scan interval is too short."""

    key = "log_scan_interval_too_short"
