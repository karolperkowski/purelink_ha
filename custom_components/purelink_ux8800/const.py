"""Constants for the PureLink UX-8800 integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "purelink_ux8800"

MANUFACTURER: Final = "PureLink"
MODEL: Final = "UX-8800"

PLATFORMS: Final = [
    Platform.MEDIA_PLAYER,
    Platform.SELECT,
    Platform.BUTTON,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
]

# Device shape (an 8x8 matrix with 20 preset slots).
MATRIX_SIZE: Final = 8
PRESET_COUNT: Final = 20
MAX_NAME_LEN: Final = 8

# Connection defaults.
DEFAULT_USERNAME: Final = "admin"
DEFAULT_WS_PORT: Final = 8887

# Options.
CONF_POLL_INTERVAL: Final = "poll_interval"
CONF_INFO_INTERVAL: Final = "info_interval"
DEFAULT_POLL_INTERVAL: Final = 3  # seconds, routing/name snapshot (source of truth)
DEFAULT_INFO_INTERVAL: Final = 15  # seconds, signal/HDCP/sync diagnostics
MIN_POLL_INTERVAL: Final = 2
MAX_POLL_INTERVAL: Final = 60

# Special routing value meaning "no input" (output disconnected).
INPUT_NONE: Final = 0

# Service names.
SERVICE_ROUTE: Final = "route"
SERVICE_ROUTE_ALL: Final = "route_all"
SERVICE_RECALL_PRESET: Final = "recall_preset"
SERVICE_SAVE_PRESET: Final = "save_preset"
SERVICE_SET_INPUT_NAME: Final = "set_input_name"
SERVICE_SET_OUTPUT_NAME: Final = "set_output_name"

# Service fields.
ATTR_INPUT: Final = "input"
ATTR_OUTPUT: Final = "output"
ATTR_PRESET: Final = "preset"
ATTR_SLOT: Final = "slot"
ATTR_NAME: Final = "name"
ATTR_ROUTING: Final = "routing"
