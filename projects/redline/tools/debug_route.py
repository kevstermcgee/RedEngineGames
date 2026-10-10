#!/usr/bin/env python3
"""Debug one chamber's scripted run: python3 tools/debug_route.py a1 [--every 6]

Runs the chamber's `checks.sim` scenario with a trace and prints the runner's path in the chamber's own coordinates (x across, z along the
course, y height) with the speed, and where every burn happened, so a failing jump is easy to see.
"""
import json, math, os, subprocess, sys, tempfile

code = sys.argv[1]
every = int(sys.argv[sys.argv.index("--every") + 1]) if "--every" in sys.argv else 6
cli = os.environ.get("RED_CLI", "scripts/red")
scene = json.load(open("maps/main.json"))
sc = next(s for s in scene["checks"]["sim"] if s["name"].startswith(f"chamber {code}:"))
spawn = next(s for s in scene["spawns"] if s["id"] == f"{code}_cp0")
ox, oz = spawn["position"][0], spawn["position"][2]
tmp = tempfile.mkdtemp()
trace = os.path.join(tmp, "t.json")
res = subprocess.run([cli, "sim", "maps/main.json", "--only", sc["name"], "--trace", trace, "--dump-every", str(every)], capture_output=True, text=True)
print("\n".join(l for l in res.stdout.splitlines() if l.startswith(("PASS", "FAIL", "  [")))[:2000])
t = json.load(open(trace))
burns = [e["tick"] for e in t["events"] if e.get("name") == "burn"] if isinstance(t["events"], list) and t["events"] and isinstance(t["events"][0], dict) else []
if not burns:
    burns = [e[0] if isinstance(e, list) else e for e in t["events"] if (isinstance(e, list) and "burn" in e)]
last = None
first_burn = burns[0] if burns else None
for d in t["dumps"]:
    tick = d["tick"]
    if first_burn and tick > first_burn + 60:
        break
    p = d["players"][0]
    x, y, z = p[1], p[2], p[3]
    sp = math.hypot(p[7], p[8]) if len(p) > 8 else 0
    print(f"t={tick / 60:6.2f}  x={x - ox:6.2f}  z={z - oz:7.2f}  y={y:5.2f}  speed={sp:5.2f}")
print("burns at ticks:", burns[:10])
if "--script" in sys.argv:
    for st in sc["script"]:
        if "walk" in st:
            x, z = map(float, st["walk"].split(","))
            print(f"  walk {x - ox:6.2f} {z - oz:7.2f}")
        elif "hold" in st:
            print("  hold", st["hold"])
        else:
            print(" ", st)
    for o in scene["objects"]:
        if o["id"].startswith(code + "_") and "." not in o["id"] and o["type"] == "box" and isinstance(o["position"], list):
            x, y, z = o["position"]; w, h, d = o["size"]
            print(f"  {o['id']:12s} x {x - ox - w / 2:6.1f}..{x - ox + w / 2:6.1f}  z {z - oz - d / 2:7.1f}..{z - oz + d / 2:7.1f}  top {y + h / 2:5.2f}")
