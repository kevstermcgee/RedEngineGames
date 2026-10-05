# Plate Chamber

A three-room physics puzzle on Red Engine. Each room has a pressure plate (red until something presses it, then green) and a door; a prop on the plate opens the door.

1. **Carry**: pick the crate up (`E`) and put it on the plate.
2. **Push**: the purple block is too big to lift, so shove it along the lane onto its plate. This plate is a scale: it only opens for something heavy (`mass(heavy) > 3 * mass(crate_a)`).
3. **Lob**: the plate is behind a wall you cannot climb. Throw a crate through the window (look up about 24 degrees and let go) onto it, then walk through the door to the yellow exit.

Stepping on the grey pads puts a room's crates back where they started, so no puzzle can be left unsolvable. Everything is data (`tools/gen_map.py` writes `maps/main.json`; no Rust).

```bash
python3 tools/gen_map.py maps/main.json   # regenerate (env: THROW, LOB_PITCH, HEAVY_SCALE)
scripts/red check                         # lint + three scripted playthroughs: room 1, rooms 1-2, all three rooms to the exit
scripts/red play-local
```

The lint budget names four rule-gated zones (`plate2`, `plate3`, `reset3`, `goal`): the engine's lint cannot know a rule opens a door, so it reports what is behind a closed door as unreachable; the
scenarios prove those routes open. Measured with `sim`: a lob between 20 and 28 degrees at 7 m/s clears the window and lands on the plate, 8 to 16 degrees hits the wall.
