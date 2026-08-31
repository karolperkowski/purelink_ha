"""Button platform: one recall button per preset slot."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import PRESET_COUNT
from .coordinator import PureLinkConfigEntry, UX8800Coordinator
from .entity import PureLinkEntity


def _is_configured(name: str, slot: int) -> bool:
    """A preset looks configured if it has a non-default, non-empty name."""
    name = (name or "").strip()
    return bool(name) and name.lower() != f"preset{slot}"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PureLinkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one recall button per preset slot (unconfigured ones disabled)."""
    coordinator = entry.runtime_data
    async_add_entities(
        PureLinkPresetButton(coordinator, slot)
        for slot in range(1, PRESET_COUNT + 1)
    )


class PureLinkPresetButton(PureLinkEntity, ButtonEntity):
    """Recall a stored preset."""

    _attr_icon = "mdi:play-box-multiple"

    def __init__(self, coordinator: UX8800Coordinator, slot: int) -> None:
        """Initialise for a specific preset slot."""
        super().__init__(coordinator)
        self._slot = slot
        self._attr_unique_id = f"{self._base_unique_id}_preset_{slot}"
        # Enable only presets that already carry a meaningful name.
        initial = coordinator.client.state.preset_names.get(slot, "")
        self._attr_entity_registry_enabled_default = _is_configured(initial, slot)

    @property
    def name(self) -> str:
        """Preset name, falling back to 'Preset N'."""
        name = (self._state.preset_names.get(self._slot, "") or "").strip()
        return name if _is_configured(name, self._slot) else f"Preset {self._slot}"

    async def async_press(self) -> None:
        """Recall this preset."""
        await self.coordinator.async_recall_preset(self._slot)
