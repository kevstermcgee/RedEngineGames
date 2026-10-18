//! The player's installed games: `library.json` plus one folder per game. Installing unpacks into a fresh `v<N>` folder and only then switches
//! the record over, so a failed or cancelled update leaves the old version playable.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::sync::atomic::AtomicBool;

use serde::{Deserialize, Serialize};

use crate::catalog::{Game, Version};
use crate::download::Progress;
use crate::{Error, Result};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Installed {
    pub name: String,
    pub version: u64,
    /// Relative to the library root (`games/<slug>/v<N>`).
    pub dir: String,
    #[serde(default)]
    pub installed: String,
    #[serde(default)]
    pub played: String,
}

#[derive(Debug, Default, Clone, Serialize, Deserialize)]
struct State {
    #[serde(default)]
    games: BTreeMap<String, Installed>,
}

/// A game as the window shows it.
#[derive(Debug, Clone, Serialize, PartialEq)]
#[serde(tag = "state", rename_all = "snake_case")]
pub enum Status {
    NotInstalled,
    Installed { version: u64 },
    UpdateAvailable { version: u64, latest: u64 },
}

pub struct Library {
    root: PathBuf,
    state: State,
}

impl Library {
    /// `root` is `%LOCALAPPDATA%\RedEngineGames` on Windows.
    pub fn open(root: &Path) -> Result<Library> {
        std::fs::create_dir_all(root)?;
        let state = match std::fs::read_to_string(root.join("library.json")) {
            Ok(text) => serde_json::from_str(&text).unwrap_or_default(),
            Err(_) => State::default(),
        };
        let mut lib = Library { root: root.to_path_buf(), state };
        lib.forget_missing()?;
        Ok(lib)
    }

    pub fn root(&self) -> &Path {
        &self.root
    }

    fn save(&self) -> Result<()> {
        let tmp = self.root.join("library.json.tmp");
        std::fs::write(&tmp, serde_json::to_string_pretty(&self.state).expect("state serializes"))?;
        std::fs::rename(tmp, self.root.join("library.json"))?;
        Ok(())
    }

    /// A game whose folder was deleted by hand is no longer installed.
    fn forget_missing(&mut self) -> Result<()> {
        let before = self.state.games.len();
        let root = self.root.clone();
        self.state.games.retain(|_, g| root.join(&g.dir).is_dir());
        if self.state.games.len() != before {
            self.save()?;
        }
        Ok(())
    }

    pub fn installed(&self, slug: &str) -> Option<&Installed> {
        self.state.games.get(slug)
    }

    pub fn all(&self) -> &BTreeMap<String, Installed> {
        &self.state.games
    }

    pub fn status(&self, game: &Game) -> Status {
        match (self.installed(&game.slug), game.latest()) {
            (None, _) => Status::NotInstalled,
            (Some(i), Some(l)) if l.version > i.version => Status::UpdateAvailable { version: i.version, latest: l.version },
            (Some(i), _) => Status::Installed { version: i.version },
        }
    }

    pub fn dir(&self, slug: &str) -> Result<PathBuf> {
        Ok(self.root.join(&self.installed(slug).ok_or_else(|| Error::NotInstalled(slug.into()))?.dir))
    }

    /// Download and install `version` of `game` (the latest when `None`), replacing an older one.
    pub fn install(&mut self, game: &Game, version: Option<u64>, today: &str, cancel: &AtomicBool, progress: &mut dyn FnMut(Progress)) -> Result<()> {
        let v = pick(game, version)?;
        let zip = self.root.join("downloads").join(&v.zip.name);
        crate::download::file(&v.zip.url, &zip, v.zip.size, &v.zip.sha256, &game.name, cancel, progress)?;
        let result = self.install_zip(game, v, &zip, today);
        let _ = std::fs::remove_file(&zip);
        result
    }

    /// Install from an already downloaded and checked ZIP.
    pub fn install_zip(&mut self, game: &Game, v: &Version, zip: &Path, today: &str) -> Result<()> {
        let rel = format!("games/{}/v{}", game.slug, v.version);
        let target = self.root.join(&rel);
        let staging = self.root.join(format!("games/{}/.v{}-unpacking", game.slug, v.version));
        let _ = std::fs::remove_dir_all(&staging);
        if let Err(e) = crate::archive::extract(zip, &staging) {
            let _ = std::fs::remove_dir_all(&staging);
            return Err(e);
        }
        let _ = std::fs::remove_dir_all(&target);
        std::fs::rename(&staging, &target)?;
        let old = self.state.games.insert(
            game.slug.clone(),
            Installed { name: game.name.clone(), version: v.version, dir: rel.clone(), installed: today.into(), played: String::new() },
        );
        self.save()?;
        if let Some(old) = old.filter(|o| o.dir != rel) {
            let _ = std::fs::remove_dir_all(self.root.join(old.dir));
        }
        Ok(())
    }

    /// Remove the game's files (never its saves, which are in `Saved Games`).
    pub fn uninstall(&mut self, slug: &str) -> Result<()> {
        self.state.games.remove(slug).ok_or_else(|| Error::NotInstalled(slug.into()))?;
        self.save()?;
        let _ = std::fs::remove_dir_all(self.root.join("games").join(slug));
        Ok(())
    }

    pub fn mark_played(&mut self, slug: &str, today: &str) -> Result<()> {
        if let Some(g) = self.state.games.get_mut(slug) {
            g.played = today.into();
            self.save()?;
        }
        Ok(())
    }
}

fn pick(game: &Game, version: Option<u64>) -> Result<&Version> {
    match version {
        Some(n) => game.versions.iter().find(|v| v.version == n),
        None => game.latest(),
    }
    .ok_or_else(|| Error::NoBuild(game.name.clone()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::archive::tests::game_zip;
    use crate::catalog::Asset;

    fn game(versions: &[u64]) -> Game {
        Game {
            slug: "coin-run".into(),
            name: "Coin Run".into(),
            description: String::new(),
            added: String::new(),
            online: String::new(),
            author: "human".into(),
            presentation: "3d".into(),
            versions: versions
                .iter()
                .map(|&n| Version {
                    version: n,
                    released: String::new(),
                    notes: vec![],
                    zip: Asset { name: format!("coin-run-{n}.zip"), size: 0, sha256: String::new(), url: String::new() },
                })
                .collect(),
            wiki: None,
        }
    }

    #[test]
    fn install_update_and_uninstall_keep_one_folder_and_a_record() {
        let dir = tempfile::tempdir().unwrap();
        let zip = dir.path().join("g.zip");
        game_zip(&zip, &[]);
        let mut lib = Library::open(&dir.path().join("lib")).unwrap();
        let g = game(&[1, 2]);
        assert_eq!(lib.status(&g), Status::NotInstalled);

        lib.install_zip(&g, &g.versions[0], &zip, "2026-10-18").unwrap();
        assert_eq!(lib.status(&g), Status::UpdateAvailable { version: 1, latest: 2 });
        assert!(lib.dir("coin-run").unwrap().join("RedEngine.exe").is_file());

        lib.install_zip(&g, &g.versions[1], &zip, "2026-10-19").unwrap();
        assert_eq!(lib.status(&g), Status::Installed { version: 2 });
        assert!(!dir.path().join("lib/games/coin-run/v1").exists(), "the old version is removed after the switch");

        let reopened = Library::open(&dir.path().join("lib")).unwrap();
        assert_eq!(reopened.installed("coin-run").unwrap().version, 2, "the record survives a restart");

        lib.uninstall("coin-run").unwrap();
        assert_eq!(lib.status(&g), Status::NotInstalled);
        assert!(!dir.path().join("lib/games/coin-run").exists());
    }

    #[test]
    fn a_broken_update_leaves_the_old_version_playable() {
        let dir = tempfile::tempdir().unwrap();
        let good = dir.path().join("good.zip");
        game_zip(&good, &[]);
        let bad = dir.path().join("bad.zip");
        std::fs::write(&bad, b"not a zip").unwrap();
        let mut lib = Library::open(&dir.path().join("lib")).unwrap();
        let g = game(&[1, 2]);
        lib.install_zip(&g, &g.versions[0], &good, "d").unwrap();
        assert!(lib.install_zip(&g, &g.versions[1], &bad, "d").is_err());
        assert_eq!(lib.installed("coin-run").unwrap().version, 1);
        assert!(lib.dir("coin-run").unwrap().join("RedEngine.exe").is_file());
        assert!(!dir.path().join("lib/games/coin-run/.v2-unpacking").exists());
    }

    #[test]
    fn a_game_folder_deleted_by_hand_is_forgotten() {
        let dir = tempfile::tempdir().unwrap();
        let zip = dir.path().join("g.zip");
        game_zip(&zip, &[]);
        let mut lib = Library::open(&dir.path().join("lib")).unwrap();
        let g = game(&[1]);
        lib.install_zip(&g, &g.versions[0], &zip, "d").unwrap();
        std::fs::remove_dir_all(dir.path().join("lib/games/coin-run")).unwrap();
        assert!(Library::open(&dir.path().join("lib")).unwrap().installed("coin-run").is_none());
    }
}
