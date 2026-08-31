from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_NUM_OUTPUTS, CONF_SWITCHER_ID, DOMAIN, PLATFORMS
from .coordinator import PureLinkCoordinator
from .purelink_client import PureLinkClient
from .purelink_names import PureLinkNamesError, async_fetch_names

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    switcher_id = entry.data[CONF_SWITCHER_ID]
    num_outputs = entry.data[CONF_NUM_OUTPUTS]

    client = PureLinkClient(host, port, switcher_id)

    try:
        await client.connect()
        alive = await client.is_alive()
    except (OSError, asyncio.TimeoutError) as err:
        raise ConfigEntryNotReady(
            f"Cannot connect to PureLink at {host}:{port}"
        ) from err

    if not alive:
        await client.disconnect()
        raise ConfigEntryNotReady(
            f"PureLink at {host}:{port} did not respond to status query"
        )

    coordinator = PureLinkCoordinator(hass, entry, client, num_outputs)
    await coordinator.async_config_entry_first_refresh()

    sw_version: str | None = None
    try:
        sw_version = await client.query_version()
    except (OSError, asyncio.TimeoutError, EOFError, asyncio.LimitOverrunError):
        _LOGGER.debug("Firmware version query failed; continuing without it")

    # Port names only exist behind the web UI websocket; fetch them once per
    # setup when credentials were provided, and fall back to generic labels
    # on any failure — names are cosmetic, routing must keep working.
    input_names: dict[int, str] = {}
    output_names: dict[int, str] = {}
    username = entry.data.get(CONF_USERNAME) or ""
    password = entry.data.get(CONF_PASSWORD) or ""
    if username and password:
        try:
            input_names, output_names = await async_fetch_names(
                async_get_clientsession(hass), host, username, password
            )
        except PureLinkNamesError as err:
            _LOGGER.warning(
                "Could not fetch port names from the web UI (%s); "
                "using generic names",
                err,
            )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
        "input_names": input_names,
        "output_names": output_names,
        "sw_version": sw_version,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["client"].disconnect()
    return unloaded
