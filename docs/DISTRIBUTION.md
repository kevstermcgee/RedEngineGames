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
2. **build** (Windows): builds `re2.exe` and `re2d.exe` at the catalog's RedEngine revision once, and each game's own client a planned playable names (`"binary": "killchain"`: `cargo build -p killchain`, listed by `release_tool.py binaries`), then per game stages its executable (`RedEngine.exe`, `RedEngine2D.exe` for `"kind": "2d"`, or `<binary>.exe`), `Play-<slug>.exe` (`distribution/play_launcher.rs`), the content and `play.cfg`, zips it and compiles the installer with Inno Setup (`distribution/installer.iss`). The installer's identity is a fixed GUID per game, which is what makes a newer installer an update of the old one; an update also clears the old `content` folder first.
3. **sign** (optional, see below), **finalize** (checksums, release notes), **publish**: one GitHub Release per game, tagged `<slug>-v<N>`, never rewritten.
   The notes' "What changed" lists the subjects of the commits that changed the game since its last version. A game synced from RedEngine changes here only through
   `Sync RedEngine content` commits, so each of those carries one line per RedEngine commit that changed a game (`<slug>: <subject>`, written by RedEngine's
   publish-games workflow): the subjects a game's author wrote in RedEngine are what its players read.
4. **site** (`pages.yml`, after every run): `site/generate.py` rebuilds the website and each game's `latest.json` from the releases.

A new RedEngine alone does not re-release every game (that was one 28-game bundle per engine commit, which made "version" meaningless). To ship an engine change to games whose content did not change, run *Build Windows releases* by hand with **force** (every game gets a new version) or **only** (a list of slugs). **dry_run** builds everything and attaches it to the run without publishing.

## Uploading a ready-made game

A game that is not built from this repository (made with another engine, a `.bat` text game, anything with an `.exe`) is published with
`distribution/upload_game.py`. It goes on the website and into the RedEngine Games app, which installs, plays, updates and uninstalls it like the others.

```sh
python3 distribution/upload_game.py ~/Downloads/StarMiner.zip --name "Star Miner" --description "Mine asteroids, dodge pirates." --kind 2d --thumb shot.png
python3 distribution/upload_game.py ~/Downloads/StarMiner-1.1.zip --name "Star Miner" --notes "Fixed the save bug."   # publishes version 2
python3 distribution/upload_game.py quest.bat --add story.txt --name "Text Quest" --dry-run                           # pack only, publish nothing
python3 distribution/upload_game.py ~/Downloads/StarMiner.zip                                                       # the game says its own name
```

**A game can describe itself.** Its card (`docs/GAME_METADATA.md`) holds its name, description, 2D/3D, designer, online note, what starts it and
a screenshot: `redengine-game.json` in a ZIP or folder (and the ZIP's comment), a header block in a `.bat`/`.cmd`, a record after an `.exe`'s
last byte, or the version information a program already has. `python3 distribution/game_meta.py stamp` writes one, `show` prints what a game
says. A game with a card needs no flags; a flag beats the card, and the card beats the previous release (except a description read only from an
`.exe`'s version information, which never replaces the previous release's). Every game published by this tool or
by the app carries its card, so dropping the published ZIP again fills everything in.

**Easiest: drag and drop onto the RedEngine Games app.** Drop the ZIP, folder, `.exe`, `.bat` or `.cmd` (plus a screenshot if you have one)
anywhere on the app's window. What the game says about itself is already in the form, marked "from the game"; fill in what is missing (at
least a name) and choose *Publish for everyone*. The first time, the app asks for a GitHub
fine-grained token with *Contents: Read and write* on this repository; it keeps it on that PC. Anyone without a token can still choose
*Add to my games* to play a dropped game on their own PC. The app writes exactly the release this tool writes (through a draft, so a failed
upload never shows a version without its download).

Without a terminal or the app: *Actions → Upload a game → Run workflow*, with a direct download link to the file (and optionally to a screenshot);
the name is needed only when the game does not say it.

* **What it accepts:** a `.zip`, a folder, or one `.exe`/`.bat`/`.cmd` (`--add` puts more files beside it). A ZIP holding a single folder is played from inside that folder. Other archives (7z, RAR, `.tar.gz`) are not opened, by this tool or by the app: repack the game as a ZIP.
* **What it starts:** `--run bin/Game.exe`, else the game's own `engine.name`, else its card's `entry`, else its only `.exe`, `.bat` or `.cmd` (uninstallers, setups and crash handlers are ignored; it looks one folder down when the top holds none). A program given alone is the game whatever it is called. `--args` adds arguments (else the card's, when they are for the program it starts).
* **What it publishes:** the release `<slug>-v<N>` with `<slug>-<N>-windows-x64.zip` (the game plus `engine.name` and `launch.args`, the two files the app reads, and its card as `redengine-game.json` and the ZIP's comment), an optional screenshot, and the usual `redengine-release` line with `"kind": "upload"` and what the site shows (description, 2D/3D, designer, online note). Run it again with the same name for the next version; description, 2D/3D, designer and screenshot carry over unless given again or the game's card says otherwise.
* **What players get:** the game's page offers the portable ZIP and the app; there is no installer and no in-game updater, so updates arrive through the app. The site lists it once `pages.yml` has run (a release published from a computer starts it; the workflow chains on *Upload a game*).
* **Limits:** the slug of a game built here is refused. A wiki page in `site/wiki/<slug>/` is used when present but not required. The app checks each download's SHA-256, which proves it arrived intact, not that the game is safe: upload only games you trust. Removing a game means deleting its releases (`gh release delete <slug>-v<N>`) and rerunning *Deploy download site*.

## Forks

A fork is a game made from another game's version, published as a game of its own that remembers where it came from. Its playable (or, for a
ready-made upload, its release) says `"forked_from": {"slug": <parent>, "version": <N>}`, and `"maintainer"` names whoever keeps it.

- `release_tool.py plan` copies both into every release's record (`family_fields`), so the edge outlives any later edit of the publish list.
- `upload_game.py --forked-from SLUG@N --maintainer LOGIN` does the same for an upload (an update keeps them); the app writes them when a fork it
  made (`launcher/core/src/fork.rs`) is dropped back on its window and published.
- `site/generate.py` reads the edge from the playable, else from the first release that has it (`link_families`), lists each game's `forks`,
  draws a **Family** box on every game page (the parent, the forks, and how to fork it: the prompt for an AI in a RedEngine checkout, which runs
  RedEngine's `scripts/games.py fork`, or the app's Fork button) and `/family/` with every family; `catalog.json` carries `maintainer`,
  `forked_from`, `forks` and `forkable` (`repo`, `app`, or empty for a game with its own client) for the app.

The fork tool and its checks live in RedEngine (`docs/GAMES_PUBLISHING.md`, "Forking a game"; ADR 2026-10-20-a-fork-is-a-game-of-its-own-that-names-the-version-it).

## Code signing and SmartScreen

Windows SmartScreen warns about any installer that is not signed with a certificate it trusts; there is no way around that from the build side. The workflow signs the engine, the launcher and every installer when the repository has two secrets, and does nothing (the files stay unsigned) when it does not:

* `SIGN_PFX_BASE64`: a code-signing certificate (`.pfx`), base64-encoded (`[Convert]::ToBase64String([IO.File]::ReadAllBytes("cert.pfx"))`)
* `SIGN_PFX_PASSWORD`: its password

`distribution/sign.ps1` signs with SHA-256 and a timestamp and verifies each signature. Until a certificate is configured the website says "Windows protected your PC → More info → Run anyway". A certificate from a public CA (not self-signed) is what removes the warning; reputation with SmartScreen builds with downloads of a signed file, and an EV certificate is trusted immediately.

## Pieces

* `distribution/release_tool.py` (+ `test_release_tool.py`): plan, build, finalize, publish. `python3 -m unittest discover -s distribution`.
* `distribution/play_launcher.rs`: the in-game launcher and updater, no dependencies (`rustc --test` runs its tests).
* `distribution/installer.iss`: the Inno Setup script. `distribution/sign.ps1`: signing hook. `distribution/config.json`: repository and site address.
* `distribution/upload_game.py` (+ `test_upload_game.py`): ready-made games (see above); `.github/workflows/upload-game.yml` runs it from GitHub.
* `distribution/game_meta.py` (+ `test_game_meta.py`): the game card, read and stamped (`docs/GAME_METADATA.md`); `testdata/game_meta/` holds the
  fixtures the app's reader (`launcher/core/src/meta.rs`) is tested against too.
* `site/generate.py`: the website, `games/<slug>/latest.json` and `catalog.json`.
* The old *RedEngine Launcher* (a desktop app that listed the ZIP bundles) was removed; the website and the installers replace it.
