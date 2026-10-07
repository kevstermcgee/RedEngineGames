# Three arcade games and Red Engine feedback

Three single player 2D browser games were built and published with Red Engine commit `6a42dd1ed6509f8b6ca9cab1a54dbecac04fa030`, the latest upstream HEAD fetched when development began on October 6, 2026 in Pacific time. Each game uses an original mascot, authored pixel sprites, a distinct synthesized soundtrack, controller actions, short rounds, two alternating player records, a five rank mastery ladder, autosaving and downloadable save backups.

## Play the games

- [Pip Cloud Post](https://kevstermcgee.github.io/RedEngineGames/play/games/pip-cloud-post/) follows a scarf wearing cloud rabbit. Steer automatic rebounds and slam for a super spring; collect 12 envelopes. Its 112 BPM F pentatonic theme uses bright plucks and a bouncing bass line.
- [Moxie Magnet Moon](https://kevstermcgee.github.io/RedEngineGames/play/games/moxie-magnet-moon/) follows an axolotl with a magnetic backpack. Snap in the last aimed direction and scoop scrap clusters with a recharging pulse; earn 30 points. Its 100 BPM D dorian theme uses spaced bell tones and low bass.
- [Riff Rooftop Rush](https://kevstermcgee.github.io/RedEngineGames/play/games/riff-rooftop-rush/) follows a roller skating fox. Change rails, hop over speaker grumps and chain timed tricks; earn 80 points. Its 120 BPM E minor pentatonic theme uses syncopated plucks, bass and percussion. Follow the gold beat meter for scoring; its simulation clock is not sample synchronized to the audio clock.

Rounds finish at the goal, after three hits, or at the 45 second limit. Fast wins receive remaining time and heart bonuses. Results name the next player; A or Space starts that player's round. Shared progress records total points, completed rounds, wins and ranks. Progress survives browser reloads; unfinished rounds restart. Saves are local to the browser and device, with backup and restore controls on the start card.

## Measured development resources

The first recorded tool timestamp was 01:28:27 UTC on October 7, 2026. All three native verifications were observed passing by 01:35:13. All three public deployments were confirmed playable by 01:39:08: **10 minutes 41 seconds from the initial recorded timestamp**. This measures this agent assisted session, not a cold installation or a human studio production estimate.

The latest engine CLI compiled in 152 seconds with existing dependency caches. The first WebAssembly package built in 14.4 seconds. The Linux host exposed four logical CPUs. Every package ships the same 679,249 byte WebAssembly player; assets are JSON sprites and scores without external image or audio downloads.

| Game | Scenarios | Native verification | Peak native RSS | Raw package | Publish and remote check |
| --- | ---: | ---: | ---: | ---: | ---: |
| pip-cloud-post | 5 | 0.714 s | 91.2 MiB | 765.6 KiB | 52.4 s |
| moxie-magnet-moon | 5 | 0.768 s | 100.6 MiB | 772.6 KiB | 52.3 s |
| riff-rooftop-rush | 6 | 0.684 s | 86.0 MiB | 765.5 KiB | 51.7 s |

Native RSS was measured with `/usr/bin/time -v`, per verification command. It is not whole session memory, compiler peak memory or player RAM. Publish timing includes upload, deployment waiting and the deployed browser suite. Package sizes are uncompressed bytes. Agent monetary cost, total token usage and aggregate session CPU were not exposed, so they are not estimated. `metrics.json` contains the exact byte counts, build IDs and timing fields.

## Verification evidence

The games pass 78 native verification rows across 16 authored scenarios, including ability behavior, successful runs, failure, deterministic replay, sound waveforms and save round trips. Each passes 67 local Chromium checks and 54 checks against its public deployment. The browser suite checks native and WebAssembly state parity, keyboard and mouse input, emulated touch, audio API startup, offline reload, installability, save recovery and corrupt storage handling.

An additional Gamepad API test checks each game's actual abilities and movement, progress reload and A button restarts with alternating players. All three pass. These are simulated standard controllers; physical hardware, Safari and human enjoyment have not been qualified. Automated audio tests confirm playback and unclipped samples, not how the music sounds to a listener.

## Confirmed teleport coordinate defect

`Act::Teleport` updates the entity position but not the derived `p_x` and `p_y` values used by a following action. In Moxie, teleporting 58 pixels and spawning the magnetic field at `p_x,p_y` placed the field at the old location. Emitting an event immediately after teleport also kept the old coordinates because the event is drained before the next movement refresh.

The minimal reproduction is `engine-feedback/teleport-stale.game2d.json`. Run `red_engine2 verify` on it at the pinned commit. The player reaches `(100,45)`, but the marker appears at the previous `(40,45)` and the overlap assertion fails: `expected hit eq 1, found 0`. The game workaround computes and clamps the destination into `snapx,snapy`, then uses those same variables for both teleport and field placement.

Suggested engine fix: refresh derived entity variables before later coordinate expressions can read them after a teleport. Add regressions for teleport then spawn, chained teleports and teleport then immediate event. Native and WebAssembly should produce the same corrected hashes.

## Improvements suggested by the build

1. **Expose the audio playhead for rhythm mechanics.** Score generation occurs in a worker after gameplay starts; Pip's local check reported 910 ms before music playback. Music continues across round restarts while the simulation's `time` resets. A beat or sample clock, phase reset policy and latency calibration would let Riff score against audible beats. The current gold meter remains the scoring reference.
2. **Make reuse of verified packages discoverable.** `publish --package P --out NEW` looked for `NEW/verification.json` and failed even though P had already been checked. Reusing the original verification output directory worked. Add `--verification RECORD` or print the known verification path and package ID from `web status`.
3. **Expose movement and held inputs to game rules.** A declarative impulse is immediately overwritten by a `keys` mover. Moxie's snap uses teleport and Pip uses vertical velocity because platformer movement only replaces horizontal velocity. A dash mover with additive impulses, plus `vx`, `vy`, grounded and held input expressions, would support smooth acceleration, tether slingshots and responsive character poses without reading simulation Rust.
4. **Qualify gamepad tests by behavior.** The stock check confirms a simulated pad can start a game. A declaration for axis movement, A/B ability effects and restart behavior would let the engine verify meaningful gamepad support itself. Keep physical controller qualification separate.
5. **Clarify browser documentation and diagnostics.** `describe web` reports simulated touch and gamepad coverage while `describe 2d` still describes those paths as unverified. The end of a passing browser report also says the paths are unverified. Separate simulated API coverage, physical device coverage and human playtesting consistently. Suppress cascading control-layout diagnostics when the mover failed to parse for an unrelated reason.

The engine's strongest features for this task were one file authoring, shared native and WebAssembly simulation, useful failed-rule diagnostics, deterministic scenarios, synthesized music, small self contained packages, offline save backups and a publishing path that checks the deployed game instead of treating a pushed commit as success.
