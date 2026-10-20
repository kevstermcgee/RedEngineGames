#!/usr/bin/env python3
"""Publish a ready-made Windows game (not built from this repository) on the website and in the RedEngine Games app, or a new version of one.

The game can be a ZIP, a folder, or a single `.exe`, `.bat` or `.cmd` (with `--add` for files that go beside it). The tool repacks it into the
same portable ZIP the RedEngine games ship as, so the app installs, plays, updates and uninstalls it like any other game:

  * a ZIP whose files all sit in one top folder is unpacked from inside that folder;
  * `engine.name` names what to start (found by itself when the game has exactly one `.exe`, `.bat` or `.cmd` that is not an uninstaller or a
    setup, else pass `--run`), and `launch.args` holds `--args`, one per line.

A game can describe itself (its card, `docs/GAME_METADATA.md`; write one with `game_meta.py stamp`): then `--name` and the rest are not needed. What
is not given as a flag comes from the card, else from the previous release of the game, else the defaults. The card (without its notes) is written
into the packed ZIP, as `redengine-game.json` and as the ZIP's comment, so the published game carries it; the card's `entry` and `args` are what
starts the game when `--run` and `--args` are absent (`engine.name` still wins), and its `notes` are "what changed" when there is no `--notes`.
A folder with a `fork.json` (which the app's Fork… writes) is a fork: that names its parent, wins over the card, and the game's own script or
program says nothing of its own for a fork's description, designer, online note or notes (they were its parent's). Links in a game's folder are left
behind, and a program given as the game is the game whatever it is called.

It is published as the GitHub Release `<slug>-v<N>` with the same `redengine-release` line the built games carry (plus `"kind": "upload"` and
what the website shows: description, 2D/3D, designer, screenshot). `N` is one more than the newest release of that slug, so running it again with
the same name publishes an update, which the app then offers to everyone who installed the game. There is no installer: players get the game
in the app or as the portable ZIP.

  python3 distribution/upload_game.py path/to/Game.zip --name "Star Miner" --description "Mine asteroids, dodge pirates." --thumb shot.png
  python3 distribution/upload_game.py path/to/Game.zip --name "Star Miner" --notes "Fixed the save bug."      # version 2
  python3 distribution/upload_game.py path/to/Game.zip                                                         # the game says its own name
  python3 distribution/upload_game.py game.bat --add data.txt --name "Text Quest" --kind 2d --dry-run           # pack only, publish nothing

Needs `gh` signed in with permission to create releases (or GH_TOKEN). The site rebuilds when the release is published.
"""

import argparse
import json
import os
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
import game_meta as gm  # noqa: E402
import release_tool as rt  # noqa: E402

RUNNABLE = gm.RUNNABLE
NOT_THE_GAME = gm.NOT_THE_GAME  # executables a ready-made game often carries that are never the game itself
KINDS = gm.KINDS


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


def _no_links(folder: str, names: list[str]) -> list[str]:
    """What `copytree` leaves behind: links, which would bring in whatever they point at, from outside the game."""
    return [n for n in names if os.path.islink(os.path.join(folder, n))]


def collect(source: Path, extra: list[Path], into: Path) -> Path:
    """The game's files in one folder (returned): a ZIP unpacked, a folder copied (without its links), or a single file with its `extra` companions."""
    if source.is_dir():
        shutil.copytree(source, into, ignore=_no_links)
    elif source.suffix.lower() == ".zip":
        unpack(source, into)
    elif source.is_file():
        into.mkdir(parents=True)
        shutil.copy2(source, into / source.name)
    else:
        raise SystemExit(f"{source}: no such file or folder")
    for f in extra:
        if f.is_dir():
            shutil.copytree(f, into / f.name, ignore=_no_links)
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


def find_entry(folder: Path, run: str | None, card_entry: str | None = None, lone: str | None = None) -> str:
    """What to start, relative to the folder, with forward slashes: `run` when given (checked), else what `engine.name` says, else the card's `entry`
    (already checked by the reader), else the one runnable file there is, else `lone`, the program given as the game itself (whatever it is called)."""
    if run:
        rel = PurePosixPath(run.replace("\\", "/"))
        if rel.is_absolute() or ".." in rel.parts or not (folder / rel).is_file():
            raise SystemExit(f"--run {run}: not a file inside the game")
        return str(rel)
    if (folder / "engine.name").is_file():  # already a RedEngine-style portable build
        return (folder / "engine.name").read_text().strip()
    if card_entry:
        return card_entry
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
    if lone and (folder / lone).is_file():
        return lone
    raise SystemExit("nothing to start: the game has no .exe, .bat or .cmd (pass --run)")


def prepare(folder: Path, run: str | None, args: list[str], card: dict | None = None, lone: str | None = None) -> str:
    """Make the folder a game the app starts: `engine.name` and `launch.args` (the card's `entry` and `args` when `run` and `args` are absent). Returns the entry."""
    card = card or {}
    entry = find_entry(folder, run, card.get("entry"), lone)
    if PurePosixPath(entry).suffix.lower() not in RUNNABLE:
        raise SystemExit(f"{entry}: the app starts .exe, .bat and .cmd files only")
    (folder / "engine.name").write_text(entry + "\n", encoding="utf-8")
    args = args or card.get("args") or []
    if args or not (folder / "launch.args").is_file():
        (folder / "launch.args").write_text("".join(a + "\n" for a in args), encoding="utf-8")
    return entry


def zip_game(folder: Path, archive: Path, card: dict | None = None) -> None:
    """Zip the folder; with a `card`, the ZIP's comment is that card too (the card file is in the folder already)."""
    archive.parent.mkdir(parents=True, exist_ok=True)
    rt.zip_folder(folder, archive)
    if card:
        with zipfile.ZipFile(archive, "a") as z:
            z.comment = gm.card_comment(card)


def source_comment(source: Path) -> dict | None:
    """The card in the comment of a ZIP given as the game: unpacking it (`collect`) loses the comment, so it is read first, as the app reads it."""
    return gm.zip_comment(source) if source.is_file() and source.suffix.lower() == ".zip" else None


def lone_program(source: Path) -> str | None:
    """The name of `source` when it is a single program (not a folder or a ZIP): it is the game, whatever its name (`Install_And_Play.bat`)."""
    return source.name if source.is_file() and source.suffix.lower() in RUNNABLE else None


def pack(source: Path, extra: list[Path], run: str | None, args: list[str], archive: Path) -> str:
    """Write the portable ZIP the app installs and return the entry it starts."""
    with tempfile.TemporaryDirectory() as tmp:
        folder = collect(source, extra, Path(tmp) / "game")
        entry = prepare(folder, run, args, gm.read(folder, lone=lone_program(source), comment=source_comment(source))["card"], lone_program(source))
        zip_game(folder, archive)
    return entry


def pick(*values):
    """The first value that is set: flags, then the card, then the previous release, then the default (None, an empty string and an empty list are not set)."""
    return next((v for v in values if v not in (None, "", [])), None)


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


def read_fork(folder: Path) -> tuple[dict, str] | None:
    """The game a fork says it was made from and the name it was given: its `fork.json` (as the app's Fork… writes it, which wins over the card), or None."""
    try:
        with open(folder / "fork.json", "rb") as f:
            raw = gm.parse_card(f.read(gm.MAX_CARD + 1)) or {}
    except OSError:
        return None
    parent, name = gm.check_card({"forked_from": raw.get("forked_from")}).get("forked_from"), raw.get("name")
    return (parent, gm.clean(name, gm.LIMITS["name"])) if parent and isinstance(name, str) else None


def launch_args(folder: Path) -> list[str]:
    """The arguments in a game's own `launch.args`, as a card keeps them."""
    try:
        with open(folder / "launch.args", "rb") as f:
            text = f.read(gm.HEADER_BYTES).decode("utf-8", "replace")
    except OSError:
        return []
    return gm.check_card({"args": text.splitlines()}).get("args", [])


def parse_forked_from(text: str, slug: str) -> dict:
    """`snake@3` (or `snake@v3`) -> {"slug": "snake", "version": 3}: the game this one was forked from."""
    parent, _, version = text.partition("@")
    if not rt.SLUG.match(parent) or parent == slug or not version.lstrip("v").isdigit() or int(version.lstrip("v")) < 1:
        raise SystemExit(f"--forked-from {text!r}: SLUG@N, the game and the version it was forked from (not itself)")
    return {"slug": parent, "version": int(version.lstrip("v"))}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path, help="the game: a .zip, a folder, or one .exe/.bat/.cmd")
    ap.add_argument("--name", help="the game's name as players see it (not needed when the game says it: its card, a script header, a program's record or version information)")
    ap.add_argument("--slug", help="its id in addresses (default: from the name); keep it the same for every version")
    ap.add_argument("--description", help="one or two sentences for the website and the app (default: the game's card; an update keeps the previous one when left out)")
    ap.add_argument("--notes", action="append", default=[], help="a line of \"what changed\" (repeatable; default: the game's card)")
    ap.add_argument("--run", help="what to start, relative to the game's folder (default: the card's entry; needed when the game has several .exe/.bat/.cmd files)")
    ap.add_argument("--args", action="append", default=[], help="an argument to start it with (repeatable; default: the card's; `--args --fullscreen` works as `--args=--fullscreen`)")
    ap.add_argument("--add", type=Path, action="append", default=[], help="a file or folder to put beside a single .exe/.bat (repeatable)")
    ap.add_argument("--kind", choices=KINDS, help="2d, 3d or hybrid (default 3d; the card's, else the previous release's)")
    ap.add_argument("--author", choices=("ai", "human"), help="who designed it (default human; the card's, else the previous release's)")
    ap.add_argument("--online", help="a note shown when it has online multiplayer (never an address or a join key)")
    ap.add_argument("--thumb", type=Path, help="a 16:9 screenshot (.png or .jpg) for the website and the app (default: the card's)")
    ap.add_argument("--forked-from", help="SLUG@N: the game and version this one was made from (a fork; the card's or the previous release's is kept)")
    ap.add_argument("--maintainer", help="the GitHub login of whoever keeps it (an update keeps the previous one)")
    ap.add_argument("--out", type=Path, default=Path("dist-upload"), help="where the files are written before publishing")
    ap.add_argument("--dry-run", action="store_true", help="pack and describe the release, publish nothing (needs no network)")
    a = ap.parse_args(gm.glue_dashed(sys.argv[1:] if argv is None else [str(x) for x in argv], [ap], "--args", "--notes"))

    if a.thumb and (a.thumb.suffix.lower() not in (".png", ".jpg", ".jpeg") or not a.thumb.is_file()):
        raise SystemExit("--thumb: a .png or .jpg file")
    playable_slugs = {p["slug"] for p in rt.load_playables()}
    history = rt.release_history([] if a.dry_run else fetch_releases())

    with tempfile.TemporaryDirectory() as tmp:
        folder = collect(a.source, a.add, Path(tmp) / "game")
        fork = read_fork(folder)
        card = gm.read(folder, fork=bool(fork), lone=lone_program(a.source), comment=source_comment(a.source))["card"]
        # The card's name, unless it makes no id (`星の旅`) or is the parent's (a fork made before the card existed has its parent's card): then the fork's own.
        card_name = next((n for n in (card.get("name"),) if n and slugify(n) and not (fork and slugify(n) == fork[0]["slug"])), None)
        name = (a.name or "").strip() or card_name or (fork[1] if fork and slugify(fork[1]) else None) or (history.get(a.slug) or [{}])[0].get("name")
        if not name:
            raise SystemExit("no name for the game: it does not say its own (a redengine-game.json card, a header in the .bat, a record or version information "
                             "in the .exe) and none was given; pass --name")
        slug = a.slug or slugify(name)
        if not rt.SLUG.match(slug):
            raise SystemExit(f"--slug {slug!r}: use lowercase letters, digits and single hyphens")
        version, previous = plan_version(slug, history, playable_slugs)
        previous = previous or {}
        if previous and not (a.name or a.slug):
            print(f"note: the game's own name makes this version {version} of {slug} (its newest release is version {previous['version']}"
                  f"{', kept by ' + previous['maintainer'] if previous.get('maintainer') else ''}); pass --slug to publish it as another game", file=sys.stderr)

        shutil.rmtree(a.out, ignore_errors=True)
        zip_name = f"{slug}-{version}-windows-x64.zip"
        entry = prepare(folder, a.run, a.args, card, lone_program(a.source))
        if fork and fork[0]["slug"] == slug and not a.forked_from:
            raise SystemExit(f"{slug} is the name of the game this fork was made from: give your version its own (--name)")
        parent = fork[0] if fork else card.get("forked_from")
        forked_from = parse_forked_from(a.forked_from, slug) if a.forked_from else pick(parent if parent and parent["slug"] != slug else None, previous.get("forked_from"))
        description = pick(a.description, card.get("description"), previous.get("description"))
        presentation = pick(a.kind, card.get("presentation"), previous.get("presentation"), "3d")
        author = pick(a.author, card.get("author"), previous.get("author"), "human")
        if a.online and gm.looks_like_address(gm.clean(a.online, gm.LIMITS["online"])):
            raise SystemExit("--online: a note on how it is played online, never an address or a join key (those are never published)")
        online = a.online if a.online is not None else pick(card.get("online"), previous.get("online")) or ""
        notes = [n.strip() for n in a.notes if n.strip()] or card.get("notes") or (["First release."] if version == 1 else ["A new build."])
        release_thumb = None
        if a.thumb:  # the screenshot travels in the game, named by the card
            ext = ".jpg" if a.thumb.suffix.lower() == ".jpeg" else a.thumb.suffix.lower()
            in_game = gm.THUMB_STEM + ext
            for other in {gm.THUMB_STEM + e for e in gm.PICTURES} - {in_game}:  # the other kind of picture would be dead weight
                (folder / other).unlink(missing_ok=True)
            if a.thumb.stat().st_size > gm.MAX_THUMB:  # a reader ignores a card's picture this big: it goes to the site only, as the app does
                (folder / in_game).unlink(missing_ok=True)
                in_game, release_thumb = None, (a.thumb, ext)
            else:
                shutil.copy2(a.thumb, folder / in_game)
        else:
            in_game = card.get("thumb")

        # The card the published game carries: what was just decided, without the notes (they are for this release only).
        own = gm.fit(gm.check_card({"name": name, "description": description, "presentation": presentation, "author": author, "online": online, "entry": entry,
                                    "args": a.args or card.get("args") or ([] if a.run else launch_args(folder)), "thumb": in_game, "forked_from": forked_from}))
        (folder / gm.CARD_FILE).write_bytes(gm.card_text(own).encode("utf-8"))
        zip_game(folder, a.out / zip_name, own)
        thumb = None
        if in_game:
            thumb = a.out / f"{slug}-{version}-thumb{Path(in_game).suffix.lower()}"
            shutil.copy2(folder / in_game, thumb)
        elif release_thumb:
            thumb = a.out / f"{slug}-{version}-thumb{release_thumb[1]}"
            shutil.copy2(release_thumb[0], thumb)

    files = [a.out / zip_name]
    meta = {
        "kind": "upload",
        "slug": slug,
        "name": name,
        "version": version,
        "released": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "description": rt.one_line(description or f"{name}, a Windows game."),
        "presentation": presentation,
        "author": author,
        "online": online,
        "entry": entry,
        "notes": notes,
        "zip": {"name": zip_name, "size": files[0].stat().st_size, "sha256": rt.sha256_of(files[0])},
    }
    if forked_from:
        meta["forked_from"] = forked_from
    if a.maintainer or previous.get("maintainer"):
        meta["maintainer"] = a.maintainer or previous["maintainer"]
    if thumb:
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
