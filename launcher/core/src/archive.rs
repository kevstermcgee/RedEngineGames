//! Unpacking a game's portable ZIP: every entry must stay inside the target folder, and the result must look like a game the launcher can
//! start (`engine.name` naming the program that is there, and `launch.args`). A RedEngine game names its engine beside it; a game uploaded
//! ready-made (`distribution/upload_game.py`) may name a `.exe`, `.bat` or `.cmd` in a subfolder (`bin/Game.exe`).
//!
//! What a member may be called is one rule ([`member_path`]), the one `crate::meta` reads a hostile ZIP by too, so a ZIP is the same game to the
//! window and to the command line.

use std::fs::File;
use std::io;
use std::path::{Component, Path, PathBuf};

use crate::{Error, Result};

/// The deepest a member may sit in a ZIP (parts of its name), and the longest its name may be (bytes). Nothing a game needs is deeper or longer, and
/// a folder tree is walked a level at a time.
pub(crate) const MAX_DEPTH: usize = 64;
const MAX_NAME: usize = 1024;

/// A name Windows takes for a device (`CON`, `aux.txt`, `Com1 .bat`): creating or opening it is not making or opening a file.
pub(crate) fn device(part: &str) -> bool {
    let stem = part.split('.').next().unwrap_or("").trim_end_matches(' ').to_ascii_lowercase();
    let numbered = |p: &str| stem.strip_prefix(p).is_some_and(|n| matches!(n.as_bytes(), [b'1'..=b'9']));
    matches!(stem.as_str(), "con" | "prn" | "aux" | "nul" | "conin$" | "conout$") || numbered("com") || numbered("lpt")
}

/// Where a ZIP member goes inside the folder it is unpacked into (a backslash separates, as it does where the app unpacks the game): `None` for a name
/// of more than 1024 bytes or 64 parts, with an empty or `..` part, a NUL, a root or a drive, or that names a device.
pub(crate) fn member_path(name: &str) -> Option<PathBuf> {
    let name = name.replace('\\', "/");
    let parts: Vec<&str> = name.strip_suffix('/').unwrap_or(&name).split('/').collect();
    let plain = name.len() <= MAX_NAME && parts.len() <= MAX_DEPTH && !name.contains('\0') && !parts.iter().any(|p| matches!(*p, "" | "..") || device(p));
    let path = PathBuf::from(name);
    (plain && path.components().all(|c| matches!(c, Component::Normal(_) | Component::CurDir))).then_some(path)
}

pub fn extract(zip_path: &Path, into: &Path) -> Result<()> {
    unpack(zip_path, into)?;
    check_game(into).map(|_| ())
}

/// Unpack any ZIP into `into` (a player's dropped game too), refusing a name that [`member_path`] refuses, so an archive cannot write outside the
/// game's folder. A link in it is an empty folder: what it holds is its target's name, which is no file.
pub fn unpack(zip_path: &Path, into: &Path) -> Result<()> {
    let mut zip = zip::ZipArchive::new(File::open(zip_path)?).map_err(|e| Error::Archive(e.to_string()))?;
    std::fs::create_dir_all(into)?;
    for i in 0..zip.len() {
        let mut entry = zip.by_index(i).map_err(|e| Error::Archive(e.to_string()))?;
        let Some(relative) = member_path(entry.name()) else {
            return Err(Error::Archive(format!("unsafe path in the archive: {}", entry.name())));
        };
        let target = into.join(relative);
        let link = entry.unix_mode().is_some_and(|m| m & 0o170_000 == 0o120_000);
        if entry.is_dir() || link {
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

    fn zip_of(path: &Path, members: &[(&str, &[u8])]) {
        let mut z = zip::ZipWriter::new(File::create(path).unwrap());
        for (name, data) in members {
            z.start_file(*name, zip::write::SimpleFileOptions::default()).unwrap();
            z.write_all(data).unwrap();
        }
        z.finish().unwrap();
    }

    #[test]
    fn what_a_member_may_be_called_is_one_rule() {
        for name in ["Game.exe", "bin/Game.exe", "bin/", "./Game.exe", "a\\b.exe", "dir\\", &"a/".repeat(63), &format!("{}x.exe", "a/".repeat(63))] {
            assert!(member_path(name).is_some(), "{name:?}");
        }
        for name in ["../x.exe", "a/../x.exe", "/x.exe", "a//b", "", "..", "a\\..\\b", "x\0.exe", "aux.bat", "dir/NUL", "com1.txt", "LPT9", "con .exe", "Conout$.x"] {
            assert!(member_path(name).is_none(), "{name:?}");
        }
        assert!(member_path(&format!("{}y.exe", "a/".repeat(64))).is_none(), "65 parts");
        let long = |n: usize| format!("{}x.exe", format!("{}/", "d".repeat(99)).repeat(n));
        assert!(member_path(&long(10)).is_some() && member_path(&long(11)).is_none(), "1007 bytes and 1107");
        let exact = format!("{}{}", "d".repeat(99) + "/", "e".repeat(1024 - 100));
        assert_eq!((exact.len(), member_path(&exact).is_some(), member_path(&format!("{exact}e")).is_some()), (1024, true, false));
        for name in ["con", "CON", "prn", "aux.txt", "NUL.tar.gz", "com1", "COM9.exe", "lpt5", "Con .bat", "conin$", "CONOUT$"] {
            assert!(device(name), "{name}");
        }
        for name in ["console", "com", "com0", "com10", "lpt", "auxiliary.exe", "xcon", "nu", "con.", "game.con"] {
            assert!(!device(name) || name == "con.", "{name}");
        }
        assert!(device("con."), "a trailing dot is dropped by Windows too");
    }

    #[test]
    fn an_archive_nested_deeper_than_a_game_can_be_is_refused_and_does_not_overflow_a_stack() {
        let dir = tempfile::tempdir().unwrap();
        let zip = dir.path().join("deep.zip");
        zip_of(&zip, &[(&format!("{}x.bat", "a/".repeat(1900)), b"@echo off"), ("other.txt", b"x")]);
        let e = unpack(&zip, &dir.path().join("game")).unwrap_err().to_string();
        assert!(e.contains("unsafe path"), "{e}");
        assert!(!dir.path().join("game/a/a").exists(), "nothing was made before the refusal");
        let ok = dir.path().join("ok.zip");
        zip_of(&ok, &[(&format!("{}x.bat", "a/".repeat(63)), b"@echo off")]);
        unpack(&ok, &dir.path().join("fine")).unwrap();
    }

    #[test]
    fn a_name_that_leaves_by_way_of_dots_or_names_a_device_is_refused_and_a_link_is_an_empty_folder() {
        let dir = tempfile::tempdir().unwrap();
        for (i, name) in ["x/../y.bat", "a//b.bat", "aux.bat", "sub\\..\\y.bat"].into_iter().enumerate() {
            let zip = dir.path().join(format!("{i}.zip"));
            zip_of(&zip, &[(name, b"@echo off"), ("ok.txt", b"x")]);
            let e = unpack(&zip, &dir.path().join(format!("game{i}"))).unwrap_err().to_string();
            assert!(e.contains("unsafe path"), "{name}: {e}");
        }
        let zip = dir.path().join("link.zip");
        let mut z = zip::ZipWriter::new(File::create(&zip).unwrap());
        z.start_file("Game.exe", zip::write::SimpleFileOptions::default()).unwrap();
        z.write_all(b"MZ").unwrap();
        z.add_symlink("lnk.exe", "Game.exe", zip::write::SimpleFileOptions::default()).unwrap();
        z.finish().unwrap();
        unpack(&zip, &dir.path().join("linked")).unwrap();
        assert!(dir.path().join("linked/Game.exe").is_file() && dir.path().join("linked/lnk.exe").is_dir(), "the link's text is no program");
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
