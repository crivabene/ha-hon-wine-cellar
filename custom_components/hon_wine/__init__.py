"""Haier hOn wine cellar, controlled exactly like the hOn app does."""

from __future__ import annotations

import asyncio
import hashlib

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HonAuthError, HonClient, HonError
from .const import WINE_CELLAR
from .coordinator import WineCellarCoordinator

PLATFORMS = [Platform.LIGHT, Platform.NUMBER, Platform.SELECT, Platform.SENSOR]

type HonWineConfigEntry = ConfigEntry[list[WineCellarCoordinator]]


def client_for(hass: HomeAssistant, entry: ConfigEntry) -> HonClient:
    # A stable mobile id per entry, so the cloud sees one device, not a new one per restart
    mobile_id = hashlib.sha256(entry.entry_id.encode()).hexdigest()[:16]
    return HonClient(
        async_get_clientsession(hass), entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD], mobile_id
    )


async def async_setup_entry(hass: HomeAssistant, entry: HonWineConfigEntry) -> bool:
    client = client_for(hass, entry)
    try:
        appliances = [a for a in await client.appliances() if a["applianceTypeName"] == WINE_CELLAR]
        cellars = [
            WineCellarCoordinator(hass, entry, client, appliance, await client.commands(appliance))
            for appliance in appliances
        ]
    except HonAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except HonError as err:
        raise ConfigEntryNotReady(f"hOn cloud: {err}") from err
    if not cellars:
        raise ConfigEntryNotReady("no wine cellar on this hOn account")

    await asyncio.gather(*(cellar.async_replay_history() for cellar in cellars))
    await asyncio.gather(*(cellar.async_config_entry_first_refresh() for cellar in cellars))
    entry.runtime_data = cellars
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HonWineConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
