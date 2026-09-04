from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    ATTR_DEVICE_ID,
    ATTR_NAME,
    ATTR_ROUTING,
    ATTR_SLOT,
    CONF_NUM_OUTPUTS,
    DEFAULT_NUM_PRESETS,
    DOMAIN,
    PRESET_DEFAULT_NAME_TEMPLATE,
    PRESET_NAME_MAX_LEN,
    SERVICE_DELETE_PRESET,
    SERVICE_SAVE_PRESET,
)
from .purelink_names import (
    PureLinkAuthError,
    PureLinkNamesError,
    async_write_preset,
    build_preset_data,
)

_LOGGER = logging.getLogger(__name__)

_SLOT = vol.All(vol.Coerce(int), vol.Range(min=1, max=DEFAULT_NUM_PRESETS))
_PORT_NUM = vol.All(vol.Coerce(int), vol.Range(min=0, max=64))

SAVE_PRESET_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_SLOT): _SLOT,
        vol.Optional(ATTR_NAME): cv.string,
        vol.Optional(ATTR_ROUTING): {_PORT_NUM: _PORT_NUM},
    }
)

DELETE_PRESET_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_SLOT): _SLOT,
    }
)


def _resolve_loaded(hass: HomeAssistant, call: ServiceCall) -> tuple[ConfigEntry, dict]:
    """Return the loaded PureLink entry (and its runtime data) for the device."""
    device_id = call.data[ATTR_DEVICE_ID]
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise ServiceValidationError(f"Unknown device: {device_id}")
    for entry_id in device.config_entries:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is not None and entry.domain == DOMAIN:
            data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
            if data is None:
                raise ServiceValidationError(
                    "The PureLink switcher is not loaded; try again once it is available."
                )
            return entry, data
    raise ServiceValidationError("Selected device is not a PureLink switcher")


async def _write_slot(
    hass: HomeAssistant,
    entry: ConfigEntry,
    entry_data: dict,
    slot: int,
    name: str | None,
    data: str,
) -> None:
    """Validate credentials, write the slot (serialised), and reload buttons."""
    username = entry.data.get(CONF_USERNAME) or ""
    password = entry.data.get(CONF_PASSWORD) or ""
    if not (username and password):
        raise ServiceValidationError(
            "Preset management requires the Web UI username and password. "
            "Reconfigure the PureLink integration and add them."
        )
    try:
        # Serialise read-modify-write per entry so concurrent calls can't
        # clobber each other's slot (last-writer-wins over the whole table).
        async with entry_data["preset_lock"]:
            await async_write_preset(
                async_get_clientsession(hass),
                entry.data[CONF_HOST],
                username,
                password,
                slot,
                name,
                data,
            )
    except PureLinkAuthError as err:
        raise ServiceValidationError(
            "The stored Web UI credentials were rejected. Reconfigure them."
        ) from err
    except PureLinkNamesError as err:
        raise HomeAssistantError(f"Preset write failed: {err}") from err

    # Reload so preset buttons pick up the new name / enabled state.
    hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register preset-management services once for the integration."""
    if hass.services.has_service(DOMAIN, SERVICE_SAVE_PRESET):
        return

    async def _save(call: ServiceCall) -> None:
        entry, entry_data = _resolve_loaded(hass, call)
        slot = call.data[ATTR_SLOT]
        num_outputs = entry.data[CONF_NUM_OUTPUTS]

        routing = dict(entry_data["coordinator"].data or {})
        for output, source in (call.data.get(ATTR_ROUTING) or {}).items():
            routing[int(output)] = int(source)
        preset_data = build_preset_data(routing, num_outputs)

        name = call.data.get(ATTR_NAME)
        if name is not None:
            # Strip, truncate to the device field width, then strip again so a
            # cut mid-word can't leave a trailing space (which the readback
            # verify would otherwise reject even though the write succeeded).
            name = name.strip()[:PRESET_NAME_MAX_LEN].strip()
            if not name:
                raise ServiceValidationError("Preset name cannot be blank")
        await _write_slot(hass, entry, entry_data, slot, name, preset_data)

    async def _delete(call: ServiceCall) -> None:
        entry, entry_data = _resolve_loaded(hass, call)
        slot = call.data[ATTR_SLOT]
        num_outputs = entry.data[CONF_NUM_OUTPUTS]
        # Reset the slot to the device's unconfigured default.
        default_name = PRESET_DEFAULT_NAME_TEMPLATE.format(n=slot)
        await _write_slot(
            hass, entry, entry_data, slot, default_name, build_preset_data({}, num_outputs)
        )

    hass.services.async_register(
        DOMAIN, SERVICE_SAVE_PRESET, _save, schema=SAVE_PRESET_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DELETE_PRESET, _delete, schema=DELETE_PRESET_SCHEMA
    )
