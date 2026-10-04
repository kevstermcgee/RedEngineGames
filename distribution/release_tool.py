#!/usr/bin/env python3
"""Versioned releases of RedEngineGames: decide what changed, build installers, describe the result.

A game is released again only when its own content changed (or on request); every release is a permanent GitHub Release tagged `<slug>-v<N>` that carries

  * `<slug>-<N>-setup.exe`        the installer (per-user, no admin rights; installs over the previous version, so an update keeps the player's saves)
  * `<slug>-<N>-windows-x64.zip`  the same game as a portable folder
  * a machine-readable line at the end of the release notes, `<!-- redengine-release {...} -->`, which is how the website and the in-game updater learn the history.

Subcommands (run from the repository root; `plan` needs only git, `build` needs Windows with Inno Setup for the installers):

  plan      decide which games get a new version        -> plan.json
  build     stage, zip and compile installers           -> dist/assets/
  finalize  checksums and release notes (after signing) -> dist/bodies/, dist/SHA256SUMS.txt
  publish   one GitHub Release per game, tagged <slug>-v<N>

Run the tests with `python3 -m unittest discover distribution`.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE / "config.json").read_text())
MARKER = re.compile(r"<!--\s*redengine-release\s+(\{.*?\})\s*-->", re.S)
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


# ---- what is published ----------------------------------------------------------------------------------------------------------------------


def load_playables(repo: Path = REPO) -> list[dict]:
    """Every playable game: the catalog's (published by RedEngine) and the repository's own data-driven ones, checked for safe slugs and paths."""
    catalog = json.loads((repo / ".games-catalog.json").read_text())
    extra = json.loads((repo / ".release-games.json").read_text())
    playables = list(catalog.get("playables", [])) + list(extra.get("data_playables", []))
    seen = set()
    for p in playables:
        if not SLUG.match(p["slug"]):
            raise SystemExit(f"unsafe slug: {p['slug']}")
        if p["slug"] in seen:
            raise SystemExit(f"duplicate slug: {p['slug']}")
        seen.add(p["slug"])
        for f in p["files"]:
            target = (repo / f).resolve()
            if repo.resolve() not in target.parents or not target.exists():
                raise SystemExit(f"{p['slug']}: published path is missing or escapes the repository: {f}")
    return playables


def one_line(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("*", "")).strip()


def describe(directory: Path, fallback: str) -> str:
    """A game's one-line description: its identity tagline, Cargo description, or first README paragraph."""
    identity = directory / "assets" / "identity.json"
    if identity.is_file():
        tagline = json.loads(identity.read_text(encoding="utf-8")).get("tagline")
        if tagline:
            return one_line(tagline)
    cargo = directory / "Cargo.toml"
    if cargo.is_file():
        m = re.search(r'(?m)^description\s*=\s*"([^"]+)"', cargo.read_text(encoding="utf-8"))
        if m:
            return one_line(m.group(1))
    readme = directory / "README.md"
    if readme.is_file():
        paragraph: list[str] = []
        for line in readme.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("!["):
                if paragraph:
                    break
                continue
            paragraph.append(line)
        if paragraph:
            return one_line(re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", " ".join(paragraph)))
    return fallback


def game_directory(playable: dict, repo: Path = REPO) -> Path:
    """The folder that holds the game (its first published path, trimmed to `games/<x>` or `projects/<x>`)."""
    parts = Path(playable["files"][0]).parts
    return repo.joinpath(*parts[:2]) if len(parts) >= 2 else repo / parts[0]


def content_hash(repo: Path, playable: dict) -> str:
    """A fingerprint of what the game consists of: the git object ids of its files (so line-ending settings on a runner cannot change it), its name and its command line."""
    listing = subprocess.run(
        ["git", "-C", str(repo), "ls-tree", "-r", "HEAD", "--", *playable["files"]], capture_output=True, text=True, check=True
    ).stdout
    h = hashlib.sha256()
    h.update(json.dumps([playable["name"], playable["arguments"]]).encode())
    h.update(listing.encode())
    return h.hexdigest()


# ---- the history, read back from the releases ----------------------------------------------------------------------------------------------


def load_releases(path: str | Path | None) -> list[dict]:
    """The releases from `gh api --paginate repos/<repo>/releases`: one JSON array per page, back to back (or with `--slurp`, an array of arrays)."""
    if not path or not Path(path).exists():
        return []
    text, pos, out = Path(path).read_text(), 0, []
    decoder = json.JSONDecoder()
    while pos < len(text):
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos >= len(text):
            break
        value, pos = decoder.raw_decode(text, pos)
        for item in value if isinstance(value, list) else [value]:
            out.extend(item if isinstance(item, list) else [item])
    return out


def release_history(releases: list[dict]) -> dict[str, list[dict]]:
    """Per slug, every versioned release (newest version first), read from the `redengine-release` line at the end of each release's notes."""
    out: dict[str, list[dict]] = {}
    for r in releases:
        m = MARKER.search(r.get("body") or "")
        if not m:
            continue
        try:
            meta = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        meta["tag"] = r.get("tag_name", "")
        meta["url"] = r.get("html_url", "")
        out.setdefault(meta["slug"], []).append(meta)
    for versions in out.values():
        versions.sort(key=lambda v: v["version"], reverse=True)
    return out


def decide(playables: list[dict], hashes: dict[str, str], history: dict[str, list[dict]], force: bool = False, only: set[str] | None = None) -> list[dict]:
    """The games that need a new version: never released, content changed since the newest release, or `force`."""
    todo = []
    for p in playables:
        slug = p["slug"]
        if only and slug not in only:
            continue
        latest = (history.get(slug) or [None])[0]
        if latest and latest.get("content_hash") == hashes[slug] and not force:
            continue
        todo.append({
            "slug": slug,
            "name": p["name"],
            "version": (latest["version"] + 1) if latest else 1,
            "content_hash": hashes[slug],
            "previous_commit": latest.get("repo_commit") if latest else None,
            "reason": "first release" if not latest else ("rebuilt on request" if latest.get("content_hash") == hashes[slug] else "content changed"),
        })
    return todo


def change_notes(repo: Path, playable: dict, previous_commit: str | None) -> list[str]:
    """Subjects of the commits that touched the game since its last release (the automatic content syncs say nothing, so they are left out)."""
    if not previous_commit:
        return []
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "log", "--format=%s", f"{previous_commit}..HEAD", "--", *playable["files"]], capture_output=True, text=True, check=True
        ).stdout
    except subprocess.CalledProcessError:
        return []
    notes: list[str] = []
    for line in out.splitlines():
        line = line.strip()
        if line and not line.startswith("Sync RedEngine content") and line not in notes:
            notes.append(line)
    return notes[:6]


# ---- building ----------------------------------------------------------------------------------------------------------------------------


def clean_name(name: str) -> str:
    """The game's name as a folder name (what the installer, the launcher and the uninstaller agree on)."""
    return "".join(c for c in name if c not in '<>:"/\\|?*').strip()


def app_guid(slug: str) -> str:
    """The installer's identity: the same for every version of a game, which is what makes a new installer an update of the old one."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, CONFIG["site_url"] + slug)).upper()


def play_cfg(entry: dict, installed: bool) -> str:
    site = CONFIG["site_url"]
    return "\n".join([
        f"name={clean_name(entry['name'])}",
        f"slug={entry['slug']}",
        f"version={entry['version']}",
        f"mode={'installed' if installed else 'portable'}",
        f"update_url={site}games/{entry['slug']}/latest.json",
        f"page_url={site}games/{entry['slug']}/",
        "",
    ])


def make_icon(slug: str, target: Path) -> bool:
    """A square icon from the game's picture on the website (centre crop), if there is one and Pillow is installed."""
    thumb = REPO / "site" / "thumbs" / f"{slug}.png"
    if not thumb.is_file():
        return False
    try:
        from PIL import Image
    except ImportError:
        return False
    image = Image.open(thumb).convert("RGBA")
    side = min(image.size)
    left, top = (image.width - side) // 2, (image.height - side) // 2
    image.crop((left, top, left + side, top + side)).resize((256, 256)).save(target, sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
    return True


def stage_game(entry: dict, playable: dict, engine: Path, launcher: Path, stage: Path) -> None:
    """The folder a player ends up with: engine, launcher, the game's content and the files that tie them together."""
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    exe = CONFIG["engine_exe"]
    shutil.copy2(engine, stage / exe)
    shutil.copy2(launcher, stage / f"Play-{entry['slug']}.exe")
    (stage / "engine.name").write_text(exe + "\n", encoding="utf-8")
    (stage / "launch.args").write_text("\n".join(playable["arguments"]) + "\n", encoding="utf-8")
    (stage / "play.cfg").write_text(play_cfg(entry, installed=False), encoding="utf-8")
    for f in playable["files"]:
        src, dst = REPO / f, stage / "content" / f
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
    make_icon(entry["slug"], stage / "game.ico")
    (stage / "README.txt").write_text(
        f"{entry['name']} (version {entry['version']})\n\nDouble-click Play-{entry['slug']}.exe to start.\n"
        f"Your saved games and settings are kept in Saved Games\\{clean_name(entry['name'])}.\n"
        "When a newer version is released the game offers to update it.\n",
        encoding="utf-8",
    )


def zip_folder(folder: Path, archive: Path) -> None:
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                z.write(path, path.relative_to(folder).as_posix())


def find_iscc() -> str:
    for candidate in (os.environ.get("ISCC"), shutil.which("iscc"), r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe", r"C:\Program Files\Inno Setup 6\ISCC.exe"):
        if candidate and Path(candidate).exists():
            return candidate
    raise SystemExit("Inno Setup (ISCC.exe) is not installed")


def compile_installer(entry: dict, stage: Path, out_dir: Path, work: Path) -> Path:
    """Compiles the per-user installer for the staged game with Inno Setup."""
    (stage / "play.cfg").write_text(play_cfg(entry, installed=True), encoding="utf-8")
    base = f"{entry['slug']}-{entry['version']}-setup"
    defines = "\n".join([
        f'#define AppId "{{{{{app_guid(entry["slug"])}}}"',
        f'#define AppName "{clean_name(entry["name"]).replace(chr(34), "")}"',
        f'#define AppSlug "{entry["slug"]}"',
        f'#define AppVersion "{entry["version"]}"',
        f'#define VersionInfo "1.0.0.{min(entry["version"], 65535)}"',
        f'#define Publisher "{CONFIG["publisher"]}"',
        f'#define SiteUrl "{CONFIG["site_url"]}games/{entry["slug"]}/"',
        f'#define StageDir "{stage.resolve()}"',
        f'#define OutDir "{out_dir.resolve()}"',
        f'#define OutName "{base}"',
        "",
    ])
    work.mkdir(parents=True, exist_ok=True)
    shutil.copy2(HERE / "installer.iss", work / "installer.iss")
    (work / "defines.iss").write_text(defines, encoding="utf-8")
    subprocess.run([find_iscc(), "/Q", str(work / "installer.iss")], check=True)
    return out_dir / f"{base}.exe"


# ---- the release notes ------------------------------------------------------------------------------------------------------------------


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def release_body(meta: dict) -> str:
    """The text of a game's release: what it is, what changed, and the machine-readable line the website reads."""
    lines = [f"**{meta['name']}**, version {meta['version']}", ""]
    if meta["notes"]:
        lines += ["What changed:", *[f"- {n}" for n in meta["notes"]], ""]
    lines += [
        f"Built with RedEngine `{meta['engine_revision'][:12]}`.",
        "",
        f"Install with `{meta['installer']['name']}`; an installed game updates itself in place and keeps the player's saves (in Saved Games).",
        f"`{meta['zip']['name']}` is the same game as a portable folder.",
        "",
        f"<!-- redengine-release {json.dumps(meta, separators=(',', ':'))} -->",
        "",
    ]
    return "\n".join(lines)


# ---- commands ------------------------------------------------------------------------------------------------------------------------------


def cmd_plan(args) -> int:
    playables = load_playables()
    history = release_history(load_releases(args.releases))
    hashes = {p["slug"]: content_hash(REPO, p) for p in playables}
    todo = decide(playables, hashes, history, force=args.force, only=set(args.only or []))
    catalog = json.loads((REPO / ".games-catalog.json").read_text())
    by_slug = {p["slug"]: p for p in playables}
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    for t in todo:
        t["notes"] = change_notes(REPO, by_slug[t["slug"]], t["previous_commit"])
        t["repo_commit"] = head
        t["engine_revision"] = catalog["source_revision"]
        t["released"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    Path(args.out).write_text(json.dumps({"engine_revision": catalog["source_revision"], "games": todo}, indent=1))
    for t in todo:
        print(f"{t['slug']:24} v{t['version']:<3} {t['reason']}")
    print(f"{len(todo)} of {len(playables)} games to release")
    return 0


def cmd_build(args) -> int:
    plan = json.loads(Path(args.plan).read_text())
    by_slug = {p["slug"]: p for p in load_playables()}
    out = Path(args.out)
    assets, work = out / "assets", out / "work"
    shutil.rmtree(out, ignore_errors=True)
    assets.mkdir(parents=True)
    for entry in plan["games"]:
        stage = work / entry["slug"] / "stage"
        stage_game(entry, by_slug[entry["slug"]], Path(args.engine), Path(args.launcher), stage)
        zip_folder(stage, assets / f"{entry['slug']}-{entry['version']}-windows-x64.zip")
        compile_installer(entry, stage, assets, work / entry["slug"] / "iss")
        shutil.rmtree(work / entry["slug"])
        print(f"built {entry['slug']} {entry['version']}")
    return 0


def cmd_finalize(args) -> int:
    plan = json.loads(Path(args.plan).read_text())
    out = Path(args.out)
    assets, bodies = out / "assets", out / "bodies"
    bodies.mkdir(parents=True, exist_ok=True)
    sums = []
    for entry in plan["games"]:
        info = {}
        for kind, name in (("installer", f"{entry['slug']}-{entry['version']}-setup.exe"), ("zip", f"{entry['slug']}-{entry['version']}-windows-x64.zip")):
            path = assets / name
            info[kind] = {"name": name, "size": path.stat().st_size, "sha256": sha256_of(path)}
            sums.append(f"{info[kind]['sha256']}  {name}")
        meta = {k: entry[k] for k in ("slug", "name", "version", "released", "content_hash", "repo_commit", "engine_revision", "notes")} | info
        meta["signed"] = bool(args.signed)
        (bodies / f"{entry['slug']}.md").write_text(release_body(meta), encoding="utf-8")
    (out / "SHA256SUMS.txt").write_text("\n".join(sorted(sums, key=lambda l: l.split()[1])) + "\n", encoding="ascii")
    print(f"described {len(plan['games'])} release(s)")
    return 0


def cmd_publish(args) -> int:
    """Creates one GitHub Release per planned game (a release that already exists is left as it is: a version is never rewritten)."""
    plan = json.loads(Path(args.plan).read_text())
    out = Path(args.out)
    for entry in plan["games"]:
        tag = f"{entry['slug']}-v{entry['version']}"
        files = sorted(str(p) for p in (out / "assets").glob(f"{entry['slug']}-{entry['version']}-*"))
        cmd = ["gh", "release", "create", tag, *files, "--title", f"{entry['name']} {entry['version']}",
               "--notes-file", str(out / "bodies" / f"{entry['slug']}.md"), "--latest=false", "--target", entry["repo_commit"]]
        if args.dry_run:
            print("would run:", " ".join(cmd[:4]), f"... ({len(files)} files)")
            continue
        exists = subprocess.run(["gh", "release", "view", tag], capture_output=True).returncode == 0
        if exists:
            print(f"{tag} exists; left alone")
            continue
        subprocess.run(cmd, check=True)
        print(f"released {tag}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--releases", help="JSON from `gh api --paginate repos/<repo>/releases`")
    p.add_argument("--force", action="store_true", help="release every game again (an engine refresh)")
    p.add_argument("--only", nargs="*", help="only these slugs")
    p.add_argument("--out", default="plan.json")
    p = sub.add_parser("build")
    p.add_argument("--plan", default="plan.json")
    p.add_argument("--engine", required=True)
    p.add_argument("--launcher", required=True)
    p.add_argument("--out", default="dist")
    p = sub.add_parser("finalize")
    p.add_argument("--plan", default="plan.json")
    p.add_argument("--out", default="dist")
    p.add_argument("--signed", action="store_true")
    p = sub.add_parser("publish")
    p.add_argument("--plan", default="plan.json")
    p.add_argument("--out", default="dist")
    p.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    return {"plan": cmd_plan, "build": cmd_build, "finalize": cmd_finalize, "publish": cmd_publish}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
