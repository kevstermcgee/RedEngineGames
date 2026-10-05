# Castle Crash

A throwing game on Red Engine. Six pieces of ammo sit on the pad behind the fence: two crates, two barrels and two heavy crates (the biggest a person can lift). Pick one up
(`E`), look up, and let go with `E` to throw it. Knock down a pyramid of 15 crates: each crate that moves more than 0.8 m or ends on its side scores 1, the red flag on top
is worth 3 more, **9 wins**, within 90 seconds. Ammo you carry back onto the pad is given back.

Everything is data (`tools/gen_map.py` writes `maps/main.json`; rules and vars, no Rust). The score reads the physics directly: `moved(id)` and `tilt(id)` per crate, `prop_below`
for the flag.

```bash
python3 tools/gen_map.py maps/main.json   # regenerate (env: THROW, GOAL, ARC)
scripts/red check                         # lint + three scripted playthroughs (no throws / lobbed throws win / flat throws fall short)
scripts/red play-local
```

What the engine's physics taught the design (measured with `sim --trace --dump-every`): every loose prop is capped at **14 m/s** (`physics::MAX_SPEED`) whatever `throw_speed` says
(the scene accepts up to 30), props are damped so a thrown crate only reaches about 8 m flat, a 16-19 degree lob lands on the castle and a flat throw falls short, and a
raised plinth in front of the castle stopped low throws, so it is only paint. Landing an exact angle is chaotic (17 misses where 16 and 18 hit), which is what makes it a skill game.
