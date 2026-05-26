# Troubleshooting

All commands below are pure stdlib Python — they work even when HA itself is broken.

## TCP sanity check

```bash
python tools/diagnose.py --host 192.0.2.10 status
```

Expected:
```
UP    192.0.2.10:3000  4.2ms  raw='*255H000!'
```

If `DOWN`:
- Confirm the IP from the device's network settings page.
- Confirm the device is powered on and on the same network.
- `nc -v 192.0.2.10 3000` to rule out a routing / firewall issue.

## Dump current routing

```bash
python tools/diagnose.py --host 192.0.2.10 dump
```

Prints the input→output map the device reports. Cross-check against the HA UI to spot drift between what HA thinks is routed and what actually is.

## End-to-end probe

```bash
python tools/diagnose.py --host 192.0.2.10 probe --input 1 --output 1
```

Sets a route, reads it back, then restores the original input. Distinguishes "device responds to heartbeat" from "device accepts routing commands" — the latter sometimes fails when the former works (firmware quirk on cold reconnect).

## Bug-report bundle

```bash
python tools/collect_diagnostics.py --config-dir /config --output purelink-bundle.zip
```

Bundles:
- `manifest.json` (verbatim)
- `environment.txt` (Python + OS)
- `config_entries.json` (purelink entries only, host last-octet masked)
- `home-assistant.log.purelink.txt` (last 500 `purelink`-tagged lines, IPs masked)

**Inspect the zip before sharing.** Redaction is best-effort. If you've embedded other identifying info in entry titles or log lines, redact it manually.

## Common failure signatures

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `cannot_connect` during setup | Wrong port or device offline | `diagnose.py status`. If down, fix network; if up, check switcher-id matches the device setting. |
| Entities show as unavailable | Coordinator update failed | Check `home-assistant.log` for `UpdateFailed`. Usually transient — should self-heal on the next poll (30s). |
| `probe` sets but doesn't verify | Device firmware drops first command after reconnect | Re-run `probe`. If persistent, open an issue with the diagnostics bundle. |
| State doesn't update after manual routing change | Polling lag | Wait up to 30s. To force an immediate refresh, toggle the entity in HA. |
| HACS won't install | Manifest version doesn't match the release tag | Bump `manifest.json::version` and retag with the matching `vX.Y.Z`. The release workflow asserts this and fails fast. |
| CI fails on "INDEX.md is out of date" | Pre-commit hook didn't run | Run `python tools/update_index.py`, commit the diff. Check that `git config core.hooksPath` is set to `.githooks`. |
