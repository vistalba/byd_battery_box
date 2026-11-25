"""Config flow for the BYD Battery Box integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries, exceptions
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant

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
)

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Required(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): int,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): int,
        vol.Optional(CONF_BMS_SCAN_INTERVAL, default=DEFAULT_BMS_SCAN_INTERVAL): int,
        vol.Optional(CONF_LOG_SCAN_INTERVAL, default=DEFAULT_LOG_SCAN_INTERVAL): int,
    }
)

async def validate_input(hass: HomeAssistant, data: dict) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from DATA_SCHEMA with values provided by the user.
    """
    # Validate the data can be used to set up a connection.

    if len(data[CONF_HOST]) < 3:
        raise InvalidHost
    if not (1 <= data[CONF_PORT] <= 65535):
        raise InvalidPort
    if data[CONF_SCAN_INTERVAL] < 10:
        raise ScanIntervalTooShort
    if data[CONF_BMS_SCAN_INTERVAL] < 60:
        raise BmsScanIntervalTooShort
    if data[CONF_LOG_SCAN_INTERVAL] < 120:
        raise LogScanIntervalTooShort

    client = BydBoxClient(
        host=data[CONF_HOST],
        port=data[CONF_PORT],
        unit_id=data[CONF_UNIT_ID],
        timeout=max(3, data[CONF_SCAN_INTERVAL] - 1),
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

    await asyncio.sleep(.1)

    return {"title": data[CONF_NAME], "serial": client.data.get("serial") or None}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow """

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            # A second connection to an already configured battery would fail
            # (the BMU only accepts one connection), so check the host first.
            self._async_abort_entries_match({CONF_HOST: user_input[CONF_HOST]})
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except ScanIntervalTooShort:
                errors["base"] = "scan_interval_too_short"
            except BmsScanIntervalTooShort:
                errors["base"] = "bms_scan_interval_too_short"
            except LogScanIntervalTooShort:
                errors["base"] = "log_scan_interval_too_short"
            except InvalidPort:
                errors["base"] = "invalid_port"
            except InvalidHost:
                errors["base"] = "invalid_host"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                if info["serial"]:
                    await self.async_set_unique_id(info["serial"])
                    self._abort_if_unique_id_configured()
                return self.async_create_entry(title=info["title"], data=user_input)

        # If there is no user input or there were errors, show the form again, including any errors that were found with the input.
        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""

class InvalidHost(exceptions.HomeAssistantError):
    """Error to indicate there is an invalid hostname."""

class InvalidPort(exceptions.HomeAssistantError):
    """Error to indicate there is an invalid hostname."""

class ScanIntervalTooShort(exceptions.HomeAssistantError):
    """Error to indicate the scan interval is too short."""

class BmsScanIntervalTooShort(exceptions.HomeAssistantError):
    """Error to indicate the bms scan interval is too short."""

class LogScanIntervalTooShort(exceptions.HomeAssistantError):
    """Error to indicate the log scan interval is too short."""
