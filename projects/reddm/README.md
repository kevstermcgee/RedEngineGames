# RedDM

![RedDM key art](assets/reddm-key-art.png)

RedDM is a compact online FPS deathmatch prototype built as a separate Red Engine 2 game project.
Its current map, **Foundry Nine**, connects a freight yard and covered assembly hall through offset
doors, an outdoor service lane and covered maintenance route. Six spawns sit behind loading/dispatch screens. Players
are human combatants; the engine's Cheddar character is not part of this game.

## Play

For direct local single-player testing (no server or network connection):

```powershell
.\scripts\play-solo.ps1
```

The **RedDM Solo** desktop shortcut runs this mode. The **RedDM** shortcut hosts and joins a local online match.

On Windows, the **RedDM** desktop shortcut starts a local server and joins it automatically.
The command-line equivalent is below.

On Windows, build/check once and start the authoritative server:

```powershell
.\scripts\red.ps1 check
.\scripts\red.ps1 serve
```

Run this in a second terminal for each local player:

```powershell
.\scripts\red.ps1 play 127.0.0.1:27015
```

For internet play, the host forwards UDP 27015 or uses Red Engine's UPnP support. Use a join key for
public networks; see the engine's `docs/HOSTING.md`.

## Controls

- WASD move; Ctrl crouch; Space jump (Shift adds no speed in this tactical profile)
- Mouse look; hold left mouse for automatic firearms, click for semi-automatic weapons
- Right mouse smoothly aims down sights
- Mouse wheel cycles the bat and eleven firearms
- R reloads; E picks up/drops loose props; Q toggles third person; Esc pauses

## Match

The server owns movement, hits, damage, deaths, respawns, score and physics. A lobby requires two
ready players, then runs an eight-minute round to 30 kills, followed by results and rematch. The current
prototype scores individuals (free-for-all deathmatch); explicit team assignment, team-colored characters,
friendly-fire rules, per-gun magazines, timed reloads and weapon selection UI remain future engine milestones.
Players now start with a rifle. Movement accelerates quickly and stops with strong ground friction.
The current map is a gameplay greybox, with deliberate sightline breaks and alternative routes.

The shooter update requires matching protocol-v6 client/server binaries from the sibling engine checkout.

## Project structure

- `blueprints/main.blueprint.json` — source for Foundry Nine; builds the committed map deterministically
- `maps/main.json` — self-contained playable map
- `assets/gameplay.json` — original procedural RedDM cover and reactor prefabs
- `DESIGN_GAPS.md` — engine audit, what was generalized, and the next reusable improvements

No RedDM game code lives in RedEngine. The game pins a sibling engine checkout through `game.json`.
