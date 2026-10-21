//! Forking a game from the window: a copy of the installed version in `forks/<slug>/` under the library, which the player (or their AI) changes,
//! with `fork.json` saying which game and version it came from. Dropping that folder back on the window (`crate::upload::stage` reads the
//! record) publishes it as a game of its own whose releases name their parent, so the site and every app draw the family. The other way to
//! fork is from the game's source, in a RedEngine checkout (`scripts/games.py fork`), which the game's web page explains.
//!
//! The fork also gets its own game card (`crate::meta`): its name, where it came from and how the parent looks, and none of the parent's
//! description, author, online note, screenshot, `entry`, `args` or notes, because the fork is somebody else's game (what starts it stays in
//! `engine.name` and `launch.args`).

use std::io::Read;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::{Error, Result};

/// The record a fork carries in its folder.
pub const RECORD: &str = "fork.json";
/// What the folder is and what to do with it, for the player and their AI.
pub const GUIDE: &str = "FORK.md";

/// The game a fork came from and the version it was copied at: the edge of the family tree (`forked_from` in the catalog and in every release).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Parent {
    pub slug: String,
    pub version: u64,
}

#[derive(Serialize, Deserialize)]
struct Record {
    forked_from: Parent,
    name: String,
}

/// Copy the installed game in `installed` (version `parent.version` of `parent_name`) to `forks/<slug of name>/` under `root`, with its record,
/// card and guide; returns the new folder. A name already used by another fork here, or the parent's own, is refused.
pub fn make(root: &Path, installed: &Path, parent: &Parent, parent_name: &str, name: &str) -> Result<PathBuf> {
    make_with(root, installed, parent, parent_name, name, None)
}

/// As [`make`], for a parent whose record on the site says it is `presentation` (`2d`, `3d` or `hybrid`): the fork's card keeps that when the
/// parent's own card says nothing.
pub fn make_with(root: &Path, installed: &Path, parent: &Parent, parent_name: &str, name: &str, presentation: Option<&str>) -> Result<PathBuf> {
    let name = name.split_whitespace().collect::<Vec<_>>().join(" ");
    let slug = crate::upload::slugify(&name);
    if slug.is_empty() {
        return Err(Error::Upload("Give your version a name (letters or digits).".into()));
    }
    if slug == parent.slug {
        return Err(Error::Upload(format!("That is {parent_name}'s own name: give your version another.")));
    }
    let folder = root.join("forks").join(&slug);
    if folder.exists() {
        return Err(Error::Upload(format!("You already have a fork called {name}: open it (Forks folder), or pick another name.")));
    }
    if !installed.is_dir() {
        return Err(Error::NotInstalled(parent.slug.clone()));
    }
    crate::upload::copy_tree(installed, &folder)?;
    let record = Record { forked_from: parent.clone(), name: name.clone() };
    std::fs::write(folder.join(RECORD), serde_json::to_string_pretty(&record).expect("a record serializes") + "\n")?;
    std::fs::write(folder.join(GUIDE), guide(parent, parent_name, &name))?;
    let look = crate::meta::read_card_file(installed).and_then(|c| c.presentation).or_else(|| presentation.map(String::from));
    let card = crate::meta::Card { name: Some(name), forked_from: Some(parent.clone()), presentation: look, ..Default::default() };
    crate::meta::write_card_file(&folder, &card)?;
    // The parent's screenshot, as the app put it beside its card, is not the fork's.
    for ext in ["png", "jpg"] {
        let _ = std::fs::remove_file(folder.join(format!("{}.{ext}", crate::meta::THUMB)));
    }
    Ok(folder)
}

/// The parent and the fork's name, when `folder` (or the folder it was copied from, one level up) holds a fork's record (of 16 KiB at most: it is
/// two names and a number).
pub fn read(folder: &Path) -> Option<(Parent, String)> {
    let mut text = String::new();
    std::fs::File::open(folder.join(RECORD)).ok()?.take(16 * 1024 + 1).read_to_string(&mut text).ok().filter(|&n| n <= 16 * 1024)?;
    let r: Record = serde_json::from_str(&text).ok()?;
    let slug_ok = !r.forked_from.slug.is_empty() && r.forked_from.slug.len() <= crate::meta::MAX_SLUG && r.forked_from.slug == crate::upload::slugify(&r.forked_from.slug);
    (slug_ok && r.forked_from.version >= 1).then_some((r.forked_from, r.name))
}

fn guide(parent: &Parent, parent_name: &str, name: &str) -> String {
    format!(
        "# {name}: a fork of {parent_name} version {v}

This folder is a copy of {parent_name} version {v} as it was installed. Change it, then **drop this whole folder on the RedEngine Games
app** and choose **Publish for everyone**: it becomes a game of its own, and the website and the app show it under {parent_name} in its
family. `{RECORD}` says where it came from: keep it.

- A RedEngine game is data: its scenes, rules, sprites, sounds and music are JSON files under `content/`. `engine.name` names the program
  that plays it and `launch.args` what that program opens.
- **With an AI** (Claude Code): open this folder and say what you want different. Tell it the game is RedEngine JSON under `content/`, to
  keep `{RECORD}`, `engine.name` and `launch.args` as they are, and to run the game to check its change. `{CARD}` is the game's card (its
  name, where it came from and how it looks); keep it too, and have the AI put a `description` and an `author` (`ai` or `human`) in it
  that say what your version is, so publishing it needs no typing.
- **Try it** before publishing: drop the folder on the app and choose **Add to my games**, then play it from your library.

A fork published from the app ships as a ZIP with the engine it was copied with. To make it part of RedEngine itself instead (checked by
CI, rebuilt with every engine update, with an installer), fork it from the game's source in a RedEngine checkout:

    python3 scripts/games.py fork {slug}@v{v} <your-slug> --name \"{name}\"

(the game's web page, under Family, has the whole prompt to give an AI).
",
        v = parent.version,
        slug = parent.slug,
        CARD = crate::meta::FILE,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn installed(root: &Path) -> PathBuf {
        let dir = root.join("games/snake/v3");
        std::fs::create_dir_all(dir.join("content/games/snake")).unwrap();
        std::fs::write(dir.join("engine.name"), "RedEngine2D.exe\n").unwrap();
        std::fs::write(dir.join("content/games/snake/snake.game2d.json"), "{}").unwrap();
        dir
    }

    #[test]
    fn a_fork_is_a_copy_with_its_record_and_guide_and_reads_back() {
        let t = tempfile::tempdir().unwrap();
        let parent = Parent { slug: "snake".into(), version: 3 };
        let folder = make(t.path(), &installed(t.path()), &parent, "Snake", "  Neon   Snake ").unwrap();
        assert_eq!(folder, t.path().join("forks/neon-snake"));
        assert_eq!(std::fs::read_to_string(folder.join("content/games/snake/snake.game2d.json")).unwrap(), "{}");
        assert!(std::fs::read_to_string(folder.join(GUIDE)).unwrap().contains("a fork of Snake version 3"));
        assert_eq!(read(&folder), Some((parent.clone(), "Neon Snake".to_string())));
        assert!(make(t.path(), &installed(t.path()), &parent, "Snake", "Neon Snake").is_err(), "a second fork of the same name");
        assert!(make(t.path(), &installed(t.path()), &parent, "Snake", "SNAKE").is_err(), "the parent's own name");
        assert!(make(t.path(), &t.path().join("nowhere"), &parent, "Snake", "Other").is_err(), "not installed");
    }

    #[test]
    fn a_fork_has_its_own_card_with_its_name_its_parent_and_the_parents_look_and_nothing_else() {
        let t = tempfile::tempdir().unwrap();
        let dir = installed(t.path());
        std::fs::write(dir.join("redengine-game.json"), r#"{"name": "Snake", "description": "Eat.", "presentation": "2d", "author": "ai", "online": "Co-op", "thumb": "redengine-game-thumb.png", "notes": ["x"], "args": ["a"], "entry": "RedEngine2D.exe"}"#).unwrap();
        std::fs::write(dir.join("redengine-game-thumb.png"), "png").unwrap();
        std::fs::write(dir.join("RedEngine2D.exe"), "MZ").unwrap();
        let parent = Parent { slug: "snake".into(), version: 3 };
        let folder = make_with(t.path(), &dir, &parent, "Snake", "Neon Snake", Some("3d")).unwrap();
        let card = crate::meta::read_card_file(&folder).unwrap();
        assert_eq!(card, crate::meta::Card { name: Some("Neon Snake".into()), presentation: Some("2d".into()), forked_from: Some(parent.clone()), ..Default::default() }, "the parent's own card says 2d, whatever the record says");
        let text = std::fs::read_to_string(folder.join(crate::meta::FILE)).unwrap();
        assert!(text.contains("\"schema\": 1") && !text.contains("Eat") && !text.contains("Co-op"), "{text}");
        assert!(!folder.join("redengine-game-thumb.png").exists(), "the parent's screenshot is left behind");
        assert!(folder.join(RECORD).is_file() && folder.join(GUIDE).is_file() && folder.join("RedEngine2D.exe").is_file());
        assert!(dir.join("redengine-game-thumb.png").is_file() && std::fs::read_to_string(dir.join("redengine-game.json")).unwrap().contains("Eat"), "the installed game is not touched");
        // No card on the parent: the site's record gives the look; with neither, the fork says nothing about it.
        std::fs::remove_file(dir.join("redengine-game.json")).unwrap();
        let folder = make_with(t.path(), &dir, &parent, "Snake", "Neon Two", Some("hybrid")).unwrap();
        assert_eq!(crate::meta::read_card_file(&folder).unwrap().presentation.as_deref(), Some("hybrid"));
        let folder = make(t.path(), &dir, &parent, "Snake", "Neon Three").unwrap();
        let card = crate::meta::read_card_file(&folder).unwrap();
        assert_eq!((card.name.as_deref(), card.presentation, card.forked_from), (Some("Neon Three"), None, Some(parent.clone())));
        let folder = make_with(t.path(), &dir, &parent, "Snake", "Neon Four", Some("sideways")).unwrap();
        assert_eq!(crate::meta::read_card_file(&folder).unwrap().presentation, None, "an unknown look is not written");
    }

    #[test]
    fn a_guide_tells_the_player_and_their_ai_to_keep_the_card() {
        let guide = guide(&Parent { slug: "snake".into(), version: 3 }, "Snake", "Neon Snake");
        assert!(guide.contains("redengine-game.json") && guide.contains("description") && guide.contains("fork.json"), "{guide}");
    }

    #[test]
    fn a_record_that_is_too_long_or_names_a_parent_slug_no_game_has_is_not_a_fork() {
        let t = tempfile::tempdir().unwrap();
        let record = |slug: &str| format!(r#"{{"forked_from": {{"slug": "{slug}", "version": 1}}, "name": "x"}}"#);
        std::fs::write(t.path().join(RECORD), record(&"a".repeat(64))).unwrap();
        assert_eq!(read(t.path()).map(|(p, _)| p.slug.len()), Some(64));
        std::fs::write(t.path().join(RECORD), record(&"a".repeat(65))).unwrap();
        assert_eq!(read(t.path()), None, "a slug is made from a name of 60 characters");
        std::fs::write(t.path().join(RECORD), format!("{}{}", record("snake"), " ".repeat(20_000))).unwrap();
        assert_eq!(read(t.path()), None, "a record is small: a big file is not read whole");
        std::fs::write(t.path().join(RECORD), b"\xff\xfe not text").unwrap();
        assert_eq!(read(t.path()), None);
    }

    #[test]
    fn a_folder_without_a_sound_record_is_not_a_fork() {
        let t = tempfile::tempdir().unwrap();
        assert_eq!(read(t.path()), None);
        std::fs::write(t.path().join(RECORD), r#"{"forked_from": {"slug": "Bad Slug", "version": 1}, "name": "x"}"#).unwrap();
        assert_eq!(read(t.path()), None);
        std::fs::write(t.path().join(RECORD), r#"{"forked_from": {"slug": "snake", "version": 0}, "name": "x"}"#).unwrap();
        assert_eq!(read(t.path()), None);
    }
}
