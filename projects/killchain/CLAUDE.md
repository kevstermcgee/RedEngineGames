# killchain

A RedEngine game project (`game.json` pins the engine by path). Never copy engine source here. Gameplay rules live in the engine's loadout-shooter mode
(`shooter` block in the map); this repo holds the map generators, scripts and docs. Start with `STATUS.md`.

- **Maps are generated**: `python3 tools/gen_map.py` (Ironworks, `maps/main.json`), `tools/gen_quarry.py`, `tools/gen_terminus.py`, each followed by
  `RED_ENGINE2=... python3 tools/prune_nav.py maps/<map>.json`. Shared pieces are in `tools/mapkit.py` (boxes, `room` with walkable interior, raised floors and stairs,
  `spot_near` pickups). Edit a generator, never the JSON.
- **Modes** (`tdm`, `ffa`, `ctf`, `snd`) are the host's choice; a map carries the data for all of them: `shooter.flags` (two bases), `shooter.sites` (bomb sites),
  `shooter.objective`, team spawns (`team1` = attackers in search and destroy) and neutral `ffa` spawns. How a mode is wired: the engine's
  `docs/adr/2026-10-07-killchain-game-modes-free-for-all-capture-the-flag.md`.
- **Check every map**: `red_engine2 lint maps/X.json && red_engine2 nav maps/X.json`, look at `red_engine2 plan maps/X.json out/plan.png`, then play it headless:
  `KC_SCRIPT=scripts/kc/<script>.json re2 maps/main.json` writes pictures to `out/kc/` (read the PNGs). `meta.x-short` is the setup-screen label (<= 6 letters).
- **Bots on a real map**: in the engine, `KC_MAP=maps/X.json KC_MODE=ctf cargo test --test objective_modes real_map -- --ignored --nocapture`.
- The weapon table is generated: `cargo run --example weapons_table > docs/WEAPONS.md` (in RedEngine).
- Joining: HOST shows a six-character relay code (the project relay is the default, `RE2_RELAY=off` disables it) and a long direct code; JOIN tries each installed map.
