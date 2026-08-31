# PureLink — Home Assistant Integration

A Home Assistant custom integration for **PureLink** AV matrix switchers (UX series). Control video routing from your Home Assistant dashboard.

## Features

- Route any input to any output via a drop-down selector or media player card
- `media_player` entity per output (source picker + on/off = connect/disconnect)
- Automatic state polling every 30 seconds
- Instant state update after routing changes
- Connection error handling with automatic reconnect
- Supports all UX-series matrix switchers (UX-4400, UX-8800, etc.)

## Supported Devices

Any PureLink / Dtrovision matrix switcher with a LAN port that accepts the ASCII TCP command protocol, including:

- UX-4400 (4×4)
- UX-8800 (8×8)
- Other UX series models

## Installation

### Manual

1. Download this repository
2. Copy the `custom_components/purelink` folder into your HA configuration directory:
   ```
   <ha_config>/custom_components/purelink/
   ```
3. Restart Home Assistant

### HACS (Manual Repository)

1. In HACS → Integrations → ⋮ → Custom repositories
2. Add this repository URL with category **Integration**
3. Install **PureLink**
4. Restart Home Assistant

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **PureLink**
3. Fill in the form:

| Field | Description | Default |
|---|---|---|
| IP Address / Hostname | Device LAN IP or hostname | — |
| TCP Port | Device port (telnet; check Network Settings in device web UI if non-standard) | `23` |
| Switcher ID | Device switcher ID (see device settings) | `255` |
| Web UI Username / Password | Optional. When provided, entities are named after the input/output names configured on the switcher (e.g. `TV1`, `CABLE`) instead of `Output 1` / `Input 1`. | empty |

4. Confirm the matrix size. The number of outputs is detected automatically
   from the switcher's status reply (UX matrices are square, so inputs default
   to the same count); adjust only if your model differs.

Device-side names are read once per (re)start of the integration — after
renaming ports in the switcher's web UI, reload the integration to pick the
new names up. Without credentials, entities use generic names that you can
rename in Home Assistant.

## Entities

Two entities are created per output port — use whichever fits your dashboard:

| Entity | Behaviour |
|---|---|
| `media_player.purelink_..._output_n` | Source picker routes an input; **off** disconnects the output, **on** restores the last input. |
| `select.purelink_..._output_n` | Options: Disconnected, Input 1 … Input N. Selecting an input routes the signal; **Disconnected** severs the connection. |

## Troubleshooting

**"Cannot connect" during setup**
- Verify the device IP and port with `nc <ip> <port>` (or telnet)
- Check the device is powered on and LAN connected
- Confirm the Switcher ID matches the device setting (default 255)
- Setup probes the device with the `*<id>?C!` status query (some models,
  e.g. the UX-8800, reject the H000 heartbeat while answering `?C` normally)

**Entities show as unavailable**
- HA lost the TCP connection; it will reconnect automatically on the next poll
- Check network connectivity between HA and the switcher

**State doesn't update after manual routing change**
- State polls every 30 seconds; wait up to 30s for HA to reflect external changes
