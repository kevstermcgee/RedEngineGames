#!/usr/bin/env python3
"""Generates maps/main.json: Skyline Stacker, a timed crate-stacking game (rapier crates, a sliding barrel that tries to knock the tower over).

Stack NEED crates (three; a fifth dropped from head height usually topples the lot, measured) on the pallet and keep them standing for HOLD_SECS to win before the clock runs out. The tower is counted by the engine's own
`props_in(zone)`, so the score is whatever the physics leaves standing on the pallet.

Run from the project root:   python3 tools/gen_map.py maps/main.json
"""
import json, os, sys

NEED = int(os.environ.get('NEED', 3))           # crates that must be inside the tower zone at once
HOLD_SECS = 5.0    # ...for this long
TIME = 120         # seconds on the clock
WRECK_EVERY = 25   # seconds between the barrel's runs at the tower
WRECK_SPEED = float(os.environ.get('WRECK_SPEED', 10.0))   # m/s the barrel is shoved at
WRECK_SCALE = float(os.environ.get('WRECK_SCALE', 1.0))   # a bigger barrel is heavier (mass follows volume) and, past the carry limit, cannot be lifted
WRECK_Z = float(os.environ.get('WRECK_Z', -4.4))   # where the barrel starts (sliding friction takes ~7 m/s^2 off it, so it must start close and fast)
WRECK_FROM = 90    # ...starting once the clock is down to this (the first run is at 50 s: build and hold before it, or rebuild after)

objects, zones = [], []
def add(o): objects.append(o)

# the yard: floor, a low skyline of pastel towers behind a fence, and walls that keep every crate in play
add({"id": "floor", "type": "plane", "size": [40, 30], "position": [0, 0.0, 0], "material": {"color": "#d9d2c5", "roughness": 0.95}})
add({"id": "stripe_a", "type": "plane", "size": [24, 0.3], "position": [0, 0.01, -4.5], "material": {"color": "#f4e3a1"}, "collide": False})
add({"id": "stripe_b", "type": "plane", "size": [24, 0.3], "position": [0, 0.01, 4.5], "material": {"color": "#f4e3a1"}, "collide": False})
for name, size, pos in (("wall_n", [26, 2.2, 0.4], [0, 1.1, -9.2]), ("wall_s", [26, 2.2, 0.4], [0, 1.1, 9.2]),
                        ("wall_w", [0.4, 2.2, 18.8], [-13.2, 1.1, 0]), ("wall_e", [0.4, 2.2, 18.8], [13.2, 1.1, 0])):
    add({"id": name, "type": "box", "size": size, "position": pos, "material": {"color": "#b7c4d9", "roughness": 0.9}})
skyline = [(-30, 26, 14, "#c9d7f2"), (-18, 30, 10, "#f2c9d7"), (-6, 34, 18, "#d7f2c9"), (8, 30, 12, "#f2e6c9"), (20, 28, 16, "#d7c9f2"), (33, 32, 11, "#c9f2ee")]
for k, (x, z, h, c) in enumerate(skyline):
    add({"id": f"tower_bg_{k}", "type": "box", "size": [8, h, 8], "position": [x, h / 2, -z], "material": {"color": c}, "collide": False})
    add({"id": f"tower_bg_top_{k}", "type": "box", "size": [8.4, 0.5, 8.4], "position": [x, h + 0.25, -z], "material": {"color": "#8e9ab5"}, "collide": False})

# the pallet: a painted square on the floor (no collision, so the barrel can reach the tower) and the zone that counts crates standing in it
PX, PZ = 6.0, 0.0
add({"id": "pallet", "type": "plane", "size": [3.4, 3.4], "position": [PX, 0.02, PZ], "material": {"color": "#e0a458", "roughness": 0.9}, "collide": False})
add({"id": "pallet_edge", "type": "plane", "size": [3.8, 3.8], "position": [PX, 0.015, PZ], "material": {"color": "#8a6a3f"}, "collide": False})
zones.append({"id": "tower", "rect": [PX - 1.7, PZ - 1.7, PX + 1.7, PZ + 1.7], "y": 0.0})
zones.append({"id": "yard", "rect": [-13, -9, 13, 9]})

# crates to build with: two loose rows on the west side
crate_colors = ["#ff9aa2", "#ffb7b2", "#ffdac1", "#e2f0cb", "#b5ead7", "#c7ceea", "#f6e6ff", "#ffe6a7", "#ffc4d6", "#bde0fe"]
crate_ids = []
for k in range(10):
    x, z = -6.0 + (k % 5) * 1.6, -2.4 if k < 5 else 2.4
    cid = f"crate_{k + 1}"
    crate_ids.append((cid, x, z))
    add({"id": cid, "type": "prop", "prop": "crate", "position": [x, 0, z], "material": {"color": crate_colors[k]}})

# the wrecker: a barrel that slides at the tower every WRECK_EVERY seconds; pick it up and park it out of the way if you like
add({"id": "wrecker", "type": "prop", "prop": "barrel", "position": [PX, 0, WRECK_Z], "scale": [WRECK_SCALE] * 3, "movable": True, "material": {"color": "#e05a5a"}})
add({"id": "wrecker_lane", "type": "plane", "size": [1.2, abs(WRECK_Z) - 1.6], "position": [PX, 0.013, (WRECK_Z - 1.6) / 2], "material": {"color": "#f6b8b8"}, "collide": False})

# What counts as standing. `props_in(tower)` alone would score a wrecked tower (toppled crates still lie in the zone) and the zone has no per-crate test, so:
# `upper` = crates that are upright (tilt under 30 degrees), up off the floor (so resting on another crate) and not in a hand; the tower's height is the base
# crate plus those, and only counts when the zone really holds that many (a tower built somewhere else scores nothing).
UPPER = " + ".join(f"(tilt({cid}) < 30) * (prop_y({cid}) > 0.15) * (held({cid}) == 0)" for cid, _, _ in crate_ids)
# `wrecker_in` is 1 while the barrel itself is inside the zone (props_in counts every loose prop, the barrel included).
CRATES_IN = "(props_in(tower) - wrecker_in)"
STACK_EXPR = f"({CRATES_IN} >= 1 + {UPPER}) * (1 + {UPPER}) * ({CRATES_IN} >= 1)"

rules = [
    {"id": "wrecker_enters", "when": {"prop_enter": {"zone": "tower"}, "prop": "wrecker"}, "do": [{"set": ["wrecker_in", 1]}, {"emit": "barrel_in_tower"}]},
    {"id": "wrecker_leaves", "when": {"prop_exit": {"zone": "tower"}, "prop": "wrecker"}, "do": [{"set": ["wrecker_in", 0]}]},
    {"id": "tick", "when": {"every": 1}, "do": [{"add": ["time_left", -1]}]},
    {"id": "timeup", "when": {"every": 1}, "if": "time_left <= 0", "do": [{"emit": "timeup"}, {"end": "timeup"}]},
    # count what stands on the pallet, four times a second, and chain the bookkeeping off that
    {"id": "count", "when": {"every": 0.25}, "do": [{"set": ["stacked", STACK_EXPR]}, {"emit": "counted"}]},
    {"id": "best_up", "when": {"event": "counted"}, "if": "stacked > best", "do": [{"set": ["best", "stacked"]}]},
    {"id": "hold_up", "when": {"event": "counted"}, "if": "stacked >= need", "do": [{"add": ["hold", 0.25]}]},
    {"id": "hold_lost", "when": {"event": "counted"}, "if": "stacked < need", "do": [{"set": ["hold", 0]}]},
    {"id": "win", "when": {"event": "counted"}, "if": f"hold >= {HOLD_SECS}", "do": [{"emit": "victory"}, {"end": "victory"}]},
    # the barrel goes back to its start, then is shoved at the tower a moment later (rules cannot reset and shove in one tick)
    {"id": "wreck_prep", "when": {"every": WRECK_EVERY}, "if": f"time_left <= {WRECK_FROM}", "do": [{"reset": "wrecker"}, {"emit": "wreck_go"}]},
    {"id": "wreck_go", "when": {"event": "wreck_go"}, "do": [{"impulse": {"object": "wrecker", "dir": [0, 0, 1], "speed": WRECK_SPEED}}, {"emit": "barrel_incoming"}]},
]

WRECK_FROM_S = TIME - WRECK_FROM   # game seconds until the first run

# a scripted player who builds the tower: picks up crate k, walks to the pallet's west edge, looks at the top of the stack and lets go
script = []
def approach(cx, cz):
    """The point in the aisle (z between the two crate rows) 1.1 m from a crate, straight across from it, so no other crate is bumped on the way."""
    return f"{cx:.2f},{cz + (1.1 if cz < 0 else -1.1):.2f}"
LOOK_DY_STEP = float(os.environ.get('LOOK_DY_STEP', 0.0))   # ...and how much higher per crate already in the tower (a held crate must clear the stack)
LOOK_DY = float(os.environ.get('LOOK_DY', 0.6))     # how far above the stack's top the builder aims
STAND_OFF = float(os.environ.get('STAND_OFF', 0.5))
stand_x, stand_z = PX - STAND_OFF, PZ   # a released crate lands about 0.6 m ahead of the player
for k, (cid, cx, cz) in enumerate(sorted(crate_ids[:NEED], key=lambda c: -c[1])):
    top = 0.56 * k              # top of the tower so far
    script += [
        {"player": "p1", "walk": approach(cx, cz)},
        {"player": "p1", "hold": {"look_at": [cx, 0.28, cz], "seconds": 0.2}},
        {"player": "p1", "hold": {"look_at": [cx, 0.28, cz], "interact": True, "seconds": 0.2}},
        {"player": "p1", "walk": f"{stand_x:.2f},{stand_z:.2f}"},
        {"player": "p1", "hold": {"look_at": [PX, top + LOOK_DY + LOOK_DY_STEP * k, PZ], "seconds": 0.3}},
        {"player": "p1", "hold": {"look_at": [PX, top + LOOK_DY + LOOK_DY_STEP * k, PZ], "interact": True, "seconds": 0.2}},
        {"player": "p1", "wait": 1.2},
    ]

scene = {
    "camera": {"position": [-11.5, 2.4, 0], "target": [6, 1.4, 0], "fov": 70},
    "background": {"sky_top": "#9ec9ff", "sky_bottom": "#fde7d3"},
    "ambient": {"color": "#fff4e6", "intensity": 0.6},
    "lights": [{"id": "sun", "type": "directional", "direction": [-0.5, -1.0, -0.3], "color": "#fff1d6", "intensity": 1.1}],
    "player": {"mode": "peaceful", "throw_speed": 0},
    "music": False,
    "zones": zones,
    "spawns": [{"id": "start", "position": [-10.5, 0, 0], "yaw_deg": 90, "group": "stack"}],
    "vars": {"wrecker_in": 0, "stacked": 0, "best": 0, "need": NEED, "hold": 0, "time_left": TIME},
    "rules": rules,
    "checks": {
        "lint": {"max_errors": 0},
        "sim": [
            {"name": "the clock runs out with nothing built", "players": [{"id": "p1", "character": "human", "spawn": "start"}],
             "script": [{"player": "p1", "wait": TIME + 3}], "max_seconds": TIME + 8,
             "expect": [{"ended": "timeup"}, {"var": "stacked", "eq": 0}, {"var": "best", "eq": 0}]},
            {"name": "an unfinished two-crate tower is knocked over by the barrel's run", "players": [{"id": "p1", "character": "human", "spawn": "start"}],
             "script": script[:len(script) // NEED * 2] + [{"player": "p1", "walk": "-9,6"}, {"player": "p1", "wait": WRECK_FROM_S + WRECK_EVERY + 20}], "max_seconds": 140,
             "expect": [{"event": "barrel_incoming", "min": 1}, {"prop": "wrecker", "moved": True}, {"var": "best", "gte": 2}, {"var": "stacked", "lt": 2}, {"not_ended": True}]},
            {"name": "build a three-crate tower and keep it standing", "players": [{"id": "p1", "character": "human", "spawn": "start"}],
             "script": script + [{"player": "p1", "wait": HOLD_SECS + 2}], "max_seconds": 80,
             "expect": [{"ended": "victory"}, {"var": "best", "gte": NEED}]},
        ],
    },
    "objects": objects,
}
json.dump(scene, open(sys.argv[1] if len(sys.argv) > 1 else "maps/main.json", "w"), indent=1)
print(f"wrote {len(objects)} objects, {len(rules)} rules")
