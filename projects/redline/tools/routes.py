"""The scripted runner: turns a chamber's `route` into a `checks.sim` scenario, checks every jump is possible at base speed, and measures pars.

The runner never strafe-jumps or bunny hops: it walks, jumps from 0.5 m before an edge holding forward, brakes in the air (holds back)
when a drop would carry it past the landing, and waits for phase platforms and heat curtains. So a passing scenario means a new player
holding W can clear the chamber, and the time it takes is an honest par for a clean, unoptimised run.
"""
import json, math, os, subprocess, sys
from kit import SPEED, JUMP, GRAVITY, AIR_ACCEL

TICK = 1 / 60
BRAKE = AIR_ACCEL * SPEED     # m/s^2 of air braking while holding back: each tick adds AIR_ACCEL * SPEED * dt against the motion (13.3)


def airtime(dy, vy=JUMP):
    """Seconds from leaving the ground at `vy` until the feet come down through `dy` metres (relative). None if never that high."""
    disc = vy * vy - 2 * GRAVITY * dy
    if disc < 0:
        return None
    return (vy + math.sqrt(disc)) / GRAVITY


def yaw_to(dx, dz):
    """The engine's yaw (degrees) that faces along (dx, dz): forward is (sin yaw, -cos yaw)."""
    return round(math.degrees(math.atan2(dx, -dz)), 2)


def plan_flight(dist_near, dist_far, t_air):
    """How to fly a jump: (forward seconds, brake seconds) so the landing falls between the platform's near and far edges.

    Holding forward the whole way covers SPEED * t_air. If that overshoots the far edge, hold forward for t1 and back for the rest.
    Returns None when even full speed falls short of the near edge (the design is impossible at base speed)."""
    full = SPEED * t_air
    if full < dist_near + 0.2:
        return None
    if full <= dist_far - 0.4:
        return (t_air, 0.0)
    target = (dist_near + dist_far) / 2
    for i in range(0, 400):
        t1 = t_air * i / 400
        t2 = t_air - t1
        tb = min(t2, SPEED / BRAKE)
        x = SPEED * t1 + SPEED * tb - 0.5 * BRAKE * tb * tb
        if x >= target:
            return (t1, t2)
    return (t_air, 0.0)


class Script:
    def __init__(self, c, pid="p1"):
        self.c, self.pid, self.steps, self.t = c, pid, [], 0.0
        self.pos = None
        self.top = None
        self.warnings = []

    def walk(self, x, z):
        self.steps.append({"player": self.pid, "walk": f"{round(self.c.wx(x), 2)},{round(self.c.wz(z), 2)}"})
        if self.pos:
            self.t += math.hypot(x - self.pos[0], z - self.pos[1]) / SPEED
        self.pos = (x, z)

    def hold(self, secs, yaw, forward=1, jump=False, aim=None):
        """Hold forward (or back) for `secs`: facing `yaw`, or, with `aim` (a local x, y, z), turning every tick to face that point."""
        h = {"forward": forward, "seconds": round(max(secs, 0.02), 3)}
        if aim is not None:
            h["look_at"] = [round(self.c.wx(aim[0]), 2), round(aim[1], 2), round(self.c.wz(aim[2]), 2)]
        else:
            h["yaw_deg"] = yaw
        if jump:
            h["jump"] = True
        self.steps.append({"player": self.pid, "hold": h})
        self.t += secs

    def jump(self, take, land, near_d, far_d, dy, runup=None, top=None, stop=False):
        """Jump from `take` toward `land`; the platform's near/far edges are `near_d`/`far_d` metres from `take` along the jump.

        In the air, facing a new way does not turn your momentum, so the runner only ever jumps the way it is already running:
        `take` is chosen on the line from where it landed to where it wants to land (see `scenario`), the walk to it points the
        momentum along that line, and the jump keeps the same heading."""
        dx, dz = land[0] - take[0], land[1] - take[1]
        yaw = yaw_to(dx, dz)
        L0 = math.hypot(dx, dz) or 1.0
        ux, uz = dx / L0, dz / L0
        lead = 0.0
        if self.pos is not None:
            # a sideways jump: line up first. Walk to a point `lead` metres back on the jump line, then run along the line
            # (holding its heading) to the take-off, so the momentum points across the gap
            avail = (take[0] - self.pos[0]) * ux + (take[1] - self.pos[1]) * uz - 0.3
            lead = min(3.0, avail)
            if lead < 1.2:
                if abs(dx) > 0.3:
                    self.warnings.append(f"{self.c.code}: only {avail:.1f} m to line up a sideways jump to x={land[0]:.1f}: make the platform deeper")
                lead = 0.0
        if lead > 0:
            self.walk(take[0] - ux * lead, take[1] - uz * lead)
            self.hold(lead / SPEED - 0.03, yaw)
        else:
            self.walk(*take)
        t_air = airtime(dy)
        if t_air is None:
            raise SystemExit(f"{self.c.code}: a jump up {dy:.2f} m is higher than the jump reaches")
        plan = plan_flight(near_d, far_d, t_air) if not stop else plan_flight(near_d, near_d + (far_d - near_d) * 0.55, t_air)
        if plan is None:
            raise SystemExit(f"{self.c.code}: a jump of {near_d:.2f} m (dy {dy:+.2f}) is too long at base speed ({SPEED * t_air:.2f} m in the air)")
        t1, t2 = plan
        self.hold(0.06, yaw, jump=True)
        self.hold(max(t1 - 0.06, 0.02), yaw)
        if t2 > 0.02:
            self.hold(max(t2 - 0.08, 0.02), yaw, forward=-1)   # stop braking just before touchdown, or the brake runs it backwards
            self.hold(0.1, yaw, forward=0)
        if stop:
            self.hold(0.35, yaw, forward=0)      # let friction stop it on landing
        # where it comes down: a full-speed flight lands near the far end unless it braked
        L = math.hypot(dx, dz) or 1.0
        reach = min(SPEED * t_air, far_d - 0.4) if t2 <= 0.02 else (near_d + far_d) / 2
        self.pos = (take[0] + dx / L * reach, take[1] + dz / L * reach)


def _plat_at(c, x, z, top=None):
    for p in c.plats:
        if abs(p.x - x) <= p.w / 2 + 0.05 and p.z_far - 0.05 <= z <= p.z_near + 0.05 and (top is None or abs(p.top - top) < 0.05):
            return p
    return None


def _line_take(c, pos, take, land, top):
    """The take-off on the line from `pos` (where the runner is) to `land`, at the same distance from the edge as `take`.

    Kept on the platform; when the line would leave the platform's sides it bends back to `take` (the runner then turns on the ground)."""
    if pos is None:
        return take
    p = _plat_at(c, take[0], take[1], top)
    dz_total = land[1] - pos[1]
    if abs(dz_total) < 0.5 or (take[1] - pos[1]) * dz_total <= 0.3:
        return take
    s = (take[1] - pos[1]) / dz_total
    x = pos[0] + (land[0] - pos[0]) * s
    if p is not None:
        lim = p.w / 2 - 0.45
        x = min(max(x, p.x - lim), p.x + lim)
    return (x, take[1])


def _edges(c, take, land, top_to):
    """Distance along the jump from `take` to the near and far edges of the platform under `land`."""
    for p in c.plats:
        if abs(p.x - land[0]) <= p.w / 2 + 0.01 and p.z_far - 0.01 <= land[1] <= p.z_near + 0.01 and abs(p.top - top_to) < 0.01:
            dx, dz = land[0] - take[0], land[1] - take[1]
            L = math.hypot(dx, dz)
            ux, uz = dx / L, dz / L
            # walk along the line until inside / outside the platform rectangle
            near = far = None
            for i in range(0, 4000):
                s = i * 0.01
                x, z = take[0] + ux * s, take[1] + uz * s
                inside = abs(x - p.x) <= p.w / 2 and p.z_far <= z <= p.z_near
                if inside and near is None:
                    near = s
                if near is not None and not inside:
                    far = s
                    break
            return near, far if far is not None else near + 1.0
    # blink platforms are not in plats as Plat objects with exact sizes; fall back to a 2.4 m square
    dx, dz = land[0] - take[0], land[1] - take[1]
    L = math.hypot(dx, dz)
    return max(L - 1.2, 0.5), L + 1.2


def _runup(c, take, land, top):
    """A point 2.6 m behind `take` on the line from `land` through `take`, pulled back onto the platform `take` is on."""
    dx, dz = land[0] - take[0], land[1] - take[1]
    L = math.hypot(dx, dz) or 1.0
    ux, uz = dx / L, dz / L
    for p in c.plats:
        if abs(p.x - take[0]) <= p.w / 2 + 0.01 and p.z_far - 0.01 <= take[1] <= p.z_near + 0.01 and (top is None or abs(p.top - top) < 0.05):
            x, z = take[0] - ux * 2.6, take[1] - uz * 2.6
            x = min(max(x, p.x - p.w / 2 + 0.4), p.x + p.w / 2 - 0.4)
            z = min(max(z, p.z_far + 0.4), p.z_near - 0.4)
            return (x, z)
    return None


def scenario(c):
    sc = Script(c)
    prev_phase = None
    blink_sizes = {}
    route = c.route
    def needs_stop(i, here_phase):
        """True when the next real step waits for a phase platform other than the one being landed on."""
        for st in route[i + 1:]:
            if st[0] == "walk" and len(st) > 3:
                continue
            return st[0] == "blinkjump" and st[1] != here_phase
        return False

    for i, step in enumerate(route):
        kind = step[0]
        nxt = route[i + 1][0] if i + 1 < len(route) else None
        if kind == "walk" and len(step) > 3 and nxt in ("jump", "blinkjump", "pad"):
            continue            # a walk to the platform's far edge: the jump that follows walks to its own take-off
        if kind == "walk":
            sc.walk(step[1], step[2])
            sc.top = sc.top
        elif kind == "jump":
            _, take, land, top = step
            cur_top = sc.top if sc.top is not None else c.plats[0].top
            near, far = _edges(c, take, land, top)
            sc.jump(take, land, near, far, top - cur_top, top=top, stop=needs_stop(i, None))
            sc.top = top
            prev_phase = None
        elif kind == "blinkjump":
            _, phase, take, land, top = step
            if phase != prev_phase:
                # stand 2.8 m short of the edge (stopped), wait for the platform to appear, then run and jump: a phase platform is
                # solid for 2.4 s of every 3.2 and the one you stand on stays for 0.8 s after the next appears
                wait_at = (take[0], take[1] + 2.8)
                if sc.pos is None or sc.pos[1] > wait_at[1] + 0.3:
                    sc.walk(*wait_at)
                    sc.hold(0.35, 0.0, forward=0)
                    sc.pos = wait_at
                # (the engine's `until_event` counts events from when the last *until_event* step ended, not from when this step
                # began, so an `_on` that already happened would end the wait at once: wait for the `_off` first)
                sc.steps.append({"player": sc.pid, "wait": 4.0, "until_event": f"{phase}_off"})
                sc.steps.append({"player": sc.pid, "wait": 4.0, "until_event": f"{phase}_on"})
                sc.t += 1.6
            dx, dz = land[0] - take[0], land[1] - take[1]
            L = math.hypot(dx, dz)
            dy = top - (sc.top if sc.top is not None else c.plats[0].top)
            near, far = _edges(c, take, land, top)
            sc.jump(take, land, near, far, dy, top=top, stop=needs_stop(i, phase))
            sc.top = top
            prev_phase = phase
        elif kind == "pad":
            _, padxz, land, top, launch = step
            x0, z0 = padxz[0], padxz[1] + 2.6
            sc.walk(x0, z0)
            dx, dz = land[0] - x0, land[1] - z0
            yaw = yaw_to(dx, dz)
            rise = top - sc.top
            t_fall = airtime(rise, vy=launch)
            # from the walk point to the pad's edge at full speed, then the flight
            t_to_pad = 1.7 / SPEED
            dist_near, dist_far = _edges(c, (x0, z0), land, top)
            reach = SPEED * (t_to_pad + t_fall)
            sc.hold(t_to_pad + t_fall + 0.05, yaw)          # the landing platform is sized for a full-speed flight (kit.pad)
            sc.top = top
            sc.pos = land
            prev_phase = None
        elif kind == "curtain":
            _, cid, before = step
            sc.walk(before[0], before[1] + 1.0)
            sc.steps.append({"player": sc.pid, "wait": 4.0, "until_event": f"{cid}_on"})
            sc.steps.append({"player": sc.pid, "wait": 4.0, "until_event": f"{cid}_off"})
            sc.t += 1.0
        elif kind == "waitev":
            sc.steps.append({"player": sc.pid, "wait": 4.0, "until_event": step[1]})
        if kind == "walk" and sc.top is None:
            sc.top = c.plats[0].top
    sc.steps.append({"player": sc.pid, "wait": 0.4})
    for w in sc.warnings:
        print("warning:", w)
    return {"name": f"chamber {c.code}: {c.name.lower()} can be cleared at base speed", "players": [{"id": "p1", "spawn": f"{c.code}_cp0"}],
            "script": sc.steps, "expect": [{"event": f"vent_{c.code}", "count": 1}, {"no_event": "burn"}], "max_seconds": 120}


def estimate(c):
    sc = scenario(c)
    t = 0.0
    last = None
    for st in sc["script"]:
        if "hold" in st:
            t += st["hold"]["seconds"]
        elif "wait" in st:
            t += 1.6 if "until_event" in st else st["wait"]
        elif "walk" in st:
            x, z = map(float, st["walk"].split(","))
            if last:
                t += math.hypot(x - last[0], z - last[1]) / SPEED
            last = (x, z)
    return t


def engine_cli():
    for cand in [os.environ.get("RED_CLI", ""), "scripts/red"]:
        if cand and os.path.exists(cand):
            return [cand]
    return ["scripts/red"]


def measure_pars(map_path, chambers, out_file, factor=0.92):
    """Run every chamber's scenario through the engine and write par = factor x the runner's time from the start line to the vent."""
    pars = {}
    for c in chambers:
        name = f"chamber {c.code}: {c.name.lower()} can be cleared at base speed"
        res = subprocess.run(engine_cli() + ["sim", map_path, "--only", name, "--json"], capture_output=True, text=True)
        try:
            env = json.loads(res.stdout)
        except Exception:
            print(f"{c.code}: could not read the sim result:\n{res.stdout[-800:]}\n{res.stderr[-800:]}")
            continue
        sc = (env.get("data") or {}).get("scenarios", [{}])[0]
        events = sc.get("events", [])
        ticks = {e.get("name"): e.get("tick") for e in events}
        vent = next((e["tick"] for e in events if e.get("name") == f"vent_{c.code}"), None)
        if vent is None:
            print(f"{c.code}: no vent (scenario {'passed' if sc.get('passed') else 'FAILED'})")
            continue
        start = 1.8 / 9.5 * 60       # the start line is ~1.8 m in front of the spawn
        secs = (vent - start) / 60
        pars[c.code] = round(math.ceil(secs * factor * 10) / 10, 1)
        print(f"{c.code}: runner {secs:.2f}s -> par {pars[c.code]}s")
    # which tier-1 chamber the hub's dive scenario lands in (deterministic: it comes from the tick the runner reaches the gate)
    res = subprocess.run(engine_cli() + ["sim", map_path, "--only", "hub: a dive starts a run in a tier-1 chamber", "--json"], capture_output=True, text=True)
    try:
        sc = json.loads(res.stdout)["data"]["scenarios"][0]
        v = sc["vars"]
        pick = int(next(x["value"] for x in v if x["name"] == "pick"))
        tier1 = [c for c in chambers if c.tier == 1]
        pars["_dive"] = tier1[pick].code
        print(f"the dive scenario lands in {pars['_dive']}")
    except Exception as e:
        print("could not find the dive's chamber:", e)
    json.dump(pars, open(out_file, "w"), indent=1, sort_keys=True)
    print(f"wrote {out_file}")
