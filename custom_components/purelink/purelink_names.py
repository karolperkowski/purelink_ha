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
    WS_ATTR_INPUT_PREFIX,
    WS_ATTR_OUTPUT_PREFIX,
    WS_CMD_LOGIN_TEMPLATE,
    WS_CMD_REQUESTALL,
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
