"""Unit tests for PureLinkClient command building and response parsing."""

from __future__ import annotations

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
