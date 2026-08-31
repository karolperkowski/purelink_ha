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
        # Entries created before the config flow validated port counts can
        # carry 0 here, which yields a hub with no entities and no device.
        _LOGGER.warning(
            "PureLink entry for %s is configured with %d inputs / %d outputs; "
            "no entities will be created. Remove and re-add the hub with the "
            "correct port counts",
            host,
            num_inputs,
            num_outputs,
        )
        return

    # DISCONNECTED_LABEL is reserved so a device input literally named
    # "Disconnected" cannot shadow the disconnect option.
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
        PureLinkOutputSelect(
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


class PureLinkOutputSelect(CoordinatorEntity[PureLinkCoordinator], SelectEntity):
    _attr_has_entity_name = True

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
        self._input_labels = input_labels
        self._label_to_input = {label: num for num, label in input_labels.items()}
        # "source" suffix distinguishes this from the media_player entity for
        # the same output; the unique_id predates media_player and is unchanged.
        self._attr_name = f"{output_label} source"
        self._attr_unique_id = f"purelink_{host}_{switcher_id}_output_{output_num}"
        self._attr_options = [DISCONNECTED_LABEL] + [
            input_labels[i] for i in sorted(input_labels)
        ]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{host}_{switcher_id}")},
            name=f"PureLink Switcher ({host})",
            manufacturer="Dtrovision",
            model="PureLink Matrix Switcher",
            sw_version=sw_version,
        )

    @property
    def current_option(self) -> str | None:
        if self.coordinator.data is None:
            return None
        inp = self.coordinator.data.get(self._output_num, 0)
        if inp == 0:
            return DISCONNECTED_LABEL
        # For an input above the configured count (routed externally) the
        # fallback is not in the options list, so HA shows the entity as
        # unknown; the .get only avoids returning a wrong port's label.
        return self._input_labels.get(inp, INPUT_LABEL_TEMPLATE.format(n=inp))

    async def async_select_option(self, option: str) -> None:
        if option == DISCONNECTED_LABEL:
            await self.coordinator.client.disconnect_output(self._output_num)
        else:
            inp = self._label_to_input[option]
            await self.coordinator.client.connect_input_to_output(inp, self._output_num)
        await self.coordinator.async_request_refresh()
