# RedEngineGames

Games, prototypes, test content, and demos produced with
[RedEngine](https://github.com/kevstermcgee/RedEngine).

**[Download ready-to-play Windows builds](../../releases/latest).** Extract a ZIP
and double-click its `Play-*.exe` launcher; no Rust toolchain or command line is
required. The executables are not code-signed, so Windows may show a SmartScreen
warning.

- `games/` contains playable game scenes.
- `prototypes/` contains data-driven recipes and their reference views.
- `tests/` contains the Red Test Lab and performance fixtures.
- `demos/` contains example scenes, golden views, and multiplayer demo scripts.

This repository is an automatically maintained, browsable copy. RedEngine is the
source of truth: update `games-publish.json` there to add or move published content.
Do not edit the four managed directories here because the next synchronization will
replace them. `.games-catalog.json` identifies the exact source commit and records a
SHA-256 digest for every copied file.
Games, prototypes, tests, and demos produced with RedEngine.
