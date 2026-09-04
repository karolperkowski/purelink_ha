from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_SWITCHER_ID,
    DEFAULT_NUM_PRESETS,
    DOMAIN,
    PRESET_DEFAULT_NAME_TEMPLATE,
    PRESET_LABEL_TEMPLATE,
)
from .coordinator import PureLinkCoordinator


def _is_configured(name: str, preset_num: int) -> bool:
    """A preset looks configured if it has a non-default, non-empty name.

    The web UI seeds unused slots with the literal name ``preset<n>``; those
    (and blanks) are created disabled so only presets the user has set up show
    by default.
    """
    name = (name or "").strip()
    return bool(name) and name.lower() != PRESET_DEFAULT_NAME_TEMPLATE.format(n=preset_num)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: PureLinkCoordinator = data["coordinator"]
    preset_names: dict[int, str] = data.get("preset_names", {})
    host: str = entry.data[CONF_HOST]
    switcher_id: int = entry.data[CONF_SWITCHER_ID]
    sw_version: str | None = data["sw_version"]

    async_add_entities(
        PureLinkPresetButton(
            coordinator=coordinator,
            preset_num=preset,
            preset_name=preset_names.get(preset, ""),
            entry_id=entry.entry_id,
            switcher_id=switcher_id,
            host=host,
            sw_version=sw_version,
        )
        for preset in range(1, DEFAULT_NUM_PRESETS + 1)
    )


class PureLinkPresetButton(CoordinatorEntity[PureLinkCoordinator], ButtonEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:play-box-multiple"

    def __init__(
        self,
        coordinator: PureLinkCoordinator,
        preset_num: int,
        preset_name: str,
        entry_id: str,
        switcher_id: int,
        host: str,
        sw_version: str | None,
    ) -> None:
        super().__init__(coordinator)
        self._preset_num = preset_num
        configured = _is_configured(preset_name, preset_num)
        self._attr_name = (
            preset_name.strip()
            if configured
            else PRESET_LABEL_TEMPLATE.format(n=preset_num)
        )
        # Only presets that already have a real name are enabled by default;
        # generic-labelled ones (or all 20 when no names were fetched) are
        # created disabled to avoid cluttering the device page.
        self._attr_entity_registry_enabled_default = configured
        self._attr_unique_id = f"purelink_{host}_{switcher_id}_preset_{preset_num}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{host}_{switcher_id}")},
            name=f"PureLink Switcher ({host})",
            manufacturer="Dtrovision",
            model="PureLink Matrix Switcher",
            sw_version=sw_version,
        )

    async def async_press(self) -> None:
        await self.coordinator.async_recall_preset(self._preset_num)
