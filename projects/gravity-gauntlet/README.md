# Gravity Gauntlet

A high-octane 3D physics gauntlet built on RedEngine. Master supercharged aerial jump pads, trigger cascading physical domino collapses, weave through kinetic pinball storm bouncers, and collect all four elemental plasma cores to breach the Victory Nexus!

## Gameplay & Features

- **Acrobatic Traversal**: High-speed locomotion (`sprint_speed: 10.5`, `jump_speed: 7.0`, `air_acceleration: 8.0`) paired with authoritative high-impulse jump pads that launch you soaring through the air.
- **Authoritative Hitscan Arsenal**: Armed with a wooden bat and infinite-ammo silver revolver; firearms exert physical knockback impulse on dynamic props.
- **Megaton Domino Demolition**: Step on the detonator pad (or shoot the lead domino) to unleash a 5-bank domino chain reaction, crashing physics slabs into each other with clattering physical impacts.
- **Kinetic Pinball Hazard Chamber**: Weave through floating kinetic hazard bumpers constantly propelled by periodic cross-axis impulses.
- **Four Plasma Cores**:
  - *Core Alpha*: High aerial orb above the launch pad.
  - *Core Beta*: Hidden within the domino demolition bunker.
  - *Core Gamma*: Dancing in the heart of the pinball hazard vortex.
  - *Core Delta*: Perched on the elevated pedestal in the Nexus chamber.
- **The Victory Nexus**: The exit portal stays locked until all 4 cores are secured. Stepping into the unlocked portal triggers victory!

## Controls

- **WASD**: Move (high air control and agility)
- **Shift**: Sprint
- **Space**: Jump (or step onto glowing Cyan Jump Pads to launch)
- **Mouse Wheel**: Cycle weapon (Bat / Revolver)
- **Left Click**: Fire / Attack (knocks back physics props)
- **Right Mouse**: Smooth Aim-Down-Sights (ADS)

## Verify & Run

```sh
RED_HEADLESS=1 scripts/red check
```

Run locally:
```sh
scripts/red play-local
```

On Windows, double-click `Play-Gravity-Gauntlet.cmd` to play, or `Install-Desktop-Shortcut.cmd` to place a launcher directly on your Desktop.
