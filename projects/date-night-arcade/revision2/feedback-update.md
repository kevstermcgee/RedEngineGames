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
