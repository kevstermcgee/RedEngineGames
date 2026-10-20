#!/usr/bin/env python3
"""Publish a ready-made Windows game (not built from this repository) on the website and in the RedEngine Games app, or a new version of one.

The game can be a ZIP, a folder, or a single `.exe`, `.bat` or `.cmd` (with `--add` for files that go beside it). The tool repacks it into the
same portable ZIP the RedEngine games ship as, so the app installs, plays, updates and uninstalls it like any other game:

  * a ZIP whose files all sit in one top folder is unpacked from inside that folder;
  * `engine.name` names what to start (found by itself when the game has exactly one `.exe`, `.bat` or `.cmd` that is not an uninstaller or a
    setup, else pass `--run`), and `launch.args` holds `--args`, one per line.

It is published as the GitHub Release `<slug>-v<N>` with the same `redengine-release` line the built games carry (plus `"kind": "upload"` and
what the website shows: description, 2D/3D, designer, screenshot). `N` is one more than the newest release of that slug, so running it again with
the same name publishes an update, which the app then offers to everyone who installed the game. There is no installer: players get the game
in the app or as the portable ZIP.

  python3 distribution/upload_game.py path/to/Game.zip --name "Star Miner" --description "Mine asteroids, dodge pirates." --thumb shot.png
  python3 distribution/upload_game.py path/to/Game.zip --name "Star Miner" --notes "Fixed the save bug."      # version 2
  python3 distribution/upload_game.py game.bat --add data.txt --name "Text Quest" --kind 2d --dry-run           # pack only, publish nothing

Needs `gh` signed in with permission to create releases (or GH_TOKEN). The site rebuilds when the release is published.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import release_tool as rt  # noqa: E402

RUNNABLE = (".exe", ".bat", ".cmd")
# Executables a ready-made game often carries that are never the game itself.
# The start of the name, as the app's `upload::NOT_THE_GAME`.
NOT_THE_GAME = re.compile(r"^(unins|setup|install|vc_?redist|dxsetup|unitycrashhandler|crashpad_handler|notification_helper)[^/]*\.(exe|bat|cmd)$", re.I)
KINDS = ("2d", "3d", "hybrid")


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def unpack(zip_path: Path, into: Path) -> None:
    """Unpack a ZIP, refusing any entry that would land outside `into`."""
    root = into.resolve()
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            target = (into / info.filename).resolve()
            if target != root and root not in target.parents:
                raise SystemExit(f"{zip_path.name}: unsafe path in the archive: {info.filename}")
        z.extractall(into)


def collect(source: Path, extra: list[Path], into: Path) -> Path:
    """The game's files in one folder (returned): a ZIP unpacked, a folder copied, or a single file with its `extra` companions."""
    if source.is_dir():
        shutil.copytree(source, into)
    elif source.suffix.lower() == ".zip":
        unpack(source, into)
    elif source.is_file():
        into.mkdir(parents=True)
        shutil.copy2(source, into / source.name)
    else:
        raise SystemExit(f"{source}: no such file or folder")
    for f in extra:
        if f.is_dir():
            shutil.copytree(f, into / f.name)
        elif f.is_file():
            shutil.copy2(f, into / f.name)
        else:
            raise SystemExit(f"--add {f}: no such file or folder")
    # A ZIP made by right-clicking a folder holds that one folder: play from inside it.
    while True:
        items = [p for p in into.iterdir() if p.name not in ("__MACOSX", ".DS_Store")]
        if len(items) == 1 and items[0].is_dir() and not extra:
            into = items[0]
            continue
        return into


def find_entry(folder: Path, run: str | None) -> str:
    """What to start, relative to the folder, with forward slashes: `run` when given (checked), else the one runnable file there is."""
    if run:
        rel = PurePosixPath(run.replace("\\", "/"))
        if rel.is_absolute() or ".." in rel.parts or not (folder / rel).is_file():
            raise SystemExit(f"--run {run}: not a file inside the game")
        return str(rel)
    if (folder / "engine.name").is_file():  # already a RedEngine-style portable build
        return (folder / "engine.name").read_text().strip()
    def runnable(depth: int) -> list[str]:
        found = []
        for p in sorted(folder.rglob("*")):
            rel = p.relative_to(folder)
            if p.is_file() and len(rel.parts) <= depth and p.suffix.lower() in RUNNABLE and not NOT_THE_GAME.match(p.name):
                found.append(rel.as_posix())
        return found
    # The top folder first; a game whose top folder holds nothing to start may keep it one level down (`bin/Game.exe`).
    for depth in (1, 2):
        found = runnable(depth)
        if len(found) == 1:
            return found[0]
        if found:
            raise SystemExit("more than one thing could start the game; pass --run with one of:\n  " + "\n  ".join(found))
    raise SystemExit("nothing to start: the game has no .exe, .bat or .cmd (pass --run)")


def pack(source: Path, extra: list[Path], run: str | None, args: list[str], archive: Path) -> str:
    """Write the portable ZIP the app installs and return the entry it starts."""
    with tempfile.TemporaryDirectory() as tmp:
        folder = collect(source, extra, Path(tmp) / "game")
        entry = find_entry(folder, run)
        if PurePosixPath(entry).suffix.lower() not in RUNNABLE:
            raise SystemExit(f"{entry}: the app starts .exe, .bat and .cmd files only")
        (folder / "engine.name").write_text(entry + "\n", encoding="utf-8")
        if args or not (folder / "launch.args").is_file():
            (folder / "launch.args").write_text("".join(a + "\n" for a in args), encoding="utf-8")
        archive.parent.mkdir(parents=True, exist_ok=True)
        rt.zip_folder(folder, archive)
    return entry


def release_body(meta: dict) -> str:
    lines = [f"**{meta['name']}**, version {meta['version']}", "", meta["description"], ""]
    if meta["notes"]:
        lines += ["What changed:", *[f"- {n}" for n in meta["notes"]], ""]
    lines += [
        f"A ready-made Windows game, uploaded as it is (it starts `{meta['entry']}`). Get it in the RedEngine Games app, which keeps it up to date,",
        f"or unzip `{meta['zip']['name']}` anywhere and run `{PurePosixPath(meta['entry']).name}`.",
        "",
        f"<!-- redengine-release {json.dumps(meta, separators=(',', ':'))} -->",
        "",
    ]
    return "\n".join(lines)


def fetch_releases() -> list[dict]:
    out = subprocess.run(["gh", "api", "--paginate", f"repos/{rt.CONFIG['repository']}/releases?per_page=100"], capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"could not read the releases (is gh signed in?): {out.stderr.strip()}")
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "releases.json").write_text(out.stdout)
        return rt.load_releases(Path(tmp) / "releases.json")


def plan_version(slug: str, history: dict[str, list[dict]], playable_slugs: set[str]) -> tuple[int, dict | None]:
    """The next version of an uploaded game, and its newest release (None for a new game). A name the built games already use is refused."""
    if slug in playable_slugs:
        raise SystemExit(f"{slug} is one of the games built from this repository; upload under another --slug")
    previous = (history.get(slug) or [None])[0]
    if previous and previous.get("kind") != "upload":
        raise SystemExit(f"{slug} has releases that were not uploaded; upload under another --slug")
    return (previous["version"] + 1 if previous else 1), previous


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path, help="the game: a .zip, a folder, or one .exe/.bat/.cmd")
    ap.add_argument("--name", required=True, help="the game's name as players see it")
    ap.add_argument("--slug", help="its id in addresses (default: from the name); keep it the same for every version")
    ap.add_argument("--description", help="one or two sentences for the website and the app (an update keeps the previous one when left out)")
    ap.add_argument("--notes", action="append", default=[], help="a line of \"what changed\" (repeatable)")
    ap.add_argument("--run", help="what to start, relative to the game's folder (needed when the game has several .exe/.bat/.cmd files)")
    ap.add_argument("--args", action="append", default=[], help="an argument to start it with (repeatable)")
    ap.add_argument("--add", type=Path, action="append", default=[], help="a file or folder to put beside a single .exe/.bat (repeatable)")
    ap.add_argument("--kind", choices=KINDS, help="2d, 3d or hybrid (default 3d; an update keeps the previous one)")
    ap.add_argument("--author", choices=("ai", "human"), help="who designed it (default human; an update keeps the previous one)")
    ap.add_argument("--online", help="a note shown when it has online multiplayer (never an address or a join key)")
    ap.add_argument("--thumb", type=Path, help="a 16:9 screenshot (.png or .jpg) for the website and the app")
    ap.add_argument("--out", type=Path, default=Path("dist-upload"), help="where the files are written before publishing")
    ap.add_argument("--dry-run", action="store_true", help="pack and describe the release, publish nothing (needs no network)")
    a = ap.parse_args(argv)

    slug = a.slug or slugify(a.name)
    if not rt.SLUG.match(slug):
        raise SystemExit(f"--slug {slug!r}: use lowercase letters, digits and single hyphens")
    playable_slugs = {p["slug"] for p in rt.load_playables()}
    history = rt.release_history([] if a.dry_run else fetch_releases())
    version, previous = plan_version(slug, history, playable_slugs)
    previous = previous or {}

    shutil.rmtree(a.out, ignore_errors=True)
    zip_name = f"{slug}-{version}-windows-x64.zip"
    entry = pack(a.source, a.add, a.run, a.args, a.out / zip_name)
    files = [a.out / zip_name]
    meta = {
        "kind": "upload",
        "slug": slug,
        "name": a.name.strip(),
        "version": version,
        "released": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "description": rt.one_line(a.description or previous.get("description") or f"{a.name.strip()}, a Windows game."),
        "presentation": a.kind or previous.get("presentation") or "3d",
        "author": a.author or previous.get("author") or "human",
        "online": a.online if a.online is not None else previous.get("online", ""),
        "entry": entry,
        "notes": [n.strip() for n in a.notes if n.strip()] or (["First release."] if version == 1 else ["A new build."]),
        "zip": {"name": zip_name, "size": files[0].stat().st_size, "sha256": rt.sha256_of(files[0])},
    }
    if a.thumb:
        ext = a.thumb.suffix.lower()
        if ext not in (".png", ".jpg", ".jpeg"):
            raise SystemExit("--thumb: a .png or .jpg")
        thumb = a.out / f"{slug}-{version}-thumb{'.jpg' if ext == '.jpeg' else ext}"
        shutil.copy2(a.thumb, thumb)
        files.append(thumb)
        meta["thumb"] = thumb.name
    elif previous.get("thumb_url"):
        meta["thumb_url"] = previous["thumb_url"]
    if "thumb" in meta:
        meta["thumb_url"] = f"https://github.com/{rt.CONFIG['repository']}/releases/download/{slug}-v{version}/{meta['thumb']}"
    body = a.out / "notes.md"
    body.write_text(release_body(meta), encoding="utf-8")

    tag = f"{slug}-v{version}"
    print(f"{tag}: {meta['name']}, starts {entry}, {meta['zip']['size'] / 1024 / 1024:.1f} MB ({', '.join(f.name for f in files)})")
    if a.dry_run:
        print(f"dry run: nothing published; the release notes are in {body}")
        return 0
    subprocess.run(["gh", "release", "create", tag, *map(str, files), "--repo", rt.CONFIG["repository"], "--title", f"{meta['name']} {version}",
                    "--notes-file", str(body), "--latest=false"], check=True)
    print(f"published {tag}; the website and the app list it once the site rebuilds (a minute or two): {rt.CONFIG['site_url']}games/{slug}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
