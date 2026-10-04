//! `Play-<slug>.exe`: starts one game, keeps its progress in `Saved Games`, and offers an update when a newer version has been released.
//!
//! It sits next to `RedEngine.exe` (`engine.name`), the game's command line (`launch.args`) and `play.cfg`, which says which game and version this is:
//!
//! ```text
//! name=Marcel
//! slug=marcel
//! version=3                 (a whole number that grows with every release of the game)
//! mode=installed            (installed: updates itself through the installer; portable: points at the download page)
//! update_url=https://.../games/marcel/latest.json
//! page_url=https://.../games/marcel/
//! ```
//!
//! Everything it needs from the machine is already there: `curl.exe` (Windows 10 and later) for the two downloads and `certutil` for the checksum, so it has no
//! dependencies and builds with a bare `rustc`. A failed or slow check never gets in the way of playing: it is given four seconds, then the game starts.
//! Pure logic (the config, the JSON field, the version rule, the save folder) is unit-tested: `rustc --test distribution/play_launcher.rs && ./play_launcher`.
#![cfg_attr(windows, windows_subsystem = "windows")]

use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

/// Which game this is, from `play.cfg`.
#[derive(Debug, Clone, Default, PartialEq)]
struct Config {
    name: String,
    slug: String,
    version: u64,
    installed: bool,
    update_url: String,
    page_url: String,
}

fn parse_config(text: &str) -> Config {
    let mut c = Config::default();
    for line in text.lines() {
        let Some((key, value)) = line.split_once('=') else { continue };
        let value = value.trim().to_string();
        match key.trim() {
            "name" => c.name = value,
            "slug" => c.slug = value,
            "version" => c.version = value.parse().unwrap_or(0),
            "mode" => c.installed = value == "installed",
            "update_url" => c.update_url = value,
            "page_url" => c.page_url = value,
            _ => {}
        }
    }
    c
}

/// `Saved Games\<name>` under the user's profile: where Windows players expect a game's saves, and a folder an update or uninstall never touches.
fn save_dir(profile: &str, name: &str) -> PathBuf {
    let clean: String = name.chars().filter(|c| !"<>:\"/\\|?*".contains(*c)).collect();
    Path::new(profile).join("Saved Games").join(clean.trim())
}

/// The value of `"key"` in a flat JSON object: a string (with the common escapes undone) or a bare number. Enough for the one small file the site publishes.
fn json_value(json: &str, key: &str) -> Option<String> {
    let at = json.find(&format!("\"{key}\""))? + key.len() + 2;
    let rest = json[at..].trim_start().strip_prefix(':')?.trim_start();
    if let Some(body) = rest.strip_prefix('"') {
        let mut out = String::new();
        let mut chars = body.chars();
        while let Some(c) = chars.next() {
            match c {
                '"' => return Some(out),
                '\\' => match chars.next()? {
                    'n' => out.push('\n'),
                    't' => out.push('\t'),
                    'u' => {
                        let hex: String = chars.by_ref().take(4).collect();
                        out.push(u32::from_str_radix(&hex, 16).ok().and_then(char::from_u32).unwrap_or('?'));
                    }
                    other => out.push(other),
                },
                c => out.push(c),
            }
        }
        None
    } else {
        let end = rest.find(|c: char| !(c.is_ascii_alphanumeric() || c == '.' || c == '-')).unwrap_or(rest.len());
        Some(rest[..end].to_string()).filter(|s| !s.is_empty())
    }
}

/// Whether `latest` is worth offering: newer than what is installed, and not a version the player already said no to ("skip this version").
fn worth_offering(latest: u64, current: u64, skipped: Option<u64>) -> bool {
    latest > current && skipped.is_none_or(|s| latest > s)
}

/// The hash in `certutil -hashfile <file> SHA256` output (the second line, bytes separated by spaces on older Windows).
fn parse_certutil(output: &str) -> Option<String> {
    let line = output.lines().nth(1)?;
    let hash: String = line.chars().filter(|c| !c.is_whitespace()).collect::<String>().to_lowercase();
    (hash.len() == 64 && hash.chars().all(|c| c.is_ascii_hexdigit())).then_some(hash)
}

/// The installer's file name, from the URL, kept to characters that are safe in a path.
fn file_name_of(url: &str) -> String {
    let name = url.rsplit('/').next().unwrap_or("update.exe");
    let name: String = name.chars().filter(|c| c.is_ascii_alphanumeric() || "-_.".contains(*c)).collect();
    if name.ends_with(".exe") { name } else { "update-setup.exe".to_string() }
}

/// Command-line arguments the player added (a shortcut with `--players 2`), minus the launcher's own switch.
fn passed_through(args: impl Iterator<Item = String>) -> Vec<String> {
    args.filter(|a| a != "--no-update").collect()
}

fn launch(directory: &Path, save: &Path, extra: &[String]) -> Result<(), String> {
    let engine_name = fs::read_to_string(directory.join("engine.name")).map_err(|e| format!("cannot read engine.name: {e}"))?;
    let arguments = fs::read_to_string(directory.join("launch.args")).map_err(|e| format!("cannot read launch.args: {e}"))?;
    let engine = directory.join(engine_name.trim());
    if !engine.is_file() {
        return Err(format!("engine executable is missing: {}", engine.display()));
    }
    Command::new(engine)
        .current_dir(directory)
        .env("RE2_SAVE_DIR", save)
        .args(arguments.lines().filter(|line| !line.is_empty()))
        .args(extra)
        .spawn()
        .map_err(|e| format!("cannot start the game: {e}"))?;
    Ok(())
}

/// What the player chose when told about an update.
#[cfg_attr(not(windows), allow(dead_code))]
#[derive(Debug, PartialEq)]
enum Choice {
    Update,
    NotNow,
    Skip,
}

#[cfg(windows)]
mod os {
    use super::Choice;
    use std::os::windows::process::CommandExt;
    use std::process::Command;

    const CREATE_NO_WINDOW: u32 = 0x0800_0000;

    #[link(name = "user32")]
    extern "system" {
        fn MessageBoxW(hwnd: isize, text: *const u16, caption: *const u16, flags: u32) -> i32;
    }

    fn wide(s: &str) -> Vec<u16> {
        s.encode_utf16().chain(std::iter::once(0)).collect()
    }

    pub fn tell(title: &str, text: &str) {
        // MB_OK | MB_ICONINFORMATION
        unsafe { MessageBoxW(0, wide(text).as_ptr(), wide(title).as_ptr(), 0x40) };
    }

    pub fn offer(title: &str, text: &str) -> Choice {
        // MB_YESNOCANCEL | MB_ICONINFORMATION
        match unsafe { MessageBoxW(0, wide(text).as_ptr(), wide(title).as_ptr(), 0x23) } {
            6 => Choice::Update,
            2 => Choice::Skip,
            _ => Choice::NotNow,
        }
    }

    /// Runs a system tool with no console window; its standard output when it succeeded.
    pub fn run(program: &str, args: &[&str]) -> Option<String> {
        let root = std::env::var("SystemRoot").unwrap_or_else(|_| r"C:\Windows".into());
        let path = format!(r"{root}\System32\{program}");
        let out = Command::new(path).args(args).creation_flags(CREATE_NO_WINDOW).output().ok()?;
        out.status.success().then(|| String::from_utf8_lossy(&out.stdout).into_owned())
    }

    pub fn open(url: &str) {
        let _ = Command::new("cmd").args(["/C", "start", "", url]).creation_flags(CREATE_NO_WINDOW).spawn();
    }

    pub fn profile() -> String {
        std::env::var("USERPROFILE").unwrap_or_default()
    }
}

#[cfg(not(windows))]
mod os {
    use super::Choice;
    pub fn tell(_: &str, _: &str) {}
    pub fn offer(_: &str, _: &str) -> Choice {
        Choice::NotNow
    }
    pub fn run(_: &str, _: &[&str]) -> Option<String> {
        None
    }
    pub fn open(_: &str) {}
    pub fn profile() -> String {
        std::env::var("HOME").unwrap_or_default()
    }
}

/// Looks for a newer version; true when an update was started (the installer takes over and restarts the game, so this process should end).
fn offer_update(cfg: &Config, save: &Path) -> bool {
    if cfg.update_url.is_empty() {
        return false;
    }
    let Some(json) = os::run("curl.exe", &["-fsSL", "--max-time", "4", &cfg.update_url]) else { return false };
    let Some(latest) = json_value(&json, "version").and_then(|v| v.parse::<u64>().ok()) else { return false };
    let skipped_file = save.join("update-skipped.txt");
    let skipped = fs::read_to_string(&skipped_file).ok().and_then(|t| t.trim().parse::<u64>().ok());
    if !worth_offering(latest, cfg.version, skipped) {
        return false;
    }
    let news = json_value(&json, "notes").filter(|n| !n.is_empty()).map(|n| format!("\n\nWhat's new:\n{n}")).unwrap_or_default();
    let ask = format!(
        "Version {latest} of {} is available (you have version {}).{news}\n\nYes: update now (your saved games are kept)\nNo: not now\nCancel: skip this version",
        cfg.name, cfg.version
    );
    match os::offer(&cfg.name, &ask) {
        Choice::NotNow => false,
        Choice::Skip => {
            let _ = fs::create_dir_all(save);
            let _ = fs::write(skipped_file, latest.to_string());
            false
        }
        Choice::Update if !cfg.installed => {
            os::open(&cfg.page_url);
            true
        }
        Choice::Update => match install(&json) {
            Ok(()) => true,
            Err(e) => {
                os::tell(&cfg.name, &format!("The update could not be installed ({e}). The game will start as it is; you can download the new version from {}.", cfg.page_url));
                false
            }
        },
    }
}

/// Downloads the installer named in `json`, checks its SHA-256, and starts it silently; it replaces this game in place and starts it again.
fn install(json: &str) -> Result<(), String> {
    let url = json_value(json, "installer").ok_or("the update has no installer")?;
    let want = json_value(json, "sha256").ok_or("the update has no checksum")?.to_lowercase();
    let folder = std::env::temp_dir().join("RedEngineGames");
    fs::create_dir_all(&folder).map_err(|e| e.to_string())?;
    let file = folder.join(file_name_of(&url));
    let file_text = file.to_string_lossy().into_owned();
    os::run("curl.exe", &["-fsSL", "--max-time", "600", "-o", &file_text, &url]).ok_or("the download failed")?;
    let got = os::run("certutil.exe", &["-hashfile", &file_text, "SHA256"]).and_then(|o| parse_certutil(&o));
    if got.as_deref() != Some(want.as_str()) {
        let _ = fs::remove_file(&file);
        return Err("the download did not match its checksum".into());
    }
    Command::new(&file)
        .args(["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"])
        .spawn()
        .map_err(|e| format!("cannot start the installer: {e}"))?;
    Ok(())
}

fn run() -> Result<(), String> {
    let executable = std::env::current_exe().map_err(|e| e.to_string())?;
    let directory = executable.parent().ok_or("launcher has no parent directory")?;
    let cfg = fs::read_to_string(directory.join("play.cfg")).map(|t| parse_config(&t)).ok();
    let save = match &cfg {
        Some(c) if !c.name.is_empty() => save_dir(&os::profile(), &c.name),
        _ => directory.join("saves"),
    };
    let _ = fs::create_dir_all(&save);
    let args: Vec<String> = std::env::args().skip(1).collect();
    let skip_check = args.iter().any(|a| a == "--no-update") || std::env::var_os("RE2_NO_UPDATE").is_some();
    if let Some(c) = cfg.as_ref().filter(|_| !skip_check) {
        if offer_update(c, &save) {
            return Ok(());
        }
    }
    launch(directory, &save, &passed_through(args.into_iter()))
}

fn main() {
    if let Err(error) = run() {
        let directory = std::env::current_exe()
            .ok()
            .and_then(|path| path.parent().map(Path::to_path_buf))
            .unwrap_or_else(|| std::env::current_dir().unwrap_or_default());
        let _ = fs::write(directory.join("launcher-error.txt"), format!("{error}\n"));
        os::tell("Could not start the game", &format!("{error}\n\nThe details are in launcher-error.txt next to the game."));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_config_names_the_game_its_version_and_where_updates_come_from() {
        let c = parse_config("name=Marcel\nslug=marcel\nversion=3\nmode=installed\nupdate_url=https://x/y.json\npage_url=https://x/\nfuture=ignored\n");
        assert_eq!(c.name, "Marcel");
        assert_eq!(c.version, 3);
        assert!(c.installed);
        assert_eq!(c.update_url, "https://x/y.json");
        assert!(!parse_config("mode=portable").installed);
        assert_eq!(parse_config("version=oops").version, 0);
    }

    #[test]
    fn saves_go_to_saved_games_under_the_game_name_with_no_characters_windows_forbids() {
        assert_eq!(save_dir(r"C:\Users\kev", "Marcel"), Path::new(r"C:\Users\kev").join("Saved Games").join("Marcel"));
        assert_eq!(save_dir("/home/k", "Who: Me? <Now>").file_name().unwrap(), "Who Me Now");
    }

    #[test]
    fn json_fields_are_read_as_strings_with_escapes_or_as_bare_numbers() {
        let j = r#"{"version": 12, "installer":"https://h/a b/x-setup.exe","notes":"Line one\nLine \"two\" \u00e9","sha256":"ab"}"#;
        assert_eq!(json_value(j, "version").as_deref(), Some("12"));
        assert_eq!(json_value(j, "installer").as_deref(), Some("https://h/a b/x-setup.exe"));
        assert_eq!(json_value(j, "notes").as_deref(), Some("Line one\nLine \"two\" é"));
        assert_eq!(json_value(j, "missing"), None);
        assert_eq!(json_value(r#"{"version": }"#, "version"), None);
    }

    #[test]
    fn an_update_is_offered_only_when_it_is_newer_and_not_already_declined() {
        assert!(worth_offering(4, 3, None));
        assert!(!worth_offering(3, 3, None), "the same version");
        assert!(!worth_offering(2, 3, None), "an older one is never offered over a newer install");
        assert!(!worth_offering(4, 3, Some(4)), "skipped");
        assert!(worth_offering(5, 3, Some(4)), "a later release asks again");
    }

    #[test]
    fn the_checksum_is_the_second_line_of_certutil_output_however_it_is_spaced() {
        let h = "ab".repeat(32);
        assert_eq!(parse_certutil(&format!("SHA256 hash of x:\n{h}\nCertUtil: -hashfile command completed successfully.\n")), Some(h.clone()));
        let spaced = h.as_bytes().chunks(2).map(|c| std::str::from_utf8(c).unwrap()).collect::<Vec<_>>().join(" ");
        assert_eq!(parse_certutil(&format!("SHA256 hash of x:\n{spaced}\nok")), Some(h));
        assert_eq!(parse_certutil("nothing useful"), None);
    }

    #[test]
    fn the_installer_is_saved_under_a_safe_name_and_the_players_own_arguments_pass_through() {
        assert_eq!(file_name_of("https://h/releases/download/marcel-v3/marcel-3-setup.exe"), "marcel-3-setup.exe");
        assert_eq!(file_name_of("https://h/evil"), "update-setup.exe");
        assert!(!file_name_of(r"https://h/..\..\x%2f.exe").contains(['/', '\\', '%']), "no separators survive");
        let args = vec!["--players".to_string(), "2".to_string(), "--no-update".to_string()];
        assert_eq!(passed_through(args.into_iter()), vec!["--players".to_string(), "2".to_string()]);
    }
}
