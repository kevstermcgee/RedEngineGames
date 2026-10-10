#!/usr/bin/env python3
"""python3 tools/first_burn.py a2 a4 ...: for each chamber, the runner's last second before its first burn, in chamber coordinates."""
import json, os, subprocess, sys, tempfile

cli = os.environ.get("RED_CLI", "scripts/red")
scene = json.load(open("maps/main.json"))
for code in sys.argv[1:]:
    sc = next(s for s in scene["checks"]["sim"] if s["name"].startswith(f"chamber {code}:"))
    sp = next(s for s in scene["spawns"] if s["id"] == f"{code}_cp0")
    ox, oz = sp["position"][0], sp["position"][2]
    tr = os.path.join(tempfile.mkdtemp(), "t.json")
    out = subprocess.run([cli, "sim", "maps/main.json", "--only", sc["name"], "--trace", tr, "--dump-every", "3"], capture_output=True, text=True).stdout
    t = json.load(open(tr))
    burns = [e[0] for e in t["events"] if e[2] == "burn"]
    print(next((l for l in out.splitlines() if l.startswith(("PASS", "FAIL"))), "?"))
    if not burns:
        last = t["dumps"][-1]["players"][0]
        print(f"   no burn; ended at x={last[1] - ox:.2f} z={last[3] - oz:.2f} y={last[2]:.2f}")
        continue
    b = burns[0]
    rows = [d for d in t["dumps"] if b - 75 <= d["tick"] <= b]
    for d in rows[::2]:
        p = d["players"][0]
        print(f"   t={d['tick'] / 60:5.2f} x={p[1] - ox:6.2f} z={p[3] - oz:7.2f} y={p[2]:5.2f} v=({p[7]:5.2f},{p[8]:6.2f})")
