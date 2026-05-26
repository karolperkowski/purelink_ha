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
```

## Development Workflow

Install HA in a local venv, symlink `custom_components/purelink` into your HA config dir, then restart HA. No build step required.

## Manual Protocol Testing

```bash
# Test heartbeat
echo -ne "*255H000!\r\n" | nc <device_ip> 3000

# Query all connections
echo -ne "*255?C!\r\n" | nc <device_ip> 3000

# Route input 1 to output 1
echo -ne "*255CI01O01!\r\n" | nc <device_ip> 3000
```

## HA Integration Conventions Used

- `DataUpdateCoordinator` for polling (avoids per-entity timers)
- `CoordinatorEntity` base class for select entities (auto state updates)
- `ConfigEntryNotReady` on setup failure (HA retries with back-off)
- `async_config_entry_first_refresh` for initial data fetch
- `_attr_has_entity_name = True` + `DeviceInfo` for clean entity naming
- No third-party dependencies — pure stdlib `asyncio` TCP client
