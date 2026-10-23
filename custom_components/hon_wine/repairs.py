"""Repairs: the warning raised when a write changed something it should not have."""

from __future__ import annotations

from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.core import HomeAssistant


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict | None
) -> RepairsFlow:
    # Nothing to repair automatically: the user checks the cellar in the hOn app and confirms
    return ConfirmRepairFlow()
