"""Fixtures: an hon_wine config entry backed by a fake hOn cloud."""

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hon_wine.api import Snapshot
from custom_components.hon_wine.const import DOMAIN

from . import fixtures


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


class FakeCloud:
    """Holds the cellar state; snapshot returns it, send records each command."""

    def __init__(self) -> None:
        self.state = dict(fixtures.STATE)
        self.connected = True
        self.sent: list[dict] = []
        self.snapshots = 0
        self.last_command = None

    async def snapshot(self, appliance):
        self.snapshots += 1
        return Snapshot(
            values=dict(self.state), connected=self.connected, last_command=self.last_command
        )

    async def send(self, appliance, options, command):
        self.sent.append(
            {
                "command": command.name,
                "parameters": command.parameters,
                "ancillary": command.ancillary,
                "program": command.program,
            }
        )


@pytest.fixture
def cloud():
    fake = FakeCloud()
    with patch("custom_components.hon_wine.HonClient", autospec=True) as client_cls:
        client = client_cls.return_value
        client.appliances = AsyncMock(return_value=[fixtures.APPLIANCE])
        client.commands = AsyncMock(return_value=fixtures.COMMANDS)
        client.snapshot = AsyncMock(side_effect=fake.snapshot)
        client.send = AsyncMock(side_effect=fake.send)
        client.history = AsyncMock(return_value=fixtures.HISTORY)
        fake.client = client
        yield fake


@pytest.fixture
def config_entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"email": "test@example.com", "password": "secret"},
        unique_id="test@example.com",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def entry(hass, cloud, config_entry):
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


@pytest.fixture
async def entry_after_rose(hass, cloud, config_entry):
    """Set up after a restart, the app having picked Rosé on zone 2 earlier."""
    cloud.client.history.return_value = [{"command": fixtures.ROSE_COMMAND}]
    cloud.state.update(fixtures.ROSE_STATE)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
