# STATUS — RiftRaze

_Handoff file for whoever (human or AI) resumes this work. Keep it short and current: update it at every checkpoint with
`red_engine2 status --note "what changed" --section done|now|next|blocked|notes`._

## Now (in flight)

- Human playtesting of the revised arena and movement.

## Done

- Shattercore blueprint, local prefab library and generated map.
- 90-degree FOV and high-speed movement profile with two authoritative jump pads.
- Two-player online deathmatch flow, 12 spawns, shotgun start and full firearm cycling.
- Blueprint/map checks, plan render, 20-view graphical tour and original key art.

## Next

- Playtest weapon and score tuning with more than two humans.
- Add projectile/splash systems and tune the implemented momentum/air-control from `DESIGN_GAPS.md`.

## Failing / blocked

- None.

## Decisions & gotchas

- RiftRaze is a hyperkinetic arena FPS, not a Quake content or physics clone.
- Port 27016 avoids colliding with RedDM's default 27015.
- Visual rift prefabs remain game-local; reusable simulation features were upstreamed.

## Shooter review implementation
- Replaced the nine-room grid with a connected arena, upper galleries, stair approaches and two launch pads.
- Added shared horizontal momentum, air strafing, ground friction, aligned sights and true shotgun pellets.
- Stair ascents are tested through MatchSim; upper gallery routes have collision walk checks.
- Projectiles, self-knockback, timed pickups and richer art remain future work.
