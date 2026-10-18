//! Starting an installed game exactly as its own `Play-<slug>.exe` does (`distribution/play_launcher.rs`): the engine named in `engine.name`,
//! the arguments in `launch.args` (one per line), from the game's folder, with `RE2_SAVE_DIR` set to `Saved Games\<name>`. The game's own update
//! check is skipped: the launcher keeps games up to date.

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
    crate::archive::check_game(dir)?;
    let engine = std::fs::read_to_string(dir.join("engine.name"))?;
    let args = std::fs::read_to_string(dir.join("launch.args"))?;
    Ok(Plan {
        program: dir.join(engine.trim()),
        args: args.lines().map(str::trim).filter(|l| !l.is_empty()).map(String::from).collect(),
        cwd: dir.to_path_buf(),
        save_dir: save_dir(profile, name),
    })
}

/// Start the game and return at once (the game runs on its own; closing the launcher does not stop it).
pub fn start(plan: &Plan) -> Result<()> {
    std::fs::create_dir_all(&plan.save_dir)?;
    let mut command = Command::new(&plan.program);
    command.args(&plan.args).current_dir(&plan.cwd).env("RE2_SAVE_DIR", &plan.save_dir);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const DETACHED_PROCESS: u32 = 0x0000_0008;
        command.creation_flags(DETACHED_PROCESS);
    }
    command.spawn().map(|_| ()).map_err(|e| Error::Archive(format!("could not start {}: {e}", plan.program.display())))
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
    fn the_save_folder_name_matches_the_installers() {
        assert_eq!(clean_name(" Tobin: the Baron? "), "Tobin the Baron");
    }
}
