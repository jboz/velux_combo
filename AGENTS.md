# AGENTS.md — Velux Combo

## Ce que fait ce dépôt

Intégration custom **Home Assistant** (distribuée via HACS) qui expose **une seule
entité `cover`** pilotant **deux entités `cover` existantes** :

- une **fenêtre de toit** Velux,
- son **store** (volet roulant).

Le but n'est pas de parler au matériel : l'intégration ne s'appuie sur aucune API
propriétaire, aucun gateway, aucune dépendance runtime. Elle ne fait que
**séquencer** des appels de service `cover.*` vers les deux entités fournies par
une autre intégration (Velux Active, HomeKit Controller, etc.).

L'essentiel du code est une machine à états : imposer un **ordre physique sûr**
entre fenêtre et store, et attendre qu'un enfant ait *réellement* atteint sa
cible avant de lancer le suivant.

## Règles métier (invariants à ne jamais casser)

| Commande | Séquence imposée | Raison |
|----------|------------------|--------|
| **Open** | store ouvre → attend arrivée → fenêtre ouvre | le store n'est jamais déroulé sous un vantail qui bouge |
| **Close** | fenêtre ferme → attend arrivée → store ferme | la fenêtre n'est jamais laissée exposée |
| **Stop** | annule la séquence en cours + stoppe chaque enfant en mouvement | pas d'état intermédiaire incohérent |

Contraintes structurelles :

- **Arrivée = position physique, pas l'état.** `_already_at_target()` exige
  `current_position >= 99` (ouverture) ou `<= 1` (fermeture). L'état seul
  (`open`/`closed`) n'est accepté **que** si aucune position n'est exposée : un
  store partiellement ouvert peut déjà se déclarer `open`.
- **Cible déjà atteinte ⇒ étape sautée.** `_move_entity` sort immédiatement si
  l'enfant est déjà à la cible (aucun service envoyé, sinon aucun `state_changed`
  n'est émis et on attendrait le timeout complet). Même contrôle juste après
  l'appel de service, via `asyncio.sleep(0)`, pour les intégrations synchrones.
- **Timeout** : `DEFAULT_TIMEOUT = 120 s` par étape, puis warning et passage à
  l'étape suivante (on ne bloque pas indéfiniment).
- **Une seule séquence à la fois** : `_task` non nul ⇒ la commande est ignorée
  (pas de file d'attente, pas d'inversion en cours de route).
- **Stop sans support natif** : si l'enfant n'implémente pas `STOP` mais
  `SET_POSITION`, on envoie la commande **inverse** pour forcer le rafraîchissement
  de `current_position` (périmée pendant le mouvement), on capture la valeur
  (`_capture_position_on_reverse`, timeout 10 s) puis on épingle l'entité dessus
  avec `set_cover_position`. Si l'enfant n'a ni `STOP` ni `SET_POSITION`, warning
  et abandon : ne pas inventer de fallback.
- **Pas de slider de position** sur l'entité combo (`SUPPORTED_FEATURES` =
  OPEN | CLOSE | STOP). `current_position` est seulement **dérivée** : moyenne
  des positions des deux enfants, à titre informatif.

## Structure

```
custom_components/velux_combo/
├── __init__.py      # setup/unload de la config entry, reload sur update
├── const.py         # DOMAIN, clés de config, DEFAULT_TIMEOUT, PLATFORMS
├── config_flow.py   # UI flow : sélection fenêtre + store, validation, unique_id
├── cover.py         # tout le métier : SequenceCover (état dérivé + séquences)
├── manifest.json    # domaine, version, iot_class=assumed_state
├── strings.json     # libellés/erreurs du config flow
└── translations/fr.json
hacs.json            # nom HACS + version HA minimale (2024.1.0)
README.md            # doc utilisateur + exemples de cartes Lovelace
```

### Points d'entrée

- `config_flow.py` : `async_step_user` valide que les deux entités sont bien des
  `cover.*` distinctes et existantes (erreurs `not_cover`, `unknown_entity`,
  `same_entity`). L'`unique_id` est un SHA-256 de la paire triée
  `window_entity|store_entity` ⇒ **stable**, changer l'ordre ne crée pas de
  doublon. Le `title` devient le nom de l'entité finale.
- `__init__.py` : setup minimal, un reload à chaque mise à jour de l'entrée.
- `cover.py` : `SequenceCover` est l'unique entité ajoutée. Elle s'abonne à
  `async_track_state_change_event` sur ses deux enfants pour recalculer son état.
  État dérivé : `opening`/`closing` si les enfants en mouvement sont unanimes,
  `open`/`closed` si les deux concordent, sinon **ni ouvert ni fermé**. Disponible
  si **au moins un** enfant est disponible.

## Conventions du dépôt

- **Async partout**, typage `from __future__ import annotations`, imports
  `homeassistant.*` uniquement (aucune dépendance tierce, `requirements: []`).
- Documentation et messages utilisateur en **français** ; code, docstrings et
  commentaires en **anglais**. Ne pas mélanger.
- Toute nouvelle clé d'erreur ou de formulaire doit être ajoutée **à la fois**
  dans `strings.json` et `translations/fr.json`.
- Pas de `set_cover_position` exposé, pas de dépendance à la marque : garder
  l'intégration agnostique du matériel.
- Commentaires utiles uniquement pour expliquer le *pourquoi* d'un ordre ou d'un
  contournement (les commentaires existants documentent des pièges matériels —
  les conserver).

## Versions et publication

- Version dans `custom_components/velux_combo/manifest.json` (`version`) ;
  incrémenter à chaque changement fonctionnel (0.x.y).
- `hacs.json` fixe la version **minimale** de Home Assistant : ne la baisser
  jamais sans raison, ne pas la monter sans vérifier les APIs utilisées
  (`CoverEntityFeature`, `ConfigFlowResult`, `async_forward_entry_setups`).
- Le README est la doc de référence utilisateur : toute nouvelle capacité
  (bouton, comportement de stop, carte Lovelace) doit y être documentée, en
  français dans les exemples.

## Développement / vérification

Il n'y a **ni suite de tests ni outillage de build** dans ce dépôt. Vérification
attendue :

```bash
python -m compileall custom_components/velux_combo   # syntaxe
ruff check custom_components                        # lint/format (README)
```

Tests manuels de référence (à décrire dans la PR) :

1. Open → store monte entièrement, *puis* fenêtre s'ouvre.
2. Close → fenêtre ferme entièrement, *puis* store descend.
3. Stop en cours d'ouverture **et** en cours de fermeture (y compris sur un
   enfant sans `stop` natif : vérifier que la position est épinglée).
4. Enfant indisponible → warning clair, pas d'exception, pas de blocage.
5. Double commande pendant une séquence → ignorée.

## Commits et branches

Suivre la skill globale `git-commit` (format Conventional Commits, gitmoji
optionnel, branche depuis la branche par défaut). Ce dépôt étant un fork,
créer les PR avec `gh pr create --repo <repo> --head <branche> --base <cible>`.

## Périmètre

Ne pas modifier de fichiers hors de ce dépôt. Ne jamais lire de `.env`.
