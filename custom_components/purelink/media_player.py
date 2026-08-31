from __future__ import annotations

import logging

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_NUM_INPUTS,
    CONF_NUM_OUTPUTS,
    CONF_SWITCHER_ID,
    DOMAIN,
)
from .coordinator import PureLinkCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: PureLinkCoordinator = data["coordinator"]
    num_inputs: int = entry.data[CONF_NUM_INPUTS]
    num_outputs: int = entry.data[CONF_NUM_OUTPUTS]
    host: str = entry.data[CONF_HOST]
    switcher_id: int = entry.data[CONF_SWITCHER_ID]

    async_add_entities(
        PureLinkOutputMediaPlayer(
            coordinator=coordinator,
            output_num=out,
            num_inputs=num_inputs,
            entry_id=entry.entry_id,
            switcher_id=switcher_id,
            host=host,
        )
        for out in range(1, num_outputs + 1)
    )


class PureLinkOutputMediaPlayer(
    CoordinatorEntity[PureLinkCoordinator], MediaPlayerEntity
):
    _attr_has_entity_name = True
    _attr_device_class = MediaPlayerDeviceClass.RECEIVER
    _attr_supported_features = (
        MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
    )

    def __init__(
        self,
        coordinator: PureLinkCoordinator,
        output_num: int,
        num_inputs: int,
        entry_id: str,
        switcher_id: int,
        host: str,
    ) -> None:
        super().__init__(coordinator)
        self._output_num = output_num
        self._last_input = 1
        self._attr_name = f"Output {output_num}"
        self._attr_unique_id = (
            f"purelink_{host}_{switcher_id}_output_{output_num}_media_player"
        )
        self._attr_source_list = [f"Input {i}" for i in range(1, num_inputs + 1)]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{host}_{switcher_id}")},
            name=f"PureLink Switcher ({host})",
            manufacturer="Dtrovision",
            model="PureLink Matrix Switcher",
        )

    def _current_input(self) -> int:
        if self.coordinator.data is None:
            return 0
        return self.coordinator.data.get(self._output_num, 0)

    @property
    def state(self) -> MediaPlayerState | None:
        if self.coordinator.data is None:
            return None
        if self._current_input():
            return MediaPlayerState.ON
        return MediaPlayerState.OFF

    @property
    def source(self) -> str | None:
        inp = self._current_input()
        if inp == 0:
            return None
        return f"Input {inp}"

    async def async_select_source(self, source: str) -> None:
        inp = int(source.split()[-1])
        self._last_input = inp
        await self.coordinator.client.connect_input_to_output(inp, self._output_num)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        inp = self._current_input()
        if inp:
            self._last_input = inp
        await self.coordinator.client.disconnect_output(self._output_num)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        await self.coordinator.client.connect_input_to_output(
            self._last_input, self._output_num
        )
        await self.coordinator.async_request_refresh()
