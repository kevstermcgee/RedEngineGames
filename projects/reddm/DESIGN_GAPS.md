# RedDM engine-first audit

## Already present in Red Engine

Authoritative UDP movement/combat/physics, authenticated join keys, lobby/countdown/round/results/rematch,
late join and reconnect, interest management, prediction/interpolation, headless bots, lossy-network tests,
deterministic replay, performance budgets, UPnP hosting, reproducible packaging, procedural characters,
game rules as data, and self-verifying map blueprints were all reusable as-is.

## Missing and generalized for this prototype

The engine had one ranged weapon and no standard aim control. RedDM therefore added the reusable engine
arsenal rather than building a private combat fork: eleven original firearms with shared authoritative
tuning and procedural models, stable one-byte network ids, and smooth right-mouse ADS. ADR 0038 records
the boundary and compatibility decisions. Foundry Nine also incubates modular cover and landmark prefabs
in the game-local asset pack; they should move to the core only after another game proves reuse.

## Next reusable engine milestones

1. Team assignment and team spawn groups in `MatchSim`, status snapshots and the standard scoreboard.
2. Friendly-fire policy plus team score and team win conditions in the data-driven match block.
3. Per-firearm magazines/reserves, reload timings, loadout selection and direct-slot weapon input.
4. Gameplay recoil/recovery, movement-dependent rifle accuracy and server-side lag compensation.
5. Character appearance variants driven by replicated team/skin ids.
6. Imported mesh/texture pipeline with licenses and provenance in the asset catalog.

The playable is intentionally honest about this boundary: it is a networked individual deathmatch
prototype inspired by team deathmatch, not yet a complete team ruleset.

## Shooter review pass
Held automatic fire, deterministic shotgun pellets, aligned/open sights, connected arms, zoom
sensitivity compensation and authored acceleration/friction now exist in the engine. The map
uses offset industrial routes rather than a nine-room grid. These are tested prototype mechanics,
not a claim of finished weapon art or CS-style team rules.
