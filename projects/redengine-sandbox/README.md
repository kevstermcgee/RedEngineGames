# RedEngineSandbox

A central, playable inspection and experimentation project for RedEngine.
Start **Play-RedEngineSandbox.cmd** or run `powershell -File scripts/red.ps1 play-local`.
Choose Human, Cheddar, Wizard, Cowboy, Alien or Robot. Press **M / D-pad up** to change maps
without leaving the game; aim at an exhibit to see its asset/object ID. **Q / Back** switches
to third person. Reload a map from the browser to reset experiments.

## Explore

- **Arrival Hub**: all six characters, movable props and shooting targets. Weapon cycling exposes the full arsenal.
- **Frontier Crossroads**: six enterable buildings, a main street and rear alleys for collision, sight-line and encounter tests.
- **Workshop Motion Lab**: workbenches, loose props, a guarded stair/deck route and a target lane.
- **Moon Garden**: crystals, giant mushrooms, research beacons, open exploration and two launch pads.
- **Asset galleries**: all 196 engine catalogue entries plus six local reusable assets, at their original size, split into bounded galleries.
- **Reference maps**: every engine example and recipe scene, plus local RedDM/RiftRaze snapshots when those projects are available.

The current generated project contains **35 maps and 202 catalogue exhibits**.
See [asset-index.json](asset-index.json) for exact exhibit names, coordinates, dimensions and map locations.
The game browser lists maps in project order; left/right or LB/RB changes pages.

## Test

| Action | Keyboard/mouse | Controller |
|---|---|---|
| Move / look | WASD / mouse | Left / right stick |
| Jump / crouch | Space / Ctrl | A / hold B |
| Interact / reload | E / R | X / Y |
| Fire / aim | Left / right mouse | RT / LT |
| Weapons | Wheel | LB / RB |
| Sprint | Shift | Hold left-stick click |
| View / pause | Q / Escape | Back / Start |
| Map browser | M | D-pad up; Y while paused |

The first connected pad owns gamepad input. Release controls after focus loss or a menu transition.
Keyboard/mouse still work alongside it. No controller remapping screen or rumble is included.
In the connect form, arbitrary server text needs a keyboard; A/B confirms/cancels.

The new humanoid costumes share human movement, carrying and weapon behavior. Cheddar retains its small body.
Maps can force a character; that destination policy takes priority over the current selection.
Local map travel resets props and rules. Online sessions do not expose local map travel.

## Maintain

```powershell
python scripts/generate.py
python scripts/generate.py --check
powershell -File scripts/red.ps1 check
```

`scripts/generate.py` is the source of truth for the hub, galleries and three new environments.
It reads the engine's real JSON catalogue and embeds [assets/gameplay.json](assets/gameplay.json).
The committed maps are self-contained. The generated asset index makes added engine assets discoverable on the next refresh.
The ordinary `build-all` command has no blueprints to regenerate in this project; use the generator instead.

Reference maps preserve the source scenes' collision/simulation checks. The hello-world and orbit-walk animation
demos have documented perimeter/decorative-collision adaptations for playable inspection. Three gallery exhibits
(bonsai, fruit bowl and floor lamp) disable low-overhang display collision; source assets remain unchanged.
Decorative walk-through assets are still visual exhibits, not necessarily carryable props.

Engine fixes belong in RedEngine, not in a fork or copied Rust crate. The matching engine changes require protocol v7
for multiplayer. Keep the local copy and RedEngineGames/projects/redengine-sandbox synchronized before publishing.
