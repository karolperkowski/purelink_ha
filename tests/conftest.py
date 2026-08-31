"""Fixtures for PureLink UX-8800 tests."""

from __future__ import annotations

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
