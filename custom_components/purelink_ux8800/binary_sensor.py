"""Binary sensor platform: per-input signal presence."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import MATRIX_SIZE
from .coordinator import PureLinkConfigEntry, UX8800Coordinator
from .entity import PureLinkEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PureLinkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one signal-present binary sensor per input."""
    coordinator = entry.runtime_data
    async_add_entities(
        PureLinkInputSignal(coordinator, inp) for inp in range(1, MATRIX_SIZE + 1)
    )


class PureLinkInputSignal(PureLinkEntity, BinarySensorEntity):
    """Whether an input currently has a detected signal."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: UX8800Coordinator, index: int) -> None:
        """Initialise for a specific input."""
        super().__init__(coordinator)
        self._index = index
        self._attr_unique_id = f"{self._base_unique_id}_input_{index}_signal"

    @property
    def name(self) -> str:
        """Name like 'CABLE signal'."""
        return f"{self._state.input_name(self._index)} signal"

    @property
    def is_on(self) -> bool | None:
        """True when a signal is present."""
        return self._state.input_signal.get(self._index)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Resolution and HDCP status for this input."""
        return {
            "resolution": self._state.input_resolution.get(self._index),
            "hdcp": self._state.input_hdcp.get(self._index),
            "input_number": self._index,
        }
