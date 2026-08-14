"""Capteurs Jow Cocktail : un par jour + cocktail du jour."""

from __future__ import annotations

from datetime import date

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_change

from .const import DOMAIN, SIGNAL_UPDATE, WEEKDAYS
from .manager import CocktailManager


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    manager: CocktailManager = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        CocktailDaySensor(manager, entry, index, week_offset=0) for index in range(7)
    ]
    entities.extend(
        CocktailDaySensor(manager, entry, index, week_offset=1) for index in range(7)
    )
    entities.append(CocktailTodaySensor(manager, entry))
    async_add_entities(entities)


class CocktailBaseSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: CocktailManager, entry: ConfigEntry) -> None:
        self._manager = manager
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Jow Cocktail",
            manufacturer="Jow Cocktail (non officiel)",
            entry_type="service",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_UPDATE, self._handle_update)
        )
        self.async_on_remove(
            async_track_time_change(
                self.hass, self._handle_midnight, hour=0, minute=0, second=10
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @callback
    def _handle_midnight(self, _now) -> None:
        self.async_write_ha_state()

    @property
    def _cocktail(self) -> dict | None:
        raise NotImplementedError

    @property
    def native_value(self) -> str:
        c = self._cocktail
        return c["name"] if c else "Rien de prévu"

    @property
    def entity_picture(self) -> str | None:
        c = self._cocktail
        return c.get("image") if c else None

    @property
    def extra_state_attributes(self) -> dict:
        c = self._cocktail
        if not c:
            return {"planned": False}
        return {
            "planned": True,
            "recipe_id": c.get("id"),
            "url": c.get("url"),
            "image": c.get("image"),
            "description": c.get("description"),
            "covers": c.get("covers"),
            "calories": c.get("calories"),
            "alcohol": c.get("alcohol"),
            "glass": c.get("glass"),
            "category": c.get("category"),
            "ingredients": c.get("ingredients", []),
            "instructions": c.get("instructions"),
            "source": c.get("source"),
        }


class CocktailDaySensor(CocktailBaseSensor):
    _attr_icon = "mdi:glass-cocktail"

    def __init__(self, manager: CocktailManager, entry: ConfigEntry, index: int, week_offset: int = 0) -> None:
        super().__init__(manager, entry)
        self._index = index
        self._week_offset = week_offset
        suffix = f"s{week_offset}" if week_offset else ""
        self._attr_name = WEEKDAYS[index].capitalize() + (f" s{week_offset}" if week_offset else "")
        self._attr_unique_id = f"{entry.entry_id}_{WEEKDAYS[index]}{suffix}"

    @property
    def _date(self) -> date:
        return self._manager.week_dates(self._week_offset)[self._index]

    @property
    def _cocktail(self) -> dict | None:
        return self._manager.get_cocktail(self._date)

    @property
    def extra_state_attributes(self) -> dict:
        return {**super().extra_state_attributes, "date": self._date.isoformat()}


class CocktailTodaySensor(CocktailBaseSensor):
    _attr_icon = "mdi:glass-cocktail"

    def __init__(self, manager: CocktailManager, entry: ConfigEntry) -> None:
        super().__init__(manager, entry)
        self._attr_name = "Cocktail du jour"
        self._attr_unique_id = f"{entry.entry_id}_today"

    @property
    def _cocktail(self) -> dict | None:
        return self._manager.get_cocktail(date.today())