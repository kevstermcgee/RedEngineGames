# Web launcher plan — RedEngineGames download site

Status: built locally (2026-10-01); awaiting push + one-time Pages enablement

Decisions from review (2026-10-01): all 20 catalog games listed; per-game
thumbnails rendered from each game's real map (`site/gen_thumbs.py`, committed
under `site/thumbs/`); default order newest-first (added date derived from git
history — the TSV `created` column is the release date, identical for every
row); client-side filter (name/description), sort (date, name, size) and an
online-multiplayer filter, all reflected in shareable URL query params
(`?q=…&sort=…&kind=online`). The page works without JS (cards are static HTML;
JS only adds sort/filter). `site/games-meta.json` holds hand-maintained
online-multiplayer notes. Thumbnails are regenerated locally, not in CI (CI
would need an engine build); a missing thumb falls back to a placeholder.
The deploy workflow chains on `workflow_run` of "Build Windows releases"
because that workflow publishes releases with GITHUB_TOKEN, whose events never
fire `release:` triggers.

Thumbnail gotcha: projects pin their own engine revisions, so some maps fail
validation on the rendering engine (removed `weapons.revolver`, newer rule
expressions). `gen_thumbs.py` retries with gameplay blocks stripped (`rules`,
`weapons`, `checks`) — visually neutral for a static frame. RedDM's scene
camera faces a wall; a per-slug `--eye/--at` override in `gen_thumbs.py` is a
polish item.

## Goal

A web page, reachable online by friends with just a link, that lists every
released RedEngineGames game and lets them download and start playing in as few
clicks as possible. Zero hosting cost, utilitarian look — a catalog, not a
storefront.

## Decision: GitHub Pages + the existing release catalog

The repo is public and every release already publishes one
`<slug>-windows-x64.zip` per game plus `RedEngineLauncher-catalog.tsv`
(slug, name, description, created, game_version, engine_version, kind,
stable `releases/latest/download/...` asset URL) and `SHA256SUMS.txt`.
The web launcher is therefore a **static site generated from that same
catalog**, hosted on **GitHub Pages** (free for public repos):

- URL: `https://kevstermcgee.github.io/RedEngineGames/`
- No server, no accounts, no cost. Downloads are served by GitHub Releases,
  which already handles bandwidth and the stable `latest/download` URLs.
- The catalog TSV stays the single source of truth, shared with the existing
  Windows `RedEngineLauncher.exe` — a new game appears on the site the same
  way it appears in the desktop launcher: by passing the all-games coverage
  gate and landing in the release.

Rejected alternatives:
- **Client-side fetch of the GitHub API** (api.github.com has CORS, releases
  `latest/download` does not): works, but adds a 60 req/hr/IP rate limit and
  a JS dependency for no benefit. Baking the page at release time is simpler
  and loads instantly.
- **itch.io**: free and solves discovery, but uploads are manual (or butler
  scripting), pages aren't generated from the repo catalog, and it's less
  utilitarian than a plain page the repo owns.
- **Hosting on the micro PC**: the box should stay a game server; a public
  web server on it adds exposure and uptime burden GitHub provides for free.

## Site design (utilitarian)

One static `index.html`, no framework, no build toolchain beyond the
generator script. Semantic HTML + one small CSS file; zero or near-zero JS
(optional: a text filter box). Reuse the launcher palette from
`.launcher-config.json` (`#FF5C7A` accent on `#160B13`) so web and desktop
launcher match.

Page structure, top to bottom:

1. **Header**: "RedEngineGames" + one line: free Windows games built on
   RedEngine.
2. **Getting started** (3 steps, always visible): download a ZIP → extract →
   double-click `Play-<Game>.exe`. Includes the SmartScreen note (builds are
   unsigned; "More info → Run anyway") and a controller-support mention.
3. **Game list**: one row/card per catalog entry — name, description,
   release date, engine revision (short), kind (data game / standalone
   project), ZIP size, and a prominent **Download** button pointing at the
   stable `latest/download/<slug>-windows-x64.zip` URL. SHA-256 shown in a
   collapsed `<details>` for anyone who cares.
4. **Online games** section: which games are multiplayer (e.g. Great
   Outdoors ships with `--host`; friends joining Kevin's server need the
   host address + join key from him — the page says "ask the host", it never
   publishes the key).
5. **Footer**: link to the desktop `RedEngineLauncher-windows-x64.zip`
   as the "install once, get everything" alternative, link to the repo,
   `SHA256SUMS.txt`, and the catalog's source commit.

## Implementation

New files (none touch the sync-managed `games/ prototypes/ tests/ demos/`):

- `site/generate.py` — reads `RedEngineLauncher-catalog.tsv` +
  `SHA256SUMS.txt` + asset sizes (from the release, via `gh` in CI or a
  local file during dev), emits `dist/index.html` (+ `catalog.json` for
  anything that later wants machine-readable data, e.g. an auto-updater).
- `site/style.css`, `site/template.html` (or inline in the generator —
  whichever stays smaller).
- `.github/workflows/pages.yml` — triggers on `release: published` (plus
  `workflow_dispatch`), downloads the release's catalog TSV + SHA256SUMS,
  runs the generator, deploys with `actions/deploy-pages`. Pages must be
  enabled once in repo settings (source: GitHub Actions).

## Phases

1. **Generator + page** — `site/generate.py` producing the full page from
   the current release's TSV; verify locally (open in the preinstalled
   Chromium, screenshot, click-check a download URL returns 200).
2. **Pages deploy** — workflow + enable Pages; confirm the live URL serves
   the page and a friend-visible download works end to end.
3. **Polish pass** — ZIP sizes, SHA-256 details, online-games section,
   desktop-launcher footer, mobile-width check (friends will open the link
   on phones even if downloads are desktop-only — the page should still read
   fine and say "Windows only").
4. **Wire into releases** — confirm the next real release re-deploys the
   site automatically with the new game present.

## Out of scope (keeps it free and simple)

- Accounts, comments, analytics, payments.
- Custom domain (costs money; the github.io URL is fine).
- In-browser play (RedEngine targets native Windows builds).
- Auto-update of installed games (that's the desktop launcher's job).
- Publishing join keys or the micro PC's address.

## Open questions for Kevin

- Should every catalog game be listed, or a curated subset? (Release also
  carries scene ZIPs like `house`/`office`/`school` that the TSV already
  excludes — plan assumes the TSV's 20 entries are exactly right.)
- Any wish for per-game screenshots on the cards? The repo has `ui-shot`
  tooling; adding one thumbnail per game is a cheap later phase but needs
  images committed or attached to releases.
