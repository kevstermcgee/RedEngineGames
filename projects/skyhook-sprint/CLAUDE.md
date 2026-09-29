# skyhook-sprint

A Red Engine 2 game project. **The engine is not in this repo**: `game.json` pins it (`engine`), and `scripts/red` fetches and
builds that version on first use. Never copy engine source here; if the engine needs a change, make it in the engine repo.

## First 60 seconds
```bash
scripts/red doctor               # which engine, is it built, is the toolchain there? (scripts\red.ps1 on Windows)
scripts/red status               # resume: facts + git + STATUS.md (what is done / in flight / next)
scripts/red describe --brief     # the engine's own ~1 KB manual; then `scripts/red search "<question>"`
```

## The loop
```bash
# 1. change WHAT THE MAP IS: blueprints/*.blueprint.json  (rooms, doors, spawns, fill; `scripts/red build --example` shows the format)
scripts/red build-all            # blueprints -> maps/*.json (walls, doors, lamps, zones, spawns, portals, checks)
scripts/red check                # blueprints build + equal their maps, every map passes its own `checks` (lint, reach, auto walks)
scripts/red plan maps/main.json  # LOOK at it (labelled top-down PNG); `tour` renders every room
```
- A failing walk names the object that blocked it (id, gap, passage width) and writes `out/verify/*_explain.png`.
  `scripts/red walk maps/main.json --auto --from X,Z --to X,Z` plans a route for you; never guess waypoints.
- **Game rules are data**: put `vars` / `rules` / `weapons` under the blueprint's `"scene"` block (`scripts/red describe rules`), and prove
  them with `checks.sim` scenarios (`scripts/red sim maps/main.json`). No Rust needed for most games.
- Maps under `maps/` are generated. Do not hand-edit them: `check` fails on drift. (If you must hand-edit, delete the blueprint.)
- **Assets grow locally first**: search core with `scripts/red catalog <need>`, then put specialized
  prefabs in `assets/gameplay.json` (already linked by `prefab_files`). Inspect both together with
  `scripts/red catalog --library assets/gameplay.json <need>`. Follow Reuse -> Modify -> Generate -> Import.

## Play locally (required for every game)
```bash
scripts/red play-local           # direct single-player: no server or network needed
```

## Multiplayer (optional in addition to local play)
```bash
scripts/red serve                # headless authoritative UDP server on the map in game.json (port 27015)
scripts/red play 127.0.0.1:27015   # the graphical client (run two)
```

## Rules for whoever works here next
1. `scripts/red check` before every commit and before you say "done".
2. Record progress: `scripts/red status --note "what changed" --section done|now|next|blocked|notes`. Do it at every checkpoint.
3. Keep this file short and true. Derived facts (binaries, counts) belong in `red_engine2 status`, not in prose.
