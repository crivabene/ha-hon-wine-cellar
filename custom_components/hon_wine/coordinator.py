"""Wine cellar coordinator and base entity.

Every write mimics the hOn app exactly: `startProgram` carrying only the parameters of
what changes (one zone's program + target, or the light). Never `settings`: that
command resets every parameter it does not carry, i.e. both zones.

The cellar works in whole °F internally: a 16 °C target comes back as 61 °F = 16.1 °C.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import logging
import time

from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import Command, HonAuthError, HonClient, HonError
from .const import DOMAIN, ZONES

_LOGGER = logging.getLogger(__name__)

POLL_INTERVAL = timedelta(seconds=60)
# Re-read this soon after a write, instead of waiting for the next poll
CONFIRM_DELAY = 15  # seconds
# How long a value we sent wins over cloud state that has not caught up yet
PENDING_TTL = 120  # seconds
# How long after a write the zones it must not touch are watched
GUARD_TTL = 300  # seconds


def to_float(value: str | None) -> float | None:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def setpoint(value: str | None) -> int | None:
    """Target in whole °C: undoes the °F round trip (16 -> 61 °F -> 16.1)."""
    number = to_float(value)
    return None if number is None else round(number)


def same(a: str | None, b: str | None) -> bool:
    """Values match, allowing for the °F round trip (at most 0.28 °C)."""
    fa, fb = to_float(a), to_float(b)
    if fa is None or fb is None:
        return a == b
    return abs(fa - fb) < 0.5


@dataclass(frozen=True)
class Program:
    """A zone program as the app offers it.

    Base programs (red, white, sparkling) carry a code and a target range. Recipes
    (iot_rose, iot_whisky, ...) only fix a temperature: the cellar then runs the base
    program whose range holds it, so the cellar alone cannot tell a recipe apart.
    """

    key: str  # "red", "iot_rose"
    name: str  # "PROGRAMS.WC.RED", as sent in programName
    code: str | None  # value of prCode / prCodeZ2; None for recipes
    low: int
    high: int
    default: int
    ancillary: dict[str, str] = field(default_factory=dict, compare=False)

    @property
    def recipe(self) -> bool:
        return self.code is None

    def fits(self, temperature: int) -> bool:
        return self.low <= temperature <= self.high


def _whole(value: str) -> int:
    return round(float(value))


def parse_programs(commands: dict) -> dict[str, Program]:
    """Base programs and recipes, from the model's startProgram definitions."""
    programs = {}
    for name, spec in commands.get("startProgram", {}).items():
        if not isinstance(spec, dict):
            continue
        params = spec.get("parameters", {})
        code, target = params.get("prCode", {}), params.get("tempSel", {})
        ancillary = {
            key: value
            for key, definition in spec.get("ancillaryParameters", {}).items()
            if (value := definition.get("fixedValue", definition.get("defaultValue"))) is not None
        }
        key = name.rsplit(".", 1)[-1].lower()
        if code.get("typology") == "fixed" and target.get("typology") == "range":
            low, high = _whole(target["minimumValue"]), _whole(target["maximumValue"])
            default, program_code = _whole(target["defaultValue"]), code["fixedValue"]
        elif "prCode" not in params and target.get("typology") == "fixed":
            low = high = default = _whole(target["fixedValue"])
            program_code = None
        else:
            continue
        programs[key] = Program(key, name, program_code, low, high, default, ancillary)
    return programs


def zone_of(parameters: dict) -> int | None:
    """Which zone a command targets, from the parameters it carries."""
    return next((zone for zone, keys in ZONES.items() if keys["target"] in parameters), None)


class WineCellarCoordinator(DataUpdateCoordinator[dict[str, str]]):
    """Polls one cellar and sends app-identical commands."""

    def __init__(self, hass, entry, client: HonClient, appliance: dict, commands: dict) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"hOn {appliance.get('modelName', 'wine cellar')}",
            update_interval=POLL_INTERVAL,
        )
        self.client = client
        self.appliance = appliance
        self.commands = commands
        self.connected = True
        self.programs = parse_programs(commands)
        if not self.programs:
            _LOGGER.warning(
                "No zone programs for %s: zones are read-only", appliance.get("modelName")
            )
        self._options = commands.get("applianceModel", {}).get("options", {})
        self._write_lock = asyncio.Lock()
        # key -> (value we sent, monotonic deadline)
        self._pending: dict[str, tuple[str, float]] = {}
        # values that must not change, and until when to check
        self._guard: dict[str, str] = {}
        self._guard_until = 0.0
        self._cancel_confirm = None
        # Recipe last chosen per zone, and the newest command already accounted for
        self._recipes: dict[int, str] = {}
        self._seen_command = ""
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, appliance["macAddress"])},
            # The name given in the hOn app, else a translated "Wine cellar"
            name=appliance.get("nickName"),
            translation_key=None if appliance.get("nickName") else "cellar",
            manufacturer=str(appliance.get("brand", "Haier")).title(),
            model=appliance.get("modelName"),
            serial_number=appliance.get("serialNumber"),
            sw_version=appliance.get("fwVersion"),
        )

    async def _async_update_data(self) -> dict[str, str]:
        try:
            snapshot = await self.client.snapshot(self.appliance)
        except HonAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except HonError as err:
            raise UpdateFailed(str(err)) from err
        self.connected = snapshot.connected
        if snapshot.last_command:
            self._track_command(snapshot.last_command)
        values = self._overlay_pending(snapshot.values)
        self._check_guard(values)
        return values

    async def async_load_recipes(self) -> None:
        """Replay the command history, so a recipe chosen before a restart is still shown."""
        try:
            history = await self.client.history(self.appliance)
        except HonError as err:
            _LOGGER.debug("No command history: %s", err)
            return
        for entry in reversed(history):
            self._track_command(entry.get("command", entry))

    def _track_command(self, command: dict) -> None:
        """Remember per zone whether the newest program command was a recipe."""
        stamp = str(command.get("timestamp", ""))
        if stamp and stamp <= self._seen_command:
            return
        self._seen_command = stamp or self._seen_command
        zone = zone_of(command.get("parameters") or {})
        if zone is None:
            return
        program = self.programs.get(str(command.get("programName", "")).rsplit(".", 1)[-1].lower())
        if program and program.recipe:
            self._recipes[zone] = program.key
        else:
            self._recipes.pop(zone, None)

    def _overlay_pending(self, values: dict[str, str]) -> dict[str, str]:
        """Values we just sent win until the cloud reflects them or they expire."""
        now = time.monotonic()
        self._pending = {
            key: (sent, deadline)
            for key, (sent, deadline) in self._pending.items()
            if deadline > now and not same(values.get(key), sent)
        }
        return values | {key: sent for key, (sent, _) in self._pending.items()}

    def _check_guard(self, values: dict[str, str]) -> None:
        """Warn loudly if a write changed something it was not meant to touch."""
        if not self._guard:
            return
        changed = {
            k: (v, values.get(k)) for k, v in self._guard.items() if not same(values.get(k), v)
        }
        if changed:
            summary = ", ".join(f"{k}: {old} → {new}" for k, (old, new) in changed.items())
            _LOGGER.error("Unexpected change after a write: %s", summary)
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self.guard_issue_id,
                is_fixable=True,
                severity=ir.IssueSeverity.WARNING,
                translation_key="unexpected_change",
                translation_placeholders={"changes": summary},
            )
            self._guard = {}
        elif time.monotonic() > self._guard_until:
            self._guard = {}

    @property
    def guard_issue_id(self) -> str:
        return f"unexpected_change_{self.config_entry.entry_id}"

    async def _write(self, command: Command, untouched: list[str]) -> None:
        """Send one command; `untouched` keys are watched to catch side effects."""
        async with self._write_lock:
            try:
                await self.client.send(self.appliance, self._options, command)
            except HonAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except HonError as err:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="command_failed",
                    translation_placeholders={"error": str(err)},
                ) from err
            now = time.monotonic()
            self._pending |= {
                key: (value, now + PENDING_TTL) for key, value in command.parameters.items()
            }
            self._guard = {k: self.data[k] for k in untouched if self.data.get(k) not in (None, "")}
            self._guard_until = now + GUARD_TTL
            self.async_set_updated_data(self.data | command.parameters)
            if self._cancel_confirm:
                self._cancel_confirm()
            self._cancel_confirm = async_call_later(self.hass, CONFIRM_DELAY, self._confirm)

    async def _confirm(self, _now) -> None:
        self._cancel_confirm = None
        await self.async_request_refresh()

    async def async_shutdown(self) -> None:
        if self._cancel_confirm:
            self._cancel_confirm()
            self._cancel_confirm = None
        await super().async_shutdown()

    def program_for(self, temperature: int, preferred: str | None = None) -> Program | None:
        """The base program whose range holds this target, keeping the current one if it fits."""
        fits = [p for p in self.programs.values() if not p.recipe and p.fits(temperature)]
        return next((p for p in fits if p.key == preferred), fits[0] if fits else None)

    def zone_program(self, zone: int) -> Program | None:
        """The recipe last chosen while its temperature still holds, else the base program."""
        recipe = self.programs.get(self._recipes.get(zone, ""))
        if recipe and setpoint(self.data.get(ZONES[zone]["target"])) == recipe.default:
            return recipe
        code = self.data.get(ZONES[zone]["program"])
        return next(
            (p for p in self.programs.values() if p.code is not None and p.code == code), None
        )

    async def async_set_zone(self, zone: int, program: Program, temperature: int) -> None:
        if not program.fits(temperature):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="out_of_range",
                translation_placeholders={
                    "temperature": str(temperature),
                    "program": program.key,
                    "low": str(program.low),
                    "high": str(program.high),
                },
            )
        keys = ZONES[zone]
        others = [k for z, ks in ZONES.items() if z != zone for k in (ks["program"], ks["target"])]
        # Recipes carry no program code: the app sends only the temperature
        parameters = {keys["target"]: str(temperature)}
        if program.code is not None:
            parameters = {keys["program"]: program.code} | parameters
        command = Command("startProgram", parameters, program.ancillary, program.name)
        await self._write(command, untouched=others)
        self._track_command(
            {
                "programName": program.name,
                "parameters": parameters,
                "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            }
        )
        self.async_update_listeners()

    async def async_set_light(self, on: bool) -> None:
        await self._write(
            Command("startProgram", {"lightStatus": "1" if on else "0"}),
            untouched=[k for zone in ZONES.values() for k in (zone["program"], zone["target"])],
        )


class WineCellarEntity(CoordinatorEntity[WineCellarCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: WineCellarCoordinator, key: str, translation_key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{coordinator.appliance['macAddress']}_{key}"
        self._attr_device_info = coordinator.device_info

    @property
    def raw(self) -> str | None:
        return self.coordinator.data.get(self._key)

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.connected
