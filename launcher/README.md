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
- Games live in `%LOCALAPPDATA%\RedEngineGames\games\<slug>\v<N>\`, recorded in `library.json`.
- An update unpacks the new version beside the old one and switches over only when it is complete, so a failed update leaves the game playable.
- Saves are in `%USERPROFILE%\Saved Games\<game>`, the same folder the stand-alone installers use. Uninstalling a game never touches them.
- A game starts the way its own `Play-<slug>.exe` starts it: the engine named in `engine.name` with the arguments in `launch.args`, and `RE2_SAVE_DIR` set.
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
