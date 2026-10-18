# RedEngine Games app: changes

Each version's "- " lines become its release notes and the text of the update banner in the app. Bump `version` in `Cargo.toml` and add a section
here to publish a new version (`.github/workflows/launcher.yml`).

## 0.1.0

- The first version: every game on the site in one app, with its wiki, and one-click install, play, update and uninstall.
- Games download one at a time from a queue, are checked against their published SHA-256, and update without losing your saves.
- The app checks for a newer version of itself and updates in place when you say so.
