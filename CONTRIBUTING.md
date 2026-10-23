# Contributing

Thanks for helping! The most useful contribution is **support for another wine cellar model**,
and you do not need to write code for it: a few diagnostics files are enough to get started.

## The one rule

Every command must be **exactly what the hOn app sends** for the same action, and nothing more.

Wine cellars apply the parameters they receive and reset the ones they don't. The general hOn
integrations use the `settings` command, which carries every parameter, and that is how toggling
the light ends up setting both zones to 5 °C. So this integration never guesses a command: it
copies one the app was seen sending.

## Adding a cellar model

### 1. Check what works already

Install the integration and look at what appears. Programs, codes and temperature ranges are
read from the cloud for your model, and entities are only created for the parameters your cellar
reports, so a single-zone or a similar dual-zone model may already work.

Before changing anything from Home Assistant, keep the hOn app open and check that **only the
zone you changed** changes. If anything else moves, stop and open an issue.

### 2. Record what the app sends

The cloud keeps a history of the commands each appliance received, from any source, and the
integration's diagnostics include the last 20.

For each action you want supported:

1. Do it **once, in the hOn app**, for one zone only (e.g. zone 2 → "White", or the light on).
2. Wait a minute, then download the diagnostics: *Settings → Devices & services → hOn Wine
   Cellar → ⋮ → Download diagnostics*.
3. Note what you did and when.

Useful actions: each program on each zone, a target temperature change within a program,
each recipe, light on/off, and anything your model has that others don't.

Diagnostics already remove credentials, account ids, MAC address, serial number and location.
Still, have a quick look before attaching them.

### 3. Open an issue

Use the **New cellar model** form and attach the diagnostics, with the list of actions you did.
That is often enough for someone to add the model.

### 4. Or open a pull request

- `const.py` → `ZONES`: parameter names per zone. A model with a third zone only needs another
  entry (`prCodeZ3`, `tempSelZ3`, ...).
- `coordinator.py` → `parse_programs`: how programs and recipes are read from the model's
  definitions; `async_set_zone` / `async_set_light`: the commands sent.
- `tests/hon_wine/fixtures.py`: add the responses of your model next to the existing ones,
  **anonymised** (made-up MAC, ids, serial, dates and names), plus tests asserting the exact
  commands sent.

## Development

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

Tests never talk to the real cloud. CI also runs Home Assistant's `hassfest` and the HACS
validation; all checks must pass.

Please keep:

- **English** for code, comments, logs and docs.
- **Translations** in sync: every key in `translations/en.json` must exist in `it.json`, with the
  same `{placeholders}`. New languages are welcome.
- **Load on the hOn cloud** low: no polling faster than once a minute.
- **Personal data** out of the repository: no real MAC addresses, ids, emails or locations in
  fixtures, issues or logs.

## Reporting bugs

Use the **Bug report** form, with diagnostics and, if possible, a debug log:

```yaml
logger:
  logs:
    custom_components.hon_wine: debug
```
