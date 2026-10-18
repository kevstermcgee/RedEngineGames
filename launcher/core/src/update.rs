//! The launcher updating itself. The site publishes `launcher/latest.json` (written by `site/generate.py` from the newest `launcher-v*`
//! release): `{"version": "0.2.0", "installer": {"name", "size", "sha256", "url"}, "notes": [...]}`. When it names a newer version the launcher
//! downloads that installer, checks its SHA-256 and runs it without questions; files the launcher downloads itself carry no "from the internet" mark, so
//! Windows does not stop the update with a SmartScreen prompt.

use serde::{Deserialize, Serialize};

use crate::catalog::Asset;
use crate::{Error, Result};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Latest {
    pub version: String,
    pub installer: Asset,
    #[serde(default)]
    pub notes: Vec<String>,
}

/// `a` is newer than `b` (dotted numbers; anything unparsable counts as 0).
pub fn newer(a: &str, b: &str) -> bool {
    let parse = |s: &str| s.trim_start_matches('v').split('.').map(|p| p.parse::<u64>().unwrap_or(0)).collect::<Vec<_>>();
    let (mut x, mut y) = (parse(a), parse(b));
    let n = x.len().max(y.len());
    x.resize(n, 0);
    y.resize(n, 0);
    x > y
}

/// The newer launcher, if the site has one.
pub fn check(site: &str, current: &str) -> Result<Option<Latest>> {
    let url = format!("{site}launcher/latest.json");
    let latest: Latest = serde_json::from_str(&crate::download::text(&url)?).map_err(|e| Error::Catalog(e.to_string()))?;
    Ok(newer(&latest.version, current).then_some(latest))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn versions_compare_as_numbers() {
        assert!(newer("0.10.0", "0.9.3"));
        assert!(newer("1.0", "0.99.99"));
        assert!(!newer("0.2.0", "0.2.0"));
        assert!(!newer("0.1.9", "0.2"));
        assert!(newer("v0.2.1", "0.2.0"));
    }

    #[test]
    fn the_site_file_parses() {
        let l: Latest = serde_json::from_str(r#"{"version": "0.2.0", "installer": {"name": "RedEngineGames-0.2.0-setup.exe", "size": 5, "sha256": "ab", "url": "https://x"}}"#).unwrap();
        assert_eq!(l.installer.size, 5);
    }
}

/// The first argument that turns the launcher into its own updater (see `run_helper`).
pub const HELPER_FLAG: &str = "--apply-update";

/// What the installer is run with: Tauri's NSIS installer in passive update mode (a progress bar and no questions; keeps the install folder and
/// shortcuts; it does not restart the app itself, the helper does).
pub const INSTALLER_ARGS: [&str; 2] = ["/P", "/UPDATE"];

/// The updater, run from a copy of the launcher with `[old pid, installer, launcher exe]`: wait until the old launcher has closed (its file can be
/// opened for writing again; a running executable cannot be on Windows), run the installer and wait for it, then start the launcher.
/// Returns the process exit code. The pid is informational: the file check is what proves the old launcher is gone.
pub fn run_helper(args: &[String]) -> i32 {
    let [_pid, installer, exe] = args else {
        return 2;
    };
    let exe = std::path::Path::new(exe);
    for _ in 0..120 {
        if std::fs::OpenOptions::new().append(true).open(exe).is_ok() {
            break;
        }
        std::thread::sleep(std::time::Duration::from_millis(250));
    }
    let installed = std::process::Command::new(installer).args(INSTALLER_ARGS).status().map(|s| s.success()).unwrap_or(false);
    let _ = std::fs::remove_file(installer);
    let _ = std::process::Command::new(exe).spawn();
    if installed { 0 } else { 1 }
}

#[cfg(all(test, unix))]
mod helper_tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;

    fn script(path: &std::path::Path, body: &str) {
        std::fs::write(path, format!("#!/bin/sh\n{body}\n")).unwrap();
        std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o755)).unwrap();
    }

    #[test]
    fn the_helper_runs_the_installer_then_starts_the_launcher() {
        let dir = tempfile::tempdir().unwrap();
        let log = dir.path().join("log");
        let installer = dir.path().join("setup.sh");
        let exe = dir.path().join("launcher.sh");
        script(&installer, &format!("echo \"installed $*\" >> {}", log.display()));
        script(&exe, &format!("echo started >> {}", log.display()));
        let code = run_helper(&["1".into(), installer.display().to_string(), exe.display().to_string()]);
        assert_eq!(code, 0);
        for _ in 0..40 {
            if std::fs::read_to_string(&log).unwrap_or_default().contains("started") {
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(50));
        }
        assert_eq!(std::fs::read_to_string(&log).unwrap(), "installed /P /UPDATE\nstarted\n");
        assert!(!installer.exists(), "the downloaded installer is cleaned up");
    }

    #[test]
    fn the_helper_refuses_wrong_arguments() {
        assert_eq!(run_helper(&["x".into()]), 2);
    }
}
