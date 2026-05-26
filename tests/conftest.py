"""Shared pytest fixtures for purelink_ha tests."""

from __future__ import annotations

import pytest

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make the purelink custom integration loadable in all tests."""
    yield
