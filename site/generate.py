#!/usr/bin/env python3
"""Generate the RedEngineGames download site into site/dist/.

The site is built from the repository's own list of games and from the GitHub Releases, which are the record of every version ever published
(`distribution/release_tool.py` writes a machine-readable line into each release's notes):

  index.html                   every game: install the latest version, link to all versions
  games/<slug>/index.html      one game: the latest version and the whole history, each with installer, portable ZIP, checksum and what changed
  games/<slug>/latest.json     what an installed game asks to learn whether an update exists
  catalog.json                 everything above as data

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

PALETTE = json.loads((REPO / "site" / "palette.json").read_text())
CONFIG = rt.CONFIG
LEGACY_TAG = re.compile(r"^redengine-([0-9a-f]{7,40})$")
e = html.escape


WEB = REPO / "webgames"


def load_web_games() -> list[dict]:
    """Browser games published by `red_engine2 publish --backend github-pages`: webgames/catalog.json (schema red2d-catalog/1) beside webgames/games/<id>/."""
    catalog = WEB / "catalog.json"
    if not catalog.is_file():
        return []
    return json.loads(catalog.read_text(encoding="utf-8")).get("games", [])


def browser_download(g: dict) -> dict:
    path = REPO / "site" / "browser-downloads.json"
    return json.loads(path.read_text()).get(g["id"], {}) if path.exists() else {}


def browser_game_page(g: dict) -> str:
    play = f'../../play/{g["url"]}'
    download = browser_download(g)
    install = (f'<a class="dl" href="{e(download["url"])}">Install for Windows</a>' if download else f'<a href="{e(play)}">Open the game to install its browser app</a>')
    controls = {
        "pip-cloud-post": "Left/right or stick: steer. A / Space: slam for a super spring. B / Shift: gust away nearby rain.",
        "moxie-magnet-moon": "Arrows / WASD or stick: move and aim. A / Space: magnetic dash. B / Shift: stationary pulse. Watch the recharge meter.",
        "riff-rooftop-rush": "Up/down or D-pad: switch lanes. A / Space: hop. B / Shift: center lane. Jump low speakers; stay grounded beneath high drones.",
    }.get(g["id"], "Use the keyboard, controller or touch controls shown on the game’s start screen.")
    survival = '<h2>Survive, then pass the controller</h2><p>Four hearts. Every 20 seconds, hazards become faster and more frequent. Survive as long as you can, then hand over the controller. Best scores, survival records and player turns save automatically.</p>' if download else ''
    desktop = '<h2>Windows installation</h2><p>Download and run the installer. It installs without administrator rights and adds desktop and Start menu shortcuts. All game files and music are included for offline play. Microsoft Edge opens the game in a dedicated app window. Windows 10 or 11 with Edge is required.</p><p>The installer is unsigned; Windows may show an unknown-publisher prompt. Its checksum is below. Uninstall through Windows Settings → Apps; the separate save profile is retained for reinstalling.</p><p>Browser and desktop saves are separate. Use Back up progress and Restore on the start screen to transfer your records.</p>' if download else '<h2>Browser installation</h2><p>Open the game in Chrome or Edge and use the address-bar install icon or the browser menu’s Apps option. Installation availability depends on your browser. Let offline caching complete before disconnecting.</p>'
    checksum = f'<details><summary>Installer checksum and version</summary><p>Version {e(download.get("version", "2.0"))} · {human_size(download.get("bytes",0))}</p><code style="overflow-wrap:anywhere">SHA-256: {e(download.get("sha256", ""))}</code></details>' if download else ''
    body = f'<p><a href="../../">← All games</a></p><section class="hero"><img class="thumb" src="../../play/{e(g["thumbnail"])}" alt="{e(g["title"])} gameplay" style="image-rendering:pixelated"><div><h2>{e(g["title"])}</h2><p>{e(g["description"])}</p><a class="dl" href="{e(play)}">Play now</a> {install}</div></section>{survival}<h2>Controls</h2><p>{e(controls)}</p><p>F toggles fullscreen. M or controller Start toggles music. A / Space starts the next player’s turn after a run. The small Menu button opens installation and audio controls during play.</p>{desktop}{checksum}'
    return shell(f'{g["title"]} — RedEngineGames', g['description'], body, 2)


def web_card(g: dict) -> str:
    page = f'play/{g["url"]}'
    detail = f'browser/{g["id"]}/'
    download = browser_download(g)
    install = f'<a href="{e(download["url"])}">Install for Windows</a>' if download else ""
    inputs = " + ".join(g.get("input", []))
    pres = g["presentation"]
    return f'''
<article class="game" data-id="web:{e(g["id"])}" data-pres="{e(pres)}" data-name="{e(g["title"].lower())}" data-added="{e(g["build_timestamp"][:10])}" data-size="{int(g.get("package_bytes", 600000))}" data-text="{e((g["title"] + " " + g["description"]).lower())}">
  <a href="{e(page)}"><img class="thumb" src="play/{e(g["thumbnail"])}" alt="{e(g["title"])} screenshot" loading="lazy" width="640" height="360" style="image-rendering:pixelated"></a>
  <button class="heart" type="button" aria-pressed="false" aria-label="Favourite {e(g["title"])}" title="Favourite: keep it at the top of your feed">&#x2661;</button>
  <div class="body">
    <h3><a href="{e(detail)}">{e(g["title"])}</a></h3>
    <p class="meta"><span class="pres">{e(pres.upper())}</span><span>{e(inputs)}</span><span>{e(g["build_timestamp"][:10])}</span></p>
    <p class="desc">{e(g["description"])}</p>
    <a class="dl" href="{e(page)}">Play in your browser</a>
    <div class="card-links"><a href="{e(detail)}">Game page</a>{install}</div>
  </div>
</article>'''


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


def load_games(releases: list[dict]) -> list[dict]:
    history = rt.release_history(releases)
    legacy = legacy_builds(releases)
    meta = json.loads((REPO / "site" / "games-meta.json").read_text())
    games = []
    for p in rt.load_playables():
        slug = p["slug"]
        versions = history.get(slug, [])
        for v in versions:
            v["installer"]["url"] = asset_url(v["tag"], v["installer"]["name"])
            v["zip"]["url"] = asset_url(v["tag"], v["zip"]["name"])
        old = legacy.get(slug, [])
        if not versions and not old:
            continue
        first = versions[-1]["released"] if versions else old[-1]["date"]
        games.append({
            "slug": slug,
            "name": p["name"],
            "description": rt.describe(rt.game_directory(p), f"{p['name']}, built with RedEngine."),
            "added": added_date(p, first),
            "online": meta.get(slug, {}).get("online", ""),
            "thumb": f"thumbs/{slug}.png" if (REPO / "site" / "thumbs" / f"{slug}.png").exists() else "",
            "versions": versions,
            "earlier": old,
        })
    games.sort(key=lambda g: g["name"].lower())
    games.sort(key=lambda g: g["added"], reverse=True)
    return games


# ---- pages ----------------------------------------------------------------------------------------------------------------------------------


def css() -> str:
    c = PALETTE
    return f'''
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
  <p>Free Windows games built on <a href="https://github.com/kevstermcgee/RedEngine">RedEngine</a>. Play in your browser or install for Windows.</p>
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
    latest = [g["versions"][0] for g in games if g["versions"]]
    if latest and all(v.get("signed") for v in latest):
        return ""
    return ('<p class="fine">These installers are not code-signed yet, so Windows may say “Windows protected your PC”: choose '
            '<strong>More info</strong>, then <strong>Run anyway</strong>. The SHA-256 of every file is listed with it.</p>')


def card(g: dict, index: int) -> str:
    v = g["versions"][0] if g["versions"] else None
    loading = "eager" if index < 6 else "lazy"
    thumb = (f'<img class="thumb" src="{e(g["thumb"])}" alt="{e(g["name"])} screenshot" loading="{loading}" width="640" height="360">'
             if g["thumb"] else '<div class="thumb thumb-missing">no screenshot</div>')
    online = f'<p class="online" title="{e(g["online"])}">&#x1F310; online multiplayer</p>' if g["online"] else ""
    page = f'games/{g["slug"]}/'
    count = len(g["versions"]) + len(g["earlier"])
    if v:
        meta = f'<span>version {v["version"]}</span><span>{e(v["released"])}</span><span>{human_size(v["installer"]["size"])}</span>'
        button = f'<a class="dl" href="{e(v["installer"]["url"])}">Install for Windows</a>'
        links = f'<a href="{e(v["zip"]["url"])}">portable ZIP</a><a href="{page}">all versions ({count})</a>'
        size = v["installer"]["size"]
    else:
        o = g["earlier"][0]
        meta = f'<span>build of {e(o["date"])}</span><span>{human_size(o["size"])}</span>'
        button = f'<a class="dl" href="{e(o["url"])}">Download ZIP</a>'
        links = f'<a href="{page}">all builds ({count})</a>'
        size = o["size"]
    return f'''
<article class="game" data-id="win:{e(g["slug"])}" data-pres="3d" data-name="{e(g["name"].lower())}" data-added="{e(g["added"])}" data-size="{size or 0}" data-text="{e((g["name"] + " " + g["description"]).lower())}">
  {thumb}
  <button class="heart" type="button" aria-pressed="false" aria-label="Favourite {e(g["name"])}" title="Favourite: keep it at the top of your feed">&#x2661;</button>
  <div class="body">
    <h3><a href="{page}">{e(g["name"])}</a></h3>
    <p class="meta"><span class="pres">3D</span>{meta}</p>
    {online}
    <p class="desc">{e(g["description"])}</p>
    {button}
    <div class="card-links">{links}</div>
  </div>
</article>'''


FILTER_JS = '''<script>
(function () {
  var q = document.getElementById("q"), sort = document.getElementById("sort"), kind = document.getElementById("kind"), pres = document.getElementById("pres"),
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
      var ok = (!needle || c.dataset.text.indexOf(needle) !== -1) && (kind.value !== "online" || c.querySelector(".online")) && (kind.value !== "fav" || isFav(c)) && presOk(c);
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
  var init = new URLSearchParams(location.search);
  if (init.get("q")) q.value = init.get("q");
  if (init.get("sort")) sort.value = init.get("sort");
  if (init.get("kind")) kind.value = init.get("kind");
  if (init.get("pres")) pres.value = init.get("pres");
  paint();
  apply();
})();
</script>'''


def index_page(games: list[dict], web: list[dict] | None = None) -> str:
    cards = "\n".join([web_card(g) for g in (web or [])] + [card(g, i) for i, g in enumerate(games)])
    body = f'''
  <section class="start">
    <h2>Getting started</h2>
    <ol>
      <li><strong>Play</strong> a browser game with one click, or <strong>install</strong> a Windows game and run the installer. It needs no administrator rights and offers a desktop shortcut.</li>
      <li><strong>Play</strong> from the Start menu or the shortcut. Most games support a gamepad; several players can share one screen where a game allows it.</li>
      <li><strong>Updates:</strong> browser games refresh when online. Native games with an updater offer new versions automatically. Update Date Night Arcade desktop games by running the latest installer; their separate save profiles are retained.</li>
    </ol>
    <p class="fine">Tap the heart on a game to keep it at the top of your feed (it is remembered in this browser). Every game keeps all its earlier versions: open a game’s “all versions” page to install an older one.</p>
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
        notes = "".join(f"<li>{e(n)}</li>" for n in v["notes"]) or f'<li>Built with RedEngine {e(v["engine_revision"][:12])}</li>'
        latest = ' <span class="tag">latest</span>' if i == 0 else ""
        rows.append(f'''<tr>
  <td><strong>{v["version"]}</strong>{latest}<br><span class="meta">{e(v["released"])}</span></td>
  <td><ul>{notes}</ul></td>
  <td><a href="{e(v["installer"]["url"])}">Installer</a> ({human_size(v["installer"]["size"])})<br><code>{e(v["installer"]["sha256"])}</code></td>
  <td><a href="{e(v["zip"]["url"])}">Portable ZIP</a> ({human_size(v["zip"]["size"])})<br><code>{e(v["zip"]["sha256"])}</code></td>
</tr>''')
    return "\n".join(rows)


def game_page(g: dict) -> str:
    v = g["versions"][0] if g["versions"] else None
    thumb = f'<img class="thumb" src="../../{e(g["thumb"])}" alt="{e(g["name"])} screenshot" width="640" height="360">' if g["thumb"] else ""
    online = f'<p class="online">&#x1F310; online multiplayer</p>' if g["online"] else ""
    hero_button = (f'<a class="dl" href="{e(v["installer"]["url"])}">Install version {v["version"]}</a>'
                   f'<p class="meta"><span>{e(v["released"])}</span><span>{human_size(v["installer"]["size"])}</span></p>' if v else "")
    table = ""
    if g["versions"]:
        table = f'''
  <h2>All versions</h2>
  <p class="fine">Installing an older version over a newer one works. The game will then offer the newest version when it starts: choose <em>Cancel</em> (“skip this version”) to stay on the one you chose.</p>
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
      {online}
      <p>{e(g["description"])}</p>
      {hero_button}
      <p class="fine">An installed game checks for updates when it starts and installs them in place; your saved games stay in <code>Saved Games\\{e(rt.clean_name(g["name"]))}</code>.</p>
      {signed_note([g])}
    </div>
  </section>{table}{earlier}'''
    return shell(f'{g["name"]} — RedEngineGames', g["description"], body, 2)


def latest_json(g: dict) -> str | None:
    """What an installed game fetches to learn whether there is a newer version."""
    if not g["versions"]:
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
    args = ap.parse_args()

    games = load_games(rt.load_releases(args.releases))
    out = Path(args.out)
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    shutil.copytree(REPO / "site" / "thumbs", out / "thumbs")
    web = load_web_games()
    if web:
        shutil.copytree(WEB, out / "play")
    (out / "index.html").write_text(index_page(games, web), encoding="utf-8")
    for g in web:
        folder = out / "browser" / g["id"]
        folder.mkdir(parents=True)
        (folder / "index.html").write_text(browser_game_page(g), encoding="utf-8")
    for g in games:
        folder = out / "games" / g["slug"]
        folder.mkdir(parents=True)
        (folder / "index.html").write_text(game_page(g), encoding="utf-8")
        if (text := latest_json(g)) is not None:
            (folder / "latest.json").write_text(text, encoding="utf-8")
    (out / "catalog.json").write_text(json.dumps({"schema": 2, "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "games": [
        {**{k: g[k] for k in ("slug", "name", "description", "added", "online", "versions", "earlier")}, "presentation": "3d"} for g in games],
        "browser_games": [{**g, "url": f'play/{g["url"]}'} for g in web]}, indent=1), encoding="utf-8")
    (out / ".nojekyll").write_text("")
    print(f"{len(games)} games -> {out / 'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
