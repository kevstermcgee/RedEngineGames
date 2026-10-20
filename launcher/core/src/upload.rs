//! A game dropped on the window: a `.zip`, a folder, or `.exe` / `.bat` / `.cmd` files, with a screenshot if one is dropped with it. The same
//! rules as `distribution/upload_game.py`, so a game added here and one uploaded from a computer are the same thing:
//!
//! * a dropped ZIP or folder whose files all sit in one top folder is played from inside that folder;
//! * what to start is the one `.exe`, `.bat` or `.cmd` in the top folder (uninstallers, setups and crash handlers do not count), or one folder
//!   down when the top holds none; with several, the player picks;
//! * the prepared folder gets `engine.name` (what to start, `/`-separated) and `launch.args`, the two files every game in the library has.
//!
//! [`stage`] copies everything into `uploads/staging/` under the library, so nothing the player dropped is changed or moved. The folder is then
//! either moved into the library (`Library::install_folder`) or zipped and published (`crate::publish`).

use std::fs::File;
use std::io::{self, Write};
use std::path::{Path, PathBuf};

use serde::Serialize;
use sha2::{Digest, Sha256};

use crate::{Error, Result};

const RUNNABLE: [&str; 3] = ["exe", "bat", "cmd"];
const PICTURES: [&str; 3] = ["png", "jpg", "jpeg"];
/// Executables a ready-made game often carries that are never the game itself (the start of the file name, lower case).
const NOT_THE_GAME: [&str; 10] = ["unins", "setup", "install", "vc_redist", "vcredist", "dxsetup", "unitycrashhandler", "crashpad_handler", "notification_helper", "uninstall"];

/// What was dropped, ready to be added or published.
#[derive(Debug, Clone, Serialize)]
pub struct Staged {
    /// The game's files (`uploads/staging/game`, or the one folder inside it).
    pub folder: PathBuf,
    /// A dropped screenshot, copied beside the game.
    pub thumb: Option<PathBuf>,
    /// A name to start from: the dropped file or folder's own.
    pub name: String,
    /// Everything that could start the game, relative and `/`-separated.
    pub candidates: Vec<String>,
    /// What starts it when that is clear (a single candidate, or a RedEngine build's own `engine.name`).
    pub entry: Option<String>,
    /// The game's size on disk, in bytes.
    pub size: u64,
    /// The game it was forked from, when it is a fork made in the window (`crate::fork`): its releases will name it.
    pub forked_from: Option<crate::fork::Parent>,
}

fn ext(p: &Path) -> String {
    p.extension().and_then(|e| e.to_str()).unwrap_or("").to_ascii_lowercase()
}

/// The game's id in addresses: lower-case letters and digits joined by single hyphens.
pub fn slugify(name: &str) -> String {
    let mut out = String::new();
    for c in name.chars().flat_map(char::to_lowercase) {
        if c.is_ascii_alphanumeric() {
            out.push(c);
        } else if !out.is_empty() && !out.ends_with('-') {
            out.push('-');
        }
    }
    out.trim_end_matches('-').to_string()
}

pub(crate) fn copy_tree(from: &Path, to: &Path) -> io::Result<()> {
    if from.is_dir() {
        std::fs::create_dir_all(to)?;
        for entry in std::fs::read_dir(from)? {
            let entry = entry?;
            copy_tree(&entry.path(), &to.join(entry.file_name()))?;
        }
        Ok(())
    } else {
        std::fs::copy(from, to).map(|_| ())
    }
}

fn size_of(dir: &Path) -> u64 {
    std::fs::read_dir(dir)
        .map(|rd| rd.flatten().map(|e| if e.path().is_dir() { size_of(&e.path()) } else { e.metadata().map(|m| m.len()).unwrap_or(0) }).sum())
        .unwrap_or(0)
}

/// Copy what was dropped into `work` (emptied first) and look at it.
pub fn stage(paths: &[PathBuf], work: &Path) -> Result<Staged> {
    let _ = std::fs::remove_dir_all(work);
    let game = work.join("game");
    std::fs::create_dir_all(&game)?;
    let (pictures, files): (Vec<&PathBuf>, Vec<&PathBuf>) = paths.iter().partition(|p| p.is_file() && PICTURES.contains(&ext(p).as_str()));
    let files = if files.is_empty() { pictures.clone() } else { files };
    if files.is_empty() {
        return Err(Error::Upload("Nothing was dropped.".into()));
    }
    for p in &files {
        let name = p.file_name().ok_or_else(|| Error::Upload(format!("{} cannot be read", p.display())))?;
        if p.is_file() && ext(p) == "zip" {
            crate::archive::unpack(p, &game).map_err(|e| Error::Upload(format!("{} could not be opened: {e}", p.display())))?;
        } else if p.exists() {
            copy_tree(p, &game.join(name))?;
        } else {
            return Err(Error::Upload(format!("{} is not there any more", p.display())));
        }
    }
    let thumb = match pictures.first() {
        Some(p) if files.len() < paths.len() => {
            let to = work.join(format!("thumb.{}", if ext(p) == "jpeg" { "jpg".into() } else { ext(p) }));
            std::fs::copy(p, &to)?;
            Some(to)
        }
        _ => None,
    };
    // A ZIP or folder holding a single folder: play from inside it (a dropped folder is itself one level, so look past it too).
    let mut folder = game.clone();
    if files.len() == 1 {
        loop {
            let items: Vec<PathBuf> = std::fs::read_dir(&folder)?.flatten().map(|e| e.path()).filter(|p| !matches!(p.file_name().and_then(|n| n.to_str()), Some("__MACOSX" | ".DS_Store"))).collect();
            match items.as_slice() {
                [only] if only.is_dir() => folder = only.clone(),
                _ => break,
            }
        }
    }
    let first = files[0];
    let name = first.file_stem().and_then(|s| s.to_str()).unwrap_or("My game").replace(['_', '-'], " ").trim().to_string();
    let candidates = candidates(&folder);
    let entry = match std::fs::read_to_string(folder.join("engine.name")) {
        Ok(own) => Some(own.trim().to_string()),
        Err(_) if candidates.len() == 1 => Some(candidates[0].clone()),
        Err(_) => None,
    };
    // A fork made in the window carries its record: it keeps its name and says where it came from.
    let (forked_from, name) = match crate::fork::read(&folder) {
        Some((parent, fork_name)) => (Some(parent), fork_name),
        None => (None, name),
    };
    Ok(Staged { size: size_of(&folder), folder, thumb, name, candidates, entry, forked_from })
}

/// The release record with the game's family: the game it was forked from and who publishes it (`maintainer`, a GitHub login).
pub fn with_family(mut meta: serde_json::Value, forked_from: Option<&crate::fork::Parent>, maintainer: &str) -> serde_json::Value {
    if let Some(p) = forked_from {
        meta["forked_from"] = serde_json::json!({"slug": p.slug, "version": p.version});
    }
    if !maintainer.is_empty() {
        meta["maintainer"] = maintainer.into();
    }
    meta
}

/// The files that could start the game: the top folder's, or one folder down when the top has none.
pub fn candidates(folder: &Path) -> Vec<String> {
    fn walk(dir: &Path, rel: &str, depth: usize, out: &mut Vec<String>) {
        let Ok(rd) = std::fs::read_dir(dir) else { return };
        let mut entries: Vec<_> = rd.flatten().collect();
        entries.sort_by_key(|e| e.file_name());
        for e in entries {
            let name = e.file_name().to_string_lossy().to_string();
            let path = format!("{rel}{name}");
            if e.path().is_dir() {
                if depth > 1 {
                    walk(&e.path(), &format!("{path}/"), depth - 1, out);
                }
            } else if RUNNABLE.contains(&ext(&e.path()).as_str()) && !NOT_THE_GAME.iter().any(|n| name.to_ascii_lowercase().starts_with(n)) {
                out.push(path);
            }
        }
    }
    for depth in [1, 2] {
        let mut out = vec![];
        walk(folder, "", depth, &mut out);
        if !out.is_empty() {
            return out;
        }
    }
    vec![]
}

/// Write `engine.name` and `launch.args` so the folder is a game the library can start; `entry` must be a runnable file inside it.
pub fn prepare(folder: &Path, entry: &str, args: &[String]) -> Result<()> {
    let entry = entry.trim().replace('\\', "/");
    if !RUNNABLE.contains(&ext(Path::new(&entry)).as_str()) {
        return Err(Error::Upload("Pick an .exe, .bat or .cmd file to start the game.".into()));
    }
    std::fs::write(folder.join("engine.name"), format!("{entry}\n"))?;
    if !args.is_empty() || !folder.join("launch.args").is_file() {
        std::fs::write(folder.join("launch.args"), args.iter().map(|a| format!("{a}\n")).collect::<String>())?;
    }
    crate::archive::check_game(folder).map(|_| ()).map_err(|_| Error::Upload(format!("`{entry}` is not a file inside the game.")))
}

/// Zip the folder into `out`; returns its size and SHA-256.
pub fn zip_folder(folder: &Path, out: &Path) -> Result<(u64, String)> {
    fn add(z: &mut zip::ZipWriter<File>, dir: &Path, rel: &str) -> Result<()> {
        let mut entries: Vec<_> = std::fs::read_dir(dir)?.flatten().collect();
        entries.sort_by_key(|e| e.file_name());
        let options = zip::write::SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated).large_file(true);
        for e in entries {
            let name = format!("{rel}{}", e.file_name().to_string_lossy());
            if e.path().is_dir() {
                add(z, &e.path(), &format!("{name}/"))?;
            } else {
                z.start_file(name, options).map_err(|e| Error::Archive(e.to_string()))?;
                io::copy(&mut File::open(e.path())?, z)?;
            }
        }
        Ok(())
    }
    if let Some(dir) = out.parent() {
        std::fs::create_dir_all(dir)?;
    }
    let mut z = zip::ZipWriter::new(File::create(out)?);
    add(&mut z, folder, "")?;
    z.finish().map_err(|e| Error::Archive(e.to_string()))?.flush()?;
    let mut hasher = Sha256::new();
    let size = io::copy(&mut File::open(out)?, &mut hasher)?;
    Ok((size, format!("{:x}", hasher.finalize())))
}

/// What the player filled in about a dropped game.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct Details {
    pub name: String,
    pub entry: String,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub presentation: String,
    #[serde(default)]
    pub author: String,
    #[serde(default)]
    pub notes: String,
}

impl Details {
    /// The details with the defaults the site uses, or why they cannot be used.
    pub fn checked(mut self) -> Result<Details> {
        self.name = self.name.split_whitespace().collect::<Vec<_>>().join(" ");
        if slugify(&self.name).is_empty() {
            return Err(Error::Upload("Give the game a name (letters or digits).".into()));
        }
        self.description = self.description.split_whitespace().collect::<Vec<_>>().join(" ");
        if !["2d", "3d", "hybrid"].contains(&self.presentation.as_str()) {
            self.presentation = "3d".into();
        }
        if !["ai", "human"].contains(&self.author.as_str()) {
            self.author = "human".into();
        }
        Ok(self)
    }
}

/// The `redengine-release` record of an uploaded version: the fields `distribution/upload_game.py` writes, which the site reads.
pub fn record(d: &Details, slug: &str, version: u64, released: &str, zip: (&str, u64, &str), thumb_url: Option<String>) -> serde_json::Value {
    let notes: Vec<String> = d.notes.lines().map(str::trim).filter(|l| !l.is_empty()).map(String::from).collect();
    let mut meta = serde_json::json!({
        "kind": "upload", "slug": slug, "name": d.name, "version": version, "released": released,
        "description": if d.description.is_empty() { format!("{}, a Windows game.", d.name) } else { d.description.clone() },
        "presentation": d.presentation, "author": d.author, "online": "", "entry": d.entry.trim().replace('\\', "/"),
        "notes": if notes.is_empty() { vec![if version == 1 { "First release.".to_string() } else { "A new build.".to_string() }] } else { notes },
        "zip": {"name": zip.0, "size": zip.1, "sha256": zip.2},
        "source": "app",
    });
    if let Some(url) = thumb_url {
        meta["thumb_url"] = url.into();
    }
    meta
}

/// The release notes: what it is, what changed, and the record on its last line (as `upload_game.release_body`).
pub fn release_body(meta: &serde_json::Value) -> String {
    let s = |k: &str| meta[k].as_str().unwrap_or("").to_string();
    let entry = s("entry");
    let mut lines = vec![format!("**{}**, version {}", s("name"), meta["version"]), String::new(), s("description"), String::new()];
    if let Some(notes) = meta["notes"].as_array().filter(|n| !n.is_empty()) {
        lines.push("What changed:".into());
        lines.extend(notes.iter().map(|n| format!("- {}", n.as_str().unwrap_or(""))));
        lines.push(String::new());
    }
    lines.push(format!("A ready-made Windows game, uploaded as it is (it starts `{entry}`). Get it in the RedEngine Games app, which keeps it up to date,"));
    lines.push(format!("or unzip `{}` anywhere and run `{}`.", meta["zip"]["name"].as_str().unwrap_or(""), entry.rsplit('/').next().unwrap_or("")));
    lines.push(String::new());
    lines.push(format!("<!-- redengine-release {meta} -->"));
    lines.push(String::new());
    lines.join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn zip_of(path: &Path, files: &[(&str, &[u8])]) {
        let mut z = zip::ZipWriter::new(File::create(path).unwrap());
        for (name, data) in files {
            z.start_file(*name, zip::write::SimpleFileOptions::default()).unwrap();
            z.write_all(data).unwrap();
        }
        z.finish().unwrap();
    }

    #[test]
    fn a_dropped_zip_of_one_folder_is_played_from_inside_and_its_one_exe_found() {
        let dir = tempfile::tempdir().unwrap();
        let zip = dir.path().join("Star_Miner.zip");
        zip_of(&zip, &[("Star Miner/StarMiner.exe", b"MZ"), ("Star Miner/unins000.exe", b"MZ"), ("Star Miner/data/a.pak", b"xyz")]);
        let s = stage(std::slice::from_ref(&zip), &dir.path().join("work")).unwrap();
        assert_eq!(s.name, "Star Miner");
        assert_eq!(s.candidates, ["StarMiner.exe"]);
        assert_eq!(s.entry.as_deref(), Some("StarMiner.exe"));
        assert!(s.folder.join("data/a.pak").is_file());
        assert!(zip.is_file(), "the dropped file is left alone");
    }

    #[test]
    fn dropped_files_go_together_and_a_screenshot_is_kept_apart() {
        let dir = tempfile::tempdir().unwrap();
        for (n, d) in [("quest.bat", "@echo off"), ("story.txt", "once"), ("shot.PNG", "png")] {
            std::fs::write(dir.path().join(n), d).unwrap();
        }
        let paths: Vec<PathBuf> = ["quest.bat", "story.txt", "shot.PNG"].iter().map(|n| dir.path().join(n)).collect();
        let s = stage(&paths, &dir.path().join("work")).unwrap();
        assert_eq!(s.candidates, ["quest.bat"]);
        assert!(s.folder.join("story.txt").is_file() && !s.folder.join("shot.PNG").exists());
        assert_eq!(s.thumb.as_ref().unwrap().file_name().unwrap(), "thumb.png");
    }

    #[test]
    fn several_candidates_are_offered_and_one_folder_down_counts() {
        let dir = tempfile::tempdir().unwrap();
        let zip = dir.path().join("g.zip");
        zip_of(&zip, &[("Game.exe", b"MZ"), ("Editor.exe", b"MZ")]);
        let s = stage(&[zip], &dir.path().join("work")).unwrap();
        assert_eq!(s.candidates, ["Editor.exe", "Game.exe"]);
        assert_eq!(s.entry, None);
        let zip = dir.path().join("h.zip");
        zip_of(&zip, &[("bin/Game.exe", b"MZ"), ("readme.txt", b"r")]);
        assert_eq!(stage(&[zip], &dir.path().join("work")).unwrap().candidates, ["bin/Game.exe"]);
    }

    #[test]
    fn prepared_folders_start_and_zip_with_their_checksum() {
        let dir = tempfile::tempdir().unwrap();
        let zip = dir.path().join("g.zip");
        zip_of(&zip, &[("bin/Game.exe", b"MZ"), ("data/x", b"x")]);
        let s = stage(&[zip], &dir.path().join("work")).unwrap();
        assert!(prepare(&s.folder, "readme.txt", &[]).is_err());
        assert!(prepare(&s.folder, "bin/Missing.exe", &[]).is_err());
        prepare(&s.folder, "bin\\Game.exe", &["--fast".into()]).unwrap();
        assert_eq!(std::fs::read_to_string(s.folder.join("engine.name")).unwrap(), "bin/Game.exe\n");
        let out = dir.path().join("out/g-1.zip");
        let (size, sha) = zip_folder(&s.folder, &out).unwrap();
        assert_eq!(size, std::fs::metadata(&out).unwrap().len());
        assert_eq!(sha.len(), 64);
        let back = dir.path().join("back");
        crate::archive::extract(&out, &back).unwrap();
        assert_eq!(std::fs::read_to_string(back.join("launch.args")).unwrap(), "--fast\n");
    }

    #[test]
    fn the_release_record_is_the_one_the_site_reads() {
        let d = Details { name: "  Text   Quest ".into(), entry: "quest.bat".into(), description: String::new(), presentation: "2d".into(), author: "x".into(), notes: "\n".into() }.checked().unwrap();
        assert_eq!((d.name.as_str(), d.author.as_str()), ("Text Quest", "human"));
        let meta = record(&d, &slugify(&d.name), 1, "2026-10-19", ("text-quest-1-windows-x64.zip", 10, "ab"), None);
        let body = release_body(&meta);
        let line = body.lines().find(|l| l.starts_with("<!-- redengine-release ")).unwrap();
        let back: serde_json::Value = serde_json::from_str(line.trim_start_matches("<!-- redengine-release ").trim_end_matches(" -->")).unwrap();
        assert_eq!(back["kind"], "upload");
        assert_eq!(back["slug"], "text-quest");
        assert_eq!(back["notes"][0], "First release.");
        assert_eq!(back["description"], "Text Quest, a Windows game.");
        assert!(body.contains("run `quest.bat`"));
        assert!(Details { name: "!!".into(), entry: "a.exe".into(), description: String::new(), presentation: String::new(), author: String::new(), notes: String::new() }.checked().is_err());
    }

    #[test]
    fn a_fork_made_in_the_window_comes_back_with_its_name_and_parent_in_its_record() {
        let dir = tempfile::tempdir().unwrap();
        let installed = dir.path().join("games/snake/v3");
        std::fs::create_dir_all(&installed).unwrap();
        std::fs::write(installed.join("RedEngine2D.exe"), "MZ").unwrap();
        std::fs::write(installed.join("engine.name"), "RedEngine2D.exe\n").unwrap();
        let parent = crate::fork::Parent { slug: "snake".into(), version: 3 };
        let fork = crate::fork::make(dir.path(), &installed, &parent, "Snake", "Neon Snake").unwrap();
        let s = stage(std::slice::from_ref(&fork), &dir.path().join("work")).unwrap();
        assert_eq!((s.name.as_str(), s.forked_from.as_ref(), s.entry.as_deref()), ("Neon Snake", Some(&parent), Some("RedEngine2D.exe")));
        let d = Details { name: s.name.clone(), entry: "RedEngine2D.exe".into(), description: String::new(), presentation: "2d".into(), author: "human".into(), notes: String::new() };
        let meta = with_family(record(&d, "neon-snake", 1, "2026-10-21", ("z", 1, "ab"), None), s.forked_from.as_ref(), "meastwood13");
        assert_eq!(meta["forked_from"], serde_json::json!({"slug": "snake", "version": 3}));
        assert_eq!(meta["maintainer"], "meastwood13");
        let plain = with_family(record(&d, "x", 1, "d", ("z", 1, "ab"), None), None, "");
        assert!(plain.get("forked_from").is_none() && plain.get("maintainer").is_none(), "an original's record is unchanged");
    }

    #[test]
    fn slugs_come_from_names() {
        assert_eq!(slugify("Star Miner: Deluxe!"), "star-miner-deluxe");
        assert_eq!(slugify("--"), "");
    }
}
