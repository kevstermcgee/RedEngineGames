#!/usr/bin/env python3
"""Generates maps/main.json: REDLINE, a momentum roguelite on Red Engine.

The reactor is redlining. From the Foundry (the hub) you dive through a chain of chambers drawn at random from three tiers, against a
clock that only grows when you vent a chamber. Clear a chamber under its par time for a streak and bonus sparks; fall into the lava and you
lose time and go back to the last checkpoint. Sparks you collect are banked for good and buy upgrades in the Foundry; reach depth 15 and
vent the Redline to escape, which opens the next Heat (a harder, richer version of the run). Golden relics hide in every chamber for
players who master bunny hopping and air strafing.

Everything is data (rules, vars, persist, ui): no Rust. Run from the project root:

    python3 tools/gen_map.py maps/main.json            # write the map
    python3 tools/gen_map.py maps/main.json --pars     # also re-measure every chamber's par with the engine's `sim` (needs the engine)
"""
import json, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kit import (Scene, Chamber, PALETTES, SPARK, RELIC, SPEED, JUMP, GRAVITY, AIR_ACCEL, GROUND_ACCEL, FRICTION, MAX_SPEED, FOV, r)
from chambers import TIERS
import routes

HERE = os.path.dirname(os.path.abspath(__file__))
PARS_FILE = os.path.join(HERE, "pars.json")
DEPTH_GOAL = 15
TIER_OF_DEPTH = "(depth <= 5) * 1 + (depth > 5 && depth <= 10) * 2 + (depth > 10 && depth <= 14) * 3 + (depth >= 15) * 4"

UPGRADES = [
    # key, name, description (sign), levels' costs
    ("coolant", "COOLANT", "+4S ON THE\nSTARTING CLOCK", [12, 30, 55, 90]),
    ("vents", "VENTS", "+1S FOR EVERY\nCHAMBER VENTED", [20, 45, 80, 125]),
    ("boots", "LAVA BOOTS", "BURNS COST\n0.8S LESS", [15, 35, 65]),
    ("magnet", "MAGNET", "GRAB SPARKS\nFROM FURTHER", [25, 60]),
    ("wind", "SECOND WIND", "+10S WHEN THE\nCLOCK HITS ZERO", [45, 100]),
    ("prism", "PRISM", "EVERY SPARK\nCOUNTS DOUBLE", [150]),
    ("keys", "OVERDRIVE KEYS", "UNLOCK THE\nSHORTCUT PADS", [80]),
]
FOCUS_TEXT = {
    "coolant": "COOLANT {lvl_coolant}/4: START CLOCK {start_clock}S",
    "vents": "VENTS {lvl_vents}/4: +{lvl_vents}S PER VENT",
    "boots": "LAVA BOOTS {lvl_boots}/3: A BURN COSTS {penalty}S",
    "magnet": "MAGNET {lvl_magnet}/2: WIDER SPARK PICKUP",
    "wind": "SECOND WIND {lvl_wind}/2: +{_wind_amt}S ONCE AT ZERO",
    "prism": "PRISM {lvl_prism}/1: SPARKS COUNT DOUBLE",
    "keys": "OVERDRIVE KEYS {lvl_keys}/1: SHORTCUT PADS",
}

S = Scene()
V = S.var

# ------------------------------------------------------------------ variables
for k in ["bank", "life_sparks", "runs", "escapes", "relics", "heat", "heat_unlocked"]:
    V(k, 0, persist=True)
for key, *_ in UPGRADES:
    V(f"lvl_{key}", 0, persist=True)
for h in range(6):
    V(f"best_h{h}", 0, persist=True)
    V(f"bestt_h{h}", 0, persist=True)
for k in ["running", "depth", "room", "cp", "tier", "pick", "rnd", "cnt", "deadline", "clock", "room_start", "run_start", "run_time",
          "run_sparks", "streak", "wind_used", "spark_val", "penalty", "start_clock", "burns",
          "_focus", "_msg", "_msg_t", "_msg_on", "_gain", "_bonus", "_need", "_rt", "_par", "_bph", "_a", "_b", "_danger", "_wind_amt", "_best_now", "_vent_t"]:
    V(k, 0)
for key, _, _, costs in UPGRADES:
    V(f"cost_{key}", costs[0])

MSG = {"spark": 1, "relic": 2, "cp": 3, "burn": 4, "vent": 5, "par": 6, "wind": 7, "bought": 8, "need": 9, "maxed": 10, "heat": 11, "locked": 12}


def msg(code):
    return [{"set": ["_msg", MSG[code] if isinstance(code, str) else code]}, {"set": ["_msg_t", "time"]}, {"set": ["_msg_on", 1]}]


def derived():
    """Recompute everything that follows from the upgrades and the heat (called at start and after any purchase or heat change)."""
    acts = [{"set": ["start_clock", "25 + 4 * lvl_coolant"]},
            {"set": ["penalty", "3 - 0.8 * lvl_boots + 0.5 * heat"]},
            {"set": ["_wind_amt", "10 * (lvl_wind >= 1) + 8 * (lvl_wind >= 2)"]},
            {"set": ["spark_val", "(1 + lvl_prism) * (1 + (heat >= 2) + (heat >= 4))"]}]
    for key, _, _, costs in UPGRADES:
        expr = " + ".join(f"(lvl_{key} == {i}) * {c}" for i, c in enumerate(costs)) or "0"
        acts.append({"set": [f"cost_{key}", expr]})
    acts.append({"set": ["_best_now", " + ".join(f"(heat == {h}) * best_h{h}" for h in range(6))]})
    return acts


# ------------------------------------------------------------------ the Foundry (hub)
HUB_TOP = 2.0
pal = PALETTES[0]
S.box("hub_floor", [32, HUB_TOP, 34], [0, HUB_TOP / 2, 0], pal["pillar"], roughness=0.85, metallic=0.2)
S.box("hub_floor.top", [32.02, 0.08, 34.02], [0, HUB_TOP - 0.035, 0], pal["top"], collide=False, roughness=0.6, metallic=0.4)
for i, (x, z, w, d) in enumerate([(0, 17, 32, 0.12), (0, -17, 32, 0.12), (16, 0, 0.12, 34), (-16, 0, 0.12, 34)]):
    S.box(f"hub_trim{i}", [w, 0.07, d], [x, HUB_TOP + 0.01, z], pal["trim"], emissive=pal["trim"], collide=False)
# floor markings: a walkway from spawn to the dive gate
S.box("hub_walk", [3.0, 0.03, 22], [0, HUB_TOP + 0.005, 0], "#3a3940", collide=False)
for i in range(6):
    S.box(f"hub_chev{i}", [1.2, 0.04, 0.25], [0, HUB_TOP + 0.02, 8 - i * 3.2], "#ff7a2f", emissive="#7a2a00", collide=False)
S.spawn("hub", 0, HUB_TOP, 12.0, 0)
S.text("hub_title", "THE FOUNDRY", [0, HUB_TOP + 9.6, -14.5], 0.9, "#ffd29a", "#ff7a2f")

# the dive gate
gz = -13.0
red, glow = "#ff3b2f", "#c41a10"
for side in (-1, 1):
    S.box(f"dive_post{side + 1}", [0.8, 5.6, 0.8], [side * 3.0, HUB_TOP + 2.8, gz], "#2a1414", emissive="#4a0a06", metallic=0.6, roughness=0.4)
S.box("dive_top", [6.8, 0.8, 0.8], [0, HUB_TOP + 5.6, gz], "#2a1414", emissive="#4a0a06", metallic=0.6, roughness=0.4)
S.box("dive_field", [5.2, 5.2, 0.1], [0, HUB_TOP + 2.6, gz], red, emissive=glow, collide=False, opacity=0.55)
S.text("dive_sign", "DIVE", [0, HUB_TOP + 6.6, gz], 0.7, "#ffb0a0", "#ff3b2f")
S.zone("dive", -2.4, gz - 0.8, 2.4, gz + 0.8, HUB_TOP)
S.light("dive_l", 0, HUB_TOP + 3.5, gz + 2.5, "#ff5a3a", 22, 16)
for i, (x, z) in enumerate([(-9, 9), (9, 9), (-9, -5), (9, -5), (0, 3)]):
    S.light(f"hub_l{i}", x, HUB_TOP + 6.5, z, "#ffd8a8", 16, 20)

# upgrade stations: west side (3), east side (3), south (1)
STATIONS = [("coolant", -12.5, 7.0, 90), ("vents", -12.5, 0.5, 90), ("boots", -12.5, -6.0, 90),
            ("magnet", 12.5, 7.0, -90), ("wind", 12.5, 0.5, -90), ("prism", 12.5, -6.0, -90), ("keys", 0, 15.0, 180)]
for fi, (key, name, desc, costs) in enumerate(UPGRADES, start=1):
    _, sx, sz, yaw = next(s for s in STATIONS if s[0] == key)
    # the station faces the middle of the hall: `inward` is the unit vector from it toward the hall
    ix, iz = (1, 0) if yaw == 90 else (-1, 0) if yaw == -90 else (0, -1)
    px, pz = sx - ix * 0.9, sz - iz * 0.9        # the back panel
    if yaw == 180:
        S.box(f"st_{key}", [4.6, 4.2, 0.5], [px, HUB_TOP + 2.1, pz], "#26252b", emissive="#140a04", metallic=0.6, roughness=0.5)
    else:
        S.box(f"st_{key}", [0.5, 4.2, 4.6], [px, HUB_TOP + 2.1, pz], "#26252b", emissive="#140a04", metallic=0.6, roughness=0.5)
    tx, tz = px + ix * 0.3, pz + iz * 0.3
    S.text(f"st_{key}.name", name, [tx, HUB_TOP + 3.5, tz], 0.34, "#ffd29a", "#ff7a2f", yaw=yaw)
    S.text(f"st_{key}.desc", desc, [tx, HUB_TOP + 2.6, tz], 0.17, "#ffffff", "#5a5a5a", yaw=yaw)
    # level pips: one per level, lit when bought
    n = len(costs)
    for j in range(n):
        off = (j - (n - 1) / 2) * 0.55
        qx, qz = (tx, tz + off) if yaw in (90, -90) else (tx + off, tz)
        S.box(f"pip_{key}_{j + 1}.off", [0.32, 0.32, 0.32], [qx, HUB_TOP + 1.7, qz], "#3a3a3a", collide=False)
        S.box(f"pip_{key}_{j + 1}", [0.36, 0.36, 0.36], [qx, HUB_TOP + 1.7, qz], "#7dff9a", emissive="#1fbf4a", collide=False)
    # the buy plate, and the info zone around it
    bx, bz = sx + ix * 1.8, sz + iz * 1.8
    S.box(f"buy_{key}.plate", [1.3, 0.05, 1.3], [bx, HUB_TOP + 0.02, bz], "#ffb347", emissive="#a85a00", collide=False)
    S.zone(f"buy_{key}", bx - 0.55, bz - 0.55, bx + 0.55, bz + 0.55, HUB_TOP)
    S.zone(f"info_{key}", sx + ix * 1.2 - 2.6, sz + iz * 1.2 - 2.6, sx + ix * 1.2 + 2.6, sz + iz * 1.2 + 2.6, HUB_TOP)
    S.light(f"st_{key}.l", sx + ix * 2.5, HUB_TOP + 3.2, sz + iz * 2.5, "#ffc488", 10, 8)

# heat selector: six pads in a row before the dive gate
HEAT_Z = -8.0
S.text("heat_sign", "HEAT", [0, HUB_TOP + 3.2, HEAT_Z], 0.4, "#ffb0a0", "#ff3b2f")
for h in range(6):
    hx = [-7.6, -5.6, -3.6, 3.6, 5.6, 7.6][h]
    S.box(f"heat{h}.base", [1.5, 0.06, 1.5], [hx, HUB_TOP + 0.02, HEAT_Z], "#3a2020", emissive="#200606", collide=False)
    S.box(f"heat{h}.sel", [1.6, 0.08, 1.6], [hx, HUB_TOP + 0.04, HEAT_Z], "#ff5a3a", emissive="#ff2a10", collide=False)
    S.box(f"heat{h}.lock", [1.0, 0.6, 1.0], [hx, HUB_TOP + 0.3, HEAT_Z], "#2a2a2e", metallic=0.8, roughness=0.3, collide=False)
    S.text(f"heat{h}.num", str(h), [hx, HUB_TOP + 1.2, HEAT_Z], 0.36, "#ffd2c8", "#ff3b2f")
    S.zone(f"heatpad{h}", hx - 0.7, HEAT_Z - 0.7, hx + 0.7, HEAT_Z + 0.7, HUB_TOP)
S.zone("info_heat", -8.6, HEAT_Z - 1.6, 8.6, HEAT_Z + 1.6, HUB_TOP)

# the relic shrine: one pedestal per chamber (the Redline has none), a gem appears on it when its relic is found
RELIC_CODES = [code for t in (1, 2, 3) for code, *_ in TIERS[t]]
S.text("shrine_sign", "RELICS", [-8.6, HUB_TOP + 2.6, 15.2], 0.32, "#ffe08a", "#c88a00", yaw=180)
for i, code in enumerate(RELIC_CODES):
    x = -13.0 + (i % 9) * 1.1          # two rows of nine
    zz = 15.7 if i < 9 else 14.5
    S.box(f"shrine_{code}.ped", [0.5, 0.9, 0.5], [x, HUB_TOP + 0.45, zz], "#2c2a28", metallic=0.5, roughness=0.5)
    S.gem(f"shrine_{code}", x, HUB_TOP + 1.25, zz, RELIC["color"], RELIC["emissive"], size=0.9)
S.zone("info_shrine", -14.5, 13.0, -3.0, 16.8, HUB_TOP)
# the records board
S.box("records", [0.4, 3.4, 5.0], [15.4, HUB_TOP + 1.7, 13.0], "#26252b", emissive="#140a04", metallic=0.6, roughness=0.5)
S.text("records.t", "RECORDS", [15.15, HUB_TOP + 2.6, 13.0], 0.34, "#ffd29a", "#ff7a2f", yaw=-90)
S.text("records.s", "STAND HERE", [15.15, HUB_TOP + 1.9, 13.0], 0.16, "#ffffff", "#5a5a5a", yaw=-90)
S.zone("info_records", 11.5, 10.5, 15.2, 15.5, HUB_TOP)
S.zone("info_dive", -3.0, -12.0, 3.0, -9.6, HUB_TOP)

# the Foundry's surroundings: reactor towers in a ring, lava glow under the deck's edge, embers
import random as _random
_rnd = _random.Random(7)
for j in range(14):
    ang = j / 14 * 6.283 + _rnd.uniform(-0.15, 0.15)
    dist = _rnd.uniform(42, 85)
    tx, tz = dist * __import__("math").sin(ang), dist * __import__("math").cos(ang)
    th, tw = _rnd.uniform(22, 70), _rnd.uniform(6, 13)
    S.box(f"hub_tower{j}", [tw, th, tw], [tx, th / 2, tz], "#1c1416", roughness=0.9, collide=False)
    S.box(f"hub_tower{j}.slit", [0.6, th * 0.7, tw + 0.06], [tx, th * 0.45, tz], "#ff7a2f", emissive="#7a2a00", collide=False)
for j, (lx, lz) in enumerate([(-19, -12), (19, -12), (-19, 10), (19, 10), (0, -21), (0, 21)]):
    S.light(f"hub_lava{j}", lx, 1.2, lz, "#ff5a14", 30, 18)

# the lava: one emissive sea under everything, and the zone that burns you
S.add({"id": "lava", "type": "plane", "size": [6000, 3200], "position": [1500, 0.02, 0], "material": {"color": "#ff5a14", "emissive": "#ff3a08", "roughness": 0.9}, "collide": False})
S.zone("lava", -1400, -1600, 4400, 1600, 0.0)

# ------------------------------------------------------------------ chambers
pars = json.load(open(PARS_FILE)) if os.path.exists(PARS_FILE) else {}
chambers = []
index = 0
for tier in (1, 2, 3, 4):
    for slot, (code, name, blurb, build) in enumerate(TIERS[tier]):
        c = Chamber(S, code, name, tier, index, blurb=blurb)
        build(c)
        c.decor(seed=1000 + index)
        c.slot, c.room = slot, index + 1
        c.par = pars.get(code, round(routes.estimate(c), 1))
        chambers.append(c)
        index += 1
for c in chambers:
    V(f"used_{c.code}", 0)
    V(f"entered_{c.code}", 0)

# ------------------------------------------------------------------ rules: start of the scene (a fresh run every time the end card restarts it)
start = derived() + [{"set": ["clock", "start_clock"]}]
S.rule("init", {"start": True}, start)
for key, _, _, costs in UPGRADES:
    for j in range(len(costs)):
        S.rule(f"pip_{key}_{j + 1}_off", {"start": True}, [{"hide": f"pip_{key}_{j + 1}"}], if_=f"lvl_{key} < {j + 1}")
for h in range(6):
    S.rule(f"heat{h}_unsel", {"start": True}, [{"hide": f"heat{h}.sel"}], if_=f"heat != {h}")
    S.rule(f"heat{h}_open", {"start": True}, [{"hide": f"heat{h}.lock"}], if_=f"heat_unlocked >= {h}")
for code in RELIC_CODES:
    S.rule(f"shrine_{code}_off", {"start": True}, [{"hide": f"shrine_{code}"}], if_=f"relic_{code} == 0")
    S.rule(f"relic_{code}_gone", {"start": True}, [{"hide": f"{code}_relic"}], if_=f"relic_{code} == 1")
    V(f"relic_{code}", 0, persist=True)
lids = [lid for c in chambers for lid in c.lids]
if lids:
    S.rule("keys_open", {"start": True}, [{"deactivate": lid} for lid in lids] + [{"hide": f"{lid}.sign"} for lid in lids], if_="lvl_keys >= 1")

# ------------------------------------------------------------------ the hub: upgrades, heat, focus lines
for fi, (key, name, desc, costs) in enumerate(UPGRADES, start=1):
    n = len(costs)
    S.rule(f"info_{key}_in", {"enter": {"zone": f"info_{key}"}}, [{"set": ["_focus", fi]}], if_="running == 0")
    S.rule(f"info_{key}_out", {"exit": {"zone": f"info_{key}"}}, [{"set": ["_focus", 0]}], if_=f"_focus == {fi}")
    S.rule(f"buy_{key}", {"enter": {"zone": f"buy_{key}"}},
           [{"add": ["bank", f"-cost_{key}"]}, {"add": [f"lvl_{key}", 1]}] + derived() + [{"set": ["clock", "start_clock"]}] + msg("bought") + [{"emit": f"bought_{key}"}],
           if_=f"running == 0 && bank >= cost_{key} && lvl_{key} < {n}")
    S.rule(f"buy_{key}_short", {"enter": {"zone": f"buy_{key}"}}, [{"set": ["_need", f"cost_{key} - bank"]}] + msg("need"),
           if_=f"running == 0 && bank < cost_{key} && lvl_{key} < {n}")
    S.rule(f"buy_{key}_max", {"enter": {"zone": f"buy_{key}"}}, msg("maxed"), if_=f"running == 0 && lvl_{key} >= {n}")
    for j in range(n):
        S.rule(f"pip_{key}_{j + 1}_on", {"event": f"bought_{key}"}, [{"show": f"pip_{key}_{j + 1}"}], if_=f"lvl_{key} >= {j + 1}")
for h in range(6):
    S.rule(f"heatpad{h}", {"enter": {"zone": f"heatpad{h}"}},
           [{"set": ["heat", h]}] + derived() + msg("heat") + [{"emit": "heat_changed"}], if_=f"running == 0 && heat_unlocked >= {h}")
    S.rule(f"heatpad{h}_locked", {"enter": {"zone": f"heatpad{h}"}}, msg("locked"), if_=f"running == 0 && heat_unlocked < {h}")
    S.rule(f"heat{h}_sel_on", {"event": "heat_changed"}, [{"show": f"heat{h}.sel"}], if_=f"heat == {h}")
    S.rule(f"heat{h}_sel_off", {"event": "heat_changed"}, [{"hide": f"heat{h}.sel"}], if_=f"heat != {h}")
for zid, fi in [("info_heat", 8), ("info_records", 9), ("info_shrine", 10), ("info_dive", 11)]:
    S.rule(f"{zid}_in", {"enter": {"zone": zid}}, [{"set": ["_focus", fi]}], if_="running == 0")
    S.rule(f"{zid}_out", {"exit": {"zone": zid}}, [{"set": ["_focus", 0]}], if_=f"_focus == {fi}")

# ------------------------------------------------------------------ the run: dive, choose a chamber, the clock
S.rule("dive", {"enter": {"zone": "dive"}},
       [{"set": ["running", 1]}, {"set": ["depth", 1]}, {"set": ["run_start", "time"]}, {"set": ["deadline", "time + start_clock"]},
        {"set": ["run_sparks", 0]}, {"set": ["streak", 0]}, {"set": ["wind_used", 0]}, {"set": ["burns", 0]}, {"add": ["runs", 1]}, {"set": ["_focus", 0]}]
       + derived() + [{"emit": "next"}], if_="running == 0")

# pick an unvisited chamber of the tier this depth is in: the r-th unused one, where r comes from the tick the runner arrived on
cnt_terms, pick_terms = [], []
for t in (1, 2, 3):
    codes = [c for c in chambers if c.tier == t]
    unused = [f"(1 - used_{c.code})" for c in codes]
    cnt_terms.append(f"(tier == {t}) * ({' + '.join(unused)})")
    terms = []
    for i, c in enumerate(codes):
        prefix = " + ".join(unused[:i]) if i else "0"
        terms.append(f"{i} * {unused[i]} * (({prefix}) == rnd)")
    pick_terms.append(f"(tier == {t}) * ({' + '.join(terms)})")
S.rule("choose", {"event": "next"},
       [{"set": ["tier", TIER_OF_DEPTH]},
        {"set": ["cnt", " + ".join(cnt_terms) + " + (tier == 4)"]},
        {"set": ["rnd", "(tick * 7919 + depth * 104729 + runs * 613) % cnt"]},
        {"set": ["pick", " + ".join(pick_terms)]},
        {"emit": "go"}], if_="running == 1")
for c in chambers:
    S.rule(f"go_{c.code}", {"event": "go"},
           [{"teleport": f"{c.code}_cp0"}, {"set": ["room", c.room]}, {"set": ["cp", 0]}, {"set": [f"used_{c.code}", 1]},
            {"set": ["room_start", "time"]}, {"set": ["_par", c.par]}, {"set": ["_msg", 100 + c.room]}, {"set": ["_msg_t", "time"]}, {"set": ["_msg_on", 1]}],
           if_=f"tier == {c.tier} && pick == {c.slot}")

S.rule("clock", {"every": 0.05},
       [{"set": ["clock", "(deadline - time) - (deadline - time) % 0.1"]}, {"set": ["run_time", "time - run_start"]},
        {"set": ["_rt", "(time - room_start) - (time - room_start) % 0.1"]}, {"set": ["_danger", "deadline - time < 8"]}], if_="running == 1")
S.rule("hubclock", {"every": 0.25}, [{"set": ["clock", "start_clock"]}], if_="running == 0")
S.rule("msg_fade", {"every": 0.05}, [{"set": ["_msg_on", "time - _msg_t < 1.8"]}], if_="_msg_on == 1")
S.rule("second_wind", {"every": 0.05}, [{"set": ["deadline", "time + _wind_amt"]}, {"set": ["wind_used", 1]}, {"set": ["_bonus", "_wind_amt"]}] + msg("wind"),
       if_="running == 1 && deadline - time <= 0 && wind_used == 0 && lvl_wind >= 1")
best_upd = [{"set": [f"best_h{h}", f"best_h{h} + (heat == {h}) * (depth - 1 > best_h{h}) * (depth - 1 - best_h{h})"]} for h in range(6)]
S.rule("burnout", {"every": 0.05},
       [{"set": ["clock", 0]}] + best_upd + [{"set": ["_best_now", " + ".join(f"(heat == {h}) * best_h{h}" for h in range(6))]}, {"set": ["running", 2]}, {"end": "burnout"}],
       if_="running == 1 && deadline - time <= 0 && (wind_used == 1 || lvl_wind == 0)")

# burning: the lava, and the heat curtains while they glow
S.rule("lava", {"enter": {"zone": "lava", "height": 0.9}}, [{"emit": "burn"}])
S.rule("burn_hub", {"event": "burn"}, [{"teleport": "hub"}], if_="room == 0")
S.rule("burn_cost", {"event": "burn"}, [{"add": ["deadline", "-penalty"]}, {"add": ["burns", 1]}, {"set": ["streak", 0]}] + msg("burn"), if_="running == 1")
for c in chambers:
    for j, (cid, zone) in enumerate(c.cps):
        S.rule(f"burn_{cid}", {"event": "burn"}, [{"teleport": cid}], if_=f"room == {c.room} && cp == {j}")

# blink phase: A is solid for [0, 2.4) s of every 3.2 s, B for [1.6, 4.0): 0.8 s of overlap at each hand-over
S.rule("blink_clock", {"every": 0.05}, [{"set": ["_bph", "time % 3.2"]}])
S.rule("a_on", {"every": 0.05}, [{"set": ["_a", 1]}, {"emit": "a_on"}], if_="_bph < 2.4 && _a == 0")
S.rule("a_off", {"every": 0.05}, [{"set": ["_a", 0]}, {"emit": "a_off"}], if_="_bph >= 2.4 && _a == 1")
S.rule("b_on", {"every": 0.05}, [{"set": ["_b", 1]}, {"emit": "b_on"}], if_="(_bph >= 1.6 || _bph < 0.8) && _b == 0")
S.rule("b_off", {"every": 0.05}, [{"set": ["_b", 0]}, {"emit": "b_off"}], if_="_bph >= 0.8 && _bph < 1.6 && _b == 1")

# ------------------------------------------------------------------ per chamber
for c in chambers:
    k = c.room
    # crossing the start line: this is the chamber you are in, and its par clock starts
    S.rule(f"enter_{c.code}", {"enter": {"zone": c.entry_zone}},
           [{"set": ["room", k]}, {"set": ["cp", 0]}, {"set": ["room_start", "time"]}, {"set": ["_par", c.par]}, {"set": [f"entered_{c.code}", 1]}],
           if_=f"entered_{c.code} == 0")
    # checkpoints
    for j, (cid, zone) in enumerate(c.cps):
        if zone:
            S.rule(f"{cid}_reach", {"enter": {"zone": zone}}, [{"set": ["cp", j]}, {"show": f"{cid}.lit"}] + msg("cp"), if_=f"room == {k} && cp < {j}")
            S.rule(f"{cid}_dark", {"start": True}, [{"hide": f"{cid}.lit"}])
    # sparks: three pick-up radii, one per MAGNET level
    for sid in c.sparks:
        V(f"got_{sid}", 0)
        for m, pad in enumerate([0.45, 1.4, 2.4]):
            S.rule(f"{sid}_m{m}", {"enter": {"object": sid, "pad": pad}},
                   [{"set": [f"got_{sid}", 1]}, {"hide": sid}, {"set": ["_gain", "spark_val"]}, {"add": ["bank", "spark_val"]},
                    {"add": ["run_sparks", "spark_val"]}, {"add": ["life_sparks", "spark_val"]}] + msg("spark"),
                   if_=f"got_{sid} == 0 && lvl_magnet == {m}")
    # the relic: once ever
    if c.relic:
        S.rule(f"{c.code}_relic_take", {"enter": {"object": c.relic, "pad": 0.6}},
               [{"set": [f"relic_{c.code}", 1]}, {"hide": c.relic}, {"add": ["relics", 1]}, {"set": ["_gain", "10 * (1 + lvl_prism)"]},
                {"add": ["bank", "_gain"]}, {"add": ["life_sparks", "_gain"]}] + msg("relic"), if_=f"relic_{c.code} == 0")
    # crumbling floor: a tile drops 0.45 s after it is first touched, and every tile comes back when you burn
    for tid in c.crumbles:
        V(f"ct_{tid}", 0)
        S.rule(f"{tid}_touch", {"enter": {"object": tid, "pad": 0.12}}, [{"set": [f"ct_{tid}", "time"]}], if_=f"ct_{tid} == 0 && room == {k}")
        S.rule(f"{tid}_fall", {"every": 0.05}, [{"deactivate": tid}, {"set": [f"ct_{tid}", -1]}], if_=f"ct_{tid} > 0 && time - ct_{tid} > 0.45")
    if c.crumbles:
        S.rule(f"{c.code}_crumble_reset", {"event": "burn"}, [a for tid in c.crumbles for a in ({"activate": tid}, {"set": [f"ct_{tid}", 0]})], if_=f"room == {k}")
    # phase platforms
    A = [b for b, ph in c.blinks if ph == "a"]
    B = [b for b, ph in c.blinks if ph == "b"]
    if A:
        S.rule(f"{c.code}_a_on", {"event": "a_on"}, [{"activate": b} for b in A])
        S.rule(f"{c.code}_a_off", {"event": "a_off"}, [{"deactivate": b} for b in A])
    if B:
        S.rule(f"{c.code}_b_on", {"event": "b_on"}, [{"activate": b} for b in B])
        S.rule(f"{c.code}_b_off", {"event": "b_off"}, [{"deactivate": b} for b in B])
    # heat curtains
    for cid, box, on, off, offset in c.curtains:
        per = on + off
        V(f"hc_{cid}", 1)
        S.rule(f"{cid}_off", {"every": 0.05}, [{"set": [f"hc_{cid}", 0]}, {"hide": cid}, {"emit": f"{cid}_off"}], if_=f"(time + {offset}) % {per} >= {on} && hc_{cid} == 1")
        S.rule(f"{cid}_on", {"every": 0.05}, [{"set": [f"hc_{cid}", 1]}, {"show": cid}, {"emit": f"{cid}_on"}], if_=f"(time + {offset}) % {per} < {on} && hc_{cid} == 0")
        S.rule(f"{cid}_burn", {"enter": {"box": box}}, [{"emit": "burn"}], if_=f"hc_{cid} == 1")
    # the vent: always raises vent_<code> (the scenarios prove it); during a run it also scores the chamber and moves on
    S.rule(f"{c.code}_vent", {"enter": {"zone": c.exit_zone}}, [{"emit": f"vent_{c.code}"}], if_=f"room == {k} && _vent_t != {k}")
    S.rule(f"{c.code}_vent_mark", {"enter": {"zone": c.exit_zone}}, [{"set": ["_vent_t", k]}], if_=f"room == {k}")
    S.rule(f"{c.code}_vent_par", {"event": f"vent_{c.code}"},
           [{"add": ["streak", 1]}, {"set": ["_bonus", f"{c.par} * (1 - 0.07 * heat) + lvl_vents"]}, {"add": ["deadline", "_bonus"]},
            {"set": ["_gain", "spark_val * (streak + (streak > 5) * (5 - streak))"]}, {"add": ["bank", "_gain"]}, {"add": ["run_sparks", "_gain"]},
            {"add": ["life_sparks", "_gain"]}] + msg("par") + [{"add": ["depth", 1]}, {"emit": "cleared"}],
           if_=f"running == 1 && time - room_start <= {c.par}")
    S.rule(f"{c.code}_vent_slow", {"event": f"vent_{c.code}"},
           [{"set": ["streak", 0]}, {"set": ["_bonus", f"{c.par} * (1 - 0.07 * heat) + lvl_vents"]}, {"add": ["deadline", "_bonus"]}] + msg("vent")
           + [{"add": ["depth", 1]}, {"emit": "cleared"}],
           if_=f"running == 1 && time - room_start > {c.par}")

S.rule("cleared_next", {"event": "cleared"}, [{"emit": "next"}], if_=f"depth <= {DEPTH_GOAL}")
esc = [{"set": ["run_time", "time - run_start"]}, {"add": ["escapes", 1]}, {"set": ["_gain", "(20 + 10 * heat) * (1 + lvl_prism)"]},
       {"add": ["bank", "_gain"]}, {"add": ["run_sparks", "_gain"]}, {"add": ["life_sparks", "_gain"]}]
esc += [{"set": [f"best_h{h}", f"best_h{h} + (heat == {h}) * ({DEPTH_GOAL} - best_h{h})"]} for h in range(6)]
esc += [{"set": [f"bestt_h{h}", f"bestt_h{h} + (heat == {h}) * ((bestt_h{h} == 0) || (run_time < bestt_h{h})) * (run_time - bestt_h{h})"]} for h in range(6)]
esc += [{"set": ["heat_unlocked", "heat_unlocked + (heat == heat_unlocked) * (heat_unlocked < 5)"]}, {"set": ["running", 2]}, {"end": "vented"}]
S.rule("escaped", {"event": "cleared"}, esc, if_=f"depth > {DEPTH_GOAL}")

# ------------------------------------------------------------------ what the game says (ui)
objective = []
M = MSG
objective += [
    {"if": f"_msg_on == 1 && _msg == {M['spark']}", "text": "+{_gain:SPARK|SPARKS}"},
    {"if": f"_msg_on == 1 && _msg == {M['relic']}", "text": "RELIC! {relics} OF 18 - +{_gain} SPARKS"},
    {"if": f"_msg_on == 1 && _msg == {M['cp']}", "text": "CHECKPOINT"},
    {"if": f"_msg_on == 1 && _msg == {M['burn']} && running == 1", "text": "BURNED  -{penalty}S"},
    {"if": f"_msg_on == 1 && _msg == {M['vent']}", "text": "VENTED  +{_bonus}S"},
    {"if": f"_msg_on == 1 && _msg == {M['par']}", "text": "UNDER PAR! +{_bonus}S +{_gain} - STREAK {streak}"},
    {"if": f"_msg_on == 1 && _msg == {M['wind']}", "text": "SECOND WIND!  +{_bonus}S"},
    {"if": f"_msg_on == 1 && _msg == {M['bought']}", "text": "INSTALLED! {bank:SPARK|SPARKS} LEFT"},
    {"if": f"_msg_on == 1 && _msg == {M['need']}", "text": "NEED {_need} MORE SPARKS"},
    {"if": f"_msg_on == 1 && _msg == {M['maxed']}", "text": "ALREADY AT FULL POWER"},
    {"if": f"_msg_on == 1 && _msg == {M['heat']}", "text": "HEAT {heat} SELECTED"},
    {"if": f"_msg_on == 1 && _msg == {M['locked']}", "text": "LOCKED - ESCAPE AT HEAT {heat_unlocked} FIRST"},
]
for c in chambers:
    objective.append({"if": f"_msg_on == 1 && _msg == {100 + c.room}", "text": f"{{depth}}/15 {c.name} - PAR {c.par}S"})
for fi, (key, name, desc, costs) in enumerate(UPGRADES, start=1):
    objective.append({"if": f"_focus == {fi} && lvl_{key} < {len(costs)}", "text": FOCUS_TEXT[key] + " - NEXT {cost_" + key + "}"})
    objective.append({"if": f"_focus == {fi}", "text": FOCUS_TEXT[key] + " - MAXED"})
objective += [
    {"if": "_focus == 8", "text": "HEAT {heat} OF {heat_unlocked} OPEN - BEST DEPTH {_best_now}/15"},
    {"if": "_focus == 9", "text": "RUNS {runs} - ESCAPES {escapes} - BEST {best_h0}/{best_h1}/{best_h2}/{best_h3}/{best_h4}/{best_h5}"},
    {"if": "_focus == 10", "text": "RELICS {relics} OF 18 - ONE HIDES IN EVERY CHAMBER"},
    {"if": "_focus == 11", "text": "DIVE WITH {start_clock}S ON THE CLOCK - HEAT {heat}"},
    {"if": "running == 1", "text": "{_rt}S - PAR {_par}S"},
    {"if": "runs == 0", "text": "WALK INTO THE RED GATE TO DIVE"},
    {"text": "THE FOUNDRY - BEST DEPTH {_best_now}/15 - HEAT {heat}"},
]
ui = {
    "title": "REDLINE",
    "labels": {"clock": "Clock", "depth": "Depth", "bank": "Sparks", "streak": "Streak"},
    "counters": [{"var": "clock", "label": "CLOCK"}, {"var": "depth", "of": DEPTH_GOAL, "label": "DEPTH"}, {"var": "bank", "label": "SPARKS"},
                 {"var": "streak", "label": "STREAK"}],
    "objective": objective,
    "start": {"title": "REDLINE",
              "text": "THE REACTOR IS REDLINING. DIVE THROUGH ITS CHAMBERS BEFORE THE CLOCK BURNS DOWN. EVERY VENT BUYS TIME. "
                      "BEAT PAR FOR A STREAK. SPARKS ARE YOURS TO KEEP: SPEND THEM IN THE FOUNDRY. "
                      "WASD MOVE, MOUSE LOOK, SPACE JUMP. HOLD SPACE TO BUNNY HOP, STRAFE AND TURN IN THE AIR TO GO FASTER.",
              "button": "ENTER THE FOUNDRY"},
    "pause": "{bank:SPARK|SPARKS}  RELICS {relics}/18  ESCAPES {escapes}",
    "end": {
        "burnout": {"title": "BURNOUT", "text": "YOU REACHED DEPTH {depth} OF 15 AT HEAT {heat} (BEST {_best_now} CLEARED). +{run_sparks:SPARK|SPARKS} THIS RUN, {bank} BANKED.", "button": "BACK TO THE FOUNDRY"},
        "vented": {"title": "CORE VENTED", "text": "YOU ESCAPED AT HEAT {heat} IN {run_time}S. +{run_sparks:SPARK|SPARKS} THIS RUN. HEAT {heat_unlocked} IS OPEN.", "button": "BACK TO THE FOUNDRY"},
    },
}

# ------------------------------------------------------------------ sound
audio = {"music": {"day": "audio/foundry.json"}, "music_volume": 0.55,
         "layers": [{"score": "audio/run.json", "var": "running", "above": 0.5, "fade": 1.2, "volume": 0.75},
                    {"score": "audio/danger.json", "var": "_danger", "above": 0.5, "fade": 0.6, "volume": 0.7}],
         "duck": {"events": ["burn"], "depth": 0.55, "hold": 0.4, "release": 1.2}}

# ------------------------------------------------------------------ checks: every chamber is clearable at base speed, and the run loop works
sims = [routes.scenario(c) for c in chambers]
sims.append({"name": "hub: a dive starts a run in a tier-1 chamber", "players": [{"id": "p1", "spawn": "hub"}],
             "script": [{"player": "p1", "walk": "0,-12.6"}, {"player": "p1", "wait": 0.3}],
             "expect": [{"var": "running", "eq": 1}, {"var": "depth", "eq": 1}, {"var": "tier", "eq": 1}, {"event": "go", "count": 1}],
             "max_seconds": 8})
# walk up to the gate, then step through it (a walk aimed into the gate would keep walking toward the hub's coordinates after the teleport)
DIVE_WALK = [{"player": "p1", "walk": "0,-11.4"}, {"player": "p1", "hold": {"forward": 1, "yaw_deg": 0, "seconds": 0.25}}, {"player": "p1", "wait": 0.4}]
sims.append({"name": "run: the clock burns out", "players": [{"id": "p1", "spawn": "hub"}],
             "script": DIVE_WALK + [{"player": "p1", "wait": 30}],
             "expect": [{"ended": "burnout"}, {"var": "runs", "eq": 1}, {"var": "depth", "eq": 1}, {"var": "clock", "eq": 0}], "max_seconds": 45})
sims.append({"name": "run: a burn costs time and comes back to the chamber start", "players": [{"id": "p1", "spawn": "hub"}],
             "script": DIVE_WALK + [{"player": "p1", "hold": {"strafe": 1, "yaw_deg": 0, "seconds": 0.8}}, {"player": "p1", "wait": 1.5}],
             "expect": [{"var": "burns", "eq": 1}, {"event": "burn", "count": 1}, {"not_ended": True}], "max_seconds": 10})
dive_pick = pars.get("_dive")
if dive_pick:
    first = next(c for c in chambers if c.code == dive_pick)
    route = routes.scenario(first)["script"]
    # the runner's last steps walk to the gate's far side: after the vent teleports it, a walk would keep heading for the old chamber,
    # so stop at the last walk before the gate and step through it instead
    while route and "hold" not in route[-1]:
        route.pop()
    route += [{"player": "p1", "hold": {"forward": 1, "yaw_deg": 0, "seconds": 1.6}}, {"player": "p1", "wait": 0.5}]
    sims.append({"name": f"run: dive, clear the first chamber ({first.code}) and go deeper", "players": [{"id": "p1", "spawn": "hub"}],
                 "script": DIVE_WALK + route,
                 "expect": [{"event": f"vent_{first.code}", "count": 1}, {"event": "cleared", "count": 1}, {"event": "go", "count": 2},
                            {"var": "depth", "eq": 2}, {"var": "tier", "eq": 1}, {"no_event": "burn"}, {"not_ended": True}],
                 "max_seconds": 90})
sims.append({"name": "hub: no sparks, no upgrade", "players": [{"id": "p1", "spawn": "hub"}],
             "script": [{"player": "p1", "walk": "-6,7; -11.5,7"}, {"player": "p1", "wait": 0.3}],
             "expect": [{"var": "lvl_coolant", "eq": 0}, {"var": "_msg", "eq": MSG["need"]}, {"var": "_focus", "eq": 1}], "max_seconds": 8})
sims.append({"name": "hub: falling off the Foundry is free", "players": [{"id": "p1", "spawn": "hub"}],
             "script": [{"player": "p1", "walk": "15.0,4"}, {"player": "p1", "hold": {"strafe": 1, "yaw_deg": 0, "seconds": 0.6}}, {"player": "p1", "wait": 1.2}],
             "expect": [{"event": "burn", "min": 1}, {"player": "p1", "near": [0, 12], "tol": 3.0}], "max_seconds": 8})

scene = {
    "schema_version": 1,
    "meta": {"fps": 30, "duration": 4.0, "resolution": [1280, 720]},
    "background": {"sky_top": "#12040a", "sky_bottom": "#7a1e0c"},
    "ambient": {"color": "#ffd9c4", "intensity": 0.34},
    # the scene camera is only for pictures (`frame`, the download site's thumbnail): it looks up the Stairwell chamber
    "camera": {"fov": 70, "position": [1043, 12, -1020], "target": [1040, 5, -1060], "far": 220},
    "player": {"humans_play_as": "human", "mode": "peaceful", "fov": FOV, "walk_speed": SPEED, "sprint_speed": SPEED, "jump_speed": JUMP, "gravity": GRAVITY,
               "acceleration": GROUND_ACCEL, "air_acceleration": AIR_ACCEL, "friction": FRICTION, "max_speed": MAX_SPEED},
    "hud": {"show_rules_vars": False, "show_events": False, "show_combat": False, "show_scoreboard": False, "show_round": False, "show_ping": False},
    "ui": ui,
    "audio": audio,
    "persist": S.persist,
    "lights": [{"id": "sun", "type": "directional", "direction": [-0.35, -1.0, 0.25], "color": "#ffe2c8", "intensity": 1.6, "cast_shadows": True, "shadow_radius": 28, "shadow_follow": True}] + S.lights,
    "spawns": S.spawns,
    "jump_pads": S.pads,
    "zones": S.zones,
    "vars": S.vars,
    "rules": S.rules,
    "checks": {"sim": sims},
    "objects": S.objects,
}

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "maps/main.json"
    with open(out, "w") as f:
        json.dump(scene, f, indent=1)
    print(f"wrote {out}: {len(S.objects)} objects, {len(S.rules)} rules, {len(S.vars)} vars ({len(S.persist)} kept), {len(chambers)} chambers, {len(S.zones)} zones")
    if "--pars" in sys.argv:
        routes.measure_pars(out, chambers, PARS_FILE)
