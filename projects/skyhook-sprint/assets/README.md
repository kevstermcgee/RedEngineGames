# Game-local assets

`gameplay.json` is this game's incubator for specialized prefabs. Search the core first, prefer an
`extends` variant second, and create a new definition only when neither fits. The main blueprint
already includes this file through `prefab_files`, so built maps remain self-contained.

Discover local and core assets together:

```bash
scripts/red catalog --library assets/gameplay.json "what I need"
```

Use the structured `meta` fields shown by `scripts/red catalog --manifest`. If an asset proves useful
across games, propose it for the narrowest engine pack; do not copy the whole local library into core.
