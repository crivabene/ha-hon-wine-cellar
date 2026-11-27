"""Whether the cellar is online in the hOn cloud."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HonWineConfigEntry
from .coordinator import WineCellarEntity

# Read-only, fed by the coordinator
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HonWineConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(CellarConnectivity(cellar) for cellar in entry.runtime_data)


class CellarConnectivity(WineCellarEntity, BinarySensorEntity):
    """On while the cellar is connected; named and translated by Home Assistant ("Connectivity")."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _requires_connection = False

    def __init__(self, cellar) -> None:
        super().__init__(cellar, "connectivity", None)

    @property
    def is_on(self) -> bool:
        return self.coordinator.connected
