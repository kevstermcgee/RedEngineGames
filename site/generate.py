#!/usr/bin/env python3
"""Generate the RedEngineGames download site into site/dist/.

Inputs (all produced by the release pipeline or the repo itself):
  - the launcher catalog TSV from the latest release (single source of truth
    for what is listed, shared with RedEngineLauncher.exe)
  - SHA256SUMS.txt and asset sizes from the same release
  - git history for each game's "added" date (the TSV's `created` column is
    the release date, identical for every row)
  - site/games-meta.json for hand-maintained extras (online-multiplayer notes)
  - site/thumbs/<slug>.png thumbnails (rendered by site/gen_thumbs.py)

Output: a single self-contained site/dist/index.html (inline CSS + JS, games
rendered as static HTML so the page works without JS; JS adds sort + filter)
plus dist/thumbs/ and dist/catalog.json.

Usage:
  python3 site/generate.py --catalog cat.tsv --sums SHA256SUMS.txt --sizes sizes.json
"""

import argparse
import html
import json
import re
import shutil
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SLUG_ALIASES = {"prop-hunt-yard": "prop-hunt"}

PALETTE = json.loads((REPO / ".launcher-config.json").read_text())


def game_dir_for(slug: str) -> Path | None:
    name = SLUG_ALIASES.get(slug, slug)
    for root in ("games", "projects"):
        d = REPO / root / name
        if d.is_dir():
            return d
    return None


def added_date(slug: str, fallback: str) -> str:
    d = game_dir_for(slug)
    if d is None:
        return fallback
    out = subprocess.run(
        ["git", "-C", str(REPO), "log", "--reverse", "--format=%ad",
         "--date=short", "--", str(d.relative_to(REPO))],
        capture_output=True, text=True,
    ).stdout.strip().splitlines()
    return out[0] if out else fallback


def human_size(n: int | None) -> str:
    return f"{n / 1024 / 1024:.0f} MB" if n else ""


def load_games(args) -> list[dict]:
    rows = [l.split("\t") for l in Path(args.catalog).read_text().splitlines() if l.strip()]
    head = rows[0]
    sums = {}
    for line in Path(args.sums).read_text().splitlines():
        parts = line.split()
        if len(parts) == 2:
            sums[parts[1]] = parts[0]
    sizes = {a["name"]: a["size"] for a in json.loads(Path(args.sizes).read_text())}
    meta = json.loads((REPO / "site" / "games-meta.json").read_text())

    games = []
    for row in rows[1:]:
        g = dict(zip(head, row))
        # Descriptions come from READMEs and can carry markdown links.
        g["description"] = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", g["description"])
        asset_name = g["asset"].rsplit("/", 1)[-1]
        g["added"] = added_date(g["slug"], g["created"])
        g["size_bytes"] = sizes.get(asset_name)
        g["size"] = human_size(g["size_bytes"])
        g["sha256"] = sums.get(asset_name, "")
        g["online"] = meta.get(g["slug"], {}).get("online", "")
        g["thumb"] = f"thumbs/{g['slug']}.png" if (REPO / "site" / "thumbs" / f"{g['slug']}.png").exists() else ""
        games.append(g)
    # Default order: newest first; alphabetical within the same date.
    games.sort(key=lambda g: g["name"].lower())
    games.sort(key=lambda g: g["added"], reverse=True)
    return games


def card(g: dict, index: int) -> str:
    e = html.escape
    loading = "eager" if index < 6 else "lazy"
    thumb = (
        f'<img class="thumb" src="{e(g["thumb"])}" alt="{e(g["name"])} screenshot" loading="{loading}" width="640" height="360">'
        if g["thumb"] else '<div class="thumb thumb-missing">no screenshot</div>'
    )
    online = (
        f'<p class="online" title="{e(g["online"])}">&#x1F310; online multiplayer</p>'
        if g["online"] else ""
    )
    sha = (
        f'<details class="sha"><summary>SHA-256</summary><code>{e(g["sha256"])}</code></details>'
        if g["sha256"] else ""
    )
    size = f'<span>{e(g["size"])}</span>' if g["size"] else ""
    return f'''
<article class="game" data-name="{e(g["name"].lower())}" data-added="{e(g["added"])}"
         data-size="{g["size_bytes"] or 0}" data-text="{e((g["name"] + " " + g["description"]).lower())}">
  {thumb}
  <div class="body">
    <h3>{e(g["name"])}</h3>
    <p class="meta"><span>added {e(g["added"])}</span>{size}<span>engine {e(g["engine_version"][:12])}</span></p>
    {online}
    <p class="desc">{e(g["description"])}</p>
    {sha}
    <a class="dl" href="{e(g["asset"])}">Download for Windows</a>
  </div>
</article>'''


def page(games: list[dict], generated: str) -> str:
    cards = "\n".join(card(g, i) for i, g in enumerate(games))
    c = PALETTE
    repo_url = f"https://github.com/{c['repository']}"
    latest = f"{repo_url}/releases/latest"
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RedEngineGames — free Windows games</title>
<meta name="description" content="Free Windows games built on RedEngine. Download a ZIP, extract, play.">
<style>
:root {{
  --accent: {c["accent"]}; --bg: {c["background"]}; --surface: {c["surface"]};
  --card: {c["card"]}; --muted: {c["muted"]};
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: #F3E6EC;
       font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }}
a {{ color: var(--accent); }}
main {{ max-width: 1100px; margin: 0 auto; padding: 0 16px 48px; }}
header.site {{ padding: 28px 16px 4px; max-width: 1100px; margin: 0 auto; }}
header.site h1 {{ margin: 0; font-size: 1.7rem; }}
header.site h1 span {{ color: var(--accent); }}
header.site p {{ margin: 4px 0 0; color: var(--muted); }}
.start {{ background: var(--surface); border: 1px solid var(--card); border-radius: 8px;
          padding: 14px 18px; margin: 20px 0; }}
.start h2 {{ margin: 0 0 8px; font-size: 1.05rem; }}
.start ol {{ margin: 0 0 8px; padding-left: 22px; }}
.start .fine {{ color: var(--muted); font-size: .85rem; margin: 0; }}
.toolbar {{ display: flex; gap: 10px; flex-wrap: wrap; align-items: center; margin: 18px 0 14px; }}
.toolbar input, .toolbar select {{ background: var(--surface); color: inherit;
  border: 1px solid var(--card); border-radius: 6px; padding: 8px 10px; font: inherit; }}
.toolbar input {{ flex: 1; min-width: 180px; }}
.toolbar .count {{ color: var(--muted); font-size: .9rem; margin-left: auto; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); gap: 16px; }}
.game {{ background: var(--card); border-radius: 8px; overflow: hidden; display: flex; flex-direction: column; }}
.thumb {{ width: 100%; height: auto; aspect-ratio: 16/9; object-fit: cover; display: block; background: var(--surface); }}
.thumb-missing {{ display: flex; align-items: center; justify-content: center; color: var(--muted); font-size: .85rem; }}
.game .body {{ padding: 12px 14px 14px; display: flex; flex-direction: column; flex: 1; gap: 6px; }}
.game h3 {{ margin: 0; font-size: 1.1rem; }}
.meta {{ margin: 0; color: var(--muted); font-size: .8rem; display: flex; gap: 10px; flex-wrap: wrap; }}
.online {{ margin: 0; font-size: .8rem; color: var(--accent); }}
.desc {{ margin: 0; font-size: .9rem; color: #E8D3DC; display: -webkit-box;
         -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }}
.sha {{ font-size: .75rem; color: var(--muted); }}
.sha code {{ word-break: break-all; }}
.dl {{ margin-top: auto; display: block; text-align: center; background: var(--accent); color: #1C0810;
       font-weight: 600; text-decoration: none; border-radius: 6px; padding: 10px; }}
.dl:hover {{ filter: brightness(1.1); }}
footer {{ margin-top: 36px; padding-top: 14px; border-top: 1px solid var(--card);
          color: var(--muted); font-size: .85rem; }}
footer p {{ margin: 4px 0; }}
.hidden {{ display: none; }}
</style>
</head>
<body>
<header class="site">
  <h1><span>Red</span>EngineGames</h1>
  <p>Free Windows games built on <a href="https://github.com/kevstermcgee/RedEngine">RedEngine</a>. No installer, no account — download, extract, play.</p>
</header>
<main>
  <section class="start">
    <h2>Getting started</h2>
    <ol>
      <li><strong>Download</strong> a game below (Windows x64 ZIP).</li>
      <li><strong>Extract</strong> the ZIP anywhere.</li>
      <li><strong>Double-click</strong> the <code>Play-*.exe</code> inside. Most games support a gamepad.</li>
    </ol>
    <p class="fine">The builds are not code-signed, so Windows SmartScreen may warn — choose
    “More info” → “Run anyway”. Checksums for every ZIP are in
    <a href="{latest}/download/SHA256SUMS.txt">SHA256SUMS.txt</a>.</p>
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
    <select id="kind" aria-label="Show">
      <option value="" selected>All games</option>
      <option value="online">Online multiplayer</option>
    </select>
    <span class="count" id="count"></span>
  </div>
  <section class="grid" id="games">
{cards}
  </section>
  <footer>
    <p>Prefer an installer-style experience? The
      <a href="{latest}/download/RedEngineLauncher-windows-x64.zip">RedEngine desktop launcher</a>
      lists every game and installs them for you.</p>
    <p>Online games: one player hosts (or a shared server runs the game) and friends join with the
      host’s address and join key — ask the host for those; they are never published here.</p>
    <p>Source &amp; issues: <a href="{repo_url}">{c["repository"]}</a> ·
      <a href="{latest}">latest release</a> · page generated {generated}.</p>
  </footer>
</main>
<script>
(function () {{
  var q = document.getElementById("q"), sort = document.getElementById("sort"),
      kind = document.getElementById("kind"), grid = document.getElementById("games"),
      count = document.getElementById("count");
  var cards = Array.prototype.slice.call(grid.querySelectorAll(".game"));
  function apply() {{
    var needle = q.value.trim().toLowerCase();
    var parts = sort.value.split("-"), key = parts[0], dir = parts[1] === "desc" ? -1 : 1;
    cards.sort(function (a, b) {{
      var av, bv;
      if (key === "size") {{ av = +a.dataset.size; bv = +b.dataset.size; }}
      else {{ av = a.dataset[key]; bv = b.dataset[key]; }}
      if (av < bv) return -dir;
      if (av > bv) return dir;
      return a.dataset.name < b.dataset.name ? -1 : 1;
    }});
    var shown = 0;
    cards.forEach(function (c) {{
      var ok = (!needle || c.dataset.text.indexOf(needle) !== -1) &&
               (kind.value !== "online" || c.querySelector(".online"));
      c.classList.toggle("hidden", !ok);
      if (ok) shown++;
      grid.appendChild(c);
    }});
    count.textContent = shown + " of " + cards.length + " games";
  }}
  function applyAndShare() {{
    apply();
    var p = new URLSearchParams();
    if (q.value.trim()) p.set("q", q.value.trim());
    if (sort.value !== "added-desc") p.set("sort", sort.value);
    if (kind.value) p.set("kind", kind.value);
    var qs = p.toString();
    history.replaceState(null, "", qs ? "?" + qs : location.pathname);
  }}
  q.addEventListener("input", applyAndShare);
  sort.addEventListener("change", applyAndShare);
  kind.addEventListener("change", applyAndShare);
  var init = new URLSearchParams(location.search);
  if (init.get("q")) q.value = init.get("q");
  if (init.get("sort")) sort.value = init.get("sort");
  if (init.get("kind")) kind.value = init.get("kind");
  apply();
}})();
</script>
</body>
</html>
'''


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True, help="RedEngineLauncher-catalog.tsv")
    ap.add_argument("--sums", required=True, help="SHA256SUMS.txt")
    ap.add_argument("--sizes", required=True, help='JSON [{"name":..., "size":...}] of release assets')
    ap.add_argument("--out", default=str(REPO / "site" / "dist"))
    args = ap.parse_args()

    games = load_games(args)
    out = Path(args.out)
    if (out / "thumbs").exists():
        shutil.rmtree(out / "thumbs")
    out.mkdir(parents=True, exist_ok=True)
    shutil.copytree(REPO / "site" / "thumbs", out / "thumbs", dirs_exist_ok=True)

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    (out / "index.html").write_text(page(games, generated))
    (out / "catalog.json").write_text(json.dumps(
        [{k: g[k] for k in ("slug", "name", "description", "added", "engine_version",
                            "kind", "asset", "size_bytes", "sha256", "online")} for g in games],
        indent=1))
    (out / ".nojekyll").write_text("")
    print(f"{len(games)} games -> {out / 'index.html'}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
