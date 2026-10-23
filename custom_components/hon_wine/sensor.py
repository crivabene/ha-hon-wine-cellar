"""Zone temperatures and humidity, room temperature, error code."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HonWineConfigEntry
from .const import ZONES
from .coordinator import WineCellarEntity, to_float


@dataclass(frozen=True, kw_only=True)
class CellarSensorDescription(SensorEntityDescription):
    numeric: bool = True


TEMPERATURE = dict(
    device_class=SensorDeviceClass.TEMPERATURE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    # The sensor resolves 1 °F: a single decimal is all the precision there is
    suggested_display_precision=1,
)
HUMIDITY = dict(
    device_class=SensorDeviceClass.HUMIDITY,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=PERCENTAGE,
    suggested_display_precision=0,
)

SENSORS = (
    *(
        CellarSensorDescription(
            key=keys["temp"], translation_key=f"zone_{zone}_temperature", **TEMPERATURE
        )
        for zone, keys in ZONES.items()
    ),
    *(
        CellarSensorDescription(
            key=keys["humidity"], translation_key=f"zone_{zone}_humidity", **HUMIDITY
        )
        for zone, keys in ZONES.items()
    ),
    CellarSensorDescription(key="tempEnv", translation_key="room_temperature", **TEMPERATURE),
    CellarSensorDescription(
        key="errors",
        translation_key="error",
        entity_category=EntityCategory.DIAGNOSTIC,
        numeric=False,
    ),
)


# Read-only, fed by the coordinator
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HonWineConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        CellarSensor(cellar, description)
        for cellar in entry.runtime_data
        for description in SENSORS
        if description.key in cellar.data
    )


class CellarSensor(WineCellarEntity, SensorEntity):
    entity_description: CellarSensorDescription

    def __init__(self, cellar, description: CellarSensorDescription) -> None:
        super().__init__(cellar, description.key, description.translation_key)
        self.entity_description = description

    @property
    def native_value(self) -> float | str | None:
        return to_float(self.raw) if self.entity_description.numeric else self.raw
