from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_POLL_INTERVAL, DOMAIN, EVENT_ROUTE_CHANGED
from .purelink_client import PureLinkClient

_LOGGER = logging.getLogger(__name__)


class PureLinkCoordinator(DataUpdateCoordinator[dict[int, int]]):
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: PureLinkClient,
        num_outputs: int,
    ) -> None:
        # config_entry must be passed explicitly: HA 2026.8 removed the
        # ContextVar fallback, which made entry setup fail silently on
        # 2026.8+ (entry loads, no devices/entities).
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=DEFAULT_POLL_INTERVAL),
        )
        self.client = client
        self._num_outputs = num_outputs

    async def _async_update_data(self) -> dict[int, int]:
        try:
            routing = await self.client.query_status()
        except Exception as err:
            raise UpdateFailed(f"PureLink status query failed: {err}") from err
        new = {out: routing.get(out, 0) for out in range(1, self._num_outputs + 1)}
        self._fire_route_events(new)
        return new

    def _fire_route_events(self, new: dict[int, int]) -> None:
        """Fire a bus event for each output whose input changed since last poll.

        ``self.data`` still holds the previous poll's routing while this method
        runs (the coordinator assigns the return value afterwards). It is None
        on the first refresh, so no events fire for the initial state.
        """
        previous = self.data
        if not previous:
            return
        for output, source in new.items():
            prior = previous.get(output)
            if prior is not None and prior != source:
                self.hass.bus.async_fire(
                    EVENT_ROUTE_CHANGED,
                    {
                        "entry_id": self.config_entry.entry_id,
                        "output": output,
                        "input": source,
                        "previous_input": prior,
                    },
                )

    async def async_recall_preset(self, preset: int) -> None:
        """Recall a preset, then refresh routing so entities update at once."""
        await self.client.recall_preset(preset)
        await self.async_request_refresh()
