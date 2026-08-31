"""Unit tests for PureLinkClient command building and response parsing."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.purelink.const import (
    CMD_CONNECT_TEMPLATE,
    CMD_DISCONNECT_TEMPLATE,
    CMD_HEARTBEAT,
    CMD_STATUS_ALL,
)
from custom_components.purelink.purelink_client import PureLinkClient


def _client() -> PureLinkClient:
    return PureLinkClient(host="192.0.2.10", port=23, switcher_id=255)


def _fake_connection(response: bytes) -> tuple[MagicMock, MagicMock]:
    reader = MagicMock()
    reader.readuntil = AsyncMock(return_value=response)
    writer = MagicMock()
    writer.is_closing.return_value = False
    writer.write = MagicMock()
    writer.drain = AsyncMock()
    return reader, writer


def test_command_templates_are_zero_padded() -> None:
    assert CMD_CONNECT_TEMPLATE.format(sid=255, inp=1, out=2) == "*255CI01O02!"
    assert CMD_DISCONNECT_TEMPLATE.format(sid=255, out=4) == "*255CI00O04!"
    assert CMD_HEARTBEAT.format(sid=255) == "*255H000!"
    assert CMD_STATUS_ALL.format(sid=255) == "*255?C!"


def test_parse_status_response_extracts_routing() -> None:
    routing = _client()._parse_status_response("?C I01O01,I02O02,I03O03,I04O04!")
    assert routing == {1: 1, 2: 2, 3: 3, 4: 4}


def test_parse_status_response_handles_extra_whitespace() -> None:
    routing = _client()._parse_status_response("  ?C  I02O01 , I04O03 !")
    assert routing == {1: 2, 3: 4}


def test_parse_status_response_rejects_missing_marker() -> None:
    with pytest.raises(ValueError):
        _client()._parse_status_response("totally invalid response!")


def test_is_success_ack_detects_errors() -> None:
    client = _client()
    assert client._is_success_ack("?C I01O01!") is True
    assert client._is_success_ack("Command Code Error!") is False
    assert client._is_success_ack("Switcher ID Error!") is False
    assert client._is_success_ack("command code error!") is False  # case-insensitive


def test_parse_status_response_handles_ux8800_echo_prefix() -> None:
    # Captured from a UX-8800 (fw CT-V1.4.2): the device echoes "*<sid>s" ahead
    # of the ?C marker.
    routing = _client()._parse_status_response(
        "*255s?CI01O01,I01O02,I01O03,I05O04,I01O05,I01O06,I01O07,I03O08!"
    )
    assert routing == {1: 1, 2: 1, 3: 1, 4: 5, 5: 1, 6: 1, 7: 1, 8: 3}


def test_is_alive_true_on_status_response() -> None:
    client = _client()
    reader, writer = _fake_connection(b"*255s?CI01O01,I02O02!")
    with patch("asyncio.open_connection", AsyncMock(return_value=(reader, writer))):
        assert asyncio.run(client.is_alive()) is True


def test_is_alive_false_on_command_error() -> None:
    # A UX-8800 answers the H000 heartbeat with "Command Code Error"; is_alive
    # must instead succeed via ?C — and report False when even ?C fails.
    client = _client()
    reader, writer = _fake_connection(b"Command Code Error!")
    with patch("asyncio.open_connection", AsyncMock(return_value=(reader, writer))):
        assert asyncio.run(client.is_alive()) is False
