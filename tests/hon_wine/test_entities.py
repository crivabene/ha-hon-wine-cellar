"""Entities and, above all, the exact commands sent to the cloud."""

from datetime import timedelta

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from . import fixtures

APP_ANCILLARY = {"programFamily": "[dashboard]", "remoteActionable": "1", "remoteVisible": "1"}


async def test_states(hass, entry):
    assert hass.states.get("sensor.my_cellar_zone_1_temperature").state == "12.8"
    assert hass.states.get("sensor.my_cellar_zone_2_temperature").state == "11.1"
    assert hass.states.get("sensor.my_cellar_zone_1_humidity").state == "47.0"
    assert hass.states.get("sensor.my_cellar_room_temperature").state == "22.2"
    assert hass.states.get("sensor.my_cellar_error_code").state == "00"
    # 16.1 is the cloud's °F echo of 16
    assert hass.states.get("number.my_cellar_zone_1_target_temperature").state == "16"
    assert hass.states.get("number.my_cellar_zone_2_target_temperature").state == "12"
    assert hass.states.get("select.my_cellar_zone_1_program").state == "red"
    assert hass.states.get("select.my_cellar_zone_2_program").state == "white"
    assert hass.states.get("light.my_cellar_light").state == "off"


async def test_number_range_covers_all_programs(hass, entry):
    attrs = hass.states.get("number.my_cellar_zone_2_target_temperature").attributes
    assert (attrs["min"], attrs["max"], attrs["step"]) == (5, 20, 1)


async def test_target_sends_only_that_zone(hass, entry, cloud):
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.my_cellar_zone_1_target_temperature", "value": 17},
        blocking=True,
    )
    assert cloud.sent == [
        {
            "command": "startProgram",
            "parameters": {"prCode": "1", "tempSel": "17"},
            "ancillary": APP_ANCILLARY,
            "program": "PROGRAMS.WC.RED",
        }
    ]
    assert hass.states.get("number.my_cellar_zone_1_target_temperature").state == "17"


async def test_target_switches_program_by_range(hass, entry, cloud):
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.my_cellar_zone_2_target_temperature", "value": 6},
        blocking=True,
    )
    assert cloud.sent[0]["parameters"] == {"prCodeZ2": "3", "tempSelZ2": "6"}
    assert cloud.sent[0]["program"] == "PROGRAMS.WC.SPARKLING"
    assert hass.states.get("select.my_cellar_zone_2_program").state == "sparkling"


async def test_program_keeps_target_when_it_fits(hass, entry, cloud):
    cloud.state["tempSelZ2"] = "10"
    await entry.runtime_data[0].async_refresh()
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.my_cellar_zone_2_program", "option": "white"},
        blocking=True,
    )
    assert cloud.sent[0]["parameters"] == {"prCodeZ2": "2", "tempSelZ2": "10"}


async def test_program_uses_default_when_target_does_not_fit(hass, entry, cloud):
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.my_cellar_zone_2_program", "option": "red"},
        blocking=True,
    )
    assert cloud.sent[0]["parameters"] == {"prCodeZ2": "1", "tempSelZ2": "16"}
    assert cloud.sent[0]["program"] == "PROGRAMS.WC.RED"


async def test_light_sends_only_light(hass, entry, cloud):
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": "light.my_cellar_light"}, blocking=True
    )
    await hass.services.async_call(
        "light", "turn_off", {"entity_id": "light.my_cellar_light"}, blocking=True
    )
    assert cloud.sent == [
        {
            "command": "startProgram",
            "parameters": {"lightStatus": "1"},
            "ancillary": {},
            "program": None,
        },
        {
            "command": "startProgram",
            "parameters": {"lightStatus": "0"},
            "ancillary": {},
            "program": None,
        },
    ]


async def test_never_sends_settings(hass, entry, cloud):
    """`settings` resets every parameter it does not carry, i.e. both zones."""
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": "light.my_cellar_light"}, blocking=True
    )
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.my_cellar_zone_1_target_temperature", "value": 14},
        blocking=True,
    )
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.my_cellar_zone_2_program", "option": "sparkling"},
        blocking=True,
    )
    assert {call["command"] for call in cloud.sent} == {"startProgram"}


async def test_pending_value_survives_stale_cloud(hass, entry, cloud):
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.my_cellar_zone_1_target_temperature", "value": 18},
        blocking=True,
    )
    # Next poll: the cloud has not caught up yet and still reports 16.1
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()
    assert hass.states.get("number.my_cellar_zone_1_target_temperature").state == "18"


async def test_guard_notifies_when_other_zone_changes(hass, entry, cloud):
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": "light.my_cellar_light"}, blocking=True
    )
    # The cellar reset zone 2 after our light command
    cloud.state.update({"lightStatus": "1", "prCodeZ2": "3", "tempSelZ2": "5"})
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()
    issue = ir.async_get(hass).async_get_issue("hon_wine", f"unexpected_change_{entry.entry_id}")
    assert issue is not None and issue.is_fixable
    assert issue.translation_key == "unexpected_change"
    assert "tempSelZ2: 12.2 → 5" in issue.translation_placeholders["changes"]


async def test_guard_quiet_when_other_zone_unchanged(hass, entry, cloud):
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.my_cellar_zone_1_target_temperature", "value": 17},
        blocking=True,
    )
    cloud.state.update({"tempSel": "17.1"})
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()
    assert not ir.async_get(hass).issues


async def test_unavailable_when_disconnected(hass, entry, cloud):
    cloud.connected = False
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.my_cellar_zone_1_temperature").state == "unavailable"


async def test_cloud_rejection_raises(hass, entry, cloud):
    from custom_components.hon_wine.api import HonError

    cloud.client.send.side_effect = HonError("rejected")
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            "light", "turn_on", {"entity_id": "light.my_cellar_light"}, blocking=True
        )
    assert err.value.translation_key == "command_failed"


async def test_rereads_soon_after_a_write(hass, entry, cloud):
    before = cloud.snapshots
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": "light.my_cellar_light"}, blocking=True
    )
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=16))
    await hass.async_block_till_done()
    assert cloud.snapshots == before + 1


async def test_select_unknown_program_code(hass, entry, cloud):
    cloud.state["prCodeZ2"] = "9"
    await entry.runtime_data[0].async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("select.my_cellar_zone_2_program").state == "unknown"


DOWNLOAD = {"programFamily": "[download]", "remoteActionable": "1", "remoteVisible": "1"}


async def test_program_options_order(hass, entry):
    assert hass.states.get("select.my_cellar_zone_1_program").attributes["options"] == [
        "sparkling",
        "white",
        "red",
        "iot_rose",
        "iot_champagne",
        "iot_dessert",
        "iot_fortified",
        "iot_whisky",
    ]


async def test_recipe_sends_only_temperature(hass, entry, cloud):
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.my_cellar_zone_2_program", "option": "iot_rose"},
        blocking=True,
    )
    assert cloud.sent == [
        {
            "command": "startProgram",
            "parameters": {"tempSelZ2": "6"},
            "ancillary": DOWNLOAD,
            "program": "PROGRAMS.WC.IOT_ROSE",
        }
    ]
    assert hass.states.get("select.my_cellar_zone_2_program").state == "iot_rose"


async def test_recipe_still_shown_once_cellar_runs_base_program(hass, entry, cloud):
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.my_cellar_zone_2_program", "option": "iot_rose"},
        blocking=True,
    )
    # The cellar itself only knows base programs: Rosé at 6 °C runs as sparkling
    cloud.state.update(fixtures.ROSE_STATE)
    await entry.runtime_data[0].async_refresh()
    assert hass.states.get("select.my_cellar_zone_2_program").state == "iot_rose"
    assert hass.states.get("number.my_cellar_zone_2_target_temperature").state == "6"


async def test_recipe_chosen_in_app(hass, entry, cloud):
    cloud.state.update(fixtures.ROSE_STATE)
    cloud.last_command = fixtures.ROSE_COMMAND
    await entry.runtime_data[0].async_refresh()
    assert hass.states.get("select.my_cellar_zone_2_program").state == "iot_rose"
    # zone 1 is untouched
    assert hass.states.get("select.my_cellar_zone_1_program").state == "red"


async def test_base_program_chosen_in_app_replaces_recipe(hass, entry, cloud):
    cloud.state.update(fixtures.ROSE_STATE)
    cloud.last_command = fixtures.ROSE_COMMAND
    await entry.runtime_data[0].async_refresh()
    cloud.state.update({"prCodeZ2": "2", "tempSelZ2": "12.2"})
    cloud.last_command = fixtures.WHITE_COMMAND
    await entry.runtime_data[0].async_refresh()
    assert hass.states.get("select.my_cellar_zone_2_program").state == "white"


async def test_recipe_dropped_when_temperature_moves(hass, entry, cloud):
    cloud.state.update(fixtures.ROSE_STATE)
    cloud.last_command = fixtures.ROSE_COMMAND
    await entry.runtime_data[0].async_refresh()
    cloud.state.update({"tempSelZ2": "7.2"})  # changed on the cellar's own panel
    await entry.runtime_data[0].async_refresh()
    assert hass.states.get("select.my_cellar_zone_2_program").state == "sparkling"


async def test_stale_command_history_ignored(hass, entry, cloud):
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.my_cellar_zone_2_program", "option": "iot_rose"},
        blocking=True,
    )
    # The cloud has not registered our command yet and still shows the older one
    cloud.state.update(fixtures.ROSE_STATE)
    cloud.last_command = fixtures.WHITE_COMMAND
    await entry.runtime_data[0].async_refresh()
    assert hass.states.get("select.my_cellar_zone_2_program").state == "iot_rose"


async def test_target_change_leaves_recipe(hass, entry, cloud):
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.my_cellar_zone_2_program", "option": "iot_rose"},
        blocking=True,
    )
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.my_cellar_zone_2_target_temperature", "value": 7},
        blocking=True,
    )
    assert cloud.sent[-1]["parameters"] == {"prCodeZ2": "3", "tempSelZ2": "7"}
    assert cloud.sent[-1]["program"] == "PROGRAMS.WC.SPARKLING"
    assert hass.states.get("select.my_cellar_zone_2_program").state == "sparkling"


async def test_recipe_restored_from_history(hass, entry_after_rose):
    assert hass.states.get("select.my_cellar_zone_2_program").state == "iot_rose"


async def test_out_of_range_is_validation_error(hass, entry):
    cellar = entry.runtime_data[0]
    with pytest.raises(ServiceValidationError) as err:
        await cellar.async_set_zone(1, cellar.programs["white"], 17)
    assert err.value.translation_key == "out_of_range"
    assert err.value.translation_placeholders == {
        "temperature": "17",
        "program": "white",
        "low": "9",
        "high": "12",
    }


def _device(hass, entry):
    [device] = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    return device


async def test_device_named_as_in_app(hass, entry):
    device = _device(hass, entry)
    assert device.name == "My cellar"


async def test_device_name_translated_without_app_name(hass, cloud, config_entry):
    cloud.client.appliances.return_value = [
        {k: v for k, v in fixtures.APPLIANCE.items() if k != "nickName"}
    ]
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    device = _device(hass, config_entry)
    assert device.name == "Wine cellar"
    assert hass.states.get("sensor.wine_cellar_zone_1_temperature") is not None


async def test_single_zone_cellar(hass, cloud, config_entry):
    """A model without zone 2 parameters gets zone 1 entities only, and writes still work."""
    for key in ("prCodeZ2", "tempSelZ2", "tempZ2", "humidityZ2"):
        cloud.state.pop(key)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("select.my_cellar_zone_1_program").state == "red"
    assert hass.states.get("select.my_cellar_zone_2_program") is None
    assert hass.states.get("number.my_cellar_zone_2_target_temperature") is None
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.my_cellar_zone_1_target_temperature", "value": 18},
        blocking=True,
    )
    assert cloud.sent[-1]["parameters"] == {"prCode": "1", "tempSel": "18"}
