"""Base entity for the PureLink UX-8800 integration."""

from __future__ import annotations

from homeassistant.helpers.device_info import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import UX8800Coordinator


class PureLinkEntity(CoordinatorEntity[UX8800Coordinator]):
    """Shared base: one HA device per matrix, coordinator-driven availability."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: UX8800Coordinator) -> None:
        """Initialise common device info."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._base_unique_id = entry.unique_id or entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._base_unique_id)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name="PureLink UX-8800",
            sw_version=coordinator.client.state.sw_version,
            configuration_url=f"http://{coordinator.client.host}",
        )

    @property
    def _state(self):
        """Convenience accessor for the current matrix state."""
        return self.coordinator.client.state
