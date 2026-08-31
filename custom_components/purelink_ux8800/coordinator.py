"""DataUpdateCoordinator for the PureLink UX-8800.

The device does not push state to other clients, so this is a *polling*
coordinator: every ``poll_interval`` it pulls an authoritative ``requestall_main``
snapshot (routing + names) and, less often, the ``info`` diagnostics.  Control
commands go through the wrapper methods here, which update entities immediately.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import (
    CannotConnect,
    InvalidAuth,
    MatrixState,
    PureLinkClient,
    PureLinkError,
)
from .const import (
    CONF_INFO_INTERVAL,
    CONF_POLL_INTERVAL,
    DEFAULT_INFO_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

type PureLinkConfigEntry = ConfigEntry[UX8800Coordinator]


class UX8800Coordinator(DataUpdateCoordinator[MatrixState]):
    """Coordinate polling and commands for one UX-8800."""

    config_entry: PureLinkConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: PureLinkConfigEntry,
        client: PureLinkClient,
    ) -> None:
        """Initialise the coordinator."""
        poll = int(entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=poll),
        )
        self.client = client
        info = int(entry.options.get(CONF_INFO_INTERVAL, DEFAULT_INFO_INTERVAL))
        self._info_every = max(1, round(info / max(1, poll)))
        self._tick = 0

    async def _async_update_data(self) -> MatrixState:
        """Fetch an authoritative snapshot from the device."""
        try:
            await self.client.async_ensure_connected()
            await self.client.async_request_all()
            if self._tick % self._info_every == 0:
                await self.client.async_refresh_info()
                await self.client.async_refresh_volume()
            self._tick += 1
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (CannotConnect, PureLinkError) as err:
            raise UpdateFailed(str(err)) from err
        return self.client.state

    # -- command wrappers (update entities immediately after each write) ------

    async def async_route(self, output: int, source: int) -> None:
        """Route an output and push the new state to entities."""
        await self.client.async_route(output, source)
        self.async_set_updated_data(self.client.state)

    async def async_route_all(self, source: int) -> None:
        """Route every output to one source."""
        await self.client.async_route_all(source)
        self.async_set_updated_data(self.client.state)

    async def async_recall_preset(self, slot: int) -> None:
        """Recall a preset by slot."""
        await self.client.async_recall_preset(slot)
        self.async_set_updated_data(self.client.state)

    async def async_save_preset(
        self, slot: int, name: str, routing: Mapping[int, int] | None = None
    ) -> None:
        """Save the current (or provided) routing into a preset slot."""
        await self.client.async_save_preset(slot, name, routing)
        self.async_set_updated_data(self.client.state)

    async def async_set_name(self, kind: str, index: int, name: str) -> None:
        """Rename an input or output on the device."""
        await self.client.async_set_name(kind, index, name)
        self.async_set_updated_data(self.client.state)

    async def async_set_edid(self, input_index: int, mode: int) -> None:
        """Assign an EDID mode to an input."""
        await self.client.async_set_edid(input_index, mode)
        self.async_set_updated_data(self.client.state)
