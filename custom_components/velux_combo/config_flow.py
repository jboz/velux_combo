"""Config flow for the Velux Combo integration."""

from __future__ import annotations

import hashlib
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector

from .const import CONF_STORE_ENTITY, CONF_WINDOW_ENTITY, DOMAIN

COVER_ENTITY_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="cover")
)

SCHEMA = vol.Schema(
    {
        vol.Optional("name"): selector.TextSelector(
            selector.TextSelectorConfig()
        ),
        vol.Required(CONF_WINDOW_ENTITY): COVER_ENTITY_SELECTOR,
        vol.Required(CONF_STORE_ENTITY): COVER_ENTITY_SELECTOR,
    }
)


class VeluxComboConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Velux Combo."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: pick a window and its store."""
        errors: dict[str, str] = {}

        if user_input is not None:
            window_entity = user_input[CONF_WINDOW_ENTITY]
            store_entity = user_input[CONF_STORE_ENTITY]
            name = user_input.get("name")

            errors = await self._validate_entities(window_entity, store_entity)

            if not errors:
                unique_id = self._generate_unique_id(window_entity, store_entity)
                await self.async_set_unique_id(unique_id)

                title = name or f"{window_entity} + {store_entity}"
                return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(step_id="user", data_schema=SCHEMA, errors=errors)

    async def _validate_entities(
        self, window_entity: str, store_entity: str
    ) -> dict[str, str]:
        """Check that the two chosen entities are distinct cover entities."""
        errors: dict[str, str] = {}

        for key, entity_id in (
            (CONF_WINDOW_ENTITY, window_entity),
            (CONF_STORE_ENTITY, store_entity),
        ):
            if not entity_id.startswith("cover."):
                errors[key] = "not_cover"
            elif self.hass.states.get(entity_id) is None:
                errors[key] = "unknown_entity"

        if not errors and window_entity == store_entity:
            errors[CONF_STORE_ENTITY] = "same_entity"

        return errors

    @staticmethod
    def _generate_unique_id(window_entity: str, store_entity: str) -> str:
        """Build a stable unique id for a window/store pair."""
        pair = "|".join(sorted((window_entity, store_entity)))
        return hashlib.sha256(pair.encode()).hexdigest()