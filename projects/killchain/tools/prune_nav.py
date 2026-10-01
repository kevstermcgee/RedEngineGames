#!/usr/bin/env python3
"""Keeps only the nav edges the real movement can walk (both directions), and only the nodes still connected to the largest island.
Run after gen_map.py: python3 tools/prune_nav.py maps/main.json  (uses red_engine2 from $RED_ENGINE2 or PATH)."""
import json, os, subprocess, sys
path = sys.argv[1]
exe = os.environ.get("RED_ENGINE2", "red_engine2")
for round_ in range(4):
    scene = json.load(open(path))
    nav = scene["nav"]
    out = subprocess.run([exe, "--json", "nav", path], capture_output=True, text=True).stdout
    data = json.loads(out)["data"]
    bad = {(t["from"], t["to"]) for t in data["trials"] if not t["ok"]}
    badnodes = {str(n).split("`")[1] if "`" in str(n) else str(n.get("node", "")) for n in data.get("node_problems", [])}
    edges = [e for e in nav["edges"] if e[0] not in badnodes and e[1] not in badnodes and (e[0], e[1]) not in bad and (e[1], e[0]) not in bad]
    # largest connected component
    adj = {}
    for a, b, *_ in edges:
        adj.setdefault(a, set()).add(b); adj.setdefault(b, set()).add(a)
    seen, best = set(), set()
    for n in adj:
        if n in seen: continue
        comp, stack = set(), [n]
        while stack:
            x = stack.pop()
            if x in comp: continue
            comp.add(x); stack.extend(adj[x] - comp)
        seen |= comp
        if len(comp) > len(best): best = comp
    first = nav["nodes"][0]["id"]
    nav["nodes"] = [n for n in nav["nodes"] if n["id"] in best]
    nav["edges"] = [e for e in edges if e[0] in best and e[1] in best]
    json.dump(scene, open(path, "w"), indent=1)
    print(f"round {round_}: {len(nav['nodes'])} nodes, {len(nav['edges'])} edges, {len(bad)} failing trials removed, {data['problems']} problems before")
    if not bad and not data["unreachable"] and not data["traps"]:
        break
