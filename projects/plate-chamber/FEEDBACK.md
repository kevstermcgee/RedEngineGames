# Engine feedback from building Plate Chamber

Built on RedEngine `origin/main` (2579c64), rules only. Rooms 1 and 2 solved on the first `sim` run; room 3 needed one design fix and two parameter sweeps. About 4 rounds, the fewest of the three.

**What worked:** `prop_enter` with a `prop:` filter, `collision`, `hide`/`show`, `reset` and `mass()` express a whole puzzle as data. `mass(heavy) > 3 * mass(crate_a)` makes the plate a real scale. `hold {forward, yaw_deg}` pushes a block in a scenario, and `sim` found a design flaw I had missed (a solid wall between the player and the exit: the door has to be in the wall).

**What cost time (ranked):**
1. **Lint cannot know a rule opens a door.** It reports every zone behind a closed door as an unreachable error (the engine's own example notes this). Zones have no `lint_ignore`, so I budgeted exactly four errors (`max_errors: 4`) and named them, which weakens the check for real problems. A `gated_by` on a door object (or on a zone) would fix it.
2. **`frame` and `plan` ignore rule state.** The "on" plates render because the `start` rule that hides them only runs in the game. An authored `"hidden": true` initial state would show the right picture and keep the map self-describing.
3. `prop_enter` fires on a bounce, so a crate that skims the plate opens the door for good (`once`) even though it is not resting there at the end; my first "crate is in the zone" expectation failed while the door correctly opened. A dwell rule (`{prop_in: zone, for: secs}`) would express "stays on the plate".
4. A scripted walk crosses zones on its way: it stepped on my reset pad and reset the crate it was carrying (proof the reset rule works, but a surprise).
5. Scaffolding: `new-game` assumes a blueprint map. I deleted the blueprint and edited `game.json` and the stale CLAUDE.md in all three projects. A `--kind blank` (rules and a generated map, no blueprint) would match how physics games are actually built.
