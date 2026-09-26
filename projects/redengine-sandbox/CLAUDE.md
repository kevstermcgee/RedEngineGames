# Working on RedEngineSandbox

This is a standalone game project using a sibling RedEngine checkout.
The source for generated maps is scripts/generate.py. Reusable local prefabs are described there
and written to assets/gameplay.json, then embedded in every generated sandbox scene.
Reference maps come from the engine examples/recipes and local RedDM/RiftRaze projects.

After editing, run python scripts/generate.py, python scripts/generate.py --check and
powershell -File scripts/red.ps1 check. Render changed maps with tour or plan and inspect the images.
Keep the standalone copy and RedEngineGames/projects/redengine-sandbox synchronized.
Never copy engine Rust into this project; input, characters, physics and map-browser fixes belong in RedEngine.

Launch Play-RedEngineSandbox.cmd; M / D-pad up opens project maps, Q / Back switches view.
Map reload resets experiments. See README.md and asset-index.json for the content inventory.
