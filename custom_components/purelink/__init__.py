from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_NUM_OUTPUTS, CONF_SWITCHER_ID, DOMAIN, PLATFORMS
from .coordinator import PureLinkCoordinator
from .purelink_client import PureLinkClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    switcher_id = entry.data[CONF_SWITCHER_ID]
    num_outputs = entry.data[CONF_NUM_OUTPUTS]

    client = PureLinkClient(host, port, switcher_id)

    try:
        await client.connect()
        alive = await client.heartbeat()
    except (OSError, asyncio.TimeoutError) as err:
        raise ConfigEntryNotReady(
            f"Cannot connect to PureLink at {host}:{port}"
        ) from err

    if not alive:
        await client.disconnect()
        raise ConfigEntryNotReady(f"PureLink at {host}:{port} did not respond to heartbeat")

    coordinator = PureLinkCoordinator(hass, client, num_outputs)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["client"].disconnect()
    return unloaded
