# RedEngineGames

Games, prototypes, test content, and demos produced with
[RedEngine](https://github.com/kevstermcgee/RedEngine).

**[Download ready-to-play Windows builds](../../releases/latest).** Extract a ZIP
and double-click its `Play-*.exe` launcher; no Rust toolchain or command line is
required. The executables are not code-signed, so Windows may show a SmartScreen
warning.

- `games/` contains playable game scenes.
- `projects/` contains standalone game projects that pin a sibling RedEngine checkout.
- `prototypes/` contains data-driven recipes and their reference views.
- `tests/` contains the Red Test Lab and performance fixtures.
- `demos/` contains example scenes, golden views, and multiplayer demo scripts.

## Standalone projects

- [RedDM](projects/reddm) — an online FPS deathmatch prototype with the Foundry Nine arena,
  eleven firearms, smooth aim-down-sights, and an authoritative two-or-more-player server.
- [RiftRaze](projects/riftraze) — a hyperkinetic online arena FPS with 90-degree FOV,
  high-speed movement, authoritative jump pads, a shotgun start, and the Shattercore arena.

The `games/`, `prototypes/`, `tests/`, and `demos/` directories are automatically
maintained browsable copies. RedEngine is their source of truth: update
`games-publish.json` there to add or move published content. Do not edit those four
managed directories because the next synchronization will replace them. Standalone
projects under `projects/` are maintained here and are not replaced by that sync.
`.games-catalog.json` identifies the exact engine source commit and records a SHA-256
digest for every copied managed file.
Games, prototypes, tests, and demos produced with RedEngine.
