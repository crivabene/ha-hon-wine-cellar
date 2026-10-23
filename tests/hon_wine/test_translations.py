"""Every translation has the same keys and {placeholders} as en.json."""

import json
from pathlib import Path
import re

import pytest

TRANSLATIONS = Path(__file__).parents[2] / "custom_components" / "hon_wine" / "translations"


def _flat(node: dict, prefix: str = "") -> dict[str, str]:
    flat = {}
    for key, value in node.items():
        path = f"{prefix}.{key}" if prefix else key
        flat |= _flat(value, path) if isinstance(value, dict) else {path: value}
    return flat


ENGLISH = _flat(json.loads((TRANSLATIONS / "en.json").read_text(encoding="utf-8")))
LANGUAGES = sorted(p.stem for p in TRANSLATIONS.glob("*.json") if p.stem != "en")


def test_languages_present():
    assert {"it", "de", "fr", "es", "pt", "nl", "pl"} <= set(LANGUAGES)


@pytest.mark.parametrize("language", LANGUAGES)
def test_same_keys_and_placeholders(language):
    translated = _flat(json.loads((TRANSLATIONS / f"{language}.json").read_text(encoding="utf-8")))
    assert translated.keys() == ENGLISH.keys()
    for key, text in ENGLISH.items():
        assert set(re.findall(r"\{(\w+)\}", translated[key])) == set(
            re.findall(r"\{(\w+)\}", text)
        ), key
        assert translated[key].strip(), key


@pytest.mark.parametrize(
    ("language", "device_name"),
    [
        ("de", "Weinkühlschrank"),
        ("fr", "Cave à vin"),
        ("es", "Vinoteca"),
        ("pt", "Garrafeira"),
        ("nl", "Wijnklimaatkast"),
        ("pl", "Chłodziarka do wina"),
    ],
)
async def test_home_assistant_uses_translation(hass, cloud, config_entry, language, device_name):
    from homeassistant.helpers import device_registry as dr

    from . import fixtures

    hass.config.language = language
    cloud.client.appliances.return_value = [
        {k: v for k, v in fixtures.APPLIANCE.items() if k != "nickName"}
    ]
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    [device] = dr.async_entries_for_config_entry(dr.async_get(hass), config_entry.entry_id)
    assert device.name == device_name
