# RedEngine Launcher

`RedEngineLauncher.exe` automatically lists every first-level game under `games/`
and `projects/`. Each card shows its creation date, game version, pinned RedEngine
revision, game type, and description. **Install & play** downloads the matching ZIP
from the latest RedEngineGames release into the current user's local
application-data directory, then starts its `Play-*.exe`.

Run `Install-RedEngineLauncher.cmd` to build and install the launcher and create a
desktop shortcut. The release workflow also publishes
`RedEngineLauncher-windows-x64.zip`.

The launcher catalog is generated from `.games-catalog.json`,
`.release-games.json`, repository history, and the game directories. A new game
therefore appears automatically as soon as it has the release definition required
by the repository's all-games coverage gate.
