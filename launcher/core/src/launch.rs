//! Starting an installed game exactly as its own `Play-<slug>.exe` does (`distribution/play_launcher.rs`): the engine named in `engine.name`,
//! the arguments in `launch.args` (one per line), from the game's folder, with `RE2_SAVE_DIR` set to `Saved Games\<name>` and `RE2_PLAYER=1`
//! (fullscreen and the title card). The game's own update check is skipped: the launcher keeps games up to date.
//!
//! A game uploaded ready-made starts the same way, from the folder its program is in (where such games expect to be started). A `.bat` or `.cmd`
//! game gets a console window of its own, since it may be a text game; everything else starts without one.

use std::path::{Path, PathBuf};
use std::process::Command;

use crate::{Error, Result};

#[derive(Debug, Clone, PartialEq)]
pub struct Plan {
    pub program: PathBuf,
    pub args: Vec<String>,
    pub cwd: PathBuf,
    pub save_dir: PathBuf,
}

/// The folder name the installers, `Play-<slug>.exe` and the launcher agree on (`release_tool.clean_name`).
pub fn clean_name(name: &str) -> String {
    name.chars().filter(|c| !"<>:\"/\\|?*".contains(*c)).collect::<String>().trim().to_string()
}

/// `Saved Games\<name>` under the user's profile.
pub fn save_dir(profile: &Path, name: &str) -> PathBuf {
    profile.join("Saved Games").join(clean_name(name))
}

pub fn plan(dir: &Path, name: &str, profile: &Path) -> Result<Plan> {
    let program = crate::archive::check_game(dir)?;
    let args = std::fs::read_to_string(dir.join("launch.args"))?;
    Ok(Plan {
        cwd: program.parent().unwrap_or(dir).to_path_buf(),
        program,
        args: args.lines().map(str::trim).filter(|l| !l.is_empty()).map(String::from).collect(),
        save_dir: save_dir(profile, name),
    })
}

/// Start the game and return at once (the game runs on its own; closing the launcher does not stop it).
pub fn start(plan: &Plan) -> Result<()> {
    std::fs::create_dir_all(&plan.save_dir)?;
    let mut command = Command::new(&plan.program);
    // `RE2_PLAYER`: a player started it, so the engine opens in fullscreen and plays the "RedEngine Games" title card first (an older engine
    // ignores it).
    command.args(&plan.args).current_dir(&plan.cwd).env("RE2_SAVE_DIR", &plan.save_dir).env("RE2_PLAYER", "1");
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const DETACHED_PROCESS: u32 = 0x0000_0008;
        const CREATE_NEW_CONSOLE: u32 = 0x0000_0010;
        // Rust runs a `.bat` / `.cmd` through `cmd.exe` itself, with its arguments escaped.
        command.creation_flags(if is_script(&plan.program) { CREATE_NEW_CONSOLE } else { DETACHED_PROCESS });
    }
    command.spawn().map(|_| ()).map_err(|e| Error::Archive(format!("could not start {}: {e}", plan.program.display())))
}

/// A batch file, which runs in a console window of its own.
pub fn is_script(program: &Path) -> bool {
    program.extension().and_then(|e| e.to_str()).is_some_and(|e| e.eq_ignore_ascii_case("bat") || e.eq_ignore_ascii_case("cmd"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_game_starts_like_its_own_play_exe_with_its_saves_in_saved_games() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("RedEngine.exe"), "MZ").unwrap();
        std::fs::write(dir.path().join("engine.name"), "RedEngine.exe\n").unwrap();
        std::fs::write(dir.path().join("launch.args"), "--host\ncontent/projects/great-outdoors/maps/main.json\n\n").unwrap();
        let p = plan(dir.path(), "Great Outdoors", Path::new("/home/p")).unwrap();
        assert_eq!(p.program, dir.path().join("RedEngine.exe"));
        assert_eq!(p.args, ["--host", "content/projects/great-outdoors/maps/main.json"]);
        assert_eq!(p.save_dir, Path::new("/home/p/Saved Games/Great Outdoors"));
    }

    #[test]
    fn an_uploaded_game_starts_from_its_programs_folder() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::create_dir(dir.path().join("bin")).unwrap();
        std::fs::write(dir.path().join("bin/run.BAT"), "@echo off").unwrap();
        std::fs::write(dir.path().join("engine.name"), "bin/run.BAT\n").unwrap();
        std::fs::write(dir.path().join("launch.args"), "").unwrap();
        let p = plan(dir.path(), "Text Quest", Path::new("/home/p")).unwrap();
        assert_eq!(p.program, dir.path().join("bin/run.BAT"));
        assert_eq!(p.cwd, dir.path().join("bin"));
        assert!(p.args.is_empty());
        assert!(is_script(&p.program) && !is_script(Path::new("Game.exe")));
    }

    #[test]
    fn the_save_folder_name_matches_the_installers() {
        assert_eq!(clean_name(" Tobin: the Baron? "), "Tobin the Baron");
    }
}
