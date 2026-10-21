//! A game dropped on the window: a `.zip`, a folder, or `.exe` / `.bat` / `.cmd` files, with a screenshot if one is dropped with it. The same
//! rules as `distribution/upload_game.py`, so a game added here and one uploaded from a computer are the same thing:
//!
//! * a dropped ZIP or folder whose files all sit in one top folder is played from inside that folder;
//! * what to start is the one `.exe`, `.bat` or `.cmd` in the top folder (uninstallers, setups and crash handlers do not count), or one folder
//!   down when the top holds none; with several, the player picks;
//! * the prepared folder gets `engine.name` (what to start, `/`-separated) and `launch.args`, the two files every game in the library has;
//! * a link (a symbolic link, a junction) in a dropped folder or ZIP is left behind, and nothing nests deeper than a ZIP member may
//!   (`crate::archive::MAX_DEPTH`): what a hostile game points at, or buries a stack in, is not part of it.
//!
//! [`stage`] copies everything into `uploads/staging/` under the library, so nothing the player dropped is changed or moved. The folder is then
//! either moved into the library (`Library::install_folder`) or zipped and published (`crate::publish`).
//!
//! A game can say what it is (`crate::meta`, the game card): [`stage`] reads that, so the window starts with the form filled in, and
//! [`write_card`] puts the card as the player left it into the folder before it is zipped or installed, so it travels with the game.

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
    /// The screenshot: a dropped one, copied beside the game, else the one the game's card names inside it.
    pub thumb: Option<PathBuf>,
    /// A name to start from: the game's own (its card, or the record of a fork), else the dropped file or folder's.
    pub name: String,
    /// Everything that could start the game, relative and `/`-separated.
    pub candidates: Vec<String>,
    /// What starts it when that is clear (a RedEngine build's own `engine.name`, else the card's, else a single candidate).
    pub entry: Option<String>,
    /// What to start it with, when the game's card says (for the card's own program only: see [`Staged::args_for`]).
    pub args: Vec<String>,
    /// The program `args` were written for: the card's own `entry`, else (a card that names none) what the game starts with.
    pub args_entry: Option<String>,
    /// What the game says about itself, and where each field was found.
    pub found: crate::meta::Found,
    /// The game's size on disk, in bytes.
    pub size: u64,
    /// The game it was forked from, when it is a fork made in the window (`crate::fork`): its releases will name it.
    pub forked_from: Option<crate::fork::Parent>,
}

/// What follows the last dot of the file's name, in lower case. A name that is only an extension (`.bat`) has it, as the command-line tool reads it.
pub(crate) fn ext(p: &Path) -> String {
    p.file_name().and_then(|n| n.to_str()).and_then(|n| n.rsplit_once('.')).map_or(String::new(), |(_, e)| e.to_ascii_lowercase())
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

/// Copy `from`, a file or a folder, to `to`. `from` is what the player dropped, so a link there is followed; inside a folder a link (a symbolic link or, on
/// Windows, a junction) is left behind, or the game would take whatever it points at, from outside itself, and publish it. A folder nested deeper than a
/// ZIP member may be (`archive::MAX_DEPTH`) is refused.
pub(crate) fn copy_tree(from: &Path, to: &Path) -> io::Result<()> {
    fn walk(from: &Path, to: &Path, depth: usize) -> io::Result<()> {
        if depth > crate::archive::MAX_DEPTH {
            return Err(io::Error::new(io::ErrorKind::InvalidData, format!("{} is nested more than {} folders deep", from.display(), crate::archive::MAX_DEPTH)));
        }
        std::fs::create_dir_all(to)?;
        for entry in std::fs::read_dir(from)? {
            let entry = entry?;
            let kind = entry.file_type()?;
            if kind.is_dir() {
                walk(&entry.path(), &to.join(entry.file_name()), depth + 1)?;
            } else if kind.is_file() {
                std::fs::copy(entry.path(), to.join(entry.file_name()))?;
            }
        }
        Ok(())
    }
    if from.is_dir() {
        walk(from, to, 1)
    } else {
        std::fs::copy(from, to).map(|_| ())
    }
}

/// The size of the files in `dir` (links and anything deeper than a game can be are not counted).
fn size_of(dir: &Path, depth: usize) -> u64 {
    let Ok(rd) = std::fs::read_dir(dir).map(|rd| rd.flatten()) else { return 0 };
    rd.map(|e| match e.file_type() {
        Ok(t) if t.is_dir() && depth <= crate::archive::MAX_DEPTH + 2 => size_of(&e.path(), depth + 1),
        Ok(t) if t.is_file() => e.metadata().map_or(0, |m| m.len()),
        _ => 0,
    })
    .sum()
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
    let mut zip_card = None;
    for p in &files {
        let name = p.file_name().ok_or_else(|| Error::Upload(format!("{} cannot be read", p.display())))?;
        if p.is_file() && ext(p) == "zip" {
            // The card in the ZIP's comment: unpacking loses it, so read it first.
            zip_card = zip_card.or_else(|| crate::meta::zip_comment(p));
            crate::archive::unpack(p, &game).map_err(|e| Error::Upload(format!("{} could not be opened: {e}", p.display())))?;
        } else if p.exists() {
            copy_tree(p, &game.join(name))?;
        } else {
            return Err(Error::Upload(format!("{} is not there any more", p.display())));
        }
    }
    let dropped_thumb = match pictures.first() {
        Some(p) if files.len() < paths.len() => {
            let to = work.join(format!("thumb.{}", if ext(p) == "jpeg" { "jpg".into() } else { ext(p) }));
            std::fs::copy(p, &to)?;
            Some(to)
        }
        _ => None,
    };
    // A ZIP or folder holding a single folder: play from inside it (a dropped folder is itself one level, so look past it too).
    let folder = if files.len() == 1 { top_folder(&game)? } else { game.clone() };
    let first = files[0];
    let stem = first.file_stem().and_then(|s| s.to_str()).unwrap_or("My game").replace(['_', '-'], " ").trim().to_string();
    let mut candidates = candidates(&folder);
    // A program dropped by itself is the game whatever it is called (`Install_And_Play.bat`): only among other files do names like Setup say it is not.
    if candidates.is_empty() && files.len() == 1 && first.is_file() && RUNNABLE.contains(&ext(first).as_str()) {
        candidates.extend(first.file_name().and_then(|n| n.to_str()).map(String::from));
    }
    // A fork made in the window carries its record: it says where the game came from (that wins over the card), and what it was called.
    let fork = crate::fork::read(&folder);
    let found = crate::meta::read_folder(&folder, zip_card, &candidates, fork.is_some());
    let entry = match crate::meta::engine_name(&folder) {
        Some(own) => Some(own),
        None => found.card.entry.clone().or_else(|| (candidates.len() == 1).then(|| candidates[0].clone())),
    };
    // The card's name, unless it is no letters or digits (`星の旅` makes no id, so it cannot be the game's) or is the parent's (a fork made before the
    // card existed has its parent's card): then the fork's own name, else the file's.
    let usable = |n: &&String| !slugify(n).is_empty();
    let parents = |n: &&String| fork.as_ref().is_some_and(|(p, _)| slugify(n) == p.slug);
    let name = found.card.name.as_ref().filter(usable).filter(|n| !parents(n)).or(fork.as_ref().map(|(_, n)| n).filter(usable)).cloned().unwrap_or(stem);
    // A game cannot be a fork of itself: a card that says so (its name is its parent's) is not telling a lineage.
    let forked_from = match fork {
        Some((parent, _)) => Some(parent),
        None => found.card.forked_from.clone().filter(|p| p.slug != slugify(&name)),
    };
    // A dropped screenshot wins over the one the card names.
    let thumb = dropped_thumb.or_else(|| found.card.thumb.as_ref().map(|t| folder.join(t)));
    // The card's arguments are for its own `entry`, never for another program (`engine.name`'s, or one the player picks); a card that names no program
    // speaks for the one the game starts with.
    let args = found.card.args.clone().unwrap_or_default();
    let args_entry = found.card.entry.clone().or_else(|| entry.clone());
    Ok(Staged { size: size_of(&folder, 1), folder, thumb, name, candidates, entry, args, args_entry, found, forked_from })
}

/// A ZIP or folder holding a single folder (and `__MACOSX` or `.DS_Store` beside it) is played from inside that folder, however deep.
pub(crate) fn top_folder(game: &Path) -> io::Result<PathBuf> {
    let mut folder = game.to_path_buf();
    loop {
        let items: Vec<_> = std::fs::read_dir(&folder)?.flatten().filter(|e| !matches!(e.file_name().to_str(), Some("__MACOSX" | ".DS_Store"))).collect();
        match items.as_slice() {
            [only] if only.file_type().is_ok_and(|t| t.is_dir()) => folder = only.path(),
            _ => return Ok(folder),
        }
    }
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
            // A link is neither a folder to look into nor a file that starts the game (a dropped copy has none; a folder read in place may).
            let kind = e.file_type();
            if kind.as_ref().is_ok_and(|t| t.is_dir()) {
                if depth > 1 {
                    walk(&e.path(), &format!("{path}/"), depth - 1, out);
                }
            } else if kind.is_ok_and(|t| t.is_file()) && RUNNABLE.contains(&ext(&e.path()).as_str()) && !NOT_THE_GAME.iter().any(|n| name.to_ascii_lowercase().starts_with(n)) {
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

/// Whether `a` names the program `b` does (`\` or `/`, spaces around).
fn same_program(a: Option<&str>, b: &str) -> bool {
    a.is_some_and(|a| a.trim().replace('\\', "/") == b.trim().replace('\\', "/"))
}

impl Staged {
    /// Whether `entry` is the program the game started with when it was dropped (its `engine.name`, its card's `entry`, or its one candidate).
    fn starts_with(&self, entry: &str) -> bool {
        same_program(self.entry.as_deref(), entry)
    }

    /// What `entry` starts with, as the game's card says: the card's arguments when it is the program they were written for (the card's own `entry`,
    /// else the one the game started with), none for another one, whether `engine.name` or the player chose it.
    pub fn args_for(&self, entry: &str) -> Vec<String> {
        if same_program(self.args_entry.as_deref(), entry) { self.args.clone() } else { vec![] }
    }
}

/// Put the game's card into its folder as the player left it in the form: `redengine-game.json`, and a dropped screenshot beside it as
/// `redengine-game-thumb.png` or `.jpg`, which the card names (a picture over 5 MB goes to the site, not into the game: a reader ignores a card's
/// picture that big). Call it before the folder is zipped or installed: the card then travels with the game (the ZIP's comment is made from it by
/// [`zip_folder`]). The game's own files are never touched, and `notes` are never kept.
pub fn write_card(staged: &Staged, d: &Details) -> Result<()> {
    let thumb = match &staged.thumb {
        // The game's own screenshot, already named by its card.
        Some(t) => match t.strip_prefix(&staged.folder) {
            Ok(rel) => Some(rel.to_string_lossy().replace('\\', "/")),
            Err(_) => {
                let ext = ext(t);
                let (png, jpg) = (staged.folder.join(format!("{}.png", crate::meta::THUMB)), staged.folder.join(format!("{}.jpg", crate::meta::THUMB)));
                let (kind, keep, other) = if ext == "png" { ("png", &png, &jpg) } else { ("jpg", &jpg, &png) };
                let _ = std::fs::remove_file(other);
                if std::fs::metadata(t)?.len() > crate::meta::MAX_THUMB {
                    let _ = std::fs::remove_file(keep);
                    None
                } else {
                    std::fs::copy(t, keep)?;
                    Some(format!("{}.{kind}", crate::meta::THUMB))
                }
            }
        },
        None => None,
    };
    let some = |s: &str| (!s.is_empty()).then(|| s.to_string());
    // The card says what the game starts with: its own arguments, else (a fork, a RedEngine build) the ones in its `launch.args`, which stays as it is.
    let args = Some(staged.args_for(&d.entry)).filter(|a| !a.is_empty()).unwrap_or_else(|| if staged.starts_with(&d.entry) { crate::meta::launch_args(&staged.folder) } else { vec![] });
    let card = crate::meta::Card {
        name: Some(d.name.clone()),
        description: some(&d.description),
        presentation: some(&d.presentation),
        author: some(&d.author),
        online: some(&d.online),
        entry: Some(d.entry.trim().replace('\\', "/")),
        args: (!args.is_empty()).then_some(args),
        thumb,
        forked_from: staged.forked_from.clone(),
        notes: None,
    };
    crate::meta::write_card_file(&staged.folder, &card)
}

/// Zip the folder into `out`; returns its size and SHA-256.
pub fn zip_folder(folder: &Path, out: &Path) -> Result<(u64, String)> {
    fn add(z: &mut zip::ZipWriter<File>, dir: &Path, rel: &str, depth: usize) -> Result<()> {
        if depth > crate::archive::MAX_DEPTH + 2 {
            return Err(Error::Archive(format!("{} is nested too deep", dir.display())));
        }
        let mut entries: Vec<_> = std::fs::read_dir(dir)?.flatten().collect();
        entries.sort_by_key(|e| e.file_name());
        let options = zip::write::SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated).large_file(true);
        for e in entries {
            let name = format!("{rel}{}", e.file_name().to_string_lossy());
            let kind = e.file_type()?;
            if kind.is_dir() {
                add(z, &e.path(), &format!("{name}/"), depth + 1)?;
            } else if kind.is_file() {
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
    // A game with a card carries it in the archive's comment too, where it can be read without unpacking.
    if let Some(card) = crate::meta::read_card_file(folder) {
        z.set_comment(crate::meta::comment(&card));
    }
    add(&mut z, folder, "", 1)?;
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
    /// A note when the game has online multiplayer (never an address or a join key).
    #[serde(default)]
    pub online: String,
    #[serde(default)]
    pub notes: String,
}

impl Details {
    /// The details with the defaults the site uses, or why they cannot be used.
    pub fn checked(mut self) -> Result<Details> {
        // Cleaned and cut as the card keeps them, so the release record and the card in the game say the same.
        self.name = crate::meta::clean(&self.name, 60);
        if slugify(&self.name).is_empty() {
            return Err(Error::Upload("Give the game a name (letters or digits).".into()));
        }
        self.description = crate::meta::clean(&self.description, 400);
        self.online = crate::meta::clean(&self.online, 200);
        if crate::meta::looks_like_address(&self.online) {
            return Err(Error::Upload("The online note looks like an address or a join key. Say how it is played instead (for example \"Up to four players on one LAN\"): addresses and keys are never published.".into()));
        }
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
        "presentation": d.presentation, "author": d.author, "online": d.online, "entry": d.entry.trim().replace('\\', "/"),
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
        let d = Details { name: "  Text   Quest ".into(), entry: "quest.bat".into(), description: String::new(), presentation: "2d".into(), author: "x".into(), online: String::new(), notes: "\n".into() }.checked().unwrap();
        assert_eq!((d.name.as_str(), d.author.as_str()), ("Text Quest", "human"));
        assert_eq!(Details { online: format!(" Co-op\u{7}  for {} ", "two ".repeat(80)), ..details("x", "a.exe") }.checked().unwrap().online.chars().count(), 200, "the note is cleaned and cut as the card keeps it");
        let meta = record(&d, &slugify(&d.name), 1, "2026-10-19", ("text-quest-1-windows-x64.zip", 10, "ab"), None);
        let body = release_body(&meta);
        let line = body.lines().find(|l| l.starts_with("<!-- redengine-release ")).unwrap();
        let back: serde_json::Value = serde_json::from_str(line.trim_start_matches("<!-- redengine-release ").trim_end_matches(" -->")).unwrap();
        assert_eq!(back["kind"], "upload");
        assert_eq!(back["slug"], "text-quest");
        assert_eq!(back["notes"][0], "First release.");
        assert_eq!(back["description"], "Text Quest, a Windows game.");
        assert!(body.contains("run `quest.bat`"));
        assert!(Details { name: "!!".into(), entry: "a.exe".into(), description: String::new(), presentation: String::new(), author: String::new(), online: String::new(), notes: String::new() }.checked().is_err());
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
        let d = Details { name: s.name.clone(), entry: "RedEngine2D.exe".into(), description: String::new(), presentation: "2d".into(), author: "human".into(), online: String::new(), notes: String::new() };
        let meta = with_family(record(&d, "neon-snake", 1, "2026-10-21", ("z", 1, "ab"), None), s.forked_from.as_ref(), "meastwood13");
        assert_eq!(meta["forked_from"], serde_json::json!({"slug": "snake", "version": 3}));
        assert_eq!(meta["maintainer"], "meastwood13");
        let plain = with_family(record(&d, "x", 1, "d", ("z", 1, "ab"), None), None, "");
        assert!(plain.get("forked_from").is_none() && plain.get("maintainer").is_none(), "an original's record is unchanged");
    }

    fn zip_with_comment(path: &Path, files: &[(&str, &[u8])], comment: &str) {
        let mut z = zip::ZipWriter::new(File::create(path).unwrap());
        for (name, data) in files {
            z.start_file(*name, zip::write::SimpleFileOptions::default()).unwrap();
            z.write_all(data).unwrap();
        }
        z.set_comment(comment);
        z.finish().unwrap();
    }

    fn details(name: &str, entry: &str) -> Details {
        Details { name: name.into(), entry: entry.into(), description: String::new(), presentation: "3d".into(), author: "human".into(), online: String::new(), notes: String::new() }
    }

    const CARD: &str = r#"{"schema": 1, "name": "Star Miner", "description": "Mine asteroids, dodge pirates.", "presentation": "3d", "author": "ai", "online": "Co-op for two.",
        "entry": "bin/StarMiner.exe", "args": ["--fast", "--windowed"], "thumb": "shots/one.png", "notes": ["First release."]}"#;

    #[test]
    fn a_game_that_says_what_it_is_arrives_with_the_form_filled_in() {
        let dir = tempfile::tempdir().unwrap();
        let zip = dir.path().join("Whatever_It_Is_Called.zip");
        zip_of(&zip, &[("Game/bin/StarMiner.exe", b"MZ"), ("Game/bin/Editor.exe", b"MZ"), ("Game/shots/one.png", b"png"), ("Game/redengine-game.json", CARD.as_bytes())]);
        let s = stage(&[zip], &dir.path().join("work")).unwrap();
        assert_eq!(s.name, "Star Miner", "the card's name, not the file's");
        assert_eq!(s.candidates, ["bin/Editor.exe", "bin/StarMiner.exe"]);
        assert_eq!(s.entry.as_deref(), Some("bin/StarMiner.exe"), "two candidates, and the card says which");
        assert_eq!(s.args, ["--fast", "--windowed"]);
        assert_eq!(s.thumb, Some(s.folder.join("shots/one.png")));
        assert_eq!(s.found.card.description.as_deref(), Some("Mine asteroids, dodge pirates."));
        assert_eq!(s.found.card.notes, Some(vec!["First release.".to_string()]));
        assert!(s.found.from.values().all(|f| *f == crate::meta::Source::Card));
    }

    #[test]
    fn the_zip_comment_is_read_before_unpacking_loses_it() {
        let dir = tempfile::tempdir().unwrap();
        let zip = dir.path().join("g.zip");
        zip_with_comment(&zip, &[("quest.bat", b"@echo off")], r#"redengine-game {"schema":1,"name":"Text Quest","presentation":"2d","entry":"quest.bat"}"#);
        let s = stage(&[zip], &dir.path().join("work")).unwrap();
        assert_eq!((s.name.as_str(), s.entry.as_deref()), ("Text Quest", Some("quest.bat")));
        assert_eq!(s.found.card.presentation.as_deref(), Some("2d"));
        assert!(s.found.from.values().all(|f| *f == crate::meta::Source::Zip));
        // A card in the dropped script itself, and a game that ships a screenshot of its own and none dropped.
        let bat = dir.path().join("Quest.bat");
        std::fs::write(&bat, "@echo off\r\nREM redengine-game\r\nREM name: Quest From Its Header\r\nREM thumb: shot.png\r\n").unwrap();
        let shot = dir.path().join("shot.png");
        std::fs::write(&shot, "png").unwrap();
        let s = stage(&[bat.clone(), shot.clone()], &dir.path().join("work")).unwrap();
        assert_eq!(s.name, "Quest From Its Header");
        assert_eq!(s.thumb.as_ref().unwrap().file_name().unwrap(), "thumb.png", "a dropped screenshot wins over the card's");
        assert_eq!(s.found.card.thumb, None, "and the card's names a file that is not in the game");
        let s = stage(&[bat], &dir.path().join("work")).unwrap();
        assert_eq!((s.thumb, s.found.from.get("name").copied()), (None, Some(crate::meta::Source::Bat)));
    }

    #[test]
    fn a_game_with_no_card_at_all_is_dropped_as_it_always_was() {
        let dir = tempfile::tempdir().unwrap();
        let zip = dir.path().join("Star_Miner.zip");
        zip_of(&zip, &[("Star Miner/StarMiner.exe", b"MZ not a real program"), ("Star Miner/data/a.pak", b"xyz")]);
        let s = stage(&[zip], &dir.path().join("work")).unwrap();
        assert_eq!((s.name.as_str(), s.entry.as_deref(), s.thumb.clone(), s.args.is_empty()), ("Star Miner", Some("StarMiner.exe"), None, true));
        assert_eq!(s.found, crate::meta::Found::default());
        let d = details("Star Miner", "StarMiner.exe").checked().unwrap();
        let meta = record(&d, "star-miner", 1, "d", ("z", 1, "ab"), None);
        assert_eq!((meta["online"].as_str(), meta["description"].as_str()), (Some(""), Some("Star Miner, a Windows game.")));
        prepare(&s.folder, "StarMiner.exe", &s.args).unwrap();
        assert_eq!(std::fs::read_to_string(s.folder.join("launch.args")).unwrap(), "");
        let out = dir.path().join("out.zip");
        zip_folder(&s.folder, &out).unwrap();
        assert_eq!(zip::ZipArchive::new(File::open(&out).unwrap()).unwrap().comment(), b"", "no card, no comment");
    }

    #[test]
    fn engine_name_comes_before_the_cards_entry_which_comes_before_the_one_candidate() {
        let dir = tempfile::tempdir().unwrap();
        let zip = dir.path().join("g.zip");
        zip_of(&zip, &[("Game.exe", b"MZ"), ("redengine-game.json", br#"{"entry": "tools/Editor.exe"}"#), ("tools/Editor.exe", b"MZ")]);
        let s = stage(std::slice::from_ref(&zip), &dir.path().join("work")).unwrap();
        assert_eq!((s.candidates.as_slice(), s.entry.as_deref()), (&["Game.exe".to_string()][..], Some("tools/Editor.exe")), "the card, though it is not a candidate");
        zip_of(&zip, &[("Game.exe", b"MZ"), ("engine.name", b"Game.exe\n"), ("redengine-game.json", br#"{"entry": "tools/Editor.exe"}"#), ("tools/Editor.exe", b"MZ")]);
        assert_eq!(stage(std::slice::from_ref(&zip), &dir.path().join("work")).unwrap().entry.as_deref(), Some("Game.exe"));
        zip_of(&zip, &[("Game.exe", b"MZ"), ("redengine-game.json", br#"{"entry": "Missing.exe"}"#)]);
        assert_eq!(stage(&[zip], &dir.path().join("work")).unwrap().entry.as_deref(), Some("Game.exe"), "a card that names nothing is passed over");
    }

    #[test]
    fn the_card_is_written_as_the_player_left_it_and_a_dropped_screenshot_comes_with_it() {
        let dir = tempfile::tempdir().unwrap();
        let zip = dir.path().join("g.zip");
        zip_of(&zip, &[("bin/Game.exe", b"MZ"), ("redengine-game.json", CARD.replace("StarMiner", "Game").as_bytes()), ("redengine-game-thumb.jpg", b"old"), ("shots/one.png", b"one")]);
        let shot = dir.path().join("Shot.PNG");
        std::fs::write(&shot, "dropped").unwrap();
        let s = stage(&[zip, shot], &dir.path().join("work")).unwrap();
        // The ZIP's card names a screenshot of its own, but the dropped one wins.
        assert_eq!(s.found.card.thumb.as_deref(), Some("shots/one.png"));
        assert_eq!(s.thumb.as_ref().unwrap().file_name().unwrap(), "thumb.png");
        let d = Details { description: "  Changed   by the poster. ".into(), presentation: "2d".into(), online: "Online.".into(), notes: "Fixed it.".into(), ..details("Star  Miner", "bin\\Game.exe") }.checked().unwrap();
        write_card(&s, &d).unwrap();
        let written = std::fs::read_to_string(s.folder.join("redengine-game.json")).unwrap();
        assert!(!written.contains("notes") && !written.contains("Fixed it") && written.contains("\"schema\": 1"), "{written}");
        let card = crate::meta::read_card_file(&s.folder).unwrap();
        assert_eq!((card.name.as_deref(), card.description.as_deref(), card.presentation.as_deref(), card.author.as_deref()), (Some("Star Miner"), Some("Changed by the poster."), Some("2d"), Some("human")));
        assert_eq!((card.online.as_deref(), card.entry.as_deref(), card.args.map(|a| a.len()), card.forked_from), (Some("Online."), Some("bin/Game.exe"), Some(2), None), "the ZIP's own args are kept");
        assert_eq!(card.thumb.as_deref(), Some("redengine-game-thumb.png"));
        assert_eq!(std::fs::read(s.folder.join("redengine-game-thumb.png")).unwrap(), b"dropped");
        assert!(!s.folder.join("redengine-game-thumb.jpg").exists(), "the other kind of picture it replaces does not linger");
        write_card(&s, &d).unwrap();
        // Dropped on its own, a game with a screenshot inside and a card naming it keeps both, and its args and its family are carried on.
        let one = dir.path().join("one.zip");
        zip_of(&one, &[("bin/Game.exe", b"MZ"), ("redengine-game.json", CARD.replace("StarMiner", "Game").as_bytes()), ("shots/one.png", b"one"), ("fork.json", br#"{"forked_from": {"slug": "snake", "version": 3}, "name": "Star Miner"}"#)]);
        let s = stage(&[one], &dir.path().join("work2")).unwrap();
        assert_eq!((s.args.len(), s.forked_from.clone()), (2, Some(crate::fork::Parent { slug: "snake".into(), version: 3 })));
        write_card(&s, &details("Star Miner", "bin/Game.exe").checked().unwrap()).unwrap();
        let card = crate::meta::read_card_file(&s.folder).unwrap();
        assert_eq!((card.thumb.as_deref(), card.args, card.forked_from), (Some("shots/one.png"), Some(vec!["--fast".to_string(), "--windowed".to_string()]), s.forked_from.clone()));
        assert!(s.folder.join("shots/one.png").is_file() && !s.folder.join("redengine-game-thumb.png").exists());
        prepare(&s.folder, "bin/Game.exe", &s.args).unwrap();
        assert_eq!(std::fs::read_to_string(s.folder.join("launch.args")).unwrap(), "--fast\n--windowed\n");
    }

    #[test]
    fn a_card_travels_from_a_folder_to_a_zip_and_back_into_the_form() {
        let dir = tempfile::tempdir().unwrap();
        let src = dir.path().join("Star Miner");
        for (name, data) in [("bin/StarMiner.exe", &b"MZ"[..]), ("bin/Editor.exe", b"MZ"), ("data/a.pak", b"xyz"), ("shots/one.png", b"png"), ("redengine-game.json", CARD.as_bytes())] {
            std::fs::create_dir_all(src.join(name).parent().unwrap()).unwrap();
            std::fs::write(src.join(name), data).unwrap();
        }
        let s = stage(&[src], &dir.path().join("work")).unwrap();
        let d = Details { description: "Mine asteroids, dodge pirates.".into(), presentation: "3d".into(), author: "ai".into(), online: "Co-op for two.".into(), ..details(&s.name, s.entry.as_deref().unwrap()) };
        write_card(&s, &d.checked().unwrap()).unwrap();
        prepare(&s.folder, s.entry.as_deref().unwrap(), &s.args).unwrap();
        let out = dir.path().join("out/star-miner-1-windows-x64.zip");
        zip_folder(&s.folder, &out).unwrap();
        let comment = zip::ZipArchive::new(File::open(&out).unwrap()).unwrap().comment().to_vec();
        assert!(comment.starts_with(b"redengine-game {\"schema\":1,\"name\":\"Star Miner\"") && !comment.contains(&b'\n'));
        let back = stage(std::slice::from_ref(&out), &dir.path().join("work2")).unwrap();
        assert_eq!((back.name.as_str(), back.entry.as_deref(), back.args.as_slice()), ("Star Miner", Some("bin/StarMiner.exe"), &["--fast".to_string(), "--windowed".to_string()][..]));
        let (mut first, mut again) = (s.found.card.clone(), back.found.card.clone());
        first.notes = None;
        again.notes = None;
        assert_eq!(again, first, "dropping the published ZIP fills the whole form again, without the old notes");
        assert!(back.found.from.values().all(|f| *f == crate::meta::Source::Card));
        assert_eq!(back.thumb, Some(back.folder.join("shots/one.png")));
        // The card alone in the comment (a ZIP stamped by the tool, or whose file was lost) says the same.
        let bare = dir.path().join("bare.zip");
        zip_with_comment(&bare, &[("bin/StarMiner.exe", b"MZ"), ("shots/one.png", b"png")], std::str::from_utf8(&comment).unwrap());
        let bare = stage(&[bare], &dir.path().join("work3")).unwrap();
        assert_eq!((bare.found.card.name.clone(), bare.found.card.thumb.clone(), bare.found.card.notes.clone()), (first.name.clone(), first.thumb.clone(), None));
        assert!(bare.found.from.values().all(|f| *f == crate::meta::Source::Zip));
    }

    #[test]
    fn a_fork_made_in_the_window_has_its_card_and_stage_reads_it() {
        let dir = tempfile::tempdir().unwrap();
        let installed = dir.path().join("games/snake/v3");
        std::fs::create_dir_all(&installed).unwrap();
        std::fs::write(installed.join("RedEngine2D.exe"), "MZ").unwrap();
        std::fs::write(installed.join("engine.name"), "RedEngine2D.exe\n").unwrap();
        std::fs::write(installed.join("redengine-game.json"), r#"{"name": "Snake", "description": "Eat.", "presentation": "2d", "author": "ai", "thumb": "redengine-game-thumb.png"}"#).unwrap();
        std::fs::write(installed.join("redengine-game-thumb.png"), "png").unwrap();
        let parent = crate::fork::Parent { slug: "snake".into(), version: 3 };
        let fork = crate::fork::make(dir.path(), &installed, &parent, "Snake", "Neon Snake").unwrap();
        let s = stage(std::slice::from_ref(&fork), &dir.path().join("work")).unwrap();
        assert_eq!((s.name.as_str(), s.forked_from.as_ref(), s.thumb), ("Neon Snake", Some(&parent), None));
        assert_eq!(s.found.card, crate::meta::Card { name: Some("Neon Snake".into()), presentation: Some("2d".into()), forked_from: Some(parent.clone()), ..Default::default() });
        // fork.json wins when the card names another parent or name.
        std::fs::write(fork.join("redengine-game.json"), r#"{"name": "Card Name", "forked_from": {"slug": "other", "version": 9}}"#).unwrap();
        let s = stage(std::slice::from_ref(&fork), &dir.path().join("work")).unwrap();
        assert_eq!((s.name.as_str(), s.forked_from.as_ref()), ("Card Name", Some(&parent)), "the parent is fork.json's; the name is the card's, as for any game");
    }

    #[cfg(unix)]
    #[test]
    fn a_link_in_a_dropped_folder_is_left_behind_so_a_card_and_a_screenshot_cannot_come_from_outside() {
        use std::os::unix::fs::symlink;
        let dir = tempfile::tempdir().unwrap();
        let outside = dir.path().join("outside");
        std::fs::create_dir_all(outside.join("inner")).unwrap();
        std::fs::write(outside.join("card.json"), r#"{"name": "LEAK", "description": "leaked"}"#).unwrap();
        std::fs::write(outside.join("shot.png"), b"outside picture").unwrap();
        std::fs::write(outside.join("inner/secret.txt"), b"secret").unwrap();
        let linked = dir.path().join("Linked Card");
        std::fs::create_dir_all(&linked).unwrap();
        std::fs::write(linked.join("Game.bat"), b"@echo off").unwrap();
        symlink(outside.join("card.json"), linked.join("redengine-game.json")).unwrap();
        symlink(outside.join("inner"), linked.join("inner")).unwrap();
        let s = stage(std::slice::from_ref(&linked), &dir.path().join("work")).unwrap();
        assert_eq!((s.name.as_str(), s.found.clone()), ("Linked Card", crate::meta::Found::default()), "a linked card says nothing");
        assert!(!s.folder.join("redengine-game.json").exists() && !s.folder.join("inner").exists() && s.size == 9, "{:?}", s.size);
        let shot = dir.path().join("Linked Shot");
        std::fs::create_dir_all(&shot).unwrap();
        std::fs::write(shot.join("Game.bat"), b"@echo off").unwrap();
        std::fs::write(shot.join("redengine-game.json"), r#"{"name": "Real", "thumb": "shot.png"}"#).unwrap();
        symlink(outside.join("shot.png"), shot.join("shot.png")).unwrap();
        let s = stage(std::slice::from_ref(&shot), &dir.path().join("work")).unwrap();
        assert_eq!((s.name.as_str(), s.thumb, s.found.card.thumb), ("Real", None, None), "a linked screenshot is neither shown nor published");
        // A folder dropped through a link is what the player pointed at, so that is followed.
        let alias = dir.path().join("alias");
        symlink(&shot, &alias).unwrap();
        assert_eq!(stage(&[alias], &dir.path().join("work")).unwrap().name, "Real");
    }

    #[test]
    fn a_folder_nested_deeper_than_a_game_can_be_is_refused() {
        let dir = tempfile::tempdir().unwrap();
        let deep = dir.path().join("Deep");
        std::fs::create_dir_all(deep.join("a/".repeat(70))).unwrap();
        let e = stage(std::slice::from_ref(&deep), &dir.path().join("work")).unwrap_err().to_string();
        assert!(e.contains("nested"), "{e}");
        let zip = dir.path().join("deep.zip");
        zip_of(&zip, &[(&format!("{}x.bat", "a/".repeat(1900)), b"@echo off"), ("other.txt", b"x")]);
        assert!(stage(&[zip], &dir.path().join("work")).unwrap_err().to_string().contains("unsafe path"));
        let ok = dir.path().join("Ok");
        std::fs::create_dir_all(ok.join("a/".repeat(60))).unwrap();
        std::fs::write(ok.join("Game.bat"), b"x").unwrap();
        assert_eq!(stage(&[ok], &dir.path().join("work")).unwrap().candidates, ["Game.bat"]);
    }

    fn big_shot(path: &Path, size: u64) -> PathBuf {
        File::create(path).unwrap().set_len(size).unwrap();
        path.to_path_buf()
    }

    #[test]
    fn a_screenshot_over_5_mb_goes_to_the_site_and_is_not_named_by_a_card_no_reader_would_accept() {
        let dir = tempfile::tempdir().unwrap();
        let bat = dir.path().join("Star Miner.bat");
        std::fs::write(&bat, "@echo off\r\nREM redengine-game\r\nREM name: Star Miner\r\n").unwrap();
        for (size, travels) in [(5 * 1024 * 1024, true), (5 * 1024 * 1024 + 1, false)] {
            let s = stage(&[bat.clone(), big_shot(&dir.path().join("shot.png"), size)], &dir.path().join("work")).unwrap();
            let d = details("Star Miner", "Star Miner.bat").checked().unwrap();
            write_card(&s, &d).unwrap();
            let card = crate::meta::read_card_file(&s.folder).unwrap();
            assert_eq!((card.thumb.is_some(), s.folder.join("redengine-game-thumb.png").exists()), (travels, travels), "{size} bytes");
            assert!(s.thumb.as_ref().is_some_and(|t| t.is_file()), "the screenshot is still the release's on the site");
            let out = dir.path().join("out.zip");
            zip_folder(&s.folder, &out).unwrap();
            let again = stage(&[out], &dir.path().join("work2")).unwrap();
            assert_eq!(again.found.card.thumb.is_some(), travels, "dropping the published ZIP again shows what the card says: {size} bytes");
        }
    }

    #[test]
    fn the_name_comes_from_the_card_unless_it_makes_no_id_or_is_the_parents() {
        let dir = tempfile::tempdir().unwrap();
        let zip = dir.path().join("Star_Miner.zip");
        zip_of(&zip, &[("StarMiner.exe", b"MZ"), ("redengine-game.json", r#"{"name": "星の旅", "description": "Words."}"#.as_bytes())]);
        let s = stage(std::slice::from_ref(&zip), &dir.path().join("work")).unwrap();
        assert_eq!((s.name.as_str(), s.found.card.name.as_deref()), ("Star Miner", Some("星の旅")), "a name with no letters or digits makes no id: the file's name is the start");
        assert_eq!(stage(&[dir.path().join("Star_Miner.zip")], &dir.path().join("work")).unwrap().name, "Star Miner");
        // A fork made before the card existed, of a game that has one now: the fork's own name, not its parent's.
        zip_of(
            &zip,
            &[
                ("Game.bat", b"@echo off"),
                ("fork.json", br#"{"forked_from": {"slug": "text-quest", "version": 1}, "name": "Quest Remix"}"#),
                ("redengine-game.json", br#"{"name": "Text Quest", "description": "The parent's."}"#),
            ],
        );
        let s = stage(std::slice::from_ref(&zip), &dir.path().join("work")).unwrap();
        assert_eq!((s.name.as_str(), s.forked_from), ("Quest Remix", Some(crate::fork::Parent { slug: "text-quest".into(), version: 1 })));
        // A card of a game that says it is a fork of itself says nothing about a lineage.
        zip_of(&zip, &[("Game.bat", b"@echo off"), ("redengine-game.json", br#"{"name": "Neon Racer", "forked_from": {"slug": "neon-racer", "version": 2}}"#)]);
        assert_eq!(stage(std::slice::from_ref(&zip), &dir.path().join("work")).unwrap().forked_from, None);
        zip_of(&zip, &[("Game.bat", b"@echo off"), ("redengine-game.json", br#"{"name": "Turbo Racer", "forked_from": {"slug": "neon-racer", "version": 2}}"#)]);
        assert_eq!(stage(&[zip], &dir.path().join("work")).unwrap().forked_from.map(|p| p.slug), Some("neon-racer".to_string()));
    }

    #[test]
    fn a_program_dropped_alone_is_the_game_whatever_it_is_called() {
        let dir = tempfile::tempdir().unwrap();
        let bat = dir.path().join("Install_And_Play.bat");
        std::fs::write(&bat, "@echo off\r\nREM redengine-game\r\nREM name: Install And Play\r\nREM presentation: 2d\r\n").unwrap();
        let s = stage(std::slice::from_ref(&bat), &dir.path().join("work")).unwrap();
        assert_eq!((s.name.as_str(), s.candidates.as_slice(), s.entry.as_deref(), s.found.card.presentation.as_deref()), ("Install And Play", &["Install_And_Play.bat".to_string()][..], Some("Install_And_Play.bat"), Some("2d")));
        // Among other files, a name like that is still not the game.
        let zip = dir.path().join("g.zip");
        zip_of(&zip, &[("Install_And_Play.bat", b"@echo off"), ("readme.txt", b"r")]);
        assert!(stage(&[zip], &dir.path().join("work")).unwrap().candidates.is_empty());
    }

    #[test]
    fn a_fork_made_in_the_window_has_nothing_of_its_parents_words_even_from_a_script_or_program() {
        let dir = tempfile::tempdir().unwrap();
        let installed = dir.path().join("games/text-quest/v1");
        std::fs::create_dir_all(&installed).unwrap();
        let script = ["@echo off", "REM redengine-game", "REM name: Text Quest", "REM description: A tiny text adventure.", "REM author: ai", "REM online: Co-op", "REM notes: First release.", "echo hi", ""];
        std::fs::write(installed.join("Quest.bat"), script.join("\r\n")).unwrap();
        std::fs::write(installed.join("engine.name"), "Quest.bat\n").unwrap();
        let parent = crate::fork::Parent { slug: "text-quest".into(), version: 1 };
        let fork = crate::fork::make(dir.path(), &installed, &parent, "Text Quest", "Quest Remix").unwrap();
        let s = stage(std::slice::from_ref(&fork), &dir.path().join("work")).unwrap();
        assert_eq!((s.name.as_str(), s.forked_from.as_ref()), ("Quest Remix", Some(&parent)));
        let c = &s.found.card;
        assert_eq!((c.description.as_deref(), c.author.as_deref(), c.online.as_deref(), c.notes.is_some()), (None, None, None, false), "{c:?}");
        // The same game by itself keeps them.
        let own = stage(&[installed], &dir.path().join("work2")).unwrap().found.card;
        assert_eq!((own.description.as_deref(), own.author.as_deref()), (Some("A tiny text adventure."), Some("ai")));
        // A fork.json beside a script is a fork even before any card says so (a fork the app made long ago).
        let old = dir.path().join("Old Fork");
        std::fs::create_dir_all(&old).unwrap();
        std::fs::write(old.join("Quest.bat"), script.join("\r\n")).unwrap();
        std::fs::write(old.join("fork.json"), r#"{"forked_from": {"slug": "text-quest", "version": 1}, "name": "Old Remix"}"#).unwrap();
        let s = stage(&[old], &dir.path().join("work3")).unwrap();
        assert_eq!((s.name.as_str(), s.found.card.description, s.found.card.notes), ("Old Remix", None, None));
    }

    #[test]
    fn engine_name_is_read_when_it_is_small() {
        let dir = tempfile::tempdir().unwrap();
        let zip = dir.path().join("g.zip");
        let big = format!("B.bat\n{}", " ".repeat(3000));
        zip_of(&zip, &[("A.bat", b"@echo off"), ("B.bat", b"@echo off"), ("engine.name", big.as_bytes())]);
        assert_eq!(stage(std::slice::from_ref(&zip), &dir.path().join("work")).unwrap().entry, None, "more than a kilobyte is not an engine.name: two candidates, none chosen");
        zip_of(&zip, &[("A.bat", b"@echo off"), ("B.bat", b"@echo off"), ("engine.name", b" B.bat \r\n")]);
        assert_eq!(stage(&[zip], &dir.path().join("work")).unwrap().entry.as_deref(), Some("B.bat"));
    }

    #[test]
    fn a_cards_arguments_are_for_its_own_program_and_launch_args_fill_in_when_it_has_none() {
        let dir = tempfile::tempdir().unwrap();
        let zip = dir.path().join("g.zip");
        zip_of(&zip, &[("bin/Game.exe", b"MZ"), ("bin/Editor.exe", b"MZ"), ("redengine-game.json", br#"{"entry": "bin/Game.exe", "args": ["--fast"]}"#)]);
        let s = stage(&[zip], &dir.path().join("work")).unwrap();
        assert_eq!((s.args_for("bin/Game.exe"), s.args_for(" bin\\Game.exe "), s.args_for("bin/Editor.exe")), (vec!["--fast".to_string()], vec!["--fast".to_string()], vec![]));
        write_card(&s, &details("Star Miner", "bin/Editor.exe").checked().unwrap()).unwrap();
        let card = crate::meta::read_card_file(&s.folder).unwrap();
        assert_eq!((card.entry.as_deref(), card.args), (Some("bin/Editor.exe"), None), "the other program does not start with the first one's arguments");
        prepare(&s.folder, "bin/Editor.exe", &s.args_for("bin/Editor.exe")).unwrap();
        assert_eq!(std::fs::read_to_string(s.folder.join("launch.args")).unwrap(), "");
        // A game with a launch.args of its own and no card: the card says what the file says (and the file is left as it is).
        let engine = dir.path().join("e.zip");
        zip_of(&engine, &[("RedEngine.exe", b"MZ"), ("engine.name", b"RedEngine.exe\n"), ("launch.args", b"content/map.json\n  --windowed  \n\n")]);
        let s = stage(&[engine], &dir.path().join("work2")).unwrap();
        assert!(s.args.is_empty());
        write_card(&s, &details("Engine Game", "RedEngine.exe").checked().unwrap()).unwrap();
        assert_eq!(crate::meta::read_card_file(&s.folder).unwrap().args, Some(vec!["content/map.json".to_string(), "--windowed".to_string()]));
        prepare(&s.folder, "RedEngine.exe", &s.args_for("RedEngine.exe")).unwrap();
        assert_eq!(std::fs::read_to_string(s.folder.join("launch.args")).unwrap(), "content/map.json\n  --windowed  \n\n", "prepare keeps the arguments file the game came with");
    }

    #[test]
    fn notes_in_a_script_are_not_the_next_builds_because_the_script_ships_unchanged() {
        let dir = tempfile::tempdir().unwrap();
        let bat = dir.path().join("Quest.bat");
        std::fs::write(&bat, "@echo off\r\nREM redengine-game\r\nREM name: Text Quest\r\nREM notes: First release.\r\nREM notes: Fixed the door.\r\necho hi\r\n").unwrap();
        let s = stage(std::slice::from_ref(&bat), &dir.path().join("work")).unwrap();
        assert_eq!((s.name.as_str(), s.found.card.notes.clone(), s.found.from.get("notes")), ("Text Quest", None, None));
        // Published as the window publishes it, then dropped again for the next build: the first build's notes do not come back as "what changed".
        write_card(&s, &details("Text Quest", "Quest.bat").checked().unwrap()).unwrap();
        prepare(&s.folder, "Quest.bat", &s.args_for("Quest.bat")).unwrap();
        let out = dir.path().join("text-quest-1-windows-x64.zip");
        zip_folder(&s.folder, &out).unwrap();
        let again = stage(&[out], &dir.path().join("work2")).unwrap();
        assert!(std::fs::read_to_string(again.folder.join("Quest.bat")).unwrap().contains("Fixed the door."), "the script is published as it was");
        assert_eq!((again.name.as_str(), again.found.card.notes, again.found.from.get("notes")), ("Text Quest", None, None));
    }

    #[test]
    fn a_cards_arguments_are_for_its_own_entry_even_when_engine_name_starts_another_program() {
        let dir = tempfile::tempdir().unwrap();
        let zip = dir.path().join("g.zip");
        zip_of(&zip, &[("A.bat", b"@echo off"), ("B.bat", b"@echo off"), ("engine.name", b"A.bat\n"), ("redengine-game.json", br#"{"entry": "B.bat", "args": ["--for-b-only"]}"#)]);
        let s = stage(&[zip], &dir.path().join("work")).unwrap();
        assert_eq!(s.entry.as_deref(), Some("A.bat"), "engine.name wins");
        assert_eq!((s.args_for("A.bat"), s.args_for("B.bat")), (vec![], vec!["--for-b-only".to_string()]));
        write_card(&s, &details("Two Bats", "A.bat").checked().unwrap()).unwrap();
        assert_eq!(crate::meta::read_card_file(&s.folder).unwrap().args, None, "the program engine.name starts gets none of the card's arguments");
        prepare(&s.folder, "A.bat", &s.args_for("A.bat")).unwrap();
        assert_eq!(std::fs::read_to_string(s.folder.join("launch.args")).unwrap(), "");
        // A card that names no program speaks for the one the game starts with.
        let one = dir.path().join("one.zip");
        zip_of(&one, &[("Game.bat", b"@echo off"), ("redengine-game.json", br#"{"args": ["--x"]}"#)]);
        let s = stage(&[one], &dir.path().join("work2")).unwrap();
        assert_eq!(s.args_for("Game.bat"), ["--x"]);
    }

    #[test]
    fn the_name_an_engine_gives_its_own_program_does_not_name_the_game() {
        // `Moonlit Quest/Game.exe` is NW.js's own program, as RPG Maker MV ships it, with NW.js's version information: the game is named after the drop.
        let dir = tempfile::tempdir().unwrap();
        let zip = dir.path().join("Moonlit_Quest.zip");
        std::fs::copy(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../distribution/testdata/game_meta/zip-runtime-program.zip"), &zip).unwrap();
        let s = stage(&[zip], &dir.path().join("work")).unwrap();
        assert_eq!((s.name.as_str(), s.entry.as_deref(), s.found.clone()), ("Moonlit Quest", Some("Game.exe"), crate::meta::Found::default()));
    }

    #[test]
    fn what_the_player_typed_is_cleaned_and_cut_as_the_card_keeps_it() {
        let d = Details { description: format!("  Words\u{7} \u{202e}here {}  ", "x".repeat(500)), ..details(&format!("  {}  ", "N".repeat(80)), "a.exe") }.checked().unwrap();
        assert_eq!((d.name.as_str(), d.description.chars().count()), ("N".repeat(60).as_str(), 400));
        assert!(d.description.starts_with("Words here x") && !d.description.contains(['\u{7}', '\u{202e}']));
        let meta = record(&d, &slugify(&d.name), 1, "d", ("z", 1, "ab"), None);
        assert_eq!((meta["name"].as_str(), meta["description"].as_str()), (Some(d.name.as_str()), Some(d.description.as_str())), "the release and the card in the game say the same");
        let e = Details { online: "Join 203.0.113.5:27015".into(), ..details("G", "a.exe") }.checked().unwrap_err().to_string();
        assert!(e.contains("address"), "{e}");
        assert!(Details { online: "Co-op for two.".into(), ..details("G", "a.exe") }.checked().is_ok());
    }

    #[test]
    fn slugs_come_from_names() {
        assert_eq!(slugify("Star Miner: Deluxe!"), "star-miner-deluxe");
        assert_eq!(slugify("--"), "");
    }
}
