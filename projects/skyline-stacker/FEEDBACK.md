# Engine feedback from building Skyline Stacker

Built on RedEngine `origin/main` (2579c64) with no Rust: a 160-line Python generator writes the map, rules and three `sim` scenarios. About 14 edit-and-run rounds, most of them tuning physics, not writing rules.

**What worked:** the rule language reads physics directly (`props_in`, `tilt`, `prop_y`, `held`), comparisons evaluate to 1 or 0 so a score is plain arithmetic, and `sim` scenarios drive the real pick-up and drop, so "a tower of three stands for 5 s" is a passing test, not a hope. `sim --trace --dump-every 15` found the real bug (the barrel never reached the tower: friction stopped it 2.7 m out).

**What cost time (ranked):**
1. Scripted stacking is chaotic. The same script flipped between pass and fail when I changed only the barrel's size. I had to sweep the standing offset and aim height and pick the middle of a passing band (0.45-0.52 m). A `sim --sweep VAR=a,b,c` (run a scenario over a list of generator values) would have saved a dozen manual loops.
2. `_`-prefixed variable names are silently dropped from `vars` (`strict.rs`: keys starting with `_` are treated as annotations), although the docs say `_` variables are the internal ones the HUD hides. The error then says "unknown variable `_in_1`, declare it in `vars`" while it is declared.
3. `props_in(zone)` counts every loose prop, hazards and toppled crates included, and there is no per-prop zone test in expressions, so a wrecked tower still scored. I built the count from `tilt`/`prop_y`/`held` sums and a `wrecker_in` flag. Something like `props_in(zone, upright)` would remove 30 lines.
4. A solid pallet slab blocked the barrel, so the "collapse" only came from vibration. The pallet had to become paint on the floor. Loose props are all box colliders with one density (mass = volume) and friction 0.7: a barrel tips over instead of sliding, and needs 10 m/s from 4.4 m out to arrive at 5 m/s. None of that is in `describe physics`.
5. A scenario ends when its scripts end, so timer rules need explicit `wait`s.

**Would like:** `describe physics` listing gravity, damping, friction, restitution, density and the carry limit; `sim --watch <prop>` printing one prop's path (I parsed trace dumps by index).
