# RedEngineSandbox status

Implemented: 35 generated maps, 202 catalogue exhibits, a six-character hub,
three general-purpose environments, reference-map collection, in-window project travel,
asset-ID inspection and native controller input. Human-rig shoulders are lowered slightly
for Human, Wizard, Cowboy, Alien and Robot.

Source of generated content: scripts/generate.py (including its LOCAL asset definitions).
The generator writes assets/gameplay.json, maps, game.json and asset-index.json.

Verified on Windows:
- Every project map passes game check; generator --check passes in both project locations.
- Engine formatting and clippy checks pass.
- Full engine regression suite passes when run serially; headless all-target check and library tests pass.
- UI layouts pass at every audited size; character and map renders were visually inspected.
- All four new character types start in the graphical client and join the real UDP server.
- The sandbox passes the simulated bad-connection test.

The first concurrent regression run hit three real-time networking timing assertions;
all six net_e2e tests passed in the complete serial rerun without relaxing assertions.
The release run also needed one isolated networking-suite rerun for a rolling-prop
position assertion; that suite then passed unchanged.
Physical controller testing and hands-on gameplay have not been performed.
Requires the matching RedEngine character styles and protocol v7 on clients and servers.
Creative-mode asset placement and the proposed additional characters remain paused and are not included.
RedEngineGames includes
a root sandbox workflow as well as the standalone project's own workflow.

Engine baseline: [24e3b5d](https://github.com/kevstermcgee/RedEngine/commit/24e3b5d851e0816d8964082dbf6fd011f24b9540).
