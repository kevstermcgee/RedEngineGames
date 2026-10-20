# RedEngine Games app

A Windows app for every game on the site: it browses the catalog with each game's wiki and installs, plays, updates and uninstalls games. A
player sees Windows' "unrecognised app" warning once, when installing the app. Files the app downloads itself carry no "from the internet" mark,
so games and the app's own updates never trigger it.

| Part | What it is |
| --- | --- |
| `core/` | All the work, no window: read `catalog.json`, download a game's portable ZIP and check its SHA-256, unpack it, keep `library.json`, start a game, check for and apply the app's own update. Builds and is tested on any platform. |
| `app/` | The Tauri 2 window: turns `core` into commands and events for the page. Built on Windows by CI (it needs WebView2). |
| `ui/` | The page: plain HTML, CSS and JavaScript, no build step. |
| `tests/` | `ui_test.py` runs the page in Chromium against the live catalog with `mock_tauri.js` standing in for the window. |
| `tools/make_icons.py` | Draws `app/icons/`. |

## On a player's PC

- The app installs per user (no administrator rights) to `%LOCALAPPDATA%\RedEngine Games`.
- Games live in `%LOCALAPPDATA%\RedEngineGames\games\<slug>\v<N>\`, recorded in `library.json`. The player's favorites (the hearts) are kept in the same file, so they outlast app updates and uninstalls.
- An update unpacks the new version beside the old one and switches over only when it is complete, so a failed update leaves the game playable.
- Saves are in `%USERPROFILE%\Saved Games\<game>`, the same folder the stand-alone installers use. Uninstalling a game never touches them.
- A game starts the way its own `Play-<slug>.exe` starts it: the engine named in `engine.name` with the arguments in `launch.args`, and `RE2_SAVE_DIR` set.
  A game uploaded ready-made (`distribution/upload_game.py`) has the same two files; its `engine.name` may name a `.exe`, `.bat` or `.cmd` in a subfolder
  (it starts from that folder), and a `.bat`/`.cmd` gets a console window of its own.
- **Drop a game on the window** (a ZIP, a folder, `.exe` / `.bat` / `.cmd` files, and a screenshot if there is one): `core/src/upload.rs` copies it to
  `uploads\staging\` (what was dropped is never changed), finds what starts it with the same rules as `distribution/upload_game.py`, and asks
  for a name, what starts it, a description, 2D/3D and who designed it. **Add to my games** moves it into the library as `local` ("On this
  PC only"). **Publish for everyone** (`core/src/publish.rs`) needs a GitHub token that may write to the repository, saved once in
  `publish-token` in the library folder (or `GH_TOKEN`): it makes the release `<slug>-v<N>` as a draft, uploads the ZIP and screenshot, then
  publishes it, so the site rebuilds and every app sees the game. Dropping a build with the same name makes its next version.
- **Forks and families:** a game's page shows the game it was forked from and its forks (the catalog's `forked_from` and `forks`). **Fork…**
  (`core/src/fork.rs`) copies the installed version to `forks\<slug>\` under the library with `fork.json` (its parent and version) and a
  `FORK.md` for the player or their AI; dropping that folder back on the window reads the record (`upload::stage`), so publishing it writes
  `forked_from` and the publisher's login (`maintainer`, saved as `publish-login` beside the token) into the release record, and the site draws
  the family from it. The dialog also gives the prompt for forking from source in a RedEngine checkout (`scripts/games.py fork`).
- **Engine feedback:** a tab for notes about the engine itself (tip, idea, bug, other), sent like reviews (`reviews::send_note`) and shown from
  `public.json`'s `engine`. With a publishing token saved, a note can go out **signed**: a GitHub issue in this repository by that account
  (`reviews::signed_note`, `publish::issue`), which RedEngine's `scripts/feedback.py digest` reads as a maintainer's word. The website has the same form at `/feedback/`.
- **Player reviews:** each game's page shows its score out of 10 and every review, and has a form to leave one, anonymously. The app posts the review to the relay that the catalog names (`reviews.send`). RedEngine's `scripts/player_reviews.py` collects it into that repo's `docs/player-reviews/`, and the published ones are read back from `reviews.read` (`core/src/reviews.rs`).
- **Updating the app:** at start and every four hours the app reads the site's `launcher/latest.json`, which `site/generate.py` writes from the newest `launcher-v*` release. When it names a newer version, a banner offers **Update now**. The app then:
  1. downloads the installer and checks its SHA-256;
  2. starts a copy of itself as a helper (`--apply-update`) and quits;
  3. the helper waits for the app to close, runs the installer in passive update mode (`/P /UPDATE`), and opens the new version.

  If games are downloading, the update waits until they finish.

## Develop

```sh
cargo test --manifest-path launcher/Cargo.toml -p redengine-games-core     # the library
cargo run  --manifest-path launcher/Cargo.toml -p redengine-games-core --example live   # a real install, update and uninstall from the site, in a temp folder
python3 launcher/tests/ui_test.py --shots /tmp/shots                        # the page (pip install playwright; python -m playwright install chromium)
cd launcher/app && npx @tauri-apps/cli@2 dev                                # the app itself (Windows, or Linux with WebKitGTK)
```

## Release

Bump `version` in `launcher/Cargo.toml` and add a `## <version>` section to `CHANGELOG.md`. On `main`, `.github/workflows/launcher.yml` then:

1. tests the app;
2. builds `RedEngineGames-<version>-setup.exe` on Windows;
3. publishes it as the release `launcher-v<version>`.

The site rebuilds after that run. It offers the new installer on the front page and in `launcher/latest.json`, and installed apps offer to update.
