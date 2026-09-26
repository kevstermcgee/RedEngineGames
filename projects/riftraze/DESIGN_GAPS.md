# RiftRaze engine audit

## Added to Red Engine

- Bounded scene-level human movement tuning for FOV, walk/sprint speed, crouch speed, jump speed
  and gravity. The same data now drives offline play, the authoritative server, bots and prediction.
- Deterministic rectangular jump pads implemented in the renderer-free simulation, with client
  prediction and reconciliation using the same pad definitions.
- A `weapons.starting` field accepting any built-in firearm, instead of forcing every game to begin
  with the legacy bat.
- Strict schema errors, self-description, glossary/spec coverage, feature ownership and ADR 0039 for
  these additions.

## Deliberately still game-local

- `rift_pad`, `rift_pylon` and `shatter_core` are original RiftRaze art direction, stored in the
  project's prefab library rather than making a one-game visual theme part of the core engine.
- Shattercore's layout, match tuning and key art belong only to RiftRaze.

## Best next reusable improvements

1. Further playtesting and tuning of the new shared momentum, air acceleration, friction and speed
   cap. It is an authored arena profile, not an exact reproduction of Quake physics.
2. Projectile weapons, splash damage and self-knockback for rocket-jump-style routes. Current firearms
   are hitscan (the shotgun now uses multiple pellets) and jump pads are vertical impulses.
3. Map-authored weapon/ammo/health pickups plus respawn timers, followed by an arena loadout UI.
4. Directed launch volumes for authored horizontal arcs, added explicitly rather than overloading the
   predictable vertical jump-pad behavior.
5. Team, capture-the-flag and round-elimination rule components that can be shared with RedDM and
   future games.

## Shooter review pass
Shattercore now uses one connected arena with upper galleries, real stair routes and two launch
pads. The shared engine supports held automatic fire, deterministic shotgun pellets, aligned/open
sights and connected arms. Both stair approaches have actual momentum-simulation checks.
