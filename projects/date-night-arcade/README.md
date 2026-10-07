# Date Night Arcade

Three original 2D solo arcade games for passing one controller, built with Red Engine `6a42dd1ed650`.

| Play | Character and mechanic | Controller | Keyboard |
| --- | --- | --- | --- |
| [Pip Cloud Post](https://kevstermcgee.github.io/RedEngineGames/play/games/pip-cloud-post/) | Cloud rabbit with automatic bounces and slam boosts | Left/right to steer, A to slam, B for music | Arrows, Space, X |
| [Moxie Magnet Moon](https://kevstermcgee.github.io/RedEngineGames/play/games/moxie-magnet-moon/) | Axolotl with snap dashes and magnetic scrap chains | Stick to aim/move, A to snap, B for a stationary pulse | Arrows/WASD, Space, X |
| [Riff Rooftop Rush](https://kevstermcgee.github.io/RedEngineGames/play/games/riff-rooftop-rush/) | Skating fox with three rails and timed aerial tricks | Up/down for lanes, A to hop, B to center | Up/down, Space, X |

Connect a standard controller and open a game in a desktop browser. Click or press a key once to start audio if needed. A or Space starts the next player's turn after a result. Start toggles music. Each round lasts at most 45 seconds; fast wins and remaining hearts add bonus points. Riff's gold meter is the timing reference.

P1 and P2 have separate high scores and share a five rank mastery ladder. Scores, wins, rounds, rank and next turn auto-save. Unfinished rounds restart on reload. Use the start card's backup and restore controls to move saves between devices. The games can be installed from the browser and run offline after the initial visit.

## Source and development

Each character, sprite, score and mechanic is defined in its game's `.game2d.json`. There are no downloaded character or music assets. `build_games.py` and `polish_games.py` rebuild the definitions with Python 3. Native and browser verification use the pinned Red Engine checkout:

```bash
python3 build_games.py
python3 polish_games.py
red_engine2 verify pip-cloud-post/pip-cloud-post.game2d.json
red_engine2 web verify pip-cloud-post/pip-cloud-post.game2d.json
```

Repeat the last two commands for Moxie and Riff. `check_controller_saves.py` adds controller ability and progress reload checks using Playwright; set `RED2D_WEB_ROOT` to the directory containing built web packages before running it.

[Engine feedback and measured resources](ENGINE_FEEDBACK.md) documents timing, byte sizes, memory measurements, verification and improvements. `evidence/metrics.json` and `evidence/controller-progress.json` provide structured results. Physical controllers and human playtesting remain unqualified; the simulated browser paths pass.
