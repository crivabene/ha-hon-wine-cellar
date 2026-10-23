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

ZONE_SENSORS = (
    ("temp", "temperature", TEMPERATURE),
    ("humidity", "humidity", HUMIDITY),
)
SENSORS = (
    CellarSensorDescription(key="tempEnv", translation_key="room_temperature", **TEMPERATURE),
    CellarSensorDescription(
        key="errors",
        translation_key="error",
        entity_category=EntityCategory.DIAGNOSTIC,
        numeric=False,
    ),
)


def _descriptions(cellar) -> list[CellarSensorDescription]:
    zone_sensors = [
        CellarSensorDescription(
            key=ZONES[zone][field], translation_key=f"{cellar.zone_name(zone)}_{name}", **kind
        )
        for field, name, kind in ZONE_SENSORS
        for zone in ZONES
    ]
    return [d for d in (*zone_sensors, *SENSORS) if d.key in cellar.data]


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
        for description in _descriptions(cellar)
    )


class CellarSensor(WineCellarEntity, SensorEntity):
    entity_description: CellarSensorDescription

    def __init__(self, cellar, description: CellarSensorDescription) -> None:
        super().__init__(cellar, description.key, description.translation_key)
        self.entity_description = description

    @property
    def native_value(self) -> float | str | None:
        return to_float(self.raw) if self.entity_description.numeric else self.raw
