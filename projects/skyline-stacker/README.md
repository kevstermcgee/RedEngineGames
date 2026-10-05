# Skyline Stacker

A timed crate-stacking game on Red Engine. Carry crates (`E` picks up and drops what the green crosshair points at) onto the orange pallet and build a tower of **three**
that stands for **5 seconds**, before the 120 s clock runs out. Every 25 s from the 50 s mark a big red barrel is shoved down the pink lane at your tower at 10 m/s:
finish before it arrives, rebuild after it, or pick the barrel up and park it somewhere harmless.

The score is the engine's own physics: the tower's height is counted from what is *upright* on the pallet (`props_in`, `tilt`, `prop_y`), so a toppled stack scores nothing.
Everything is data: `tools/gen_map.py` writes `maps/main.json` (rules, vars, checks). No Rust.

```bash
python3 tools/gen_map.py maps/main.json   # regenerate the map (env: NEED, STAND_OFF, LOOK_DY, WRECK_SPEED, WRECK_SCALE, WRECK_Z)
scripts/red check                         # lint + 3 scripted playthroughs (nothing built / a two-crate tower wrecked / a three-crate win)
scripts/red play-local                    # play it
```

What the physics taught the design (measured with `sim`): a fifth crate dropped from head height topples the stack, so the target is three; the barrel loses ~7 m/s^2 to
friction, so it starts 4.4 m out at 10 m/s; a solid pallet blocks the barrel, so the pallet is only paint on the floor.
