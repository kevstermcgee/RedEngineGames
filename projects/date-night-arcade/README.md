# Date Night Arcade: Survival Edition

Three solo 2D games for passing one controller, built on Red Engine `6a42dd1ed650`.

| Game page and Windows download | World and mechanic | Controller |
| --- | --- | --- |
| [Pip Cloud Post](https://kevstermcgee.github.io/RedEngineGames/browser/pip-cloud-post/) | Bright paper-and-cloud sky. Bunny bounces, collects letters and slams into super springs. | Left/right steer; A slam; B gust |
| [Moxie Magnet Moon](https://kevstermcgee.github.io/RedEngineGames/browser/moxie-magnet-moon/) | Luminous blue cosmos. Axolotl dashes into scrap chains and clears hunters with magnetic pulses. | Stick move/aim; A dash; B pulse |
| [Riff Rooftop Rush](https://kevstermcgee.github.io/RedEngineGames/browser/riff-rooftop-rush/) | Warm sunset city. Skating fox changes rooftops and catches notes while dodging low speakers and high drones. | Up/down lanes; A hop; B center |

Four hearts, endless runs, harder waves every 20 seconds. Riff cannot farm points by jumping in place. A / Space starts the next player's turn after a result; Start or M toggles music. F toggles fullscreen. The Menu button opens audio and installation controls and pauses the run. Active gameplay shows only score/player, elapsed time, health and a relevant mechanic meter. Controls and records live on the start, game and results pages.

Each game has an original 32-bar soundtrack with eight arranged sections, alternate melodies, counterlines, bridges and percussion variations, plus its own layered effects and cycling pickup tones. Music is synthesized by Red Engine at build time and included as PCM; a worker decodes it without delaying gameplay.

## Windows installation and saves

Use **Install for Windows** on each game page and run the downloaded `.exe`. Installers include all game and music assets, need no administrator rights, create desktop and Start menu shortcuts, and launch Microsoft Edge in an app window. Windows 10/11 with Edge is required. They are unsigned. Uninstall through Windows Settings → Apps.

Desktop progress uses an isolated Edge profile in `%LOCALAPPDATA%\RedEngineGames\profiles\<game-id>`. Uninstall retains it, and reinstalling keeps records. Browser and desktop saves are separate: use **Back up progress / Restore** on the start screen to transfer them. Best scores, survival times, ranks, rounds and the next player save automatically; unfinished runs restart on reload.

## Rebuild and verify

Python 3 generates all characters, scenery, rules and scores; no third-party character or audio assets are downloaded.

```bash
python3 build_games.py
python3 polish_games.py
python3 upgrade_survival.py
python3 visual_refresh.py
red_engine2 verify pip-cloud-post/pip-cloud-post.game2d.json
red_engine2 web build pip-cloud-post/pip-cloud-post.game2d.json --out revision2/packages/pip-cloud-post
python3 package_client.py revision2/packages/pip-cloud-post
red_engine2 web verify --package revision2/packages/pip-cloud-post --out revision2/evidence/pip-cloud-post-browser
```

Repeat build/verify for each ID. Set `RED_ENGINE2` to the engine CLI path if it is not on PATH. `windows/build.py --packages revision2/packages --out revision2/windows --target x86_64-pc-windows-gnu` cross-compiles the installers with Rust and MinGW; omit `--target` on Windows. The launcher uses Rust's standard library and Windows APIs, with no downloaded runtime dependencies. Its server binds only to loopback and serves only embedded package files.

`revision2/check_upgrades.py` checks fullscreen, menu pausing, music controls, harder-wave survival, saved progress and phone layouts. Set `RED2D_WEB_ROOT=revision2/packages` when running `revision2/check_controller_v2.py` with a Playwright-enabled Python. The Windows CI workflow tests the exact release installers, including Unicode paths, embedded hashes, shortcuts, reinstalling, offline HTTP assets, blocked traversal and uninstalling.

[Engine feedback and resources](ENGINE_FEEDBACK.md) includes measured timing and evidence. Physical controller feel and human audio/gameplay judgments remain for playtesting.
