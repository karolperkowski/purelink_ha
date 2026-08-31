"""The PureLink UX-8800 matrix switcher integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import PureLinkClient
from .const import PLATFORMS
from .coordinator import PureLinkConfigEntry, UX8800Coordinator
from .services import async_setup_services


async def async_setup_entry(hass: HomeAssistant, entry: PureLinkConfigEntry) -> bool:
    """Set up PureLink UX-8800 from a config entry."""
    session = async_get_clientsession(hass)
    client = PureLinkClient(
        session,
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    coordinator = UX8800Coordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_update))
    async_setup_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PureLinkConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.client.async_disconnect()
    return unload_ok


async def _async_reload_on_update(
    hass: HomeAssistant, entry: PureLinkConfigEntry
) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
