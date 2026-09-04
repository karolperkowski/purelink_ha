"""Tests for the UX-8800 coordinator's external route-change events."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant

from custom_components.purelink_ux8800.const import (
    ATTR_INPUT,
    ATTR_INPUT_NAME,
    ATTR_OUTPUT,
    ATTR_OUTPUT_NAME,
    ATTR_PREVIOUS_INPUT,
    ATTR_PREVIOUS_INPUT_NAME,
    EVENT_ROUTE_CHANGED,
)

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)


async def _setup_entry(hass: HomeAssistant, entry: MockConfigEntry):
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry.runtime_data


async def test_external_route_change_fires_event(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
) -> None:
    """A routing change seen only via polling fires a route_changed event."""
    coordinator = await _setup_entry(hass, mock_config_entry)
    events = async_capture_events(hass, EVENT_ROUTE_CHANGED)

    # Someone at the front panel / web UI moves OUT3 from IN1 to IN4.
    mock_client.state.routing[3] = 4
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(events) == 1
    data = events[0].data
    assert data[ATTR_OUTPUT] == 3
    assert data[ATTR_OUTPUT_NAME] == "PROJ"
    assert data[ATTR_INPUT] == 4
    assert data[ATTR_INPUT_NAME] == "LAPTOP"
    assert data[ATTR_PREVIOUS_INPUT] == 1
    assert data[ATTR_PREVIOUS_INPUT_NAME] == "CABLE"
    assert data["entry_id"] == mock_config_entry.entry_id
    assert data["device_id"] is not None

    # No repeat event for an unchanged snapshot.
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert len(events) == 1


async def test_external_disconnect_fires_event_without_input_name(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
) -> None:
    """Disconnecting an output externally reports input 0 with no name."""
    coordinator = await _setup_entry(hass, mock_config_entry)
    events = async_capture_events(hass, EVENT_ROUTE_CHANGED)

    mock_client.state.routing[1] = 0
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(events) == 1
    data = events[0].data
    assert data[ATTR_INPUT] == 0
    assert data[ATTR_INPUT_NAME] is None


async def test_ha_route_does_not_fire_event(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
) -> None:
    """Routing through Home Assistant must not be reported as external."""
    coordinator = await _setup_entry(hass, mock_config_entry)
    events = async_capture_events(hass, EVENT_ROUTE_CHANGED)

    async def fake_route(output: int, source: int) -> None:
        mock_client.state.routing[output] = source

    mock_client.async_route.side_effect = fake_route
    await coordinator.async_route(2, 3)
    await hass.async_block_till_done()

    # Neither the command itself nor the next poll fires an event.
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert events == []
