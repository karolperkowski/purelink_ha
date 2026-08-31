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
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_NUM_INPUTS,
    CONF_NUM_OUTPUTS,
    CONF_SWITCHER_ID,
    DISCONNECTED_LABEL,
    DOMAIN,
    INPUT_LABEL_TEMPLATE,
    OUTPUT_LABEL_TEMPLATE,
)
from .coordinator import PureLinkCoordinator
from .purelink_names import build_labels

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

    if num_outputs < 1 or num_inputs < 1:
        # select.py logs the actionable warning for this misconfiguration;
        # skip quietly here to avoid a duplicate log line.
        return

    # Reserve DISCONNECTED_LABEL here too so both platforms agree on labels.
    input_labels = build_labels(
        data["input_names"],
        num_inputs,
        INPUT_LABEL_TEMPLATE,
        reserved=frozenset({DISCONNECTED_LABEL}),
    )
    output_labels = build_labels(
        data["output_names"], num_outputs, OUTPUT_LABEL_TEMPLATE
    )

    async_add_entities(
        PureLinkOutputMediaPlayer(
            coordinator=coordinator,
            output_num=out,
            output_label=output_labels[out],
            input_labels=input_labels,
            entry_id=entry.entry_id,
            switcher_id=switcher_id,
            host=host,
            sw_version=data["sw_version"],
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
        output_label: str,
        input_labels: dict[int, str],
        entry_id: str,
        switcher_id: int,
        host: str,
        sw_version: str | None,
    ) -> None:
        super().__init__(coordinator)
        self._output_num = output_num
        self._last_input = 1
        self._input_labels = input_labels
        self._label_to_input = {label: num for num, label in input_labels.items()}
        self._attr_name = output_label
        self._attr_unique_id = (
            f"purelink_{host}_{switcher_id}_output_{output_num}_media_player"
        )
        self._attr_source_list = [input_labels[i] for i in sorted(input_labels)]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{host}_{switcher_id}")},
            name=f"PureLink Switcher ({host})",
            manufacturer="Dtrovision",
            model="PureLink Matrix Switcher",
            sw_version=sw_version,
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
        return self._input_labels.get(inp, INPUT_LABEL_TEMPLATE.format(n=inp))

    async def async_select_source(self, source: str) -> None:
        # Unlike select, core does not validate select_source against the
        # source list, so scripts can pass stale names (e.g. "Input 3" written
        # before name sync); surface a clean error instead of a KeyError.
        inp = self._label_to_input.get(source)
        if inp is None:
            raise ServiceValidationError(
                f"Unknown source {source!r}; valid sources: "
                f"{', '.join(self._attr_source_list or [])}"
            )
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
