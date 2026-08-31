"""Async WebSocket client for the PureLink UX-8800 matrix switcher.

This module is intentionally Home Assistant-agnostic: it only depends on
``aiohttp`` (already a HA dependency) and ``defusedxml``.  It is vendored inside
the integration for v1; it can later be extracted into a standalone ``pypurelink``
package on PyPI without touching the rest of the integration.

Protocol (reverse-engineered and live-validated against a real UX-8800):

* Control channel is a WebSocket at ``ws://<host>:8887`` exchanging XML frames.
* On connect the device sends ``<Update name='connected'>``.
* The client must authenticate before any command is honoured::

      <command type='inquery' name='login' id='admin' pass='...'>login</command>
      -> <Update name="update" result="good"/>

* Routing (core feature)::

      <command type='update' name='GetOut' id='<out 1-8>'><in 0-8></command>

  Input ``0`` disconnects the output.

Key behaviours learned from the hardware (do not "simplify" these away):

1.  The device does **not** broadcast state changes to other clients, so the
    integration polls ``requestall_main`` for authoritative state.
2.  A command sent on a freshly-logged-in socket can be silently dropped, so we
    hydrate (``requestall_main``) right after login to "warm" the connection and
    routing writes are verify-and-retry.
3.  Cancelling a pending WebSocket ``receive()`` aborts the socket, so exactly one
    task (the reader loop) ever calls ``receive()`` and it is never wrapped in a
    cancelling timeout.  Request/response correlation uses futures whose *await*
    is what carries a timeout, never the socket read.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from xml.sax.saxutils import quoteattr

import aiohttp
from defusedxml.ElementTree import fromstring as xml_fromstring

_LOGGER = logging.getLogger(__name__)

DEFAULT_WS_PORT = 8887
MATRIX_SIZE = 8
PRESET_COUNT = 20
MAX_NAME_LEN = 8
INPUT_NONE = 0

CONNECT_TIMEOUT = 10.0
HANDSHAKE_TIMEOUT = 8.0
RESPONSE_TIMEOUT = 6.0
ROUTE_MAX_ATTEMPTS = 3
ROUTE_SETTLE = 0.35


class PureLinkError(Exception):
    """Base error for the PureLink client."""


class CannotConnect(PureLinkError):
    """Raised when the device cannot be reached."""


class InvalidAuth(PureLinkError):
    """Raised when authentication is rejected by the device."""


@dataclass
class MatrixState:
    """In-memory snapshot of the matrix, kept current by the reader loop."""

    connected: bool = False
    # Routing: output number (1..8) -> input number (0..8); 0 means disconnected.
    routing: dict[int, int] = field(default_factory=dict)
    input_names: dict[int, str] = field(default_factory=dict)
    output_names: dict[int, str] = field(default_factory=dict)
    # Presets: slot (1..20) -> friendly name / compact routing data ("I01O01,...").
    preset_names: dict[int, str] = field(default_factory=dict)
    preset_data: dict[int, str] = field(default_factory=dict)
    # Diagnostics (from the "info" query).
    input_signal: dict[int, bool] = field(default_factory=dict)
    input_resolution: dict[int, str] = field(default_factory=dict)
    input_hdcp: dict[int, str] = field(default_factory=dict)
    output_sync: dict[int, str] = field(default_factory=dict)
    master_volume: int | None = None
    sw_version: str | None = None
    web_version: str | None = None
    # EDID: available modes (index 1..N -> label) and current per-input EDID
    # description as reported by the device.
    edid_list: dict[int, str] = field(default_factory=dict)
    edid_current: dict[int, str] = field(default_factory=dict)

    def input_name(self, index: int) -> str:
        """Return a display name for an input, falling back to ``IN n``."""
        name = self.input_names.get(index, "").strip()
        return name or f"IN {index}"

    def output_name(self, index: int) -> str:
        """Return a display name for an output, falling back to ``OUT n``."""
        name = self.output_names.get(index, "").strip()
        return name or f"OUT {index}"

    def source_options(self) -> list[tuple[int, str]]:
        """Return ``[(input_index, unique_label), ...]`` for inputs 1..8.

        Labels use the friendly input name, disambiguated with ``(IN n)`` when
        the same name is shared by more than one input (e.g. several "EMPTY").
        """
        base = {i: self.input_name(i) for i in range(1, MATRIX_SIZE + 1)}
        counts: dict[str, int] = {}
        for name in base.values():
            counts[name] = counts.get(name, 0) + 1
        options: list[tuple[int, str]] = []
        for i in range(1, MATRIX_SIZE + 1):
            label = base[i] if counts[base[i]] == 1 else f"{base[i]} (IN{i})"
            options.append((i, label))
        return options

    def label_for_input(self, index: int) -> str | None:
        """Return the unique source label for a given input index."""
        for idx, label in self.source_options():
            if idx == index:
                return label
        return None

    def input_for_label(self, label: str) -> int | None:
        """Return the input index for a given unique source label."""
        for idx, lbl in self.source_options():
            if lbl == label:
                return idx
        return None

    def edid_options(self) -> list[tuple[int, str]]:
        """Return ``[(mode_index, label), ...]`` of assignable EDID modes."""
        return [
            (idx, label)
            for idx, label in sorted(self.edid_list.items())
            if label.strip().upper() != "END"
        ]

    def edid_label_for_mode(self, mode: int) -> str | None:
        """Return the label for an EDID mode index."""
        label = self.edid_list.get(mode)
        return label if label and label.strip().upper() != "END" else None

    def edid_mode_for_label(self, label: str) -> int | None:
        """Return the EDID mode index for a label."""
        for idx, lbl in self.edid_options():
            if lbl == label:
                return idx
        return None


def _build_command(cmd_type: str, name: str, body: str, **attrs: str) -> str:
    """Build an XML command frame with safely-escaped attribute values."""
    parts = [f"<command type={quoteattr(cmd_type)} name={quoteattr(name)}"]
    for key, value in attrs.items():
        parts.append(f" {key}={quoteattr(str(value))}")
    parts.append(f">{body}</command>")
    return "".join(parts)


class PureLinkClient:
    """Manage a single authenticated WebSocket to a UX-8800."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        username: str,
        password: str,
        *,
        port: int = DEFAULT_WS_PORT,
    ) -> None:
        """Initialise the client. ``session`` should be HA's shared session."""
        self._session = session
        self._host = host
        self._username = username
        self._password = password
        self._port = port
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._send_lock = asyncio.Lock()
        self._conn_lock = asyncio.Lock()
        self._waiters: dict[str, list[asyncio.Future[None]]] = {}
        self.state = MatrixState()

    @property
    def host(self) -> str:
        """Return the configured host."""
        return self._host

    @property
    def uri(self) -> str:
        """Return the WebSocket URI."""
        return f"ws://{self._host}:{self._port}"

    @property
    def connected(self) -> bool:
        """Return whether a live, authenticated socket is available."""
        return (
            self._ws is not None
            and not self._ws.closed
            and self.state.connected
        )

    # -- connection lifecycle -------------------------------------------------

    async def async_ensure_connected(self) -> None:
        """Connect + authenticate + hydrate if not already connected."""
        if self.connected:
            return
        async with self._conn_lock:
            if self.connected:
                return
            await self._async_connect_locked()

    async def _async_connect_locked(self) -> None:
        await self._async_teardown()
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT):
                ws = await self._session.ws_connect(self.uri)
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as err:
            raise CannotConnect(f"Cannot connect to {self.uri}: {err}") from err

        try:
            # 1) Greeting: the device sends <Update name='connected'> on connect.
            await self._handshake_receive(ws)
            # 2) Authenticate.
            await ws.send_str(self._build_login())
            result = await self._handshake_receive(ws)
            if (result.get("__name__") != "update") or (
                result.get("result") != "good"
            ):
                await ws.close()
                raise InvalidAuth("Login rejected by device")
        except InvalidAuth:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as err:
            await ws.close()
            raise CannotConnect(f"Handshake failed: {err}") from err

        # Handshake complete: from here on, only the reader touches receive().
        self._ws = ws
        self.state.connected = True
        self._reader_task = asyncio.create_task(self._reader(ws))

        # 3) Hydrate BEFORE any control command, both to populate state and to
        #    "warm" the socket (commands right after login can be dropped).
        try:
            await self.async_request_all()
            await self.async_refresh_info()
            await self.async_refresh_presets()
            await self.async_refresh_edid()
            await self.async_refresh_volume()
            await self._async_refresh_versions()
        except PureLinkError:
            await self._async_teardown()
            raise

    def _build_login(self) -> str:
        return _build_command(
            "inquery",
            "login",
            "login",
            id=self._username,
            **{"pass": self._password},
        )

    async def _handshake_receive(self, ws: aiohttp.ClientWebSocketResponse) -> dict[str, str]:
        """Receive and parse one frame during the pre-reader handshake.

        Only used before the reader loop starts; a timeout here discards the
        whole socket, so cancelling the receive is acceptable.
        """
        async with asyncio.timeout(HANDSHAKE_TIMEOUT):
            msg = await ws.receive()
        if msg.type is not aiohttp.WSMsgType.TEXT:
            raise CannotConnect(f"Unexpected frame during handshake: {msg.type}")
        return self._parse_frame(msg.data)

    async def async_disconnect(self) -> None:
        """Cleanly close the connection (used on unload)."""
        async with self._conn_lock:
            await self._async_teardown()

    async def _async_teardown(self) -> None:
        self.state.connected = False
        ws = self._ws
        self._ws = None
        if ws is not None and not ws.closed:
            # Clean close makes the reader's ``async for`` end (no cancel).
            try:
                await ws.close()
            except Exception:  # noqa: BLE001 - best effort during teardown
                _LOGGER.debug("Error closing websocket", exc_info=True)
        task = self._reader_task
        self._reader_task = None
        if task is not None:
            try:
                # ws.close() above makes the reader's `async for` end on its own;
                # wait_for is just a safety net for a stuck reader.
                await asyncio.wait_for(task, timeout=5)
            except asyncio.TimeoutError:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            except Exception:  # noqa: BLE001 - CancelledError (our own) propagates
                _LOGGER.debug("Reader task ended with error", exc_info=True)
        self._fail_waiters(CannotConnect("Disconnected"))

    # -- reader loop ----------------------------------------------------------

    async def _reader(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        """Single consumer of ``ws.receive()`` — never wrapped in a cancel."""
        try:
            async for msg in ws:
                if msg.type is aiohttp.WSMsgType.TEXT:
                    try:
                        self._dispatch(self._parse_frame(msg.data))
                    except Exception:  # noqa: BLE001 - never kill the loop on one bad frame
                        _LOGGER.debug("Failed to handle frame", exc_info=True)
                elif msg.type in (
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSING,
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                ):
                    break
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Reader loop terminated", exc_info=True)
        finally:
            self.state.connected = False
            self._fail_waiters(CannotConnect("Connection closed"))

    # -- frame parsing / dispatch --------------------------------------------

    @staticmethod
    def _parse_frame(data: str) -> dict[str, str]:
        """Parse a device frame into a flat dict of attrs + ``__name__``/``__text__``.

        Uses defusedxml because the device's ``setting`` frames echo cleartext
        account passwords and we never want that expanded/entity-exploded.
        """
        root = xml_fromstring(data)
        parsed: dict[str, str] = {str(k): str(v) for k, v in root.attrib.items()}
        parsed["__name__"] = str(parsed.get("name", ""))
        parsed["__text__"] = (root.text or "").strip()
        return parsed

    def _dispatch(self, frame: Mapping[str, str]) -> None:
        name = frame.get("__name__", "")
        state = self.state

        if name == "setall":
            self._apply_setall(frame)
            self._resolve("setall")
        elif name == "GetOut":
            out = _as_int(frame.get("id"))
            src = _as_int(frame.get("__text__"))
            if out is not None and src is not None:
                state.routing[out] = src
        elif name == "ResetOut":
            # Old input for this output is being cleared before a re-route.
            out = _as_int(frame.get("id"))
            if out is not None:
                state.routing[out] = INPUT_NONE
        elif name == "SetChanel":
            self._apply_channels(frame.get("__text__", ""))
        elif name == "SetName":
            self._apply_setname(frame)
        elif name == "MasterVolume":
            vol = _as_int(frame.get("__text__"))
            if vol is not None:
                state.master_volume = vol
            self._resolve("volume")
        elif name == "update":
            # The "update" name is overloaded; disambiguate by attributes.
            if "result" in frame:  # login ack (normally consumed in handshake)
                self._resolve("login")
            elif any(k.startswith("presetname") for k in frame):
                self._apply_presets(frame)
                self._resolve("preset")
            elif any(k.startswith("edidlist") for k in frame):
                self._apply_edid(frame)
                self._resolve("edid")
            elif any(k.endswith("data1") for k in frame):  # inNdata1 / outNdata1
                self._apply_info(frame)
                self._resolve("info")
            elif "dhcp" in frame:
                self._apply_setting(frame)
                self._resolve("setting")
        elif name == "connected":
            pass  # greeting only

    def _apply_setall(self, frame: Mapping[str, str]) -> None:
        state = self.state
        for i in range(1, MATRIX_SIZE + 1):
            src = _as_int(frame.get(f"out{i}"))
            if src is not None:
                state.routing[i] = src
            if (iname := frame.get(f"inname{i}")) is not None:
                state.input_names[i] = iname
            if (oname := frame.get(f"outname{i}")) is not None:
                state.output_names[i] = oname

    def _apply_channels(self, text: str) -> None:
        # Compact form: "I01O01,I02O02,..." (one In->Out pair per output).
        for pair in text.split(","):
            pair = pair.strip()
            if len(pair) >= 6 and pair[0] == "I" and pair[3] == "O":
                src = _as_int(pair[1:3])
                out = _as_int(pair[4:6])
                if out is not None and src is not None:
                    self.state.routing[out] = src

    def _apply_setname(self, frame: Mapping[str, str]) -> None:
        kind = frame.get("kind")
        idx = _as_int(frame.get("id"))
        data = frame.get("data", "")
        if idx is None:
            return
        if kind == "input":
            self.state.input_names[idx] = data
        elif kind == "output":
            self.state.output_names[idx] = data

    def _apply_presets(self, frame: Mapping[str, str]) -> None:
        for i in range(1, PRESET_COUNT + 1):
            if (pname := frame.get(f"presetname{i}")) is not None:
                self.state.preset_names[i] = pname
            if (pdata := frame.get(f"presetdata{i}")) is not None:
                self.state.preset_data[i] = pdata
        # Preset frames also carry the current in/out names.
        self._apply_names_only(frame)

    def _apply_names_only(self, frame: Mapping[str, str]) -> None:
        for i in range(1, MATRIX_SIZE + 1):
            if (iname := frame.get(f"inname{i}")) is not None:
                self.state.input_names[i] = iname
            if (oname := frame.get(f"outname{i}")) is not None:
                self.state.output_names[i] = oname

    def _apply_info(self, frame: Mapping[str, str]) -> None:
        state = self.state
        for i in range(1, MATRIX_SIZE + 1):
            res = frame.get(f"in{i}data1")
            if res is not None:
                state.input_signal[i] = res.strip().lower() != "no signal"
                state.input_resolution[i] = res
            hdcp = frame.get(f"in{i}data2")
            if hdcp is not None:
                state.input_hdcp[i] = hdcp
            sync = frame.get(f"out{i}data2")
            if sync is not None:
                state.output_sync[i] = sync
        self._apply_names_only(frame)

    def _apply_setting(self, frame: Mapping[str, str]) -> None:
        # SECURITY: never log this frame — it echoes account passwords.
        if (ver := frame.get("vercontroller")) is not None:
            self.state.sw_version = ver
        if (web := frame.get("verwebui")) is not None:
            self.state.web_version = web

    def _apply_edid(self, frame: Mapping[str, str]) -> None:
        # edidlist<N> are assignable modes (an "END" entry marks the terminator);
        # edid<1..8> is the current EDID description per input.
        for key, label in frame.items():
            if key.startswith("edidlist") and key[8:].isdigit():
                if label.strip().upper() == "END":
                    continue
                self.state.edid_list[int(key[8:])] = label
        for j in range(1, MATRIX_SIZE + 1):
            if (cur := frame.get(f"edid{j}")) is not None:
                self.state.edid_current[j] = cur
        self._apply_names_only(frame)

    # -- request/response correlation ----------------------------------------

    def _resolve(self, key: str) -> None:
        # Resolve exactly ONE waiter (FIFO) per matching frame so overlapping
        # requests (e.g. a poll and a route's verify readback) each consume their
        # own response instead of both latching onto the first frame (which could
        # be a pre-command snapshot).
        waiters = self._waiters.get(key)
        if not waiters:
            return
        fut = waiters.pop(0)
        if not waiters:
            self._waiters.pop(key, None)
        if not fut.done():
            fut.set_result(None)

    def _fail_waiters(self, err: Exception) -> None:
        for futs in list(self._waiters.values()):
            for fut in futs:
                if not fut.done():
                    fut.set_exception(err)
        self._waiters.clear()

    async def _send(self, payload: str) -> None:
        ws = self._ws
        if ws is None or ws.closed:
            raise CannotConnect("Not connected")
        async with self._send_lock:
            try:
                await ws.send_str(payload)
            except (aiohttp.ClientError, ConnectionError) as err:
                raise CannotConnect(f"Send failed: {err}") from err

    async def _request(self, key: str, payload: str) -> None:
        """Send ``payload`` and wait for the reader to see a ``key`` response.

        The timeout wraps the *future await*, never the socket receive, so a slow
        response never aborts the connection.
        """
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[None] = loop.create_future()
        self._waiters.setdefault(key, []).append(fut)
        try:
            await self._send(payload)
            async with asyncio.timeout(RESPONSE_TIMEOUT):
                await fut
        except asyncio.TimeoutError as err:
            raise CannotConnect(f"Timed out waiting for '{key}' response") from err
        finally:
            waiters = self._waiters.get(key)
            if waiters and fut in waiters:
                waiters.remove(fut)

    # -- high-level commands --------------------------------------------------

    async def async_request_all(self) -> None:
        """Fetch the authoritative routing + names snapshot."""
        await self._request(
            "setall", "<command type='inquery' name='requestall_main'>main</command>"
        )

    async def async_refresh_info(self) -> None:
        """Fetch per-input signal/HDCP and per-output sync diagnostics."""
        await self._request(
            "info", "<command type='inquery' name='info'>info</command>"
        )

    async def async_refresh_presets(self) -> None:
        """Fetch the preset table (names + routing data)."""
        await self._request(
            "preset", "<command type='inquery' name='preset'>preset</command>"
        )

    async def async_refresh_volume(self) -> None:
        """Fetch the (read-only) master volume."""
        await self._request(
            "volume", "<command type='inquery' name='MasterVolume'>main</command>"
        )

    async def async_refresh_edid(self) -> None:
        """Fetch the EDID mode list and current per-input EDID descriptions."""
        await self._request(
            "edid", "<command type='inquery' name='edid'>edid</command>"
        )

    async def _async_refresh_versions(self) -> None:
        """Fetch firmware versions once (from the sensitive ``setting`` frame)."""
        try:
            await self._request(
                "setting", "<command type='inquery' name='setting'>setting</command>"
            )
        except PureLinkError:
            # Non-fatal: versions are cosmetic.
            _LOGGER.debug("Could not fetch device versions")

    async def async_route(self, output: int, source: int) -> None:
        """Route ``output`` <- ``source`` (0 = disconnect), verify, and retry.

        The device can silently drop a command, so we confirm via an
        authoritative ``requestall_main`` readback and resend if needed.
        """
        if not 1 <= output <= MATRIX_SIZE:
            raise ValueError(f"output out of range: {output}")
        if not 0 <= source <= MATRIX_SIZE:
            raise ValueError(f"source out of range: {source}")

        payload = f"<command type='update' name='GetOut' id='{output}'>{source}</command>"
        last_seen: int | None = None
        for attempt in range(1, ROUTE_MAX_ATTEMPTS + 1):
            await self._send(payload)
            self.state.routing[output] = source  # optimistic
            await asyncio.sleep(ROUTE_SETTLE)
            await self.async_request_all()  # authoritative readback
            last_seen = self.state.routing.get(output)
            if last_seen == source:
                return
            _LOGGER.debug(
                "Route OUT%s->IN%s not confirmed (got IN%s), attempt %s/%s",
                output,
                source,
                last_seen,
                attempt,
                ROUTE_MAX_ATTEMPTS,
            )
        raise PureLinkError(
            f"Failed to route OUT{output}->IN{source} after "
            f"{ROUTE_MAX_ATTEMPTS} attempts (device reports IN{last_seen})"
        )

    async def async_route_all(self, source: int) -> None:
        """Route every output to ``source``."""
        for out in range(1, MATRIX_SIZE + 1):
            await self.async_route(out, source)

    async def async_recall_preset(self, slot: int) -> None:
        """Recall preset ``slot`` (1..20), then refresh routing."""
        if not 1 <= slot <= PRESET_COUNT:
            raise ValueError(f"preset slot out of range: {slot}")
        await self._send(
            f"<command type='update' name='callpreset' presetid='{slot}'>preset</command>"
        )
        await asyncio.sleep(ROUTE_SETTLE)
        await self.async_request_all()

    async def async_set_name(self, kind: str, index: int, name: str) -> None:
        """Rename an ``input`` or ``output`` (device limit: 8 characters)."""
        if kind not in ("input", "output"):
            raise ValueError(f"kind must be input/output: {kind}")
        if not 1 <= index <= MATRIX_SIZE:
            raise ValueError(f"index out of range: {index}")
        trimmed = name[:MAX_NAME_LEN]
        await self._send(
            _build_command(
                "update", "GetNames", "temp", data=trimmed, kind=kind, id=str(index)
            )
        )
        await asyncio.sleep(ROUTE_SETTLE)
        await self.async_request_all()

    async def async_set_edid(self, input_index: int, mode: int) -> None:
        """Assign EDID ``mode`` to ``input_index`` (1..8).

        The web UI wraps a raw ASCII command inside ``senddata``:
        ``*777EL{mode:02d}I{input:02d}!``. We then trigger an ``edid_refresh``
        and re-read the EDID table.
        """
        if not 1 <= input_index <= MATRIX_SIZE:
            raise ValueError(f"input out of range: {input_index}")
        if mode not in self.state.edid_list:
            raise ValueError(f"unknown EDID mode: {mode}")
        sdata = f"*777EL{mode:02d}I{input_index:02d}!"
        await self._send(_build_command("update", "senddata", "temp", data=sdata))
        await asyncio.sleep(ROUTE_SETTLE)
        await self._send(
            f"<command type='update' name='edid_refresh' "
            f"id='{input_index:02d}'>temp</command>"
        )
        await asyncio.sleep(ROUTE_SETTLE)
        await self.async_refresh_edid()

    async def async_save_preset(
        self, slot: int, name: str, routing: Mapping[int, int] | None = None
    ) -> None:
        """Save a preset. The device saves all 20 slots at once, so we
        read-modify-write the whole table from current state.
        """
        if not 1 <= slot <= PRESET_COUNT:
            raise ValueError(f"preset slot out of range: {slot}")
        # The device saves all 20 slots at once, so refresh first to avoid
        # clobbering the other 19 with a stale cache (presets are not polled).
        await self.async_refresh_presets()
        if routing is None:
            routing = dict(self.state.routing)
        data = ",".join(
            f"I{routing.get(out, 0):02d}O{out:02d}" for out in range(1, MATRIX_SIZE + 1)
        )

        names = dict(self.state.preset_names)
        datas = dict(self.state.preset_data)
        names[slot] = name[:MAX_NAME_LEN]
        datas[slot] = data

        attrs: dict[str, str] = {}
        for i in range(1, PRESET_COUNT + 1):
            attrs[f"presetname{i}"] = names.get(i, f"preset{i}")
            attrs[f"presetdata{i}"] = datas.get(
                i, ",".join(f"I00O{o:02d}" for o in range(1, MATRIX_SIZE + 1))
            )
        await self._send(_build_command("update", "updatepreset", "preset", **attrs))
        await asyncio.sleep(ROUTE_SETTLE)
        await self.async_refresh_presets()


def _as_int(value: str | None) -> int | None:
    """Parse an int, tolerating whitespace and non-numeric device values."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None
