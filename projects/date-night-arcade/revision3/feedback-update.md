
## Latest release 2.1: single player

At the user's request, all three games now have one personal scoreboard and Play Again. Numbered-player variables, alternating turns, separate player records and pass-the-controller prompts were removed from gameplay, results, game pages and installers. Migration tests confirm existing overall best scores, survival records, ranks and completed-run counts survive the change.

The instrumented single-player revision took 491 seconds (8 minutes 11 seconds), including native/browser checks, installer builds, Windows CI and publication. All three current builds passed 93 native checks, 201 local browser checks and 162 remote browser checks in total. Their real install buttons downloaded the exact binaries tested on Windows. The original audio/resource measurements remain applicable because the soundtracks and engine player are unchanged.

[Single-player timing, bytes and publication evidence](https://github.com/kevstermcgee/RedEngineGames/blob/main/projects/date-night-arcade/revision3/evidence/metrics.json) · [Save migration](https://github.com/kevstermcgee/RedEngineGames/blob/main/projects/date-night-arcade/revision3/evidence/save-migration.json) · [Windows CI](https://github.com/kevstermcgee/RedEngineGames/actions/runs/37561839139) · [Current Windows release](https://github.com/kevstermcgee/RedEngineGames/releases/tag/date-night-arcade-v2-1).
