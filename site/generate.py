#!/usr/bin/env python3
"""Generate the RedEngineGames download site into site/dist/.

The site is built from the repository's own list of games and from the GitHub Releases, which are the record of every version ever published
(`distribution/release_tool.py` writes a machine-readable line into each release's notes):

  index.html                   every game: install the latest version, link to all versions
  games/<slug>/index.html      one game: the latest version and the whole history, each with installer, portable ZIP, checksum and what changed
  games/<slug>/latest.json     what an installed game asks to learn whether an update exists
  catalog.json                 everything above as data (what the RedEngine Games app reads)
  launcher/latest.json         the newest RedEngine Games app (`launcher/`), which it checks to update itself

Games uploaded ready-made (`distribution/upload_game.py`: a ZIP, a folder, a .exe or a .bat) are read from their releases alone: they have a
portable ZIP and no installer, and the app installs them like the others.

Builds from before installers existed (one release per engine commit, a ZIP per game) are listed under "Earlier builds" on each game's page, one per day.
Usage:  gh api --paginate repos/OWNER/REPO/releases > releases.json && python3 site/generate.py --releases releases.json
"""

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "distribution"))
import release_tool as rt  # noqa: E402
sys.path.insert(0, str(REPO / "site"))
import wiki  # noqa: E402

PALETTE = json.loads((REPO / "site" / "palette.json").read_text())
CONFIG = rt.CONFIG
LEGACY_TAG = re.compile(r"^redengine-([0-9a-f]{7,40})$")
LAUNCHER_TAG = re.compile(r"^launcher-v(\d+(?:\.\d+)*)$")
e = html.escape
AUTHORS = {"ai": "AI-designed", "human": "Human-designed"}


def human_size(n) -> str:
    return f"{n / 1024 / 1024:.0f} MB" if n else ""


def asset_url(tag: str, name: str) -> str:
    return f"https://github.com/{CONFIG['repository']}/releases/download/{tag}/{name}"


def added_date(playable: dict, fallback: str) -> str:
    d = rt.game_directory(playable)
    if not d.is_dir():
        return fallback
    out = subprocess.run(
        ["git", "-C", str(REPO), "log", "--reverse", "--format=%ad", "--date=short", "--", str(d.relative_to(REPO))], capture_output=True, text=True
    ).stdout.strip().splitlines()
    return out[0] if out else fallback


def legacy_builds(releases: list[dict]) -> dict[str, list[dict]]:
    """Per slug, the old-style builds (a ZIP per game in a release per engine commit): the newest of each day."""
    per_slug: dict[str, dict[str, dict]] = {}
    for r in sorted(releases, key=lambda r: r.get("published_at") or "", reverse=True):
        m = LEGACY_TAG.match(r.get("tag_name", ""))
        if not m:
            continue
        day = (r.get("published_at") or "")[:10]
        for a in r.get("assets", []):
            name = a["name"]
            if name.endswith("-windows-x64.zip") and name != "RedEngineLauncher-windows-x64.zip":
                slug = name[: -len("-windows-x64.zip")]
                per_slug.setdefault(slug, {}).setdefault(day, {
                    "date": day, "engine_revision": m.group(1), "url": asset_url(r["tag_name"], name), "size": a.get("size", 0), "tag": r["tag_name"],
                })
    return {slug: sorted(days.values(), key=lambda b: b["date"], reverse=True) for slug, days in per_slug.items()}


def launcher_release(releases: list[dict]) -> dict | None:
    """The newest RedEngine Games app (`.github/workflows/launcher.yml` releases it as `launcher-v<version>` with one `-setup.exe`), as
    `launcher/latest.json` gives it to the app's self-update: the version, the installer (with the SHA-256 GitHub computed for it) and the
    release notes' bullet points."""
    best = None
    for r in releases:
        m = LAUNCHER_TAG.match(r.get("tag_name", ""))
        if not m or r.get("draft") or r.get("prerelease"):
            continue
        setup = [a for a in r.get("assets", []) if a["name"].endswith("-setup.exe") and (a.get("digest") or "").startswith("sha256:")]
        key = tuple(int(x) for x in m.group(1).split("."))
        if setup and (best is None or key > best[0]):
            a = setup[0]
            best = (key, {
                "version": m.group(1),
                "released": (r.get("published_at") or "")[:10],
                "installer": {"name": a["name"], "size": a["size"], "sha256": a["digest"][len("sha256:"):], "url": asset_url(r["tag_name"], a["name"])},
                "notes": [line[2:].strip() for line in (r.get("body") or "").splitlines() if line.startswith("- ")],
            })
    return best[1] if best else None


def app_box(app: dict | None) -> str:
    if not app:
        return ""
    i = app["installer"]
    return f'''
  <section class="app" id="app">
    <div>
      <h2>Get the RedEngine Games app <span class="tag">New</span></h2>
      <p>One app for every game on this site: browse them, read each game's wiki, and install, play and update any of them with one click. No more installer per game.</p>
      <p class="fine">Windows may warn you once, when you install the app, because it is not code-signed: choose <strong>More info</strong>, then <strong>Run anyway</strong>. Games you install inside the app never show that warning. It installs for you only (no administrator rights) and keeps itself up to date.</p>
    </div>
    <a class="dl" href="{e(i["url"])}">Download the app for Windows<span>version {e(app["version"])} · {human_size(i["size"]) or "under 1 MB"}</span></a>
  </section>'''


def load_games(releases: list[dict]) -> list[dict]:
    history = rt.release_history(releases)
    legacy = legacy_builds(releases)
    meta = json.loads((REPO / "site" / "games-meta.json").read_text())
    pending = set(json.loads((REPO / "site" / "wiki-pending.json").read_text())["pending"])
    wiki_errors = []
    games = []
    for p in rt.load_playables():
        slug = p["slug"]
        versions = history.get(slug, [])
        for v in versions:
            v["installer"]["url"] = asset_url(v["tag"], v["installer"]["name"])
            v["zip"]["url"] = asset_url(v["tag"], v["zip"]["name"])
        if meta.get(slug, {}).get("author", "human") not in AUTHORS:
            raise SystemExit(f"site/games-meta.json: {slug}: author must be one of {sorted(AUTHORS)}")
        old = legacy.get(slug, [])
        if not versions and not old:
            continue
        first = versions[-1]["released"] if versions else old[-1]["date"]
        author = meta.get(slug, {}).get("author", "human")
        page_dir = REPO / "site" / "wiki" / slug
        page = None
        if (page_dir / "wiki.json").is_file():
            page = json.loads((page_dir / "wiki.json").read_text())
            wiki_errors += [f"{slug}: {m}" for m in wiki.problems(page, author, page_dir)]
            if slug in pending:
                wiki_errors.append(f"{slug}: has a wiki page, so remove it from site/wiki-pending.json")
        elif slug not in pending:
            wiki_errors.append(f"{slug}: needs a wiki page (site/wiki/{slug}/wiki.json, see site/wiki.py): every new game has one")
        games.append({
            "wiki": page,
            "slug": slug,
            "name": p["name"],
            "presentation": p.get("kind", "3d"),
            "description": rt.describe(rt.game_directory(p), f"{p['name']}, built with RedEngine."),
            "added": added_date(p, first),
            "online": meta.get(slug, {}).get("online", ""),
            "author": meta.get(slug, {}).get("author", "human"),
            "thumb": f"thumbs/{slug}.png" if (REPO / "site" / "thumbs" / f"{slug}.png").exists() else "",
            "versions": versions,
            "earlier": old,
            "maintainer": p.get("maintainer") or (versions[0].get("maintainer", "") if versions else ""),
            "forked_from": p.get("forked_from") or (versions[-1].get("forked_from") if versions else None),
            "forkable": "" if p.get("binary") else "repo",
        })
    if wiki_errors:
        raise SystemExit("wiki pages are incomplete:\n  " + "\n  ".join(wiki_errors))
    games += upload_games(history, {g["slug"] for g in games} | {p["slug"] for p in rt.load_playables()})
    games.sort(key=lambda g: g["name"].lower())
    games.sort(key=lambda g: g["added"], reverse=True)
    link_families(games)
    return games


def link_families(games: list[dict]) -> None:
    """Each game's `forks` (the games forked from it, oldest first), from the others' `forked_from`. A parent the site does not list keeps its edge
    (the fork's page names it) but links nowhere."""
    by_slug = {g["slug"]: g for g in games}
    for g in games:
        g["forks"] = []
    for g in sorted(games, key=lambda g: (g["added"], g["slug"])):
        parent = (g.get("forked_from") or {}).get("slug")
        if parent in by_slug and parent != g["slug"]:
            by_slug[parent]["forks"].append(g["slug"])


def upload_games(history: dict[str, list[dict]], taken: set[str]) -> list[dict]:
    """The games uploaded ready-made: everything the site shows comes from the newest release's `redengine-release` line. A wiki page in
    `site/wiki/<slug>/` is used when there is one, and is not required (the game was not written here)."""
    games = []
    for slug, versions in history.items():
        latest = versions[0]
        if latest.get("kind") != "upload" or slug in taken:
            continue
        for v in versions:
            v["installer"] = None
            v["zip"]["url"] = asset_url(v["tag"], v["zip"]["name"])
        page_dir = REPO / "site" / "wiki" / slug
        local_thumb = REPO / "site" / "thumbs" / f"{slug}.png"
        games.append({
            "wiki": json.loads((page_dir / "wiki.json").read_text()) if (page_dir / "wiki.json").is_file() else None,
            "slug": slug,
            "name": latest["name"],
            "presentation": latest.get("presentation", "3d"),
            "description": latest.get("description", ""),
            "added": versions[-1]["released"],
            "online": latest.get("online", ""),
            "author": latest.get("author", "human") if latest.get("author") in AUTHORS else "human",
            "thumb": f"thumbs/{slug}.png" if local_thumb.exists() else "",
            "thumb_url": "" if local_thumb.exists() else latest.get("thumb_url", ""),
            "uploaded": True,
            "versions": versions,
            "earlier": [],
            "maintainer": latest.get("maintainer", ""),
            "forked_from": next((v["forked_from"] for v in reversed(versions) if v.get("forked_from")), None),
            "forkable": "app",
        })
    return games


def fetch_upload_thumbs(games: list[dict], thumbs: Path) -> None:
    """Copy each uploaded game's screenshot from its release into the site, which is where the app may load pictures from (its CSP). A
    screenshot that cannot be fetched leaves the game without one rather than failing the site."""
    import urllib.request
    for g in games:
        url = g.pop("thumb_url", "")
        if not url:
            continue
        name = f'{g["slug"]}{Path(url).suffix.lower()}'
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                (thumbs / name).write_bytes(r.read())
            g["thumb"] = f"thumbs/{name}"
        except OSError as err:
            print(f"warning: {g['slug']}: screenshot not fetched ({err})", file=sys.stderr)


def download(v: dict) -> dict:
    """What a version's main button downloads: the installer, or the portable ZIP for a game that has none."""
    return v["installer"] or v["zip"]


# ---- pages ----------------------------------------------------------------------------------------------------------------------------------


def css() -> str:
    c = PALETTE
    return wiki.WIKI_CSS + f'''
:root {{ --accent: {c["accent"]}; --bg: {c["background"]}; --surface: {c["surface"]}; --card: {c["card"]}; --muted: {c["muted"]}; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: #F3E6EC; font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }}
a {{ color: var(--accent); }}
main {{ max-width: 1100px; margin: 0 auto; padding: 0 16px 48px; }}
header.site {{ padding: 28px 16px 4px; max-width: 1100px; margin: 0 auto; }}
header.site h1 {{ margin: 0; font-size: 1.7rem; }}
header.site h1 span {{ color: var(--accent); }}
header.site h1 a {{ color: inherit; text-decoration: none; }}
header.site p {{ margin: 4px 0 0; color: var(--muted); }}
.start {{ background: var(--surface); border: 1px solid var(--card); border-radius: 8px; padding: 14px 18px; margin: 20px 0; }}
.start h2 {{ margin: 0 0 8px; font-size: 1.05rem; }}
.start ol {{ margin: 0 0 8px; padding-left: 22px; }}
.start .fine {{ color: var(--muted); font-size: .85rem; margin: 6px 0 0; }}
.toolbar {{ display: flex; gap: 10px; flex-wrap: wrap; align-items: center; margin: 18px 0 14px; }}
.toolbar input, .toolbar select {{ background: var(--surface); color: inherit; border: 1px solid var(--card); border-radius: 6px; padding: 8px 10px; font: inherit; }}
.toolbar input {{ flex: 1; min-width: 180px; }}
.toolbar .count {{ color: var(--muted); font-size: .9rem; margin-left: auto; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); gap: 16px; }}
.game {{ background: var(--card); border-radius: 8px; overflow: hidden; display: flex; flex-direction: column; position: relative; }}
.game.fav {{ box-shadow: 0 0 0 2px var(--accent); }}
.heart {{ position: absolute; top: 8px; right: 8px; z-index: 2; width: 38px; height: 38px; border-radius: 50%; border: 0; background: rgba(20, 8, 14, .72); color: #F3E6EC; font-size: 1.35rem; line-height: 1; cursor: pointer; display: flex; align-items: center; justify-content: center; }}
.heart:hover {{ background: rgba(20, 8, 14, .9); }}
.heart[aria-pressed="true"] {{ color: var(--accent); }}
.by {{ border-radius: 4px; padding: 0 6px; font-weight: 700; border: 1px solid var(--accent); color: var(--accent); }}
.by.ai {{ background: transparent; }}
.by.human {{ border-color: var(--muted); color: var(--muted); }}
.pres {{ background: var(--accent); color: #1C0810; border-radius: 4px; padding: 0 6px; font-weight: 700; }}
.thumb {{ width: 100%; height: auto; aspect-ratio: 16/9; object-fit: cover; display: block; background: var(--surface); }}
.thumb-missing {{ display: flex; align-items: center; justify-content: center; color: var(--muted); font-size: .85rem; }}
.game .body {{ padding: 12px 14px 14px; display: flex; flex-direction: column; flex: 1; gap: 6px; }}
.game h3 {{ margin: 0; font-size: 1.1rem; }}
.game h3 a {{ color: inherit; text-decoration: none; }}
.meta {{ margin: 0; color: var(--muted); font-size: .8rem; display: flex; gap: 10px; flex-wrap: wrap; }}
.online {{ margin: 0; font-size: .8rem; color: var(--accent); }}
.desc {{ margin: 0; font-size: .9rem; color: #E8D3DC; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }}
.dl {{ display: block; text-align: center; background: var(--accent); color: #1C0810; font-weight: 600; text-decoration: none; border-radius: 6px; padding: 10px; }}
.dl:hover {{ filter: brightness(1.1); }}
.app {{ display: flex; gap: 22px; align-items: center; flex-wrap: wrap; background: linear-gradient(100deg, #4A1428, var(--surface)); border: 1px solid var(--accent); border-radius: 8px; padding: 16px 20px; margin: 20px 0; }}
.app > div {{ flex: 1; min-width: 260px; }}
.app h2 {{ margin: 0 0 6px; font-size: 1.2rem; }}
.app p {{ margin: 0 0 6px; }}
.app .fine {{ color: var(--muted); font-size: .85rem; }}
.app .dl {{ padding: 12px 22px; font-size: 1.05rem; }}
.app .dl span {{ display: block; font-weight: 500; font-size: .8rem; }}
.card-links {{ margin-top: auto; padding-top: 6px; display: flex; gap: 14px; font-size: .85rem; justify-content: center; }}
.hidden {{ display: none; }}
.hero {{ display: grid; grid-template-columns: minmax(240px, 420px) 1fr; gap: 22px; margin: 22px 0; align-items: start; }}
@media (max-width: 760px) {{ .hero {{ grid-template-columns: 1fr; }} }}
.hero .thumb {{ border-radius: 8px; }}
.hero h2 {{ margin: 0 0 6px; }}
.hero .dl {{ display: inline-block; padding: 12px 22px; margin: 8px 0 4px; }}
table.versions {{ width: 100%; border-collapse: collapse; margin: 8px 0 24px; font-size: .92rem; }}
table.versions th, table.versions td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--card); vertical-align: top; }}
table.versions th {{ color: var(--muted); font-weight: 500; font-size: .8rem; }}
table.versions code {{ word-break: break-all; font-size: .72rem; color: var(--muted); }}
table.versions ul {{ margin: 0; padding-left: 18px; }}
.tag {{ background: var(--accent); color: #1C0810; border-radius: 4px; padding: 1px 6px; font-size: .75rem; font-weight: 600; }}
details {{ margin: 10px 0; }}
summary {{ cursor: pointer; color: var(--muted); }}
.family {{ background: var(--surface); border-radius: 8px; padding: 6px 18px 10px; margin: 18px 0; }}
.family h2 {{ font-size: 1.1rem; display: flex; gap: 14px; align-items: baseline; }}
.family .fine, .who {{ color: var(--muted); font-size: .85rem; }}
.family pre.prompt {{ white-space: pre-wrap; background: var(--card); border-radius: 6px; padding: 10px 12px; font-size: .85rem; user-select: all; }}
ul.tree, ul.tree ul {{ list-style: none; margin: 4px 0; padding-left: 20px; border-left: 2px solid var(--card); }}
ul.tree {{ border-left: 0; padding-left: 0; }}
ul.tree li {{ margin: 6px 0; }}
footer {{ margin-top: 36px; padding-top: 14px; border-top: 1px solid var(--card); color: var(--muted); font-size: .85rem; }}
footer p {{ margin: 4px 0; }}
'''


def shell(title: str, description: str, body: str, depth: int, script: str = "") -> str:
    up = "../" * depth
    repo_url = f"https://github.com/{CONFIG['repository']}"
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<style>{css()}</style>
</head>
<body>
<header class="site">
  <h1><a href="{up or "./"}"><span>Red</span>EngineGames</a></h1>
  <p>Free Windows games built on <a href="https://github.com/kevstermcgee/RedEngine">RedEngine</a>. Download and install for Windows. · <a href="{up}family/">Game families</a> · <a href="{up}feedback/">Engine feedback</a></p>
</header>
<main>
{body}
  <footer>
    <p>Online games: one player hosts (or a shared server runs the game) and friends join with the host’s address and join key — ask the host for those; they are never published here.</p>
    <p>Source &amp; issues: <a href="{repo_url}">{CONFIG["repository"]}</a> · every version ever released stays downloadable.</p>
  </footer>
</main>
{script}
</body>
</html>
'''


def signed_note(games: list[dict]) -> str:
    latest = [g["versions"][0] for g in games if g["versions"] and g["versions"][0]["installer"]]
    if latest and all(v.get("signed") for v in latest):
        return ""
    return ('<p class="fine">These installers are not code-signed yet, so Windows may say “Windows protected your PC”: choose '
            '<strong>More info</strong>, then <strong>Run anyway</strong>. The SHA-256 of every file is listed with it.</p>')


def by_badge(g: dict) -> str:
    return f'<span class="by {e(g["author"])}" title="{"Designed by an AI on its own" if g["author"] == "ai" else "Designed by a person"}">{AUTHORS[g["author"]]}</span>'


def card(g: dict, index: int) -> str:
    v = g["versions"][0] if g["versions"] else None
    loading = "eager" if index < 6 else "lazy"
    thumb = (f'<img class="thumb" src="{e(g["thumb"])}" alt="{e(g["name"])} screenshot" loading="{loading}" width="640" height="360">'
             if g["thumb"] else '<div class="thumb thumb-missing">no screenshot</div>')
    online = f'<p class="online" title="{e(g["online"])}">&#x1F310; online multiplayer</p>' if g["online"] else ""
    page = f'games/{g["slug"]}/'
    count = len(g["versions"]) + len(g["earlier"])
    if v:
        meta = f'<span>version {v["version"]}</span><span>{e(v["released"])}</span><span>{human_size(download(v)["size"])}</span>'
        if v["installer"]:
            button = f'<a class="dl" href="{e(v["installer"]["url"])}">Install for Windows</a>'
            links = f'<a href="{e(v["zip"]["url"])}">portable ZIP</a><a href="{page}">all versions ({count})</a>'
        else:
            button = f'<a class="dl" href="{e(v["zip"]["url"])}">Download ZIP for Windows</a>'
            links = f'<a href="#app">get it in the app</a><a href="{page}">all versions ({count})</a>'
        size = download(v)["size"]
    else:
        o = g["earlier"][0]
        meta = f'<span>build of {e(o["date"])}</span><span>{human_size(o["size"])}</span>'
        button = f'<a class="dl" href="{e(o["url"])}">Download ZIP</a>'
        links = f'<a href="{page}">all builds ({count})</a>'
        size = o["size"]
    return f'''
<article class="game" data-id="win:{e(g["slug"])}" data-pres="{e(g["presentation"])}" data-author="{e(g["author"])}" data-name="{e(g["name"].lower())}" data-added="{e(g["added"])}" data-size="{size or 0}" data-text="{e((g["name"] + " " + g["description"]).lower())}">
  {thumb}
  <button class="heart" type="button" aria-pressed="false" aria-label="Favourite {e(g["name"])}" title="Favourite: keep it at the top of your feed">&#x2661;</button>
  <div class="body">
    <h3><a href="{page}">{e(g["name"])}</a></h3>{f'<p class="meta">fork of <a href="games/{e(g["forked_from"]["slug"])}/">{e(g["forked_from"]["slug"])}</a> v{int(g["forked_from"].get("version") or 0)}</p>' if g.get("forked_from") else ""}
    <p class="meta"><span class="pres">{e(g["presentation"].upper())}</span>{by_badge(g)}{meta}</p>
    {online}
    <p class="desc">{e(g["description"])}</p>
    {button}
    <div class="card-links">{links}</div>
  </div>
</article>'''


FILTER_JS = '''<script>
(function () {
  var q = document.getElementById("q"), sort = document.getElementById("sort"), kind = document.getElementById("kind"), pres = document.getElementById("pres"), who = document.getElementById("who"),
      grid = document.getElementById("games"), count = document.getElementById("count");
  var cards = Array.prototype.slice.call(grid.querySelectorAll(".game"));
  var KEY = "redengine:hearts";
  function load() { try { var v = JSON.parse(localStorage.getItem(KEY) || "[]"); return Array.isArray(v) ? v : []; } catch (e) { return []; } }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(favs)); } catch (e) { /* private mode: the hearts last until the page closes */ } }
  var favs = load();
  function isFav(c) { return favs.indexOf(c.dataset.id) !== -1; }
  function paint() {
    cards.forEach(function (c) {
      var f = isFav(c), b = c.querySelector(".heart");
      c.classList.toggle("fav", f);
      if (b) { b.setAttribute("aria-pressed", f ? "true" : "false"); b.textContent = f ? "♥" : "♡"; }
    });
  }
  // A hybrid game has 2D and 3D parts, so it shows under both filters.
  function presOk(c) { var p = pres.value; return !p || c.dataset.pres === p || c.dataset.pres === "hybrid"; }
  function apply() {
    var needle = q.value.trim().toLowerCase();
    var parts = sort.value.split("-"), key = parts[0], dir = parts[1] === "desc" ? -1 : 1;
    cards.sort(function (a, b) {
      var av, bv;
      if (key === "size") { av = +a.dataset.size; bv = +b.dataset.size; } else { av = a.dataset[key]; bv = b.dataset[key]; }
      if (av < bv) return -dir;
      if (av > bv) return dir;
      return a.dataset.name < b.dataset.name ? -1 : 1;
    });
    // Favourites first, each group in the chosen order (the sort above is stable).
    cards.sort(function (a, b) { return (isFav(b) ? 1 : 0) - (isFav(a) ? 1 : 0); });
    var shown = 0;
    cards.forEach(function (c) {
      var ok = (!needle || c.dataset.text.indexOf(needle) !== -1) && (kind.value !== "online" || c.querySelector(".online")) && (kind.value !== "fav" || isFav(c)) && presOk(c) && (!who.value || c.dataset.author === who.value);
      c.classList.toggle("hidden", !ok);
      if (ok) shown++;
      grid.appendChild(c);
    });
    var hearts = cards.filter(isFav).length;
    count.textContent = shown + " of " + cards.length + " games" + (hearts ? " · " + hearts + " ♥" : "");
  }
  function applyAndShare() {
    apply();
    var p = new URLSearchParams();
    if (q.value.trim()) p.set("q", q.value.trim());
    if (sort.value !== "added-desc") p.set("sort", sort.value);
    if (kind.value) p.set("kind", kind.value);
    if (pres.value) p.set("pres", pres.value);
    if (who.value) p.set("by", who.value);
    var qs = p.toString();
    history.replaceState(null, "", qs ? "?" + qs : location.pathname);
  }
  grid.addEventListener("click", function (ev) {
    var b = ev.target.closest ? ev.target.closest(".heart") : null;
    if (!b) return;
    ev.preventDefault();
    var id = b.closest(".game").dataset.id, i = favs.indexOf(id);
    if (i === -1) favs.push(id); else favs.splice(i, 1);
    save(); paint(); apply();
  });
  window.addEventListener("storage", function (ev) { if (ev.key === KEY) { favs = load(); paint(); apply(); } });
  q.addEventListener("input", applyAndShare);
  sort.addEventListener("change", applyAndShare);
  kind.addEventListener("change", applyAndShare);
  pres.addEventListener("change", applyAndShare);
  who.addEventListener("change", applyAndShare);
  var init = new URLSearchParams(location.search);
  if (init.get("q")) q.value = init.get("q");
  if (init.get("sort")) sort.value = init.get("sort");
  if (init.get("kind")) kind.value = init.get("kind");
  if (init.get("pres")) pres.value = init.get("pres");
  if (init.get("by")) who.value = init.get("by");
  paint();
  apply();
})();
</script>'''


def index_page(games: list[dict], app: dict | None = None) -> str:
    cards = "\n".join(card(g, i) for i, g in enumerate(games))
    body = f'''{app_box(app)}
  <section class="start">
    <h2>Getting started</h2>
    <ol>
      <li><strong>Install</strong> a Windows game: download its installer and run it. It needs no administrator rights and offers a desktop shortcut.</li>
      <li><strong>Play</strong> from the Start menu or the shortcut. Most games support a gamepad; several players can share one screen where a game allows it.</li>
      <li><strong>Updates:</strong> games with an updater offer new versions automatically. Update Date Night Arcade games by running the latest installer; their separate save profiles are retained.</li>
    </ol>
    <p class="fine"><strong>Who designed it?</strong> Every game is labelled <em>Human-designed</em> or <em>AI-designed</em>. AI-designed games are invented and built by an AI on its own, a new one most days, so they vary in quality; use the “Designed by” filter to see only one kind. Tap the heart on a game to keep it at the top of your feed (it is remembered in this browser). Every game keeps all its earlier versions: open a game’s “all versions” page to install an older one.</p>
    {signed_note(games)}
  </section>
  <div class="toolbar">
    <input id="q" type="search" placeholder="Filter by name or description…" aria-label="Filter games">
    <select id="sort" aria-label="Sort games">
      <option value="added-desc" selected>Newest first</option>
      <option value="added-asc">Oldest first</option>
      <option value="name-asc">Name A–Z</option>
      <option value="name-desc">Name Z–A</option>
      <option value="size-asc">Smallest first</option>
    </select>
    <select id="pres" aria-label="2D or 3D">
      <option value="" selected>2D and 3D</option>
      <option value="2d">2D</option>
      <option value="3d">3D</option>
    </select>
    <select id="who" aria-label="Designed by">
      <option value="" selected>Human and AI designed</option>
      <option value="human">Human-designed</option>
      <option value="ai">AI-designed</option>
    </select>
    <select id="kind" aria-label="Show">
      <option value="" selected>All games</option>
      <option value="fav">&#x2665; Favourites</option>
      <option value="online">Online multiplayer</option>
    </select>
    <span class="count" id="count"></span>
  </div>
  <section class="grid" id="games">
{cards}
  </section>'''
    return shell("RedEngineGames — free Windows games", "Free Windows games built on RedEngine. Install in a click; every version stays available.", body, 0, FILTER_JS)


def version_rows(g: dict) -> str:
    rows = []
    for i, v in enumerate(g["versions"]):
        notes = "".join(f"<li>{e(n)}</li>" for n in v["notes"]) or f'<li>Built with RedEngine {e(v.get("engine_revision", "")[:12])}</li>'
        latest = ' <span class="tag">latest</span>' if i == 0 else ""
        rows.append(f'''<tr>
  <td><strong>{v["version"]}</strong>{latest}<br><span class="meta">{e(v["released"])}</span></td>
  <td><ul>{notes}</ul></td>
  <td>{f'<a href="{e(v["installer"]["url"])}">Installer</a> ({human_size(v["installer"]["size"])})<br><code>{e(v["installer"]["sha256"])}</code>' if v["installer"] else "none: unzip and play, or use the app"}</td>
  <td><a href="{e(v["zip"]["url"])}">Portable ZIP</a> ({human_size(v["zip"]["size"])})<br><code>{e(v["zip"]["sha256"])}</code></td>
</tr>''')
    return "\n".join(rows)


def review_settings(g: dict) -> dict | None:
    """What a game's review form needs (`wiki.reviews_section`): where to send a review and where to read them (`distribution/config.json`)."""
    r = CONFIG.get("reviews")
    if not r or not g["versions"]:
        return None
    return {"game": g["slug"], "name": g["name"], "version": g["versions"][0]["version"], "send": r["send"], "read": r["read"]}


def game_page(g: dict, app: dict | None = None, by_slug: dict | None = None) -> str:
    v = g["versions"][0] if g["versions"] else None
    thumb = f'<img class="thumb" src="../../{e(g["thumb"])}" alt="{e(g["name"])} screenshot" width="640" height="360">' if g["thumb"] else ""
    online = f'<p class="online">&#x1F310; online multiplayer</p>' if g["online"] else ""
    hero_button = (f'<a class="dl" href="{e(download(v)["url"])}">{"Install" if v["installer"] else "Download"} version {v["version"]}</a>'
                   f'<p class="meta"><span>{e(v["released"])}</span><span>{human_size(download(v)["size"])}</span></p>' if v else "")
    table = ""
    if g["versions"]:
        table = f'''
  <h2>All versions</h2>
  <p class="fine">{"Every version stays downloadable; the app installs the newest." if g.get("uploaded") else "Installing an older version over a newer one works. The game will then offer the newest version when it starts: choose <em>Cancel</em> (“skip this version”) to stay on the one you chose."}</p>
  <table class="versions">
    <tr><th>Version</th><th>What changed</th><th>Installer (recommended)</th><th>Portable</th></tr>
{version_rows(g)}
  </table>'''
    earlier = ""
    if g["earlier"]:
        items = "".join(
            f'<tr><td>{e(b["date"])}</td><td>RedEngine {e(b["engine_revision"][:12])}</td><td><a href="{e(b["url"])}">ZIP</a> ({human_size(b["size"])})</td></tr>'
            for b in g["earlier"])
        earlier = f'''
  <details {"open" if not g["versions"] else ""}>
    <summary>Earlier builds ({len(g["earlier"])}) from before installers: ZIP only, the newest of each day</summary>
    <table class="versions"><tr><th>Date</th><th>Engine</th><th>Download</th></tr>{items}</table>
  </details>'''
    body = f'''
  <p><a href="../../">&larr; all games</a></p>
  <section class="hero">
    {thumb}
    <div>
      <h2>{e(g["name"])}</h2>
      <p class="meta">{by_badge(g)}</p>
      {online}
      <p>{e(g["description"])}</p>
      {hero_button}
      {uploaded_note(g, v) if g.get("uploaded") else f'''<p class="fine">An installed game checks for updates when it starts and installs them in place; your saved games stay in <code>Saved Games\\{e(rt.clean_name(g["name"]))}</code>.</p>
      {signed_note([g])}'''}
      {'<p class="fine">Or get it in the <a href="../../#app">RedEngine Games app</a>, which installs and updates every game for you.</p>' if app and v and not g.get("uploaded") else ""}
    </div>
  </section>{family_section(g, by_slug or {g["slug"]: g})}{wiki.render(g["wiki"], g["author"], review_settings(g)) if g["wiki"] else '<p class="soon">This game has no wiki page yet: its rules, story, characters and pictures are still to be written.</p>'}{table}{earlier}'''
    return shell(f'{g["name"]} — RedEngineGames', g["description"], body, 2)


def game_link(slug: str, by_slug: dict, depth: int = 2) -> str:
    g = by_slug.get(slug)
    if not g:
        return f"<code>{e(slug)}</code>"
    who = f' <span class="who">by @{e(g["maintainer"])}</span>' if g.get("maintainer") else ""
    return f'<a href="{"../" * depth}games/{e(slug)}/">{e(g["name"])}</a>{who}'


def root_of(g: dict, by_slug: dict) -> str:
    """The original a game's family starts from (the game itself when it is not a fork of a listed game)."""
    seen = set()
    while (g.get("forked_from") or {}).get("slug") in by_slug and g["slug"] not in seen:
        seen.add(g["slug"])
        g = by_slug[g["forked_from"]["slug"]]
    return g["slug"]


def fork_prompt(g: dict) -> str:
    """What to paste into an AI session (Claude Code in a RedEngine checkout) to fork this game: the command copies it; the person says what changes."""
    v = g["versions"][0]["version"] if g["versions"] else 1
    return (f'Fork the RedEngine game "{g["name"]}" (version {v}) into a game of my own called "MY GAME". In a RedEngine checkout run\n'
            f'  python3 scripts/games.py fork {g["slug"]}@v{v} my-game --name "MY GAME"\n'
            "then make the changes below, check it, finish its page (every TODO(fork)) and send it in one pull request (CONTRIBUTING.md).\n\n"
            "What I want different: ")


def family_section(g: dict, by_slug: dict) -> str:
    """Where the game came from, what came of it, and how to make your own version of it."""
    parts = []
    parent = g.get("forked_from")
    if parent:
        parts.append(f'<p>Forked from {game_link(parent["slug"], by_slug)}, version {int(parent.get("version") or 0) or "?"}.</p>')
    if g.get("forks"):
        parts.append("<p>Forks: " + " · ".join(game_link(s, by_slug) for s in g["forks"]) + "</p>")
    if g.get("forkable") == "repo":
        how = ('<p>A fork is a new game, with its own page and versions, that remembers it came from this one. Ask an AI (Claude Code in a '
               '<a href="https://github.com/kevstermcgee/RedEngine">RedEngine</a> checkout) with the text below after saying what you want different, '
               'or press <strong>Fork</strong> on this game in the RedEngine Games app.</p>'
               f'<pre class="prompt">{e(fork_prompt(g))}</pre>')
    elif g.get("forkable") == "app":
        how = "<p>Press <strong>Fork</strong> on this game in the RedEngine Games app, change the copy it makes, and publish it as your version.</p>"
    else:
        how = ('<p>This game plays with its own client, which is engine code: fork it as code, in a pull request to '
               '<a href="https://github.com/kevstermcgee/RedEngine">RedEngine</a> that the other maintainer reviews.</p>')
    whole = f' <a class="fine" href="../../family/#{e(root_of(g, by_slug))}">the whole family</a>' if parent or g.get("forks") else ""
    origin = "".join(parts) or '<p class="fine">An original: not made from another game, and not forked yet.</p>'
    return f'''
  <section class="family">
    <h2>Family{whole}</h2>
    {origin}
    <details><summary>Fork this game</summary>{how}</details>
  </section>'''


def family_page(games: list[dict]) -> str:
    """Every family: an original with its forks below it, and their forks below them, each with its newest version and who keeps it."""
    by_slug = {g["slug"]: g for g in games}

    def node(g: dict, seen: set) -> str:
        if g["slug"] in seen:
            return ""
        seen.add(g["slug"])
        v = f'v{g["versions"][0]["version"]}' if g["versions"] else ""
        edge = f' <span class="who">from v{int(g["forked_from"].get("version") or 0)}</span>' if g.get("forked_from") else ""
        kids = "".join(node(by_slug[c], seen) for c in g.get("forks", []))
        return f'<li>{game_link(g["slug"], by_slug, 1)} <span class="who">{v}</span>{edge}{f"<ul>{kids}</ul>" if kids else ""}</li>'

    roots = sorted((g for g in games if g.get("forks") and root_of(g, by_slug) == g["slug"]), key=lambda g: g["name"].lower())
    trees = "".join(f'<section class="family" id="{e(g["slug"])}"><ul class="tree">{node(g, set())}</ul></section>' for g in roots)
    alone = sum(1 for g in games if not g.get("forks") and not g.get("forked_from"))
    body = f'''
  <p><a href="../">&larr; all games</a></p>
  <h2>Game families</h2>
  <p>A fork is a game made from another one: someone took a version of it, changed it and published it as a game of its own. Each family starts with an
    original, with its forks under it and their forks under them. Every version of every game stays downloadable, so each step can still be played.</p>
  {trees or '<p class="soon">No game has been forked yet: open any game and choose “Fork this game”.</p>'}
  <p class="fine">{alone} game(s) have no family yet.</p>'''
    return shell("Game families — RedEngineGames", "Which games were made from which: originals, their forks and forks of forks.", body, 1)


def uploaded_note(g: dict, v: dict | None) -> str:
    if not v:
        return ""
    run = e(v["entry"].rsplit("/", 1)[-1])
    return (f'<p class="fine">A ready-made Windows game, not built with RedEngine. The <a href="../../#app">RedEngine Games app</a> installs it and offers every new '
            f'version; or unzip the download anywhere and run <code>{run}</code>. Windows may say “Windows protected your PC” for a file downloaded '
            'with a browser: choose <strong>More info</strong>, then <strong>Run anyway</strong>.</p>')


def feedback_page() -> str:
    """Notes about the engine itself, not one game: the same form and list as the app's Engine feedback."""
    r = CONFIG.get("reviews")
    form = wiki.engine_feedback_section(r["send"], r["read"]) if r else "<p>Engine feedback is not open right now.</p>"
    body = f'''
  <p><a href="../">&larr; all games</a></p>
  <h2>Engine feedback</h2>
  <p>Notes about <strong>RedEngine</strong> itself rather than one game: how its games feel to play, what the engine could do better, tips for the people
    building it, a bug you keep meeting in several games. Every note is read. (To review a single game, use the form on its page.)</p>{form}'''
    return shell("Engine feedback — RedEngineGames", "Tips, ideas and bugs for the RedEngine game engine.", body, 1)


def latest_json(g: dict) -> str | None:
    """What an installed game fetches to learn whether there is a newer version (a game without an installer has no updater of its own)."""
    if not g["versions"] or not g["versions"][0]["installer"]:
        return None
    v = g["versions"][0]
    return json.dumps({
        "slug": g["slug"],
        "version": v["version"],
        "released": v["released"],
        "installer": v["installer"]["url"],
        "sha256": v["installer"]["sha256"],
        "size": v["installer"]["size"],
        "notes": "\n".join(f"- {n}" for n in v["notes"]),
        "page": f"{CONFIG['site_url']}games/{g['slug']}/",
    }, indent=1) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--releases", required=True, help="JSON from `gh api --paginate repos/<repo>/releases`")
    ap.add_argument("--out", default=str(REPO / "site" / "dist"))
    ap.add_argument("--offline", action="store_true", help="do not fetch uploaded games' screenshots from their releases")
    args = ap.parse_args()

    releases = rt.load_releases(args.releases)
    games = load_games(releases)
    app = launcher_release(releases)
    out = Path(args.out)
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    shutil.copytree(REPO / "site" / "thumbs", out / "thumbs")
    if args.offline:
        for g in games:
            g.pop("thumb_url", None)
    else:
        fetch_upload_thumbs(games, out / "thumbs")
    (out / "index.html").write_text(index_page(games, app), encoding="utf-8")
    (out / "feedback").mkdir()
    (out / "feedback" / "index.html").write_text(feedback_page(), encoding="utf-8")
    (out / "family").mkdir()
    (out / "family" / "index.html").write_text(family_page(games), encoding="utf-8")
    by_slug = {g["slug"]: g for g in games}
    if app:
        (out / "launcher").mkdir()
        (out / "launcher" / "latest.json").write_text(json.dumps(app, indent=1) + "\n", encoding="utf-8")
    for g in games:
        folder = out / "games" / g["slug"]
        folder.mkdir(parents=True)
        (folder / "index.html").write_text(game_page(g, app, by_slug), encoding="utf-8")
        if g["wiki"] and (REPO / "site" / "wiki" / g["slug"]).is_dir():
            for f in (REPO / "site" / "wiki" / g["slug"]).iterdir():
                if f.name != "wiki.json":
                    shutil.copy(f, folder / f.name)
        if (text := latest_json(g)) is not None:
            (folder / "latest.json").write_text(text, encoding="utf-8")
    (out / "catalog.json").write_text(json.dumps({"schema": 2, "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "reviews": CONFIG.get("reviews"), "games": [
        {**{k: g[k] for k in ("slug", "name", "description", "added", "online", "author", "thumb", "wiki", "versions", "earlier", "maintainer", "forked_from", "forks",
                              "forkable")}, "uploaded": bool(g.get("uploaded")), "presentation": g["presentation"]} for g in games]}, indent=1), encoding="utf-8")
    (out / ".nojekyll").write_text("")
    print(f"{len(games)} games -> {out / 'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
