"""Media player platform: one entity per matrix output (routing control)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import INPUT_NONE, MATRIX_SIZE
from .coordinator import PureLinkConfigEntry, UX8800Coordinator
from .entity import PureLinkEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PureLinkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one media_player per output."""
    coordinator = entry.runtime_data
    async_add_entities(
        PureLinkOutputMediaPlayer(coordinator, out)
        for out in range(1, MATRIX_SIZE + 1)
    )


class PureLinkOutputMediaPlayer(PureLinkEntity, MediaPlayerEntity):
    """An output modelled as a media_player whose 'source' is the routed input."""

    _attr_device_class = MediaPlayerDeviceClass.RECEIVER
    _attr_supported_features = (
        MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator: UX8800Coordinator, output: int) -> None:
        """Initialise for a specific output."""
        super().__init__(coordinator)
        self._output = output
        self._attr_unique_id = f"{self._base_unique_id}_output_{output}_media_player"
        self._last_source = 1

    @property
    def name(self) -> str:
        """Friendly output name (e.g. 'TV1')."""
        return self._state.output_name(self._output)

    @property
    def state(self) -> MediaPlayerState:
        """ON when routed to an input, OFF when disconnected (input 0)."""
        src = self._state.routing.get(self._output, INPUT_NONE)
        return MediaPlayerState.ON if src else MediaPlayerState.OFF

    @property
    def source_list(self) -> list[str]:
        """Available input labels."""
        return [label for _, label in self._state.source_options()]

    @property
    def source(self) -> str | None:
        """Currently routed input label, or None when disconnected."""
        src = self._state.routing.get(self._output, INPUT_NONE)
        return self._state.label_for_input(src) if src else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose raw routing numbers and sink resolution for automations."""
        src = self._state.routing.get(self._output, INPUT_NONE)
        return {
            "output_number": self._output,
            "input_number": src,
            "sink_resolution": self._state.output_sync.get(self._output),
        }

    async def async_select_source(self, source: str) -> None:
        """Route the selected input to this output."""
        index = self._state.input_for_label(source)
        if index is None:
            raise ServiceValidationError(f"Unknown source: {source}")
        self._last_source = index
        await self.coordinator.async_route(self._output, index)

    async def async_turn_off(self) -> None:
        """Disconnect this output (route to input 0)."""
        current = self._state.routing.get(self._output, INPUT_NONE)
        if current:
            self._last_source = current
        await self.coordinator.async_route(self._output, INPUT_NONE)

    async def async_turn_on(self) -> None:
        """Reconnect this output to its last-used input."""
        await self.coordinator.async_route(self._output, self._last_source or 1)
