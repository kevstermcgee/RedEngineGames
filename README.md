# RedEngineGames

Games, prototypes, test content, and demos produced with
[RedEngine](https://github.com/kevstermcgee/RedEngine).

**[Browse and install the games on the web](https://kevstermcgee.github.io/RedEngineGames/)**:
each game has an installer (no administrator rights, optional desktop shortcut), updates itself when a new version is
released, keeps its saves in `Saved Games`, and every older version stays downloadable. How it works, and code signing:
[docs/DISTRIBUTION.md](docs/DISTRIBUTION.md).

- `games/` contains playable game scenes.
- `projects/` contains standalone game projects that pin a sibling RedEngine checkout.
- `prototypes/` contains data-driven recipes and their reference views.
- `tests/` contains the Red Test Lab and performance fixtures.
- `demos/` contains example scenes, golden views, and multiplayer demo scripts.

## Standalone projects

- [Redline](projects/redline) — a first-person momentum roguelite: dive from the Foundry through 19 chambers over lava against a
  draining clock, beat par for streaks, bank sparks for seven upgrades, escape to open six Heats, and hunt 18 hidden relics.

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
