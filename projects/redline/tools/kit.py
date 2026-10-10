"""Building blocks for Redline's generator: the scene under construction, the visual kit and the chamber course builder.

Everything here is plain data for the Red Engine scene language (SPEC.md): boxes, planes, zones, spawns, jump pads, vars and rules.
`gen_map.py` assembles the hub, the chambers (chambers.py) and the run rules on top of it.
"""
import math

# ---- movement: one profile for the whole game (walk == sprint, so the player is always at full speed; Shift is not needed) ----
SPEED = 9.5            # m/s on the ground
JUMP = 7.4             # m/s up
GRAVITY = 21.0         # m/s^2  -> apex 1.30 m, 0.70 s in the air on the flat, a 6.7 m flat jump at full speed
AIR_ACCEL = 1.4        # Quake-style air acceleration: steer in the air, strafe-jump to go faster than SPEED
GROUND_ACCEL = 12.0
FRICTION = 7.0
MAX_SPEED = 22.0
FOV = 104

LAVA_Y = 0.0
SPACING = 520.0        # metres between chambers (far beyond the 200 m far plane: you never see another chamber)

# ---- palettes per tier: (pillar, top, trim emissive, accent) ----
PALETTES = {
    0: dict(pillar="#3a3836", top="#6b6f7a", trim="#ffb347", accent="#ff7a2f", sign="#ffd29a", band="#7a4a10", band2="#2a1a08"),     # the hub
    1: dict(pillar="#3c4652", top="#7d8794", trim="#38d6ff", accent="#38d6ff", sign="#b8f2ff", band="#0e5a72", band2="#0a2a36"),  # Intake: cool steel, cyan
    2: dict(pillar="#4a3a30", top="#6e5f55", trim="#ffaa2b", accent="#ffaa2b", sign="#ffe0a8", band="#7a4a08", band2="#2e1c06"),  # Furnace: iron, amber
    3: dict(pillar="#33303a", top="#4d4852", trim="#ff3355", accent="#ff3355", sign="#ffb0bd", band="#7a0e22", band2="#2c0810"),  # Core: dark, red
    4: dict(pillar="#3a2a2e", top="#5a3e44", trim="#ff2a2a", accent="#ffffff", sign="#ffffff", band="#8a0a0a", band2="#300404"),  # the Redline
}
CRUMBLE = dict(top="#c9772e", pillar="#5a3010", trim="#ffcf6b", band="#8a4a10", band2="#3a1a04")
BLINK = {"a": dict(top="#ff3fa4", emissive="#7a0f4a", ghost="#ff3fa4"), "b": dict(top="#3fe1ff", emissive="#0c5a6e", ghost="#3fe1ff")}
SPARK = dict(color="#7ff5ff", emissive="#2fd0ff")
RELIC = dict(color="#ffd23f", emissive="#c88a00")
PAD = dict(color="#ffe14a", emissive="#ff9d00")


def r(v, n=3):
    return round(float(v), n)


class Scene:
    """The scene being written: objects, lights, zones, spawns, pads, vars, rules, checks."""

    def __init__(self):
        self.objects, self.lights, self.zones, self.spawns, self.pads = [], [], [], [], []
        self.vars, self.persist, self.rules, self.sims = {}, [], [], []
        self.ids = set()
        self.lint_ignore_zones = []

    def uid(self, i):
        assert i not in self.ids, f"duplicate id {i}"
        self.ids.add(i)
        return i

    def add(self, o):
        self.uid(o["id"])
        self.objects.append(o)
        return o

    def var(self, name, value=0, persist=False):
        if name in self.vars:
            return name
        self.vars[name] = value
        if persist:
            self.persist.append(name)
        return name

    def rule(self, id, when, do, if_=None, cooldown=None, once=False):
        ru = {"id": self.uid("rule:" + id) and id, "when": when}
        if if_:
            ru["if"] = if_
        if cooldown:
            ru["cooldown"] = cooldown
        if once:
            ru["once"] = True
        ru["do"] = do
        self.rules.append(ru)
        return ru

    def zone(self, id, x0, z0, x1, z1, y, kind=None):
        z = {"id": self.uid("zone:" + id) and id, "rect": [r(min(x0, x1)), r(min(z0, z1)), r(max(x0, x1)), r(max(z0, z1))], "y": r(y)}
        if kind:
            z["kind"] = kind
        self.zones.append(z)
        return id

    def spawn(self, id, x, y, z, yaw=0):
        self.spawns.append({"id": self.uid("spawn:" + id) and id, "position": [r(x), r(y), r(z)], "yaw_deg": yaw})
        return id

    def light(self, id, x, y, z, color, intensity, rng):
        self.lights.append({"id": self.uid("light:" + id) and id, "type": "point", "position": [r(x), r(y), r(z)], "color": color, "intensity": intensity, "range": rng})

    # ---- visual kit ----
    def box(self, id, size, pos, color, emissive=None, collide=True, opacity=None, roughness=None, metallic=None, rot=None):
        m = {"color": color}
        if emissive:
            m["emissive"] = emissive
        if opacity is not None:
            m["opacity"] = opacity
        if roughness is not None:
            m["roughness"] = roughness
        if metallic is not None:
            m["metallic"] = metallic
        o = {"id": id, "type": "box", "size": [r(s) for s in size], "position": [r(p) for p in pos], "material": m}
        if rot:
            o["rotation"] = rot
        if not collide:
            o["collide"] = False
        return self.add(o)

    def plane(self, id, size, pos, color, emissive=None, opacity=None):
        m = {"color": color}
        if emissive:
            m["emissive"] = emissive
        if opacity is not None:
            m["opacity"] = opacity
        return self.add({"id": id, "type": "plane", "size": [r(s) for s in size], "position": [r(p) for p in pos], "material": m, "collide": False})

    def text(self, id, text, pos, height, color, emissive, yaw=0, backing=None):
        o = {"id": id, "type": "text", "text": text, "position": [r(p) for p in pos], "height": height,
             "material": {"color": color, "emissive": emissive}}
        if yaw:
            o["rotation"] = [0, yaw, 0]
        if backing:
            o["backing"] = backing
        return self.add(o)

    def gem(self, id, x, y, z, color, emissive, size=1.0, spin=True):
        """A spinning, bobbing double cone (a cut gem): sparks and relics. One top-level group, so `hide` takes all of it."""
        kids = [
            {"id": f"{id}.up", "type": "cone", "radius": r(0.24 * size), "height": r(0.34 * size), "position": [0, r(0.17 * size), 0], "material": {"color": color, "emissive": emissive, "metallic": 0.3, "roughness": 0.25}},
            {"id": f"{id}.dn", "type": "cone", "radius": r(0.24 * size), "height": r(0.34 * size), "position": [0, r(-0.17 * size), 0], "rotation": [180, 0, 0], "material": {"color": color, "emissive": emissive, "metallic": 0.3, "roughness": 0.25}},
        ]
        o = {"id": id, "type": "group", "collide": False, "children": kids}
        if spin:
            o["position"] = {"keyframes": [{"t": 0, "value": [r(x), r(y), r(z)]}, {"t": 2, "value": [r(x), r(y + 0.18), r(z)], "ease": "inout"}, {"t": 4, "value": [r(x), r(y), r(z)], "ease": "inout"}]}
            o["rotation"] = {"keyframes": [{"t": 0, "value": [0, 0, 0]}, {"t": 4, "value": [0, 360, 0]}]}
        else:
            o["position"] = [r(x), r(y), r(z)]
        return self.add(o)


class Plat:
    def __init__(self, id, x, top, z_near, z_far, w):
        self.id, self.x, self.top, self.z_near, self.z_far, self.w = id, x, top, z_near, z_far, w

    @property
    def zc(self):
        return (self.z_near + self.z_far) / 2

    @property
    def d(self):
        return self.z_near - self.z_far


class Chamber:
    """One chamber: a course along -Z from its origin. A cursor (`x`, `top`, `z`) is the middle of the far edge of the last platform.

    Every builder call places geometry AND appends the step a scripted runner takes (`route`), so `checks.sim` proves the chamber
    can be cleared at base speed with no strafe-jumping, and the measured time becomes its par.
    """

    def __init__(self, scene, code, name, tier, index, start_top=4.0, blurb=""):
        self.s, self.code, self.name, self.tier, self.index, self.blurb = scene, code, name, tier, index, blurb
        self.pal = PALETTES[tier]
        col, row = index % 5, index // 5
        self.ox, self.oz = (col + 1) * SPACING, (row - 2) * SPACING
        self.x, self.top, self.z = 0.0, start_top, 0.0
        self.plats, self.route, self.sparks, self.cps = [], [], [], []
        self.crumbles, self.blinks, self.curtains, self.lids = [], [], [], []
        self.relic = None
        self.n = 0
        self.exit_zone = None
        self.min_x = self.max_x = 0.0
        self.min_z, self.max_z = -1.0, 8.0

    # world coordinates
    def wx(self, x):
        return self.ox + x

    def wz(self, z):
        return self.oz + z

    def nid(self, kind):
        self.n += 1
        return f"{self.code}_{kind}{self.n}"

    def _extent(self, x0, x1, z0, z1):
        self.min_x, self.max_x = min(self.min_x, x0), max(self.max_x, x1)
        self.min_z, self.max_z = min(self.min_z, z0), max(self.max_z, z1)

    # ---- geometry ----
    def slab(self, x, top, z_near, z_far, w, kind="steel", pillar=True, id=None, trims=True):
        """A platform: a pillar from the lava up to `top` (or a 0.6 m floating slab), with glowing edge trims."""
        pid = id or self.nid("p")
        d = z_near - z_far
        thick = top - LAVA_Y if pillar else 0.6
        pal = self.pal if kind == "steel" else CRUMBLE
        s = self.s
        s.box(pid, [w, thick, d], [self.wx(x), top - thick / 2, self.wz((z_near + z_far) / 2)], pal["pillar"] if pillar else pal["top"], roughness=0.85, metallic=0.2)
        if pillar:
            s.box(f"{pid}.top", [w + 0.02, 0.08, d + 0.02], [self.wx(x), top - 0.035, self.wz((z_near + z_far) / 2)], pal["top"], collide=False, roughness=0.7, metallic=0.35)
        if trims:
            tr = pal["trim"]
            s.box(f"{pid}.tn", [w, 0.07, 0.1], [self.wx(x), top + 0.01, self.wz(z_near - 0.05)], tr, emissive=tr, collide=False)
            s.box(f"{pid}.tf", [w, 0.07, 0.1], [self.wx(x), top + 0.01, self.wz(z_far + 0.05)], tr, emissive=tr, collide=False)
            if pillar and thick > 1.0:
                # the near face: a lit band under the lip and a dim one lower down, so a pillar reads as a height, not a black slab
                s.box(f"{pid}.band", [w + 0.02, 0.22, 0.04], [self.wx(x), top - 0.2, self.wz(z_near + 0.02)], tr, emissive=pal["band"], collide=False)
                if thick > 4.0:
                    s.box(f"{pid}.band2", [w + 0.02, 0.12, 0.04], [self.wx(x), top - thick * 0.55, self.wz(z_near + 0.02)], pal["pillar"], emissive=pal["band2"], collide=False)
        p = Plat(pid, x, top, z_near, z_far, w)
        self._extent(x - w / 2, x + w / 2, z_far, z_near)
        return p

    def start(self, w=7, d=8):
        """The chamber's first platform: spawn at its back, the chamber's name in front of the player."""
        p = self.slab(0, self.top, self.z + d, self.z, w, id=f"{self.code}_start")
        self.plats.append(p)
        self.s.spawn(f"{self.code}_cp0", self.wx(0), self.top, self.wz(d - 1.2), 0)
        self.cps.append((f"{self.code}_cp0", None))
        pal = self.pal
        # the chamber's name hangs high over the first gap, where it reads from the spawn and its shadow falls in the lava
        self.s.text(f"{self.code}_title", self.name, [self.wx(0), self.top + 6.4, self.wz(-11)], 0.8, pal["sign"], pal["accent"])
        if self.blurb:
            self.s.text(f"{self.code}_blurb", self.blurb, [self.wx(0), self.top + 5.3, self.wz(-11)], 0.3, "#ffffff", "#7a7a7a")
        self.s.light(f"{self.code}_l0", self.wx(0), self.top + 5, self.wz(d / 2), "#fff2e0", 16, 26)
        # the start line: crossing it starts the chamber's par clock (and tells the rules which chamber you are in)
        lz = d - 3.0
        self.s.box(f"{self.code}_line", [w, 0.06, 0.35], [self.wx(0), self.top + 0.01, self.wz(lz)], "#ffffff", emissive="#9a9a9a", collide=False)
        self.entry_zone = self.s.zone(f"{self.code}_entry", self.wx(-w / 2), self.wz(lz - 0.3), self.wx(w / 2), self.wz(lz + 0.3), self.top)
        self.cur = p
        self.route.append(("walk", 0, 0.6))
        return p

    def run(self, d, w=None, dx=0.0):
        """Extend the current platform forward by `d` metres (a walkway; same height, adjoining)."""
        w = w or self.cur.w
        p = self.slab(self.cur.x + dx, self.top, self.z, self.z - d, w)
        self.plats.append(p)
        self.z -= d
        self.x = p.x
        self.cur = p
        self.route.append(("walk", p.x, self.z + 0.6, "soft"))
        return p

    def jump(self, gap, d, w=4.0, dx=0.0, dy=0.0, kind="steel", pillar=True, land=None):
        """A jump: a gap of `gap` metres, then a platform `d` deep, offset `dx` sideways and `dy` up. The runner jumps from the edge."""
        frm = self.cur
        # take off from the side of the platform nearer the target, so a zig-zag is run corner to corner (as a person runs it)
        shift = 0.0
        take = (frm.x + shift, self.z + 0.5)
        x = frm.x + dx
        top = self.top + dy
        if dy >= -1.0:
            disc = JUMP * JUMP - 2 * GRAVITY * dy
            t_air = (JUMP + math.sqrt(max(disc, 0))) / GRAVITY
            along = SPEED * t_air          # how far a full-speed jump carries (a diagonal one goes mostly forward too)
            d = max(d, along - gap - 0.5 + 1.4)
        p = self.slab(x, top, self.z - gap, self.z - gap - d, w, kind=kind, pillar=pillar)
        self.plats.append(p)
        land = land if land is not None else min(1.6, d / 2)
        self.route.append(("jump", take, (x, self.z - gap - land), top))
        self.z = self.z - gap - d
        self.top = top
        self.x = x
        self.cur = p
        self.route.append(("walk", x, self.z + 0.6, "soft"))
        return p

    def pad(self, rise, launch, gap, d, w=5.0, dx=0.0):
        """A jump pad at the end of the current platform that launches the player up `rise` metres onto a platform `gap` ahead.

        A pad needs a run-up: a landing (from a jump or another pad) comes down near the far end of its platform, and a pad there
        would catch it and throw the player again before they choose to go. So a short platform gets a 4 m walkway first."""
        if self.cur.d < 9:
            self.run(4.0)
        frm = self.cur
        px, pz = frm.x, self.z + 1.2
        pid = self.nid("pad")
        s = self.s
        s.pads.append({"id": pid, "position": [r(self.wx(px)), r(self.top), r(self.wz(pz))], "size": [1.8, 1.8], "launch_speed": launch})
        s.add({"id": f"{pid}.disc", "type": "cylinder", "radius": 0.95, "height": 0.06, "position": [r(self.wx(px)), r(self.top + 0.03), r(self.wz(pz))], "material": {"color": PAD["color"], "emissive": PAD["emissive"]}, "collide": False})
        s.add({"id": f"{pid}.ring", "type": "cylinder", "radius": 0.55, "height": 0.08, "position": [r(self.wx(px)), r(self.top + 0.04), r(self.wz(pz))], "material": {"color": "#fff6c8", "emissive": "#ffd000"}, "collide": False})
        s.light(f"{pid}.l", self.wx(px), self.top + 1.2, self.wz(pz), "#ffcc33", 8, 7)
        self.launches = getattr(self, "launches", []) + [launch]
        top = self.top + rise
        t_fall = (launch + math.sqrt(max(launch * launch - 2 * GRAVITY * rise, 0))) / GRAVITY
        reach = SPEED * t_fall - 0.9          # metres past the pad's middle where a full-speed flight comes down
        d = max(d, reach - gap + 4.6)         # land, then room to run on (a pad at the far end must not catch the landing)
        p = self.slab(px + dx, top, pz - gap, pz - gap - d, w)
        self.plats.append(p)
        self.route.append(("pad", (px, pz), (px + dx, pz - gap - min(1.8, d / 2)), top, launch))
        self.z = pz - gap - d
        self.top = top
        self.x = px + dx
        self.cur = p
        self.route.append(("walk", self.x, self.z + 0.6))
        return p

    def skip_pad(self, frm, to, side=1):
        """A locked shortcut: a pad at the side of platform `frm` that throws you straight ahead onto platform `to`, skipping what lies
        between. A lid covers it until OVERDRIVE KEYS are bought. The main route runs past it."""
        px = frm.x + side * (frm.w / 2 - 1.2)
        pz = frm.z_far + 1.4
        assert abs(px - to.x) <= to.w / 2 - 0.3, f"{self.code}: the skip pad at x={px:.1f} does not line up with its landing (x {to.x:.1f}, w {to.w})"
        rise = to.top - frm.top
        D = pz - to.zc + 0.9
        t = D / SPEED
        launch = (rise + 0.5 * GRAVITY * t * t) / t
        assert launch <= 28, f"{self.code}: the skip pad would need a {launch:.1f} m/s launch (at most 28): aim it at a nearer platform"
        pid = self.nid("skip")
        s = self.s
        s.pads.append({"id": pid, "position": [r(self.wx(px)), r(frm.top), r(self.wz(pz))], "size": [1.8, 1.8], "launch_speed": r(launch, 2)})
        s.add({"id": f"{pid}.disc", "type": "cylinder", "radius": 0.95, "height": 0.06, "position": [r(self.wx(px)), r(frm.top + 0.03), r(self.wz(pz))], "material": {"color": "#8affd8", "emissive": "#13a37a"}, "collide": False})
        s.add({"id": f"{pid}.ring", "type": "cylinder", "radius": 0.55, "height": 0.08, "position": [r(self.wx(px)), r(frm.top + 0.04), r(self.wz(pz))], "material": {"color": "#e8fff6", "emissive": "#2affb0"}, "collide": False})
        lid_id = f"{pid}_lid"
        s.box(lid_id, [2.2, 0.5, 2.2], [self.wx(px), frm.top + 0.25, self.wz(pz)], "#3a3a40", roughness=0.4, metallic=0.8)
        s.text(f"{lid_id}.sign", "LOCKED", [self.wx(px), frm.top + 0.9, self.wz(pz) + 1.15], 0.16, "#ff8a8a", "#7a1010")
        self.lids.append(lid_id)
        return pid

    def crumble(self, n, size=2.4, gap=0.0, dxs=None, first_gap=None, dy=0.0):
        """`n` tiles that fall 0.45 s after they are first touched (they come back when the chamber is entered again)."""
        dxs = dxs or [0.0] * n
        first_gap = gap if first_gap is None else first_gap
        for i in range(n):
            g = first_gap if i == 0 else gap
            x = self.cur.x + dxs[i] if i == 0 else self.x + dxs[i]
            tid = self.nid("cr")
            top = self.top + (dy if i == 0 else 0)
            depth = size
            if g > 0.05:
                depth = max(size, SPEED * 0.705 - g - 0.5 + 1.4)
            p = self.slab(x, top, self.z - g, self.z - g - depth, size, kind="crumble", pillar=False, id=tid)
            self.crumbles.append(tid)
            self.plats.append(p)
            if g > 0.05 or (i == 0 and abs(dy) > 0.01):
                self.route.append(("jump", (self.x, self.z + 0.4), (x, self.z - g - min(1.6, depth / 2)), top))
            else:
                # a run of tiles: the runner keeps to one straight line that every tile covers (tiles only weave by less than half their width)
                line_x = self.route[-1][1] if self.route and self.route[-1][0] == "walk" else x
                self.route.append(("walk", line_x if abs(line_x - x) < size / 2 - 0.3 else x, self.z - g - depth / 2))
            self.z = self.z - g - depth
            self.top = top
            self.x = x
            self.cur = p
        return self.cur

    def blink(self, steps, gap=2.4, size=6.0, dy=0.0):
        """Platforms in two sets that take turns to exist (magenta / cyan, 1.4 s each). `steps` lists the set of each platform in order."""
        for i, phase in enumerate(steps):
            bid = self.nid("bl")
            top = self.top + (dy if i == 0 else 0)
            col = BLINK[phase]
            s = self.s
            zc = self.z - gap - size / 2
            s.box(bid, [size, 0.5, size], [self.wx(self.x), top - 0.25, self.wz(zc)], col["top"], emissive=col["emissive"], roughness=0.3)
            s.box(f"{bid}.ghost", [size + 0.06, 0.08, size + 0.06], [self.wx(self.x), top - 0.46, self.wz(zc)], col["ghost"], emissive=col["emissive"], collide=False, opacity=0.35)
            self.blinks.append((bid, phase))
            self.route.append(("blinkjump", phase, (self.x, self.z + 0.4), (self.x, zc), top))
            self.plats.append(Plat(bid, self.x, top, zc + size / 2, zc - size / 2, size))
            self._extent(self.x - size / 2, self.x + size / 2, zc - size / 2, zc + size / 2)
            self.z = zc - size / 2
            self.top = top
            self.cur = Plat(bid, self.x, top, zc + size / 2, zc - size / 2, size)
        return self.cur

    def curtain(self, period_on=1.1, period_off=1.1, offset=0.0, w=None):
        """A heat curtain across the walkway at the cursor (it must be on a walkway): it burns you while it glows.

        You wait for it on the ground before it, so the walkway is long enough to land on, stop and wait (a landing from a jump
        comes down well into its platform)."""
        if self.cur.d < 10:
            self.run(5.0)
        w = w or self.cur.w
        cid = self.nid("hc")
        s = self.s
        zc = self.z + 1.5
        s.box(cid, [w, 2.6, 0.12], [self.wx(self.x), self.top + 1.3, self.wz(zc)], "#ff2a2a", emissive="#ff1010", collide=False, opacity=0.55)
        for side in (-1, 1):
            s.box(f"{cid}.post{side + 1}", [0.3, 3.0, 0.3], [self.wx(self.x + side * (w / 2 + 0.15)), self.top + 1.5, self.wz(zc)], "#2a2a2a", emissive="#401010", metallic=0.7, roughness=0.4)
        s.box(f"{cid}.beam", [w + 0.6, 0.3, 0.3], [self.wx(self.x), self.top + 3.0, self.wz(zc)], "#2a2a2a", emissive="#401010", metallic=0.7, roughness=0.4)
        box = [self.wx(self.x - w / 2), self.top - 0.2, self.wz(zc - 0.25), self.wx(self.x + w / 2), self.top + 2.6, self.wz(zc + 0.25)]
        self.curtains.append((cid, box, period_on, period_off, offset))
        crossing = self.route.pop() if self.route and self.route[-1][0] == "walk" else None
        self.route.append(("curtain", cid, (self.x, zc + 3.5)))
        if crossing:
            self.route.append(crossing)
        return cid

    def checkpoint(self):
        """A checkpoint on the current platform: falling after this point puts you back here."""
        j = len(self.cps)
        cid = f"{self.code}_cp{j}"
        x, z = self.cur.x, self.z + min(2.0, self.cur.d / 2)
        s = self.s
        s.spawn(cid, self.wx(x), self.top, self.wz(z), 0)
        s.add({"id": f"{cid}.ring", "type": "cylinder", "radius": 1.1, "height": 0.04, "position": [r(self.wx(x)), r(self.top + 0.02), r(self.wz(z))], "material": {"color": "#1b5b66", "emissive": "#0b3a44"}, "collide": False})
        s.add({"id": f"{cid}.lit", "type": "cylinder", "radius": 1.1, "height": 0.05, "position": [r(self.wx(x)), r(self.top + 0.03), r(self.wz(z))], "material": {"color": "#7ff5ff", "emissive": "#2fd0ff"}, "collide": False})
        zone = s.zone(f"{cid}_z", self.wx(x - 1.3), self.wz(z - 1.3), self.wx(x + 1.3), self.wz(z + 1.3), self.top)
        self.cps.append((cid, zone))
        return cid

    def spark(self, dx, dz, dy=1.2, at=None):
        """A spark `dx`/`dz` from the cursor (or at absolute local `at`), `dy` above the current top."""
        sid = f"{self.code}_sp{len(self.sparks) + 1}"
        if at:
            x, y, z = at
        else:
            x, y, z = self.x + dx, self.top + dy, self.z + dz
        self.s.gem(sid, self.wx(x), y, self.wz(z), SPARK["color"], SPARK["emissive"])
        self.sparks.append(sid)
        return sid

    def relic_at(self, x, y, z):
        rid = f"{self.code}_relic"
        self.s.gem(rid, self.wx(x), y, self.wz(z), RELIC["color"], RELIC["emissive"], size=1.7)
        self.s.light(f"{rid}.l", self.wx(x), y + 0.8, self.wz(z), "#ffcc44", 6, 6)
        self.relic = rid
        return rid

    def decor(self, seed):
        """Atmosphere that costs no gameplay: orange light thrown up from the lava along the course, distant reactor towers with
        glowing slits on both sides, and embers drifting over the lava. Deterministic per chamber (`seed`)."""
        import random
        rnd = random.Random(seed)
        s = self.s
        # lava glow: a warm light low beside the course every ~16 m (the renderer keeps the 16 nearest)
        z = 6.0
        i = 0
        while z > self.min_z - 6:
            side = 1 if i % 2 == 0 else -1
            s.light(f"{self.code}_lava{i}", self.wx(side * (self.max_x - self.min_x) / 2 + side * 4.0), 1.4, self.wz(z), "#ff5a14", 26, 16)
            z -= 16.0
            i += 1
        # towers: far enough out never to be in the way, tall enough to give the place a scale
        length = self.max_z - self.min_z
        for j in range(10):
            side = -1 if j % 2 == 0 else 1
            tx = side * rnd.uniform(34, 70)
            tz = self.max_z - rnd.uniform(0, length + 30)
            th = rnd.uniform(18, 64)
            tw = rnd.uniform(5, 12)
            s.box(f"{self.code}_tower{j}", [tw, th, tw], [self.wx(tx), th / 2, self.wz(tz)], "#1c1416", roughness=0.9, collide=False)
            s.box(f"{self.code}_tower{j}.slit", [0.5, th * 0.7, tw + 0.06], [self.wx(tx), th * 0.45, self.wz(tz)], self.pal["accent"], emissive=self.pal["band"], collide=False)
        # embers
        for j in range(12):
            ex = rnd.uniform(self.min_x - 10, self.max_x + 10)
            ez = rnd.uniform(self.min_z, self.max_z)
            ey = rnd.uniform(1.0, 9.0)
            r0 = rnd.uniform(0.05, 0.11)
            dy = rnd.uniform(0.6, 1.6)
            s.add({"id": f"{self.code}_ember{j}", "type": "sphere", "radius": round(r0, 3), "collide": False,
                   "position": {"keyframes": [{"t": 0, "value": [r(self.wx(ex)), r(ey), r(self.wz(ez))]},
                                              {"t": 2, "value": [r(self.wx(ex + 0.4)), r(ey + dy), r(self.wz(ez))], "ease": "inout"},
                                              {"t": 4, "value": [r(self.wx(ex)), r(ey), r(self.wz(ez))], "ease": "inout"}]},
                   "material": {"color": "#ffb36b", "emissive": "#ff6a00"}})

    def finish(self, d=7, w=7):
        """The vent: the chamber's exit gate on a last platform."""
        p = self.run(d, w=w)
        s = self.s
        gx, gz = self.x, self.z + 2.2
        green, glow = "#5dff8a", "#1fbf4a"
        for side in (-1, 1):
            s.box(f"{self.code}_gate{side + 1}", [0.5, 4.2, 0.5], [self.wx(gx + side * 2.2), self.top + 2.1, self.wz(gz)], "#1d2a22", emissive="#0a3a18", metallic=0.6, roughness=0.4)
        s.box(f"{self.code}_gatetop", [4.9, 0.5, 0.5], [self.wx(gx), self.top + 4.2, self.wz(gz)], "#1d2a22", emissive="#0a3a18", metallic=0.6, roughness=0.4)
        s.box(f"{self.code}_gatefield", [3.9, 3.9, 0.08], [self.wx(gx), self.top + 1.95, self.wz(gz)], green, emissive=glow, collide=False, opacity=0.45)
        s.text(f"{self.code}_gatesign", "VENT", [self.wx(gx), self.top + 5.0, self.wz(gz)], 0.5, green, glow)
        s.light(f"{self.code}_gl", self.wx(gx), self.top + 3.0, self.wz(gz + 2.0), "#7dff9a", 14, 14)
        self.exit_zone = s.zone(f"{self.code}_exit", self.wx(gx - 2.0), self.wz(gz - 0.6), self.wx(gx + 2.0), self.wz(gz + 0.6), self.top)
        self.route.append(("walk", gx, gz - 1.0))
        return p
