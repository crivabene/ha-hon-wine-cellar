## What this changes

<!-- e.g. support for model XYZ, with the commands recorded from the hOn app -->

## Checklist

- [ ] Every command sent is one the hOn app was seen sending for the same action (never `settings`)
- [ ] Tests assert the exact commands sent; fixtures are anonymised
- [ ] `pytest`, `ruff check` and `ruff format --check` pass
- [ ] User-facing strings are translatable, with `en.json` and `it.json` in sync
