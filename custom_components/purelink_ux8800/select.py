"""Select platform: one dropdown per output (an alternative to media_player)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import INPUT_NONE, MATRIX_SIZE
from .coordinator import PureLinkConfigEntry, UX8800Coordinator
from .entity import PureLinkEntity

OFF_LABEL = "Off"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PureLinkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one routing select per output."""
    coordinator = entry.runtime_data
    async_add_entities(
        PureLinkOutputSelect(coordinator, out) for out in range(1, MATRIX_SIZE + 1)
    )


class PureLinkOutputSelect(PureLinkEntity, SelectEntity):
    """An output modelled as a plain source-selector dropdown."""

    _attr_icon = "mdi:swap-horizontal"

    def __init__(self, coordinator: UX8800Coordinator, output: int) -> None:
        """Initialise for a specific output."""
        super().__init__(coordinator)
        self._output = output
        self._attr_unique_id = f"{self._base_unique_id}_output_{output}_select"

    @property
    def name(self) -> str:
        """Name like 'TV1 source'."""
        return f"{self._state.output_name(self._output)} source"

    @property
    def options(self) -> list[str]:
        """Off plus all input labels."""
        return [OFF_LABEL, *[label for _, label in self._state.source_options()]]

    @property
    def current_option(self) -> str | None:
        """Currently routed input label, or 'Off'."""
        src = self._state.routing.get(self._output, INPUT_NONE)
        if not src:
            return OFF_LABEL
        return self._state.label_for_input(src)

    async def async_select_option(self, option: str) -> None:
        """Route the chosen input (or disconnect on 'Off')."""
        if option == OFF_LABEL:
            await self.coordinator.async_route(self._output, INPUT_NONE)
            return
        index = self._state.input_for_label(option)
        if index is None:
            raise ServiceValidationError(f"Unknown source: {option}")
        await self.coordinator.async_route(self._output, index)
