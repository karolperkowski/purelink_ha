"""Services for the PureLink UX-8800 integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .client import PureLinkError
from .const import (
    ATTR_INPUT,
    ATTR_NAME,
    ATTR_OUTPUT,
    ATTR_PRESET,
    ATTR_SLOT,
    DOMAIN,
    MATRIX_SIZE,
    PRESET_COUNT,
    SERVICE_RECALL_PRESET,
    SERVICE_ROUTE,
    SERVICE_ROUTE_ALL,
    SERVICE_SAVE_PRESET,
    SERVICE_SET_INPUT_NAME,
    SERVICE_SET_OUTPUT_NAME,
)
from .coordinator import UX8800Coordinator

ATTR_DEVICE_ID = "device_id"

_INPUT = vol.All(vol.Coerce(int), vol.Range(min=0, max=MATRIX_SIZE))
_OUTPUT = vol.All(vol.Coerce(int), vol.Range(min=1, max=MATRIX_SIZE))
_SLOT = vol.All(vol.Coerce(int), vol.Range(min=1, max=PRESET_COUNT))
_NAME = vol.All(cv.string, vol.Length(min=1, max=8))

_BASE = {vol.Optional(ATTR_DEVICE_ID): cv.string}

ROUTE_SCHEMA = vol.Schema({**_BASE, vol.Required(ATTR_OUTPUT): _OUTPUT, vol.Required(ATTR_INPUT): _INPUT})
ROUTE_ALL_SCHEMA = vol.Schema({**_BASE, vol.Required(ATTR_INPUT): _INPUT})
RECALL_SCHEMA = vol.Schema({**_BASE, vol.Required(ATTR_PRESET): vol.Any(_SLOT, cv.string)})
SAVE_SCHEMA = vol.Schema({**_BASE, vol.Required(ATTR_SLOT): _SLOT, vol.Required(ATTR_NAME): _NAME})
SET_INPUT_NAME_SCHEMA = vol.Schema({**_BASE, vol.Required(ATTR_INPUT): _OUTPUT, vol.Required(ATTR_NAME): _NAME})
SET_OUTPUT_NAME_SCHEMA = vol.Schema({**_BASE, vol.Required(ATTR_OUTPUT): _OUTPUT, vol.Required(ATTR_NAME): _NAME})


def _loaded_coordinators(hass: HomeAssistant) -> list[UX8800Coordinator]:
    return [
        entry.runtime_data
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
        and getattr(entry, "runtime_data", None) is not None
    ]


def _resolve(hass: HomeAssistant, call: ServiceCall) -> UX8800Coordinator:
    """Return the coordinator to act on, disambiguating by device_id if needed."""
    coordinators = _loaded_coordinators(hass)
    if not coordinators:
        raise ServiceValidationError("No PureLink UX-8800 device is configured")

    device_id = call.data.get(ATTR_DEVICE_ID)
    if device_id:
        device = dr.async_get(hass).async_get(device_id)
        if device is None:
            raise ServiceValidationError(f"Unknown device: {device_id}")
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.entry_id in device.config_entries and getattr(
                entry, "runtime_data", None
            ):
                return entry.runtime_data
        raise ServiceValidationError("device_id does not belong to a UX-8800")

    if len(coordinators) > 1:
        raise ServiceValidationError(
            "Multiple UX-8800 devices configured; specify 'device_id'"
        )
    return coordinators[0]


def _resolve_preset(coordinator: UX8800Coordinator, value: str | int) -> int:
    """Accept a slot number or a preset name and return the slot."""
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if text.isdigit():
        slot = int(text)
        if 1 <= slot <= PRESET_COUNT:
            return slot
    for slot, name in coordinator.client.state.preset_names.items():
        if name.strip().lower() == text.lower():
            return slot
    raise ServiceValidationError(f"Unknown preset: {value}")


async def _run(awaitable) -> None:
    """Await a device operation, mapping device errors to HomeAssistantError."""
    try:
        await awaitable
    except PureLinkError as err:
        raise HomeAssistantError(str(err)) from err


def async_setup_services(hass: HomeAssistant) -> None:
    """Register integration services once."""
    if hass.services.has_service(DOMAIN, SERVICE_ROUTE):
        return

    async def _route(call: ServiceCall) -> None:
        coordinator = _resolve(hass, call)
        await _run(coordinator.async_route(call.data[ATTR_OUTPUT], call.data[ATTR_INPUT]))

    async def _route_all(call: ServiceCall) -> None:
        coordinator = _resolve(hass, call)
        await _run(coordinator.async_route_all(call.data[ATTR_INPUT]))

    async def _recall_preset(call: ServiceCall) -> None:
        coordinator = _resolve(hass, call)
        slot = _resolve_preset(coordinator, call.data[ATTR_PRESET])
        await _run(coordinator.async_recall_preset(slot))

    async def _save_preset(call: ServiceCall) -> None:
        coordinator = _resolve(hass, call)
        await _run(coordinator.async_save_preset(call.data[ATTR_SLOT], call.data[ATTR_NAME]))

    async def _set_input_name(call: ServiceCall) -> None:
        coordinator = _resolve(hass, call)
        await _run(coordinator.async_set_name("input", call.data[ATTR_INPUT], call.data[ATTR_NAME]))

    async def _set_output_name(call: ServiceCall) -> None:
        coordinator = _resolve(hass, call)
        await _run(coordinator.async_set_name("output", call.data[ATTR_OUTPUT], call.data[ATTR_NAME]))

    hass.services.async_register(DOMAIN, SERVICE_ROUTE, _route, schema=ROUTE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_ROUTE_ALL, _route_all, schema=ROUTE_ALL_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_RECALL_PRESET, _recall_preset, schema=RECALL_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SAVE_PRESET, _save_preset, schema=SAVE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SET_INPUT_NAME, _set_input_name, schema=SET_INPUT_NAME_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SET_OUTPUT_NAME, _set_output_name, schema=SET_OUTPUT_NAME_SCHEMA)
