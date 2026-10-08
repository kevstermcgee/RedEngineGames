# Feedback on developing with RedEngine

Two rounds, newest first. Round 2 is the modes-and-maps update (2026-10-07); round 1 (2026-09-30) built the game.

---

# Round 2 (2026-10-07): game modes, three maps, eight weapons, soldier looks, easy joining

Scope: free for all, duels, capture the flag, search and destroy, two new maps and a reworked one, eight weapons, four looks per team, a join flow that needs no setup.
What follows is what the work actually cost and what I would change in the engine, in the order they hurt.

## What worked
- **The mode checklist from round 1 was the right ask, and writing it down helped.** `docs/adr/2026-10-07-killchain-game-modes-...md` now lists every place a mode touches. The
  second mode took a fraction of the time of the first because the seams were named. Keep that ADR current when a fifth mode arrives.
- **Pure state machines with a `step(tick, actors) -> commands` shape** (`sim/objective.rs`) were fast to write and trivially testable: ten unit tests passed on the first run, and
  the match glue was ~120 lines. This is the pattern to promote to an engine convention for modes.
- **`KC_SCRIPT` plus `Read` on the PNG** is still the most valuable tool: I saw the CTF HUD, the lobby, the setup screen and each map from the player's eye on a box with no display.
  It caught real problems layout audits cannot (washed-out Quarry, near-black Terminus, a stale note on the setup screen, "S&D" printing as "S D" because the font has no `&`).
- **`lint` / `nav` / `plan` / `tour`** found stairs that led nowhere, rails that blocked their own stairs, drops at every plateau edge and unreachable raised floors before any play test.
  The nav pruner (`tools/prune_nav.py`) discarded 216 broken edges the first time a raised floor was linked wrongly: exactly its job.
- **`audio report`** let me check eight new sounds for clipping, tails and loudness without listening.
- **`preflight --fix`** turned eight chores (feature ownership, doc facts, formatting) into one command.
- **Worktrees with a shared target dir** kept the other session's uncommitted work untouched.

## What cost the most (and the fix I would like)
1. **A weapon is nine edits across eight files.** Enum, roster (wire order), name, parse, kit row, sound voice, model shape, bot profile, the flyer list for projectiles, plus the golden
   audio file. The compiler finds most of them, which is why it was possible, but the information is data. *Want:* weapons (stats, model recipe, voice, bot profile, payload) as JSON
   assets read at start-up, with the wire id assigned by order of appearance in one file. Then `Weapon` stops being an enum and a new gun is a file.
2. **A look is a new `Character` and 26 match sites.** Four looks per team meant six new enum variants, a wire map, avatar pool sizing and changes in `session`, `costumes`,
   `characters`, `avatar` and `main`. *Want:* a character is a body plus a *look* (palette, headgear, accessories) chosen from data, so a team's look count does not grow the enum or the
   avatar pool arithmetic (pool size per body kind, with a "stand-in" fallback, made this survivable).
3. **Tests that encode today's design break when the design grows.** `arsenal::every_weapon_has_a_sane_row` required every grenade to have a fuse and every launcher to be explosive;
   the impact grenade (contact) and the flare gun (fire) are legitimate. I changed the invariants to what the sim actually supports. *Want:* invariants written as "the sim handles this
   field combination" with a pointer to the code that proves it, not as a list of shapes.
4. **No way to *measure* a bot match.** The first CTF and S&D bot runs showed zero captures and no way to say why. I wrote an ignored test (`real_map_bots`) that loads any map, adds bots,
   and prints positions and objective events. It found three real things (bots always in "fight" mode in open arenas; both teams' raiders funnelling down one lane; equal-skill bots
   trading kills evenly at a shared central route). *Want:* `red_engine2 bot-match MAP --mode ctf --bots 3v3 --minutes 5` printing events, per-bot distance travelled and time in fight/objective.
5. **The scene hash does not cover the host's mode choice** (by design, so a joiner's file matches). The client therefore cannot read the mode from its own map and must take it from
   `Status`. That is right, but every client screen that branches on mode needed the same plumbing. *Want:* a `MatchInfo` struct on the client (mode, size, limit, names) that every screen reads.
6. **UI layout at 480x270 is a hard budget** (240 virtual pixels at the audit's worst case). Adding the MODE, SIZE and MAP rows to setup meant merging BOTS and SKILL into one row and
   shortening a label to fit a 38 px chip. The audit made this tractable; the budget makes the next row expensive. *Want:* a scrolling or two-column setup screen helper.
7. **`ui-shot` knows the engine's screens, not a game's.** Killchain's screens can only be photographed by running the client script. *Want:* `ui-shot --game` that asks the game's own
   `ui::killchain::build` (the audit already iterates `all()`), so screens render without a GPU context.
8. **Map generation was copy-paste.** Ironworks' generator had helpers inline; a second and third map needed them. I extracted `tools/mapkit.py` (boxes, rooms, nav grid, raised floors,
   snapped pickups). *Want:* the engine's `blueprint` language grows these primitives (a "room with doors" that keeps its interior walkable for nav, raised floors with rails and
   stairs, a "nearest free point" snap) so a map is data, not a script.
9. **`building` blocks its whole footprint for nav**, so bots cannot enter a building made with it; `wall_solids` per wall with door gaps is the workaround (now `mapkit.room`).
   *Want:* the nav grid builder to understand wall openings itself.
10. **Raised floors need explicit nav** (`raised_nav`, `stair_link`): a staircase foot sits inside the padding of the blocks beside it, so a ground node cannot see it. An approach node
    a few metres out fixed every case. *Want:* `nav --auto` that links floors through stairs it finds in the scene.
11. **Reachability from outside cannot be tested from inside.** The relay answers on loopback but not on its public name from the same network (a router without NAT loopback), so
    "the cousin can join" is unverifiable without the cousin. *Want:* `red_engine2 net-check` that probes a relay or server from a hosted probe and reports
    forwarded / blocked / CGNAT, with the router's LAN address to forward to.
12. **A full CI run was 47 minutes** on the 4-core box while other work competed for it (22 minutes alone). The first stage that fails should stop the rest and `affected` should remember
    green stages across a rebase, as it does for content-identical runs.
13. **Strict `meta`** rejected a `name` field (right, with a clear message); map labels live under `x-` keys, which worked. Documenting `x-` as the convention for tool data would help.

## Smaller notes
- Wire order is part of the protocol for weapons (`ROSTER` index) and for characters (`ALL` index); appending kept every old number. Say so in the enum docs.
- The client knows the host's mode only from `Status`, so the first frame of a lobby can briefly show the map file's default; it corrects in 200 ms.
- A scout's pouches, a heavy's pauldrons, a ghost's headset were each ten lines of boxes and spheres; the costume code (`costumes::soldier_gear`) is a good place to learn the style.
- The server log gained `objective:` lines (flag taken, bomb planted, round won): invaluable for headless runs. Keep them.
- `LocalHost` and `red_server` each parse the same overrides; a shared options struct would remove the duplication.

---

# Round 1 (2026-09-30): the first build

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
