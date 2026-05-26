from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
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
    DISCONNECTED_LABEL,
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
        PureLinkOutputSelect(
            coordinator=coordinator,
            output_num=out,
            num_inputs=num_inputs,
            entry_id=entry.entry_id,
            switcher_id=switcher_id,
            host=host,
        )
        for out in range(1, num_outputs + 1)
    )


class PureLinkOutputSelect(CoordinatorEntity[PureLinkCoordinator], SelectEntity):
    _attr_has_entity_name = True

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
        self._attr_name = f"Output {output_num}"
        self._attr_unique_id = f"purelink_{host}_{switcher_id}_output_{output_num}"
        self._attr_options = [DISCONNECTED_LABEL] + [
            f"Input {i}" for i in range(1, num_inputs + 1)
        ]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{host}_{switcher_id}")},
            name=f"PureLink Switcher ({host})",
            manufacturer="Dtrovision",
            model="PureLink Matrix Switcher",
        )

    @property
    def current_option(self) -> str | None:
        if self.coordinator.data is None:
            return None
        inp = self.coordinator.data.get(self._output_num, 0)
        if inp == 0:
            return DISCONNECTED_LABEL
        return f"Input {inp}"

    async def async_select_option(self, option: str) -> None:
        if option == DISCONNECTED_LABEL:
            await self.coordinator.client.disconnect_output(self._output_num)
        else:
            inp = int(option.split()[-1])
            await self.coordinator.client.connect_input_to_output(inp, self._output_num)
        await self.coordinator.async_request_refresh()
