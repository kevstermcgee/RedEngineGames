#!/usr/bin/env python3
"""Draw the pictures of wiki pages from the `shot` each entry carries, so a page can be redrawn whenever a game or the engine changes.

  python3 site/wiki_build.py SLUG [SLUG...] [--engine PATH] [--sheet OUT.jpg]
  python3 site/wiki_build.py --all [--engine PATH] [--redraw]

A page's `scene_patch` {"drop": ["weapons.revolver", ...]} draws from a temporary copy of the scene without those keys, for a game whose data the
current engine refuses (the page itself should say so). Only missing pictures, and pictures whose `shot` changed (`drawn_from` records it), are drawn unless --redraw (a playtest does not replay exactly, so a captioned picture is kept until asked).

The engine is `--engine`, else $RED_ENGINE_EXE, else `red_engine2` on PATH. Needs Pillow (JPEG and 2D sprite portraits).
Every character and gallery entry of `site/wiki/<slug>/wiki.json` that has a `shot` gets its picture drawn to the file its `image` names (a `.jpg` name is
saved as JPEG); an entry without `image` gets one (`c1.jpg`, `g1.png`, ...). Kinds of shot:

  {"frame": {t, scenario, eye, at, fov, hide, hour, cut_above, seed, play, song_journey}}  the game itself (song_journey: a scene whose music journey to play to it)
                                                                        , as `red_engine2 frame` draws it (a 2D game is drawn at 3x its screen);
                                                                         "crop": [l, t, r, b] (fractions) keeps and enlarges part of it
  {"sprite": NAME | [NAMES], "index": 0, "scale": 0}                     a 2D game's own pixel art, from its `sprites`, enlarged without blur
  {"prefab": NAME}                                                       a 3D game's own prefab, as `red_engine2 catalog --sheet` draws it (label band cropped)
  {"studio": [OBJECTS], "eye": "x,y,z", "at": "x,y,z", "fov": 40}         objects (e.g. a `humanoid`) in a small lit room with the game's prefabs and style
  {"file": PATH}                                                         an existing picture in the repository
  {"playtest": NAME}                                                     the picture the page's `playtest` script took with {"shot": NAME, "camera": ...}: the real
                                                                         game running headless (rules, HUD, cards), via `red_engine2 playtest --script`

`--sheet` writes one contact sheet of everything drawn, for a person to check that each picture shows what its caption says.
Then `python3 site/wiki.py`'s rules run on the page (`site/generate.py` runs them again for the site).
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "distribution"))
sys.path.insert(0, str(REPO / "site"))
import release_tool as rt  # noqa: E402
import wiki  # noqa: E402

try:
    from PIL import Image, ImageDraw
except ImportError:  # only the shots that need it fail
    Image = None

SIZE_3D = (960, 540)
JPEG_QUALITY = 84


def scene_of(slug: str) -> Path:
    for p in rt.load_playables():
        if p["slug"] == slug:
            for arg in p.get("arguments", []):
                if arg.endswith(".json"):
                    return REPO / arg.removeprefix("content/")
    raise SystemExit(f"{slug}: not a listed game (or it has no scene argument)")


def is_2d(scene: Path) -> bool:
    return scene.name.endswith(".game2d.json")


def run(engine: str, args: list[str]) -> str:
    p = subprocess.run([engine] + args, capture_output=True, text=True, timeout=600, cwd=REPO)
    if p.returncode:
        raise RuntimeError(f"{' '.join(args[:3])}: {(p.stderr or p.stdout).strip()[-400:]}")
    return p.stdout


def save(img, out: Path):
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() in (".jpg", ".jpeg"):
        img.convert("RGB").save(out, quality=JPEG_QUALITY, optimize=True, progressive=True)
    else:
        img.save(out, optimize=True)


def need_pil():
    if Image is None:
        raise RuntimeError("this shot needs Pillow (pip install pillow)")


_SONGS = {}


def journey_song(engine, scene_rel, sections):
    """`red_engine2 audio journey SCENE --sections N --out song.wav`, once per build."""
    key = (scene_rel, sections)
    if key not in _SONGS:
        out = Path(tempfile.mkdtemp(prefix="wiki-song-")) / "song.wav"
        run(engine, ["audio", "journey", str(REPO / scene_rel), "--sections", str(sections), "--out", str(out)])
        _SONGS[key] = out
    return _SONGS[key]


def draw_frame(engine, scene, shot, out):
    opts = shot["frame"]
    if is_2d(scene):
        view = json.loads(scene.read_text()).get("view", {})
        size = (int(view.get("width", 320)) * 3, int(view.get("height", 240)) * 3)
    else:
        size = SIZE_3D
    args = ["frame", str(scene), "", "--size", f"{size[0]}x{size[1]}"]
    for k in ("t", "scenario", "eye", "at", "fov", "hour", "cut_above", "seed", "play"):
        if opts.get(k) is not None:
            args += [f"--{k.replace('_', '-')}", str(opts[k])]
    if opts.get("song_journey"):   # a song for a game that listens to music: the music journey of a scene, rendered by the engine (nothing to commit)
        args += ["--song", str(journey_song(engine, opts["song_journey"], opts.get("sections", 1)))]
    for h in ([opts["hide"]] if isinstance(opts.get("hide"), str) else opts.get("hide") or []):
        args += ["--hide", h]
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "f.png"
        args[2] = str(png)
        run(engine, args)
        crop = shot.get("crop")   # [left, top, right, bottom] as fractions of the picture: a close-up, enlarged without blur
        if crop:
            need_pil()
            img = Image.open(png)
            w, h = img.size
            box = (int(crop[0] * w), int(crop[1] * h), int(crop[2] * w), int(crop[3] * h))
            part = img.crop(box)
            k = max(1, min(SIZE_3D[0] // part.width, SIZE_3D[1] // part.height))
            save(part.resize((part.width * k, part.height * k), Image.NEAREST if is_2d(scene) else Image.LANCZOS), out)
        else:
            finish(png, out)


def finish(png: Path, out: Path, crop=None):
    """Keep a PNG as it is, or convert it (and crop it) with Pillow."""
    if crop is None and out.suffix.lower() == ".png":
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(png, out)
        return
    need_pil()
    img = Image.open(png)
    if crop:
        img = img.crop(crop)
    save(img, out)


def draw_sprite(scene, shot, out):
    need_pil()
    game = json.loads(scene.read_text())
    names = shot["sprite"] if isinstance(shot["sprite"], list) else [shot["sprite"]]
    bg = game.get("view", {}).get("background", "#202020")
    tiles = []
    for name in names:
        sp = game["sprites"][name]
        rows = sp["frames"][shot.get("index", 0)] if "frames" in sp else sp["rows"]
        pal = sp.get("palette", {})
        h, w = len(rows), max(len(r) for r in rows)
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch in pal:
                    im.putpixel((x, y), Image.new("RGB", (1, 1), pal[ch]).getpixel((0, 0)) + (255,))
        tiles.append(im)
    tallest = max(t.height for t in tiles)
    scale = shot.get("scale") or max(1, min(300 // tallest, 900 // max(1, sum(t.width for t in tiles) + 4 * (len(tiles) - 1))))
    gap = 4 * scale
    width = sum(t.width * scale for t in tiles) + gap * (len(tiles) - 1)
    canvas = Image.new("RGB", (max(480, width + 80), max(360, tallest * scale + 80)), bg)
    x = (canvas.width - width) // 2
    for t in tiles:
        big = t.resize((t.width * scale, t.height * scale), Image.NEAREST)
        canvas.paste(big, (x, (canvas.height - big.height) // 2 + (tallest * scale - big.height) // 2), big)
        x += big.width + gap
    save(canvas, out)


def draw_prefab(engine, scene, shot, out):
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "p.png"
        own = shot["prefab"] in json.loads(scene.read_text()).get("prefabs", {})   # the game's own prefab: never the engine asset of a similar name
        run(engine, ["catalog", shot["prefab"], "--scene", str(scene), "--sheet", str(png), "--cols", "1"] + (["--local"] if own else []))
        need_pil()
        w, h = Image.open(png).size
        finish(png, out, crop=(0, 30, w, h - 30))   # the sheet's name and size bands


def draw_studio(engine, scene, shot, out):
    src = json.loads(scene.read_text())
    room = {k: src[k] for k in ("prefabs", "style", "materials") if k in src}
    room.update({
        "camera": {"fov": shot.get("fov", 40), "position": [float(v) for v in shot.get("eye", "0,1.6,3.2").split(",")], "target": [float(v) for v in shot.get("at", "0,1,0").split(",")]},
        "lights": [{"id": "key", "type": "directional", "direction": [-0.4, -1, -0.5], "intensity": 1.1, "cast_shadows": True}],
        "spawns": [{"id": "start", "position": [0, 0, 8], "yaw_deg": 0}],
        "objects": [{"id": "floor", "type": "box", "position": [0, -0.05, 0], "scale": [12, 0.1, 12], "material": {"color": shot.get("floor", [0.32, 0.34, 0.38])}}] + shot["studio"],
    })
    if isinstance(src.get("sky"), (dict, str)):
        room["sky"] = src["sky"]
    with tempfile.TemporaryDirectory(dir=scene.parent) as tmp:   # beside the scene, so its relative paths still resolve
        path = Path(tmp) / "studio.json"
        path.write_text(json.dumps(room))
        png = Path(tmp) / "s.png"
        run(engine, ["frame", str(path), str(png), "--size", f"{SIZE_3D[0]}x{SIZE_3D[1]}"])
        finish(png, out)


class Playtest:
    """The page's `playtest` scripts, each run once in the real game (`red_engine2 playtest`): rules, HUD and cards as a player sees them.
    `playtest` is {"script": {...}} (one run) or {RUN: {"script": {...}}, ...} (several); a shot names a picture its `shot` steps took: "NAME" or "RUN/NAME"."""

    def __init__(self, engine, scene, spec):
        self.engine, self.scene = engine, scene
        self.runs = {"": spec} if "script" in spec else spec
        self.dirs = {}

    def picture(self, ref):
        run, _, name = ref.rpartition("/")
        if run not in self.runs:
            raise RuntimeError(f"no playtest run `{run}`")
        if run not in self.dirs:
            d = self.dirs[run] = Path(tempfile.mkdtemp(prefix="wiki-playtest-"))
            (d / "script.json").write_text(json.dumps(self.runs[run]["script"]))
            # exit 1 only means an expectation or a remote player failed; the pictures are what matter here, and each is checked below
            subprocess.run([self.engine, "playtest", str(self.scene), "--script", str(d / "script.json"), "--out", str(d / "out"),
                            "--size", f"{SIZE_3D[0]}x{SIZE_3D[1]}"], capture_output=True, text=True, timeout=900, cwd=REPO)
        found = sorted((self.dirs[run] / "out" / "shots").glob(f"*-{name}.png"))
        if not found:
            raise RuntimeError(f"the playtest {run or 'run'} took no picture named `{name}`")
        return found[-1]

    def close(self):
        for d in self.dirs.values():
            shutil.rmtree(d, ignore_errors=True)


def draw(engine, scene, shot, out, playtest=None):
    if "playtest" in shot:
        if playtest is None:
            raise RuntimeError("a `playtest` shot needs the page's `playtest` script")
        finish(playtest.picture(shot["playtest"]), out)
    elif "frame" in shot:
        draw_frame(engine, scene, shot, out)
    elif "sprite" in shot:
        draw_sprite(scene, shot, out)
    elif "prefab" in shot:
        draw_prefab(engine, scene, shot, out)
    elif "studio" in shot:
        draw_studio(engine, scene, shot, out)
    elif "file" in shot:
        src = REPO / shot["file"]
        if src.suffix.lower() == out.suffix.lower():
            shutil.copy(src, out)
        else:
            need_pil()
            save(Image.open(src), out)
    else:
        raise RuntimeError(f"unknown shot {sorted(shot)}")


def build(slug: str, engine: str, redraw: bool = False) -> tuple[list[str], list[tuple[str, Path]]]:
    """Draw one page's pictures that are missing (all of them with `redraw`). Returns (problems, [(caption, picture)]).
    A playtest is not exactly repeatable (physics, timing), so a picture once drawn and captioned is kept unless asked: after `--redraw`, look again."""
    folder = REPO / "site" / "wiki" / slug
    path = folder / "wiki.json"
    data = json.loads(path.read_text())
    scene = scene_of(slug)
    patched = None
    if data.get("scene_patch"):   # pictures only: a temporary copy of the scene with keys the current engine refuses removed (the page should say why)
        src = json.loads(scene.read_text())
        for dotted in data["scene_patch"].get("drop", []):
            parent = src
            keys = dotted.split(".")
            for k in keys[:-1]:
                parent = parent.get(k, {})
            parent.pop(keys[-1], None)
        patched = scene.parent / f".wiki-{scene.name}"
        patched.write_text(json.dumps(src))
        scene = patched
    playtest = Playtest(engine, scene, data["playtest"]) if data.get("playtest") else None
    default_ext = ".png" if is_2d(scene) else ".jpg"
    drawn, problems = [], []
    taken = {e.get("image") for k in ("characters", "gallery") for e in data.get(k, [])}
    for key, prefix in (("characters", "c"), ("gallery", "g")):
        for i, entry in enumerate(data.get(key, [])):
            shot = entry.get("shot")
            if not shot:
                continue
            fresh = not entry.get("image")
            if fresh:   # a new entry: the first free name, so inserting one never takes another's picture
                ext = ".png" if "sprite" in shot else default_ext
                n = i + 1
                while f"{prefix}{n}{ext}" in taken:
                    n += 1
                entry["image"] = f"{prefix}{n}{ext}"
                taken.add(entry["image"])
            out = folder / entry["image"]
            key = hashlib.sha1(json.dumps(shot, sort_keys=True).encode()).hexdigest()[:12]
            if out.is_file() and not redraw and not fresh and entry.setdefault("drawn_from", key) == key:   # a picture without a record predates it: taken as current
                drawn.append((entry.get("name") or entry.get("caption", ""), out))
                continue
            try:
                draw(engine, scene, shot, out, playtest)
                entry["drawn_from"] = key
                drawn.append((entry.get("name") or entry.get("caption", ""), out))
            except (RuntimeError, KeyError, subprocess.TimeoutExpired, OSError) as e:
                problems.append(f"{entry['image']}: {e}")
    if playtest:
        playtest.close()
    if patched:
        patched.unlink(missing_ok=True)
    digests = [hashlib.sha256((folder / g["image"]).read_bytes()).hexdigest() for g in data.get("gallery", []) if (folder / g.get("image", "-")).is_file()]
    if len(set(digests)) != len(digests):
        problems.append("two gallery pictures are identical: change a shot")
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    meta = json.loads((REPO / "site" / "games-meta.json").read_text())
    problems += wiki.problems(data, meta.get(slug, {}).get("author", "human"), folder)
    used = {e.get("image") for k in ("characters", "gallery") for e in data.get(k, [])} | {"wiki.json"}
    for f in folder.iterdir():   # a picture no entry names any more
        if f.name not in used:
            f.unlink()
    return problems, drawn


def sheet(items, out: Path):
    need_pil()
    cols, tw, th = 4, 400, 250
    rows = (len(items) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * tw, rows * (th + 22)), "#111")
    d = ImageDraw.Draw(canvas)
    for i, (label, pic) in enumerate(items):
        im = Image.open(pic).convert("RGB")
        im.thumbnail((tw - 6, th - 6))
        x, y = (i % cols) * tw, (i // cols) * (th + 22)
        canvas.paste(im, (x + 3, y + 3))
        d.text((x + 4, y + th + 4), label[:60], fill="#eee")
    save(canvas, out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("slugs", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--engine", default=os.environ.get("RED_ENGINE_EXE") or shutil.which("red_engine2") or "red_engine2")
    ap.add_argument("--sheet")
    ap.add_argument("--redraw", action="store_true", help="draw every picture again, not only the missing ones (then look at them: a playtest may play out differently)")
    a = ap.parse_args()
    slugs = sorted(p.name for p in (REPO / "site" / "wiki").iterdir() if (p / "wiki.json").is_file()) if a.all else a.slugs
    bad, drawn = 0, []
    for slug in slugs:
        problems, pics = build(slug, a.engine, a.redraw)
        drawn += [(f"{slug}: {c}", p) for c, p in pics]
        print(f"{slug}: {len(pics)} picture(s)" + ("" if not problems else "\n  " + "\n  ".join(problems)))
        bad += bool(problems)
    if a.sheet and drawn:
        sheet(drawn, Path(a.sheet))
        print(f"contact sheet: {a.sheet}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
