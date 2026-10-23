"""Diagnostics: definitions, state and recent commands, to support other cellar models.

Appliance fields are allow-listed, not deny-listed: the hOn appliance list also carries
account ids, purchase dates and the appliance's GPS coordinates. Identifiers that leak
into free text (the MAC is part of the MQTT topic names) are scrubbed everywhere.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from . import HonWineConfigEntry
from .api import HonError

APPLIANCE_FIELDS = (
    "applianceTypeName",
    "applianceTypeId",
    "applianceModelId",
    "modelName",
    "code",
    "brand",
    "series",
    "fwVersion",
    "eepromId",
    "eepromName",
    "connectivity",
    "zone",
    "applianceCapacity",
)
COMMAND_FIELDS = ("timestamp", "commandName", "programName", "parameters", "ancillaryParameters")
REDACT = {
    CONF_EMAIL,
    CONF_PASSWORD,
    "macAddress",
    "mobileId",
    "transactionId",
    "serialNumber",
    "nickName",
}


def _command(entry: dict) -> dict:
    """What was sent, when and from which kind of client; history entries also carry account ids."""
    command = entry.get("command", entry)
    device = command.get("device") or {}
    return {key: command[key] for key in COMMAND_FIELDS if key in command} | {
        "source": {
            key: device[key] for key in ("deviceModel", "appVersion", "mobileOs") if key in device
        },
    }


def _scrub(value: Any, secrets: list[str]) -> Any:
    """Replace every occurrence of the given identifiers, at any depth."""
    if isinstance(value, dict):
        return {key: _scrub(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item, secrets) for item in value]
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, REDACTED)
    return value


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: HonWineConfigEntry
) -> dict:
    cellars = []
    secrets = [entry.data[CONF_EMAIL]]
    for cellar in entry.runtime_data:
        mac = cellar.appliance.get("macAddress", "")
        secrets += [
            s for s in (mac, mac.replace("-", ":"), cellar.appliance.get("serialNumber")) if s
        ]
        try:
            history: list | str = [
                _command(e) for e in (await cellar.client.history(cellar.appliance))[:20]
            ]
        except HonError as err:
            history = f"unavailable: {err}"
        cellars.append(
            {
                "appliance": {
                    key: cellar.appliance[key]
                    for key in APPLIANCE_FIELDS
                    if key in cellar.appliance
                },
                "programs": {key: vars(program) for key, program in cellar.programs.items()},
                "commands": cellar.commands,
                "state": cellar.data,
                "history": history,
            }
        )
    redacted = async_redact_data({"entry": dict(entry.data), "cellars": cellars}, REDACT)
    return _scrub(redacted, secrets)
