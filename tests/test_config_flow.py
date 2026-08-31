"""Config-flow tests for the PureLink UX-8800 integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.purelink_ux8800.client import CannotConnect, InvalidAuth
from custom_components.purelink_ux8800.const import DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry

USER_INPUT = {
    CONF_HOST: "192.168.11.9",
    CONF_USERNAME: "admin",
    CONF_PASSWORD: "coldbeer",
}


@pytest.fixture
def mock_validate():
    """Patch the client connect + MAC lookup used during validation."""
    with (
        patch(
            "custom_components.purelink_ux8800.config_flow.PureLinkClient",
            autospec=True,
        ) as client_cls,
        patch(
            "custom_components.purelink_ux8800.config_flow._get_mac",
            return_value="AA:BB:CC:DD:EE:FF",
        ),
    ):
        client = client_cls.return_value
        client.async_ensure_connected = AsyncMock()
        client.async_disconnect = AsyncMock()
        yield client


async def test_user_flow_success(hass: HomeAssistant, mock_validate) -> None:
    """A valid host + credentials creates an entry with a MAC unique_id."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "aa:bb:cc:dd:ee:ff"
    assert result["data"] == USER_INPUT


async def test_user_flow_invalid_auth(hass: HomeAssistant, mock_validate) -> None:
    """Bad credentials surface an invalid_auth error."""
    mock_validate.async_ensure_connected.side_effect = InvalidAuth
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_cannot_connect(hass: HomeAssistant, mock_validate) -> None:
    """An unreachable host surfaces a cannot_connect error."""
    mock_validate.async_ensure_connected.side_effect = CannotConnect
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_already_configured(hass: HomeAssistant, mock_validate) -> None:
    """A second entry for the same device aborts."""
    MockConfigEntry(
        domain=DOMAIN, unique_id="aa:bb:cc:dd:ee:ff", data=USER_INPUT
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
