# RiftRaze

![RiftRaze key art](assets/riftraze-key-art.png)

**RiftRaze** is a hyperkinetic online arena FPS built as a standalone Red Engine 2 game.
Its current arena, **Shattercore**, is one connected combat volume with a central rift monolith,
three connected upper galleries, two stair approaches, lower routes and two cyan launch pads.

The movement profile uses a 95-degree field of view, 9 m/s base movement, ground acceleration/friction,
air strafing and retained horizontal momentum capped at 20 m/s. Shift adds no extra speed. Players
are human combatants, spawn with the shotgun and can cycle through the engine's full eleven-firearm arsenal.

## Play

For direct local single-player testing (no server or network connection):

```powershell
.\scripts\play-solo.ps1
```

The **RiftRaze Solo** desktop shortcut runs this mode. The **RiftRaze** shortcut hosts and joins a local online match.

On Windows, the **RiftRaze** desktop shortcut starts a local authoritative server and joins it.
The command-line equivalent is:

```powershell
.\scripts\red.ps1 check
.\scripts\red.ps1 serve
```

Then, in a second terminal for every player:

```powershell
.\scripts\red.ps1 play 127.0.0.1:27016
```

For LAN play, use the host computer's LAN address. For internet play, forward UDP 27016 or use
Red Engine's UPnP option and a join key; see the engine's `docs/HOSTING.md`.

## Controls

- WASD move/air-strafe; Ctrl crouch; Space jump
- Mouse look; hold left mouse for automatic weapons, click for semi-automatic weapons; right mouse aims
- Mouse wheel cycles weapons; R reloads
- E picks up or drops loose props; Q toggles third person; Esc pauses

## Match

The authoritative server owns movement, launch-pad impulses, hits, health, respawns and score.
Two ready players begin a seven-minute free-for-all round; first to 40 wins. Shattercore provides
eight arena spawns; two additional spawns belong only to the automated route-check group.
The four unguarded stair-edge drops are intentional arena movement routes and explicitly budgeted in lint.
Both stair ascents are tested through the real momentum simulation, and all upper galleries have route checks.

This is a gameplay greybox. Rockets/splash/self-knockback, timed pickups and a dedicated arena arsenal
are still missing. The momentum update requires matching protocol-v6 client/server binaries.

## Project structure

- `blueprints/main.blueprint.json` — authored source for Shattercore
- `maps/main.json` — deterministic, self-contained playable map
- `assets/gameplay.json` — original procedural rift pad, pylon and Shattercore prefabs
- `outputs/` — rendered map previews
- `DESIGN_GAPS.md` — engine audit and logical future improvements

The project does not fork or embed Red Engine. It exercises reusable engine features added during
development: scene-authored movement/FOV, authoritative jump pads and configurable starting weapons.
