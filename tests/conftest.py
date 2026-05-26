"""Shared pytest fixtures for purelink_ha tests.

Intentionally empty: the current tests under tests/test_purelink_client.py
are pure unit tests on the protocol parser and command templates — they
don't need a HomeAssistant fixture.

Add the pytest-homeassistant-custom-component plugin back here when we
add integration-level tests (config flow, coordinator end-to-end, etc.):

    pytest_plugins = ["pytest_homeassistant_custom_component"]

    @pytest.fixture(autouse=True)
    def auto_enable_custom_integrations(enable_custom_integrations):
        yield
"""

from __future__ import annotations
