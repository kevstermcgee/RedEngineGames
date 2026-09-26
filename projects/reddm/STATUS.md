# STATUS — RedDM

_Handoff file for whoever (human or AI) resumes this work. Keep it short and current: update it at every checkpoint with
`red_engine2 status --note "what changed" --section done|now|next|blocked|notes`._

## Now (in flight)

## Done

- Foundry Nine arena: six industrial spaces, offset doors, protected spawn exits and lane cover.
- Lobby/round/results flow configured for 2+ players, 8 minutes or 30 kills.
- Game-local procedural asset pack and performance budget.
- Uses the engine's eleven-firearm arsenal and smooth ADS implementation (ADR 0038).

## Next

- Generalize teams, friendly fire and team scoring in Red Engine.
- Add per-firearm magazines, timed reloads and loadout selection.
- Add replicated team-colored humanoid variants.

## Failing / blocked

## Decisions & gotchas

## Shooter review implementation
- Rebuilt Foundry Nine as six differently sized industrial spaces with offset doors and protected spawn exits.
- Rifle start, tactical acceleration/friction, aligned sights, open optics, connected arms, automatic fire and shotgun pellets.
- Team rules, individual magazines, timed reloads and richer art remain future work.
