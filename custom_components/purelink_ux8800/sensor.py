"""Sensor platform: input resolution/HDCP, output sync, and master volume."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .client import MatrixState
from .const import MATRIX_SIZE
from .coordinator import PureLinkConfigEntry, UX8800Coordinator
from .entity import PureLinkEntity


@dataclass(frozen=True, kw_only=True)
class PureLinkSensorDescription(SensorEntityDescription):
    """Describes a UX-8800 sensor bound to a channel index."""

    value_fn: Callable[[MatrixState, int], str | int | None]
    name_fn: Callable[[MatrixState, int], str]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PureLinkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up diagnostic sensors and the master-volume sensor."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = []

    for inp in range(1, MATRIX_SIZE + 1):
        entities.append(
            PureLinkChannelSensor(
                coordinator,
                inp,
                PureLinkSensorDescription(
                    key=f"input_{inp}_resolution",
                    entity_category=EntityCategory.DIAGNOSTIC,
                    icon="mdi:monitor",
                    value_fn=lambda s, i: s.input_resolution.get(i),
                    name_fn=lambda s, i: f"{s.input_name(i)} resolution",
                ),
            )
        )
        entities.append(
            PureLinkChannelSensor(
                coordinator,
                inp,
                PureLinkSensorDescription(
                    key=f"input_{inp}_hdcp",
                    entity_category=EntityCategory.DIAGNOSTIC,
                    entity_registry_enabled_default=False,
                    icon="mdi:shield-lock",
                    value_fn=lambda s, i: s.input_hdcp.get(i),
                    name_fn=lambda s, i: f"{s.input_name(i)} HDCP",
                ),
            )
        )

    for out in range(1, MATRIX_SIZE + 1):
        entities.append(
            PureLinkChannelSensor(
                coordinator,
                out,
                PureLinkSensorDescription(
                    key=f"output_{out}_sync",
                    entity_category=EntityCategory.DIAGNOSTIC,
                    entity_registry_enabled_default=False,
                    icon="mdi:television",
                    value_fn=lambda s, i: s.output_sync.get(i),
                    name_fn=lambda s, i: f"{s.output_name(i)} sync",
                ),
            )
        )

    entities.append(PureLinkVolumeSensor(coordinator))
    async_add_entities(entities)


class PureLinkChannelSensor(PureLinkEntity, SensorEntity):
    """A diagnostic string sensor tied to an input or output index."""

    entity_description: PureLinkSensorDescription

    def __init__(
        self,
        coordinator: UX8800Coordinator,
        index: int,
        description: PureLinkSensorDescription,
    ) -> None:
        """Initialise from a description + channel index."""
        super().__init__(coordinator)
        self._index = index
        self.entity_description = description
        self._attr_unique_id = f"{self._base_unique_id}_{description.key}"

    @property
    def name(self) -> str:
        """Dynamic name derived from the current channel label."""
        return self.entity_description.name_fn(self._state, self._index)

    @property
    def native_value(self) -> str | int | None:
        """Current sensor value."""
        return self.entity_description.value_fn(self._state, self._index)


class PureLinkVolumeSensor(PureLinkEntity, SensorEntity):
    """Read-only master volume reported by the device."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:volume-high"

    def __init__(self, coordinator: UX8800Coordinator) -> None:
        """Initialise the master-volume sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._base_unique_id}_master_volume"

    @property
    def name(self) -> str:
        """Sensor name."""
        return "Master volume"

    @property
    def native_value(self) -> int | None:
        """Current master volume value."""
        return self._state.master_volume
