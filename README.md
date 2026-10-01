# RedEngineGames

Games, prototypes, test content, and demos produced with
[RedEngine](https://github.com/kevstermcgee/RedEngine).

**[Browse and download the games on the web](https://kevstermcgee.github.io/RedEngineGames/)**
or grab the ZIPs straight from the
**[latest release](../../releases/latest)**. Extract a ZIP
and double-click its `Play-*.exe` launcher; no Rust toolchain or command line is
required. The executables are not code-signed, so Windows may show a SmartScreen
warning.

- `games/` contains playable game scenes.
- `projects/` contains standalone game projects that pin a sibling RedEngine checkout.
- `prototypes/` contains data-driven recipes and their reference views.
- `tests/` contains the Red Test Lab and performance fixtures.
- `demos/` contains example scenes, golden views, and multiplayer demo scripts.

## Standalone projects

- [Gravity Gauntlet](projects/gravity-gauntlet) — a high-octane 3D physics gauntlet featuring supercharged jump pads, cascading megaton domino collapses, kinetic hazard bumpers, and four collectible plasma cores.

- [RedEngineSandbox](projects/redengine-sandbox) — an asset inspection and testing hub with 202 catalogue assets, 35 maps, six playable characters, and native controller navigation.

- [RedDM](projects/reddm) â€” an online FPS deathmatch prototype with the Foundry Nine arena,
  eleven firearms, smooth aim-down-sights, and an authoritative two-or-more-player server.
- [RiftRaze](projects/riftraze) â€” a hyperkinetic online arena FPS with 90-degree FOV,
  high-speed movement, authoritative jump pads, a shotgun start, and the Shattercore arena.

The `games/`, `prototypes/`, `tests/`, and `demos/` directories are automatically
maintained browsable copies. RedEngine is their source of truth: update
`games-publish.json` there to add or move published content. Do not edit those four
managed directories because the next synchronization will replace them. Standalone
projects under `projects/` are maintained here and are not replaced by that sync.
`.games-catalog.json` identifies the exact engine source commit and records a SHA-256
digest for every copied managed file.
Games, prototypes, tests, and demos produced with RedEngine.
