from __future__ import annotations

import asyncio
import logging

# The switcher's frames are small, fixed-shape XML from a local device; the
# stdlib parser keeps us within the no-third-party-deps rule.
from xml.etree import ElementTree
from xml.sax.saxutils import quoteattr

# aiohttp ships with Home Assistant core, so importing it here does not add a
# manifest requirement (requirements stays []). See AGENTS.md.
import aiohttp

from .const import (
    DEFAULT_NUM_PRESETS,
    WS_ATTR_INPUT_PREFIX,
    WS_ATTR_OUTPUT_PREFIX,
    WS_ATTR_PRESET_DATA_PREFIX,
    WS_ATTR_PRESET_PREFIX,
    WS_CMD_LOGIN_TEMPLATE,
    WS_CMD_PRESET,
    WS_CMD_REQUESTALL,
    WS_CMD_UPDATEPRESET_HEAD,
    WS_CMD_UPDATEPRESET_TAIL,
    WS_FETCH_TIMEOUT,
    WS_FRAME_SETALL,
    WS_GREETING_NAME,
    WS_MAX_FRAMES,
    WS_PORT,
    WS_RESULT_OK,
)

_LOGGER = logging.getLogger(__name__)


class PureLinkNamesError(Exception):
    """Fetching names from the web UI websocket failed."""


class PureLinkAuthError(PureLinkNamesError):
    """The web UI rejected the credentials."""


async def async_fetch_names(
    session: aiohttp.ClientSession,
    host: str,
    username: str,
    password: str,
    *,
    port: int = WS_PORT,
    timeout: float = WS_FETCH_TIMEOUT,
) -> tuple[dict[int, str], dict[int, str]]:
    """One-shot fetch of (input_names, output_names) from the web UI websocket.

    The UX-series web UI speaks XML over a websocket on port 8887: the device
    greets with <Update name='connected'>, expects a login command, then
    answers requestall_main with a 'setall' frame carrying innameN/outnameN
    attributes. The ASCII/Telnet protocol has no names query, so this channel
    is the only way to read the user-assigned port labels.
    """
    try:
        async with asyncio.timeout(timeout):
            ws = await session.ws_connect(f"ws://{host}:{port}")
            try:
                await _greet_and_login(ws, username, password)
                await ws.send_str(WS_CMD_REQUESTALL)
                for _ in range(WS_MAX_FRAMES):
                    frame = await _recv_update(ws)
                    if frame.get("name") == WS_FRAME_SETALL:
                        break
                else:
                    raise PureLinkNamesError("No 'setall' frame received")
                return (
                    _collect(frame, WS_ATTR_INPUT_PREFIX),
                    _collect(frame, WS_ATTR_OUTPUT_PREFIX),
                )
            finally:
                await ws.close()
    except PureLinkNamesError:
        raise
    except (
        aiohttp.ClientError,
        asyncio.TimeoutError,
        OSError,
        ElementTree.ParseError,
    ) as err:
        raise PureLinkNamesError(str(err)) from err


async def async_fetch_presets(
    session: aiohttp.ClientSession,
    host: str,
    username: str,
    password: str,
    *,
    port: int = WS_PORT,
    timeout: float = WS_FETCH_TIMEOUT,
) -> dict[int, str]:
    """One-shot fetch of preset slot names (1..20) from the web UI websocket.

    Same channel and handshake as :func:`async_fetch_names`; the preset query
    answers with a frame carrying presetnameN attributes. The Telnet protocol
    can recall/read presets by number but exposes no preset *names*, so this is
    the only source for friendly preset labels.
    """
    try:
        async with asyncio.timeout(timeout):
            ws = await session.ws_connect(f"ws://{host}:{port}")
            try:
                await _greet_and_login(ws, username, password)
                await ws.send_str(WS_CMD_PRESET)
                for _ in range(WS_MAX_FRAMES):
                    frame = await _recv_update(ws)
                    if any(k.startswith(WS_ATTR_PRESET_PREFIX) for k in frame):
                        return _collect(frame, WS_ATTR_PRESET_PREFIX)
                raise PureLinkNamesError("No preset frame received")
            finally:
                await ws.close()
    except PureLinkNamesError:
        raise
    except (
        aiohttp.ClientError,
        asyncio.TimeoutError,
        OSError,
        ElementTree.ParseError,
    ) as err:
        raise PureLinkNamesError(str(err)) from err


async def async_write_preset(
    session: aiohttp.ClientSession,
    host: str,
    username: str,
    password: str,
    slot: int,
    name: str | None,
    data: str,
    *,
    num_presets: int = DEFAULT_NUM_PRESETS,
    port: int = WS_PORT,
    timeout: float = WS_FETCH_TIMEOUT,
) -> None:
    """Read-modify-write a single preset slot over the web UI websocket.

    The device only writes the whole preset table at once, so this reads all
    slots, changes just ``slot`` to (``name``, ``data``), and writes them all
    back. ``name=None`` keeps the slot's current name (routing-only update). A
    hard guard aborts if the read did not return every slot, so a partial read
    can never blank the user's presets. After writing, the table is re-read and
    the target slot confirmed.
    """
    if not 1 <= slot <= num_presets:
        raise PureLinkNamesError(f"preset slot out of range: {slot}")
    try:
        async with asyncio.timeout(timeout):
            ws = await session.ws_connect(f"ws://{host}:{port}")
            try:
                await _greet_and_login(ws, username, password)
                await ws.send_str(WS_CMD_PRESET)
                names, datas = await _read_preset_table(ws, num_presets)
                if name is not None:
                    names[slot] = name
                datas[slot] = data
                await ws.send_str(_build_updatepreset(names, datas, num_presets))
                # Re-query and confirm the slot took (the device also echoes the
                # table after updatepreset; either frame is a valid readback).
                await ws.send_str(WS_CMD_PRESET)
                check_names, check_data = await _read_preset_table(ws, num_presets)
                # Compare stripped: the device may trim the stored name, and
                # _collect already strips the readback.
                if name is not None and check_names.get(slot, "").strip() != name.strip():
                    raise PureLinkNamesError(
                        f"Preset {slot} name not confirmed "
                        f"(device reports {check_names.get(slot)!r})"
                    )
                if check_data.get(slot) != data:
                    raise PureLinkNamesError(
                        f"Preset {slot} routing not confirmed "
                        f"(device reports {check_data.get(slot)!r})"
                    )
            finally:
                await ws.close()
    except PureLinkNamesError:
        raise
    except (
        aiohttp.ClientError,
        asyncio.TimeoutError,
        OSError,
        ElementTree.ParseError,
    ) as err:
        raise PureLinkNamesError(str(err)) from err


async def _greet_and_login(
    ws: aiohttp.ClientWebSocketResponse, username: str, password: str
) -> None:
    """Consume the greeting and authenticate; raise PureLinkAuthError on reject."""
    frame = await _recv_update(ws)
    if frame.get("name") != WS_GREETING_NAME:
        raise PureLinkNamesError(
            f"Unexpected websocket greeting: {frame.get('name')!r}"
        )
    await ws.send_str(
        WS_CMD_LOGIN_TEMPLATE.format(
            id=quoteattr(username), password=quoteattr(password)
        )
    )
    frame = await _recv_update(ws)
    if frame.get("result") != WS_RESULT_OK:
        raise PureLinkAuthError("Web UI rejected the credentials")


async def _read_preset_table(
    ws: aiohttp.ClientWebSocketResponse, num_presets: int
) -> tuple[dict[int, str], dict[int, str]]:
    """Read a full preset table; raise unless every slot's name and data parse."""
    for _ in range(WS_MAX_FRAMES):
        frame = await _recv_update(ws)
        if any(k.startswith(WS_ATTR_PRESET_PREFIX) for k in frame):
            names = _collect(frame, WS_ATTR_PRESET_PREFIX)
            datas = _collect(frame, WS_ATTR_PRESET_DATA_PREFIX)
            # Treat an absent OR empty name/data as missing: writing back a
            # blank slot would defeat the "never blank a preset" guarantee.
            missing = [
                i
                for i in range(1, num_presets + 1)
                if not names.get(i) or not datas.get(i)
            ]
            if missing:
                raise PureLinkNamesError(
                    f"Incomplete preset table; missing slots {missing}"
                )
            return names, datas
    raise PureLinkNamesError("No preset frame received")


def build_preset_data(routing: dict[int, int], num_outputs: int) -> str:
    """Build a ``presetdata`` string (``I01O01,...``) from an output->input map.

    One ``IxxOyy`` pair per output 1..num_outputs; outputs absent from
    ``routing`` (or mapped to 0) are stored as disconnected (``I00``).
    """
    return ",".join(
        f"I{routing.get(out, 0):02d}O{out:02d}" for out in range(1, num_outputs + 1)
    )


def _build_updatepreset(
    names: dict[int, str], datas: dict[int, str], num_presets: int
) -> str:
    parts = [WS_CMD_UPDATEPRESET_HEAD]
    for i in range(1, num_presets + 1):
        parts.append(f"{WS_ATTR_PRESET_PREFIX}{i}={quoteattr(names[i])} ")
        parts.append(f"{WS_ATTR_PRESET_DATA_PREFIX}{i}={quoteattr(datas[i])} ")
    parts.append(WS_CMD_UPDATEPRESET_TAIL)
    return "".join(parts)


async def _recv_update(ws: aiohttp.ClientWebSocketResponse) -> dict[str, str]:
    msg = await ws.receive()
    if msg.type is not aiohttp.WSMsgType.TEXT:
        raise PureLinkNamesError(f"Unexpected websocket frame: {msg.type}")
    return {str(k): str(v) for k, v in ElementTree.fromstring(msg.data).attrib.items()}


def _collect(frame: dict[str, str], prefix: str) -> dict[int, str]:
    names: dict[int, str] = {}
    for key, value in frame.items():
        suffix = key[len(prefix) :]
        if key.startswith(prefix) and suffix.isdigit():
            names[int(suffix)] = value.strip()
    return names


def build_labels(
    names: dict[int, str],
    count: int,
    fallback: str,
    reserved: frozenset[str] = frozenset(),
) -> dict[int, str]:
    """Build unique, non-empty display labels for ports 1..count.

    ``fallback`` is a format string like ``"Input {n}"`` used for blank names.
    Duplicated device names (e.g. several ports named EMPTY) get a ``(n)``
    suffix, uniqueness is guaranteed even against pathological device names
    (an input literally called "EMPTY (5)"), and labels never collide with
    ``reserved`` strings (e.g. the select platform's "Disconnected" option).
    """
    base = {
        n: (names.get(n) or "").strip() or fallback.format(n=n)
        for n in range(1, count + 1)
    }
    counts: dict[str, int] = {}
    for label in base.values():
        counts[label] = counts.get(label, 0) + 1

    used: set[str] = set(reserved)
    labels: dict[int, str] = {}
    for n in sorted(base):
        label = base[n]
        candidate = (
            f"{label} ({n})" if counts[label] > 1 or label in reserved else label
        )
        while candidate in used:
            candidate = f"{candidate} ({n})"
        used.add(candidate)
        labels[n] = candidate
    return labels
