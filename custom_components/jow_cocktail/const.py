"""Constantes de l'intégration Jow Cocktail."""

DOMAIN = "jow_cocktail"

STORAGE_KEY = "jow_cocktail.data"
STORAGE_VERSION = 1

SIGNAL_UPDATE = "jow_cocktail_update"

WEEKDAYS = [
    "lundi", "mardi", "mercredi", "jeudi",
    "vendredi", "samedi", "dimanche",
]

DEFAULT_COVERS = 1
RECIPE_BASE_URL = "https://jow.fr/recipes/"

# Services
SERVICE_SUGGEST = "suggest"
SERVICE_CLEAR = "clear"
SERVICE_SEARCH = "search"
SERVICE_PLAN = "plan"
SERVICE_GET_CONTEXT = "get_context"
SERVICE_CLEAR_RECENT = "clear_recent"

# Attributs
ATTR_QUERY = "query"
ATTR_CRITERIA = "criteria"
ATTR_DATE = "date"
ATTR_WEEKDAY = "weekday"
ATTR_LIMIT = "limit"
ATTR_CHOICE = "choice"
ATTR_COVERS = "covers"
ATTR_WEEK_OFFSET = "week_offset"
ATTR_ENTRY_NAME = "entry_name"
ATTR_AI_PROMPT = "ai_prompt"

# Options config
CONF_AI_ENTITY = "ai_entity"
CONF_WEATHER_ENTITY = "weather_entity"
CONF_JOW_TOKEN = "jow_token"
CONF_JOW_REFRESH_TOKEN = "jow_refresh_token"
CONF_PREFERENCES = "preferences"

# API Jow
JOW_API_BASE = "https://api.jow.fr/public"
JOW_AUTH_URL = f"{JOW_API_BASE}/auth"
JOW_AUTH_REFRESH_URL = f"{JOW_API_BASE}/auth/refresh"

# TheCocktailDB (API gratuite, pas de clé requise)
COCKTAILDB_BASE = "https://www.thecocktaildb.com/api/json/v1/1"
COCKTAILDB_SEARCH = f"{COCKTAILDB_BASE}/search.php"
COCKTAILDB_LOOKUP = f"{COCKTAILDB_BASE}/lookup.php"
COCKTAILDB_RANDOM = f"{COCKTAILDB_BASE}/random.php"
COCKTAILDB_FILTER = f"{COCKTAILDB_BASE}/filter.php"