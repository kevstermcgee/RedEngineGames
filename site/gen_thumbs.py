#!/usr/bin/env python3
"""Render one thumbnail PNG per launcher-catalog game into site/thumbs/.

Each game's map is rendered with the engine's `frame` command using the
scene's own camera, so the thumbnail shows what the player actually sees.
The map path for a slug comes from .release-games.json (the same source the
release workflow packages); slugs absent there fall back to the single JSON
in the game's directory.

Usage: python3 site/gen_thumbs.py [--engine PATH_TO_red_engine2] [--only SLUG]
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
THUMBS = REPO / "site" / "thumbs"
SIZE = "640x360"

# Launcher catalog slugs that differ from .release-games.json slugs.
SLUG_ALIASES = {"prop-hunt-yard": "prop-hunt"}


def map_path_for(slug: str, playables: dict) -> Path | None:
    entry = playables.get(SLUG_ALIASES.get(slug, slug))
    if entry:
        for arg in entry.get("arguments", []):
            if arg.endswith(".json"):
                return REPO / arg.removeprefix("content/")
    for root in ("games", "projects"):
        d = REPO / root / SLUG_ALIASES.get(slug, slug)
        if d.is_dir():
            maps = sorted(d.glob("maps/main.json")) or sorted(d.glob("*.json"))
            if maps:
                return maps[0]
    return None


def render(engine: str, scene: Path, out: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [engine, "frame", str(scene), str(out), "--size", SIZE],
        capture_output=True, text=True,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default=str(REPO.parent / "RedEngine-latest" / "target" / "debug" / "red_engine2"))
    ap.add_argument("--catalog", default="/tmp/cat.tsv", help="launcher catalog TSV (header: slug\\tname\\t...)")
    ap.add_argument("--only")
    args = ap.parse_args()

    release = json.loads((REPO / ".release-games.json").read_text())
    playables = {g["slug"]: g for g in release.get("data_playables", [])}

    rows = [l.split("\t") for l in Path(args.catalog).read_text().splitlines()[1:] if l.strip()]
    slugs = [r[0] for r in rows]
    if args.only:
        slugs = [s for s in slugs if s == args.only]

    THUMBS.mkdir(parents=True, exist_ok=True)
    failed = []
    for slug in slugs:
        scene = map_path_for(slug, playables)
        out = THUMBS / f"{slug}.png"
        if scene is None or not scene.exists():
            print(f"SKIP {slug}: no map found ({scene})")
            failed.append(slug)
            continue
        r = render(args.engine, scene, out)
        if r.returncode != 0:
            # Projects pin their own engine revisions, so gameplay blocks
            # (rules expressions, removed weapon keys) can fail validation on
            # the rendering engine. They don't affect a static frame — `frame`
            # ignores rule state — so retry with them stripped.
            scene_data = json.loads(scene.read_text())
            for key in ("rules", "weapons", "checks"):
                scene_data.pop(key, None)
            # Next to the original so relative asset references still resolve.
            tmp = scene.with_name(scene.stem + ".__thumbtmp.json")
            tmp.write_text(json.dumps(scene_data))
            r = render(args.engine, tmp, out)
            tmp.unlink()
        if r.returncode != 0 or not out.exists():
            print(f"FAIL {slug}: {r.stderr.strip().splitlines()[-1] if r.stderr else r.returncode}")
            failed.append(slug)
        else:
            print(f"ok   {slug} <- {scene.relative_to(REPO)}")
    if failed:
        print(f"\n{len(failed)} failed: {', '.join(failed)}")
        return 1
    print(f"\nall {len(slugs)} thumbnails in {THUMBS.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
