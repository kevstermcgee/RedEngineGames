# Killchain development metrics

Wall-clock and token budget checkpoints (token counts are the session's remaining budget, start 15,000,000).
Each row: time | tokens left | phase | what cost the most.

| time (local) | tokens left | phase | notes |
|---|---|---|---|
| 2026-09-30 14:41 | 14,925,000 | start | read engine docs/ADRs via `search`, `describe`; engine has 10 hitscan guns, no teams/grenades/projectiles/killcam/stats |
| 2026-09-30 15:02 | 14,620,000 | engine sim core | arsenal/kit/ordnance/shooter modules + 7 sim tests green. Biggest cost so far: reading ~4k lines of engine source to find where weapons/teams/flow live (the docs said never read source; for a NEW game mode there was no other way) |
