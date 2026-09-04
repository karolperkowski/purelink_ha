"""Fixtures for PureLink UX-8800 tests."""

from __future__ import annotations

import socket
import sys

if sys.platform == "win32":
    # pytest-homeassistant-custom-component disables socket creation via
    # pytest_socket.disable_socket(allow_unix_socket=True). On Windows there is
    # no AF_UNIX, so asyncio's internal loopback socket.socketpair() (needed to
    # construct every event loop) gets blocked, erroring all tests with
    # SocketBlockedError. Wrap socketpair() so it briefly uses the real socket
    # class — equivalent to what allow_unix_socket already permits on Linux.
    import pytest_socket

    _orig_socketpair = socket.socketpair

    def _unblocked_socketpair(*args, **kwargs):
        saved = socket.socket
        socket.socket = pytest_socket._true_socket
        try:
            return _orig_socketpair(*args, **kwargs)
        finally:
            socket.socket = saved

    socket.socketpair = _unblocked_socketpair

    # aiodns (used by HA's aiohttp client session) requires a SelectorEventLoop
    # on Windows, but HA's test plugin installs a Proactor-based policy and
    # no-ops asyncio.set_event_loop_policy. Point the installed policy's loop
    # factory at SelectorEventLoop instead so every per-test loop is a selector
    # loop.
    import asyncio

    asyncio.get_event_loop_policy()._loop_factory = asyncio.SelectorEventLoop

# pycares (pulled in via aiodns for HA's aiohttp client session) lazily starts
# a permanent daemon thread the first time a DNS channel is destroyed. If that
# happens mid-test, the HA plugin's verify_cleanup fixture fails the test for
# the "lingering" thread. Start it up-front so it is part of the baseline
# thread set for every test.
try:
    import pycares

    pycares._shutdown_manager.start()
except (ImportError, AttributeError):  # pragma: no cover - depends on version
    pass

# Back-port shim: the platforms annotate async_setup_entry with
# AddConfigEntryEntitiesCallback, which was only added in HA 2025.3, while the
# newest pytest-homeassistant-custom-component installable on Python 3.12
# bundles HA 2025.1.4 (later releases require Python 3.13). The name is a pure
# typing alias, so alias it to AddEntitiesCallback on older HA so the platform
# modules import cleanly.
import homeassistant.helpers.entity_platform as _entity_platform

if not hasattr(_entity_platform, "AddConfigEntryEntitiesCallback"):
    _entity_platform.AddConfigEntryEntitiesCallback = (
        _entity_platform.AddEntitiesCallback
    )

# Same story for homeassistant.helpers.device_info: the module was introduced
# after HA 2025.1; DeviceInfo lives in homeassistant.helpers.device_registry
# there. Register a stand-in module exposing the same class.
try:
    import homeassistant.helpers.device_info  # noqa: F401
except ImportError:  # pragma: no cover - depends on HA version
    import types

    import homeassistant.helpers as _helpers
    from homeassistant.helpers.device_registry import DeviceInfo as _DeviceInfo

    _device_info_mod = types.ModuleType("homeassistant.helpers.device_info")
    _device_info_mod.DeviceInfo = _DeviceInfo
    sys.modules["homeassistant.helpers.device_info"] = _device_info_mod
    _helpers.device_info = _device_info_mod

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME

from custom_components.purelink_ux8800.client import MatrixState
from custom_components.purelink_ux8800.const import DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom integration in every test."""
    yield


def _sample_state() -> MatrixState:
    """A representative populated state matching the real device."""
    state = MatrixState(connected=True, sw_version="UX-8800-CT-V1.4.2")
    state.routing = {1: 1, 2: 1, 3: 1, 4: 2, 5: 1, 6: 1, 7: 1, 8: 1}
    state.output_names = {1: "TV1", 2: "TV2", 3: "PROJ", 4: "2R-2", 8: "ENCODER"}
    state.input_names = {1: "CABLE", 2: "BUZZTV", 3: "PROTECT", 4: "LAPTOP"}
    state.preset_names = {1: "CABLE", 20: "BAR TALK"}
    state.input_signal = {1: True, 2: True, 3: True, 4: False}
    state.master_volume = 10
    return state


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """A configured entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="PureLink UX-8800",
        unique_id="aa:bb:cc:dd:ee:ff",
        data={
            CONF_HOST: "192.168.11.9",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "coldbeer",
        },
    )


@pytest.fixture
def mock_client() -> Generator[MagicMock]:
    """Patch PureLinkClient with a mock exposing sample state."""
    with patch(
        "custom_components.purelink_ux8800.PureLinkClient", autospec=True
    ) as client_cls:
        client = client_cls.return_value
        client.host = "192.168.11.9"
        client.state = _sample_state()
        client.async_ensure_connected = AsyncMock()
        client.async_request_all = AsyncMock()
        client.async_refresh_info = AsyncMock()
        client.async_refresh_volume = AsyncMock()
        client.async_route = AsyncMock()
        client.async_recall_preset = AsyncMock()
        client.async_disconnect = AsyncMock()
        yield client
