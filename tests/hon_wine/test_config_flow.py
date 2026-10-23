"""Config flow, reauthentication and diagnostics."""

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)

from custom_components.hon_wine.api import HonAuthError, HonError
from custom_components.hon_wine.const import DOMAIN

LOGIN = "custom_components.hon_wine.config_flow.HonClient.login"
CREDENTIALS = {"email": "test@example.com", "password": "secret"}


async def test_user_flow(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    with (
        patch(LOGIN, AsyncMock()),
        patch("custom_components.hon_wine.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == CREDENTIALS


async def test_user_flow_errors(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(LOGIN, AsyncMock(side_effect=HonAuthError)):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    assert result["errors"] == {"base": "invalid_auth"}
    with patch(LOGIN, AsyncMock(side_effect=HonError)):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    assert result["errors"] == {"base": "cannot_connect"}


async def test_already_configured(hass, config_entry):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(LOGIN, AsyncMock()):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_rejected_password_starts_reauth(hass, cloud, config_entry):
    cloud.client.appliances.side_effect = HonAuthError("rejected")
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_cloud_down_retries(hass, cloud, config_entry):
    cloud.client.appliances.side_effect = HonError("timeout")
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_reauth_updates_password(hass, entry):
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    with patch(LOGIN, AsyncMock()):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"password": "new"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == "new"


async def test_diagnostics_redacted(hass, hass_client, entry):
    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    text = str(diagnostics)
    for secret in (
        "secret",
        "test@example.com",
        "aa-bb-cc-dd-ee-ff",
        "0123456789abcdef",
        "00000000-1111",
        "PERSONAL",
        "1.2345",
        "SERIAL123456",
        "2001-02-03",
        "My cellar",
    ):
        assert secret not in text, secret
    cellar = diagnostics["cellars"][0]
    assert cellar["appliance"]["modelName"] == "HWS42GDAU1"
    assert cellar["programs"]["red"]["code"] == "1"
    assert cellar["history"][0]["programName"] == "PROGRAMS.WC.WHITE"
    assert cellar["history"][0]["parameters"] == {"prCodeZ2": "2", "tempSelZ2": "12"}


async def test_diagnostics_without_history(hass, hass_client, entry, cloud):
    cloud.client.history.side_effect = HonError("down")
    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    assert diagnostics["cellars"][0]["history"].startswith("unavailable")


async def test_repair_flow_dismisses_warning(hass, hass_client, entry, cloud, next_poll):
    from homeassistant.helpers import issue_registry as ir
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, "repairs", {})
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": "light.my_cellar_light"}, blocking=True
    )
    cloud.state.update({"prCodeZ2": "3", "tempSelZ2": "5"})
    await next_poll()
    issue_id = f"unexpected_change_{entry.entry_id}"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id)

    client = await hass_client()
    resp = await client.post(
        "/api/repairs/issues/fix", json={"handler": DOMAIN, "issue_id": issue_id}
    )
    flow = await resp.json()
    assert flow["step_id"] == "confirm"
    resp = await client.post(f"/api/repairs/issues/fix/{flow['flow_id']}")
    assert (await resp.json())["type"] == "create_entry"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
