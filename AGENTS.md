# PureLink HA Integration — Developer Notes

## Purpose

Home Assistant custom integration for the **PureLink by Dtrovision** AV matrix switcher (UX series). Enables routing of video inputs to outputs via HA `select` entities, with automatic state polling over TCP.

## Directory Layout

```
custom_components/purelink/   ← HA integration package
  manifest.json               ← integration metadata
  const.py                    ← all constants and command templates
  purelink_client.py          ← async TCP client (asyncio StreamReader/Writer)
  coordinator.py              ← DataUpdateCoordinator (polls every 30s)
  select.py                   ← SelectEntity per output port
  __init__.py                 ← async_setup_entry / async_unload_entry
  config_flow.py              ← UI config flow (host/port/switcher_id/inputs/outputs)
  strings.json                ← config flow UI strings
  translations/en.json        ← English translations (same content as strings.json)
tests/                        ← pytest suite (pytest-homeassistant-custom-component)
tools/                        ← operator-facing scripts (Python, stdlib only)
docs/                         ← CONTRIBUTING.md, TROUBLESHOOTING.md
.githooks/                    ← pre-commit hook (regenerates INDEX.md, runs lint.sh)
.github/workflows/            ← CI (lint + hassfest + HACS) and tag-driven release
```

## First-Time Setup

```bash
git config core.hooksPath .githooks
pip install -r requirements-dev.txt
```

The pre-commit hook regenerates `INDEX.md` and runs `lint.sh`. Don't skip it.

## Per-Change Workflow

```bash
./lint.sh                       # before every commit; CI runs the same script
git add path/to/file.py         # explicit paths only, never -A
git commit -m '...'             # conventional commit format (see RULES.md)
git pull --rebase origin main   # rebase, don't merge
git push origin main
gh run watch --exit-status      # CI green = done
```

## Manual Protocol Testing

Quick checks without HA running:

```bash
# Heartbeat
echo -ne "*255H000!\r\n" | nc <device_ip> 3000

# Query all connections
echo -ne "*255?C!\r\n" | nc <device_ip> 3000

# Route input 1 to output 1
echo -ne "*255CI01O01!\r\n" | nc <device_ip> 3000
```

For repeatable diagnostics, use `python tools/diagnose.py --host <ip> status|dump|probe`.

## HA Integration Conventions

- `DataUpdateCoordinator` for polling (avoids per-entity timers)
- `CoordinatorEntity` base class for select entities (auto state updates)
- `ConfigEntryNotReady` on setup failure (HA retries with back-off)
- `async_config_entry_first_refresh` for initial data fetch
- `_attr_has_entity_name = True` + `DeviceInfo` for clean entity naming
- No third-party runtime dependencies — pure stdlib `asyncio` TCP client

## Release Process

Releases are tag-driven. The release workflow asserts the tag matches `manifest.json::version`.

```bash
# 1. Bump version in custom_components/purelink/manifest.json
# 2. Commit + push
# 3. Tag and push
git tag vX.Y.Z
git push --tags
```

HACS picks up the GitHub Release artifact (`purelink.zip`) created by the workflow.

## House Rules (Summary)

See `RULES.md` for the full numbered list. The non-negotiables:

- Run `./lint.sh` before every commit; same script CI runs.
- Rebase, don't merge. Never force-push to `main`.
- Stage by explicit path; never `git add -A`.
- No third-party deps under `custom_components/purelink/`.
- Pre-commit hook regenerates `INDEX.md` — don't disable it.
