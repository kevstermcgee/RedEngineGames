#!/usr/bin/env python3
"""Generates maps/main.json: IRONWORKS, Killchain's industrial team-deathmatch map.

A steel works on a river bend: Ridgeback's freight yard in the west, Nightfall's smelter yard in the east (point-symmetric, so neither side has
the better lane), and the dead foundry between them with a catwalk ring, a furnace and a hall you can cross or climb. North lane: warehouse and
pipe racks. South lane: the same turned around. Scale sits between Dust 2 and Nuke: about 170 x 110 m, 40 s end to end at a run.
Run: python3 tools/gen_map.py  (then scripts/red check)
"""
import json, math, random

rnd = random.Random(9)
objs = []
solids = []
pick = []
spawns = []
_n = {}

def nid(p):
    _n[p] = _n.get(p, 0) + 1
    return f"{p}_{_n[p]}"

def mat(color, rough=0.9, metal=0.0, emissive=None, opacity=None):
    m = {"color": color, "roughness": rough}
    if metal: m["metallic"] = metal
    if emissive: m["emissive"] = emissive
    if opacity is not None: m["opacity"] = opacity
    return m

def box(p, x, z, sx, sy, sz, color, y=0.0, rough=0.9, metal=0.0, collide=True, rot=None):
    o = {"id": nid(p), "type": "box", "size": [sx, sy, sz], "position": [x, y + sy / 2, z], "material": mat(color, rough, metal)}
    if not collide: o["collide"] = False
    if rot: o["rotation"] = [0, rot, 0]
    objs.append(o)
    if collide and sy > 0.4:
        solids.append((x - sx / 2 - 0.3, z - sz / 2 - 0.3, x + sx / 2 + 0.3, z + sz / 2 + 0.3))
    return o

def cyl(p, x, z, r, h, color, y=0.0, rot=None, metal=0.3, rough=0.6, pos_y=None):
    o = {"id": nid(p), "type": "cylinder", "radius": r, "height": h, "position": [x, (y + h / 2) if pos_y is None else pos_y, z],
         "material": mat(color, rough, metal), "collide": False}
    if rot: o["rotation"] = rot
    objs.append(o)

def sym(x, z):
    return -x, -z

CONC, STEEL, DARK, RUST = "#8b8d89", "#525a62", "#2f343a", "#8a4b2d"
ASPH, YEL, WHITE = "#4b4e51", "#c9a227", "#d8d8d2"
CRED, CBLUE, CGREEN, CGREY, CORANGE = "#8f3a2b", "#2f5d7c", "#4a6b3b", "#6b7077", "#b5662a"

# ---- ground and the perimeter ---------------------------------------------------------------------------------------------
objs.append({"id": "ground", "type": "plane", "size": [220, 150], "material": mat(ASPH, 0.95)})
W, H = 86, 54  # half extents of the playable yard
for i, (x, z, sx, sz) in enumerate([(0, -H - 1, 2 * W + 4, 2), (0, H + 1, 2 * W + 4, 2), (-W - 1, 0, 2, 2 * H), (W + 1, 0, 2, 2 * H)]):
    box("perimeter", x, z, sx, 9, sz, CONC, rough=0.95)
    box("perimeter_cap", x, z, sx + 0.4, 0.6, sz + 0.4, DARK, y=9)
# grass verges outside the working yard (walk-through tint only)
objs.append({"id": "verge_n", "type": "box", "size": [2 * W, 0.02, 10], "position": [0, 0.011, -H + 5], "material": mat("#4e6238", 1.0), "collide": False})
objs.append({"id": "verge_s", "type": "box", "size": [2 * W, 0.02, 10], "position": [0, 0.011, H - 5], "material": mat("#4e6238", 1.0), "collide": False})

def lane_line(x0, z0, x1, z1, color=YEL, w=0.25):
    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
    sx, sz = abs(x1 - x0) or w, abs(z1 - z0) or w
    box("marking", cx, cz, sx, 0.02, sz, color, y=0.0, collide=False)

# ---- containers -------------------------------------------------------------------------------------------------------------
def container(x, z, along="z", color=CRED, stack=1, y=0.0):
    sx, sz = (2.5, 12.0) if along == "z" else (12.0, 2.5)
    for k in range(stack):
        box("container", x, z, sx, 2.6, sz, color, y=y + k * 2.6, rough=0.7, metal=0.25)
    # ribbing: darker stripes on the long sides
    for t in (-0.3, 0.3):
        if along == "z":
            for zz in (-4.0, -1.4, 1.4, 4.0):
                box("rib", x + (sx / 2 + 0.02) * (1 if t > 0 else -1), z + zz, 0.04, 2.3 * stack, 0.35, DARK, y=y + 0.15, collide=False)
        else:
            for xx in (-4.0, -1.4, 1.4, 4.0):
                box("rib", x + xx, z + (sz / 2 + 0.02) * (1 if t > 0 else -1), 0.35, 2.3 * stack, 0.04, DARK, y=y + 0.15, collide=False)

# Ridgeback freight yard (west): a wall of stacked containers with three gaps, and rows inside.
def yard_wall(sign):
    cols = [CRED, CBLUE, CGREEN, CGREY, CORANGE, CRED]
    z = -48.0
    i = 0
    # the wall runs along z at x = sign * 62 with gaps at z = -24..-19, -3..3 and 19..24 (mirrored by the caller)
    segs = [(-48, -25), (-19, -4), (4, 19), (25, 48)]
    for a, b in segs:
        zz = a + 6
        while zz <= b - 6 + 0.01:
            container(sign * 62, zz, "z", cols[i % len(cols)], stack=2 if (i % 3 == 0) else 1)
            zz += 12.2
            i += 1

yard_wall(-1)
yard_wall(1)
# Inner yard cover, west; twin to the east.
for (x, z, al, c, st) in [(-74, -30, "x", CBLUE, 1), (-74, 30, "x", CGREEN, 1), (-70, -12, "z", CORANGE, 1), (-70, 12, "z", CGREY, 2), (-78, 0, "x", CRED, 1)]:
    container(x, z, al, c, st)
    container(-x, -z, al, {CBLUE: CGREEN, CGREEN: CBLUE, CORANGE: CGREY, CGREY: CORANGE, CRED: CRED}[c], st)

# ---- the dead foundry in the middle ---------------------------------------------------------------------------------------
HX, HZ, HH = 34, 22, 10.0
PLAT = 4.0

def hall():
    arch_ns = [{"kind": "arch", "at": 34 - 15, "width": 5, "height": 4.5}, {"kind": "arch", "at": 34 + 15, "width": 5, "height": 4.5}]
    arch_ew = [{"kind": "arch", "at": 22, "width": 7, "height": 5}, {"kind": "window", "at": 8, "width": 2.4, "height": 1.6, "sill": 4.6}, {"kind": "window", "at": 36, "width": 2.4, "height": 1.6, "sill": 4.6}]
    for (fx, fz, tx, tz, ops) in [(-HX, -HZ, HX, -HZ, arch_ns), (-HX, HZ, HX, HZ, arch_ns), (-HX, -HZ, -HX, HZ, arch_ew), (HX, -HZ, HX, HZ, arch_ew)]:
        objs.append({"id": nid("hall_wall"), "type": "wall", "from": [fx, fz], "to": [tx, tz], "height": HH, "thickness": 0.6, "openings": ops, "material": mat("#7d6f63", 0.95)})
    for x in range(-30, 31, 10):
        box("truss", x, 0, 0.5, 0.6, 2 * HZ, DARK, y=HH - 0.6, collide=False)
    box("furnace", 0, 0, 10, 7, 6, "#5a3a2f", rough=0.85)
    box("furnace_mouth", 0, 3.06, 4.5, 2.4, 0.3, "#d0601f", y=1.6, collide=False)
    box("furnace_mouth", 0, -3.06, 4.5, 2.4, 0.3, "#d0601f", y=1.6, collide=False)
    cyl("chimney", 0, 0, 1.2, 12, "#3b3f44", y=7.0)
    for (px, pz) in [(-14, -14), (14, -14), (-14, 14), (14, 14), (-24, 0), (24, 0)]:
        box("pillar", px, pz, 1.2, 9.5, 1.2, STEEL, metal=0.3)
    def deck(x0, z0, x1, z1):
        box("catwalk", (x0 + x1) / 2, (z0 + z1) / 2, abs(x1 - x0), 0.3, abs(z1 - z0), "#6a7077", y=PLAT - 0.3, metal=0.5, rough=0.6)
    deck(-11, -11, 17, -8)
    deck(-17, 8, 11, 11)
    def rail(x0, z0, x1, z1):
        box("rail", (x0 + x1) / 2, (z0 + z1) / 2, abs(x1 - x0) or 0.12, 1.1, abs(z1 - z0) or 0.12, YEL, y=PLAT, rough=0.6, metal=0.3)
    rail(-11, -11.05, 17, -11.05); rail(-17, 11.05, 11, 11.05); rail(-11, -7.95, 17, -7.95); rail(-17, 7.95, 11, 7.95)
    rail(17.05, -11, 17.05, -8); rail(-17.05, 8, -17.05, 11)
    st = lambda x, z, rot: {"id": nid("stairs"), "type": "stairs", "width": 3.0, "run": 20, "rise": PLAT, "steps": 20, "position": [x, 0, z], "rotation": [0, rot, 0], "material": mat("#5d646b", 0.7, 0.4)}
    objs.append(st(-21, -9.5, 90))
    objs.append(st(21, 9.5, 270))
    solids.append((-32.5, -11.5, -10.5, -7.5))
    solids.append((10.5, 7.5, 32.5, 11.5))
    # machinery on the floor: low blocks for cover
    for (x, z, sx, sy, sz, c) in [(-10, 16, 4, 1.4, 2.2, RUST), (10, -16, 4, 1.4, 2.2, RUST), (-8, -17, 2.2, 1.2, 2.2, CGREY), (8, 17, 2.2, 1.2, 2.2, CGREY),
                                   (-27, 8, 3, 1.3, 5, DARK), (27, -8, 3, 1.3, 5, DARK), (-27, -14, 2, 2.2, 2, RUST), (27, 14, 2, 2.2, 2, RUST),
                                   (0, 12, 6, 0.9, 1.4, STEEL), (0, -12, 6, 0.9, 1.4, STEEL)]:
        box("machine", x, z, sx, sy, sz, c, rough=0.8, metal=0.3)
    for z in (-15, 15):
        cyl("pipe", 0, z, 0.3, 66, "#6b7077", pos_y=7.5, rot=[0, 0, 90])
    # warm light over the furnace, cold light over the catwalk ends
    lights.append({"id": "furnace_glow", "type": "point", "position": [0, 3.2, 5.5], "color": "#ff7a30", "intensity": 18, "range": 26})
    for (x, z) in [(-26, 0), (26, 0), (0, -17), (0, 17)]:
        lights.append({"id": nid("hall_lamp"), "type": "point", "position": [x, 7.5, z], "color": "#cfe0ff", "intensity": 9, "range": 22})

lights = [{"id": "sun", "type": "directional", "direction": [-0.45, -1, -0.35], "color": "#fff0d6", "intensity": 2.3}]
hall()

# ---- buildings --------------------------------------------------------------------------------------------------------------
def building(x0, z0, x1, z1, h, doors, color, roof=True, label="bldg", windows=True):
    """A walled building. `doors` = [(side, at, width)], side in n/s/e/w; `at` from the wall's start (west->east, north->south)."""
    solids.append((x0 - 1, z0 - 1, x1 + 1, z1 + 1))
    sides = {"n": (x0, z0, x1, z0), "s": (x0, z1, x1, z1), "w": (x0, z0, x0, z1), "e": (x1, z0, x1, z1)}
    for side, (fx, fz, tx, tz) in sides.items():
        ops = [{"kind": "door", "at": at, "width": w, "height": min(h - 0.3, 3.4)} for (sd, at, w) in doors if sd == side]
        length = abs(tx - fx) + abs(tz - fz)
        if windows:
            k = 6.0
            while k < length - 4:
                if all(abs(k - o["at"]) > o["width"] / 2 + 2 for o in ops):
                    ops.append({"kind": "window", "at": k, "width": 1.6, "height": 1.0, "sill": 1.7})
                k += 8.0
        objs.append({"id": nid(label), "type": "wall", "from": [fx, fz], "to": [tx, tz], "height": h, "thickness": 0.4, "openings": ops, "material": mat(color, 0.9)})
    if roof:
        box(label + "_roof", (x0 + x1) / 2, (z0 + z1) / 2, abs(x1 - x0) + 0.8, 0.4, abs(z1 - z0) + 0.8, DARK, y=h, rough=0.8)

def control_room(cx, cz, flip):
    """Two-level office on the lane: ground-floor rooms, an outside stair to a flat roof that overlooks the lane."""
    x0, x1, z0, z1 = cx - 8, cx + 8, cz - 5, cz + 5
    h = 3.4
    d = -1 if flip else 1
    building(x0, z0, x1, z1, h, [("n", 4, 1.4), ("s", 12, 1.4), ("w", 5, 1.4), ("e", 5, 1.4)], "#9a9388", roof=False, label="office")
    box("office_roof", cx, cz, 16.8, 0.4, 10.8, "#5c6167", y=h, rough=0.7)
    box("office_partition", cx, cz, 0.3, 2.8, 10, "#b0aa9c", collide=True)
    # roof parapet as cover, with a gap where the stairs arrive (on the west side for the north office, the east side for its twin)
    side = -d  # -1: stairs arrive at the west edge
    gz0, gz1 = cz + 2 * d - 1.4, cz + 2 * d + 1.4
    for (px, pz, sx, sz) in [(0, -5.3, 16.8, 0.3), (0, 5.3, 16.8, 0.3)]:
        box("parapet", cx + px, cz + pz, sx, 1.0, sz, "#5c6167", y=h + 0.4)
    far = cx - side * 8.4
    box("parapet", far, cz, 0.3, 1.0, 10.8, "#5c6167", y=h + 0.4)
    near = cx + side * 8.4
    lo, hi = cz - 5.4, cz + 5.4
    if gz0 > lo:
        box("parapet", near, (lo + gz0) / 2, 0.3, 1.0, gz0 - lo, "#5c6167", y=h + 0.4)
    if hi > gz1:
        box("parapet", near, (gz1 + hi) / 2, 0.3, 1.0, hi - gz1, "#5c6167", y=h + 0.4)
    top_x = cx + side * 8.4 + side * 0.0
    solids.append((top_x + side * 17 - 1.5 if side < 0 else top_x - 1.5, cz + 2 * d - 2.0, top_x + 1.5 if side < 0 else top_x + side * 17 + 1.5, cz + 2 * d + 2.0))
    objs.append({"id": nid("stairs"), "type": "stairs", "width": 2.4, "run": 17, "rise": h + 0.4, "steps": 19,
                 "position": [top_x + side * 8.5, 0, cz + 2 * d], "rotation": [0, 90 if side < 0 else 270, 0], "material": mat("#59606a", 0.7, 0.4)})

def warehouse(x0, z0, x1, z1):
    building(x0, z0, x1, z1, 7.5, [("n", 7, 4), ("n", 21, 4), ("s", 7, 4), ("s", 21, 4), ("w", 7, 3), ("e", 7, 3)], "#8e8a80", roof=True, label="warehouse", windows=False)
    # racks inside
    cxm = (x0 + x1) / 2
    for dx in (-8, 0, 8):
        box("rack", cxm + dx, (z0 + z1) / 2, 1.4, 2.4, (z1 - z0) - 6, "#6d5a3c", rough=0.85)
        for k in range(3):
            box("pallet", cxm + dx, z0 + 4 + k * 3, 1.3, 0.9, 1.3, "#a88b55", y=2.4)

def silo(x, z, h=12):
    box("silo", x, z, 6, h, 6, "#9da1a4", rough=0.6, metal=0.3)
    cyl("silo_dome", x, z, 3.1, 0.5, "#7b8084", y=h)
    cyl("ladder", x + 3.1, z, 0.08, h, DARK, y=0.0)

warehouse(8, -50, 40, -36)
warehouse(-40, 36, -8, 50)
control_room(-12, -38, False)
control_room(12, 38, True)
for (x, z) in [(-46, -36), (-46, -28), (46, 36), (46, 28)]:
    silo(x, z)
# pipe racks along the lanes: a long low pipe line with legs is cover you can crouch behind
def pipe_rack(x0, z0, x1, z1):
    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
    sx, sz = abs(x1 - x0) or 1.0, abs(z1 - z0) or 1.0
    box("rack_beam", cx, cz, sx, 0.4, sz, STEEL, y=1.3, metal=0.4)
    box("rack_wall", cx, cz, sx if sx > sz else 0.5, 1.3, sz if sz >= sx else 0.5, "#6d7479", metal=0.3)
    for k in range(3):
        o = 0.5 + k * 0.45
        if sx > sz:
            cyl("pipe", cx, cz - 0.4 + k * 0.4, 0.3, sx, "#8b949b" if k != 1 else RUST, pos_y=2.0, rot=[0, 0, 90])
        else:
            cyl("pipe", cx - 0.4 + k * 0.4, cz, 0.3, sz, "#8b949b" if k != 1 else RUST, pos_y=2.0, rot=[90, 0, 0])
for (x0, z0, x1, z1) in [(-50, -20, -50, -6), (-30, -44, -16, -44), (-55, 34, -41, 34), (50, 6, 50, 20), (30, 44, 16, 44), (55, -34, 41, -34)]:
    pipe_rack(x0, z0, x1, z1)
# low walls / jersey barriers across the lanes
for (x, z, sx, sz) in [(-44, -8, 6, 0.8), (44, 8, 6, 0.8), (-22, -30, 0.8, 6), (22, 30, 0.8, 6), (-40, 20, 6, 0.8), (40, -20, 6, 0.8), (0, -30, 6, 0.8), (0, 30, 6, 0.8), (-58, 4, 0.8, 5), (58, -4, 0.8, 5)]:
    box("barrier", x, z, sx, 1.2, sz, "#9b9d98", rough=0.9)
    box("barrier_stripe", x, z, sx + 0.02, 0.2, sz + 0.02, YEL, y=0.9, collide=False)
# crates in the open
for (x, z) in [(-36, -16), (36, 16), (-30, 22), (30, -22), (-50, 0), (50, 0), (-20, 44), (20, -44), (-62, -40), (62, 40)]:
    box("crate", x, z, 1.6, 1.6, 1.6, "#8a6a3f", rough=0.9)
    box("crate", x + 1.8, z + 0.6, 1.3, 1.3, 1.3, "#7d6036", rough=0.9)
# a gantry crane over each wing of the yard (visual)
for sgn in (-1, 1):
    for z in (-14, 14):
        box("crane_leg", sgn * 52, z, 0.8, 9, 0.8, YEL, metal=0.3, collide=True)
    box("crane_beam", sgn * 52, 0, 0.8, 0.9, 30, YEL, y=8.6, collide=False)
# lamp posts
for (x, z) in [(-56, -30), (-56, 30), (56, -30), (56, 30), (-20, -14), (20, 14), (-70, 0), (70, 0)]:
    cyl("lamp_post", x, z, 0.1, 8, DARK, y=0)
    lights.append({"id": nid("lamp"), "type": "point", "position": [x, 7.6, z], "color": "#ffe2b0", "intensity": 7, "range": 18})
# plants: the works sits in a bend of a wooded valley
plants = []
for k in range(46):
    side = rnd.choice([-1, 1])
    if rnd.random() < 0.5:
        x, z = rnd.uniform(-W + 2, W - 2), side * rnd.uniform(H - 7, H - 2)
    else:
        x, z = side * rnd.uniform(W - 7, W - 2), rnd.uniform(-H + 2, H - 2)
    if abs(x) < 70 and abs(z) < H - 8:
        continue
    if any(a - 1 < x < c + 1 and b - 1 < z < e + 1 for (a, b, c, e) in solids):
        continue
    if any((x - px) ** 2 + (z - pz) ** 2 < 25 for (px, pz) in plants):
        continue
    plants.append((x, z))
    objs.append({"id": nid("tree"), "type": "prop", "prop": rnd.choice(["tree_pine", "tree_oak", "tree_pine"]), "position": [round(x, 1), 0, round(z, 1)], "rotation": [0, rnd.randint(0, 359), 0],
                 "material": {"color": rnd.choice(["#3f5b34", "#486b3a", "#56703a"])}})
for k in range(40):
    x, z = rnd.uniform(-W + 3, W - 3), rnd.choice([-1, 1]) * rnd.uniform(H - 12, H - 3)
    if any(a - 1.5 < x < c + 1.5 and b - 1.5 < z < e + 1.5 for (a, b, c, e) in solids):
        continue
    if any((x - px) ** 2 + (z - pz) ** 2 < 12 for (px, pz) in plants):
        continue
    plants.append((x, z))
    objs.append({"id": nid("bush"), "type": "prop", "prop": rnd.choice(["bush", "boulder", "bush"]), "position": [round(x, 1), 0, round(z, 1)], "rotation": [0, rnd.randint(0, 359), 0],
                 "material": {"color": "#587a3c"}})
# floor markings
for z in (-24, 24):
    lane_line(-60, z, 60, z)
lane_line(0, -44, 0, 44, WHITE)

# ---- weapons and ammunition ---------------------------------------------------------------------------------------------------
def spot(w, x, z, y=0.3, respawn=30, twin=True):
    pick.append({"weapon": w, "at": [round(x, 1), y, round(z, 1)], "respawn_secs": respawn} if w != "ammo" else {"ammo": True, "at": [round(x, 1), y, round(z, 1)], "respawn_secs": respawn})
    if twin:
        pick.append({"weapon": w, "at": [round(-x, 1), y if y < 3 else y, round(-z, 1)], "respawn_secs": respawn} if w != "ammo" else {"ammo": True, "at": [round(-x, 1), y, round(-z, 1)], "respawn_secs": respawn})

# by the spawns: sidearms, an SMG, ammunition, a grenade
for (w, x, z) in [("bulldog", -72, -6), ("marshal", -72, 6), ("stinger", -76, -14), ("wasp", -76, 14), ("ammo", -78, -2), ("frag", -68, 0)]:
    spot(w, x, z)
# the yard gaps: rifles and carbines
for (w, x, z) in [("rifle", -58, -22), ("carbine", -58, 0), ("ironside", -58, 22), ("machinepistol", -64, 10), ("ranger", -64, -10)]:
    spot(w, x, z)
# the outside middle and the lanes
for (w, x, z) in [("bullpup", -44, 0), ("auto12", -38, -22), ("shotgun", -38, 22), ("coach", -28, -8), ("flash", -44, -16), ("smoke", -44, 16), ("incendiary", -30, 30),
                  ("hatchet", -50, -10), ("bat", -52, 10), ("ammo", -40, -6), ("thumper", -24, -40), ("scout", -50, -44), ("handcannon", -34, 4), ("marksman", -44, 36)]:
    spot(w, x, z)
# inside the hall: the prizes
spot("gale", -14, -9.5, y=4.3)       # north catwalk west (twin on the south catwalk)
spot("sentinel", 0, -9.5, y=4.3)     # catwalk middle
spot("lancer", -6.5, 0, y=0.3)       # beside the furnace
spot("hammer", -20, 14)
spot("lmg", -20, -14)
spot("ammo", -8, 15)
spot("frag", -29, 0)
spot("frag", -12, 19)
# the offices' roofs
spot("sentinel", -12, -38, y=3.8, respawn=45, twin=False)
pick.append({"weapon": "scout", "at": [12, 3.8, 38], "respawn_secs": 45})
spot("ammo", -10, -44)

# ---- spawns -----------------------------------------------------------------------------------------------------------------
for i in range(6):
    x, z = -82 + (i % 2) * 4, -10 + (i // 2) * 8 + (i % 2) * 2
    spawns.append({"id": f"ridge_{i}", "position": [x, 0, z], "yaw_deg": 90, "group": "team1"})
    spawns.append({"id": f"night_{i}", "position": [-x, 0, -z], "yaw_deg": 270, "group": "team2"})

for p in pick:
    if p.get("weapon") == "machinepistol":
        p["weapon"] = "machine-pistol"
    if p.get("weapon") == "handcannon":
        p["weapon"] = "hand-cannon"


# ---- the nav graph bots route along ---------------------------------------------------------------------------------------
# Hall walls block the ground graph except at their openings (solids only knows boxes and whole buildings).
def wall_solids(x0, z0, x1, z1, gaps):
    horizontal = z0 == z1
    a, b = (x0, x1) if horizontal else (z0, z1)
    cuts = sorted([(c - w / 2, c + w / 2) for c, w in gaps])
    cur = a
    for lo, hi in cuts + [(b, b)]:
        if lo > cur:
            solids.append((cur, z0 - 0.5, lo, z0 + 0.5) if horizontal else (x0 - 0.5, cur, x0 + 0.5, lo))
        cur = max(cur, hi)
wall_solids(-HX, -HZ, HX, -HZ, [(-15, 5), (15, 5)])
wall_solids(-HX, HZ, HX, HZ, [(-15, 5), (15, 5)])
wall_solids(-HX, -HZ, -HX, HZ, [(0, 7)])
wall_solids(HX, -HZ, HX, HZ, [(0, 7)])

def free(x, z, pad=0.9):
    if abs(x) > W - 2.5 or abs(z) > H - 2.5:
        return False
    return not any(a - pad < x < c + pad and b - pad < z < e + pad for (a, b, c, e) in solids)

def clear_line(x0, z0, x1, z1):
    n = int(math.hypot(x1 - x0, z1 - z0) / 0.6) + 1
    return all(free(x0 + (x1 - x0) * k / n, z0 + (z1 - z0) * k / n, 0.6) for k in range(n + 1))

nodes, index = [], {}
STEP = 7.0
xs = [(-W + 4) + STEP * i for i in range(int((2 * W - 8) / STEP) + 1)]
zs = [(-H + 4) + STEP * i for i in range(int((2 * H - 8) / STEP) + 1)]
for x in xs:
    for z in zs:
        # stair footprints are not ground
        if free(x, z, 1.0):
            index[(x, z)] = len(nodes)
            nodes.append({"id": f"n{len(nodes)}", "pos": [round(x, 1), 0, round(z, 1)]})
edges = []
for (x, z), i in index.items():
    for dx, dz in [(STEP, 0), (0, STEP), (STEP, STEP), (STEP, -STEP)]:
        j = index.get((x + dx, z + dz))
        if j is not None and clear_line(x, z, x + dx, z + dz):
            edges.append([nodes[i]["id"], nodes[j]["id"]])
def add_node(name, x, y, z):
    nodes.append({"id": name, "pos": [x, y, z]})
    return name
def link(a, b, kind=None):
    edges.append([a, b] if kind is None else [a, b, kind])
def nearest(x, z, maxd=11.0):
    best = None
    for (nx, nz), i in index.items():
        d = math.hypot(nx - x, nz - z)
        if d < maxd and clear_line(x, z, nx, nz) and (best is None or d < best[0]):
            best = (d, nodes[i]["id"])
    return best[1] if best else None
# the catwalk: up the west stairs to the north deck, up the east stairs to the south deck
for (nm, bx, bz, tx, dxs) in [("nw", -31, -9.5, -11, [0, 14]), ("se", 31, 9.5, 11, [0, -14])]:
    b = add_node(f"{nm}_stairs_bottom", bx, 0, bz)
    t = add_node(f"{nm}_stairs_top", tx, 4.0, bz)
    g = nearest(bx, bz)
    if g: link(g, b)
    link(b, t)
    prev = t
    for k, d in enumerate(dxs):
        n = add_node(f"{nm}_deck_{k}", d, 4.0, bz)
        link(prev, n); prev = n
# the office roofs
for (nm, bx, bz, tx) in [("o1", -37.4, -36.0, -20.4), ("o2", 37.4, 36.0, 20.4)]:
    b = add_node(f"{nm}_stairs_bottom", bx, 0, bz)
    t = add_node(f"{nm}_stairs_top", tx, 3.8, bz)
    g = nearest(bx, bz)
    if g: link(g, b)
    link(b, t)
    r = add_node(f"{nm}_roof", -12.0 if nm == "o1" else 12.0, 3.8, bz)
    link(t, r)
scene_nav = {"nodes": nodes, "edges": edges}

scene = {
    "meta": {"fps": 30, "duration": 10, "resolution": [1280, 720]},
    "camera": {"position": [-80, 1.7, 0], "target": [0, 1.7, 0], "fov": 90},
    "background": {"sky_top": "#7fa6cf", "sky_bottom": "#cfd3c4"},
    "ambient": {"color": "#e8eeff", "intensity": 0.55},
    "lights": lights[:200],
    "player": {"fov": 90, "walk_speed": 4.6, "sprint_speed": 4.6, "crouch_multiplier": 0.45, "jump_speed": 5.0, "gravity": 15.0,
               "acceleration": 38, "air_acceleration": 10, "friction": 10, "max_speed": 4.8},
    "music": False,
    "combat": {"respawn_secs": 8, "spawn": "farthest", "spawn_protect_secs": 2.0},
    "match": {"min_players": 1, "countdown_secs": 5, "round_secs": 600, "results_secs": 3600, "score_to_win": 50, "join_in_progress": True, "ready_check": True},
    "shooter": {"start": ["pistol", "knife"], "friendly_fire": False, "pickups": pick},
    "spawns": spawns,
    "nav": scene_nav,
    "objects": objs,
}
json.dump(scene, open("maps/main.json", "w"), indent=1)
print(len(nodes), "nav nodes,", len(edges), "edges;", len(objs), "objects,", len(pick), "pickups,", len(lights), "lights")
