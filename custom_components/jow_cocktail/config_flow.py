"""Config flow de l'intégration Jow Cocktail."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_AI_ENTITY,
    CONF_PREFERENCES,
    CONF_WEATHER_ENTITY,
    DEFAULT_COVERS,
    DOMAIN,
)


class JowCocktailConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            name = user_input.get("name", "Jow Cocktail").strip() or "Jow Cocktail"
            await self.async_set_unique_id(f"{DOMAIN}_{name.lower()}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=name,
                data={"name": name},
                options={
                    "covers": user_input["covers"],
                    CONF_PREFERENCES: user_input.get(CONF_PREFERENCES, ""),
                    CONF_AI_ENTITY: user_input.get(CONF_AI_ENTITY, ""),
                    CONF_WEATHER_ENTITY: user_input.get(CONF_WEATHER_ENTITY, ""),
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default="Jow Cocktail"): cv.string,
                    vol.Required("covers", default=DEFAULT_COVERS): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=12)
                    ),
                    vol.Optional(CONF_PREFERENCES, default=""): cv.string,
                    vol.Optional(CONF_AI_ENTITY, default=""): cv.string,
                    vol.Optional(CONF_WEATHER_ENTITY, default=""): cv.string,
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return JowCocktailOptionsFlow()


class JowCocktailOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("covers", default=opts.get("covers", DEFAULT_COVERS)): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=12)
                    ),
                    vol.Optional(CONF_PREFERENCES, default=opts.get(CONF_PREFERENCES, "")): cv.string,
                    vol.Optional(CONF_AI_ENTITY, default=opts.get(CONF_AI_ENTITY, "")): cv.string,
                    vol.Optional(CONF_WEATHER_ENTITY, default=opts.get(CONF_WEATHER_ENTITY, "")): cv.string,
                }
            ),
        )