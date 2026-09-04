"""DataUpdateCoordinator for the PureLink UX-8800.

The device does not push state to other clients, so this is a *polling*
coordinator: every ``poll_interval`` it pulls an authoritative ``requestall_main``
snapshot (routing + names) and, less often, the ``info`` diagnostics.  Control
commands go through the wrapper methods here, which update entities immediately.

Because the poll is the only way changes made at the front panel or the device's
web UI become visible, the coordinator also diffs each routing snapshot against
the previous one and fires a ``purelink_ux8800_route_changed`` event on the HA
event bus for every externally-changed output.  Changes made *through* Home
Assistant are excluded: the command wrappers resync the diff baseline (and hold
an in-flight marker so a concurrent poll doesn't misattribute them).
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator, Mapping
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import (
    CannotConnect,
    InvalidAuth,
    MatrixState,
    PureLinkClient,
    PureLinkError,
)
from .const import (
    ATTR_INPUT,
    ATTR_INPUT_NAME,
    ATTR_OUTPUT,
    ATTR_OUTPUT_NAME,
    ATTR_PREVIOUS_INPUT,
    ATTR_PREVIOUS_INPUT_NAME,
    CONF_INFO_INTERVAL,
    CONF_POLL_INTERVAL,
    DEFAULT_INFO_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    EVENT_ROUTE_CHANGED,
    INPUT_NONE,
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
        # Diff baseline for external-change events, and a counter of HA-initiated
        # commands in flight (their changes must not be reported as external).
        self._known_routing: dict[int, int] | None = None
        self._ha_commands = 0
        self._device_id: str | None = None

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
        self._fire_external_route_events()
        return self.client.state

    # -- external change events -----------------------------------------------

    def _fire_external_route_events(self) -> None:
        """Diff the fresh snapshot and fire events for non-HA routing changes.

        Runs synchronously (no awaits) right after the poll, so the snapshot,
        the baseline swap, and the in-flight check are atomic on the event loop.
        """
        state = self.client.state
        new_routing = dict(state.routing)
        known, self._known_routing = self._known_routing, new_routing
        if known is None or self._ha_commands:
            # First snapshot, or an HA command is mid-flight (its wrapper will
            # resync the baseline when it finishes) — nothing to attribute to
            # the front panel / web UI.
            return
        for output, source in new_routing.items():
            previous = known.get(output)
            if previous is None or previous == source:
                continue
            self.hass.bus.async_fire(
                EVENT_ROUTE_CHANGED,
                {
                    "device_id": self._get_device_id(),
                    "entry_id": self.config_entry.entry_id,
                    ATTR_OUTPUT: output,
                    ATTR_OUTPUT_NAME: state.output_name(output),
                    ATTR_INPUT: source,
                    ATTR_INPUT_NAME: (
                        state.input_name(source) if source != INPUT_NONE else None
                    ),
                    ATTR_PREVIOUS_INPUT: previous,
                    ATTR_PREVIOUS_INPUT_NAME: (
                        state.input_name(previous) if previous != INPUT_NONE else None
                    ),
                },
            )

    def _get_device_id(self) -> str | None:
        """Return (and cache) the device registry id for the matrix."""
        if self._device_id is None:
            entry = self.config_entry
            device = dr.async_get(self.hass).async_get_device(
                identifiers={(DOMAIN, entry.unique_id or entry.entry_id)}
            )
            self._device_id = device.id if device else None
        return self._device_id

    @contextlib.asynccontextmanager
    async def _ha_command(self) -> AsyncIterator[None]:
        """Mark a routing-affecting HA command so its changes stay event-free."""
        self._ha_commands += 1
        try:
            yield
        finally:
            self._known_routing = dict(self.client.state.routing)
            self._ha_commands -= 1

    # -- command wrappers (update entities immediately after each write) ------

    async def async_route(self, output: int, source: int) -> None:
        """Route an output and push the new state to entities."""
        async with self._ha_command():
            await self.client.async_route(output, source)
        self.async_set_updated_data(self.client.state)

    async def async_route_all(self, source: int) -> None:
        """Route every output to one source."""
        async with self._ha_command():
            await self.client.async_route_all(source)
        self.async_set_updated_data(self.client.state)

    async def async_recall_preset(self, slot: int) -> None:
        """Recall a preset by slot."""
        async with self._ha_command():
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
