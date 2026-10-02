# Killchain

A first-person team deathmatch for friends, built on [RedEngine](https://github.com/kevstermcgee/RedEngine). Two teams of six,
**Ridgeback** (army green and tan) against **Nightfall** (navy and black), fight over **Ironworks**, a steel works with a dead foundry in the
middle, freight yards on each side, warehouses and office roofs on the lanes. No music, no radio: gunfire, wind and far-off machines. Footstep playback is disabled.

## Play

Install from the latest [RedEngineGames release](https://github.com/kevstermcgee/RedEngineGames/releases/latest) (`killchain-windows-x64.zip`),
extract, double-click `Play-killchain.exe`.

* **SOLO**: play on this PC. Bots are **off** by default (only the people who joined play); switch them on in the setup screen to fill both teams to six.
* **HOST**: same setup, but others can join. The lobby shows a **join code**; press PASTE-able text to friends. The game opens the router's port with UPnP
  when it can, and the connection is encrypted (QUIC + TLS 1.3) with the host's identity pinned in the code.
* **JOIN**: paste the code (Ctrl+V or the PASTE button), press JOIN, pick a team in the lobby.
* **STATS**: kills, deaths, headshots, accuracy, matches won, time played, best streak, favourite weapon. Kept in `%APPDATA%\Killchain\stats.json`.

The host chooses how a match ends: first team to **25 / 50 / 75 / 100 kills**, or a **5 / 10 / 15 / 20 minute** clock, or both. When it ends you
choose **PLAY AGAIN** or **HOME SCREEN**. Dying shows an 8 second **killcam**: the last seconds of the fight through your killer's eyes.

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
Walking is 4.6 m/s and sprinting is 7.0 m/s before weapon weight; aiming or crouching returns you to the slower pace.
Open optics (including the Rook) show an illuminated cross when fully aimed, and magnified scopes keep their cross and range marks.

## Weapons (31)

Tuned after real counterparts: magazine, rate of fire, reload time, recoil, spread (worse when moving, jumping, spraying; best aimed or crouched),
range falloff, headshot multiplier, movement penalty. The full table is `docs/WEAPONS.md`.

Melee: combat knife (backstab kills), camp hatchet, baseball bat. Pistols: R9 (Glock 17), Bulldog .45 (M1911), Hand Cannon .50 (Desert Eagle),
Marshal .357 (Python), Viper (Glock 18). SMGs: Ember (MP5), Stinger (UMP45), Ranger (P90), Wasp (Vector). Rifles: Rook (M4A1), Redline (AK-47),
Kestrel (AUG), Ironside (SCAR-H). Marksman: Longbow (M14). Snipers: Gale (G3SG/1), Warden (Steyr Scout), Sentinel (.338 bolt). Shotguns: Breach
(pump), Auto-12 (Benelli M4), Coach gun (sawed-off). Machine guns: Atlas (M249), Hammer (Negev). Launchers: Lancer (RPG-7), Thumper (M79).
Grenades: frag, flashbang, smoke, incendiary.

Both teams start with the same pistol and knife; everything else lies around the map and respawns.

## Development

The game is data plus the engine's loadout-shooter mode (`docs/adr/2026-09-30-killchain-loadout-shooter.md` in RedEngine). The map is generated:

```bash
python3 tools/gen_map.py                      # maps/main.json (objects, pickups, spawns, nav graph)
RED_ENGINE2=/path/to/red_engine2 python3 tools/prune_nav.py maps/main.json   # keep only nav edges the real movement can walk
red_engine2 lint maps/main.json && red_engine2 nav maps/main.json
re2 maps/main.json                            # the game
KC_SCRIPT=scripts/kc/solo_bots.json re2 maps/main.json   # a scripted run with no window: pictures in out/kc/
```

`docs/metrics.md` records what the build cost; `docs/ENGINE_FEEDBACK.md` lists what would have made it cheaper.
