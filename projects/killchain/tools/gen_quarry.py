#!/usr/bin/env python3
"""Generates maps/quarry.json: QUARRY, Killchain's big open desert map.

A sandstone quarry worked out to a ragged floor: each team holds a raised plateau at its end (4 m up, stairs down at two points, a rail along
the edge), the floor between them is cut by rock outcrops, a haul truck and a central mesa with an excavator on top, and two overlooks in
the north and south walls give the scoped weapons a view of the whole floor. About 184 x 120 m, the longest sightlines in the game: a
marksman on the mesa sees both stair heads. Point-symmetric, so neither side has the better lane.
Modes: capture the flag (flags on the plateaus), search and destroy (attackers west; site A on the mesa, site B at the east stairs),
free for all (neutral spawns spread over the floor).
Run: python3 tools/gen_quarry.py  (then tools/prune_nav.py maps/quarry.json)
"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mapkit as mk
from mapkit import objs, solids, pick, spawns, lights, box, cyl, mat, nid, free, spot, add_node, link, nearest, stairs

W, H = 92, 60
mk.configure(W, H, ground=(240, 160), seed=21, step=7.0)
rnd = mk.rnd

SAND, SAND2, ROCK, ROCK2, DUST = "#c4a06a", "#957650", "#8a5a3a", "#6e4a33", "#c9a875"
METAL, DARKM, YEL, RED, TEAL = "#5a6068", "#2f3338", "#d0a020", "#9a3d2a", "#2f6b72"
PLAT = 4.0       # plateau height
MESA = 3.0

objs.append({"id": "ground", "type": "plane", "size": [260, 180], "material": mat(SAND2, 0.97)})

# ---- the rim: sandstone walls all round --------------------------------------------------------------------------------------
for (x, z, sx, sz) in [(0, -H - 3, 2 * W + 10, 6), (0, H + 3, 2 * W + 10, 6), (-W - 3, 0, 6, 2 * H), (W + 3, 0, 6, 2 * H)]:
    box("rim", x, z, sx, 14, sz, ROCK, rough=1.0)
    box("rim_cap", x, z, sx + 0.6, 1.2, sz + 0.6, ROCK2, y=14)

def both(fn, *a):
    """Place something and its point-symmetric twin: fn(x, z, *rest) is called for (x, z) and (-x, -z); `flip` is True for the twin."""
    x, z, *rest = a
    fn(x, z, False, *rest)
    fn(-x, -z, True, *rest)

# ---- the plateaus -----------------------------------------------------------------------------------------------------------
def plateau(x, z, flip):
    sgn = 1 if flip else -1                      # the west plateau (flip False) sits at negative x and its edge faces +x
    box("plateau", sgn * 78, 0, 28, PLAT, 120, SAND, rough=0.95)
    box("plateau_edge", sgn * 63.6, 0, 0.8, 0.5, 120, ROCK2, y=PLAT, collide=False)
    # rail along the edge, with a 3.2 m gap at each staircase
    for (z0, z1) in [(-60, -31.6), (-28.4, 28.4), (31.6, 60)]:
        box("rail", sgn * 64.1, (z0 + z1) / 2, 0.14, 1.1, z1 - z0, YEL, y=PLAT, rough=0.6, metal=0.3, top=True)
    # sandbags and crates up top, to fight from
    for (dx, dz, sx, sy, sz, c) in [(-70, -14, 5, 1.2, 1.0, "#a79470"), (-70, 14, 5, 1.2, 1.0, "#a79470"), (-76, -6, 1.0, 1.2, 5, "#a79470"), (-76, 6, 1.0, 1.2, 5, "#a79470"),
                                    (-82, -24, 3, 1.8, 3, "#7d6036"), (-82, 24, 3, 1.8, 3, "#7d6036"), (-66, -42, 4, 1.4, 1.6, "#6d7479"), (-66, 42, 4, 1.4, 1.6, "#6d7479")]:
        box("cover", (-dx if flip else dx), (-dz if flip else dz), sx, sy, sz, c, y=PLAT, top=True)
    # the flag stand
    box("flag_base", sgn * 80, 0, 3.2, 0.3, 3.2, TEAL if not flip else RED, y=PLAT, top=False, collide=False)

plateau(0, 0, False)
plateau(0, 0, True)

def cheeks(cx, cz, length, width, h, color=ROCK2):
    """Solid blocks along both sides of a staircase that climbs along x, so the stair is a walled cut and nobody walks off its edge."""
    for sgn in (-1, 1):
        # 1.4 m above the floor they flank: too high to climb onto, so nobody can walk along the top and off the end
        box("cheek", cx, cz + sgn * (width / 2 + 0.55), length, h + 1.4, 1.0, color, rough=1.0)

STAIR_RUN = 14
def plateau_stairs(zc, flip):
    # climbs toward the plateau: west plateau toward -x (rotation 270), east toward +x (rotation 90)
    if not flip:
        stairs(-57, zc, 270, PLAT, STAIR_RUN, width=3.2, steps=20, color="#8b7551")
    else:
        stairs(57, -zc, 90, PLAT, STAIR_RUN, width=3.2, steps=20, color="#8b7551")
    cheeks(-57 if not flip else 57, zc if not flip else -zc, STAIR_RUN, 3.2, PLAT)
    solids.append((-65.5, zc - 2.2, -49.5, zc + 2.2) if not flip else (49.5, -zc - 2.2, 65.5, -zc + 2.2))
for zc in (-30, 30):
    plateau_stairs(zc, False)
    plateau_stairs(zc, True)

# ---- the mesa in the middle ---------------------------------------------------------------------------------------------------
box("mesa", 0, 0, 24, MESA, 20, SAND, rough=0.95)
stairs(-18, 0, 90, MESA, 12, width=3.2, steps=15, color="#8b7551")
stairs(18, 0, 270, MESA, 12, width=3.2, steps=15, color="#8b7551")
solids.append((-25, -2.2, -11, 2.2)); solids.append((11, -2.2, 25, 2.2))
cheeks(-18, 0, 12, 3.2, MESA)
cheeks(18, 0, 12, 3.2, MESA)
# rails round the mesa top, with a gap where each staircase arrives
for zs in (-9.9, 9.9):
    box("mesa_rail", 0, zs, 24, 1.1, 0.14, YEL, y=MESA, top=True, rough=0.6)
for xs in (-11.9, 11.9):
    for (a, b) in [(-10, -1.7), (1.7, 10)]:
        box("mesa_rail", xs, (a + b) / 2, 0.14, 1.1, b - a, YEL, y=MESA, top=True, rough=0.6)
# the excavator on top: cab, boom, tracks, counterweight
box("excavator_tracks", 0, 0, 9, 1.0, 4.4, DARKM, y=MESA, top=True, metal=0.3)
box("excavator_cab", -1, 0, 4.4, 2.4, 3.6, YEL, y=MESA + 1.0, top=True, metal=0.3)
box("excavator_boom", 3.2, 0, 7, 0.7, 0.9, YEL, y=MESA + 2.6, top=False, collide=False, metal=0.3)
box("crate_top", -7, -6, 2.0, 1.4, 2.0, "#7d6036", y=MESA, top=True)
box("crate_top", 7, 6, 2.0, 1.4, 2.0, "#7d6036", y=MESA, top=True)
box("barrel_row", 0, -8, 6.0, 1.1, 0.9, RED, y=MESA, top=True)
box("barrel_row", 0, 8, 6.0, 1.1, 0.9, TEAL, y=MESA, top=True)

# ---- rock outcrops: break the long sightlines -----------------------------------------------------------------------------------
def outcrop(x, z, flip, sx, sy, sz, rot):
    r = (rot + 180) % 360 if flip else rot
    box("rock", x, z, sx, sy, sz, ROCK if (int(abs(x)) + int(abs(z))) % 2 else ROCK2, rough=1.0, rot=r)
    box("rock_top", x, z, sx * 0.7, 0.8, sz * 0.7, DUST, y=sy, rough=1.0, rot=r, collide=False)

for (x, z, sx, sy, sz, rot) in [(-42, -22, 7, 4.5, 5, 20), (-40, 24, 5, 3.5, 7, -15), (-24, -40, 8, 5.0, 4, 35), (-20, 42, 6, 3.0, 5, 0),
                                (-47, 2, 3, 2.2, 8, 0), (-30, -6, 4, 2.4, 3, 45), (-32, 8, 3, 2.0, 3.5, 10), (-12, -22, 5, 2.6, 4, 60),
                                (-8, 28, 4, 2.0, 6, -30), (-54, -46, 6, 3.0, 6, 25)]:
    both(outcrop, x, z, sx, sy, sz, rot)

# a haul truck across the middle lane (cover you can walk around), and its twin
def truck(x, z, flip):
    box("truck_bed", x, z, 10, 2.6, 4.2, "#a78a3c", y=1.0, metal=0.3, rough=0.7)
    box("truck_cab", x + (5.6 if not flip else -5.6), z, 2.6, 2.8, 4.0, YEL, y=1.0, metal=0.3)
    for wx in (-3, 3):
        for wz in (-2.4, 2.4):
            cyl("wheel", x + wx, z + wz, 1.0, 0.8, "#1c1e20", pos_y=1.0, rot=[90, 0, 0])
both(truck, -34, -20, )

# barrels, crates and a conveyor, scattered symmetrically
for (x, z) in [(-52, 18), (-14, -8), (-26, 22), (-58, -12), (-6, 18)]:
    both(lambda px, pz, f: [box("barrel", px + dx * 0.8, pz + dz * 0.8, 0.9, 1.2, 0.9, RED if (dx + dz) % 2 else TEAL, rough=0.7, metal=0.3) for dx in (0, 1) for dz in (0, 1)], x, z)
for (x, z, al) in [(-46, -38, "x"), (-14, 46, "x")]:
    both(lambda px, pz, f: box("conveyor", px, pz, 22 if al == "x" else 1.2, 0.9, 1.2 if al == "x" else 22, METAL, metal=0.4), x, z)

# ---- overlooks in the north and south walls ---------------------------------------------------------------------------------
def overlook(x, z, flip):
    sgn = -1 if not flip else 1
    box("overlook", x, z, 16, 3.0, 10, SAND, rough=0.95)
    box("overlook_rail", x, z + (4.9 if z < 0 else -4.9), 16, 1.0, 0.14, YEL, y=3.0, top=True, rough=0.6)  # the edge facing the quarry
    # the short sides: the one the stairs arrive on keeps a gap of the stairs' width (3.4 m) for them
    near = x + 7.9 if not flip else x - 7.9
    far = x - 7.9 if not flip else x + 7.9
    box("overlook_rail", far, z, 0.14, 1.0, 10, YEL, y=3.0, top=True, rough=0.6)
    zc = z + (1.5 if not flip else -1.5)
    for (a, b) in [(z - 5, zc - 1.7), (zc + 1.7, z + 5)]:
        if b > a:
            box("overlook_rail", near, (a + b) / 2, 0.14, 1.0, b - a, YEL, y=3.0, top=True, rough=0.6)
    # stairs on the long side that faces the quarry, climbing along x
    if not flip:
        stairs(x + 14, z + 1.5, 270, 3.0, 12, width=3.0, steps=15, color="#8b7551")
        cheeks(x + 14, z + 1.5, 12, 3.0, 3.0)
        solids.append((x + 7.5, z - 0.5, x + 20.5, z + 3.5))
    else:
        stairs(x - 14, z - 1.5, 90, 3.0, 12, width=3.0, steps=15, color="#8b7551")
        cheeks(x - 14, z - 1.5, 12, 3.0, 3.0)
        solids.append((x - 20.5, z - 3.5, x - 7.5, z + 0.5))
overlook(-8, -55, False)
overlook(8, 55, True)

# ---- lighting: a high hard sun ------------------------------------------------------------------------------------------------
lights.append({"id": "sun", "type": "directional", "direction": [-0.35, -1, -0.45], "color": "#ffe9c8", "intensity": 2.0})
for (x, z) in [(-80, -46), (-80, 46), (80, -46), (80, 46)]:
    mk.light("point", x, PLAT + 5, z, "#ffd9a0", 6, 20)

# ---- pickups -----------------------------------------------------------------------------------------------------------------
# on the plateau by the spawns
for (w, x, z) in [("bulldog", -84, -8, ), ("marshal", -84, 8), ("stinger", -86, -16), ("wasp", -86, 16), ("ammo", -88, 0), ("frag", -74, 0)]:
    spot(w, x, z, y=PLAT + 0.3)
# at the stair heads: rifles
for (w, x, z) in [("rifle", -60, -32), ("carbine", -60, 32), ("ironside", -60, -26), ("ranger", -60, 26)]:
    spot(w, x, z, y=PLAT + 0.3)
# on the floor: the middle prizes and cover pickups
for (w, x, z) in [("bullpup", -26, 0), ("auto12", -36, -34), ("shotgun", -36, 34), ("coach", -16, -12), ("flash", -50, -22), ("smoke", -50, 22), ("incendiary", -22, 14),
                  ("hatchet", -44, 6), ("bat", -44, -6), ("ammo", -30, 2), ("thumper", -14, -30), ("handcannon", -28, -16), ("ammo", -52, 0)]:
    spot(w, x, z)
# the mesa: the heavy weapons
spot("lancer", -8, 0, y=MESA + 0.3)
spot("lmg", 0, -7.5, y=MESA + 0.3, twin=False)
spot("hammer", 0, 7.5, y=MESA + 0.3, twin=False)
spot("frag", -4, 7.5, y=MESA + 0.3)
# the overlooks: the long guns
spot("sentinel", -8, -55, y=3.3, respawn=45, twin=False)
pick.append({"weapon": "scout", "at": [8, 3.3, 55], "respawn_secs": 45})
spot("marksman", -2, -55, y=3.3, respawn=45, twin=True)
spot("ammo", -12, -52, y=3.3)

# the newer weapons: the heavy ones in the open middle, the long gun on an overlook, close-in tools by the stair heads
for (w, x, z, r) in [("reaper", -34, 0, 60), ("breaker", -36, -34, 30), ("flare", -52, 14, 30), ("lobber", -28, 16, 45), ("impact", -48, 8, 30), ("machete", -42, -30, 30)]:
    mk.spot_near(w, x, z, respawn=r)
spot("hunter", -8, -52, y=3.3, respawn=40)
spot("sledge", -72, 20, y=PLAT + 0.3, respawn=40)

# ---- spawns: on the plateaus (team) and over the floor (free for all) ------------------------------------------------------------
for i in range(6):
    x, z = -86 + (i % 2) * 4, -10 + (i // 2) * 8 + (i % 2) * 2
    spawns.append({"id": f"ridge_{i}", "position": [x, PLAT, z], "yaw_deg": 90, "group": "team1"})
    spawns.append({"id": f"night_{i}", "position": [-x, PLAT, -z], "yaw_deg": 270, "group": "team2"})

def near_free(x, z, pad=1.5):
    for r in [0.0] + [1.0 * i for i in range(1, 12)]:
        for a in range(0, 360, 30) if r else [0]:
            px, pz = x + r * math.cos(math.radians(a)), z + r * math.sin(math.radians(a))
            if free(px, pz, pad):
                return round(px, 1), round(pz, 1)
    raise AssertionError((x, z))
for (x, z) in [(-40, 0), (40, 0), (-24, -30), (24, 30), (-20, 24), (20, -24), (0, -34), (0, 34)]:
    px, pz = near_free(x, z)
    spawns.append({"id": f"ffa_{len(spawns)}", "position": [px, 0, pz], "yaw_deg": round(math.degrees(math.atan2(-px, pz)) % 360), "group": "ffa"})

# ---- nav ----------------------------------------------------------------------------------------------------------------------
mk.build_ground_nav()
# plateaus: a grid of raised nodes joined to the ground at the stair feet
for (nm, x0, x1, flip) in [("pw", -90, -66, False), ("pe", 66, 90, True)]:
    grid = mk.raised_nav(nm, x0, -54, x1, 54, PLAT, step=6.0)
    for zc in (-30, 30):
        zz = zc if not flip else -zc
        edge = -64.5 if not flip else 64.5
        foot = -49 if not flip else 49
        top = mk.nearest_raised(grid, edge + (-1.0 if not flip else 1.0), zz)
        t = mk.stair_link(f"{nm}_stairs_{'n' if zc < 0 else 's'}", (foot, zz), (edge + (-1.0 if not flip else 1.0), PLAT, zz))
        link(t, top)
# the mesa
mgrid = mk.raised_nav("mesa", -9, -7, 9, 7, MESA, step=4.5)
for (side, fx, tx) in [("w", -25, -11), ("e", 25, 11)]:
    t = mk.stair_link(f"mesa_{side}", (fx, 0), (tx, MESA, 0))
    link(t, mk.nearest_raised(mgrid, tx, 0))
# the overlooks
for (nm, x0, z0, x1, z1, fx, fz, tx, tz) in [("ovn", -15, -59, 0, -51, -8 + 14 + 7, -55 + 1.5, -8 + 7.5, -55 + 1.5), ("ovs", 0, 51, 15, 59, 8 - 14 - 7, 55 - 1.5, 8 - 7.5, 55 - 1.5)]:
    g = mk.raised_nav(nm, x0, z0, x1, z1, 3.0, step=4.0)
    t = mk.stair_link(f"{nm}_stairs", (fx, fz), (tx, 3.0, tz))
    link(t, mk.nearest_raised(g, tx, tz))

# ---- game modes -----------------------------------------------------------------------------------------------------------------
MODES = {
    "flags": [{"team": 1, "at": [-80, PLAT, 0]}, {"team": 2, "at": [80, PLAT, 0]}],
    "sites": [{"name": "A", "at": [0, MESA, 0], "radius": 6}, {"name": "B", "at": [56, 0, -22], "radius": 6}],
    "objective": {"capture_limit": 3, "return_secs": 15, "win_rounds": 4, "swap_after": 3, "round_secs": 110, "freeze_secs": 5, "plant_secs": 3, "defuse_secs": 5, "fuse_secs": 40},
}
mk.emit("maps/quarry.json", camera={"position": [-86, 5.7, 0], "target": [0, 3, 0], "fov": 90},
        background={"sky_top": "#6fa0d8", "sky_bottom": "#e6d6b0"}, ambient={"color": "#e8dcc8", "intensity": 0.38}, name="Quarry", short="QUARRY",
        extra_shooter=MODES,
        sky={"zenith": "#3f78c8", "horizon": "#ecd8a8", "gradient_power": 0.5, "sun": {"direction": [0.35, 1, 0.45], "size_deg": 2.2, "color": "#fff1d8", "glow": 0.6}},
        combat={"respawn_secs": 6, "spawn": "farthest", "spawn_protect_secs": 2.0, "regen_delay_secs": 5, "regen_per_sec": 20})
