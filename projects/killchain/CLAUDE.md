# killchain

A RedEngine game project (`game.json` pins the engine by path). Never copy engine source here. Gameplay rules live in the engine's loadout-shooter mode
(`shooter` block in the map); this repo holds the map generator, scripts and docs.

- `python3 tools/gen_map.py` then `tools/prune_nav.py`: maps/main.json is generated, edit the generator.
- Check: `red_engine2 lint maps/main.json && red_engine2 nav maps/main.json`.
- Scripted client runs (no window): `KC_SCRIPT=scripts/kc/*.json re2 maps/main.json` (see `run_script` in the engine's `src/bin/re2/kc/app.rs`).
