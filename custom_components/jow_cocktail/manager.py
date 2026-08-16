"""Manager Jow Cocktail : IA + Jow + TheCocktailDB, planning, anti-répétition."""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlparse

import requests

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import (
    COCKTAILDB_LOOKUP, COCKTAILDB_RANDOM, COCKTAILDB_SEARCH,
    COCKTAILDB_FILTER,
    DEFAULT_COVERS, DOMAIN, RECIPE_BASE_URL, SIGNAL_UPDATE,
    STORAGE_KEY, STORAGE_VERSION, WEEKDAYS,
)

_LOGGER = logging.getLogger(__name__)

_MAX_NAME_LEN = 200
_MAX_FIELD_LEN = 2000
_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_ALLOWED_URL_SCHEMES = {"http", "https"}

# API Jow (non officielle) — on cherche aussi les cocktails côté Jow.
_JOW_SEARCH_URL = "https://api.jow.fr/public/recipe/quicksearch"
_JOW_RECIPE_URL = "https://api.jow.fr/public/recipe"
_JOW_STATIC_URL = "https://static.jow.fr/"
_JOW_HEADERS = {
    "accept": "application/json",
    "accept-language": "fr",
    "content-type": "application/json",
    "x-jow-withmeta": "1",
    "origin": "https://jow.fr",
    "referer": "https://jow.fr/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}
def _safe_url(value: Any, fallback: str | None = None) -> str | None:
    if not value or not isinstance(value, str):
        return fallback
    parsed = urlparse(value)
    if parsed.scheme in _ALLOWED_URL_SCHEMES and parsed.netloc:
        return value
    return fallback


def _safe_id(value: Any) -> str | None:
    if not value:
        return None
    text = str(value)
    return text if _ID_RE.match(text) else None


def _truncate(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    return str(value)[:limit]


def _cocktail_to_dict(recipe: Any, covers: int) -> dict:
    """Convertit un cocktail (Jow ou TheCocktailDB) en dict sérialisable."""
    if not isinstance(recipe, dict):
        return {}

    # Détection de la source
    if recipe.get("_source") == "cocktaildb":
        return _cocktaildb_to_dict(recipe, covers)
    return _jow_to_dict(recipe, covers)


def _jow_to_dict(recipe: dict, covers: int) -> dict:
    """Convertit une recette Jow en dict cocktail."""
    ratio = 1.0
    base_covers = recipe.get("roundedCoversCount") or DEFAULT_COVERS
    if base_covers:
        try:
            ratio = covers / float(base_covers)
        except (TypeError, ValueError, ZeroDivisionError):
            ratio = 1.0

    ingredients = []
    for const in recipe.get("constituents", []) or []:
        ing = const.get("ingredient", {})
        qty_per_cover = ing.get("quantityPerCover")
        try:
            qty_per_cover = float(qty_per_cover) if qty_per_cover else None
        except (TypeError, ValueError):
            qty_per_cover = None
        quantity = round(qty_per_cover * ratio, 2) if qty_per_cover else None
        ingredients.append({
            "name": _truncate(ing.get("name", ""), _MAX_NAME_LEN) or "",
            "quantity": quantity,
            "unit": "",
            "optional": bool(const.get("isOptional", False)),
        })

    recipe_id = _safe_id(recipe.get("_id") or recipe.get("id"))
    url = f"{RECIPE_BASE_URL}{recipe_id}" if recipe_id else None
    image = None
    if recipe.get("imageUrl"):
        image = _safe_url(f"{_JOW_STATIC_URL}{recipe['imageUrl']}")

    return {
        "id": recipe_id,
        "name": _truncate(recipe.get("title", "Cocktail"), _MAX_NAME_LEN) or "Cocktail",
        "url": url,
        "image": image,
        "description": _truncate(recipe.get("description"), _MAX_FIELD_LEN),
        "preparation_time": recipe.get("preparationTime"),
        "covers": covers,
        "calories": recipe.get("_calories"),
        "ingredients": ingredients,
        "instructions": None,
        "alcohol": None,
        "glass": None,
        "category": None,
        "source": "jow",
    }


def _cocktaildb_to_dict(drink: dict, covers: int) -> dict:
    """Convertit un cocktail TheCocktailDB en dict."""
    drink_id = _safe_id(drink.get("idDrink"))
    name = _truncate(drink.get("strDrink", "Cocktail"), _MAX_NAME_LEN) or "Cocktail"
    image = _safe_url(drink.get("strDrinkThumb"))
    if image:
        image = f"{image}/preview"

    # Ingrédients (TheCocktailDB stocke 15 slots max)
    ingredients = []
    for i in range(1, 16):
        ing_name = drink.get(f"strIngredient{i}")
        measure = drink.get(f"strMeasure{i}")
        if ing_name and ing_name.strip():
            ingredients.append({
                "name": ing_name.strip(),
                "quantity": measure.strip() if measure else None,
                "unit": "",
                "optional": False,
            })

    return {
        "id": drink_id,
        "name": name,
        "url": f"https://www.thecocktaildb.com/drink.php?c={drink_id}" if drink_id else None,
        "image": image,
        "description": None,
        "preparation_time": None,
        "covers": covers,
        "calories": None,
        "ingredients": ingredients,
        "instructions": _truncate(drink.get("strInstructions"), _MAX_FIELD_LEN),
        "alcohol": drink.get("strAlcoholic"),
        "glass": drink.get("strGlass"),
        "category": drink.get("strCategory"),
        "source": "cocktaildb",
    }


class CocktailManager:
    """Garde le planning des cocktails et l'historique."""

    def __init__(
        self,
        hass: HomeAssistant,
        default_covers: int,
        preferences: str = "",
        ai_entity: str = "",
        weather_entity: str = "",
        entry_id: str = "",
    ) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.default_covers = default_covers
        self.preferences = preferences
        self.ai_entity = ai_entity
        self.weather_entity = weather_entity
        store_key = f"{STORAGE_KEY}.{entry_id}" if entry_id else STORAGE_KEY
        self._store: Store = Store(hass, STORAGE_VERSION, store_key)
        self.plan: dict[str, dict] = {}
        # Historique des IDs de cocktails déjà proposés (survit au clear)
        self.history: list[str] = []
        self._history_max = 50

    # ------------------------------------------------------------------
    # Persistance
    # ------------------------------------------------------------------
    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.plan = data.get("plan", {})
        self.history = data.get("history", [])

    async def async_save(self) -> None:
        await self._store.async_save({"plan": self.plan, "history": self.history})
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)

    def _add_to_history(self, cocktail_id: str) -> None:
        """Ajoute un cocktail à l'historique (anti-répétition)."""
        if not cocktail_id:
            return
        if cocktail_id in self.history:
            self.history.remove(cocktail_id)
        self.history.append(cocktail_id)
        # Garder les 50 plus récents
        if len(self.history) > self._history_max:
            self.history = self.history[-self._history_max:]

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------
    @staticmethod
    def monday_of(day: date, week_offset: int = 0) -> date:
        return day - timedelta(days=day.weekday()) + timedelta(weeks=week_offset)

    def week_dates(self, week_offset: int = 0) -> list[date]:
        monday = self.monday_of(date.today(), week_offset)
        return [monday + timedelta(days=i) for i in range(7)]

    def get_cocktail(self, day: date) -> dict | None:
        return self.plan.get(day.isoformat())

    async def async_clear_cocktail(self, day: date) -> None:
        self.plan.pop(day.isoformat(), None)
        await self.async_save()

    def clear_history(self) -> dict:
        """Vide l'historique des cocktails déjà proposés."""
        count = len(self.history)
        self.history = []
        return {"cleared": count}

    async def async_clear_recent(self, date_iso: str) -> dict:
        c = self.plan.get(date_iso)
        if not c:
            return {"error": "Aucun cocktail à cette date"}
        c["_no_exclude"] = True
        await self.async_save()
        return {"cleared": c.get("name", ""), "date": date_iso}

    def purge_old(self, keep_days: int = 30) -> None:
        limit = (date.today() - timedelta(days=keep_days)).isoformat()
        for key in [k for k in self.plan if k < limit]:
            self.plan.pop(key, None)

    # ------------------------------------------------------------------
    # Recherche Jow
    # ------------------------------------------------------------------
    async def async_search_jow(self, query: str, limit: int = 5) -> list[dict]:
        def _search():
            params = {
                "start": "0", "availabilityZoneId": "FR",
                "query": query, "limit": str(max(limit, 1)),
            }
            options_headers = {
                "accept": "*/*", "accept-language": "fr,fr-FR;q=0.9",
                "access-control-request-method": "POST",
                "access-control-request-headers": "content-type,x-jow-withmeta",
            }
            requests.options(_JOW_SEARCH_URL, headers=options_headers, params=params, timeout=10)
            resp = requests.post(
                _JOW_SEARCH_URL, headers=dict(_JOW_HEADERS), params=params, data="{}", timeout=15
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            return data.get("content", []) if isinstance(data, dict) else []

        try:
            results = await self.hass.async_add_executor_job(_search) or []
            # Filtrer les plats salés : les cocktails n'ont pas de cookingTime
            # (pas de cuisson), tandis que les plats ont cookingTime >= 5.
            filtered = [r for r in results if not r.get("cookingTime")]
            if filtered:
                return filtered
            # Si tous ont un cookingTime, garder quand même (mieux que rien)
            return results
        except Exception as err:
            _LOGGER.warning("Recherche Jow impossible (%s) : %s", query, err)
            return []

    async def async_fetch_jow_calories(self, recipe_id: str) -> int | None:
        if not recipe_id or not _ID_RE.match(recipe_id):
            return None

        def _fetch():
            url = f"{_JOW_RECIPE_URL}/{recipe_id}"
            headers = dict(_JOW_HEADERS)
            headers["x-jow-withmeta"] = "true"
            headers["accept"] = "application/json, text/plain, */*"
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            facts = data.get("nutritionalFacts", [])
            for fact in facts:
                if fact.get("id") == "ENERC":
                    try:
                        return int(round(float(fact.get("amount", 0))))
                    except (TypeError, ValueError):
                        return None
            return None

        try:
            return await self.hass.async_add_executor_job(_fetch)
        except Exception as err:
            _LOGGER.debug("Calories Jow indisponibles pour %s : %s", recipe_id, err)
            return None

    # ------------------------------------------------------------------
    # Recherche TheCocktailDB
    # ------------------------------------------------------------------
    async def async_search_cocktaildb(self, query: str, limit: int = 5, sans_alcool: bool = False) -> list[dict]:
        """Recherche sur TheCocktailDB.
        
        TheCocktailDB fait une recherche par nom (search.php?s=) qui ne matche
        pas les requêtes IA comme "fresh gin cocktail". On essaime donc :
        1. Recherche par nom (search.php?s=query)
        2. Si aucun résultat, extraction du premier mot comme ingrédient
           (filter.php?i=ingredient) puis lookup détaillé.
        Si sans_alcool=True, filtre les résultats avec strAlcoholic != "Alcoholic".
        """
        def _search_by_name(q):
            resp = requests.get(COCKTAILDB_SEARCH, params={"s": q}, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            drinks = data.get("drinks") or []
            for d in drinks:
                d["_source"] = "cocktaildb"
            return drinks[:limit]

        def _search_by_ingredient(ingredient):
            resp = requests.get(COCKTAILDB_FILTER, params={"i": ingredient}, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            drinks = data.get("drinks") or []
            return drinks[:limit]

        def _lookup_drink(drink_id):
            resp = requests.get(COCKTAILDB_LOOKUP, params={"i": drink_id}, timeout=10)
            resp.raise_for_status()
            d2 = resp.json().get("drinks") or []
            if d2:
                d2[0]["_source"] = "cocktaildb"
                return d2[0]
            return None

        async def _parallel_lookup(drinks_list):
            import asyncio
            ids = [d.get("idDrink") for d in drinks_list if d.get("idDrink")]
            lookups = await asyncio.gather(
                *[self.hass.async_add_executor_job(_lookup_drink, did) for did in ids],
                return_exceptions=True,
            )
            return [r for r in lookups if isinstance(r, dict)]

        try:
            # Si sans alcool, utiliser l'endpoint dédié
            if sans_alcool:
                def _list_non_alcoholic():
                    resp = requests.get(COCKTAILDB_FILTER, params={"a": "non_alcoholic"}, timeout=10)
                    resp.raise_for_status()
                    data = resp.json()
                    return data.get("drinks") or []
                drinks = await self.hass.async_add_executor_job(_list_non_alcoholic)
                results = await _parallel_lookup(drinks[:limit * 2])
                return results[:limit]

            # 1. Recherche par nom
            results = await self.hass.async_add_executor_job(_search_by_name, query)
            if results:
                return results

            # 2. Fallback : extraire le premier mot comme ingrédient
            words = query.strip().split()
            for word in words:
                if len(word) >= 3 and word.lower() not in ("cocktail", "drink", "fresh", "with", "the", "and", "sans", "alcool", "mocktail", "virgin", "non"):
                    drinks = await self.hass.async_add_executor_job(_search_by_ingredient, word)
                    if drinks:
                        results = await _parallel_lookup(drinks)
                        if results:
                            return results
            return []
        except Exception as err:
            _LOGGER.error("Recherche TheCocktailDB impossible (%s) : %s", query, err)
            return []

    async def async_random_cocktaildb(self) -> dict | None:
        def _fetch():
            resp = requests.get(COCKTAILDB_RANDOM, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            drinks = data.get("drinks") or []
            if drinks:
                drinks[0]["_source"] = "cocktaildb"
                return drinks[0]
            return None

        try:
            return await self.hass.async_add_executor_job(_fetch)
        except Exception as err:
            _LOGGER.error("Cocktail aléatoire TheCocktailDB impossible : %s", err)
            return None

    # ------------------------------------------------------------------
    # Recherche combinée
    # ------------------------------------------------------------------
    async def async_search(self, query: str, limit: int = 5, sans_alcool: bool = False) -> list[dict]:
        """Recherche sur Jow et TheCocktailDB, fusionne en alternant les sources.
        
        Si sans_alcool=True, ignore Jow (qui ne filtre pas l'alcool) et
        utilise uniquement TheCocktailDB filter.php?a=non_alcoholic.
        """
        covers = self.default_covers
        if sans_alcool:
            # Jow ne comprend pas "sans alcool" — utiliser uniquement TheCocktailDB
            cdb_results = await self.async_search_cocktaildb(query, limit=limit, sans_alcool=True)
            return [_cocktail_to_dict(r, covers) for r in cdb_results[:limit * 2]]
        
        jow_results = await self.async_search_jow(query, limit=limit)
        cdb_results = await self.async_search_cocktaildb(query, limit=limit)
        # Alterner Jow et CocktailDB pour avoir de la variété
        all_recipes = []
        max_len = max(len(jow_results), len(cdb_results))
        for i in range(max_len):
            if i < len(jow_results):
                all_recipes.append(jow_results[i])
            if i < len(cdb_results):
                all_recipes.append(cdb_results[i])
        return [_cocktail_to_dict(r, covers) for r in all_recipes[:limit * 2]]

    async def async_plan_cocktail(
        self, day: date, query: str, covers: int | None = None, choice: int = 1
    ) -> dict | None:
        covers = covers or self.default_covers
        results = await self.async_search(query, limit=max(choice, 1))
        if not results:
            _LOGGER.warning("Aucun cocktail trouvé pour « %s »", query)
            return None
        chosen = results[min(choice, len(results)) - 1]
        # Fetch calories si source Jow
        if chosen.get("source") == "jow" and chosen.get("id"):
            calories = await self.async_fetch_jow_calories(chosen["id"])
            if calories is not None:
                chosen["calories"] = calories
        chosen["covers"] = covers
        self._add_to_history(chosen.get("id", ""))
        self.plan[day.isoformat()] = chosen
        await self.async_save()
        return chosen

    # ------------------------------------------------------------------
    # Suggestion IA
    # ------------------------------------------------------------------
    async def async_suggest(
        self,
        criteria: str = "",
        covers: int | None = None,
        limit: int = 5,
        weather_entity: str | None = None,
        ai_entity: str | None = None,
        weekday: str | None = None,
        week_offset: int = 0,
        ai_prompt: str = "",
    ) -> list[dict]:
        """Génère une requête via l'IA puis cherche des cocktails."""
        ai_ent = ai_entity or self.ai_entity
        weather_ent = weather_entity or self.weather_entity

        # Contexte météo
        weather_ctx = ""
        if weather_ent:
            state = self.hass.states.get(weather_ent)
            if state and state.state not in (None, "unknown", "unavailable"):
                temp = state.attributes.get("temperature", "?")
                weather_ctx = f"Météo actuelle : {state.state}, {temp}°C. "

        # Contraintes
        constraints = ""
        if self.preferences:
            constraints += f"Préférences : {self.preferences}. "
        if criteria:
            constraints += f"Demande : {criteria}. "

        # Cocktails récents à éviter
        from datetime import date as _date, timedelta as _td
        cutoff = (_date.today() - _td(weeks=4)).isoformat()
        recent_names = []
        for day_iso, c in self.plan.items():
            if c and c.get("name") and day_iso >= cutoff:
                recent_names.append(c["name"])
        if recent_names:
            constraints += (
                f"Évite ces cocktails déjà faits récemment : {', '.join(recent_names[:8])}. "
                "Propose quelque chose de différent. "
            )

        instructions = (
            f"{weather_ctx}{constraints}"
            "Génère une requête de recherche de cocktail courte (2 à 5 mots, "
            "sans guillemets ni ponctuation) adaptée au contexte. "
            "Il s'agit d'un COCKTAIL ou d'une boisson alcoolisée ou sans alcool. "
            "Varie le style (sour, sweet, fizz, tropical, classique, etc). "
            "Réponds en ANGLAIS (ex: gin sour, mojito, espresso martini) "
            "car la recherche se fait aussi sur une base anglophone. "
            "Réponds uniquement avec la requête."
        )
        if ai_prompt:
            instructions = (
                f"{weather_ctx}{constraints}"
                f"{ai_prompt} "
                "Il s'agit d'un COCKTAIL. "
                "Réponds en ANGLAIS. "
                "Réponds uniquement avec la requête de recherche."
            )

        # Si l'utilisateur a fourni un critère court (1-5 mots), l'utiliser
        # directement. Si c'est une phrase longue ou complexe, utiliser l'IA
        # pour extraire une requête de recherche courte.
        query = ""
        # Détecter la demande "sans alcool"
        criteria_lower = (criteria or "").lower()
        sans_alcool = any(kw in criteria_lower for kw in
                          ("sans alcool", "mocktail", "no alcohol", "virgin",
                           "boisson sans alcool"))
        
        criteria_words = criteria.strip().split() if criteria else []
        is_long_phrase = len(criteria_words) > 5
        
        if not criteria or (is_long_phrase and ai_ent):
            # Pas de critère → l'IA génère une requête (Surprends-moi)
            # Phrase longue → l'IA extrait une requête courte
            if ai_ent:
                if is_long_phrase:
                    instructions = (
                        f"{weather_ctx}{constraints}"
                        f"Transforme cette demande en requête de recherche de "
                        f"cocktail courte (2 à 5 mots, en ANGLAIS) : « {criteria} ». "
                        "Il s'agit d'un COCKTAIL. "
                        "Réponds uniquement avec la requête de recherche."
                    )
                try:
                    response = await self.hass.services.async_call(
                        "ai_task", "generate_data",
                        {
                            "task_name": "jow_cocktail_suggest",
                            "instructions": instructions,
                            "entity_id": ai_ent,
                        },
                        blocking=True, return_response=True,
                    )
                    if isinstance(response, dict):
                        data = response.get("data")
                        if not data:
                            data = response.get("response", {}).get("data", "")
                        if not data:
                            for _k, val in response.items():
                                if isinstance(val, dict) and "data" in val:
                                    data = val["data"]
                                    break
                        query = str(data or "").strip().strip('"').strip("'")
                    elif isinstance(response, str):
                        query = response.strip().strip('"').strip("'")
                except Exception as err:
                    _LOGGER.warning("ai_task.generate_data a échoué : %s", err)
                    query = ""

        if not query:
            # Fallback : extraire les mots-clés pertinents de la phrase
            if is_long_phrase:
                # Garder les mots > 3 lettres, igniser les mots vides
                stop_words = {"propose", "moi", "un", "une", "des", "avec", "sans",
                              "facile", "faire", "base", "pour", "the", "and",
                              "cocktail", "drink", "boisson", "alcool"}
                keywords = [w for w in criteria_words
                           if len(w) > 3 and w.lower() not in stop_words]
                query = " ".join(keywords[:4]) if keywords else "cocktail"
            else:
                query = criteria or "cocktail"

        _LOGGER.info("Requête cocktail suggérée : %s (sans_alcool=%s)", query, sans_alcool)
        results = await self.async_search(query, limit=max(limit * 2, 10), sans_alcool=sans_alcool)
        covers = covers or self.default_covers
        cocktails = results

        # Exclure les cocktails déjà planifiés récemment ET l'historique
        deja_planifies = set()
        for day_iso, c in self.plan.items():
            if c and c.get("id") and day_iso >= cutoff:
                if not c.get("_no_exclude"):
                    deja_planifies.add(c["id"])
        deja_planifies.update(self.history)
        if deja_planifies:
            avant = len(cocktails)
            cocktails = [c for c in cocktails if c.get("id") not in deja_planifies]
            _LOGGER.info("Cocktails dédupliqués : %d exclues, %d restantes",
                         avant - len(cocktails), len(cocktails))

        if not cocktails and self.history:
            _LOGGER.info("Tous les cocktails exclus par l'historique, recherche élargie")
            results = await self.async_search("cocktail", limit=max(limit * 3, 15), sans_alcool=sans_alcool)
            cocktails = [c for c in results if c.get("id") not in deja_planifies]

        cocktails = cocktails[:limit]

        # Si on ne demande pas "sans alcool", privilégier les cocktails
        # alcoolisés (TheCocktailDB) en mettant les "Non alcoholic" en fin
        if not sans_alcool and cocktails:
            alcoolises = [c for c in cocktails if c.get("alcohol") != "Non alcoholic" and c.get("alcohol") != "Non-Alcoholic"]
            non_alcoolises = [c for c in cocktails if c.get("alcohol") in ("Non alcoholic", "Non-Alcoholic")]
            if alcoolises:
                cocktails = alcoolises + non_alcoolises

        if weekday and weekday in WEEKDAYS and cocktails:
            import random
            day_idx = WEEKDAYS.index(weekday)
            target_date = self.week_dates(week_offset)[day_idx]
            # Si l'utilisateur a fourni un critère précis, prendre le 1er résultat
            if criteria:
                chosen = cocktails[0]
            else:
                chosen = random.choice(cocktails)
            if chosen.get("source") == "jow" and chosen.get("id"):
                calories = await self.async_fetch_jow_calories(chosen["id"])
                if calories is not None:
                    chosen["calories"] = calories
            chosen["covers"] = covers
            self._add_to_history(chosen.get("id", ""))
            self.plan[target_date.isoformat()] = chosen
            await self.async_save()
            _LOGGER.info("Cocktail '%s' planifié sur %s (criteria=%s, source=%s, alcohol=%s)",
                         chosen.get("name", ""), weekday, bool(criteria),
                         chosen.get("source", "?"), chosen.get("alcohol", "?"))

        return cocktails