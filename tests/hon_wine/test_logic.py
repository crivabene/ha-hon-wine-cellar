"""Pure helpers: program parsing, loose comparison, program choice."""

import pytest

from custom_components.hon_wine.coordinator import Program, parse_programs, same, setpoint, to_float

from . import fixtures


def test_parse_base_programs():
    programs = parse_programs(fixtures.COMMANDS)
    assert programs["sparkling"] == Program("sparkling", "PROGRAMS.WC.SPARKLING", "3", 5, 8, 8)
    assert programs["white"] == Program("white", "PROGRAMS.WC.WHITE", "2", 9, 12, 12)
    assert programs["red"] == Program("red", "PROGRAMS.WC.RED", "1", 13, 20, 16)
    assert programs["red"].ancillary == {
        "programFamily": "[dashboard]",
        "remoteActionable": "1",
        "remoteVisible": "1",
    }


def test_parse_recipes():
    programs = parse_programs(fixtures.COMMANDS)
    rose = programs["iot_rose"]
    assert rose.recipe and rose.code is None
    assert (rose.low, rose.high, rose.default) == (6, 6, 6)
    assert rose.ancillary["programFamily"] == "[download]"
    assert {k for k, p in programs.items() if p.recipe} == {
        "iot_rose",
        "iot_whisky",
        "iot_fortified",
        "iot_dessert",
        "iot_champagne",
    }


def test_parse_programs_without_definitions():
    assert parse_programs({}) == {}


def test_same_tolerates_cloud_echo():
    # The cloud echoes a target of 16 as 16.1
    assert same("16.1", "16")
    assert not same("16.1", "17")
    assert same("00", "00")
    assert not same(None, "1")


def test_to_float():
    assert to_float("12,5") == 12.5
    assert to_float("") is None
    assert to_float(None) is None


@pytest.mark.parametrize("celsius", range(5, 21))
def test_setpoint_undoes_fahrenheit_round_trip(celsius):
    """The cellar stores whole °F; the cloud converts back with one decimal."""
    echoed = f"{(round(celsius * 9 / 5 + 32) - 32) * 5 / 9:.1f}"
    assert setpoint(echoed) == celsius
    assert same(echoed, str(celsius))


def test_setpoint_observed_values():
    # Seen on a real HWS42GDAU1: 16 -> 16.1, 12 -> 12.2, 10 -> 10.0
    assert [setpoint(v) for v in ("16.1", "12.2", "10.0", None)] == [16, 12, 10, None]


def test_program_fits():
    red = Program("red", "PROGRAMS.WC.RED", "1", 13, 20, 16)
    assert red.fits(13) and red.fits(20)
    assert not red.fits(12)
