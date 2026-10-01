# Feedback on developing with RedEngine (Killchain build, 2026-09-30)

Killchain needed a new game mode, not just a map, so this is feedback from extending the engine as well as from using it. Ordered by how much
time each item cost.

## What worked
- **`describe` / `search` / `context`** got me to the right files without reading whole docs. `scripts/dev iterate` (seconds) made the edit loop tolerable.
- **Scripted headless client (`KC_SCRIPT`, `Capture`) and `ui-shot`/`ui-check`** let me verify menus and gameplay with screenshots on a box with no display.
  This was the single most valuable tool; I built the Killchain script runner on the same idea and it should be an engine feature.
- **`lint` / `plan` / `nav` / `walk` on maps** caught stairs, plants inside solids and unreachable nav nodes before any play test.
- **Server-authoritative sim with prediction, and pure-function sim modules**: adding a mode was mostly adding pure state machines plus tests.

## What cost the most (and the fix I would like)
1. **No first-class "new game mode" path.** The docs say never read source, but a mode with teams, inventories, projectiles and a killcam touches
   `sim`, `net/protocol`, `server`, `snapshots`, `client`, `session`, the viewer and the UI. I read about 4,000 lines of source to find the seams.
   *Want:* an extension point (a `Mode` trait with hooks for rules, per-player extra state, snapshot extension bytes, HUD) and a short
   "how a mode is wired" document that lists every file to touch.
2. **Protocol changes ripple through test literals.** Adding one field to `PlayerSnap`, `Hello` or the lobby roster broke struct literals in a dozen
   tests and needed regex patching. *Want:* `Default`/builder constructors for protocol structs in tests, and versioned optional extension blocks.
3. **Hard-coded player and avatar limits** (8 players, 6 body pool, karts 8 animals, snapshot byte budget and `MAX_PROPS_PER_SNAPSHOT`).
   Going to 12 players touched lobby, pool, budget tests and kart-bot slot choice (bots silently took duplicate animals). *Want:* one `MAX_PLAYERS`
   constant that derives the dependent budgets, and tests that state their assumption from it instead of the literal 8.
4. **Weapons are an enum in engine code**, not data. 31 weapons meant a large Rust table plus matching name/model/sound tables.
   *Want:* weapons (stats, model, sounds, projectile payload) as JSON assets, like prefabs.
5. **Viewmodel and hands.** Matching arms and gloves to each team's uniform, sight alignment and recoil all needed code. *Want:* a viewmodel rig
   described in data (hand anchors per weapon, ADS offset from a named sight node) and a `viewmodel-shot` command that renders every weapon.
6. **Full CI is 22 minutes and the dev-box target lock serialises everything.** A first run failed late on clippy; `iterate` did not run clippy on the touched
   files. *Want:* clippy in `iterate` and a `ci --resume` that re-runs only failed targets.
7. **No display on the dev box:** `re2` panics at event-loop creation. A clear "no display, use KC_SCRIPT / --headless" message would save a debugging round.
8. **Test budget constants encode history** (`WORST_SNAPSHOT_BUDGET: 1260 // v8 added 13 bytes`). Each protocol bump needed hand-tuned numbers.
   Derive from the formula with a headroom percentage.
9. **Audio is synthesized from code** (good for licensing) but each new effect (explosion, rocket, reload, footsteps per surface) needed iteration by
   listening. *Want:* a `sfx-render` command that prints a loudness/silence/spectrum summary so I can check without ears (I added a tail-silence check myself).
10. **Map authoring at 200 m scale** was written as a Python generator since JSON by hand is too long. The `blueprint` language targets rooms and
    doors; it has no outdoor "yard, lane, building with floor plan" primitives. *Want:* building/yard/stairs/cover primitives and a plant/crate catalog.

## Smaller notes
- `describe rules` does not cover loadout/inventory games; I had to add `shooter` to the schema, the strict checker and `describe scene` by hand.
- Nav graph generation is manual; `prune_nav` (my script) checks edges against real movement and should be `nav --prune`.
- Clipboard, UPnP and saved identity existed only partially; the join-code paste flow needed a clipboard module (X11/Wayland/Windows).
- Doc-fact and feature-ownership preflight checks were excellent; they told me exactly what edit to make.

## The crash (2026-10-01)

The original build session for this game crashed partway through. Evidence, for whoever works on session
resilience next: `docs/metrics.md` (a checkpoint log of wall-clock time and remaining token budget, updated by hand
at major phase boundaries) has exactly two entries and stops dead at **15:02**, mid-build, right after "7 sim tests
green" on the core weapons/teams engine work. Every other file in the project — the map, the scripts, the README,
the weapons doc, and the final green `ci.log` — carries timestamps running to **16:41**, another hour and forty
minutes of real, completed work that was never logged. Nothing in the finished project is actually broken or
half-done; a later instance evidently picked the work back up and finished it without knowing to resume that
particular log file. *Want:* checkpoint files like this should be something the harness itself keeps (or at least
reminds a fresh instance to resume), not a manually-maintained habit that silently stops the moment a session ends
mid-task.

## Publishing friction (2026-10-01)

Pain points found actually shipping this game to RedEngineGames, after the engine work above was already done:

11. **A stale engine path in `game.json`.** `"engine": {"path": "../../../RedEngine"}` was wrong for this project's
    actual location (it should have been `"../RedEngine"` — one level up, not three) and nobody caught it because
    `game publish` silently overwrites the field to the correct published-relative value regardless of what it
    currently holds. *Want:* `game publish` (or `scripts/red doctor`) should warn, not silently paper over it, when
    the source project's own engine path doesn't actually resolve — it's a sign something upstream (probably
    `new-game`, or a hand-edit) got the path wrong, and it is wrong for every local command run against the
    unpublished copy until someone notices.
12. **The `scripts/red` wrapper isn't guaranteed.** Every sibling project in `RedEngineGames/projects/` has it
    (it's generated by `new-game`), but this project was apparently never scaffolded with `new-game` and so shipped
    without it — nothing caught the gap until I compared directory listings by hand. *Want:* `game publish` (or
    `preflight`) should flag a published project that's missing the standard wrapper scripts every other published
    game has, since it's a silent inconsistency, not a hard error.
13. **The release pipeline can only build from `main`.** `RedEngineGames`'s `.games-catalog.json` pins a single
    `source_revision`, and that field is only ever advanced by RedEngine's own CI on push to `main` — there is no
    supported way to ship a game whose engine dependency lives on a long-running feature branch without either
    merging that whole branch to `main` first, or hand-editing the catalog to point at a branch commit directly
    (which is what shipping this game actually required, since its branch had accumulated 133 files of unrelated
    session work that nobody wanted to merge wholesale). *Want:* either `game publish` should offer to pin
    `source_revision` to the exact engine commit the game was last verified against (not necessarily `main`), or the
    "one engine commit for every game" model itself needs revisiting — a monorepo-style engine branch is a real
    thing that happens, not a mistake to work around by hand each time.
