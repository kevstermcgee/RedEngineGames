# Engine feedback from building Castle Crash

Built on RedEngine `origin/main` (2579c64), rules and vars only. About 9 rounds; the throwing physics was the whole design problem.

**What worked:** scoring straight from the physics is elegant: `moved(id)` and `tilt(id)` per crate plus `prop_below` for the flag needed no Rust. Throwing is a real, provable mechanic (`player.throw_speed`, `release_velocity`), and a scenario can throw and assert the castle fell.

**What cost time (ranked):**
1. **An undocumented 14 m/s cap.** The scene accepts `throw_speed` up to 30, but every loose prop is clamped to `MAX_SPEED = 14` in `physics/mod.rs`; 20 and 30 behave exactly like 14. I found it by tracing a throw and noticing the speed saturated at 13.6. The schema should clamp to 14 or the docs should say so.
2. **Damping.** A crate thrown flat travels only about 8 m; horizontal speed decays (about 11.7 m/s effective). My drag-free arc solver overshot, so I swept the launch pitch instead. A lob between 16 and 19 degrees hits, and it is non-monotonic (17 misses where 16 and 18 hit): stacking contacts make it chaotic, which made it a skill game but made the test tolerant by design.
3. **Silent pickup failure.** The heavy crate at scale 1.37 was 0.451 m^3, a hair over the 0.45 m^3 carry limit: the scenario only showed an `interact` event with no `pickup`. A lint warning ("movable prop too big to carry") or a `sim` message ("nothing in reach / too heavy") would have shown it at once.
4. A carried prop sweeps sideways as the player turns and shoves its neighbours (the first ammo row was too tight), and the spawn placed behind the ammo made my first walk plow through it.
5. A raised plinth under the castle stopped low throws; the engine's lint said nothing, since it is not a bug.

**Would like:** the physics constants in `describe physics` (gravity, damping, MAX_SPEED, carry limits); a ballistic aim helper for scripted throws.
