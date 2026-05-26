from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

from .const import (
    CMD_CONNECT_TEMPLATE,
    CMD_DISCONNECT_ALL,
    CMD_DISCONNECT_TEMPLATE,
    CMD_HEARTBEAT,
    CMD_STATUS_ALL,
    DEFAULT_TIMEOUT,
    RESP_ERROR_COMMAND,
    RESP_ERROR_SWITCHER,
)

_LOGGER = logging.getLogger(__name__)

_STATUS_TOKEN_RE = re.compile(r"I(\d{2,})O(\d{2,})", re.IGNORECASE)


class PureLinkClient:
    def __init__(
        self,
        host: str,
        port: int,
        switcher_id: int,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._host = host
        self._port = port
        self._sid = switcher_id
        self._timeout = timeout
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self._host, self._port),
            timeout=self._timeout,
        )
        _LOGGER.debug("PureLink: connected to %s:%d", self._host, self._port)

    async def disconnect(self) -> None:
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            finally:
                self._writer = None
                self._reader = None

    def _is_connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def _ensure_connected(self) -> None:
        if self._is_connected():
            return
        _LOGGER.debug("PureLink: reconnecting to %s:%d", self._host, self._port)
        await self.connect()

    async def _send_raw(self, command: str) -> str:
        async with self._lock:
            await self._ensure_connected()
            assert self._writer is not None
            assert self._reader is not None
            self._writer.write((command + "\r\n").encode("ascii"))
            await self._writer.drain()
            data = await asyncio.wait_for(
                self._reader.readuntil(b"!"),
                timeout=self._timeout,
            )
            return data.decode("ascii", errors="replace")

    def _is_success_ack(self, raw: str) -> bool:
        raw_upper = raw.upper()
        if RESP_ERROR_COMMAND.upper() in raw_upper:
            return False
        if RESP_ERROR_SWITCHER.upper() in raw_upper:
            return False
        return True

    def _parse_status_response(self, raw: str) -> dict[int, int]:
        inner = raw.strip().rstrip("!")
        idx = inner.upper().find("?C")
        if idx == -1:
            raise ValueError(f"Unexpected status response: {raw!r}")
        payload = inner[idx + 2:]
        routing: dict[int, int] = {}
        for token in payload.split(","):
            m = _STATUS_TOKEN_RE.match(token.strip())
            if m:
                inp, out = int(m.group(1)), int(m.group(2))
                routing[out] = inp
        return routing

    async def heartbeat(self) -> bool:
        try:
            cmd = CMD_HEARTBEAT.format(sid=self._sid)
            raw = await self._send_raw(cmd)
            return self._is_success_ack(raw)
        except Exception as err:
            _LOGGER.debug("PureLink heartbeat failed: %s", err)
            return False

    async def query_status(self) -> dict[int, int]:
        cmd = CMD_STATUS_ALL.format(sid=self._sid)
        raw = await self._send_raw(cmd)
        return self._parse_status_response(raw)

    async def connect_input_to_output(self, input_num: int, output_num: int) -> bool:
        cmd = CMD_CONNECT_TEMPLATE.format(sid=self._sid, inp=input_num, out=output_num)
        raw = await self._send_raw(cmd)
        ok = self._is_success_ack(raw)
        if not ok:
            _LOGGER.warning("PureLink connect I%02d→O%02d failed: %s", input_num, output_num, raw.strip())
        return ok

    async def disconnect_output(self, output_num: int) -> bool:
        cmd = CMD_DISCONNECT_TEMPLATE.format(sid=self._sid, out=output_num)
        raw = await self._send_raw(cmd)
        ok = self._is_success_ack(raw)
        if not ok:
            _LOGGER.warning("PureLink disconnect O%02d failed: %s", output_num, raw.strip())
        return ok

    async def disconnect_all(self) -> bool:
        cmd = CMD_DISCONNECT_ALL.format(sid=self._sid)
        raw = await self._send_raw(cmd)
        return self._is_success_ack(raw)
