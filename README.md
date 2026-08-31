# PureLink UX-8800 — Home Assistant integration

A custom [Home Assistant](https://www.home-assistant.io/) integration for the
**PureLink UX-8800** 8×8 HDMI/HDBaseT matrix switcher. It controls routing,
recalls/saves presets, renames inputs/outputs, and exposes live signal
diagnostics — all over the device's local WebSocket control channel.

> Status: v1 (MVP). Not affiliated with or endorsed by PureLink.

## Features

- **8 outputs as `media_player` entities** — pick the source input from a
  dropdown, or turn an output off (disconnect).
- **8 outputs as `select` entities** — a plain input selector per output, if you
  prefer that to a media player card. (Both are provided; disable whichever set
  you don't want.)
- **20 preset recall buttons** — named presets are enabled by default; empty
  slots are created but disabled.
- **Diagnostics** — per-input signal-present (`binary_sensor`), input resolution
  and HDCP (`sensor`), per-output sync resolution, and the read-only master
  volume.
- **EDID** — assign any of the 27 EDID modes per input, via a config `select`
  (disabled by default) or the `set_edid` service.
- **Services** — `route`, `route_all`, `recall_preset`, `save_preset`,
  `set_input_name`, `set_output_name`, `set_edid`.

## How it works

The UX-8800 is controlled through an XML-over-WebSocket API on port **8887**
(the same channel its web UI uses). The device does **not** broadcast state
changes to other clients, so this integration **polls** for authoritative state
(`local_polling`): routing/names every few seconds, diagnostics less often.
Routing writes are verified and retried, because the controller can silently
drop a command issued immediately after connecting.

## Requirements

- Home Assistant 2024.12 or newer.
- Network reachability from HA to the matrix on TCP port 8887 (and 80 for the
  `configuration_url` link).
- The Web UI credentials (default username `admin`).

`defusedxml` and `getmac` are declared as requirements; both already ship with
Home Assistant core.

## Installation

### HACS (custom repository)

1. In HACS → Integrations → ⋮ → **Custom repositories**, add this repository as
   an **Integration**.
2. Install **PureLink UX-8800** and restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration** and search for
   *PureLink UX-8800*.

### Manual

Copy `custom_components/purelink_ux8800/` into your Home Assistant
`config/custom_components/` directory and restart.

## Configuration

Add the integration from the UI and enter the host, username and password. The
integration validates the connection before finishing.

Options (⚙ on the integration): **routing poll interval** (default 3 s) and
**diagnostics poll interval** (default 15 s).

## Services

| Service | Description |
| --- | --- |
| `purelink_ux8800.route` | Route one input to one output (input `0` disconnects). |
| `purelink_ux8800.route_all` | Route every output to one input. |
| `purelink_ux8800.recall_preset` | Recall a preset by slot number or name. |
| `purelink_ux8800.save_preset` | Save the current routing into a preset slot. |
| `purelink_ux8800.set_input_name` | Rename an input (≤ 8 characters). |
| `purelink_ux8800.set_output_name` | Rename an output (≤ 8 characters). |
| `purelink_ux8800.set_edid` | Assign an EDID mode (1-27, or its label) to an input. |

Example:

```yaml
service: purelink_ux8800.route
data:
  output: 3
  input: 1
```

## Limitations / notes

- **Master volume is read-only.** The web UI exposes no volume-set command, so
  it is surfaced as a sensor only.
- **EDID selects are optimistic.** The device does not report which EDID mode is
  active (only a free-text description, exposed as the `current_edid` attribute),
  so the EDID `select` shows the last mode set from Home Assistant. Changing EDID
  can briefly interrupt a connected source.
- Names are limited to **8 characters** by the device.
- Because the device does not push state, changes made at the front panel are
  reflected after the next poll (a few seconds).

## Development

The protocol client (`custom_components/purelink_ux8800/client.py`) is
Home-Assistant-agnostic and can be exercised on its own. See `tests/` for unit
tests (run with [`pytest-homeassistant-custom-component`](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component)).

Before publishing, update the placeholder `codeowners`, `documentation` and
`issue_tracker` fields in `manifest.json` (and the repo URLs above).

## License

[MIT](LICENSE)
