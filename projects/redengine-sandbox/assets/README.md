# Game-local assets

`gameplay.json` is this game's incubator for specialized prefabs. Search the core first, prefer an
`extends` variant second, and create a new definition only when neither fits.
For this generated project, edit the LOCAL definitions in scripts/generate.py and regenerate;
the generator writes this library and embeds it into the maps, so they remain self-contained.

Discover local and core assets together:

```bash
scripts/red catalog --library assets/gameplay.json "what I need"
```

Use the structured `meta` fields shown by `scripts/red catalog --manifest`. If an asset proves useful
across games, propose it for the narrowest engine pack; do not copy the whole local library into core.
