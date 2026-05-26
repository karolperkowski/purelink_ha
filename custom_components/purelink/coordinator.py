from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_POLL_INTERVAL, DOMAIN
from .purelink_client import PureLinkClient

_LOGGER = logging.getLogger(__name__)


class PureLinkCoordinator(DataUpdateCoordinator[dict[int, int]]):
    def __init__(
        self,
        hass: HomeAssistant,
        client: PureLinkClient,
        num_outputs: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_POLL_INTERVAL),
        )
        self.client = client
        self._num_outputs = num_outputs

    async def _async_update_data(self) -> dict[int, int]:
        try:
            routing = await self.client.query_status()
        except Exception as err:
            raise UpdateFailed(f"PureLink status query failed: {err}") from err
        return {out: routing.get(out, 0) for out in range(1, self._num_outputs + 1)}
