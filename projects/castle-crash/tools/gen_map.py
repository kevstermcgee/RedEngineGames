#!/usr/bin/env python3
"""Generates maps/main.json: Castle Crash, a throwing game. Six pieces of ammo (crates, barrels, one heavy crate) to demolish a pyramid of 15 crates with a flag on top.

A thrown prop leaves the hand with the holder's velocity plus `player.throw_speed` along the look (engine ADR "one release velocity"), so every piece flies at the same
speed and a heavier one carries more momentum. The score is read straight from the physics: a castle crate counts as knocked when it has moved more than a
crate's width from where the map put it, or lies on its side (`moved()` and `tilt()`); the flag is worth three more when it falls.

Run from the project root:   python3 tools/gen_map.py maps/main.json
"""
import json, os, sys

THROW = float(os.environ.get("THROW", 14))       # m/s a thrown prop leaves the hand with. The engine caps every prop at 14 m/s (physics::MAX_SPEED), so more does nothing
GOAL = int(os.environ.get("GOAL", 9))            # points to win: crates knocked down, plus 3 for the flag
TIME = 90
ROWS = 5                                         # the pyramid: 5, 4, 3, 2, 1 crates = 15
ARC = [float(a) for a in os.environ.get("ARC", "16,18,19,16,18,17").split(",")]   # launch pitches (degrees) the scripted thrower tries; a window around 16-19 clears the ground and lands on the castle (found by sweeping: props are damped, so a drag-free arc overshoots)
FRONT_Z = -7.6                                   # the castle's front face
THROW_FROM = (5.0, 1.05)                         # where a thrown crate leaves the hand: the player's z, and about this high (measured from a trace)

def launch_pitch(dz, ty, v):
    """The lower launch angle (radians) at which a prop leaving the hand at THROW_FROM's height with speed `v` is `ty` m high after travelling `dz` m across."""
    import math
    best = None
    for i in range(1, 900):
        th = math.radians(i * 0.05)
        t = dz / (v * math.cos(th))
        y = THROW_FROM[1] + v * math.sin(th) * t - 4.9 * t * t
        if best is None or abs(y - ty) < best[0]:
            best = (abs(y - ty), th)
        if y > ty and i > 1:
            return th
    return best[1]

objects, zones = [], []
def add(o): objects.append(o)

# the field: a floor, a long fence that keeps the thrower back, a plinth for the castle and a painted line at the ammo pad
add({"id": "floor", "type": "plane", "size": [40, 44], "position": [0, 0.0, 0], "material": {"color": "#c9e4c5", "roughness": 0.95}})
add({"id": "fence", "type": "box", "size": [26, 0.9, 0.25], "position": [0, 0.45, 3.0], "material": {"color": "#f7d9a8", "roughness": 0.9}})
for k in range(-6, 7):
    add({"id": f"fence_post_{k + 6}", "type": "box", "size": [0.3, 1.25, 0.3], "position": [k * 2.0, 0.625, 3.0], "material": {"color": "#c9915a"}, "collide": False})
for name, size, pos in (("wall_w", [0.4, 3, 44], [-13.2, 1.5, 0]), ("wall_e", [0.4, 3, 44], [13.2, 1.5, 0]), ("wall_s", [26, 3, 0.4], [0, 1.5, 13.2]), ("wall_n", [26, 6, 0.4], [0, 3, -21.2])):
    add({"id": name, "type": "box", "size": size, "position": pos, "material": {"color": "#b7c4d9"}})
CZ = -8.0                                       # the castle's depth (z)
add({"id": "footing", "type": "plane", "size": [7.4, 3.2], "position": [0, 0.02, CZ], "material": {"color": "#a3a3b8"}, "collide": False})   # paint only: a raised plinth stopped low throws
add({"id": "pad", "type": "plane", "size": [13.6, 3.4], "position": [0, 0.02, 8.4], "material": {"color": "#ffd6a5"}, "collide": False})
zones.append({"id": "depot", "rect": [-6.8, 6.7, 6.8, 10.1], "y": 0.0})

# the castle: a wall of crates, five, four, three, two, one; each row sits between the two crates under it
castle = []
colors = ["#a0c4ff", "#bdb2ff", "#ffc6ff", "#caffbf", "#fdffb6", "#9bf6ff"]
for r in range(ROWS):
    n = ROWS - r
    for c in range(n):
        x = (c - (n - 1) / 2) * 0.58
        cid = f"block_{r}_{c}"
        castle.append(cid)
        add({"id": cid, "type": "prop", "prop": "crate", "position": [round(x, 3), r * 0.565, CZ], "material": {"color": colors[(r + c) % len(colors)]}})
add({"id": "flag", "type": "prop", "prop": "traffic_cone", "position": [0, ROWS * 0.565, CZ], "material": {"color": "#ff5c7a"}})

# the ammo, on the pad: light and quick, medium, and one heavy crate as big as a person can lift
ammo = [("ammo_crate_1", "crate", 1.0, -5.5), ("ammo_crate_2", "crate", 1.0, -3.3), ("ammo_barrel_1", "barrel", 1.0, -1.1),
        ("ammo_barrel_2", "barrel", 1.0, 1.1), ("ammo_heavy_1", "crate", 1.35, 3.3), ("ammo_heavy_2", "crate", 1.35, 5.5)]
for aid, prop, scale, x in ammo:
    add({"id": aid, "type": "prop", "prop": prop, "position": [x, 0, 8.4], "scale": [scale] * 3, "material": {"color": "#ff8fa3" if prop == "crate" else "#ffb347"}})

CRATES = " + ".join(f"((moved({c}) > 0.8) || (tilt({c}) > 45))" for c in castle)
rules = [
    {"id": "tick", "when": {"every": 1}, "do": [{"add": ["time_left", -1]}]},
    {"id": "timeup", "when": {"every": 1}, "if": "time_left <= 0", "do": [{"emit": "timeup"}, {"end": "timeup"}]},
    # ammo leaves the pad: one less throw (carrying it back onto the pad gives it back)
    {"id": "ammo_out", "when": {"prop_exit": {"zone": "depot"}}, "do": [{"add": ["ammo", -1]}]},
    {"id": "ammo_back", "when": {"prop_enter": {"zone": "depot"}}, "do": [{"add": ["ammo", 1]}]},
    {"id": "flag_down", "when": {"prop_below": ["flag", (ROWS - 1) * 0.565 + 0.3]}, "once": True, "do": [{"set": ["flag_down", 1]}, {"emit": "flag"}]},
    {"id": "count", "when": {"every": 0.25}, "do": [{"set": ["knocked", CRATES]}, {"set": ["score", "knocked + 3 * flag_down"]}, {"emit": "counted"}]},
    {"id": "win", "when": {"event": "counted"}, "if": "score >= goal", "do": [{"emit": "victory"}, {"end": "victory"}]},
]

# a scripted thrower: fetch ammo k, stand behind the fence, aim at the castle and let go
script = []
def throw(aid, x, pitch):
    import math
    th = math.radians(pitch)
    far = 30.0
    aim = [0, 1.7 + far * math.tan(th), THROW_FROM[0] - far]      # a point far along the launch direction (the eye is 1.7 m up)
    return [
        {"player": "p1", "walk": f"{x:.2f},7.0"},                                      # the throwing side of the pad (the fence side)
        {"player": "p1", "hold": {"look_at": [x, 0.3, 8.4], "seconds": 0.2}},
        {"player": "p1", "hold": {"look_at": [x, 0.3, 8.4], "interact": True, "seconds": 0.2}},
        {"player": "p1", "walk": "0,5.0"},
        {"player": "p1", "hold": {"look_at": aim, "seconds": 0.3}},
        {"player": "p1", "hold": {"look_at": aim, "interact": True, "seconds": 0.2}},
        {"player": "p1", "wait": 2.5},
    ]
arc_script, flat_script = [], []
for k, (aid, prop, scale, x) in enumerate(ammo):
    arc_script += throw(aid, x, ARC[k % len(ARC)])     # a thrower who tries different angles, as a person would
    flat_script += throw(aid, x, 6)                    # every throw nearly flat

scene = {
    "camera": {"position": [0, 3.5, 14], "target": [0, 1.5, CZ], "fov": 65},
    "background": {"sky_top": "#a2d2ff", "sky_bottom": "#ffe5d9"},
    "ambient": {"color": "#fff4e6", "intensity": 0.62},
    "lights": [{"id": "sun", "type": "directional", "direction": [-0.4, -1.0, -0.5], "color": "#fff1d6", "intensity": 1.1}],
    "player": {"mode": "peaceful", "throw_speed": THROW},
    "music": False,
    "zones": zones,
    "spawns": [{"id": "start", "position": [0, 0, 5.4], "yaw_deg": 0, "group": "thrower"}],
    "vars": {"ammo": len(ammo), "knocked": 0, "flag_down": 0, "score": 0, "goal": GOAL, "time_left": TIME},
    "rules": rules,
    "checks": {
        "lint": {"max_errors": 0},
        "sim": [
            {"name": "with no throws the castle stands and the clock ends the game", "players": [{"id": "p1", "character": "human", "spawn": "start"}],
             "script": [{"player": "p1", "wait": TIME + 3}], "max_seconds": TIME + 8,
             "expect": [{"ended": "timeup"}, {"var": "knocked", "eq": 0}, {"var": "score", "eq": 0}, {"var": "ammo", "eq": len(ammo)}]},
            {"name": "lobbed throws (16 to 19 degrees) bring the castle down and win", "players": [{"id": "p1", "character": "human", "spawn": "start"}],
             "script": arc_script, "max_seconds": 80,
             "expect": [{"ended": "victory"}, {"var": "knocked", "gte": 5}, {"var": "flag_down", "eq": 1}, {"var": "ammo", "gte": 1}]},
            {"name": "six flat throws fall short and the castle stands", "players": [{"id": "p1", "character": "human", "spawn": "start"}],
             "script": flat_script, "max_seconds": 80,
             "expect": [{"var": "ammo", "eq": 0}, {"var": "knocked", "eq": 0}, {"var": "score", "eq": 0}, {"not_ended": True}]},
        ],
    },
    "objects": objects,
}
json.dump(scene, open(sys.argv[1] if len(sys.argv) > 1 else "maps/main.json", "w"), indent=1)
print(f"wrote {len(objects)} objects, {len(rules)} rules")
