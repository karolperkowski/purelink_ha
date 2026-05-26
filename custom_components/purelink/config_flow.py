from __future__ import annotations

import asyncio
import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT

from .const import (
    CONF_NUM_INPUTS,
    CONF_NUM_OUTPUTS,
    CONF_SWITCHER_ID,
    DEFAULT_PORT,
    DEFAULT_SWITCHER_ID,
    DOMAIN,
)
from .purelink_client import PureLinkClient

_LOGGER = logging.getLogger(__name__)

_STEP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_SWITCHER_ID, default=DEFAULT_SWITCHER_ID): int,
        vol.Required(CONF_NUM_INPUTS): int,
        vol.Required(CONF_NUM_OUTPUTS): int,
    }
)


class PureLinkConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            client = PureLinkClient(
                user_input[CONF_HOST],
                user_input[CONF_PORT],
                user_input[CONF_SWITCHER_ID],
            )
            try:
                await client.connect()
                ok = await client.heartbeat()
                await client.disconnect()
            except (OSError, asyncio.TimeoutError):
                errors["base"] = "cannot_connect"
            else:
                if not ok:
                    errors["base"] = "cannot_connect"

            if not errors:
                await self.async_set_unique_id(
                    f"{user_input[CONF_HOST]}_{user_input[CONF_SWITCHER_ID]}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"PureLink ({user_input[CONF_HOST]})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_STEP_SCHEMA,
            errors=errors,
        )
