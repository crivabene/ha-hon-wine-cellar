"""hOn client against a mocked HTTP cloud."""

import base64
import json
import time

from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest

from custom_components.hon_wine.api import (
    Command,
    HonAuthError,
    HonClient,
    HonError,
    command_body,
    token_expiry,
)
from custom_components.hon_wine.const import API_URL

from . import fixtures


def jwt(exp: float) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).rstrip(b"=").decode()
    return f"header.{payload}.signature"


def mock_login(aioclient_mock, exp: float | None = None, session: bool = True) -> None:
    exp = exp or time.time() + 3600
    aioclient_mock.get(f"{API_URL}/ciam/authorize", json={"session_id": "s1"} if session else {})
    aioclient_mock.post(
        f"{API_URL}/ciam/token", json={"tokens": {"cognito_token": jwt(exp), "id_token": jwt(exp)}}
    )


@pytest.fixture
async def client(hass, aioclient_mock):
    return HonClient(
        async_get_clientsession(hass), "user@example.com", "secret", "0123456789abcdef"
    )


def test_token_expiry():
    assert token_expiry(jwt(1234.0)) == 1234.0
    assert token_expiry("not-a-jwt") is None


def test_command_body_matches_app():
    body = command_body(
        fixtures.APPLIANCE,
        {},
        Command(
            "startProgram",
            {"prCode": "1", "tempSel": "16"},
            {"programFamily": "[dashboard]"},
            "PROGRAMS.WC.RED",
        ),
        "0123456789abcdef",
    )
    assert body["commandName"] == "startProgram"
    assert body["programName"] == "PROGRAMS.WC.RED"
    assert body["parameters"] == {"prCode": "1", "tempSel": "16"}
    assert body["ancillaryParameters"] == {"programFamily": "[dashboard]"}
    assert body["applianceType"] == "WC"
    assert body["transactionId"].startswith("aa-bb-cc-dd-ee-ff_")
    assert body["device"]["mobileId"] == "0123456789abcdef"


def test_command_body_without_program():
    body = command_body(fixtures.APPLIANCE, {}, Command("startProgram", {"lightStatus": "1"}), "x")
    assert "programName" not in body
    assert body["ancillaryParameters"] == {}


async def test_rejected_credentials(client, aioclient_mock):
    mock_login(aioclient_mock, session=False)
    with pytest.raises(HonAuthError):
        await client.login()


async def test_password_never_in_error(client, aioclient_mock):
    aioclient_mock.get(f"{API_URL}/ciam/authorize", exc=TimeoutError)
    with pytest.raises(HonError) as err:
        await client.login()
    assert "secret" not in str(err.value)


async def test_snapshot(client, aioclient_mock):
    mock_login(aioclient_mock)
    aioclient_mock.get(f"{API_URL}/commands/v1/context", json={"payload": fixtures.context()})
    snapshot = await client.snapshot(fixtures.APPLIANCE)
    assert snapshot.values == fixtures.STATE
    assert snapshot.connected


async def test_snapshot_disconnected(client, aioclient_mock):
    mock_login(aioclient_mock)
    aioclient_mock.get(
        f"{API_URL}/commands/v1/context", json={"payload": fixtures.context(connected=False)}
    )
    assert not (await client.snapshot(fixtures.APPLIANCE)).connected


async def test_logs_in_once_while_token_valid(client, aioclient_mock):
    mock_login(aioclient_mock)
    aioclient_mock.get(f"{API_URL}/commands/v1/context", json={"payload": fixtures.context()})
    await client.snapshot(fixtures.APPLIANCE)
    await client.snapshot(fixtures.APPLIANCE)
    authorize_calls = [c for c in aioclient_mock.mock_calls if "/ciam/authorize" in str(c[1])]
    assert len(authorize_calls) == 1


async def test_renews_token_before_expiry(client, aioclient_mock):
    mock_login(aioclient_mock, exp=time.time() + 30)  # inside the renewal margin
    aioclient_mock.get(f"{API_URL}/commands/v1/context", json={"payload": fixtures.context()})
    await client.snapshot(fixtures.APPLIANCE)
    await client.snapshot(fixtures.APPLIANCE)
    # one login per call: the token is already due for renewal
    authorize_calls = [c for c in aioclient_mock.mock_calls if "/ciam/authorize" in str(c[1])]
    assert len(authorize_calls) == 2


async def test_unauthorized_twice_is_auth_error(client, aioclient_mock):
    mock_login(aioclient_mock)
    aioclient_mock.get(f"{API_URL}/commands/v1/context", status=401)
    with pytest.raises(HonAuthError):
        await client.snapshot(fixtures.APPLIANCE)


async def test_server_error(client, aioclient_mock):
    mock_login(aioclient_mock)
    aioclient_mock.get(f"{API_URL}/commands/v1/context", status=500)
    with pytest.raises(HonError, match="HTTP 500"):
        await client.snapshot(fixtures.APPLIANCE)


async def test_send_refused(client, aioclient_mock):
    mock_login(aioclient_mock)
    aioclient_mock.post(f"{API_URL}/commands/v1/send", json={"payload": {"resultCode": "1"}})
    with pytest.raises(HonError, match="refused"):
        await client.send(fixtures.APPLIANCE, {}, Command("startProgram", {"lightStatus": "1"}))


async def test_send_ok(client, aioclient_mock):
    mock_login(aioclient_mock)
    aioclient_mock.post(f"{API_URL}/commands/v1/send", json={"payload": {"resultCode": "0"}})
    await client.send(fixtures.APPLIANCE, {}, Command("startProgram", {"lightStatus": "1"}))
    sent = aioclient_mock.mock_calls[-1][2]
    assert sent["parameters"] == {"lightStatus": "1"}


async def test_appliances(client, aioclient_mock):
    mock_login(aioclient_mock)
    aioclient_mock.post(
        f"{API_URL}/unified-api/v1/view/appliance-list",
        json={
            "modules": {
                "applianceList": {"payload": {"appliances": [fixtures.APPLIANCE, {"broken": 1}]}}
            }
        },
    )
    assert await client.appliances() == [fixtures.APPLIANCE]


async def test_appliances_unexpected(client, aioclient_mock):
    mock_login(aioclient_mock)
    aioclient_mock.post(f"{API_URL}/unified-api/v1/view/appliance-list", json={"error": "x"})
    with pytest.raises(HonError, match="appliance list"):
        await client.appliances()


async def test_commands(client, aioclient_mock):
    mock_login(aioclient_mock)
    aioclient_mock.get(f"{API_URL}/commands/v1/retrieve", json={"payload": fixtures.COMMANDS})
    assert (await client.commands(fixtures.APPLIANCE))["startProgram"]


async def test_commands_missing(client, aioclient_mock):
    mock_login(aioclient_mock)
    aioclient_mock.get(f"{API_URL}/commands/v1/retrieve", json={"payload": {"resultCode": "1"}})
    with pytest.raises(HonError, match="no command definitions"):
        await client.commands(fixtures.APPLIANCE)


async def test_history(client, aioclient_mock):
    mock_login(aioclient_mock)
    aioclient_mock.get(
        f"{API_URL}/commands/v1/appliance/aa-bb-cc-dd-ee-ff/history",
        json={"payload": {"history": fixtures.HISTORY}},
    )
    assert await client.history(fixtures.APPLIANCE) == fixtures.HISTORY


async def test_login_without_tokens(client, aioclient_mock):
    aioclient_mock.get(f"{API_URL}/ciam/authorize", json={"session_id": "s1"})
    aioclient_mock.post(f"{API_URL}/ciam/token", json={"error": "nope"})
    with pytest.raises(HonError, match="no tokens"):
        await client.login()


async def test_network_error_during_request(client, aioclient_mock):
    mock_login(aioclient_mock)
    aioclient_mock.get(f"{API_URL}/commands/v1/context", exc=TimeoutError)
    with pytest.raises(HonError, match="TimeoutError"):
        await client.snapshot(fixtures.APPLIANCE)
