"""Rebuild the sandbox from the engine catalogue. --check detects drift without writing."""
import argparse
import copy
import json
import math
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ARGS = argparse.ArgumentParser(description=__doc__)
ARGS.add_argument("--check", action="store_true")
ARGS.add_argument("--engine", type=Path)
OPT = ARGS.parse_args()
ENGINE = (OPT.engine or ROOT / json.loads((ROOT / "game.json").read_text())["engine"]["path"]).resolve()
CLI = ENGINE / "target/debug/red_engine2.exe"
if not CLI.exists():
    CLI = ENGINE / "target/debug/red_engine2"
GENERATED = []
def save(name, value):
    text = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    path = ROOT / name
    GENERATED.append(name)
    if OPT.check:
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            raise SystemExit(f"stale sandbox output: {name}; run scripts/generate.py")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

def box(id, p, size, color, **extra):
    return dict(id=id, type="box", position=p, size=size, material={"color":color,"roughness":0.8}, **extra)
def shape(id, kind, p, color, **extra):
    return dict(id=id, type=kind, position=p, material={"color":color,"roughness":0.65}, **extra)
def prop(id, kind, x, z, y=0):
    colors={"crate":"#b88b58","barrel":"#648099","chair":"#bb8060","traffic_cone":"#e78836","dining_table":"#9e7653","tree_oak":"#56805b"}
    return dict(id=id,type="prop",prop=kind,position=[x,y,z],material={"color":colors.get(kind,"#87949c")})
def prefab(id, name, x, z, y=0):
    return dict(id=id,type="prefab",prefab=name,position=[x,y,z])

# Local reusable assets are embedded into the committed maps; no runtime file dependencies.
LOCAL = [
 {"name":"sandbox_crystal","tags":["sandbox","outdoor","alien"],"desc":"Cluster of three faceted mineral spires.","collide":False,"objects":[
    shape("spire_a","cone",[-0.28,0.75,0],"#7ce1e0",radius=0.3,height=1.5),
    shape("spire_b","cone",[0.24,0.5,0.12],"#b6a0eb",radius=0.22,height=1.0),
    shape("spire_c","cone",[0,0.33,-0.28],"#5398c4",radius=0.19,height=0.66)]},
 {"name":"sandbox_mushroom","tags":["sandbox","outdoor","fantasy"],"desc":"Broad colourful mushroom for gardens.","collide":False,"objects":[
    shape("stem","cylinder",[0,0.38,0],"#eee0c1",radius=0.16,height=0.76),
    shape("cap","sphere",[0,0.78,0],"#c2609b",radius=0.7,scale=[1,0.36,1]),
    shape("spot","sphere",[0.25,1.01,0.12],"#ffdbb5",radius=0.12,scale=[1,0.2,1])]},
 {"name":"sandbox_frontier_sign","tags":["sandbox","outdoor","western"],"desc":"Freestanding wooden direction marker.","objects":[
    box("post",[0,0.75,0],[0.15,1.5,0.15],"#795737"),
    box("board",[0,1.4,0],[1.5,0.35,0.16],"#cb9f63")]},
 {"name":"sandbox_workbench","tags":["sandbox","furniture","workshop"],"desc":"Heavy workbench with open shelf and a vice.","objects":[
    box("top",[0,0.95,0],[2.4,0.16,0.9],"#b98b58"),
    box("shelf",[0,0.32,0],[2.2,0.1,0.7],"#4a6770"),
    *[box(f"leg{i}",[x,0.45,z],[0.12,0.9,0.12],"#43616b") for i,(x,z) in enumerate([(-1,-0.3),(1,-0.3),(-1,0.3),(1,0.3)])],
    box("vice",[0.8,1.1,0.1],[0.3,0.2,0.35],"#506b88")]},
 {"name":"sandbox_beacon","tags":["sandbox","lamp","science"],"desc":"Solar research beacon with a luminous-looking blue cap.","objects":[
    box("base",[0,0.1,0],[0.8,0.2,0.8],"#304b63"),
    shape("pole","cylinder",[0,1.1,0],"#526f89",radius=0.08,height=2),
    shape("orb","sphere",[0,2.15,0],"#7ee6ee",radius=0.28,collide=False)]},
 {"name":"sandbox_target","tags":["sandbox","test","range"],"desc":"Freestanding three-ring target with solid rectangular backing.","objects":[
    box("foot",[0,0.05,0],[0.8,0.1,0.5],"#3c4d5c"),
    box("post",[0,0.8,0],[0.1,1.6,0.1],"#596775"),
    box("back",[0,1.5,0],[1.1,1.1,0.12],"#d4d7ca"),
    shape("outer","cylinder",[0,1.5,0.08],"#b7444f",radius=0.45,height=0.035,rotation=[90,0,0],collide=False),
    shape("middle","cylinder",[0,1.5,0.11],"#eee2bb",radius=0.3,height=0.035,rotation=[90,0,0],collide=False),
    shape("bull","cylinder",[0,1.5,0.14],"#b7444f",radius=0.13,height=0.035,rotation=[90,0,0],collide=False)]}
]
save("assets/gameplay.json",LOCAL)
catalog=json.loads(subprocess.check_output([str(CLI),"catalog","--json","--library",str(ROOT/"assets/gameplay.json")],text=True,encoding="utf-8"))["data"]
if any(a.get("error") for a in catalog):
    raise SystemExit("Catalogue contains expansion errors")

def scene(name,w=48,d=40,color="#536571",sky="#253c59"):
    z=d/2-4
    objects=[box("floor",[0,-0.1,0],[w,0.2,d],color),
      box("wall_w",[-w/2,1.5,0],[0.3,3,d],"#7d8e9c"),
      box("wall_e",[w/2,1.5,0],[0.3,3,d],"#7d8e9c"),
      box("wall_n",[0,1.5,-d/2],[w,3,0.3],"#7d8e9c"),
      box("wall_s",[0,1.5,d/2],[w,3,0.3],"#7d8e9c")]
    return {"x-sandbox":{"name":name,"source":"scripts/generate.py"},
      "meta":{"fps":60,"duration":6,"resolution":[1280,720]},
      "background":{"sky_top":sky,"sky_bottom":"#cad8df"},
      "ambient":{"color":"#ffffff","intensity":0.65},
      "camera":{"fov":80,"position":[0,1.7,z],"target":[0,1.5,z-10]},
      "post":{"ao":0.5,"outline":0.3},
      "player":{"walk_speed":4.5,"sprint_speed":7.5,"jump_speed":5.5},
      "weapons":{"starting":"pistol"},
      "lights":[{"id":"sun","type":"directional","direction":[-0.5,-1,-0.3],"color":"#fff0db","intensity":1.1,"cast_shadows":True,"shadow_center":[0,0,0],"shadow_radius":max(w,d)}],
      "prefabs":LOCAL,
      "spawns":[{"id":"entry","position":[0,0,z],"yaw_deg":0,"group":"sandbox"}],
      "zones":[{"id":"space","rect":[-w/2+0.3,-d/2+0.3,w/2-0.3,d/2-0.3],"y":0,"kind":"room"}],
      "checks":{"lint":{"max_errors":0,"max_warnings":0},"walk":[{"name":"central aisle","from":[0,z],"to":[0,-d/2+4],"auto":True}],"objects":{"min_count":5}},
      "objects":objects}
MAPS=[]
def write_map(slug,s):
    name=f"maps/{slug}.json"
    save(name,s); MAPS.append(name)

# Arrival hub: six model stands, freely movable test props, and firing targets.
hub=scene("RedEngineSandbox / Arrival Hall",48,40,"#4a5a6d")
for i,(style,color) in enumerate([("human","#b64d50"),("rat","#7b6a5d"),("wizard","#6250ae"),("cowboy","#9b6d46"),("alien","#dba84a"),("robot","#469caf")]):
    x=-17+i*6.8
    hub["objects"].append(box(f"stand_{style}",[x,0.15,-12],[3.2,0.3,3.2],"#273647"))
    hub["objects"].append(dict(id=f"character_{style}",type="rat" if style=="rat" else "humanoid",position=[x,0.3,-12],material={"color":color},**({} if style=="rat" else {"style":style,"pose":{"l_shoulder":[0,0,-8],"r_shoulder":[0,0,8]}})))
for i in range(4):
    hub["objects"].append(prefab(f"weapon_target_{i}","sandbox_target",8+i*3,-2))
for i,kind in enumerate(["crate","barrel","chair","traffic_cone"]):
    hub["objects"].append(prop(f"physics_try_{kind}",kind,-16+i*3,3))
for x in [-20,20]:
    hub["objects"].append(prefab(f"arrival_beacon_{x}","sandbox_beacon",x,12))
write_map("00-arrival-hub",hub)

# Every catalogue entry gets a full-size, identified exhibit. Page size bounds scene/render cost.
inventory=[]
groups={}
for asset in catalog: groups.setdefault(asset["category"],[]).append(asset)
for category,entries in sorted(groups.items()):
    for page in range(math.ceil(len(entries)/20)):
        batch=entries[page*20:(page+1)*20]
        s=scene(f"Asset Gallery / {category} / {page+1}",40,52,"#52616c")
        slug=f"gallery-{category}-{page+1:02}"
        for index,asset in enumerate(batch):
            x=-15+(index%4)*10
            z=16-(index//4)*9
            item=copy.deepcopy(asset["instantiation"]["object"])
            minimum=asset["geometry"]["bounds_m"]["min"]
            maximum=asset["geometry"]["bounds_m"]["max"]
            item["id"]="asset_"+asset["name"]
            if asset["name"] in ["bonsai","fruit_bowl","lamp_floor"]:
                item["collide"]=False
                item["x-display-note"]="Visual exhibit: the source asset has a low overhang that fails player headroom checks."
            item["position"]=[x-(minimum[0]+maximum[0])/2,0.12-minimum[1],z-(minimum[2]+maximum[2])/2]
            if asset["mount"]=="wall":
                item["position"][1]+=1.0
                s["objects"].append(box("display_panel_"+asset["name"],[x,1.5,z-0.25],[max(2,asset["size"][0]+0.3),3,0.15],"#a6afb0"))
            s["objects"].append(box("plinth_"+asset["name"],[x,0.06,z],[8,0.12,7],"#354753"))
            s["objects"].append(item)
            inventory.append({"asset":asset["name"],"map":f"maps/{slug}.json","object":item["id"],"position":item["position"],"description":asset["desc"],"size_m":asset["size"]})
        write_map(slug,s)

# General-purpose environment 1: connected main street, six enterable frontier buildings, back alleys.
town=scene("Frontier Crossroads",64,56,"#b19a75","#e1b782")
town["objects"].append(box("main_street",[0,0.006,0],[10,0.012,54],"#897f73",collide=False))
for side in [-1,1]:
    for row,z in enumerate([-16,0,16]):
        x=side*18
        prefix=f"building_{side}_{row}"
        town["objects"] += [
          box(prefix+"_back",[x+side*5,2,z],[0.25,4,10],"#927b64"),
          box(prefix+"_north",[x,2,z-5],[10,4,0.25],"#ae9273"),
          box(prefix+"_south",[x,2,z+5],[10,4,0.25],"#ae9273"),
          box(prefix+"_front_a",[x-side*5,2,z-3.25],[0.25,4,3.5],"#b59671"),
          box(prefix+"_front_b",[x-side*5,2,z+3.25],[0.25,4,3.5],"#b59671"),
          box(prefix+"_lintel",[x-side*5,3.5,z],[0.25,1,3],"#85684f"),
          box(prefix+"_roof",[x,4.1,z],[10.6,0.2,10.6],"#725849"),
          prop(prefix+"_table","dining_table",x,z-1),
          prop(prefix+"_barrel","barrel",x+2,z+2)]
town["objects"] += [prefab("crossroads_sign","sandbox_frontier_sign",-7,20),prop("oak","tree_oak",27,21)]
town["checks"]["walk"] += [{"name":"enter frontier shop","from":[0,24],"to":[18,16],"auto":True},{"name":"back alley","from":[0,24],"to":[28,-22],"auto":True}]
write_map("frontier-crossroads",town)

# General-purpose environment 2: movement, prop interactions, stairs, precision aiming.
shop=scene("Workshop / Motion and Physics",52,44,"#597173")
for i in range(4):
    shop["objects"].append(prefab(f"bench_{i}","sandbox_workbench",-17,-12+i*7))
    shop["objects"].append(prop(f"loose_crate_{i}","crate",-12,-12+i*7))
    shop["objects"].append(prop(f"loose_barrel_{i}","barrel",-10,-12+i*7))
shop["objects"] += [
    box("test_deck",[13,1.4,-10],[12,0.2,8],"#496782"),
    {"id":"deck_stairs","type":"stairs","position":[13,0,-2],"rotation":[0,180,0],"width":4,"rise":1.5,"run":8,"steps":10,"material":{"color":"#819da8"}},
    box("stairs_guard_w",[10.8,1.5,-2],[0.2,3,8],"#73848b"),
    box("stairs_guard_e",[15.2,1.5,-2],[0.2,3,8],"#73848b"),
    box("deck_rail_n",[13,2,-14],[12,1,0.2],"#c0a15b"),
    box("deck_rail_e",[19,2,-10],[0.2,1,8],"#c0a15b"),
    box("deck_rail_w",[7,2,-10],[0.2,1,8],"#c0a15b")]
shop["objects"] += [box("deck_front_w",[8.85,2,-6],[3.7,1,0.2],"#c0a15b"),box("deck_front_e",[17.15,2,-6],[3.7,1,0.2],"#c0a15b")]
for i in range(5): shop["objects"].append(prefab(f"range_target_{i}","sandbox_target",6+i*3,15))
shop["checks"]["walk"].append({"name":"stairs to test deck","from":[0,18],"to":[13,-10,1.5],"auto":True})
write_map("workshop-motion-lab",shop)

# General-purpose environment 3: open, colourful outdoor exploration with alien/fantasy props.
garden=scene("Moon Garden",60,52,"#526b70","#242b64")
garden["player"].update({"jump_speed":7,"gravity":18})
for i,(x,z) in enumerate([(-23,-18),(-15,-12),(-22,0),(-16,12),(20,-18),(15,-6),(23,6),(18,16)]):
    garden["objects"].append(prefab(f"crystal_{i}","sandbox_crystal",x,z))
    garden["objects"].append(prefab(f"mushroom_{i}","sandbox_mushroom",x+3,z+3))
for i,(x,z) in enumerate([(-8,-17),(8,-17),(-8,15),(8,15)]):
    garden["objects"].append(prefab(f"beacon_{i}","sandbox_beacon",x,z))
for i,(x,z) in enumerate([(-12,0),(12,0)]):
    garden["objects"].append(box(f"launch_pad_{i}",[x,0.05,z],[3,0.1,3],"#b081cc"))
garden["jump_pads"]=[{"id":f"garden_pad_{i}","position":[x,0.1,z],"size":[3,3],"launch_speed":10} for i,(x,z) in enumerate([(-12,0),(12,0)])]
garden["objects"].append(shape("moon_arch_left","cylinder",[-5,2,-6],"#a0b2c1",radius=0.7,height=4))
garden["objects"].append(shape("moon_arch_right","cylinder",[5,2,-6],"#a0b2c1",radius=0.7,height=4))
garden["objects"].append(box("moon_arch_top",[0,4.2,-6],[11,0.5,1.5],"#a0b2c1"))
write_map("moon-garden",garden)

# Keep every engine example/recipe available as a clearly labelled reference map.
references=[]
for folder in ["examples","recipes"]:
    for path in sorted((ENGINE/folder).glob("*.json")):
        data=json.loads(path.read_text(encoding="utf-8-sig"))
        if "objects" not in data or "camera" not in data: continue
        data.setdefault("x-sandbox",{})["reference_source"]=f"{folder}/{path.name}"
        data.setdefault("checks",{"lint":{"max_errors":0}})
        if path.stem in ["hello_world","orbit_walk"]:
            # These source files are animation demonstrations, so give the sandbox copy a safe perimeter.
            extent=9 if path.stem=="hello_world" else 11
            for obj in data["objects"]:
                if obj["id"] in ["post","tree1","tree2"]: obj["collide"]=False
            data["objects"] += [
              box("sandbox_barrier_w",[-extent,1.5,0],[0.2,3,extent*2],"#536575"),
              box("sandbox_barrier_e",[extent,1.5,0],[0.2,3,extent*2],"#536575"),
              box("sandbox_barrier_n",[0,1.5,-extent],[extent*2,3,0.2],"#536575"),
              box("sandbox_barrier_s",[0,1.5,extent],[extent*2,3,0.2],"#536575")]
            data["x-sandbox"]["adaptation"]="Added a safe perimeter and disabled low decorative overhang collision for playable inspection."
        # Golden render comparisons belong to the source checkout; retain collision/simulation checks.
        data.get("checks",{}).pop("views",None)
        slug="reference-"+path.stem.replace("_","-")
        write_map(slug,data)
        references.append({"source":f"{folder}/{path.name}","map":f"maps/{slug}.json"})
for game in ["RedDM","RiftRaze"]:
    path=ENGINE.parent/game/"maps/main.json"
    if not path.exists():
        path=ROOT/f"maps/reference-{game.lower()}.json"
    if path.exists():
        data=json.loads(path.read_text(encoding="utf-8-sig"))
        write_map("reference-"+game.lower(),data)
        references.append({"source":f"../{game}/maps/main.json","map":f"maps/reference-{game.lower()}.json"})
front=["maps/00-arrival-hub.json","maps/frontier-crossroads.json","maps/workshop-motion-lab.json","maps/moon-garden.json"]
MAPS=front+[m for m in MAPS if m not in front]
config={"game":1,"name":"RedEngineSandbox","engine":{"path":json.loads((ROOT/"game.json").read_text())["engine"]["path"].replace(chr(92),"/")},
        "blueprints":[],"maps":MAPS,"server":{"map":MAPS[0],"port":27017,"spawn_group":"sandbox"}}
save("game.json",config)
save("asset-index.json",{"asset_count":len(inventory),"assets":inventory,"reference_maps":references})
print(f"RedEngineSandbox: {len(MAPS)} maps, {len(inventory)} catalogue assets, six characters.")
