# hOn Wine Cellar

Home Assistant integration for **Haier wine cellars** connected to the hOn app
(appliance type `WC`), tested with an HWS42GDAU1 dual-zone cellar.

It sends exactly the commands the hOn app sends, so changing one zone never touches the other.

> [!IMPORTANT]
> **Unofficial.** This project is not affiliated with, endorsed or supported by Haier, Haier Europe
> or hOn. It talks to the hOn cloud the way the hOn app does; that interface is not public, may
> change without notice, and using it may not be covered by the hOn terms of use. Use it at your
> own risk, with your own hOn account.
>
> To keep the load on the hOn cloud low it polls once a minute (the interval agreed with Haier
> for the original hOn integration in 2024) and re-reads once shortly after each command.
> If Haier asks for this repository to be changed or removed, it will be.

## Why another hOn integration

The general hOn integrations change the light or a temperature with the `settings` command,
which carries every parameter. The cellar applies what it receives and resets the rest, so
toggling the light could set both zones to 5 °C
([Andre0512/hon#238](https://github.com/Andre0512/hon/issues/238)).

This integration only uses what the app uses, as read from the cloud's own command history:

| Action | Command |
|---|---|
| Light | `startProgram {lightStatus}` |
| Zone 1 program | `startProgram PROGRAMS.WC.<PROGRAM> {prCode, tempSel}`, family `[dashboard]` |
| Zone 2 program | `startProgram PROGRAMS.WC.<PROGRAM> {prCodeZ2, tempSelZ2}`, family `[dashboard]` |
| Recipe | `startProgram PROGRAMS.WC.IOT_<RECIPE> {tempSel or tempSelZ2}`, family `[download]` |

After every write, the parameters it must not touch are watched for five minutes; an unexpected
change raises a repair issue.

## Entities

Per cellar:

- **Zone 1/2 program** (select): red 13–20 °C, white 9–12 °C, sparkling 5–8 °C, plus the app's
  recipes (rosé 6, champagne 6, dessert 8, fortified 15, whisky 17 °C)
- **Zone 1/2 target temperature** (number, 5–20 °C): the program follows from the range
- **Zone 1/2 temperature** and **humidity**, **room temperature**, **error code** (sensors)
- **Light**

Programs, codes and ranges are read from the cloud's definitions for the model, not hard-coded.

### Dashboard example

A card with both zones, their program and target, the light, an error warning and the last two
days. In a dashboard: **Edit → Add card → Manual**, then paste:

```yaml
type: vertical-stack
cards:
  - type: heading
    heading: Wine cellar
    icon: mdi:bottle-wine
  - type: grid
    columns: 2
    square: false
    cards:
      - type: tile
        entity: sensor.wine_cellar_zone_1_temperature
        name: Zone 1
        color: red
      - type: tile
        entity: sensor.wine_cellar_zone_2_temperature
        name: Zone 2
        color: amber
      - type: tile
        entity: select.wine_cellar_zone_1_program
        name: Program
        features:
          - type: select-options
      - type: tile
        entity: select.wine_cellar_zone_2_program
        name: Program
        features:
          - type: select-options
      - type: tile
        entity: number.wine_cellar_zone_1_target_temperature
        name: Target
        features:
          - type: numeric-input
            style: buttons
      - type: tile
        entity: number.wine_cellar_zone_2_target_temperature
        name: Target
        features:
          - type: numeric-input
            style: buttons
      - type: tile
        entity: sensor.wine_cellar_zone_1_humidity
        name: Humidity
        color: blue
      - type: tile
        entity: sensor.wine_cellar_zone_2_humidity
        name: Humidity
        color: blue
  - type: tile
    entity: light.wine_cellar_light
    name: Light
    features:
      - type: toggle
  - type: conditional
    conditions:
      - condition: state
        entity: sensor.wine_cellar_error_code
        state_not: "00"
    card:
      type: markdown
      content: >-
        ⚠️ **The wine cellar reports an error** (code
        `{{ states('sensor.wine_cellar_error_code') }}`).
  - type: history-graph
    title: Last 48 hours
    hours_to_show: 48
    entities:
      - entity: sensor.wine_cellar_zone_1_temperature
        name: Zone 1
      - entity: sensor.wine_cellar_zone_2_temperature
        name: Zone 2
      - entity: sensor.wine_cellar_room_temperature
        name: Room
```

Entity IDs follow the device name and the language Home Assistant had when the integration was
set up. The example uses the English ones; if yours differ, find them under
**Settings → Devices & services → hOn Wine Cellar → device**, or pick them in the card editor.

| English | Italian |
|---|---|
| `sensor.wine_cellar_zone_1_temperature` | `sensor.cantinetta_temperatura_zona_1` |
| `sensor.wine_cellar_zone_1_humidity` | `sensor.cantinetta_umidita_zona_1` |
| `select.wine_cellar_zone_1_program` | `select.cantinetta_programma_zona_1` |
| `number.wine_cellar_zone_1_target_temperature` | `number.cantinetta_temperatura_impostata_zona_1` |
| `sensor.wine_cellar_room_temperature` | `sensor.cantinetta_temperatura_ambiente` |
| `sensor.wine_cellar_error_code` | `sensor.cantinetta_codice_errore` |
| `light.wine_cellar_light` | `light.cantinetta_luce` |

Zone 2 entities are the same with `2` in place of `1`.

### Things worth knowing

- The cellar works in **whole °F** internally: a 16 °C target is stored as 61 °F and reported back
  as 16.1 °C. Targets are therefore shown rounded to whole degrees; measured temperatures have a
  real resolution of 1 °F (about 0.56 °C).
- Recipes exist only in the app: they set a temperature and the cellar runs the base program whose
  range holds it (rosé → sparkling at 6 °C). The integration remembers the last recipe per zone from
  the cloud's command history, for as long as the target stays at the recipe's temperature.
- Cloud polling every 60 s, plus a re-read 15 s after each command.

## Installation

Requires Home Assistant 2026.10 or later and an hOn app account with the cellar already set up
in the app.

### HACS (recommended)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=crivabene&repository=ha-hon-wine-cellar&category=integration)

Or by hand: HACS → ⋮ → **Custom repositories** → add
`https://github.com/crivabene/ha-hon-wine-cellar`, type **Integration**.

Then download **hOn Wine Cellar** in HACS and restart Home Assistant. HACS will offer updates
when a new release comes out.

### Manual

1. Download `hon_wine.zip` from the
   [latest release](https://github.com/crivabene/ha-hon-wine-cellar/releases/latest).
2. Extract it into `config/custom_components/hon_wine/` (create the folders if needed), so that
   `config/custom_components/hon_wine/manifest.json` exists.
3. Restart Home Assistant.

From the Terminal & SSH add-on, the same in one go:

```sh
mkdir -p /config/custom_components/hon_wine && cd /config/custom_components/hon_wine && \
  wget -q https://github.com/crivabene/ha-hon-wine-cellar/releases/latest/download/hon_wine.zip && \
  unzip -o hon_wine.zip && rm hon_wine.zip
```

To update, repeat the steps with the new release.

### Set up

[![Open your Home Assistant instance and start setting up hOn Wine Cellar.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=hon_wine)

Or: Settings → Devices & services → **Add integration** → **hOn Wine Cellar**, then sign in with
the email and password of your hOn app account.

Do not run it alongside another hOn integration for the same cellar: their `settings` commands
would still reset the zones.

## Languages

English and Italian.

## Troubleshooting

Settings → Devices & services → hOn Wine Cellar → ⋮ → **Download diagnostics** gives the model's
command definitions, the current state and the last commands the cellar received. Account ids,
MAC address, serial number, location and credentials are removed. Attach it to an issue to help
support another model.

Debug logging:

```yaml
logger:
  logs:
    custom_components.hon_wine: debug
```

## Development

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

CI also runs Home Assistant's `hassfest` and the HACS validation.

The cloud is replaced by responses captured from a real cellar (anonymised) in
`tests/hon_wine/fixtures.py`.

## Contributing

Support for other hOn wine cellars is very welcome, and usually needs only a few diagnostics files
recorded while using the hOn app: see [CONTRIBUTING.md](CONTRIBUTING.md).

## Credits

The hOn endpoints and the CIAM/PKCE login are those of the hOn mobile app, as documented by
[pyhOn](https://github.com/Andre0512/pyhOn) and
[DerTakku/hOn-Wine-HACS](https://github.com/DerTakku/hOn-Wine-HACS), which this integration
started from.

Haier and hOn are trademarks of their respective owners, used here only to describe the
appliances this integration works with.

## License

MIT, see [LICENSE](LICENSE) and [NOTICE](NOTICE).
