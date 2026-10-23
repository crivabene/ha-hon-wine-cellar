"""hOn cloud responses for an HWS42GDAU1, anonymised: identifiers, dates and names are made up."""

APPLIANCE = {
    "macAddress": "aa-bb-cc-dd-ee-ff",
    "applianceTypeName": "WC",
    "applianceTypeId": 6,
    "applianceModelId": 127,
    "modelName": "HWS42GDAU1",
    "brand": "haier",
    "code": "TESTCODE000",
    "eepromId": 41,
    "fwVersion": "5.30.0",
    "series": "series50",
    "nickName": "My cellar",
    # Personal data the real appliance list carries: must never reach diagnostics
    "PK": "user#eu-west-1:00000000-1111-2222-3333-444444444444",
    "sfPersonAccountId": "0016800000PERSONAL",
    "coords": {"lat": 1.2345, "lng": 6.7891},
    "purchaseDate": "2001-02-03T00:00:00.0Z",
    "serialNumber": "SERIAL123456",
    "topics": {"subscribe": ["haier/things/aa-bb-cc-dd-ee-ff/event/appliancestatus/update"]},
}


def _fixed(value: str) -> dict:
    return {"category": "command", "typology": "fixed", "mandatory": 0, "fixedValue": value}


def _range(default: str, low: str, high: str) -> dict:
    return {
        "category": "command",
        "typology": "range",
        "mandatory": 0,
        "defaultValue": default,
        "minimumValue": low,
        "maximumValue": high,
        "incrementValue": "1",
    }


_ANCILLARY = {
    "programFamily": {
        "category": "cluster",
        "typology": "enum",
        "mandatory": 1,
        "enumValues": ["dashboard"],
        "defaultValue": "[dashboard]",
    },
    "remoteActionable": {
        "category": "general",
        "typology": "fixed",
        "mandatory": 0,
        "fixedValue": "1",
    },
    "remoteVisible": {
        "category": "general",
        "typology": "fixed",
        "mandatory": 0,
        "fixedValue": "1",
    },
}


def _program(code: str, default: str, low: str, high: str) -> dict:
    return {
        "description": "The command allows to start a program",
        "protocolType": "MQTT",
        "parameters": {
            "prCode": _fixed(code),
            "prCodeZ2": _fixed(code),
            "tempSel": _range(default, low, high),
            "tempSelZ2": _range(default, low, high),
        },
        "ancillaryParameters": _ANCILLARY,
    }


def _recipe(temperature: str) -> dict:
    """IoT recipes: fixed temperature, no program code, family "download"."""
    return {
        "parameters": {"tempSel": _fixed(temperature), "tempSelZ2": _fixed(temperature)},
        "ancillaryParameters": _ANCILLARY
        | {
            "programFamily": {
                "category": "cluster",
                "typology": "enum",
                "mandatory": 1,
                "enumValues": ["download"],
                "defaultValue": "[download]",
            },
        },
    }


COMMANDS = {
    "resultCode": "0",
    "applianceModel": {"options": {}},
    "settings": {
        "parameters": {
            "lightStatus": _range("0", "0", "1"),
            "sabbathStatus": _range("0", "0", "1"),
            "tempSel": _range("5", "5", "20"),
            "tempSelZ2": _range("5", "5", "20"),
            "tempUnit": _range("0", "0", "1"),
        }
    },
    "startProgram": {
        "PROGRAMS.WC.SPARKLING": _program("3", "8", "5", "8"),
        "PROGRAMS.WC.WHITE": _program("2", "12", "9", "12"),
        "PROGRAMS.WC.RED": _program("1", "16", "13", "20"),
        "PROGRAMS.WC.IOT_WHISKY": _recipe("17"),
        "PROGRAMS.WC.IOT_ROSE": _recipe("6"),
        "PROGRAMS.WC.IOT_FORTIFIED": _recipe("15"),
        "PROGRAMS.WC.IOT_DESSERT": _recipe("8"),
        "PROGRAMS.WC.IOT_CHAMPAGNE": _recipe("6"),
    },
}

STATE = {
    "errors": "00",
    "humidityZ1": "47",
    "humidityZ2": "69",
    "lightStatus": "0",
    "onOffStatus": "1",
    "prCode": "1",
    "prCodeZ2": "2",
    "sabbathStatus": "0",
    "temp": "12.8",
    "tempEnv": "22.2",
    "tempSel": "16.1",
    "tempSelZ2": "12.2",
    "tempUnit": "0",
    "tempZ2": "11.1",
}


def context(state: dict | None = None, connected: bool = True) -> dict:
    """Raw /commands/v1/context payload."""
    return {
        "resultCode": "0",
        "shadow": {"parameters": {k: {"parNewVal": v} for k, v in (state or STATE).items()}},
        "lastConnEvent": {"category": "CONNECTED" if connected else "DISCONNECTED"},
    }


# /commands/v1/appliance/<mac>/history, the app changing zone 2 then the light
HISTORY = [
    {
        "PK": "user#eu-west-1:00000000-1111-2222-3333-444444444444",
        "command": {
            "commandName": "startProgram",
            "programName": "PROGRAMS.WC.WHITE",
            "parameters": {"prCodeZ2": "2", "tempSelZ2": "12"},
            "macAddress": "aa-bb-cc-dd-ee-ff",
            "device": {"mobileId": "0123456789abcdef"},
        },
    },
    {
        "command": {
            "commandName": "startProgram",
            "parameters": {"lightStatus": "0"},
            "macAddress": "aa-bb-cc-dd-ee-ff",
            "device": {"mobileId": "0123456789abcdef"},
        }
    },
]


# What the app sent for "Rosé" on zone 2, and how the cellar then reported the zone
ROSE_COMMAND = {
    "commandName": "startProgram",
    "programName": "PROGRAMS.WC.IOT_ROSE",
    "parameters": {"tempSelZ2": "6"},
    "ancillaryParameters": {
        "programFamily": "[download]",
        "remoteActionable": "1",
        "remoteVisible": "1",
    },
    "timestamp": "2001-01-01T10:00:00.000Z",
}
ROSE_STATE = {"prCodeZ2": "3", "tempSelZ2": "6.1"}
WHITE_COMMAND = {
    "commandName": "startProgram",
    "programName": "PROGRAMS.WC.WHITE",
    "parameters": {"prCodeZ2": "2", "tempSelZ2": "12"},
    "ancillaryParameters": {
        "programFamily": "[dashboard]",
        "remoteActionable": "1",
        "remoteVisible": "1",
    },
    "timestamp": "2001-01-01T10:00:30.000Z",
}
