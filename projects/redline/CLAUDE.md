# redline

REDLINE, a first-person momentum roguelite on Red Engine 2. **The engine is not in this repo**: `game.json` pins it (`engine`), and
`scripts/red` finds or builds that version. Never copy engine source here; if the engine needs a change, make it in the engine repo.

## The loop
```bash
python3 tools/gen_map.py maps/main.json          # the map is GENERATED: edit tools/*.py, never maps/main.json by hand
scripts/red check                                 # 25 scenarios: every chamber clearable at base speed, the run loop works
python3 tools/gen_map.py maps/main.json --pars   # after changing a chamber: re-measure pars (and the dive's chamber), then generate again
python3 tools/first_burn.py a4 b2                 # a failing chamber: where the scripted runner fell, in chamber coordinates
python3 tools/debug_route.py a4 --script          # its whole path, its script and its platforms
scripts/red play-local                            # play it
```
- `tools/kit.py` = building blocks and movement constants; `tools/chambers.py` = the 19 chamber designs; `tools/gen_map.py` = the hub,
  the run rules, the HUD, audio and checks; `tools/routes.py` = the scripted runner (and the check that every jump is possible).
- Design rules the runner depends on are at the top of `tools/chambers.py`. Keep sideways offsets small and give real turns a deep platform.
- `lint` cannot run on this map (the chambers are spread over ~2 km and the reach grid aborts), so `checks` has no `lint` group.
- `ENGINE_FEEDBACK.md` is what this game taught about the engine.

## Rules for whoever works here next
1. `scripts/red check` before every commit and before you say "done".
2. Record progress in `STATUS.md`.
