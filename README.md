# Jow Cocktail — Intégration Home Assistant

Cocktail du jour pour Home Assistant. L'IA génère des suggestions de cocktails adaptées à vos préférences et à la météo, en cherchant sur **Jow** et **TheCocktailDB**.

## Fonctionnalités

- **Cocktail du jour** : un capteur par jour de la semaine + capteur "Cocktail du jour"
- **Suggestion IA** : l'agent `ai_task` génère une requête adaptée (préférences, météo, anti-répétition)
- **Sources combinées** : Jow (recettes) + TheCocktailDB (base de cocktails)
- **Anti-répétition** : les cocktails des 4 dernières semaines sont exclus
- **Historique** : les cocktails passés restent visibles
- **Barre de saisie** : demandez un cocktail en langage naturel ("rafraîchissant avec du gin")

## Installation

1. Ajoutez ce dépôt dans HACS → Intégrations → Dépôts personnalisés
2. Installez "Jow Cocktail"
3. Redémarrez Home Assistant
4. Ajoutez l'intégration via Paramètres → Appareils & Services

## Configuration

| Champ | Description |
|-------|-------------|
| Nom | Nom de l'instance |
| Verres par défaut | Nombre de verres (défaut: 1) |
| Préférences | Ex: "pas trop sucré, plutôt du gin" |
| Agent IA | `ai_task.ollama_ai_task` ou similaire |
| Météo | `weather.maison` (facultatif) |

## Services

| Service | Description |
|---------|-------------|
| `jow_cocktail.suggest` | Suggère un cocktail via l'IA |
| `jow_cocktail.plan` | Planifie un cocktail par nom |
| `jow_cocktail.search` | Recherche un cocktail |
| `jow_cocktail.clear` | Efface le cocktail d'un jour |
| `jow_cocktail.get_context` | Retourne le contexte IA |
| `jow_cocktail.clear_recent` | Retire un cocktail de l'anti-répétition |

## Carte Lovelace

Voir le repo [jow-cocktail-card](https://github.com/junkoku38/jow-cocktail-card) pour la carte d'affichage.