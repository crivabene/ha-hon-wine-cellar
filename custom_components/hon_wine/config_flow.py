"""Config flow: the hOn app account; asks again for the password when it stops working."""

from __future__ import annotations

from collections.abc import Mapping
import secrets
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

from .api import HonAuthError, HonClient, HonError
from .const import DOMAIN

CREDENTIALS = vol.Schema({vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): str})
PASSWORD = vol.Schema({vol.Required(CONF_PASSWORD): str})


class HonWineConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _login_error(self, email: str, password: str) -> str | None:
        client = HonClient(
            async_get_clientsession(self.hass), email, password, secrets.token_hex(8)
        )
        try:
            await client.login()
        except HonAuthError:
            return "invalid_auth"
        except HonError:
            return "cannot_connect"
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        error = None
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_EMAIL].lower())
            self._abort_if_unique_id_configured()
            error = await self._login_error(user_input[CONF_EMAIL], user_input[CONF_PASSWORD])
            if error is None:
                return self.async_create_entry(title=user_input[CONF_EMAIL], data=user_input)
        return self.async_show_form(
            step_id="user", data_schema=CREDENTIALS, errors={"base": error} if error else {}
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        error = None
        if user_input is not None:
            error = await self._login_error(entry.data[CONF_EMAIL], user_input[CONF_PASSWORD])
            if error is None:
                return self.async_update_reload_and_abort(entry, data_updates=user_input)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=PASSWORD,
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors={"base": error} if error else {},
        )
