# Great Outdoors

A hosted, up-to-8-player kart racer built on [RedEngine](https://github.com/kevstermcgee/RedEngine): eight fairytale animals (Duck, Bunny, Deer, Coyote, Hawk, Bear, Wolf and
Beaver, each with their own kart and perk), a pastel palette, and one track, **Whispering Woods**: a forest loop with a dirt shortcut across the south-east bend, mud in the
east, a ford in the north, item boxes with three pickups (Mushroom boost, Acorn, Bubble shield), bots that fill the grid, third-person camera and full gamepad support.

**Play against bots on your own PC:** download the *great-outdoors* ZIP from the latest release and double-click `Play-great-outdoors.exe`. It hosts a race on your machine and
joins it. Pick your animal in the lobby (left/right, or the d-pad and bumpers on a controller), press Ready (R, Enter or A) and race.

**Play on the shared server:** ask the host for the address and the join key, then

```
RedEngine.exe --connect HOST:27015 --server-fingerprint sha256:8fb44edfadd195996d5de78744aa076d5129f35af7094062d5b5f1262ce105a9 --key JOIN_KEY content/projects/great-outdoors/maps/main.json
```

(the fingerprint names the host's server; the join key is private, so the host sends it to you directly). Your download must come from the same release as the server: they
are built from the same engine commit.

Controls: W/S or up/down throttle and brake, A/D or left/right steer, Space hop and drift (hold), F or click the item, E the driver's ability (the Beaver builds planks).
Gamepad: left stick steers, right trigger accelerates, left trigger brakes and reverses, a shoulder button hops and drifts, X the item, Y the ability.

## Making changes

The map and the animals are generated: `tools/gen_track.py` and `tools/gen_karts.py` (Python 3, no dependencies), then `scripts/red check` and
`red_engine2 race-test maps/main.json` (eight bots race it headless and report every animal's lap times). The game's source repository is the private
`kevstermcgee/great-outdoors`; this folder is its published copy.
