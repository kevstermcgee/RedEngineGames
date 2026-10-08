# Killchain

A fast first-person shooter for friends, built on [RedEngine](https://github.com/kevstermcgee/RedEngine). **Ridgeback** (army green and tan) against **Nightfall**
(navy and black), on three maps, in four modes, from a 1v1 duel up to six a side. No music, no radio: gunfire, wind and far-off machines. Footstep playback is disabled.

## Modes

Pick the mode, the team size and the map on the setup screen (SOLO or HOST).

| Mode | What wins it |
|---|---|
| **TDM** team deathmatch | the team with the most kills when the limit or the clock is reached |
| **FFA** free for all | the player with the most kills (everyone for themselves, spread over the map) |
| **CTF** capture the flag | take the enemy flag to your own base while yours is at home; first to the capture limit |
| **BOMB** search and destroy | one life a round: attackers plant the bomb on a site (hold **E** about 3 s) and defend it, defenders stop them or defuse it (hold **E** about 5 s); first to the round limit, sides swap partway |

**Team size** is 1v1, 2v2, 3v3 or 6v6 (free for all: 2, 4, 6 or 12 players). A duel is just team size 1 in any mode. Bots are optional and fill what the people leave empty.

## Maps

* **Ironworks** (WORKS): a steel works with a dead foundry in the middle, freight yards on each side, warehouses and office roofs on the lanes; late-afternoon light.
* **Quarry**: a big open desert quarry, a raised plateau at each end, a central mesa with an excavator, rock outcrops and two overlooks; the longest sightlines.
* **Terminus** (DEPOT): a railway terminus at night, ticket halls, a tall concourse and two platforms with parked trains; close quarters, made for duels and bomb rounds.

Health slowly returns if you stay out of trouble for a few seconds.

## Play

Install from the latest [RedEngineGames release](https://github.com/kevstermcgee/RedEngineGames/releases/latest) (`killchain-windows-x64.zip`),
extract, double-click `Play-killchain.exe`.

* **SOLO**: play on this PC. Bots are **off** by default (only the people who joined play); switch them on in the setup screen.
* **HOST**: same setup, but others can join. The lobby shows a **six-character code** (for example `H3PQXR`) and a long code. Send either to a friend. The short code goes through
  the project's relay, so nobody has to forward a port or know an address; the long code connects directly (the game also opens the router's port with UPnP when it can).
  The connection is encrypted (QUIC + TLS 1.3) with the host's identity pinned.
* **JOIN**: paste the code (Ctrl+V or the PASTE button) and press JOIN. **You do not have to pick the same map**: the game tries each installed map until the host's accepts you.
  Then pick a team (or, in free for all, just ready up) and choose your **look** (Trooper, Scout, Heavy or Ghost).
* **STATS**: kills, deaths, headshots, accuracy, matches won, time played, best streak, favourite weapon. Kept in `%APPDATA%\Killchain\stats.json`.

If the short code does not work, the host's long code always does, and `RE2_RELAY=off` turns the relay off. Playing across the internet needs the relay's port (UDP 28016) or
the host's own (UDP 27015) reachable; on a home network that is a router port forward.

The host chooses how a match ends: a kill, capture or round limit, or a **5 / 10 / 15 / 20 minute** clock, or both. When it ends you
choose **PLAY AGAIN** or **HOME SCREEN**. Dying shows a **killcam**: the last seconds of the fight through your killer's eyes.

## Controls

| Action | Keyboard and mouse | Gamepad (laid out like CS:GO's) |
|---|---|---|
| Move / look | W A S D, mouse | left stick, right stick |
| Fire | left mouse | right trigger |
| Aim down sights / scope (grenades: underhand) | right mouse (scopes: click cycles zoom) | left trigger |
| Jump | Space | A |
| Sprint (hold, forward) | Shift | left stick click |
| Crouch (hold) | Ctrl or C | B |
| Reload | R | X |
| Use / pick up | E | Y |
| Drop weapon | G | Y while crouching |
| Weapon slots (1 primary, 2 secondary, 3 knife, 4 grenades) | 1 2 3 4 | D-pad up, right, left, down |
| Previous / next weapon | mouse wheel | LB / RB |
| Last weapon | Q | |
| Scoreboard | hold Tab | Back |
| Pause | Esc | Start |
| Fullscreen | F or F11 | |

Field of view is 90 degrees (horizontal). Walking over a weapon picks it up if you have a free slot; **E** swaps it for the gun in hand. You hold
two guns, one melee weapon and up to two grenades; every gun keeps its own magazine and reserve, and dropped guns keep what is left in them.
Ammunition crates top up every gun you carry.
Walking is 4.7 m/s and sprinting is 7.2 m/s before weapon weight; aiming or crouching returns you to the slower pace. In capture the flag and search and destroy, **E** also takes
a flag, plants and defuses the bomb; the flag is picked up by walking onto it.
Open optics (including the Rook) show an illuminated cross when fully aimed, and magnified scopes keep their cross and range marks.

## Weapons (39)

Tuned after real counterparts: magazine, rate of fire, reload time, recoil, spread (worse when moving, jumping, spraying; best aimed or crouched),
range falloff, headshot multiplier, movement penalty. The full table is `docs/WEAPONS.md`.

Melee: combat knife (backstab kills), camp hatchet, baseball bat. Pistols: R9 (Glock 17), Bulldog .45 (M1911), Hand Cannon .50 (Desert Eagle),
Marshal .357 (Python), Viper (Glock 18). SMGs: Ember (MP5), Stinger (UMP45), Ranger (P90), Wasp (Vector). Rifles: Rook (M4A1), Redline (AK-47),
Kestrel (AUG), Ironside (SCAR-H). Marksman: Longbow (M14). Snipers: Gale (G3SG/1), Warden (Steyr Scout), Sentinel (.338 bolt). Shotguns: Breach
(pump), Auto-12 (Benelli M4), Coach gun (sawed-off). Machine guns: Atlas (M249), Hammer (Negev). Launchers: Lancer (RPG-7), Thumper (M79).
Grenades: frag, flashbang, smoke, incendiary.

New with the game modes: **Reaper** (rotary minigun: 200 rounds, walks slowly), **Breaker** (single-slug pump shotgun: two shots to kill), **Hunter** (silent crossbow: one bolt, a headshot kills),
**Flare** (flare gun: a small fire where it lands), **Lobber** (arcing mortar launcher), **Impact** (a grenade that bursts where it first lands), **Machete** (fast, long reach) and **Sledge**
(slow, and one hit kills).

Both teams start with the same pistol and knife; everything else lies around the map and respawns.

## Development

The game is data plus the engine's loadout-shooter mode (`docs/adr/2026-09-30-killchain-loadout-shooter.md` and
`docs/adr/2026-10-07-killchain-game-modes-free-for-all-capture-the-flag.md` in RedEngine, the second lists every place a mode touches). The maps are generated from a shared kit:

```bash
python3 tools/gen_map.py                      # maps/main.json    Ironworks
python3 tools/gen_quarry.py                   # maps/quarry.json
python3 tools/gen_terminus.py                 # maps/terminus.json
RED_ENGINE2=/path/to/red_engine2 python3 tools/prune_nav.py maps/quarry.json   # keep only nav edges the real movement can walk (each map)
red_engine2 lint maps/quarry.json && red_engine2 nav maps/quarry.json && red_engine2 plan maps/quarry.json out/plan.png
re2 maps/main.json                            # the game (the other maps beside it are offered on the setup screen)
KC_SCRIPT=scripts/kc/ctf_solo.json re2 maps/main.json    # a scripted run with no window: pictures in out/kc/
cargo run --example weapons_table > docs/WEAPONS.md       # (in RedEngine) the weapon tables, always from the arsenal
```

`tools/mapkit.py` holds the shared pieces (boxes, rooms that keep their interior walkable for the nav graph, raised floors and stairs, a snap-to-free-ground pickup helper, the scene
writer). A map names its mode data under `shooter` (`flags`, `sites`, `objective`) and a short setup label under `meta.x-short`.
`docs/metrics.md` records what the build cost; `docs/ENGINE_FEEDBACK.md` lists what would have made it cheaper.
