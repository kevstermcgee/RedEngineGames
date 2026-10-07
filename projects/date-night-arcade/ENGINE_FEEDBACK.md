# Three arcade games and Red Engine feedback

## Current release: 2.1, purely single player

Player numbers, alternating turns and separate player records were removed at the user’s request. Every game now has Play Again and one personal record set. Native scenarios, controller/reload tests and migration from the previous save format passed. Existing overall scores, survival times, ranks and completed-run counts are preserved. Historical measurements below describe their respective releases.

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
## Survival Edition follow-up: user feedback and measured costs

The initial three published prototypes were technically verified, but the player reported that they were too easy, ended too quickly, sounded repetitive, displayed too much text during play, looked too similar, could not be installed on a Windows PC, and linked to raw JSON as their game pages.

The revised games use four-heart endless survival and 20-second difficulty waves, distinct scenery/palettes, a compact gameplay HUD, F fullscreen, visible installation controls, human-readable pages and offline Windows installers. Controls, instructions and player records move to start/results/pages. Riff no longer awards free points for tapping jump; later waves introduce overhead hazards. Pip adds a gust with a cooldown and telegraphed falling rain. Moxie adds faster hunters and aimed comets.

Each score now has 32 bars and eight arranged sections with alternate melodies, counterlines, a bridge, a drum break and instrument changes. Pickup tones cycle through three pitches; each game has its own layered effects. The native synth generates a checked PCM WAV at build time, and a small worker decodes it in the player. Final local browser reports measured roughly 0.13 seconds to prepare playback and zero milliseconds of main-thread music rendering. This trades package size for fast startup.

Measured on Linux, four logical CPUs, using existing Rust dependencies and the already-built engine CLI/WASM:

| Game | Native verification | Native checks | Scenarios | Loop length | Browser package | Windows installer |
| --- | --- | --- | --- | --- | --- | --- |
| Pip Cloud Post | 6.6 s | 30 | 5 | 66.21 s | 12.50 MB | 13.40 MB |
| Moxie Magnet Moon | 6.7 s | 30 | 5 | 72.45 s | 13.62 MB | 14.52 MB |
| Riff Rooftop Rush | 6.3 s | 33 | 6 | 64.00 s | 12.12 MB | 13.02 MB |

Each game uses the same 679,249-byte WASM player. A separately measured Moxie score render took 5.66 s wall time (5.36 s user CPU, 0.30 s system CPU) and peaked at 362,488 KiB RSS. These are process measurements, not whole-session memory or CPU. No art/audio assets, paid asset services or additional application runtime dependencies were purchased/downloaded. Dollar cost and model token use are not exposed and are not estimated.

The original idea-to-confirmed-remote-playable run took 641 seconds, including a 152-second native CLI compile and 14.4-second first WASM package build. Revision two began at 2026-10-07 01:48:03 UTC; final publication timing and exact package IDs, bytes, checks and Windows CI evidence are recorded in `projects/date-night-arcade/revision2/evidence/metrics.json` in RedEngineGames.

### Engine / publication improvements

1. Distinguish “valid PWA package”, “browser offered an install prompt”, and “downloadable Windows installer”. The original install control was hidden until `beforeinstallprompt`, and the verification's “installable” pass did not prove that a user could install anything on their PC. Keep an install/help surface visible and document actual supported routes.
2. A game's human-facing details link should never target `game.json`. The RedEngineGames site generator did exactly that; it now builds real HTML pages for all browser games.
3. Add F fullscreen to the default host, with a discoverable control and a test asserting `document.fullscreenElement`. It belongs in the reusable player.
4. Offer cooked audio assets, a compressed format and a checked cache. Richer scores are much more expensive than one-shots; pre-rendering cuts startup latency but uncompressed stereo WAV substantially increases package/offline-cache bytes.
5. Expose a real music/sample playhead to game rules. The custom host now synchronizes Riff when audio starts and resets playback on round restart; simulation time alone drifts during delayed audio initialization and across restarts.
6. Publish a minimal HUD / start / results template. The prototype's title, instruction row and record footer occupied a large fraction of the small game view. The new screen shows only player/score, time, health and a relevant meter.
7. “All checks pass” does not measure difficulty or enjoyment. Require a longer active route into multiple waves, an idle-loss route and assertions that survival speed/density scale. Physical controller feel and subjective music/playtesting still need people.
8. One intermediate `web verify` failed backup/restore with `ReferenceError: __red2d is not defined` while restore triggered a reload. Re-running the unchanged host sequentially passed. The verifier should wait for the restore navigation and new runtime readiness before accessing the hook.

The existing teleport-derived-coordinate bug and reproduction in this issue remain relevant; game scripts continue to use explicitly computed snap destinations as a workaround. No Red Engine Rust changes were made in this follow-up.

All three revised browser builds were remotely confirmed and their real installer buttons successfully downloaded binaries matching the Windows-tested checksums by 2026-10-07 02:19:32 UTC: 1,889 seconds (31 minutes 29 seconds) after revision work began. Final evidence totals: 93 native checks, 16 scenarios, 201 local browser checks, 162 remote browser checks, three controller/save checks, and Windows installer CI covering all three exact binaries.

[Windows installer CI](https://github.com/kevstermcgee/RedEngineGames/actions/runs/37561096525) · [Measured resources and timing](https://github.com/kevstermcgee/RedEngineGames/blob/main/projects/date-night-arcade/revision2/evidence/metrics.json) · [Windows release](https://github.com/kevstermcgee/RedEngineGames/releases/tag/date-night-arcade-v2).
