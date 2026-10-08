#!/usr/bin/env python3
"""Shared building blocks for Killchain's map generators (gen_map.py = Ironworks, gen_quarry.py, gen_terminus.py).

State is module-level on purpose: a generator is a short script that imports this, calls `configure`, places things, then `emit`s one map.
Everything that blocks movement also registers a footprint in `solids`, which the nav-graph builder uses to keep bots out of walls.

Typical use:
    import mapkit as k
    k.configure(half_w=86, half_h=54, ground=(220, 150), seed=9)
    k.box("crate", 10, 5, 1.6, 1.6, 1.6, "#8a6a3f")
    k.spot("rifle", -58, -22)                      # a pickup and its point-symmetric twin
    k.team_spawns(...)                             # six a side
    k.emit("maps/main.json", extra_shooter={...})  # mode data (flags, sites) goes in extra_shooter
"""
import json, math, random

objs, solids, pick, spawns, lights = [], [], [], [], []
elev = []  # footprints of things standing on raised floors: (y_of_floor, x0, z0, x1, z1)
_n = {}
rnd = random.Random(1)
W = H = 0.0
_ground = (200, 140)
nodes, edges, index = [], [], {}
STEP = 7.0

def configure(half_w, half_h, ground=None, seed=1, step=7.0):
    """Sets the playable half extents (the nav graph and `free` stay inside them) and the RNG seed."""
    global W, H, _ground, rnd, STEP
    W, H, rnd, STEP = half_w, half_h, random.Random(seed), step
    _ground = ground or (2 * W + 40, 2 * H + 40)

def nid(p):
    _n[p] = _n.get(p, 0) + 1
    return f"{p}_{_n[p]}"

def mat(color, rough=0.9, metal=0.0, emissive=None, opacity=None):
    m = {"color": color, "roughness": rough}
    if metal: m["metallic"] = metal
    if emissive: m["emissive"] = emissive
    if opacity is not None: m["opacity"] = opacity
    return m

def box(p, x, z, sx, sy, sz, color, y=0.0, rough=0.9, metal=0.0, collide=True, rot=None, emissive=None, top=False):
    """A box standing on `y` (its base), centred on x/z. Solid boxes taller than 0.4 m also block the nav graph; with `top=True` it stands on
    a raised floor, so it blocks only that floor's nav nodes (see `raised_nav`), not the ground beneath."""
    o = {"id": nid(p), "type": "box", "size": [sx, sy, sz], "position": [x, y + sy / 2, z], "material": mat(color, rough, metal, emissive)}
    if not collide: o["collide"] = False
    if rot: o["rotation"] = [0, rot, 0]
    objs.append(o)
    if collide and sy > 0.4:
        rect = (x - sx / 2 - 0.3, z - sz / 2 - 0.3, x + sx / 2 + 0.3, z + sz / 2 + 0.3)
        if top:
            elev.append((y,) + rect)
        else:
            solids.append(rect)
    return o

def cyl(p, x, z, r, h, color, y=0.0, rot=None, metal=0.3, rough=0.6, pos_y=None, emissive=None):
    o = {"id": nid(p), "type": "cylinder", "radius": r, "height": h, "position": [x, (y + h / 2) if pos_y is None else pos_y, z],
         "material": mat(color, rough, metal, emissive), "collide": False}
    if rot: o["rotation"] = rot
    objs.append(o)
    return o

def stairs(x, z, rot, rise, run, width=3.0, color="#5d646d", steps=None):
    """A staircase whose bottom-centre is at x/z climbing along `rot` (0, 90, 180, 270 degrees: +z, -x... see the engine's `stairs`)."""
    o = {"id": nid("stairs"), "type": "stairs", "width": width, "run": run, "rise": rise, "steps": steps or max(4, int(rise / 0.2)),
         "position": [x, 0, z], "rotation": [0, rot, 0], "material": mat(color, 0.7, 0.4)}
    objs.append(o)
    return o

def light(kind, x, y, z, color, intensity, rng=20):
    lights.append({"id": nid("lamp"), "type": kind, "position": [x, y, z], "color": color, "intensity": intensity, "range": rng})

def wall_solids(x0, z0, x1, z1, gaps):
    """Footprints for an axis-aligned wall with gaps `(centre, width)` along it (solids alone only knows boxes and whole buildings)."""
    horizontal = z0 == z1
    a, b = (x0, x1) if horizontal else (z0, z1)
    cuts = sorted([(c - w / 2, c + w / 2) for c, w in gaps])
    cur = a
    for lo, hi in cuts + [(b, b)]:
        if lo > cur:
            solids.append((cur, z0 - 0.5, lo, z0 + 0.5) if horizontal else (x0 - 0.5, cur, x0 + 0.5, lo))
        cur = max(cur, hi)

def building(x0, z0, x1, z1, h, doors, color, roof=True, label="bldg", windows=True, roof_color="#2f343a", thick=0.4):
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
        objs.append({"id": nid(label), "type": "wall", "from": [fx, fz], "to": [tx, tz], "height": h, "thickness": thick, "openings": ops, "material": mat(color, 0.9)})
    if roof:
        box(label + "_roof", (x0 + x1) / 2, (z0 + z1) / 2, abs(x1 - x0) + 0.8, 0.4, abs(z1 - z0) + 0.8, roof_color, y=h, rough=0.8)

def room(x0, z0, x1, z1, h, doors, color, roof=True, label="room", roof_color="#454b53", thick=0.5, door_h=3.2, windows=()):
    """A room whose interior stays walkable for the nav graph (unlike `building`, which blocks its whole footprint). `doors` maps a side
    (n, s, w, e) to a list of `(centre, width)` along that wall in absolute coordinates (x for n/s, z for w/e); `windows` is the same with a
    sill height: `(side, centre, width)`. Walls are registered with gaps at the doors, so bots and players pass exactly where the doors are."""
    sides = {"n": (x0, z0, x1, z0), "s": (x0, z1, x1, z1), "w": (x0, z0, x0, z1), "e": (x1, z0, x1, z1)}
    for side, (fx, fz, tx, tz) in sides.items():
        horizontal = fz == tz
        start = fx if horizontal else fz
        gaps = doors.get(side, [])
        ops = [{"kind": "door", "at": round(c - w / 2 - start + w / 2, 2), "width": w, "height": min(door_h, h - 0.3)} for (c, w) in gaps]
        ops += [{"kind": "window", "at": round(c - start, 2), "width": w, "height": 1.3, "sill": 1.6} for (sd, c, w) in windows if sd == side]
        objs.append({"id": nid(label), "type": "wall", "from": [fx, fz], "to": [tx, tz], "height": h, "thickness": thick, "openings": ops, "material": mat(color, 0.9)})
        wall_solids(fx, fz, tx, tz, gaps)
    if roof:
        box(label + "_roof", (x0 + x1) / 2, (z0 + z1) / 2, abs(x1 - x0) + 1.0, 0.4, abs(z1 - z0) + 1.0, roof_color, y=h, rough=0.8)

def free(x, z, pad=0.9):
    if abs(x) > W - 2.5 or abs(z) > H - 2.5:
        return False
    return not any(a - pad < x < c + pad and b - pad < z < e + pad for (a, b, c, e) in solids)

def clear_line(x0, z0, x1, z1):
    n = int(math.hypot(x1 - x0, z1 - z0) / 0.6) + 1
    return all(free(x0 + (x1 - x0) * k / n, z0 + (z1 - z0) * k / n, 0.6) for k in range(n + 1))

def build_ground_nav():
    """A grid of ground nodes joined where the straight line between them is clear. Call after every solid is placed."""
    xs = [(-W + 4) + STEP * i for i in range(int((2 * W - 8) / STEP) + 1)]
    zs = [(-H + 4) + STEP * i for i in range(int((2 * H - 8) / STEP) + 1)]
    for x in xs:
        for z in zs:
            if free(x, z, 1.0):
                index[(x, z)] = len(nodes)
                nodes.append({"id": f"n{len(nodes)}", "pos": [round(x, 1), 0, round(z, 1)]})
    for (x, z), i in index.items():
        for dx, dz in [(STEP, 0), (0, STEP), (STEP, STEP), (STEP, -STEP)]:
            j = index.get((x + dx, z + dz))
            if j is not None and clear_line(x, z, x + dx, z + dz):
                edges.append([nodes[i]["id"], nodes[j]["id"]])

def raised_nav(prefix, x0, z0, x1, z1, y, step=6.0, pad=1.0):
    """Nav nodes on a raised floor (top at height `y`) covering the rectangle, skipping anything standing on it (`top=True` boxes).
    Returns {(i, j): node id}. Neighbouring nodes are linked when the line between them is clear."""
    nx, nz = max(1, int((x1 - x0) / step)), max(1, int((z1 - z0) / step))
    grid = {}
    def blocked(px, pz, m):
        return any(abs(fy - y) < 0.3 and a - m < px < c + m and b - m < pz < e + m for (fy, a, b, c, e) in elev)
    for i in range(nx + 1):
        for j in range(nz + 1):
            px, pz = x0 + (x1 - x0) * i / nx, z0 + (z1 - z0) * j / nz
            if not blocked(px, pz, pad):
                grid[(i, j)] = add_node(f"{prefix}_{i}_{j}", round(px, 1), y, round(pz, 1))
    pos = {n["id"]: n["pos"] for n in nodes if n["id"].startswith(prefix + "_")}
    def clear(a, b):
        (ax, _, az), (bx, _, bz) = pos[a], pos[b]
        k = max(2, int(math.hypot(bx - ax, bz - az) / 0.6))
        return all(not blocked(ax + (bx - ax) * t / k, az + (bz - az) * t / k, 0.6) for t in range(k + 1))
    for (i, j), a in grid.items():
        for di, dj in [(1, 0), (0, 1), (1, 1), (1, -1)]:
            b = grid.get((i + di, j + dj))
            if b and clear(a, b):
                link(a, b)
    return grid

def nearest_raised(grid, x, z):
    """The id of the node of a `raised_nav` grid closest to x/z."""
    best = None
    for nid_ in grid.values():
        px, _, pz = next(n["pos"] for n in nodes if n["id"] == nid_)
        d = math.hypot(px - x, pz - z)
        if best is None or d < best[0]:
            best = (d, nid_)
    return best[1]

def stair_link(name, bottom, top, lead=3.5):
    """Joins the ground graph to a raised-floor node `top` (x, y, z) through the staircase whose foot is `bottom` (x, z). An approach node
    `lead` metres out along the staircase's axis (away from the top) carries the ground link, because the foot itself usually sits inside the
    padding of the blocks that flank the stairs, where a ground node cannot see it."""
    b = add_node(f"{name}_bottom", bottom[0], 0, bottom[1])
    t = add_node(f"{name}_top", top[0], top[1], top[2])
    dx, dz = bottom[0] - top[0], bottom[1] - top[2]
    d = math.hypot(dx, dz) or 1.0
    ax, az = bottom[0] + dx / d * lead, bottom[1] + dz / d * lead
    a = add_node(f"{name}_approach", round(ax, 1), 0, round(az, 1))
    g = nearest(ax, az, maxd=16.0)
    if g: link(g, a)
    link(a, b)
    link(b, t)
    return t

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

def near_free(x, z, pad=1.2, rings=12):
    """The free point nearest (x, z): the wanted spot if it is clear, else the closest clear one on a growing ring."""
    for r in [0.0] + [1.0 * i for i in range(1, rings)]:
        for a in range(0, 360, 30) if r else [0]:
            px, pz = x + r * math.cos(math.radians(a)), z + r * math.sin(math.radians(a))
            if free(px, pz, pad):
                return round(px, 1), round(pz, 1)
    raise AssertionError((x, z))

def spot_near(w, x, z, y=0.3, respawn=30, twin=True):
    """Like `spot`, but each copy is moved to the nearest free ground, so a pickup never lands inside a wall or crate."""
    spot(w, *near_free(x, z), y=y, respawn=respawn, twin=False)
    if twin:
        spot(w, *near_free(-x, -z), y=y, respawn=respawn, twin=False)

def spot(w, x, z, y=0.3, respawn=30, twin=True):
    """A pickup (a weapon name, or "ammo"); `twin` adds the point-symmetric copy so neither side has the better lane."""
    def one(px, pz):
        pick.append({"weapon": w, "at": [round(px, 1), y, round(pz, 1)], "respawn_secs": respawn} if w != "ammo"
                     else {"ammo": True, "at": [round(px, 1), y, round(pz, 1)], "respawn_secs": respawn})
    one(x, z)
    if twin:
        one(-x, -z)

def team_spawns(x, z0, dz, yaw=90, cols=2, rows=3, jitter=2, sym="point"):
    """Six spawns a side: team1 around (x, z0), team2 mirrored through the origin (`point`) or across the x axis (`mirror`)."""
    for i in range(cols * rows):
        px, pz = x + (i % cols) * 4, z0 + (i // cols) * dz + (i % cols) * jitter
        spawns.append({"id": f"ridge_{i}", "position": [px, 0, pz], "yaw_deg": yaw, "group": "team1"})
        if sym == "point":
            spawns.append({"id": f"night_{i}", "position": [-px, 0, -pz], "yaw_deg": (yaw + 180) % 360, "group": "team2"})
        else:
            spawns.append({"id": f"night_{i}", "position": [-px, 0, pz], "yaw_deg": (360 - yaw) % 360, "group": "team2"})

def fix_weapon_names():
    for p in pick:
        if p.get("weapon") == "machinepistol":
            p["weapon"] = "machine-pistol"
        if p.get("weapon") == "handcannon":
            p["weapon"] = "hand-cannon"

# Movement tuned for flow: a quicker start and stop, more say in the air, a touch more top speed. Jump height is unchanged, so nothing that was
# a wall is now a step (the nav graphs were verified against the real movement).
PLAYER = {"fov": 90, "walk_speed": 4.7, "sprint_speed": 7.2, "crouch_multiplier": 0.45, "jump_speed": 5.0, "gravity": 15.0,
          "acceleration": 46, "air_acceleration": 14, "friction": 9, "max_speed": 7.4}

def emit(path, camera, background, ambient, name, extra_shooter=None, match=None, combat=None, sky=None, short=None):
    """Writes the scene. `extra_shooter` adds the mode blocks (`flags`, `sites`, `objective`) next to `start`/`pickups`."""
    fix_weapon_names()
    shooter = {"start": ["pistol", "knife"], "friendly_fire": False, "pickups": pick}
    shooter.update(extra_shooter or {})
    scene = {
        "meta": {"fps": 30, "duration": 10, "resolution": [1280, 720], "x-name": name, "x-short": short or name[:6].upper()},
        "camera": camera, "background": background, "ambient": ambient, "lights": lights[:200],
        "player": PLAYER, "music": False,
        "combat": combat or {"respawn_secs": 8, "spawn": "farthest", "spawn_protect_secs": 2.0},
        "match": match or {"min_players": 1, "countdown_secs": 5, "round_secs": 600, "results_secs": 3600, "score_to_win": 50, "join_in_progress": True, "ready_check": True},
        "shooter": shooter, "spawns": spawns, "nav": {"nodes": nodes, "edges": edges}, "objects": objs,
    }
    if sky: scene["sky"] = sky
    json.dump(scene, open(path, "w"), indent=1)
    print(path, ":", len(nodes), "nav nodes,", len(edges), "edges;", len(objs), "objects,", len(pick), "pickups,", len(lights), "lights")
