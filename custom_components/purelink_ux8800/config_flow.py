"""Config flow for the PureLink UX-8800 integration."""

from __future__ import annotations

import logging
from functools import partial
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac

from .client import CannotConnect, InvalidAuth, PureLinkClient
from .const import (
    CONF_INFO_INTERVAL,
    CONF_POLL_INTERVAL,
    DEFAULT_INFO_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_USERNAME,
    DOMAIN,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
)
from .coordinator import PureLinkConfigEntry

_LOGGER = logging.getLogger(__name__)

TITLE = "PureLink UX-8800"


async def _validate(hass, data: dict[str, Any]) -> tuple[str, bool]:
    """Validate credentials against the device and derive a unique id.

    Returns ``(unique_id, from_mac)``. ``from_mac`` is True when the id is a
    resolved MAC address (confident) and False when it fell back to the host
    (getmac could not resolve one). Raises CannotConnect / InvalidAuth on failure.
    """
    session = async_get_clientsession(hass)
    client = PureLinkClient(
        session, data[CONF_HOST], data[CONF_USERNAME], data[CONF_PASSWORD]
    )
    try:
        await client.async_ensure_connected()
    finally:
        await client.async_disconnect()

    # The device exposes no serial/MAC over its protocol, so resolve the host's
    # MAC via ARP (only reliable on the same subnet). Fall back to the host.
    mac = await hass.async_add_executor_job(partial(_get_mac, data[CONF_HOST]))
    if mac:
        return format_mac(mac), True
    return data[CONF_HOST].lower(), False


def _get_mac(host: str) -> str | None:
    """Resolve a MAC address for the host (blocking; run in executor)."""
    try:
        from getmac import get_mac_address

        return get_mac_address(ip=host)
    except Exception:  # noqa: BLE001 - getmac is best-effort
        return None


def _schema(
    *, host: str = "", username: str = DEFAULT_USERNAME, include_host: bool = True
) -> vol.Schema:
    fields: dict[Any, Any] = {}
    if include_host:
        fields[vol.Required(CONF_HOST, default=host)] = str
    fields[vol.Required(CONF_USERNAME, default=username)] = str
    fields[vol.Required(CONF_PASSWORD)] = str
    return vol.Schema(fields)


class PureLinkConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PureLink UX-8800."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                unique_id, _ = await _validate(self.hass, user_input)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error validating UX-8800")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured(
                    updates={CONF_HOST: user_input[CONF_HOST]}
                )
                return self.async_create_entry(title=TITLE, data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=_schema(), errors=errors
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication when credentials stop working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm new credentials."""
        errors: dict[str, str] = {}
        reauth_entry: PureLinkConfigEntry = self._get_reauth_entry()
        if user_input is not None:
            data = {**reauth_entry.data, **user_input}
            try:
                await _validate(self.hass, data)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during reauth")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(reauth_entry, data=data)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_schema(
                username=reauth_entry.data.get(CONF_USERNAME, DEFAULT_USERNAME),
                include_host=False,
            ),
            errors=errors,
            description_placeholders={CONF_HOST: reauth_entry.data[CONF_HOST]},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle changing host/credentials of an existing entry."""
        errors: dict[str, str] = {}
        entry: PureLinkConfigEntry = self._get_reconfigure_entry()
        if user_input is not None:
            data = {**entry.data, **user_input}
            try:
                unique_id, from_mac = await _validate(self.hass, data)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during reconfigure")
                errors["base"] = "unknown"
            else:
                # Only guard against pointing at a *different* physical unit when
                # we have a confident MAC id on both sides. A transient getmac
                # miss must not raise a false 'wrong_device' for the same device.
                entry_is_mac = bool(entry.unique_id) and ":" in (entry.unique_id or "")
                if from_mac and entry_is_mac:
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data=data)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_schema(
                host=entry.data[CONF_HOST],
                username=entry.data.get(CONF_USERNAME, DEFAULT_USERNAME),
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: PureLinkConfigEntry,
    ) -> PureLinkOptionsFlow:
        """Return the options flow."""
        return PureLinkOptionsFlow()


class PureLinkOptionsFlow(OptionsFlow):
    """Handle polling-interval options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_POLL_INTERVAL,
                    default=options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_POLL_INTERVAL, max=MAX_POLL_INTERVAL)),
                vol.Optional(
                    CONF_INFO_INTERVAL,
                    default=options.get(CONF_INFO_INTERVAL, DEFAULT_INFO_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_POLL_INTERVAL, max=300)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
