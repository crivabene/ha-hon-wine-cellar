"""Zone programs, one per zone like in the hOn app."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HonWineConfigEntry
from .const import ZONES
from .coordinator import WineCellarEntity, setpoint

# Writes are serialised by the coordinator; one at a time per platform
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HonWineConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        ZoneProgram(cellar, zone)
        for cellar in entry.runtime_data
        if cellar.programs
        for zone, keys in ZONES.items()
        if keys["program"] in cellar.data
    )


class ZoneProgram(WineCellarEntity, SelectEntity):
    def __init__(self, cellar, zone: int) -> None:
        super().__init__(cellar, ZONES[zone]["program"], f"{cellar.zone_name(zone)}_program")
        self._zone = zone
        # Base programs first, then recipes, each from coldest to warmest
        self._attr_options = [
            p.key for p in sorted(cellar.programs.values(), key=lambda p: (p.recipe, p.default))
        ]

    @property
    def current_option(self) -> str | None:
        program = self.coordinator.zone_program(self._zone)
        return program.key if program else None

    async def async_select_option(self, option: str) -> None:
        # Keep the current target when the new program allows it, else the program default
        # (recipes have a single, fixed temperature)
        program = self.coordinator.programs[option]
        current = setpoint(self.coordinator.data.get(ZONES[self._zone]["target"]))
        temperature = current if current is not None and program.fits(current) else program.default
        await self.coordinator.async_set_zone(self._zone, program, temperature)
