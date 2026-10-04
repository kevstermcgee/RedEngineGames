# How games are distributed

A player installs a game with a normal Windows installer, plays it from the Start menu or a desktop shortcut, and is offered every new version from inside the game.
Every version ever released stays downloadable.

## What a player gets

| | |
|---|---|
| **Installer** | `<slug>-<N>-setup.exe`. Per-user (no administrator prompt), installs to `%LOCALAPPDATA%\Programs\<Game>`, adds a Start-menu entry, offers a desktop shortcut and registers an uninstaller under *Apps*. |
| **Saved games and settings** | `%USERPROFILE%\Saved Games\<Game>` (the engine reads it from `RE2_SAVE_DIR`). Never inside the install folder, so updating, reinstalling or moving the game cannot lose them. The uninstaller asks whether to delete them (default: keep). |
| **Update** | When the game starts it asks `…/games/<slug>/latest.json` (4 s timeout, silent when offline). If a newer version exists: *Yes* downloads the installer, checks its SHA-256 and runs it silently over the old version, then the game starts again; *No* asks next time; *Cancel* skips that version. Running a newer installer by hand does the same. |
| **Portable ZIP** | `<slug>-<N>-windows-x64.zip`, the same game as a folder. It keeps its saves in `Saved Games` too, and offers to open the download page when a new version exists. |
| **Older versions** | The game's page (`/games/<slug>/`) lists every version with what changed, the installer, the ZIP and checksums. Installing an old version over a new one works; choose *Cancel* at the update prompt to stay on it. Builds from before installers are listed as "Earlier builds" (ZIP only, newest of each day). |

## How a version is made

`releases.yml` runs on every push that changes the published games (`.games-catalog.json` is rewritten by RedEngine's *Publish games* workflow).

1. **plan** (`distribution/release_tool.py plan`): fingerprints each game (the git object ids of its files, its name and command line) and compares with the newest release of that game. Only games whose content changed get a new version `N+1`; a game never released gets version 1. Nothing changed means no Windows job at all. The history is read back from the releases themselves (a `<!-- redengine-release {…} -->` line in each release's notes), so there is no version file to keep in step.
2. **build** (Windows): builds `re2.exe` at the catalog's RedEngine revision once, then per game stages `RedEngine.exe`, `Play-<slug>.exe` (`distribution/play_launcher.rs`), the content and `play.cfg`, zips it and compiles the installer with Inno Setup (`distribution/installer.iss`). The installer's identity is a fixed GUID per game, which is what makes a newer installer an update of the old one; an update also clears the old `content` folder first.
3. **sign** (optional, see below), **finalize** (checksums, release notes), **publish**: one GitHub Release per game, tagged `<slug>-v<N>`, never rewritten.
4. **site** (`pages.yml`, after every run): `site/generate.py` rebuilds the website and each game's `latest.json` from the releases.

A new RedEngine alone does not re-release every game (that was one 28-game bundle per engine commit, which made "version" meaningless). To ship an engine change to games whose content did not change, run *Build Windows releases* by hand with **force** (every game gets a new version) or **only** (a list of slugs). **dry_run** builds everything and attaches it to the run without publishing.

## Code signing and SmartScreen

Windows SmartScreen warns about any installer that is not signed with a certificate it trusts; there is no way around that from the build side. The workflow signs the engine, the launcher and every installer when the repository has two secrets, and does nothing (the files stay unsigned) when it does not:

* `SIGN_PFX_BASE64`: a code-signing certificate (`.pfx`), base64-encoded (`[Convert]::ToBase64String([IO.File]::ReadAllBytes("cert.pfx"))`)
* `SIGN_PFX_PASSWORD`: its password

`distribution/sign.ps1` signs with SHA-256 and a timestamp and verifies each signature. Until a certificate is configured the website says "Windows protected your PC → More info → Run anyway". A certificate from a public CA (not self-signed) is what removes the warning; reputation with SmartScreen builds with downloads of a signed file, and an EV certificate is trusted immediately.

## Pieces

* `distribution/release_tool.py` (+ `test_release_tool.py`): plan, build, finalize, publish. `python3 -m unittest discover -s distribution`.
* `distribution/play_launcher.rs`: the in-game launcher and updater, no dependencies (`rustc --test` runs its tests).
* `distribution/installer.iss`: the Inno Setup script. `distribution/sign.ps1`: signing hook. `distribution/config.json`: repository and site address.
* `site/generate.py`: the website, `games/<slug>/latest.json` and `catalog.json`.
* The old *RedEngine Launcher* (a desktop app that listed the ZIP bundles) was removed; the website and the installers replace it.
