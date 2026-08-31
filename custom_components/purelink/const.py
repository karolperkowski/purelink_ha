DOMAIN = "purelink"

CONF_SWITCHER_ID = "switcher_id"
CONF_NUM_INPUTS = "num_inputs"
CONF_NUM_OUTPUTS = "num_outputs"

DEFAULT_PORT = 23
DEFAULT_SWITCHER_ID = 255
DEFAULT_TIMEOUT = 5
DEFAULT_POLL_INTERVAL = 30

CMD_CONNECT_TEMPLATE = "*{sid:03d}CI{inp:02d}O{out:02d}!"
CMD_DISCONNECT_TEMPLATE = "*{sid:03d}CI00O{out:02d}!"
CMD_DISCONNECT_ALL = "*{sid:03d}DALLIO!"
CMD_STATUS_ALL = "*{sid:03d}?C!"
CMD_HEARTBEAT = "*{sid:03d}H000!"
CMD_VERSION = "*{sid:03d}?VERSIONCT!"

# Web UI websocket (only source for user-assigned port names; see AGENTS.md).
WS_PORT = 8887
WS_FETCH_TIMEOUT = 10
WS_MAX_FRAMES = 10
# XML frames ({id}/{password} are filled with quoteattr-escaped values).
WS_CMD_LOGIN_TEMPLATE = (
    "<command type='inquery' name='login' id={id} pass={password}>login</command>"
)
WS_CMD_REQUESTALL = "<command type='inquery' name='requestall_main'>main</command>"
WS_GREETING_NAME = "connected"
WS_RESULT_OK = "good"
WS_FRAME_SETALL = "setall"
WS_ATTR_INPUT_PREFIX = "inname"
WS_ATTR_OUTPUT_PREFIX = "outname"

# Generic port label fallbacks (used when no device names are available).
INPUT_LABEL_TEMPLATE = "Input {n}"
OUTPUT_LABEL_TEMPLATE = "Output {n}"

RESP_ERROR_COMMAND = "Command Code Error"
RESP_ERROR_SWITCHER = "Switcher ID Error"

DISCONNECTED_LABEL = "Disconnected"

PLATFORMS = ["media_player", "select"]
