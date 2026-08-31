from __future__ import annotations

import asyncio
import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_NUM_INPUTS,
    CONF_NUM_OUTPUTS,
    CONF_SWITCHER_ID,
    DEFAULT_PORT,
    DEFAULT_SWITCHER_ID,
    DOMAIN,
)
from .purelink_client import PureLinkClient
from .purelink_names import (
    PureLinkAuthError,
    PureLinkNamesError,
    async_fetch_names,
)

_LOGGER = logging.getLogger(__name__)

# Port counts must be >= 1: a 0 slipping through creates a hub with zero
# entities and no device, silently (observed in the field with a UX-8800).
_PORT_COUNT = vol.All(vol.Coerce(int), vol.Range(min=1, max=64))

_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
        vol.Optional(CONF_SWITCHER_ID, default=DEFAULT_SWITCHER_ID): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=999)
        ),
        # Optional web UI credentials: when provided, the integration reads the
        # user-assigned port names (the Telnet protocol has no names query).
        vol.Optional(CONF_USERNAME, default=""): str,
        vol.Optional(CONF_PASSWORD, default=""): str,
    }
)


def _ports_schema(detected: int) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_NUM_INPUTS, default=detected): _PORT_COUNT,
            vol.Required(CONF_NUM_OUTPUTS, default=detected): _PORT_COUNT,
        }
    )


class PureLinkConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._connection: dict | None = None
        self._detected_outputs: int = 0

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
            detected = 0
            try:
                await client.connect()
                # The status reply enumerates outputs as IxxOyy tokens; the
                # highest output number seen is the port count (robust even if
                # a firmware omits disconnected outputs). UX matrices are
                # square, e.g. UX-4400 = 4x4, UX-8800 = 8x8.
                routing = await client.query_status()
                detected = max(routing, default=0)
            except (
                OSError,
                asyncio.TimeoutError,
                # readuntil() raises IncompleteReadError (an EOFError, not an
                # OSError) when the peer closes before '!', e.g. a wrong port.
                EOFError,
                asyncio.LimitOverrunError,
                ValueError,
            ):
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error probing PureLink switcher")
                errors["base"] = "unknown"
            finally:
                await client.disconnect()

            if not errors and detected < 1:
                # Reply parsed but no outputs enumerated (e.g. fully
                # disconnected matrix on a firmware that omits idle outputs):
                # fall through with the most common size prefilled; the user
                # confirms or corrects it on the next step.
                detected = 8

            # Bad web UI credentials block the flow (certain user error);
            # any other names failure is tolerated here and again at setup.
            username = user_input.get(CONF_USERNAME, "")
            password = user_input.get(CONF_PASSWORD, "")
            if not errors and username and password:
                try:
                    await async_fetch_names(
                        async_get_clientsession(self.hass),
                        user_input[CONF_HOST],
                        username,
                        password,
                    )
                except PureLinkAuthError:
                    errors["base"] = "invalid_auth"
                except PureLinkNamesError as err:
                    _LOGGER.warning(
                        "Could not verify web UI credentials (%s); "
                        "continuing without names",
                        err,
                    )

            if not errors:
                await self.async_set_unique_id(
                    f"{user_input[CONF_HOST]}_{user_input[CONF_SWITCHER_ID]}"
                )
                self._abort_if_unique_id_configured()
                self._connection = user_input
                self._detected_outputs = detected
                return await self.async_step_ports()

        return self.async_show_form(
            step_id="user",
            data_schema=_USER_SCHEMA,
            errors=errors,
        )

    async def async_step_ports(
        self, user_input: dict | None = None
    ) -> config_entries.FlowResult:
        assert self._connection is not None

        if user_input is not None:
            data = {**self._connection, **user_input}
            return self.async_create_entry(
                title=f"PureLink ({data[CONF_HOST]})",
                data=data,
            )

        return self.async_show_form(
            step_id="ports",
            data_schema=_ports_schema(self._detected_outputs),
            description_placeholders={"detected": str(self._detected_outputs)},
        )
