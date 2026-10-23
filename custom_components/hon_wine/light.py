"""Interior light, switched with the same one-parameter command as the app."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HonWineConfigEntry
from .coordinator import WineCellarEntity

# Writes are serialised by the coordinator; one at a time per platform
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HonWineConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        CellarLight(cellar, "lightStatus", "light")
        for cellar in entry.runtime_data
        if "lightStatus" in cellar.data
    )


class CellarLight(WineCellarEntity, LightEntity):
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    @property
    def is_on(self) -> bool | None:
        return None if self.raw is None else self.raw == "1"

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_light(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_light(False)
