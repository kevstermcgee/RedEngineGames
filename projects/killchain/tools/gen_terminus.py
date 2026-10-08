#!/usr/bin/env python3
"""Generates maps/terminus.json: TERMINUS, Killchain's close-quarters night map.

A small railway terminus after the last train: Ridgeback holds the west ticket hall, Nightfall the east one, a tall concourse sits between
them, and two platforms (north and south) run alongside it with a parked train each, a canopy over them and signal lamps down the line.
About 118 x 78 m with doors you can count: the shortest map, made for duels, small teams and search and destroy. Point-symmetric.
Modes: capture the flag (flags in the ticket halls), search and destroy (attackers west; site A in the concourse's east end, site B on the
north-east platform), free for all (neutral spawns spread through the station).
Run: python3 tools/gen_terminus.py  (then tools/prune_nav.py maps/terminus.json)
"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mapkit as mk
from mapkit import objs, solids, pick, spawns, lights, box, cyl, mat, nid, free, spot, room

W, H = 59, 39
mk.configure(W, H, ground=(150, 100), seed=33, step=5.0)
rnd = mk.rnd

TILE, WALL_A, WALL_B, TRIM, DARKW = "#5d636b", "#b4ac96", "#7b8a78", "#c9a227", "#2c3238"
WOOD, CARRIAGE, CARR2, STEEL, RAIL = "#6b4d33", "#7b2f2b", "#2f4f6b", "#5a626b", "#8a8f96"

objs.append({"id": "ground", "type": "plane", "size": [150, 100], "material": mat(TILE, 0.85)})
# the outer wall of the station yard
for (x, z, sx, sz) in [(0, -H - 1, 2 * W + 4, 2), (0, H + 1, 2 * W + 4, 2), (-W - 1, 0, 2, 2 * H), (W + 1, 0, 2, 2 * H)]:
    box("yard_wall", x, z, sx, 8, sz, "#4a4f55", rough=0.95)
    box("yard_wall_cap", x, z, sx + 0.4, 0.5, sz + 0.4, DARKW, y=8)

def lamp(x, z, y=4.6, color="#ffd9a0", intensity=7, rng=16):
    mk.light("point", x, y, z, color, intensity * 1.7, rng * 1.2)

def ticket_hall(sgn):
    """The base: a hall with three doors onto the passage and one onto each platform lane. sgn -1 = west (Ridgeback), +1 = east (Nightfall)."""
    x0, x1 = (-57, -37) if sgn < 0 else (37, 57)
    doors = {("e" if sgn < 0 else "w"): [(-10, 4.0), (0, 4.0), (10, 4.0)], "n": [((x0 + x1) / 2, 4.0)], "s": [((x0 + x1) / 2, 4.0)]}
    room(x0, -14, x1, 14, 5.6, doors, WALL_A, label="hall", windows=[("n", x0 + 3.5, 1.8), ("n", x1 - 3.5, 1.8), ("s", x0 + 3.5, 1.8), ("s", x1 - 3.5, 1.8)])
    # ticket counters, benches, pillars: cover that still leaves lanes
    cx = (x0 + x1) / 2
    far = x0 + 2.5 if sgn < 0 else x1 - 2.5            # the back wall side
    box("counter", far, 0, 1.4, 1.2, 12, WOOD, rough=0.7)
    box("counter_top", far, 0, 1.7, 0.15, 12.2, "#c9b27a", y=1.2, collide=False)
    for dz in (-9, 9):
        box("bench", cx + sgn * 2, dz, 5, 0.9, 1.0, WOOD, rough=0.8)
    for (dx, dz) in [(-4, -5), (-4, 5), (4, -5), (4, 5)]:
        box("pillar", cx + dx, dz, 1.0, 5.6, 1.0, "#d6cfba", rough=0.7)
    for dz in (-8, 8):
        lamp(cx, dz, 5.0)
    # the flag stand
    box("flag_stand", far + sgn * 2.5, 0, 2.6, 0.2, 2.6, "#2f6b72" if sgn < 0 else "#7a2f33", collide=False)

ticket_hall(-1)
ticket_hall(1)

# ---- the concourse -----------------------------------------------------------------------------------------------------------
room(-30, -14, 30, 14, 9.0, {"n": [(-20, 5.0), (0, 5.0), (20, 5.0)], "s": [(-20, 5.0), (0, 5.0), (20, 5.0)], "w": [(-10, 4.0), (0, 4.0), (10, 4.0)], "e": [(-10, 4.0), (0, 4.0), (10, 4.0)]},
     WALL_B, label="concourse", roof_color="#454b53")
box("clock_tower", 0, 0, 3.0, 8.5, 3.0, "#5b6068", metal=0.3)
box("clock_face", 0, 1.55, 1.8, 1.8, 0.1, "#e8e0c8", y=5.8, collide=False)
box("clock_face", 0, -1.55, 1.8, 1.8, 0.1, "#e8e0c8", y=5.8, collide=False)
for (x, z) in [(-14, -7), (-14, 7), (14, -7), (14, 7)]:
    box("column", x, z, 1.2, 9.0, 1.2, "#8a9488", rough=0.7)
for (x, z, sx, sz) in [(-22, 0, 3.0, 5.0), (22, 0, 3.0, 5.0), (-8, 9, 4.0, 1.4), (8, -9, 4.0, 1.4), (-8, -9, 4.0, 1.4), (8, 9, 4.0, 1.4)]:
    box("kiosk", x, z, sx, 2.2, sz, "#8b6f47", rough=0.7)
    box("kiosk_awning", x, z, sx + 0.6, 0.15, sz + 0.6, "#b0392e", y=2.2, collide=False)
for (x, z) in [(-18, 0), (18, 0), (0, -9), (0, 9), (-26, -9), (26, 9), (-26, 9), (26, -9)]:
    lamp(x, z, 8.0, "#ffe6b8", 11, 20)

# ---- the passages between halls and concourse (open air, a roof on posts) -------------------------------------------------------
for sgn in (-1, 1):
    for dz in (-10, 10):
        box("passage_bin", sgn * 33.5, dz * 1.15, 0.9, 1.0, 0.9, "#2f4a35", rough=0.7)
    lamp(sgn * 33.5, 0, 5.0, "#c8d8ff", 8, 12)

# ---- platforms and trains -------------------------------------------------------------------------------------------------------
def platform_side(sgn):
    """North (sgn -1) or south (+1): a train, a canopy and a platform edge. The train has gaps so lanes cross it."""
    zc = sgn * 27
    # the tracks: two rails and sleepers running east-west (walkable, so players cross them)
    for rz in (zc - 0.75, zc + 0.75):
        box("rail", 0, rz, 112, 0.12, 0.12, RAIL, collide=False, metal=0.5)
    for x in range(-54, 55, 3):
        box("sleeper", x, zc, 0.4, 0.08, 3.0, "#3a2e22", collide=False)
    # the train: two carriages a side of the middle crossing
    for (x, c) in [(-31, CARRIAGE), (-10, CARR2), (10, CARRIAGE), (31, CARR2)]:
        box("carriage", x, zc, 18.0, 3.6, 3.0, c, y=0.5, rough=0.6, metal=0.2)
        box("carriage_roof", x, zc, 18.0, 0.3, 2.6, "#2a2d31", y=4.1, collide=False)
        box("carriage_stripe", x, zc, 18.05, 0.35, 3.04, "#d8d2c0", y=2.2, collide=False)
        for wx in (-6, -2, 2, 6):
            box("carriage_window", x + wx, zc - 1.52, 1.4, 1.0, 0.05, "#c9d8e0", y=2.4, collide=False, emissive="#6f8896")
            box("carriage_window", x + wx, zc + 1.52, 1.4, 1.0, 0.05, "#c9d8e0", y=2.4, collide=False, emissive="#6f8896")
    # the platform: a low kerb along the concourse side, a yellow line, and benches
    box("kerb", 0, sgn * 18.2, 100, 0.25, 0.5, "#9a9a92", y=0.0, rough=0.9, collide=False)
    box("safety_line", 0, sgn * 18.9, 100, 0.02, 0.35, TRIM, y=0.01, collide=False)
    for x in (-38, -22, 22, 38):
        box("bench", x, sgn * 20.5, 4.0, 0.9, 1.0, WOOD, rough=0.8)
    # the canopy over the platform edge on posts
    box("canopy", 0, sgn * 21.0, 108, 0.35, 8.0, "#2b3036", y=6.0, rough=0.7, collide=False)
    for x in range(-50, 51, 10):
        box("post", x, sgn * 24.8, 0.5, 6.0, 0.5, STEEL, metal=0.4)
        lamp(x, sgn * 21.0, 5.6, "#ffe0a8", 6, 14)
    # signals and a crate stack at the buffers
    for sx in (-52, 52):
        box("buffer", sx, zc, 1.0, 1.6, 3.2, "#7a2f33", rough=0.7)
    box("crate_stack", -44 * -sgn, sgn * 33.5, 2.4, 2.4, 2.4, "#8a6a3f", rough=0.9)
    box("crate_stack", -42 * -sgn, sgn * 33.5, 1.8, 1.8, 1.8, "#7d6036", rough=0.9)

platform_side(-1)
platform_side(1)

# the service roads between the platforms and the yard wall: crates and a lamp every so often
for sgn in (-1, 1):
    for x in (-40, -20, 0, 20, 40):
        lamp(x, sgn * 35, 5.5, "#b8c8ff", 5, 14)
        cyl("lamp_post", x, sgn * 35.5, 0.1, 5.5, "#1f2328", y=0.0)
    for (x, w) in [(-28, 3.0), (6, 2.4), (30, 2.4)]:
        box("barrier", x, sgn * 36.5, w, 1.1, 0.7, "#9b9d98", rough=0.9)

# ---- weapons and ammunition (close quarters: shotguns and SMGs, few long guns) -----------------------------------------------------
for (w, x, z) in [("bulldog", -54, -6), ("marshal", -54, 6), ("stinger", -51, -9), ("wasp", -51, 9), ("ammo", -55, 0), ("frag", -47, 0)]:
    spot(w, x, z)
for (w, x, z) in [("shotgun", -34, -10), ("auto12", -34, 10), ("carbine", -26, 0), ("coach", -18, -11), ("flash", -26, -10), ("smoke", -26, 10), ("machinepistol", -10, 0)]:
    spot(w, x, z)
for (w, x, z) in [("rifle", -40, -26), ("bullpup", -22, -22), ("ranger", -8, -30), ("handcannon", -12, -18), ("bat", -45, -33), ("hatchet", -30, -33), ("ammo", -16, -26), ("thumper", -2, -22)]:
    spot(w, x, z)
for (w, x, z) in [("lancer", -12, 0), ("hammer", -22, 7), ("lmg", -22, -7), ("frag", -5, 4)]:
    spot(w, x, z)
spot("scout", -36, -26, y=0.3, respawn=45)

# the newer weapons
for (w, x, z, r) in [("reaper", -8, 4, 60), ("breaker", -33, 10, 30), ("flare", -46, 8, 30), ("lobber", -28, -30, 45), ("impact", -14, 8, 30), ("machete", -44, -33, 30), ("sledge", -50, -10, 40)]:
    mk.spot_near(w, x, z, respawn=r)
spot("hunter", -38, -30, respawn=40)

# ---- spawns -------------------------------------------------------------------------------------------------------------------------
for i in range(6):
    x, z = -53 + (i % 2) * 4, -8 + (i // 2) * 8 + (i % 2) * 2
    spawns.append({"id": f"ridge_{i}", "position": [x, 0, z], "yaw_deg": 90, "group": "team1"})
    spawns.append({"id": f"night_{i}", "position": [-x, 0, -z], "yaw_deg": 270, "group": "team2"})

def near_free(x, z, pad=1.2):
    for r in [0.0] + [1.0 * i for i in range(1, 10)]:
        for a in range(0, 360, 30) if r else [0]:
            px, pz = x + r * math.cos(math.radians(a)), z + r * math.sin(math.radians(a))
            if free(px, pz, pad):
                return round(px, 1), round(pz, 1)
    raise AssertionError((x, z))
for (x, z) in [(-20, 0), (20, 0), (0, -6), (0, 6), (-30, -22), (30, 22), (-10, -33), (10, 33)]:
    px, pz = near_free(x, z)
    spawns.append({"id": f"ffa_{len(spawns)}", "position": [px, 0, pz], "yaw_deg": round(math.degrees(math.atan2(-px, pz)) % 360), "group": "ffa"})

# ---- lights: night, a cold moon and the station's own lamps -------------------------------------------------------------------------
lights.insert(0, {"id": "moon", "type": "directional", "direction": [-0.35, -1, -0.4], "color": "#aebfff", "intensity": 1.1})

mk.build_ground_nav()

MODES = {
    "flags": [{"team": 1, "at": [-52, 0, 0]}, {"team": 2, "at": [52, 0, 0]}],
    "sites": [{"name": "A", "at": [18, 0, 0], "radius": 6}, {"name": "B", "at": [30, 0, -20], "radius": 5}],
    "objective": {"capture_limit": 3, "return_secs": 12, "win_rounds": 4, "swap_after": 3, "round_secs": 90, "freeze_secs": 5, "plant_secs": 3, "defuse_secs": 5, "fuse_secs": 35},
}
for f in MODES["flags"]:
    assert free(f["at"][0], f["at"][2], 0.8), f
for st in MODES["sites"]:
    assert free(st["at"][0], st["at"][2], 0.5), st

mk.emit("maps/terminus.json", camera={"position": [-54, 1.7, 0], "target": [0, 1.7, 0], "fov": 90},
        background={"sky_top": "#05070f", "sky_bottom": "#1a2238"}, ambient={"color": "#a8aec8", "intensity": 0.5}, name="Terminus", short="DEPOT",
        extra_shooter=MODES,
        sky={"zenith": "#03050c", "horizon": "#1b2440", "gradient_power": 0.7, "sun": {"direction": [0.35, 1, 0.4], "size_deg": 3.0, "color": "#cfe0ff", "glow": 0.35}},
        combat={"respawn_secs": 5, "spawn": "farthest", "spawn_protect_secs": 2.0, "regen_delay_secs": 5, "regen_per_sec": 20},
        match={"min_players": 1, "countdown_secs": 5, "round_secs": 600, "results_secs": 3600, "score_to_win": 30, "join_in_progress": True, "ready_check": True})
