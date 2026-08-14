"""Intégration Jow Cocktail pour Home Assistant."""

from __future__ import annotations

import logging
from datetime import date, datetime

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_CHOICE, ATTR_COVERS, ATTR_CRITERIA, ATTR_DATE, ATTR_LIMIT,
    ATTR_QUERY, ATTR_WEEK_OFFSET, ATTR_WEEKDAY, ATTR_ENTRY_NAME,
    ATTR_AI_PROMPT, CONF_AI_ENTITY, CONF_PREFERENCES, CONF_WEATHER_ENTITY,
    DEFAULT_COVERS, DOMAIN, SERVICE_SUGGEST, SERVICE_CLEAR, SERVICE_SEARCH,
    SERVICE_PLAN, SERVICE_GET_CONTEXT, SERVICE_CLEAR_RECENT,
    SERVICE_CLEAR_HISTORY, WEEKDAYS,
)
from .manager import CocktailManager, _cocktail_to_dict

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


def _get_manager(hass: HomeAssistant, call: ServiceCall, default_manager: CocktailManager) -> CocktailManager:
    entry_name = call.data.get(ATTR_ENTRY_NAME)
    if not entry_name:
        return default_manager
    for entry_id, manager in hass.data.get(DOMAIN, {}).items():
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry and (entry.title == entry_name or entry.data.get("name") == entry_name):
            return manager
    _LOGGER.warning("Instance « %s » introuvable, utilisation de l'instance par défaut", entry_name)
    return default_manager


def _resolve_date(manager: CocktailManager, call: ServiceCall) -> date:
    if raw := call.data.get(ATTR_DATE):
        if isinstance(raw, date):
            return raw
        return datetime.fromisoformat(str(raw)).date()
    weekday = call.data.get(ATTR_WEEKDAY)
    offset = call.data.get(ATTR_WEEK_OFFSET, 0)
    if weekday:
        return manager.week_dates(offset)[WEEKDAYS.index(weekday)]
    return date.today()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    opts = entry.options
    manager = CocktailManager(
        hass,
        opts.get("covers", DEFAULT_COVERS),
        preferences=opts.get(CONF_PREFERENCES, ""),
        ai_entity=opts.get(CONF_AI_ENTITY, ""),
        weather_entity=opts.get(CONF_WEATHER_ENTITY, ""),
        entry_id=entry.entry_id,
    )
    await manager.async_load()
    manager.purge_old()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def handle_suggest(call: ServiceCall) -> ServiceResponse:
        mgr = _get_manager(hass, call, manager)
        results = await mgr.async_suggest(
            criteria=call.data.get(ATTR_CRITERIA, ""),
            covers=call.data.get(ATTR_COVERS),
            limit=call.data.get(ATTR_LIMIT, 5),
            weather_entity=call.data.get(CONF_WEATHER_ENTITY),
            ai_entity=call.data.get(CONF_AI_ENTITY),
            weekday=call.data.get(ATTR_WEEKDAY),
            week_offset=call.data.get(ATTR_WEEK_OFFSET, 0),
            ai_prompt=call.data.get(ATTR_AI_PROMPT, ""),
        )
        return {"cocktails": results}

    async def handle_clear(call: ServiceCall) -> None:
        mgr = _get_manager(hass, call, manager)
        await mgr.async_clear_cocktail(_resolve_date(mgr, call))

    async def handle_search(call: ServiceCall) -> ServiceResponse:
        mgr = _get_manager(hass, call, manager)
        results = await mgr.async_search(call.data[ATTR_QUERY], limit=call.data.get(ATTR_LIMIT, 5))
        return {"cocktails": results}

    async def handle_plan(call: ServiceCall) -> ServiceResponse:
        mgr = _get_manager(hass, call, manager)
        day = _resolve_date(mgr, call)
        result = await mgr.async_plan_cocktail(
            day,
            call.data[ATTR_QUERY],
            covers=call.data.get(ATTR_COVERS),
            choice=call.data.get(ATTR_CHOICE, 1),
        )
        if result is None:
            return {"error": "Aucun cocktail trouvé"}
        return {"cocktail": result}

    async def handle_get_context(call: ServiceCall) -> ServiceResponse:
        mgr = _get_manager(hass, call, manager)
        from datetime import date as _date, timedelta as _td
        cutoff = (_date.today() - _td(weeks=4)).isoformat()
        recent = []
        for day_iso, c in mgr.plan.items():
            if c and c.get("name") and day_iso >= cutoff:
                recent.append({
                    "name": c["name"],
                    "date": day_iso,
                    "excluded": not c.get("_no_exclude", False),
                })
        return {
            "preferences": mgr.preferences or "",
            "recent_cocktails": recent,
            "default_covers": mgr.default_covers,
        }

    async def handle_clear_recent(call: ServiceCall) -> ServiceResponse:
        mgr = _get_manager(hass, call, manager)
        date_iso = call.data.get("date", "")
        result = await mgr.async_clear_recent(date_iso)
        return result

    async def handle_clear_history(call: ServiceCall) -> ServiceResponse:
        mgr = _get_manager(hass, call, manager)
        return mgr.clear_history()

    hass.services.async_register(
        DOMAIN, SERVICE_SUGGEST, handle_suggest,
        schema=vol.Schema({
            vol.Optional(ATTR_CRITERIA): cv.string,
            vol.Optional(ATTR_LIMIT, default=5): vol.All(vol.Coerce(int), vol.Range(min=1, max=20)),
            vol.Optional(ATTR_COVERS): vol.All(vol.Coerce(int), vol.Range(min=1, max=12)),
            vol.Optional(CONF_WEATHER_ENTITY): cv.string,
            vol.Optional(CONF_AI_ENTITY): cv.string,
            vol.Optional(ATTR_WEEKDAY): vol.In(WEEKDAYS),
            vol.Optional(ATTR_WEEK_OFFSET, default=0): vol.Coerce(int),
            vol.Optional(ATTR_ENTRY_NAME): cv.string,
            vol.Optional(ATTR_AI_PROMPT): cv.string,
        }),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CLEAR, handle_clear,
        schema=vol.Schema({
            vol.Optional(ATTR_DATE): cv.date,
            vol.Optional(ATTR_WEEKDAY): vol.In(WEEKDAYS),
            vol.Optional(ATTR_WEEK_OFFSET, default=0): vol.Coerce(int),
            vol.Optional(ATTR_ENTRY_NAME): cv.string,
        }),
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SEARCH, handle_search,
        schema=vol.Schema({
            vol.Required(ATTR_QUERY): cv.string,
            vol.Optional(ATTR_LIMIT, default=5): vol.All(vol.Coerce(int), vol.Range(min=1, max=20)),
            vol.Optional(ATTR_COVERS): vol.Coerce(int),
            vol.Optional(ATTR_ENTRY_NAME): cv.string,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_PLAN, handle_plan,
        schema=vol.Schema({
            vol.Required(ATTR_QUERY): cv.string,
            vol.Optional(ATTR_DATE): cv.date,
            vol.Optional(ATTR_WEEKDAY): vol.In(WEEKDAYS),
            vol.Optional(ATTR_WEEK_OFFSET, default=0): vol.Coerce(int),
            vol.Optional(ATTR_COVERS): vol.All(vol.Coerce(int), vol.Range(min=1, max=12)),
            vol.Optional(ATTR_CHOICE, default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
            vol.Optional(ATTR_ENTRY_NAME): cv.string,
        }),
    )
    hass.services.async_register(
        DOMAIN, SERVICE_GET_CONTEXT, handle_get_context,
        schema=vol.Schema({}, extra=vol.ALLOW_EXTRA),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CLEAR_RECENT, handle_clear_recent,
        schema=vol.Schema({
            vol.Required("date"): cv.string,
            vol.Optional(ATTR_ENTRY_NAME): cv.string,
        }),
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CLEAR_HISTORY, handle_clear_history,
        schema=vol.Schema({}, extra=vol.ALLOW_EXTRA),
        supports_response=SupportsResponse.ONLY,
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            for service in (SERVICE_SUGGEST, SERVICE_CLEAR, SERVICE_SEARCH, SERVICE_PLAN, SERVICE_GET_CONTEXT, SERVICE_CLEAR_RECENT, SERVICE_CLEAR_HISTORY):
                hass.services.async_remove(DOMAIN, service)
    return unload_ok