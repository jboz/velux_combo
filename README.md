# Velux Combo

Custom Home Assistant integration that synchronises a **Velux roof window** and its **store** (roller shutter) so they move in a safe, deterministic sequence.

> If you already use the official **Velux Active** integration (KIG 300 / KIX 300 gateway), this wrapper simply drives the two cover entities it provides.

## How it works

Each configured cover exposes a single, combined `cover` entity. It never sends conflicting commands:

| Command | Sequence |
|---------|----------|
| **Open** | 1. Store opens → 2. Window opens *(only after the store is fully open)* |
| **Close** | 1. Window closes → 2. Store closes *(only after the window is fully closed)* |
| **Stop** | Stops both entities if they are moving, and cancels a pending sequence |

Why this order?

- **Opening**: the store moves first so it is never rolled down while the window opens (no stored fabric jamming under the moving pane).
- **Closing**: the window closes first so it is never left exposed while the store rolls down.

## Installation (HACS)

1. Make sure [HACS](https://hacs.xyz) is installed.
2. In HACS → **three-dot menu** → **Custom repositories**:
   - URL: `https://github.com/jboz/velux_combo`
   - Category: **Integration**
3. Click **Download** and install.
4. **Restart Home Assistant.**

*Manual install:* copy the `custom_components/velux_combo` folder into your `<config>/custom_components/` directory and restart Home Assistant.

## Configuration

The integration is configured entirely from the UI:

1. Go to **Settings → Devices & Services → Add Integration → Velux Combo**.
2. Select the **window** cover entity.
3. Select the **store** cover entity.
4. (Optional) give the pair a name.
5. Repeat the flow for every additional window/store pair.

You will then see one new cover entity per pair.

### Requirements

- Home Assistant **2024.1 or newer**.
- Two existing **cover** entities (the window and its store), for example from the
  [Velux Active](https://www.home-assistant.io/integrations/velux/) or
  [HomeKit Controller](https://www.home-assistant.io/integrations/homekit_controller/)
  integration.

## Usage

Once configured, use the new cover entity like any other:

- The dashboard card, `cover.open_cover` / `cover.close_cover` services,
  automations, scripts and virtual assistants all target the single combined
  entity.
- The entity reports **open / closed / opening / closing** by combining the
  state of both child covers.

### Notes

- Only full *open → close* commands are exposed (no position slider): the
  sequencing guarantees the window is never partially opened with the store
  rolled down.
- Each step waits until its child has **physically** reached the target: a
  `current_position` of `>= 99` (opening) or `<= 1` (closing) is required
  before the next child starts. State alone is not trusted — a partially
  opened store can already report `open`.
- If a child never reaches its target within `120 s`, the integration logs a
  warning and moves on to the next step.
- Commands that arrive while a sequence is already running are ignored
  (see `Stop`).
- **Stop** halts each running child: it uses the child's native stop when
  available, otherwise it briefly sends the **opposite command** to make the
  child refresh its `current_position` (which is otherwise stale during
  travel), captures the refreshed value and pins the cover to it via
  `set_cover_position`. This works with covers (e.g. Velux / HomeKit) that
  expose no native `stop` but refresh their position when the travel
  direction is reversed.

## Dashboard examples

Ready-made Lovelace cards build on the native **tile** card and its selectable
**features** — no custom card required. Each tile shows its own state
(open / closed / opening / closing) and its own controls.

### One card per Velux (window + store + combined)

```yaml
type: vertical-stack
title: Velux 1
cards:
  - type: tile
    entity: cover.velux_1
    name: Combo
    vertical: false
    features:
      - type: cover-open-close
    features_position: bottom
  - type: horizontal-stack
    cards:
      - type: tile
        entity: cover.velux_1_roof_window
        name: Fenêtre
        vertical: false
        features:
          - type: cover-position-favorite
#          - type: cover-position
#          - type: cover-open-close
        features_position: bottom
      - type: tile
        entity: cover.velux_1_roller_shutter
        name: Store
        features:
          - type: cover-position
#          - type: cover-open-close
#          - type: cover-position-favorite
```

Replace the entity ids with your own (`cover.velux_*`, plus the window and
store covers you selected during setup).

### Open or close all Velux at once

Add a **cover group** helper containing all your combined entities
(`cover.velux_*`), then control them from a single card. When the group is told
to open or close, it drives every member: each combined entity starts its own
sequence immediately in the background, so all Velux move **in parallel**.

1. **Settings → Devices & Services → Helpers → Create Helper → Group →
   Cover group**.
2. Select all your combined entities (e.g. `cover.velux_1` … `cover.velux_7`)
   and give the group a name, e.g. `Tous les Velux` (the entity becomes
   `cover.tous_les_velux`).
3. Add the group's tile card at the top of your row:

```yaml
type: tile
entity: cover.tous_les_velux
name: Tous les Velux
features:
  - type: cover-open-close
```

The group card exposes the global **open / stop / close** buttons and the
group's combined state.

### Notes on the examples

- The combined entity only supports full *open / close*: use
  `cover-open-close` and do **not** add a position slider to it.
- `cover-position-favorite` shows the **preset positions** (by default
  0 / 25 / 50 / 75 / 100 %). Edit them from the entity's *More info* dialog:
  press and hold a preset to change or remove it (e.g. delete 50 % to get
  0 / 25 / 75 / 100 %).
- `cover-position` adds a free slider instead of presets, if you prefer fine
  control.
- These features require a recent Home Assistant version with tile card
  **features** support.

## Troubleshooting

- **"This entity must be a cover entity"** — the window/store must be `cover`
  entities (entity id starting with `cover.`).
- **Entities not moving** — check the underlying Velux/HomeKit integration
  can control the window and store individually first.
- **Sequence stops early** — a child reported itself as *open/closed* via its
  `current_position` even though it was still moving; this is a limitation of
  the underlying entity, not of this integration.

## Development

```bash
pip install -e .[dev]  # or just run pylint/mypy
```

This repository is formatted with `ruff`. No third-party runtime dependencies.

## License

MIT. See [LICENSE](LICENSE).

---

*Not affiliated with VELUX. Velux is a trademark of VELUX Group.*
