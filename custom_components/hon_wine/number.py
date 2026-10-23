"""Zone targets: the program follows from the range the target falls in."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HonWineConfigEntry
from .const import DOMAIN, ZONES
from .coordinator import WineCellarEntity, setpoint

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HonWineConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        ZoneTarget(cellar, zone)
        for cellar in entry.runtime_data
        if cellar.programs
        for zone, keys in ZONES.items()
        if keys["target"] in cellar.data
    )


class ZoneTarget(WineCellarEntity, NumberEntity):
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX
    _attr_native_step = 1

    def __init__(self, cellar, zone: int) -> None:
        super().__init__(cellar, ZONES[zone]["target"], f"{cellar.zone_name(zone)}_target")
        self._zone = zone
        self._attr_native_min_value = min(p.low for p in cellar.programs.values())
        self._attr_native_max_value = max(p.high for p in cellar.programs.values())

    @property
    def native_value(self) -> int | None:
        return setpoint(self.raw)

    async def async_set_native_value(self, value: float) -> None:
        temperature = round(value)
        current = self.coordinator.zone_program(self._zone)
        program = self.coordinator.program_for(temperature, current.key if current else None)
        if program is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_program",
                translation_placeholders={"temperature": str(temperature)},
            )
        await self.coordinator.async_set_zone(self._zone, program, temperature)
