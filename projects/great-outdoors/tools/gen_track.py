#!/usr/bin/env python3
"""Generates maps/main.json: the Great Outdoors circuit ("Whispering Woods"), a pastel forest track for up to eight karts.

Kart driving direction is counter-clockwise seen from above (x right, z toward the viewer): east along the south straight, north up the east side, west along
the north straight, south down the west side. The centre line is straights joined by four quarter-circle bends; everything else (road, fences, gates, item
boxes, grid, racing line, scenery) is derived from it.

Run from the repository root:   python3 tools/gen_karts.py assets/karts.json && python3 tools/gen_track.py maps/main.json
"""
import json, math, sys

# ---- the circuit -------------------------------------------------------------------------------------------------------------------------------------
HALF_W = 110.0        # centre line of the east/west straights
HALF_H = 70.0         # centre line of the north/south straights
R = 40.0              # bend radius of the centre line
ROAD = 22.0           # road width, m
STEP = 8.0            # length of one road/fence piece, m

def centre_line():
    """Points along the centre line starting at the start line (0, HALF_H), in driving order."""
    pts = []
    def straight(a, b):
        n = max(1, int(math.dist(a, b) // STEP))
        for i in range(n):
            t = i / n
            pts.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    def arc(cx, cz, a0, a1):
        length = abs(a1 - a0) * R
        n = max(4, int(length // STEP))
        for i in range(n):
            a = a0 + (a1 - a0) * i / n
            pts.append((cx + R * math.cos(a), cz + R * math.sin(a)))
    # south straight (z = +H), heading +x
    straight((0, HALF_H), (HALF_W - R, HALF_H))
    arc(HALF_W - R, HALF_H - R, math.pi / 2, 0)                 # south-east bend: from +z side round to +x side (heading north)
    straight((HALF_W, HALF_H - R), (HALF_W, -HALF_H + R))
    arc(HALF_W - R, -HALF_H + R, 0, -math.pi / 2)               # north-east bend (heading west)
    straight((HALF_W - R, -HALF_H), (-HALF_W + R, -HALF_H))
    arc(-HALF_W + R, -HALF_H + R, -math.pi / 2, -math.pi)       # north-west bend (heading south)
    straight((-HALF_W, -HALF_H + R), (-HALF_W, HALF_H - R))
    arc(-HALF_W + R, HALF_H - R, math.pi, math.pi / 2)          # south-west bend (heading east)
    straight((-HALF_W + R, HALF_H), (0, HALF_H))
    return pts

PATH = centre_line()
N = len(PATH)

def seg(i):
    a, b = PATH[i], PATH[(i + 1) % N]
    dx, dz = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dz)
    return a, b, dx / length, dz / length, length

def heading(i):
    """The direction of piece i as a yaw for a plane/box whose long axis is local Z."""
    _, _, ux, uz, _ = seg(i)
    return math.degrees(math.atan2(ux, uz))

def turn(i):
    """The change of heading (radians) between piece i and the next one, wrapped to -pi..pi."""
    d = math.radians(heading((i + 1) % N) - heading(i))
    return (d + math.pi) % math.tau - math.pi

def offset_vertices(off, side):
    """The centre line pushed sideways by `off` on `side` (-1 / +1), with mitred joins: consecutive pieces built between these vertices meet exactly."""
    out = []
    for j in range(N):
        _, _, upx, upz, _ = seg((j - 1) % N)
        _, _, unx, unz, _ = seg(j)
        n0 = (-upz * side, upx * side); n1 = (-unz * side, unx * side)
        mx, mz = n0[0] + n1[0], n0[1] + n1[1]
        ml = math.hypot(mx, mz)
        mx, mz = mx / ml, mz / ml
        miter = off / max(0.3, mx * n1[0] + mz * n1[1])
        out.append((PATH[j][0] + mx * miter, PATH[j][1] + mz * miter))
    return out

def piece(a, b, extra=0.0):
    """Centre, yaw (degrees) and length of the straight piece from a to b."""
    dx, dz = b[0] - a[0], b[1] - a[1]
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, math.degrees(math.atan2(dx, dz)), math.hypot(dx, dz) + extra)

# ---- palette (a pastel forest) -------------------------------------------------------------------------------------------------------------------------
MOSS = "#8fcf9b"; MOSS_DARK = "#7dbf8e"; DIRT = "#d2b48f"; DIRT_EDGE = "#e9d6b8"; SKY_TOP = "#bcdcff"; SKY_BOTTOM = "#ffe6d0"
HEDGE = ["#86c99a", "#9fd6a6", "#78bb8f"]; LOG = "#b98d62"; LOG_DARK = "#a47850"
LEAVES = ["#a8e6cf", "#bfe8b6", "#ffd3b6", "#ffb8c6", "#d5c6ff", "#c8ecd8", "#f8e1a6"]
PINES = ["#8fd3b4", "#9bd7a4", "#7fc9ae", "#a6dcc0"]

objects = []
zones = []

def add(o): objects.append(o)

# ground and road ----------------------------------------------------------------------------------------------------------------------------------------
add({"id": "forest_floor", "type": "plane", "size": [560, 460], "position": [0, 0.0, 0], "material": {"color": MOSS, "roughness": 1.0}, "collide": False})
rng0 = __import__("random").Random(11)
moss_n = 0
for gx in range(-4, 5):                               # darker moss patches on the floor, one per grid cell at most, so they never overlap
    for gz in range(-3, 4):
        if rng0.random() < 0.6:
            add({"id": f"moss_{moss_n}", "type": "plane", "size": [rng0.uniform(14, 34), rng0.uniform(12, 28)],
                 "position": [round(gx * 62 + rng0.uniform(-8, 8), 1), 0.01, round(gz * 56 + rng0.uniform(-8, 8), 1)],
                 "rotation": [0, 0, 0], "material": {"color": MOSS_DARK, "roughness": 1.0}, "collide": False})
            moss_n += 1
for i in range(N):
    a_, b_, ux, uz, length = seg(i)
    mx, mz = (a_[0] + b_[0]) / 2, (a_[1] + b_[1]) / 2
    yaw = heading(i)
    wedge = ROAD * abs(math.tan(turn(i) / 2)) + 0.5              # the gap that opens on the outside of a bend between two straight pieces
    level = i % 5                                              # neighbouring pieces overlap (more on the inside of a tight bend), so they sit at slightly different heights
    add({"id": f"road_{i}", "type": "plane", "size": [ROAD, round(length + wedge, 3)], "position": [round(mx, 3), 0.03 + 0.01 * level, round(mz, 3)], "rotation": [0, round(yaw, 3), 0],
         "material": {"color": DIRT, "roughness": 0.98}, "collide": False})
for side in (-1, 1):                                            # a paler worn edge on each side of the dirt track, laid along the offset curve
    vs = offset_vertices(ROAD / 2 - 0.9, side)
    for j in range(N):
        cx, cz, yaw, length = piece(vs[j], vs[(j + 1) % N], 0.3)
        add({"id": f"edge_{j}_{'l' if side < 0 else 'r'}", "type": "plane", "size": [1.8, round(length, 3)], "position": [round(cx, 3), 0.08 + 0.01 * (j % 5), round(cz, 3)],
             "rotation": [0, round(yaw, 3), 0], "material": {"color": DIRT_EDGE, "roughness": 0.98}, "collide": False})

# barriers on both edges (these block karts): hedges and stacked logs in turns, built along the offset curve so the ring has no gaps ---------------------------------
SHORTCUT_IN = []      # end points of the inner-barrier pieces left out at the entrance (south straight) and the exit (east straight) of the dirt shortcut
SHORTCUT_OUT = []
for side in (-1, 1):
    vs = offset_vertices(ROAD / 2 + 0.7, side)
    tag = 'l' if side < 0 else 'r'
    for i in range(N):
        px, pz, yaw, length = piece(vs[i], vs[(i + 1) % N], 0.3)
        if side < 0 and abs(pz - (HALF_H - ROAD / 2 - 0.7)) < 1.5 and 22 < px < 52:            # the entrance: the inner barrier of the south straight
            SHORTCUT_IN += [vs[i], vs[(i + 1) % N]]
            continue
        if side < 0 and abs(px - (HALF_W - ROAD / 2 - 0.7)) < 1.5 and -12 < pz < 20:            # the exit: the inner barrier of the east straight
            SHORTCUT_OUT += [vs[i], vs[(i + 1) % N]]
            continue
        px, pz = round(px, 3), round(pz, 3)
        if ((i // 3) + (0 if side < 0 else 1)) % 2 == 0:
            add({"id": f"hedge_{i}_{tag}", "type": "box", "size": [1.3, 1.6, round(length, 3)], "position": [px, 0.8, pz], "rotation": [0, round(yaw, 3), 0],
                 "material": {"color": HEDGE[i % len(HEDGE)], "roughness": 1.0}})
            if i % 2 == 0:
                add({"id": f"bloom_{i}_{tag}", "type": "sphere", "radius": 0.3, "position": [px, 1.75, pz], "material": {"color": ["#ffb3c8", "#fff1a8", "#d5c6ff"][i % 3]}, "collide": False})
        else:
            add({"id": f"log_{i}_{tag}", "type": "box", "size": [1.1, 1.5, round(length, 3)], "position": [px, 0.75, pz], "rotation": [0, round(yaw, 3), 0],
                 "material": {"color": LOG if i % 2 == 0 else LOG_DARK, "roughness": 0.95}})
            # A log lying along the barrier: a group turned to the piece's heading, holding a cylinder laid on its side (nested turns are unambiguous).
            add({"id": f"logtop_{i}_{tag}", "type": "group", "position": [px, 1.6, pz], "rotation": [0, round(yaw, 3), 0], "collide": False,
                 "children": [{"id": f"logtop_{i}_{tag}_c", "type": "cylinder", "radius": 0.5, "height": round(length, 3), "rotation": [90, 0, 0],
                               "material": {"color": "#c9a173", "roughness": 0.95}, "collide": False}]})

# the dirt shortcut: across the infield from a gap in the south straight's inner barrier to a gap in the east straight's, cutting the south-east bend ------------------
in_west, in_east = min(SHORTCUT_IN), max(SHORTCUT_IN)                         # the two edges of the entrance gap (by x)
out_north, out_south = min(SHORTCUT_OUT, key=lambda v: v[1]), max(SHORTCUT_OUT, key=lambda v: v[1])   # the two edges of the exit gap (by z)
def wall(a, b, tag):
    n = max(1, int(math.dist(a, b) // 7.5))
    for k in range(n):
        p0 = (a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)
        p1 = (a[0] + (b[0] - a[0]) * (k + 1) / n, a[1] + (b[1] - a[1]) * (k + 1) / n)
        cx, cz, yaw, length = piece(p0, p1, 0.3)
        add({"id": f"sc_wall_{tag}_{k}", "type": "box", "size": [1.2, 1.5, round(length, 3)], "position": [round(cx, 3), 0.75, round(cz, 3)], "rotation": [0, round(yaw, 3), 0],
             "material": {"color": HEDGE[k % len(HEDGE)] if tag == "n" else LOG if k % 2 == 0 else LOG_DARK, "roughness": 1.0}})
wall(in_west, out_north, "n")                                                  # the north-west wall of the corridor
wall(in_east, out_south, "s")                                                  # the south-east wall
mid_in = ((in_west[0] + in_east[0]) / 2, (in_west[1] + in_east[1]) / 2)
mid_out = ((out_north[0] + out_south[0]) / 2, (out_north[1] + out_south[1]) / 2)
SC_STEPS = 14
SC_POINTS = [(mid_in[0] + (mid_out[0] - mid_in[0]) * k / SC_STEPS, mid_in[1] + (mid_out[1] - mid_in[1]) * k / SC_STEPS) for k in range(SC_STEPS + 1)]

# start / finish line and its arch ----------------------------------------------------------------------------------------------------------------------
line_x, line_z = 0.0, HALF_H
squares = 11
for k in range(squares):
    for row in (0, 1):
        z = line_z - ROAD / 2 + (k + 0.5) * (ROAD / squares)
        add({"id": f"chk_{k}_{row}", "type": "plane", "size": [1.2, ROAD / squares], "position": [line_x + (row - 0.5) * 1.2, 0.14, round(z, 3)],
             "material": {"color": "#ffffff" if (k + row) % 2 == 0 else "#5b5470", "roughness": 0.9}, "collide": False})
for z, tag in ((line_z - ROAD / 2 - 1.6, "a"), (line_z + ROAD / 2 + 1.6, "b")):
    add({"id": f"arch_post_{tag}", "type": "box", "size": [0.9, 7.0, 0.9], "position": [line_x, 3.5, z], "material": {"color": LOG}, "collide": False})
add({"id": "arch_bar", "type": "box", "size": [1.6, 1.4, ROAD + 4.2], "position": [line_x, 7.2, line_z], "material": {"color": LOG_DARK}, "collide": False})
add({"id": "arch_stripe", "type": "box", "size": [1.7, 0.5, ROAD + 4.3], "position": [line_x, 7.2, line_z], "material": {"color": "#fff1c1", "emissive": "#fff1c1"}, "collide": False})

# gates: one across each straight, thin along the road (axis-aligned rectangles), the first is the start line ---------------------------------------------------
zones.append({"id": "gate_line", "rect": [line_x - 1.5, line_z - ROAD / 2 - 1, line_x + 1.5, line_z + ROAD / 2 + 1]})
zones.append({"id": "gate_east", "rect": [HALF_W - ROAD / 2 - 1, -1.5, HALF_W + ROAD / 2 + 1, 1.5]})
zones.append({"id": "gate_north", "rect": [-1.5, -HALF_H - ROAD / 2 - 1, 1.5, -HALF_H + ROAD / 2 + 1]})
zones.append({"id": "gate_west", "rect": [-HALF_W - ROAD / 2 - 1, -1.5, -HALF_W + ROAD / 2 + 1, 1.5]})

# terrain: patches of mud, a ford and a dirt stretch on half of the road, so a driver can steer round them or take them (each animal is affected differently) -------------
surfaces = []
def patch(zone_id, kind, rect, color, y, extra=None, look=True):
    """A surface zone the simulation reads (`race.surfaces`) and the plane the player sees over it."""
    x0, z0, x1, z1 = rect
    zones.append({"id": zone_id, "rect": [x0, z0, x1, z1]})
    surfaces.append({"zone": zone_id, "kind": kind})
    if look:
        add({"id": f"{zone_id}_look", "type": "plane", "size": [round(x1 - x0, 2), round(z1 - z0, 2)], "position": [round((x0 + x1) / 2, 2), y, round((z0 + z1) / 2, 2)],
             "material": {"color": color, "roughness": 0.25 if kind == "water" else 1.0}, "collide": False})
    for k, (dx, dz) in enumerate(extra or []):
        add({"id": f"{zone_id}_bit_{k}", "type": "sphere", "radius": 0.35, "position": [round((x0 + x1) / 2 + dx, 2), 0.2, round((z0 + z1) / 2 + dz, 2)],
             "scale": [1.6, 0.35, 1.2], "material": {"color": "#f3f8ff" if kind == "water" else "#8a6a4a"}, "collide": False})
# mud across the racing line on the east straight (northbound): plough through it or steer round
patch("mud_east", "mud", [HALF_W - 7.0, -34.0, HALF_W + 3.0, -12.0], "#8a6a4a", 0.20, [(-2, -5), (2, 3), (-3, 6), (3, -8)])
# a ford across the racing line on the north straight (westbound): the Duck floats, the Beaver's kart shrugs it off, the others wade
patch("ford_north", "water", [12.0, -HALF_H - 5.0, 44.0, -HALF_H + 5.0], "#a9d8f0", 0.21, [(-8, 0), (0, 2), (9, -1)])
# a stretch of packed dirt across the racing line on the west straight (southbound): Coyote's karts don't lose speed on it
patch("dirt_west", "dirt", [-HALF_W - 5.0, 8.0, -HALF_W + 5.0, 36.0], "#b98f62", 0.19)

# the shortcut's floor: dirt patches stepped along the corridor (surface zones are axis-aligned), and a strip of packed earth for the eye
for k, (x, z) in enumerate(SC_POINTS):
    patch(f"dirt_cut_{k}", "dirt", [round(x - 8.5, 2), round(z - 8.5, 2), round(x + 8.5, 2), round(z + 8.5, 2)], "#a97f55", 0.19, look=False)
for k in range(SC_STEPS):
    cx, cz, yaw, length = piece(SC_POINTS[k], SC_POINTS[k + 1], 1.2)
    add({"id": f"dirt_cut_look_{k}", "type": "plane", "size": [11.0, round(length, 2)], "position": [round(cx, 3), 0.19 + 0.01 * (k % 3), round(cz, 3)],
         "rotation": [0, round(yaw, 3), 0], "material": {"color": "#a97f55" if k % 2 == 0 else "#b3885d", "roughness": 1.0}, "collide": False})

# item boxes: three rows of three across the road ----------------------------------------------------------------------------------------------------------
box_ids = []
rows = [(-55.0, HALF_H, "x"), (HALF_W, -25.0, "z"), (30.0, -HALF_H, "x"), (-HALF_W, 30.0, "z")]
for r, (cx, cz, axis) in enumerate(rows):
    for k in (-1, 0, 1):
        px, pz = (cx, cz + k * 6.0) if axis == "x" else (cx + k * 6.0, cz)
        bid = f"box_{r}_{k + 1}"
        zones.append({"id": bid, "rect": [px - 1.5, pz - 1.5, px + 1.5, pz + 1.5]})
        box_ids.append(bid)
        add({"id": bid, "type": "box", "size": [1.5, 1.5, 1.5], "position": [px, 1.4, pz], "rotation": [0, 45, 0], "collide": False,
             "material": {"color": "#ffe27a" if (r + k) % 2 == 0 else "#ffb3c8", "emissive": "#5a4a1e", "roughness": 0.4}})

# the forest: trees walling the track in, and a floor of mushrooms, ferns and stumps ------------------------------------------------------------------------
import random
rng = random.Random(7)
trees = 0
def pine(x, z, h):
    global trees
    i = trees; trees += 1
    add({"id": f"pt_{i}", "type": "cylinder", "radius": 0.6, "height": h * 0.35, "position": [x, h * 0.175, z], "material": {"color": LOG_DARK, "roughness": 0.95}, "collide": False})
    col = rng.choice(PINES)
    for k, (rr, hh, yy) in enumerate(((0.36, 0.42, 0.34), (0.28, 0.38, 0.55), (0.2, 0.32, 0.75))):
        add({"id": f"pc_{i}_{k}", "type": "cone", "radius": h * rr, "height": h * hh, "position": [x, h * yy, z], "material": {"color": col, "roughness": 0.9}, "collide": False})
    add({"id": f"pf_{i}", "type": "cone", "radius": h * 0.09, "height": h * 0.16, "position": [x, h * 0.98, z], "material": {"color": "#ffffff"}, "collide": False})
def oak(x, z, h):
    global trees
    i = trees; trees += 1
    add({"id": f"ot_{i}", "type": "cylinder", "radius": 0.75, "height": h * 0.5, "position": [x, h * 0.25, z], "material": {"color": LOG, "roughness": 0.95}, "collide": False})
    col = rng.choice(LEAVES)
    add({"id": f"oc_{i}", "type": "sphere", "radius": h * 0.36, "position": [x, h * 0.66, z], "material": {"color": col, "roughness": 0.9}, "collide": False})
    for k in range(2):
        add({"id": f"oc_{i}_{k}", "type": "sphere", "radius": h * 0.24, "position": [round(x + rng.uniform(-h * 0.25, h * 0.25), 2), h * rng.uniform(0.6, 0.78), round(z + rng.uniform(-h * 0.25, h * 0.25), 2)],
             "material": {"color": col, "roughness": 0.9}, "collide": False})
def blossom(x, z, h):
    global trees
    i = trees; trees += 1
    add({"id": f"bt_{i}", "type": "cylinder", "radius": 0.5, "height": h * 0.55, "position": [x, h * 0.275, z], "material": {"color": "#8a6a5a", "roughness": 0.95}, "collide": False})
    for k in range(3):
        add({"id": f"bc_{i}_{k}", "type": "sphere", "radius": h * rng.uniform(0.2, 0.3), "position": [round(x + rng.uniform(-h * 0.22, h * 0.22), 2), h * rng.uniform(0.62, 0.85), round(z + rng.uniform(-h * 0.22, h * 0.22), 2)],
             "material": {"color": rng.choice(["#ffc4d6", "#ffd9e4", "#f8b4cb"]), "roughness": 0.9}, "collide": False})
def in_cut(x, z, margin=13.0):
    """Whether (x, z) is within `margin` of the shortcut's corridor (or its two mouths): scenery keeps out so the way through can be seen."""
    (ax, az), (bx, bz) = mid_in, mid_out
    dx, dz = bx - ax, bz - az
    t = max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / (dx * dx + dz * dz)))
    return math.hypot(x - (ax + dx * t), z - (az + dz * t)) < margin
def any_tree(x, z):
    if in_cut(x, z):
        return
    h = rng.uniform(9.0, 19.0)
    r = rng.random()
    (pine if r < 0.5 else oak if r < 0.85 else blossom)(round(x, 2), round(z, 2), h)

# rows of trees along both sides of the track, stepping outwards so the forest is a wall of different depths
for i in range(0, N, 1):
    a_, b_, ux, uz, length = seg(i)
    mx, mz = (a_[0] + b_[0]) / 2, (a_[1] + b_[1]) / 2
    for side in (-1, 1):
        nx, nz = -uz * side, ux * side
        for row, extra in enumerate((5.5, 12.0, 20.0)):
            if rng.random() < (0.9 if row == 0 else 0.7):
                jitter = rng.uniform(-3.0, 3.0)
                off = ROAD / 2 + extra + rng.uniform(0, 3.0)
                any_tree(mx + nx * off + ux * jitter, mz + nz * off + uz * jitter)
# the infield: a stand of trees around a clearing with a stream
for i in range(70):
    x, z = rng.uniform(-HALF_W + ROAD + 6, HALF_W - ROAD - 6), rng.uniform(-HALF_H + ROAD + 6, HALF_H - ROAD - 6)
    if abs(x) < 34 and abs(z) < 16:
        continue                                                      # keep the clearing open
    any_tree(x, z)
# a distant ring of taller trees so the horizon is forest too
for i in range(120):
    ang = rng.uniform(0, math.tau)
    x, z = math.cos(ang) * rng.uniform(230, 262), math.sin(ang) * rng.uniform(170, 205)
    pine(round(x, 1), round(z, 1), rng.uniform(16, 26))

# forest floor: mushrooms, ferns, stumps, rocks and flowers beside the track
def beside_track(margin_lo, margin_hi):
    while True:
        x, z = _beside_track(margin_lo, margin_hi)
        if not in_cut(x, z):
            return x, z
def _beside_track(margin_lo, margin_hi):
    i = rng.randrange(N)
    a_, b_, ux, uz, length = seg(i)
    side = rng.choice((-1, 1))
    nx, nz = -uz * side, ux * side
    off = ROAD / 2 + rng.uniform(margin_lo, margin_hi)
    return a_[0] + nx * off + ux * rng.uniform(0, length), a_[1] + nz * off + uz * rng.uniform(0, length)
for i in range(55):
    x, z = beside_track(2.6, 9.0)
    h = rng.uniform(0.5, 1.2)
    add({"id": f"mstem_{i}", "type": "cylinder", "radius": 0.18 * h, "height": h, "position": [round(x, 2), h / 2, round(z, 2)], "material": {"color": "#fff4e6"}, "collide": False})
    add({"id": f"mcap_{i}", "type": "sphere", "radius": 0.5 * h, "position": [round(x, 2), h * 1.05, round(z, 2)],
         "material": {"color": rng.choice(["#ff9eb5", "#ffb38a", "#e2c2ff", "#ffe08a"]), "roughness": 0.7}, "collide": False})
for i in range(40):
    x, z = beside_track(2.6, 10.0)
    add({"id": f"fern_{i}", "type": "cone", "radius": 0.6, "height": rng.uniform(0.9, 1.5), "position": [round(x, 2), 0.6, round(z, 2)], "material": {"color": "#7fcf9a"}, "collide": False})
for i in range(22):
    x, z = beside_track(3.0, 12.0)
    add({"id": f"stump_{i}", "type": "cylinder", "radius": rng.uniform(0.6, 1.0), "height": rng.uniform(0.6, 1.1), "position": [round(x, 2), 0.4, round(z, 2)], "material": {"color": LOG}, "collide": False})
    add({"id": f"stumptop_{i}", "type": "cylinder", "radius": 0.5, "height": 0.05, "position": [round(x, 2), 0.95, round(z, 2)], "material": {"color": "#e6c9a0"}, "collide": False})
for i in range(18):
    x, z = beside_track(3.0, 14.0)
    add({"id": f"rock_{i}", "type": "sphere", "radius": rng.uniform(0.6, 1.4), "position": [round(x, 2), 0.3, round(z, 2)], "scale": [1.3, 0.7, 1.0], "material": {"color": "#c9c6d6", "roughness": 1.0}, "collide": False})
for i in range(70):
    x, z = beside_track(2.6, 14.0)
    add({"id": f"flower_{i}", "type": "sphere", "radius": 0.22, "position": [round(x, 2), 0.22, round(z, 2)], "material": {"color": rng.choice(["#ffb3c8", "#fff1c1", "#c9e4ff", "#e2d5f5"])}, "collide": False})
# fireflies: tiny glowing beads hanging in the trees
for i in range(45):
    x, z = beside_track(4.0, 16.0)
    add({"id": f"firefly_{i}", "type": "sphere", "radius": 0.12, "position": [round(x, 2), round(rng.uniform(1.8, 5.5), 2), round(z, 2)],
         "material": {"color": "#fff6a8", "emissive": "#fff6a8"}, "collide": False})
# the infield clearing: a stream with stepping stones
add({"id": "stream", "type": "plane", "size": [64, 9], "position": [0, 0.05, 0], "rotation": [0, 8, 0], "material": {"color": "#a9d8f0", "roughness": 0.15}, "collide": False})
for k in range(9):
    add({"id": f"stone_{k}", "type": "sphere", "radius": 0.7, "position": [round(-24 + k * 6, 1), 0.1, round(k % 2 * 1.2 - 0.6, 1)], "scale": [1.2, 0.35, 1.0], "material": {"color": "#d8d4e6"}, "collide": False})

# the racing line for bots: the centre line, every other point ---------------------------------------------------------------------------------------------------
i0 = max(j for j in range(N // 2) if PATH[j][1] > HALF_H - 1 and PATH[j][0] < mid_in[0] - 10)                    # the last south-straight point before the entrance
i1 = min(j for j in range(N) if j > i0 + 5 and PATH[j][0] > HALF_W - 5 and PATH[j][1] < mid_out[1] - 3)        # the first east-straight point past the exit
assert i0 < i1, (i0, i1)
approach = [(mid_in[0] - 6.0, HALF_H - 4.0)]
leave = [(mid_out[0] + 7.0, mid_out[1] - 6.0)]
cut = approach + SC_POINTS[::3] + [SC_POINTS[-1]] + leave
line = []
spliced = False
for j in range(0, N, 2):
    if i0 < j < i1:
        if not spliced:
            line += [[round(x, 2), round(z, 2)] for (x, z) in cut]
            spliced = True
        continue
    line.append([round(PATH[j][0], 2), round(PATH[j][1], 2)])

# eight grid places behind the line, two abreast, facing east ------------------------------------------------------------------------------------------------------
spawns = []
for i in range(8):
    row, col = divmod(i, 2)
    spawns.append({"id": f"grid_{i + 1}", "position": [round(line_x - 7.0 - 5.0 * row, 2), 0, round(line_z + (-3.2 if col == 0 else 3.2), 2)], "yaw_deg": 90, "group": "race"})

# the animals' karts: game-local prefabs, parked out of sight until the client places them -------------------------------------------------------------------
prefab_file = sys.argv[2] if len(sys.argv) > 2 else "assets/karts.json"
library = json.load(open(prefab_file))
prefabs = {p["name"]: {k: v for k, v in p.items() if k != "name"} for p in library}
for k, p in enumerate(library):
    add({"id": p["name"], "type": "prefab", "prefab": p["name"], "position": [0, -50, 0], "collide": False, "lint_ignore": ["sunk"]})

scene = {
    "camera": {"position": [0, 60, 150], "target": [0, 0, 0], "fov": 60, "near": 0.3, "far": 900},
    "background": {"sky_top": SKY_TOP, "sky_bottom": SKY_BOTTOM},
    "ambient": {"color": "#f6f0e0", "intensity": 0.62},
    "lights": [{"id": "sun", "type": "directional", "direction": [-0.4, -1.0, -0.6], "color": "#fff1d6", "intensity": 1.15}],
    "post": {"enabled": True, "ao": 0.6, "outline": 0.25, "ao_radius": 0.6},
    "player": {"mode": "peaceful"},
    "music": False,
    "zones": zones,
    "spawns": spawns,
    "race": {"laps": 3, "gates": ["gate_line", "gate_east", "gate_north", "gate_west"], "countdown_secs": 3, "finish_grace_secs": 30,
             "item_boxes": box_ids, "item_respawn_secs": 6, "line": line, "surfaces": surfaces},
    "bots": {"fill": 8, "skill": "normal"},
    # lobby (pick your animal, ready up) -> a one second hold -> the race (its own countdown) -> results -> lobby. A kart cannot join a race in progress.
    "match": {"min_players": 1, "countdown_secs": 1, "round_secs": 600, "results_secs": 20, "join_in_progress": False, "ready_check": True},
    "checks": {"lint": {"max_errors": 0}},
    "prefabs": prefabs,
    "objects": objects,
}
json.dump(scene, open(sys.argv[1] if len(sys.argv) > 1 else "maps/main.json", "w"), separators=(",", ":"))
print(f"wrote {len(objects)} objects, {len(zones)} zones, {len(line)} line points, {N} centre-line pieces, lap about {sum(seg(i)[4] for i in range(N)):.0f} m")
