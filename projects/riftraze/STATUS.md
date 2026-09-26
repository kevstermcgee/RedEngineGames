# STATUS — RiftRaze

_Handoff file for whoever (human or AI) resumes this work. Keep it short and current: update it at every checkpoint with
`red_engine2 status --note "what changed" --section done|now|next|blocked|notes`._

## Now (in flight)

- Final publication and desktop-shortcut verification.

## Done

- Shattercore blueprint, local prefab library and generated map.
- 90-degree FOV and high-speed movement profile with four authoritative jump pads.
- Two-player online deathmatch flow, 12 spawns, shotgun start and full firearm cycling.
- Blueprint/map checks, plan render, 20-view graphical tour and original key art.

## Next

- Playtest weapon and score tuning with more than two humans.
- Consider momentum/air-control and projectile/splash systems from `DESIGN_GAPS.md`.

## Failing / blocked

- None.

## Decisions & gotchas

- RiftRaze is a hyperkinetic arena FPS, not a Quake content or physics clone.
- Port 27016 avoids colliding with RedDM's default 27015.
- Visual rift prefabs remain game-local; reusable simulation features were upstreamed.
