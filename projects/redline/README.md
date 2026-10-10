# REDLINE

A first-person momentum roguelite on Red Engine. The reactor is redlining: dive from the Foundry through a chain of chambers over a
sea of lava, against a clock that only grows when you vent a chamber. How deep can you get before it burns down?

## How a run works

- **Dive.** Walk into the red gate in the Foundry. You start with 25 seconds on the clock.
- **Chambers.** Each chamber is a short course of gaps, steps, jump pads and hazards that ends at a green **VENT**. Venting one adds
  its par time to the clock and drops you into the next chamber, drawn at random from the tier for that depth (no repeats in a run):
  - depth 1-5, **the Intake**: gaps, stairs, jump pads, sidesteps, a split route
  - depth 6-10, **the Furnace**: crumbling floors, phase platforms (magenta and cyan take turns to exist), heat curtains, narrow beams
  - depth 11-14, **the Core**: all of it at once, longer and less forgiving
  - depth 15, **the Redline**: the finale. Vent it and you escape.
- **Par and streaks.** Every chamber has a par time (shown when you enter it, and live on the HUD). Beat it for a streak: each
  chamber under par in a row pays more sparks (up to 5x).
- **Burns.** Touch the lava or a glowing heat curtain and you are put back at the last checkpoint, and it costs you seconds.
- **Burnout.** When the clock hits zero the run is over. Everything you banked stays banked.

## Between runs: the Foundry

Sparks are kept forever (saved on your PC) and buy upgrades. Walk up to a station to read it, step on its orange plate to buy.

| station | levels | what it does |
|---|---|---|
| COOLANT | 4 | +4 s on the starting clock |
| VENTS | 4 | +1 s every time you vent a chamber |
| LAVA BOOTS | 3 | burns cost 0.8 s less |
| MAGNET | 2 | pick sparks up from further away |
| SECOND WIND | 2 | once a run, +10 s (+18 s at level 2) when the clock hits zero |
| PRISM | 1 | every spark counts double |
| OVERDRIVE KEYS | 1 | opens the locked shortcut pads that fly you over phase platforms and heat curtains |

**Heat.** Escape once and Heat 1 opens (the six pads in front of the dive gate). Each Heat gives less time per vent and bigger
burns, and pays more sparks per pickup. There are six Heats; your best depth and fastest escape are kept for each.

**Relics.** One golden relic hides in every chamber (18), off the route: on a lone pillar too far for a normal jump, or high above
a pad's arc. They need speed and air control. Each is worth 10 sparks and appears on the shrine in the Foundry.

## Controls and movement

WASD move, mouse look, Space jump, Escape pauses. You always run (no sprint key).

Movement is Quake-style: **hold Space to bunny hop**, and **strafe + turn the mouse in the air** to steer and to build speed past
the normal 9.5 m/s. Momentum does not turn in the air on its own, so line your run up before a sideways jump, or steer with the
strafe keys while you fly. Speed is how you beat par, reach relics and survive the high Heats.

## Playing it

On Windows, install it from the [RedEngineGames download site](https://kevstermcgee.github.io/RedEngineGames/). From a checkout:

```bash
scripts/red play-local      # needs the engine (game.json pins it)
```

## How it is made

Everything is data on Red Engine 2: one scene (`maps/main.json`) with vars, rules, a persisted save, a HUD and synthesized music. No
Rust. The map is generated:

```bash
python3 tools/gen_map.py maps/main.json           # write the map
python3 tools/gen_map.py maps/main.json --pars    # also re-measure every chamber's par time with the engine (then run it again)
scripts/red check                                  # every chamber proven clearable, the run loop proven (25 scenarios)
```

- `tools/kit.py`: the building blocks (platforms, pads, crumbling tiles, phase platforms, heat curtains, checkpoints, sparks, relics,
  shortcut pads, the vent) and the movement constants.
- `tools/chambers.py`: the 19 chamber designs, each a short program on a course cursor.
- `tools/gen_map.py`: the Foundry, the run rules (choose a chamber, the clock, par, streak, burns, upgrades, Heat, persistence) and the HUD.
- `tools/routes.py`: turns every chamber into a scripted runner (`checks.sim`). It holds forward at base speed, never strafe-jumps, and
  must vent the chamber without a single burn. Its time, x0.92, is the chamber's par. It also refuses to generate a jump that is too
  long to make at base speed.
- `tools/debug_route.py`, `tools/first_burn.py`: show where a scripted run went wrong, in the chamber's own coordinates.
- `maps/audio/*.json`: the scores (the Foundry's drone, the run's 150 bpm layer, the low-clock alarm layer), synthesized by the engine.

The chambers sit 520 m apart and the player is teleported between them. The run order comes from the tick you reach a vent on, so
it is different every run.

`ENGINE_FEEDBACK.md` is what building this taught about the engine.
