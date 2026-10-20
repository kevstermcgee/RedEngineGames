# RedEngine Games app: changes

Each version's "- " lines become its release notes and the text of the update banner in the app. Bump `version` in `Cargo.toml` and add a section
here to publish a new version (`.github/workflows/launcher.yml`).

## 0.5.0

- Game families: a game's page shows which game it was forked from and which games were forked from it, and you can jump between them.
- **Fork…** on any game makes your own copy of the version you have installed, in your Forks folder, with a `FORK.md` that says how to change it (by hand or with an AI). Drop the folder back on the window to try it, or publish it as a game of your own: the site and the app show it in the original's family.
- The Fork window also has the prompt to give Claude Code in a RedEngine checkout, to fork a game from its source so it becomes part of RedEngine itself.
- Engine notes can be sent signed: with a publishing token saved, a note goes to GitHub as an issue under your name, so the maintainers know who sent it and you hear when it is fixed.
- Publishing works for every maintainer, not only the site's owner: the setup window says which kind of GitHub token a collaborator needs.

## 0.4.0

- Downloads are now part of Library: games that are downloading or waiting show at the top of Library, and the Library tab says how many. The separate Downloads tab is gone.
- A **Check for new games** button at the top right looks for new games and updates whenever you like, and says what it found. (The old refresh icon did nothing when clicked; only F5 worked.)
- Drop a game on the window to add it: a ZIP, a folder, or an .exe or .bat file (drop a screenshot with it if you have one). It goes into your library on this PC, ready to play.
- The site's owner can publish a dropped game for everyone from the same window, and drop a newer build to publish its next version.
- Engine feedback: a new tab for tips, ideas and bugs about the engine itself, not just one game. No account needed.
- The app can now install and play games that were not made with RedEngine: ready-made games uploaded as a ZIP, an .exe or a .bat file. They update like every other game.
- A game started from a .bat or .cmd file opens in its own console window, so text games can be played.

## 0.3.0

- Each game's page says at the top which version you have (or would get) and when it was released.
- When a newer version is out, a small button beside Play shows its number and release date. Click it to update.
- Every version of a game is listed in a table, as on the website, with its release date and what changed.
- Favorites: click the heart on any game to keep it in a Favorites section at the top of Games.

## 0.2.1

- Fixed: jumping around a game's page, or picking a review score, could push the whole window up and leave much of it blank.
- The app now opens maximized.

## 0.2.0

- Player reviews: rate any game out of 10 and say what you enjoyed and what you didn't, right on its page. No account needed; reviews help make the next games better.
- Pressing Escape while typing no longer leaves the page.
- Games open in fullscreen with a short "RedEngine Games" title card (with games built on the newest engine).

## 0.1.0

- The first version: every game on the site in one app, with its wiki, and one-click install, play, update and uninstall.
- Games download one at a time from a queue, are checked against their published SHA-256, and update without losing your saves.
- The app checks for a newer version of itself and updates in place when you say so.
