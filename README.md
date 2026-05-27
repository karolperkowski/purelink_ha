# PureLink — Home Assistant Integration

A Home Assistant custom integration for **PureLink** AV matrix switchers (UX series). Control video routing from your Home Assistant dashboard.

## Features

- Route any input to any output via a drop-down selector
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
| TCP Port | Device port (see Network Settings in device web UI) | `3000` |
| Switcher ID | Device switcher ID (see device settings) | `255` |
| Number of Inputs | How many input ports your switcher has | — |
| Number of Outputs | How many output ports your switcher has | — |

## Entities

One `select` entity is created per output port. For a 4×4 switcher:

| Entity | Options |
|---|---|
| `select.purelink_output_1` | Disconnected, Input 1, Input 2, Input 3, Input 4 |
| `select.purelink_output_2` | Disconnected, Input 1, Input 2, Input 3, Input 4 |
| … | … |

Selecting an input routes the signal. Selecting **Disconnected** severs the connection.

## Troubleshooting

**"Cannot connect" during setup**
- Verify the device IP and port with `nc <ip> <port>` (or telnet)
- Check the device is powered on and LAN connected
- Confirm the Switcher ID matches the device setting (default 255)

**Entities show as unavailable**
- HA lost the TCP connection; it will reconnect automatically on the next poll
- Check network connectivity between HA and the switcher

**State doesn't update after manual routing change**
- State polls every 30 seconds; wait up to 30s for HA to reflect external changes
