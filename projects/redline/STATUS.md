# STATUS — redline

## Now (in flight)
- Nothing. Released as a standalone project in RedEngineGames (`projects/redline`).

## Done
- 2026-10-10: the game. Hub (7 upgrades, 6 Heats, relic shrine, records), 19 chambers in 3 tiers + the Redline finale, random run order,
  clock / par / streak / burns / second wind, persisted progress, 3 music layers, 25 passing scenarios, pars measured by the runner.
- 2026-10-10: Kevin's first pass. Opens in first person (`player.view`, explicit). You play a repair robot (`humans_play_as: robot`,
  same body numbers as the human, so no scenario changed). Minimal HUD: four rows, no title, no standing banner; banners only for a
  vent, a burn, a relic, a purchase, a station and the first visit. Fixed: a vent's banner (time bought, streak) was overwritten in the
  same tick by the next chamber's entry banner, so it was never seen; chamber entry no longer has a banner (the name is in the world).

## Next
- Human playtest: tune the starting clock (25 s), par factor (0.92 of the runner) and upgrade prices from real runs.
- Sound for the game's own events once the engine has a cue action (see ENGINE_FEEDBACK.md item 1).
- More chambers per tier (the pools are 6; a run visits 5 of tier 1, 5 of tier 2, 4 of tier 3).

## Failing / blocked
- `lint`/`reach`/`plan` on the whole map abort (engine; ENGINE_FEEDBACK.md item 5).

## Decisions & gotchas
- The HUD's banner is 260*s px wide and its panel 140*s px whatever they hold, and the panel drops 40*s px while a banner shows
  (engine layout, ENGINE_FEEDBACK.md item 11); keep banners rare and short (one line is about 24 characters at 720p).
- Chambers are teleport-linked rooms 520 m apart, all laid out along -Z so the player's facing survives the teleport.
- Randomness comes from the tick the runner reaches a vent on; the "dive" scenario is deterministic, and `--pars` records which chamber it lands in.
- Scenario `until_event` waits for the `_off` event first (engine bug, ENGINE_FEEDBACK.md item 3).
