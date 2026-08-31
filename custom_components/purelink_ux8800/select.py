"""Select platform: one dropdown per output (an alternative to media_player)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
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
    """Set up routing selects (per output) and EDID selects (per input)."""
    coordinator = entry.runtime_data
    entities: list[SelectEntity] = [
        PureLinkOutputSelect(coordinator, out) for out in range(1, MATRIX_SIZE + 1)
    ]
    entities += [
        PureLinkEdidSelect(coordinator, inp) for inp in range(1, MATRIX_SIZE + 1)
    ]
    async_add_entities(entities)


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


class PureLinkEdidSelect(PureLinkEntity, SelectEntity):
    """Assign an EDID mode to an input.

    The device cannot report which mode is currently active (it only returns a
    free-text EDID description), so this is an optimistic control: it shows the
    last mode set from Home Assistant and exposes the device's current EDID
    description as an attribute. Disabled by default (config category).
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:video-input-hdmi"

    def __init__(self, coordinator: UX8800Coordinator, index: int) -> None:
        """Initialise for a specific input."""
        super().__init__(coordinator)
        self._index = index
        self._attr_unique_id = f"{self._base_unique_id}_input_{index}_edid"
        self._last_label: str | None = None

    @property
    def name(self) -> str:
        """Name like 'CABLE EDID'."""
        return f"{self._state.input_name(self._index)} EDID"

    @property
    def options(self) -> list[str]:
        """Available EDID mode labels."""
        return [label for _, label in self._state.edid_options()]

    @property
    def current_option(self) -> str | None:
        """Last EDID mode set from HA (device does not report the active mode)."""
        return self._last_label

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the device's reported current EDID description."""
        return {"current_edid": self._state.edid_current.get(self._index)}

    async def async_select_option(self, option: str) -> None:
        """Assign the chosen EDID mode to this input."""
        mode = self._state.edid_mode_for_label(option)
        if mode is None:
            raise ServiceValidationError(f"Unknown EDID mode: {option}")
        await self.coordinator.async_set_edid(self._index, mode)
        self._last_label = option
