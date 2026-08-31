"""Diagnostics support for PureLink UX-8800.

Note: the client never stores the device's ``setting`` frame (which echoes
account passwords), so the state snapshot is safe. We still redact the config
entry password.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .coordinator import PureLinkConfigEntry

TO_REDACT = {CONF_PASSWORD}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PureLinkConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    state = coordinator.client.state
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
            "unique_id": entry.unique_id,
        },
        "device": {
            "host": coordinator.client.host,
            "sw_version": state.sw_version,
            "web_version": state.web_version,
            "connected": state.connected,
            "last_update_success": coordinator.last_update_success,
        },
        "routing": state.routing,
        "input_names": state.input_names,
        "output_names": state.output_names,
        "input_signal": state.input_signal,
        "input_resolution": state.input_resolution,
        "input_hdcp": state.input_hdcp,
        "output_sync": state.output_sync,
        "preset_names": state.preset_names,
        "preset_data": state.preset_data,
        "master_volume": state.master_volume,
    }
