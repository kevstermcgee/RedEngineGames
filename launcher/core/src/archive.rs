//! Unpacking a game's portable ZIP: every entry must stay inside the target folder, and the result must look like a game the launcher can
//! start (`engine.name` naming the program that is there, and `launch.args`). A RedEngine game names its engine beside it; a game uploaded
//! ready-made (`distribution/upload_game.py`) may name a `.exe`, `.bat` or `.cmd` in a subfolder (`bin/Game.exe`).

use std::fs::File;
use std::io;
use std::path::{Component, Path, PathBuf};

use crate::{Error, Result};

pub fn extract(zip_path: &Path, into: &Path) -> Result<()> {
    unpack(zip_path, into)?;
    check_game(into).map(|_| ())
}

/// Unpack any ZIP into `into` (a player's dropped game too), refusing entries that would land outside it.
pub fn unpack(zip_path: &Path, into: &Path) -> Result<()> {
    let mut zip = zip::ZipArchive::new(File::open(zip_path)?).map_err(|e| Error::Archive(e.to_string()))?;
    std::fs::create_dir_all(into)?;
    for i in 0..zip.len() {
        let mut entry = zip.by_index(i).map_err(|e| Error::Archive(e.to_string()))?;
        // `enclosed_name` refuses absolute paths and `..`: an archive cannot write outside the game's folder.
        let Some(relative) = entry.enclosed_name() else {
            return Err(Error::Archive(format!("unsafe path in the archive: {}", entry.name())));
        };
        let target = into.join(relative);
        if entry.is_dir() {
            std::fs::create_dir_all(&target)?;
            continue;
        }
        if let Some(parent) = target.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let mut out = File::create(&target)?;
        io::copy(&mut entry, &mut out)?;
    }
    Ok(())
}

/// The folder holds a runnable game; returns the program `engine.name` names.
pub fn check_game(dir: &Path) -> Result<PathBuf> {
    let engine = std::fs::read_to_string(dir.join("engine.name")).map_err(|_| Error::Archive("engine.name is missing".into()))?;
    let engine = engine.trim();
    let relative = Path::new(engine);
    // Only plain names inside the folder: no drive, no root, no `..`.
    let inside = !engine.is_empty() && relative.components().all(|c| matches!(c, Component::Normal(_))) && !engine.contains(['\\', ':']);
    let program = dir.join(relative);
    if !inside || !program.is_file() {
        return Err(Error::Archive(format!("the engine `{engine}` is missing")));
    }
    if !dir.join("launch.args").is_file() {
        return Err(Error::Archive("launch.args is missing".into()));
    }
    Ok(program)
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    use std::io::Write;

    /// A portable build the way `distribution/release_tool.py` stages one.
    pub fn game_zip(path: &Path, extra: &[(&str, &[u8])]) {
        let mut z = zip::ZipWriter::new(File::create(path).unwrap());
        let o = zip::write::SimpleFileOptions::default();
        for (name, data) in [
            ("RedEngine.exe", &b"MZ engine"[..]),
            ("Play-coin-run.exe", &b"MZ play"[..]),
            ("engine.name", &b"RedEngine.exe\n"[..]),
            ("launch.args", &b"content/games/coin-run/coin_run.json\n"[..]),
            ("play.cfg", &b"name=Coin Run\nslug=coin-run\nversion=2\nmode=portable\n"[..]),
            ("content/games/coin-run/coin_run.json", &b"{}"[..]),
        ]
        .into_iter()
        .chain(extra.iter().copied())
        {
            z.start_file(name, o).unwrap();
            z.write_all(data).unwrap();
        }
        z.finish().unwrap();
    }

    #[test]
    fn a_portable_build_unpacks_into_a_runnable_folder() {
        let dir = tempfile::tempdir().unwrap();
        let zip = dir.path().join("g.zip");
        game_zip(&zip, &[]);
        let into = dir.path().join("game");
        extract(&zip, &into).unwrap();
        assert!(into.join("content/games/coin-run/coin_run.json").is_file());
    }

    #[test]
    fn an_archive_that_escapes_its_folder_is_refused() {
        let dir = tempfile::tempdir().unwrap();
        let zip = dir.path().join("g.zip");
        game_zip(&zip, &[("../evil.txt", b"x")]);
        let e = extract(&zip, &dir.path().join("game")).unwrap_err().to_string();
        assert!(e.contains("unsafe path"), "{e}");
        assert!(!dir.path().join("evil.txt").exists());
    }

    #[test]
    fn an_uploaded_game_may_start_a_program_in_a_subfolder_but_never_outside_its_own() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::create_dir(dir.path().join("bin")).unwrap();
        std::fs::write(dir.path().join("bin/Star Miner.exe"), "MZ").unwrap();
        std::fs::write(dir.path().join("launch.args"), "").unwrap();
        std::fs::write(dir.path().join("engine.name"), "bin/Star Miner.exe\n").unwrap();
        assert_eq!(check_game(dir.path()).unwrap(), dir.path().join("bin/Star Miner.exe"));
        for bad in ["../outside.exe", "/etc/passwd", "bin\\..\\..\\x.exe", "C:x.exe", "bin/../../x.exe"] {
            std::fs::write(dir.path().join("engine.name"), bad).unwrap();
            assert!(check_game(dir.path()).is_err(), "{bad}");
        }
    }

    #[test]
    fn a_folder_without_its_engine_is_not_a_game() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("engine.name"), "RedEngine.exe").unwrap();
        std::fs::write(dir.path().join("launch.args"), "x").unwrap();
        assert!(check_game(dir.path()).unwrap_err().to_string().contains("RedEngine.exe"));
    }
}
