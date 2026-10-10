"""The nineteen chambers of the reactor, in three tiers of six plus the Redline itself.

Each design is a short program on the `Chamber` cursor (kit.py): `run` extends a walkway, `jump` crosses a gap, `pad` launches,
`crumble`/`blink`/`curtain` add the hazards, `spark` places currency on a risky line, `relic_*` hides a golden relic for experts.
Every chamber can be cleared at base speed with no strafe-jumping (its `checks.sim` scenario proves it); relics deliberately cannot
be reached that way: they need a perfect edge jump, speed built with bunny hops and air strafing, or a pad arc steered hard.

Design rules the runner (and a new player) relies on, learned the hard way in `sim`:
- at 9.5 m/s a jump carries 6.7 m on the flat, so a landing platform is made deep enough for a full-speed landing (kit.jump does it);
- momentum does not turn in the air, so the course only changes direction on a platform with room to turn: sideways offsets are
  small (a diagonal line), and a real turn gets a deep "turn" platform;
- a stop slides about a metre, so anything you wait on (phase platforms, curtains) is big enough to stand still on.

Tiers: 1 = the Intake (depth 1-5: gaps, steps, pads), 2 = the Furnace (depth 6-10: crumbling floors, phase platforms, heat
curtains, beams), 3 = the Core (depth 11-14: everything at once, longer and less forgiving), 4 = the Redline (depth 15, the finale).
"""
import math
from kit import GRAVITY


def launch_for(rise, margin=1.4):
    """The pad speed whose apex clears `rise` metres by `margin`."""
    return round(math.sqrt(2 * GRAVITY * (rise + margin)), 2)


def relic_pillar(c, x, z, top, size=1.3, color=None):
    """A lone pillar from the lava to `top` at local (x, z) with the chamber's relic on it."""
    c.s.box(f"{c.code}_relicp", [size, top, size], [c.wx(x), top / 2, c.wz(z)], color or c.pal["pillar"], roughness=0.8)
    c.s.box(f"{c.code}_relicp.cap", [size + 0.04, 0.08, size + 0.04], [c.wx(x), top - 0.03, c.wz(z)], "#ffd23f", emissive="#7a5200", collide=False)
    c.relic_at(x, top + 1.05, z)


def side_spark(c, plat, side, gap, dz=0.0, size=1.6):
    """A spark on a little pillar `gap` metres off the side of `plat`: a sideways hop out and back."""
    x = plat.x + side * (plat.w / 2 + gap + size / 2)
    z = plat.zc + dz
    c.s.box(f"{c.code}_sp{len(c.sparks) + 1}p", [size, plat.top, size], [c.wx(x), plat.top / 2, c.wz(z)], c.pal["pillar"], roughness=0.8)
    c.spark(0, 0, at=(x, plat.top + 1.0, z))


# ------------------------------------------------------------------ tier 1: the Intake
def a1(c):
    c.start()
    c.run(5)
    c.spark(0, -1.7, dy=1.3)            # over the first gap: jump through it
    c.jump(3.0, 6, w=5)
    c.jump(3.4, 5, w=4, dy=0.8)
    c.jump(4.0, 6, w=5)
    c.checkpoint()
    c.jump(3.0, 6, w=4.6, dx=1.2)
    p = c.jump(3.0, 6, w=4.6, dx=1.2)
    side_spark(c, p, +1, 2.4)
    c.jump(3.2, 8, w=6, dx=-1.0)
    p = c.cur
    relic_pillar(c, p.x - p.w / 2 - 5.9 - 0.65, p.zc, p.top)     # 5.9 m off the side: a perfect edge jump
    c.finish()


def a2(c):
    c.start()
    c.run(4)
    for i in range(5):
        c.jump(2.2, 3.0, w=3.6, dy=0.9)
        if i == 2:
            c.spark(0, 1.5, dy=1.6)
    top = c.cur
    c.checkpoint()
    relic_pillar(c, top.x + top.w / 2 + 6.0 + 0.65, top.zc, top.top + 0.4)
    c.run(3)
    c.jump(5.5, 8, w=6, dy=-4.0)
    c.spark(-2.0, 2.0, dy=1.0)
    c.jump(3.0, 6, w=4.6, dx=-1.2)
    c.jump(3.0, 6, w=4.6, dx=-1.2)
    c.finish()


def a3(c):
    c.start()
    c.run(5)
    rise = 3.0
    c.pad(rise, launch_for(rise), 5.0, 6)
    c.spark(0, 9.0, dy=1.9)             # high in the pad's arc: you fly through it
    c.run(3, w=6)
    c.pad(rise, launch_for(rise), 5.0, 5)
    hi = c.cur
    c.checkpoint()
    c.spark(0, 8.4, dy=2.0)
    # relic: a perch beside the top platform, higher than it: steer the second pad's arc hard left
    relic_pillar(c, hi.x - hi.w / 2 - 3.2, hi.zc + 1.5, hi.top + 1.2, size=1.2)
    c.jump(4.0, 4, w=4, dy=-2.0)
    c.jump(4.0, 4, w=4, dy=-2.0)
    c.jump(3.5, 5, w=5, dy=-1.0)
    c.finish()


def a4(c):
    c.start()
    c.run(6)
    for _ in range(3):                  # a diagonal line to the right...
        c.jump(2.8, 6.0, w=4.4, dx=1.4)
    c.spark(1.0, 2.0, dy=1.3)
    turn = c.jump(2.8, 9.0, w=7.0, dx=1.0)     # ...a turn platform...
    c.checkpoint()
    relic_pillar(c, turn.x + turn.w / 2 + 6.3 + 0.65, turn.zc - 2.0, turn.top + 0.2)   # off the turn's outside edge: carry speed into it
    for _ in range(3):                  # ...and back to the left, climbing
        c.jump(2.8, 6.0, w=4.4, dx=-1.4, dy=0.4)
    p = c.cur
    side_spark(c, p, -1, 2.6)
    c.jump(3.0, 6, w=5, dx=-0.6)
    c.finish()


def a5(c):
    c.start(w=9)
    fork = c.run(4, w=9)
    # the risky line straight ahead on the right: two long gaps onto posts, a spark over each
    z0, t = c.z, c.top
    c.s.box(f"{c.code}_rk1", [2.2, t, 2.4], [c.wx(2.2), t / 2, c.wz(z0 - 5.2 - 1.2)], c.pal["pillar"])
    c.s.box(f"{c.code}_rk2", [2.2, t, 2.4], [c.wx(2.2), t / 2, c.wz(z0 - 5.2 - 2.4 - 5.2 - 1.2)], c.pal["pillar"])
    c.spark(0, 0, at=(2.2, t + 1.3, z0 - 2.6))
    c.spark(0, 0, at=(2.2, t + 1.3, z0 - 2.4 - 5.2 - 2.6 - 2.4))
    # the safe line: easy hops out to the left and back (the runner takes this one)
    c.jump(2.4, 6, w=4.0, dx=-2.0)
    c.jump(2.4, 9, w=5.0, dx=-1.0)      # the turn
    c.jump(2.4, 6, w=4.0, dx=1.5)
    c.jump(2.6, 7, w=9, dx=1.5)         # both lines meet here
    c.checkpoint()
    c.run(3, w=9)
    c.jump(4.2, 6, w=5)
    c.jump(4.6, 7, w=6, dy=-0.6)
    p = c.cur
    relic_pillar(c, p.x + p.w / 2 + 3.0, p.zc, p.top + 2.0, size=1.1)   # high: from a bunny hop's apex
    c.finish()


def a6(c):
    c.top = 14.0
    c.start()
    c.run(5)
    for i, (gap, dx) in enumerate([(4.8, 0), (5.0, 1.2), (5.0, 1.2), (5.2, 0)]):
        c.jump(gap, 7.0, w=4.6, dx=dx, dy=-1.6)
        if i == 1:
            c.spark(0, 2.6, dy=1.0)
    c.checkpoint()
    c.run(2)
    for gap, dx in [(5.4, -1.2), (5.4, -1.2)]:
        c.jump(gap, 7.0, w=4.6, dx=dx, dy=-1.6)
    c.spark(0, 2.8, dy=1.5)
    p = c.cur
    relic_pillar(c, p.x + p.w / 2 + 6.8, p.zc, p.top - 1.0)   # off to the right and lower: drop to it at speed
    c.jump(5.0, 6, w=6, dy=-1.6)
    c.finish()


# ------------------------------------------------------------------ tier 2: the Furnace
def b1(c):
    c.start()
    c.run(5)
    c.crumble(7)
    c.spark(0, 4.0, dy=1.2)
    c.jump(3.2, 5, w=5)
    c.checkpoint()
    c.crumble(6, dxs=[0.8, -0.8, 0.8, -0.8, 0.8, -0.8])
    c.spark(0.8, 1.2, dy=1.3)
    c.jump(3.0, 6, w=5)
    c.crumble(4, first_gap=2.0)
    p = c.cur
    relic_pillar(c, p.x - p.w / 2 - 6.4, p.zc, p.top)
    c.jump(2.6, 6, w=6)
    c.finish()


def b2(c):
    c.start()
    pre = c.run(5, w=7)
    c.blink(["a", "b"])
    c.spark(0, 2.0, dy=1.4)
    after = c.jump(2.6, 6, w=6)
    c.checkpoint()
    c.skip_pad(pre, after, side=1)        # OVERDRIVE KEYS: over the phase platforms, no waiting
    c.blink(["b", "a", "b"])
    c.spark(0, 1.6, dy=1.3)
    p = c.cur
    relic_pillar(c, p.x + p.w / 2 + 6.4, p.zc, p.top, size=1.1, color="#ff3fa4")
    c.jump(2.8, 6, w=6)
    c.finish()


def b3(c):
    c.start(w=6)
    pre = c.run(9, w=6)
    c.curtain(1.2, 1.0, 0.0)
    after = c.run(9)
    c.curtain(1.2, 1.0, 1.1)
    c.skip_pad(pre, after, side=-1)       # OVERDRIVE KEYS: over the first curtain
    c.run(5)
    c.checkpoint()
    c.jump(3.0, 9, w=4)
    c.curtain(0.9, 0.9, 0.4)
    c.run(8)
    c.curtain(0.9, 0.9, 1.2)
    c.spark(0, 2.0, dy=1.3)
    p = c.cur
    relic_pillar(c, p.x + p.w / 2 + 6.6, p.zc + 2.0, p.top + 0.6)
    c.run(4)
    c.finish()


def b4(c):
    c.start()
    c.run(5)
    c.pad(3.0, launch_for(3.0), 5.0, 4)
    c.spark(0, 7.0, dy=2.0)
    c.crumble(3)
    c.jump(2.8, 5, w=4)
    c.checkpoint()
    c.pad(3.5, launch_for(3.5), 5.0, 4)
    c.crumble(3)
    c.spark(0, 1.5, dy=1.3)
    c.jump(3.0, 6, w=4, dy=-1.5)
    p = c.cur
    relic_pillar(c, p.x - 5.5, p.zc + 9.0, p.top + 4.0, size=1.4)    # up by the second pad's arc: steer left at the top
    c.jump(3.0, 6, w=6, dy=-1.0)
    c.finish()


def b5(c):
    c.start()
    c.run(3)
    c.run(10, w=1.3)
    c.jump(2.6, 8, w=1.3)
    c.spark(0, 3.5, dy=1.1)
    c.jump(2.6, 6, w=4)
    c.checkpoint()
    c.jump(2.8, 7, w=1.2, dy=0.8)
    c.jump(2.8, 7, w=1.2, dy=0.8)
    c.spark(0, 3.0, dy=1.1)
    c.jump(3.0, 6, w=5)
    p = c.cur
    relic_pillar(c, p.x + p.w / 2 + 6.6, p.zc - 1.0, p.top, size=0.9)
    c.jump(3.0, 6, w=6, dy=-0.8)
    c.finish()


def b6(c):
    c.start()
    c.run(4, w=7)
    c.pad(3.0, launch_for(3.0), 5.0, 4, w=7)
    c.spark(0, 7.0, dy=2.0)
    c.pad(3.0, launch_for(3.0), 5.0, 4, w=6)
    c.pad(3.0, launch_for(3.0), 5.0, 4, w=6)
    c.checkpoint()
    hi = c.cur
    relic_pillar(c, hi.x + hi.w / 2 + 3.0, hi.zc + 4.0, hi.top + 2.4, size=1.2)
    c.run(2)
    for gap in (5.4, 5.4, 5.4):
        c.jump(gap, 5, w=4.4, dy=-2.5)
    c.spark(0, 2.4, dy=1.2)
    c.jump(4.0, 6, w=6, dy=-1.5)
    c.finish()


# ------------------------------------------------------------------ tier 3: the Core
def c1(c):
    c.start()
    c.run(5)
    c.crumble(5)
    c.jump(4.6, 4, w=3.4)
    c.crumble(4, first_gap=2.0)
    c.spark(0, 3.0, dy=1.3)
    c.jump(4.8, 6, w=4, dy=0.5)
    c.checkpoint()
    c.pad(3.0, launch_for(3.0), 5.0, 3, w=3.0)
    c.crumble(5, dxs=[0, 0.8, -0.8, 0.8, -0.8])
    c.spark(0, 2.0, dy=1.3)
    c.jump(4.8, 6, w=4, dy=-1.5)
    p = c.cur
    relic_pillar(c, p.x - p.w / 2 - 7.6, p.zc, p.top - 1.2, size=1.1)       # far off the side and lower: only a long, fast jump
    c.jump(3.0, 6, w=6)
    c.finish()


def c2(c):
    c.start()
    pre = c.run(5, w=6)
    c.blink(["a", "b"], size=5.0)
    after = c.jump(3.0, 7, w=6)
    c.skip_pad(pre, after, side=-1)       # OVERDRIVE KEYS: over the strobe
    c.curtain(0.8, 0.9, 0.0)
    c.run(5)
    c.spark(0, 2.5, dy=1.2)
    c.checkpoint()
    c.blink(["b", "a", "b"], size=5.0, dy=0.6)
    c.jump(3.0, 8, w=4)
    c.curtain(0.8, 0.8, 0.5)
    c.spark(0, 2.0, dy=1.3)
    c.run(4)
    p = c.cur
    relic_pillar(c, p.x - p.w / 2 - 7.0, p.zc, p.top - 0.5, size=1.0, color="#3fe1ff")
    c.finish()


def c3(c):
    c.start()
    c.run(5)
    c.jump(5.0, 5, w=3.6)
    c.crumble(4, first_gap=1.5)
    c.pad(3.0, launch_for(3.0), 5.0, 8, w=4)
    c.spark(0, 9.0, dy=2.1)
    c.curtain(0.9, 0.9, 0.3)
    c.checkpoint()
    c.blink(["a", "b"], size=5.0)
    c.jump(3.0, 7, w=1.2)
    c.run(6, w=1.2)
    c.spark(0, 3.0, dy=1.1)
    c.jump(2.8, 6, w=4, dy=-1.0)
    c.checkpoint()
    c.crumble(5, dxs=[0.8, -0.8, 0.8, -0.8, 0])
    c.pad(3.0, launch_for(3.0), 5.0, 4)
    c.jump(4.0, 5, w=4, dy=-2.0)
    p = c.cur
    relic_pillar(c, p.x + p.w / 2 + 7.0, p.zc + 2.0, p.top)
    c.jump(3.0, 6, w=6, dy=-1.0)
    c.finish()


def c4(c):
    c.top = 22.0
    c.start(w=5)
    c.run(10, w=1.1)
    c.jump(3.0, 7, w=1.1)
    c.spark(0, 2.5, dy=1.1)
    c.jump(3.0, 5, w=4)
    c.pad(3.0, launch_for(3.0), 5.0, 4, w=4)
    c.jump(3.0, 3, w=2.0)
    c.jump(3.0, 3, w=2.0)
    c.jump(3.0, 6, w=4)
    c.checkpoint()
    c.run(8, w=1.0)
    c.jump(3.2, 8, w=1.0, dy=-0.8)
    c.spark(0, 4.0, dy=1.1)
    c.jump(3.2, 6, w=4, dy=-0.8)
    p = c.cur
    relic_pillar(c, p.x - p.w / 2 - 7.2, p.zc + 3.0, p.top + 0.3, size=0.9)
    c.jump(3.0, 6, w=6, dy=-1.0)
    c.finish()


def c5(c):
    c.top = 34.0
    c.start()
    c.run(5)
    drops = [(5.0, 0.0, -4.5), (5.4, 0.0, -4.5), (5.4, 0.0, -4.5), (6.0, 0.0, -5.0)]
    for i, (gap, dx, dy) in enumerate(drops):
        c.jump(gap, 4.0, w=3.6, dx=dx, dy=dy)
        if i in (1, 3):
            c.spark(0, 3.0, dy=2.4)
    c.checkpoint()
    c.run(3)
    for gap, dx, dy in [(6.0, 0.0, -5.0), (6.0, 0.0, -4.0)]:
        c.jump(gap, 3.6, w=3.2, dx=dx, dy=dy)
    p = c.cur
    relic_pillar(c, p.x + p.w / 2 + 6.0, p.zc - 3.0, p.top - 4.0, size=1.2)
    c.jump(5.0, 6, w=6, dy=-2.0)
    c.finish()


def c6(c):
    c.start()
    c.run(14, w=4)
    c.jump(5.6, 10, w=6)
    c.spark(0, 5.0, dy=1.3)
    c.jump(5.6, 10, w=5)
    c.checkpoint()
    c.jump(4.8, 6, w=3, dy=0.6)
    c.jump(5.4, 6, w=3, dy=0.0)
    c.jump(5.6, 12, w=4, dy=-0.6)
    c.spark(0, 6.0, dy=1.3)
    c.pad(3.0, launch_for(3.0), 5.0, 4)
    c.jump(5.0, 6, w=4, dy=-3.0)
    p = c.cur
    relic_pillar(c, p.x - p.w / 2 - 7.8, p.zc - 1.0, p.top, size=1.0)          # 8 m off the side: speed only
    c.jump(3.0, 6, w=6, dx=1.5)
    c.finish()


# ------------------------------------------------------------------ tier 4: the Redline (depth 15)
def core(c):
    c.start(w=9, d=10)
    c.run(5, w=6)
    c.pad(3.0, launch_for(3.0), 5.0, 5)
    c.spark(0, 9.0, dy=2.0)
    c.crumble(5)
    pre = c.jump(4.6, 6, w=6)
    c.checkpoint()
    c.blink(["a", "b"], size=5.0)
    after = c.jump(3.0, 9, w=6)
    c.skip_pad(pre, after, side=1)        # OVERDRIVE KEYS: over the phase platforms
    c.curtain(0.9, 0.9, 0.2)
    c.run(4)
    c.curtain(0.9, 0.9, 1.0)
    c.spark(0, 2.0, dy=1.3)
    c.checkpoint()
    c.run(10, w=1.1)
    c.jump(2.8, 7, w=1.1)
    c.jump(3.0, 6, w=4)
    c.pad(3.0, launch_for(3.0), 5.0, 4)
    c.pad(3.0, launch_for(3.0), 5.0, 4)
    c.checkpoint()
    c.run(2)
    c.crumble(4, dxs=[0.8, -0.8, 0.8, -0.8], first_gap=2.0)
    for gap in (5.4, 5.4):
        c.jump(gap, 5, w=4.4, dy=-2.0)
    c.spark(0, 2.4, dy=1.3)
    c.jump(4.0, 12, w=12, dy=-2.0)
    c.finish(d=8, w=12)


TIERS = {
    1: [("a1", "FIRST LIGHT", "JUMP THE GAPS. FIND THE VENT.", a1), ("a2", "STAIRWELL", "UP, THEN A LONG WAY DOWN.", a2),
        ("a3", "LAUNCH BAY", "PADS THROW YOU. KEEP RUNNING.", a3), ("a4", "SIDESTEP", "STEER ON THE GROUND, NOT IN THE AIR.", a4),
        ("a5", "SPLIT DECISION", "THE SHORT WAY PAYS.", a5), ("a6", "THE SLOPE", "DOWNHILL. DO NOT BRAKE.", a6)],
    2: [("b1", "CRUMBLE RUN", "AMBER FLOORS FALL. DO NOT STOP.", b1), ("b2", "PHASE SHIFT", "JUMP AS THE NEXT ONE APPEARS.", b2),
        ("b3", "HEAT CURTAINS", "RUN WHEN THE RED GOES DARK.", b3), ("b4", "PAD CHAIN", "LAND LIGHT.", b4),
        ("b5", "THE BEAM", "NARROW. FAST. STRAIGHT.", b5), ("b6", "THE CLIMB", "UP THE SHAFT.", b6)],
    3: [("c1", "MELTDOWN", "EVERYTHING FALLS.", c1), ("c2", "STROBE", "READ THE RHYTHM.", c2),
        ("c3", "THE GAUNTLET", "ALL OF IT. AT ONCE.", c3), ("c4", "SKYWALK", "A LONG WAY UP.", c4),
        ("c5", "FREEFALL", "DROP. STICK THE LANDING.", c5), ("c6", "OVERPASS", "MOMENTUM IS EVERYTHING.", c6)],
    4: [("core", "THE REDLINE", "VENT THE CORE.", core)],
}
