"""hOn cloud client, limited to what a wine cellar needs.

Endpoints and the CIAM/PKCE login are the ones the hOn mobile app uses.
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import json
import logging
import secrets
import time
from typing import Any

import aiohttp

from .const import API_URL, APP_VERSION, DEVICE_MODEL, OS, OS_VERSION, USER_AGENT

_LOGGER = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=30)
# Renew this long before the tokens expire
TOKEN_MARGIN = 120  # seconds
# Used when a token carries no readable expiry
TOKEN_FALLBACK_TTL = 600  # seconds


class HonError(Exception):
    """The hOn cloud could not be reached or answered something unexpected."""


class HonAuthError(HonError):
    """The hOn cloud rejected the credentials: retrying will not help."""


@dataclass(frozen=True)
class Command:
    """One command as the hOn app sends it."""

    name: str
    parameters: dict[str, str]
    ancillary: dict[str, str] = field(default_factory=dict)
    program: str | None = None


@dataclass(frozen=True)
class Snapshot:
    """Current values reported by the appliance, all as strings."""

    values: dict[str, str]
    connected: bool
    # Last command the appliance received, from any source (app, HA, ...)
    last_command: dict | None = None


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def token_expiry(token: str) -> float | None:
    """`exp` claim of a JWT (epoch seconds), read without verifying the signature."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload))["exp"])
    except (IndexError, KeyError, TypeError, ValueError):
        return None


def command_body(
    appliance: dict, options: dict, command: Command, mobile_id: str
) -> dict[str, Any]:
    """Request body of /commands/v1/send, field for field what the app posts."""
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    body: dict[str, Any] = {
        "macAddress": appliance["macAddress"],
        "timestamp": now,
        "commandName": command.name,
        "transactionId": f"{appliance['macAddress']}_{now}",
        "applianceOptions": options,
        "device": {
            "mobileId": mobile_id,
            "mobileOs": OS,
            "osVersion": OS_VERSION,
            "appVersion": APP_VERSION,
            "deviceModel": DEVICE_MODEL,
        },
        "attributes": {"channel": "mobileApp", "origin": "standardProgram", "energyLabel": "0"},
        "ancillaryParameters": command.ancillary,
        "parameters": command.parameters,
        "applianceType": appliance["applianceTypeName"],
    }
    if command.program:
        body["programName"] = command.program
    return body


class HonClient:
    def __init__(
        self, session: aiohttp.ClientSession, email: str, password: str, mobile_id: str
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._mobile_id = mobile_id
        self._tokens: dict[str, str] = {}
        self._expires = 0.0
        self._login_lock = asyncio.Lock()

    async def login(self) -> None:
        verifier = _b64url(secrets.token_bytes(64))
        challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
        headers = {"User-Agent": USER_AGENT}
        try:
            # The app sends the password in the query string: never let the URL reach a log
            async with self._session.get(
                f"{API_URL}/ciam/authorize",
                params={
                    "username": self._email,
                    "password": self._password,
                    "code_challenge": challenge,
                },
                headers=headers,
                timeout=TIMEOUT,
            ) as resp:
                authorized = await resp.json(content_type=None) if resp.status == 200 else None
            session_id = authorized.get("session_id") if isinstance(authorized, dict) else None
            if not session_id:
                raise HonAuthError("hOn rejected the email or password")

            async with self._session.post(
                f"{API_URL}/ciam/token",
                json={"session_id": session_id, "code_verifier": verifier},
                headers=headers,
                timeout=TIMEOUT,
            ) as resp:
                issued = await resp.json(content_type=None)
        except (TimeoutError, aiohttp.ClientError) as err:
            raise HonError(f"hOn login failed ({type(err).__name__})") from None

        tokens = issued.get("tokens") if isinstance(issued, dict) else None
        if not isinstance(tokens, dict) or not {"cognito_token", "id_token"} <= tokens.keys():
            raise HonError("hOn login returned no tokens")
        self._tokens = {"cognito-token": tokens["cognito_token"], "id-token": tokens["id_token"]}
        expiries = [e for e in map(token_expiry, self._tokens.values()) if e]
        self._expires = min(expiries) if expiries else time.time() + TOKEN_FALLBACK_TTL

    async def _ensure_token(self, force: bool = False) -> None:
        async with self._login_lock:
            if force or time.time() > self._expires - TOKEN_MARGIN:
                await self.login()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Authenticated call; on 401/403 log in again and retry once."""
        for retry in (False, True):
            await self._ensure_token(force=retry)
            try:
                async with self._session.request(
                    method,
                    f"{API_URL}{path}",
                    headers={
                        "User-Agent": USER_AGENT,
                        "Content-Type": "application/json",
                        **self._tokens,
                    },
                    timeout=TIMEOUT,
                    **kwargs,
                ) as resp:
                    if resp.status in (401, 403):
                        if not retry:
                            continue
                        raise HonAuthError(f"{path}: still unauthorized after a fresh login")
                    if resp.status >= 400:
                        raise HonError(f"{path}: HTTP {resp.status}")
                    return await resp.json(content_type=None)
            except (TimeoutError, aiohttp.ClientError) as err:
                raise HonError(f"{path}: {type(err).__name__}") from None
        raise AssertionError("unreachable")

    async def appliances(self) -> list[dict]:
        data = await self._request(
            "POST", "/unified-api/v1/view/appliance-list", json={"deviceId": "homeassistant"}
        )
        try:
            appliances = data["modules"]["applianceList"]["payload"]["appliances"]
        except (KeyError, TypeError):
            raise HonError("unexpected appliance list") from None
        return [a for a in appliances if "macAddress" in a and "applianceTypeName" in a]

    async def commands(self, appliance: dict) -> dict:
        """Command definitions for this model: programs with their codes and ranges."""
        payload = (
            await self._request(
                "GET",
                "/commands/v1/retrieve",
                params={
                    "applianceType": appliance["applianceTypeId"],
                    "code": appliance["code"],
                    "applianceModelId": appliance["applianceModelId"],
                    "firmwareId": appliance["eepromId"],
                    "macAddress": appliance["macAddress"],
                    "fwVersion": appliance["fwVersion"],
                    "os": OS,
                    "appVersion": APP_VERSION,
                    "series": appliance.get("series", ""),
                },
            )
        ).get("payload", {})
        if payload.get("resultCode") != "0":
            raise HonError(f"no command definitions (resultCode {payload.get('resultCode')})")
        return payload

    async def snapshot(self, appliance: dict) -> Snapshot:
        payload = (
            await self._request(
                "GET",
                "/commands/v1/context",
                params={
                    "macAddress": appliance["macAddress"],
                    "applianceType": appliance["applianceTypeName"],
                    "category": "CYCLE",
                },
            )
        ).get("payload", {})
        parameters = payload.get("shadow", {}).get("parameters", {})
        return Snapshot(
            values={
                key: str(value.get("parNewVal"))
                for key, value in parameters.items()
                if value.get("parNewVal") is not None
            },
            connected=payload.get("lastConnEvent", {}).get("category") != "DISCONNECTED",
            last_command=(payload.get("commandHistory") or {}).get("command"),
        )

    async def history(self, appliance: dict) -> list[dict]:
        """Last commands received by the appliance, from any source (app, HA, ...)."""
        data = await self._request(
            "GET", f"/commands/v1/appliance/{appliance['macAddress']}/history"
        )
        return (data.get("payload") or {}).get("history", []) if isinstance(data, dict) else []

    async def send(self, appliance: dict, options: dict, command: Command) -> None:
        body = command_body(appliance, options, command, self._mobile_id)
        # The body carries the MAC and mobile id: log only what the command does
        _LOGGER.debug("Sending %s %s %s", command.name, command.program or "", command.parameters)
        result = await self._request("POST", "/commands/v1/send", json=body)
        code = (result.get("payload") or {}).get("resultCode") if isinstance(result, dict) else None
        if code != "0":
            raise HonError(f"command refused (resultCode {code})")
