//! The game card: a game that describes itself, so the person publishing it types nothing. `docs/GAME_METADATA.md` is the contract and
//! `distribution/game_meta.py` its twin for the command line; both read the same fixtures. A card is a small JSON object kept where it suits
//! each kind of file: `redengine-game.json` in the game's folder, the ZIP's comment, a header block in a `.bat` / `.cmd`, a record after an
//! `.exe`'s last byte (or just before its certificate table, when it was signed after it was stamped), or the version information an `.exe` already
//! has. [`Found`] is what a game says, with the source of every field.
//!
//! Everything here reads a hostile game. Nothing is run, every read is bounded (a card over 16 KiB is ignored whole, a script is read for its
//! first 64 lines, a program for its last 16 KiB and its resources), a program's headers are checked at every step (no `unsafe`, nothing indexed
//! without a length check, counts and depths limited), and a path in a card is used only when it is a plain file inside the game, never through
//! a link. A ZIP is looked at as the app unpacks it (`crate::archive::member_path` is the one rule for what a member may be called), so what the
//! command line reads and what the window stages are the same game.
#![forbid(unsafe_code)]

use std::collections::BTreeMap;
use std::fs::File;
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};

use serde::Serialize;
use serde_json::Value;

use crate::fork::Parent;
use crate::{Error, Result};

/// The card's file, at the root of a game.
pub const FILE: &str = "redengine-game.json";
/// The screenshot the app copies beside it (`.png` or `.jpg`).
pub const THUMB: &str = "redengine-game-thumb";
const TAG: &str = "redengine-game";
const MAGIC: &[u8; 8] = b"REDGAME1";
const BOM: &[u8] = b"\xEF\xBB\xBF";
const RUNNABLE: [&str; 3] = ["exe", "bat", "cmd"];
const PRESENTATIONS: [&str; 3] = ["2d", "3d", "hybrid"];
/// A card is ignored whole above this many bytes.
const MAX_CARD: usize = 16 * 1024;
/// A screenshot of a game is at most this many bytes.
pub(crate) const MAX_THUMB: u64 = 5 * 1024 * 1024;
/// What is read of a script (64 lines are looked at, however long).
const HEAD: u64 = 64 * 1024;
/// The most programs read when none is chosen.
const MAX_PROGRAMS: usize = 16;
/// The most any one read of a program asks for.
const MAX_READ: usize = 128 * 1024;
const MAX_VERSION: usize = 64 * 1024;
/// A `forked_from` slug is at most this long (a game's slug is made from a name of 60 characters).
pub(crate) const MAX_SLUG: usize = 64;
/// White space as the ZIP comment and a script header count it: ASCII only (space, tab, line ends, vertical tab, form feed).
const SPACE: [char; 6] = [' ', '\t', '\n', '\r', '\x0b', '\x0c'];

/// What a game says about itself. A field the game does not say, or says wrongly, is `None`.
#[derive(Debug, Clone, Default, PartialEq, Serialize)]
pub struct Card {
    /// The name players see (60 characters).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    /// One or two sentences (400).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    /// `2d`, `3d` or `hybrid`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub presentation: Option<String>,
    /// Who designed it: `ai` or `human`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub author: Option<String>,
    /// A note when it has online multiplayer (200).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub online: Option<String>,
    /// What starts it: a `.exe`, `.bat` or `.cmd` path inside the game, `/`-separated.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub entry: Option<String>,
    /// What to start it with (16 of 200).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub args: Option<Vec<String>>,
    /// A `.png` or `.jpg` screenshot inside the game, up to 5 MB.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub thumb: Option<String>,
    /// What changed in this build (10 of 200); read to fill in the form, never written.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub notes: Option<Vec<String>>,
    /// The game and version it was made from.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub forked_from: Option<Parent>,
}

/// Where a field of the card was found, from the strongest source to the weakest.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Source {
    /// `redengine-game.json`.
    Card,
    /// The ZIP's comment.
    Zip,
    /// A script's header block.
    Bat,
    /// The record after an `.exe`.
    Exe,
    /// The `.exe`'s version information.
    Program,
}

/// What a game says about itself: each field from the strongest source that has it, and which source that was.
#[derive(Debug, Clone, Default, PartialEq, Serialize)]
pub struct Found {
    pub card: Card,
    pub from: BTreeMap<&'static str, Source>,
}

/// A string as the card keeps it: control characters and the Unicode direction overrides dropped, runs of white space one space, the ends
/// trimmed, and cut to `max` characters.
pub fn clean(s: &str, max: usize) -> String {
    let mut out = String::new();
    let mut gap = false;
    for c in s.chars() {
        if c.is_whitespace() {
            gap = true;
        } else if !c.is_control() && !matches!(c, '\u{202A}'..='\u{202E}' | '\u{2066}'..='\u{2069}') {
            if gap && !out.is_empty() {
                out.push(' ');
            }
            gap = false;
            out.push(c);
        }
    }
    if let Some((i, _)) = out.char_indices().nth(max) {
        out.truncate(i);
        out.truncate(out.trim_end().len());
    }
    out
}

/// A path inside the game as a card may name it, as written: relative and `/`-separated (so no leading or doubled `/`, no `.` or `..` part), no
/// backslash, drive or stream colon, no device name, at most 260 characters, ending in one of `exts` in any case.
fn inside(s: &str, exts: &[&str]) -> Option<String> {
    let bad = s.chars().count() > 260 || s.contains(['\\', ':', '\0']) || s.split('/').any(|p| matches!(p, "" | "." | "..") || crate::archive::device(p));
    let lower = s.to_ascii_lowercase();
    (!bad && exts.iter().any(|e| lower.ends_with(&format!(".{e}")))).then(|| s.to_string())
}

/// Well-known endings of the name of a place on the internet.
const DOMAINS: [&str; 17] = ["com", "net", "org", "io", "gg", "tv", "me", "us", "uk", "de", "eu", "xyz", "dev", "app", "ly", "gl", "info"];

/// Whether an online note is a place or a key rather than words (a card says how a game is played online, never where to join it): a URL, an IPv4 or an
/// IPv6 address, `name:port`, a name ending in a well-known domain, or a secret given as `key=...`. The note is cleaned; the check is on ASCII only.
pub fn looks_like_address(note: &str) -> bool {
    let note = note.to_ascii_lowercase();
    if ["key=", "token=", "password=", "pass=", "secret="].iter().any(|k| note.contains(k)) {
        return true;
    }
    note.split_whitespace().any(|word| {
        let t = word.trim_start_matches(|c: char| ",;!?()[]{}<>\"'".contains(c)).trim_end_matches(|c: char| ",;!?()[]{}<>\"'.:".contains(c));
        let host = t.split('/').next().unwrap_or("");
        let host = host.rsplit('@').next().unwrap_or(host);
        let (name, port) = host.rsplit_once(':').map_or((host, ""), |(n, p)| (n, p));
        let labels: Vec<&str> = name.split('.').collect();
        let digits = |s: &str, most: usize| (1..=most).contains(&s.len()) && s.bytes().all(|b| b.is_ascii_digit());
        t.contains("://")
            || t.starts_with("www.")
            || t.contains("::")
            || (t.matches(':').count() >= 3 && t.bytes().all(|b| b.is_ascii_hexdigit() || b == b':'))
            || (labels.len() == 4 && labels.iter().all(|l| digits(l, 3)))
            || (digits(port, 5) && port.len() >= 2 && name.bytes().last().is_some_and(|b| b.is_ascii_lowercase() || b == b']'))
            || (labels.len() >= 2 && labels.iter().all(|l| !l.is_empty() && l.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-')) && DOMAINS.contains(&labels[labels.len() - 1]))
    })
}

fn parent(v: &Value) -> Option<Parent> {
    let f = v.get("forked_from")?;
    let slug = f.get("slug")?.as_str()?;
    let version = f.get("version")?.as_u64()?;
    (!slug.is_empty() && slug.len() <= MAX_SLUG && slug == crate::upload::slugify(slug) && version >= 1).then(|| Parent { slug: slug.into(), version })
}

impl Card {
    /// The card in `bytes`: UTF-8 JSON (a leading byte order mark is allowed). `None` when it is over 16 KiB, not text, or not an object.
    pub fn parse(bytes: &[u8]) -> Option<Card> {
        if bytes.len() > MAX_CARD {
            return None;
        }
        let text = std::str::from_utf8(bytes.strip_prefix(BOM).unwrap_or(bytes)).ok()?;
        let v: Value = serde_json::from_str(text).ok()?;
        v.is_object().then(|| Card::from_value(&v))
    }

    /// The fields of a JSON object, cleaned; one of the wrong type (a list holding anything but strings too), or empty once cleaned, is left out.
    fn from_value(v: &Value) -> Card {
        let text = |k: &str, max: usize| v.get(k).and_then(Value::as_str).map(|s| clean(s, max)).filter(|s| !s.is_empty());
        let one_of = |k: &str, ok: &[&str]| text(k, 20).filter(|s| ok.contains(&s.as_str()));
        let list = |k: &str, n: usize| {
            let all = v.get(k)?.as_array()?.iter().map(Value::as_str).collect::<Option<Vec<&str>>>()?;
            let items: Vec<String> = all.into_iter().map(|s| clean(s, 200)).filter(|s| !s.is_empty()).take(n).collect();
            (!items.is_empty()).then_some(items)
        };
        Card {
            name: text("name", 60),
            description: text("description", 400),
            presentation: one_of("presentation", &PRESENTATIONS).or_else(|| one_of("kind", &PRESENTATIONS)),
            author: one_of("author", &["ai", "human"]),
            online: text("online", 200).filter(|o| !looks_like_address(o)),
            entry: text("entry", usize::MAX).and_then(|e| inside(&e, &RUNNABLE)),
            args: list("args", 16),
            thumb: text("thumb", usize::MAX).and_then(|t| inside(&t, &["png", "jpg"])),
            notes: list("notes", 10),
            forked_from: parent(v),
        }
    }

    /// The card as a reader would find it again after it was written (cleaned, limits applied).
    fn normalized(&self) -> Card {
        Card::from_value(&serde_json::to_value(self).expect("a card serializes"))
    }

    /// Drop the `entry` and `thumb` that name no usable file in `game`.
    fn check(&mut self, game: &Game) {
        if self.entry.as_ref().is_some_and(|e| game.file(e).is_none()) {
            self.entry = None;
        }
        if self.thumb.as_ref().is_some_and(|t| game.file(t).is_none_or(|(_, size)| size > MAX_THUMB)) {
            self.thumb = None;
        }
    }
}

impl Found {
    /// Take from `card` (read from `src`) every field not found yet, once its `entry` and `thumb` are checked against `game`.
    fn add(&mut self, src: Source, card: Option<Card>, game: &Game) {
        let Some(mut card) = card else { return };
        card.check(game);
        macro_rules! take {
            ($($f:ident),*) => {
                $(if self.card.$f.is_none() && card.$f.is_some() {
                    self.card.$f = card.$f.take();
                    self.from.insert(stringify!($f), src);
                })*
            };
        }
        take!(name, description, presentation, author, online, entry, args, thumb, notes, forked_from);
    }
}

/// The card as the tool writes it: `schema` 1 first, then the fields, never `notes`. Pretty for the file, on one line for the comment and the record.
fn json(card: &Card, pretty: bool) -> String {
    #[derive(Serialize)]
    struct Out<'a> {
        schema: u8,
        #[serde(flatten)]
        card: &'a Card,
    }
    let card = Card { notes: None, ..card.normalized() };
    let out = Out { schema: 1, card: &card };
    (if pretty { serde_json::to_string_pretty(&out) } else { serde_json::to_string(&out) }).expect("a card serializes")
}

/// `card` cut to what a reader takes, for a card that goes into a game: while its file would be over 16 KiB (only with fields of the longest, in
/// 4-byte characters), the arguments (`launch.args` has them), the online note, the description and the screenshot go, in that order.
fn fitted(card: &Card) -> Card {
    let mut card = Card { notes: None, ..card.normalized() };
    for cut in 0..4 {
        if json(&card, true).len() < MAX_CARD {
            break;
        }
        match cut {
            0 => card.args = None,
            1 => card.online = None,
            2 => card.description = None,
            _ => card.thumb = None,
        }
    }
    card
}

/// Write `card` as the game's `redengine-game.json` (pretty, `schema` 1, without `notes`, cut to fit 16 KiB).
pub fn write_card_file(folder: &Path, card: &Card) -> Result<()> {
    std::fs::write(folder.join(FILE), json(&fitted(card), true) + "\n")?;
    Ok(())
}

/// The ZIP comment for `card`: `redengine-game ` and the card on one line.
pub fn comment(card: &Card) -> String {
    format!("{TAG} {}", json(&fitted(card), false))
}

/// The card file at the root of `folder`, when there is a usable one.
pub fn read_card_file(folder: &Path) -> Option<Card> {
    Game { dir: folder, only: None }.read(FILE, MAX_CARD + 1).and_then(|b| Card::parse(&b))
}

/// The card in a ZIP's comment, read from the archive itself: unpacking it loses the comment, so read it first.
pub fn zip_comment(path: &Path) -> Option<Card> {
    let zip = zip::ZipArchive::new(File::open(path).ok()?).ok()?;
    let rest = space_start(zip.comment()).strip_prefix(TAG.as_bytes())?;
    let payload = space_start(rest);
    (payload.len() < rest.len()).then(|| Card::parse(space_end(payload))).flatten()
}

fn space_start(b: &[u8]) -> &[u8] {
    &b[b.iter().position(|c| !SPACE.contains(&char::from(*c))).unwrap_or(b.len())..]
}

fn space_end(b: &[u8]) -> &[u8] {
    &b[..b.iter().rposition(|c| !SPACE.contains(&char::from(*c))).map_or(0, |n| n + 1)]
}

/// What a ZIP, a folder or a single `.exe` / `.bat` / `.cmd` says about itself. A ZIP is unpacked into a temporary folder to be looked at (see
/// [`unpack_to_read`]), and the answer is the one the app finds when it is dropped on the window.
pub fn read_path(path: &Path) -> Found {
    use crate::upload::{candidates, ext, top_folder};
    if path.is_dir() {
        let root = top_folder(path).unwrap_or_else(|_| path.to_path_buf());
        return read_folder(&root, None, &candidates(&root), false);
    }
    match ext(path).as_str() {
        "zip" => {
            let Some(tmp) = new_folder() else { return Found::default() };
            let found = match unpack_to_read(path, &tmp) {
                Some(()) => {
                    let root = top_folder(&tmp).unwrap_or_else(|_| tmp.clone());
                    read_folder(&root, zip_comment(path), &candidates(&root), false)
                }
                None => Found::default(),
            };
            let _ = std::fs::remove_dir_all(&tmp);
            found
        }
        "exe" | "bat" | "cmd" => match (path.parent(), path.file_name().and_then(|n| n.to_str())) {
            (Some(dir), Some(name)) => read(&Game { dir, only: Some(name) }, None, &[name.to_string()], false),
            _ => Found::default(),
        },
        _ => Found::default(),
    }
}

/// A folder in the temporary folder that did not exist before, with a name nobody can guess (so nobody can have put a link there); `None` if none can be made.
fn new_folder() -> Option<PathBuf> {
    static N: std::sync::atomic::AtomicU32 = std::sync::atomic::AtomicU32::new(0);
    let nanos = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_or(0, |d| d.as_nanos());
    (0..8).find_map(|_| {
        let n = N.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!("redengine-card-{}-{n}-{nanos:x}", std::process::id()));
        std::fs::create_dir(&path).ok().map(|()| path)
    })
}

/// Unpack a ZIP into `into` to look at it. Unlike `archive::unpack`, which refuses a whole archive for one bad name, a member with an unsafe name
/// (see [`crate::archive::member_path`]) is simply not there, a link is an empty folder (never a file), one that cannot be read is left as far as it
/// got, at most 200 000 members are looked at, and no more than 512 MiB is written (members after that are empty files).
fn unpack_to_read(path: &Path, into: &Path) -> Option<()> {
    let mut zip = zip::ZipArchive::new(File::open(path).ok()?).ok()?;
    if zip.len() > 200_000 {
        return None;
    }
    std::fs::create_dir_all(into).ok()?;
    let mut budget = 512u64 << 20;
    for i in 0..zip.len() {
        let Ok(mut entry) = zip.by_index(i) else { continue };
        let link = entry.unix_mode().is_some_and(|m| m & 0o170_000 == 0o120_000);
        let Some(relative) = crate::archive::member_path(entry.name()) else { continue };
        let target = into.join(relative);
        // A link is not a file, but it is something the ZIP holds: an empty folder stands in for it, so a ZIP of one folder and a link is not one folder.
        if entry.is_dir() || link {
            let _ = std::fs::create_dir_all(&target);
            continue;
        }
        // A member that cannot be made or read to its end is left as far as it got.
        if let Ok(mut out) = target.parent().map_or(Ok(()), std::fs::create_dir_all).and_then(|()| File::create(&target)) {
            let _ = std::io::copy(&mut (&mut entry).take(budget), &mut out);
            budget -= out.metadata().map_or(0, |m| m.len()).min(budget);
        }
    }
    Some(())
}

/// What the game in `folder` says about itself. `zip` is the card in the comment of the ZIP it came from, `candidates` what could start it
/// (`upload::candidates`) and `fork` whether the caller knows it is a fork (its `fork.json`): a fork, which is also a game whose card file or ZIP comment
/// says `forked_from`, takes no description, designer, online note or notes from a script or program, because those were its parent's.
pub fn read_folder(folder: &Path, zip: Option<Card>, candidates: &[String], fork: bool) -> Found {
    read(&Game { dir: folder, only: None }, zip, candidates, fork)
}

fn read(game: &Game, zip: Option<Card>, candidates: &[String], fork: bool) -> Found {
    let mut found = Found::default();
    found.add(Source::Card, game.read(FILE, MAX_CARD + 1).and_then(|b| Card::parse(&b)), game);
    found.add(Source::Zip, zip, game);
    let fork = fork || found.card.forked_from.is_some();
    // The program that starts the game: `engine.name` (at most 1024 bytes), else the card's `entry`, else each candidate in name order.
    let engine = game.engine_name().and_then(|s| inside(&s, &RUNNABLE)).filter(|e| game.file(e).is_some());
    let programs: Vec<String> = match engine.or_else(|| found.card.entry.clone()) {
        Some(p) => vec![p],
        None => candidates.iter().filter(|c| game.file(c).is_some()).take(MAX_PROGRAMS).cloned().collect(),
    };
    for src in [Source::Bat, Source::Exe, Source::Program] {
        for p in &programs {
            let mut card = game.program_card(p, src);
            if let Some(c) = card.as_mut().filter(|_| fork) {
                (c.description, c.author, c.online, c.notes) = (None, None, None, None);
            }
            found.add(src, card, game);
        }
    }
    found
}

/// The text of the `engine.name` of the game in `folder` (what starts it, as written), when it has one of at most 1024 bytes.
pub(crate) fn engine_name(folder: &Path) -> Option<String> {
    Game { dir: folder, only: None }.engine_name()
}

/// The lines of the `launch.args` of the game in `folder` as a card keeps arguments (at most 16 of 200 characters, none empty).
pub(crate) fn launch_args(folder: &Path) -> Vec<String> {
    let text = Game { dir: folder, only: None }.read("launch.args", HEAD as usize).map(|b| String::from_utf8_lossy(&b).into_owned()).unwrap_or_default();
    text.lines().map(|l| clean(l, 200)).filter(|l| !l.is_empty()).take(16).collect()
}

/// The files a card may name: a game's folder, or one file of it when a program is read alone.
struct Game<'a> {
    dir: &'a Path,
    only: Option<&'a str>,
}

impl Game<'_> {
    /// The regular file at `rel` (`/`-separated), with its path and size; `None` for anything else, and for a path through a link (except the one
    /// file of a game that is one file).
    fn file(&self, rel: &str) -> Option<(PathBuf, u64)> {
        if let Some(only) = self.only {
            // The one file the person named: whatever it is a link to is theirs to read.
            let path = self.dir.join(only);
            return (only == rel).then(|| std::fs::metadata(&path).ok().filter(|m| m.is_file()).map(|m| (path, m.len()))).flatten();
        }
        let mut path = self.dir.to_path_buf();
        let parts: Vec<&str> = rel.split('/').collect();
        for (i, part) in parts.iter().enumerate() {
            if matches!(*part, "" | "." | "..") || part.contains(['\\', ':']) || crate::archive::device(part) {
                return None;
            }
            path.push(part);
            let meta = std::fs::symlink_metadata(&path).ok()?;
            let last = i + 1 == parts.len();
            if meta.file_type().is_symlink() || if last { !meta.is_file() } else { !meta.is_dir() } {
                return None;
            }
            if last {
                return Some((path, meta.len()));
            }
        }
        None
    }

    /// The first `cap` bytes of the file at `rel`.
    fn read(&self, rel: &str, cap: usize) -> Option<Vec<u8>> {
        let (path, _) = self.file(rel)?;
        let mut out = vec![];
        File::open(path).ok()?.take(cap as u64).read_to_end(&mut out).ok()?;
        Some(out)
    }

    /// The text of `engine.name` (trimmed), when there is one of at most 1024 bytes.
    fn engine_name(&self) -> Option<String> {
        let bytes = self.read("engine.name", 1025).filter(|b| b.len() <= 1024)?;
        String::from_utf8(bytes).ok().map(|s| s.trim().to_string())
    }

    /// What the program at `rel` says about the game as `src`: a script's header block, an `.exe`'s record or its version information.
    fn program_card(&self, rel: &str, src: Source) -> Option<Card> {
        match (crate::upload::ext(Path::new(rel)).as_str(), src) {
            ("bat" | "cmd", Source::Bat) => script_card(&self.read(rel, HEAD as usize)?),
            ("exe", Source::Exe) => record(&mut Bytes::open(&self.file(rel)?.0)?),
            ("exe", Source::Program) => version(&mut Bytes::open(&self.file(rel)?.0)?),
            _ => None,
        }
    }
}

// ---------- scripts

/// The text of a batch comment line (`REM`, `@REM` in any case, or `::`, after spaces and tabs); `None` for any other line.
fn comment_text(line: &str) -> Option<&str> {
    let l = line.trim_start_matches([' ', '\t']);
    if let Some(t) = l.strip_prefix("::") {
        return Some(t.trim_matches(SPACE));
    }
    let l = l.strip_prefix('@').unwrap_or(l);
    let (rem, text) = (l.get(..3)?, l.get(3..)?);
    (rem.eq_ignore_ascii_case("rem") && (text.is_empty() || text.starts_with([' ', '\t']))).then(|| text.trim_matches(SPACE))
}

/// The card in a script's header block: within the first 64 lines, a comment line `redengine-game`, then the comment lines right after it,
/// one `key: value` each (`notes` and `args` repeat), until the first line that is not a comment.
fn script_card(head: &[u8]) -> Option<Card> {
    let head = head.strip_prefix(BOM).unwrap_or(head);
    let lines: Vec<String> = head.split(|&b| b == b'\n').take(64).map(|l| String::from_utf8_lossy(l.strip_suffix(b"\r").unwrap_or(l)).into_owned()).collect();
    let start = lines.iter().position(|l| comment_text(l) == Some(TAG))?;
    let mut card = serde_json::Map::new();
    for text in lines[start + 1..].iter().map_while(|l| comment_text(l)) {
        let Some((key, value)) = text.split_once(':') else { continue };
        let (key, value) = (key.trim_matches(SPACE), value.trim_matches(SPACE));
        match key {
            "notes" | "args" => {
                if let Value::Array(items) = card.entry(key).or_insert_with(|| Value::Array(vec![])) {
                    items.push(value.into());
                }
            }
            "name" | "description" | "presentation" | "kind" | "author" | "online" | "entry" | "thumb" => {
                card.insert(key.into(), value.into());
            }
            _ => {}
        }
    }
    Some(Card::from_value(&Value::Object(card)))
}

// ---------- programs

fn u16_at(b: &[u8], at: usize) -> Option<u16> {
    Some(u16::from_le_bytes(b.get(at..at.checked_add(2)?)?.try_into().ok()?))
}

fn u32_at(b: &[u8], at: usize) -> Option<u32> {
    Some(u32::from_le_bytes(b.get(at..at.checked_add(4)?)?.try_into().ok()?))
}

/// The UTF-16 units of `b` up to the first NUL.
fn units(b: &[u8]) -> impl Iterator<Item = u16> + '_ {
    (0..b.len() / 2).map_while(move |i| u16_at(b, i * 2)).take_while(|&u| u != 0)
}

/// A program read at offsets: no read is longer than `MAX_READ` or reaches past the file's end.
struct Bytes<R> {
    r: R,
    len: u64,
}

impl<R: Read + Seek> Bytes<R> {
    fn new(mut r: R) -> Option<Self> {
        let len = r.seek(SeekFrom::End(0)).ok()?;
        Some(Bytes { r, len })
    }

    fn at(&mut self, off: u64, n: usize) -> Option<Vec<u8>> {
        if n > MAX_READ || off.checked_add(n as u64)? > self.len {
            return None;
        }
        self.r.seek(SeekFrom::Start(off)).ok()?;
        let mut buf = vec![0; n];
        self.r.read_exact(&mut buf).ok()?;
        Some(buf)
    }
}

impl Bytes<File> {
    fn open(path: &Path) -> Option<Self> {
        Bytes::new(File::open(path).ok()?)
    }
}

/// The length of the record that ends `end` bytes into a program (its card and the 12 bytes after it), when there is one.
fn record_len_at<R: Read + Seek>(f: &mut Bytes<R>, end: u64) -> Option<u64> {
    let tail = f.at(end.checked_sub(12)?, 12)?;
    let n = u64::from(u32_at(&tail, 0)?);
    (tail.ends_with(MAGIC) && n <= MAX_CARD as u64 && n + 12 <= end).then_some(n + 12)
}

/// The length of the record at the end of a program, when there is one.
fn record_len<R: Read + Seek>(f: &mut Bytes<R>) -> Option<u64> {
    record_len_at(f, f.len)
}

/// Where the record of a program ends: at the end of the file, or, when the program was signed after it was stamped, where the certificate table
/// starts (on a multiple of 8 bytes, so up to 7 bytes of padding come first).
fn record_end<R: Read + Seek>(f: &mut Bytes<R>) -> Option<u64> {
    if record_len(f).is_some() {
        return Some(f.len);
    }
    let &(table, size) = Pe::read(f)?.dirs.get(4)?;
    (size != 0).then(|| (0..8).find_map(|pad| u64::from(table).checked_sub(pad).filter(|&end| record_len_at(f, end).is_some()))).flatten()
}

/// The card recorded after the program's last byte (or before its certificate table): the card as JSON, its length (4 bytes, little-endian) and
/// `REDGAME1`.
fn record<R: Read + Seek>(f: &mut Bytes<R>) -> Option<Card> {
    let end = record_end(f)?;
    let n = record_len_at(f, end)?;
    Card::parse(&f.at(end - n, usize::try_from(n - 12).ok()?)?)
}

/// Put `card` after a program's last byte, replacing the record of its own it already has. Only a Windows program with nothing after its last
/// section (no installer, self-extractor or signature) is changed. This is the tool's job (`distribution/game_meta.py stamp`): the app never
/// edits a game's files.
pub fn write_record(path: &Path, card: &Card) -> Result<()> {
    let refuse = |why: &str| Error::Upload(format!("{} {why}.", path.display()));
    let line = json(card, false);
    if line.len() > MAX_CARD {
        return Err(refuse("cannot take a card over 16 KiB"));
    }
    let mut f = std::fs::OpenOptions::new().read(true).write(true).open(path)?;
    let mut b = Bytes::new(&mut f).ok_or_else(|| refuse("cannot be read"))?;
    let pe = Pe::read(&mut b).ok_or_else(|| refuse("is not a Windows program"))?;
    let end = b.len - record_len(&mut b).unwrap_or(0);
    if pe.dirs.get(4).is_some_and(|d| d.0 != 0 || d.1 != 0) {
        return Err(refuse("is signed, and a record would break the signature"));
    }
    if end < pe.end {
        return Err(refuse("is cut short"));
    }
    if end > pe.end {
        return Err(refuse("has data after its last section (an installer, a self-extracting archive or a signature)"));
    }
    f.set_len(end)?;
    f.seek(SeekFrom::Start(end))?;
    f.write_all(line.as_bytes())?;
    f.write_all(&(line.len() as u32).to_le_bytes())?;
    f.write_all(MAGIC)?;
    Ok(())
}

/// A section of a Windows program: where it is in memory, how much of it is in the file, and where.
struct Section {
    va: u32,
    size: u32,
    at: u32,
}

/// The parts of a Windows program's headers the card needs.
struct Pe {
    sections: Vec<Section>,
    /// The data directories as (address, size); the resources are the third, the signature the fifth.
    dirs: Vec<(u32, u32)>,
    /// Where the program ends in the file: the end of its headers, its last section or its symbol table and strings, the last of them.
    end: u64,
    /// The file's length.
    len: u64,
}

impl Pe {
    /// The DOS header, the PE header and the section table, each checked against the file; `None` for anything else.
    fn read<R: Read + Seek>(f: &mut Bytes<R>) -> Option<Pe> {
        let dos = f.at(0, 64)?;
        if !dos.starts_with(b"MZ") {
            return None;
        }
        let pe = u64::from(u32_at(&dos, 0x3C)?);
        if pe < 64 {
            return None;
        }
        let h = f.at(pe, 24)?;
        if !h.starts_with(b"PE\0\0") {
            return None;
        }
        let count = usize::from(u16_at(&h, 6)?);
        let (symbols, symbol_count) = (u64::from(u32_at(&h, 12)?), u64::from(u32_at(&h, 16)?));
        let opt_len = usize::from(u16_at(&h, 20)?);
        if count == 0 || count > 96 || opt_len < 64 {
            return None;
        }
        let opt = f.at(pe + 24, opt_len.min(240))?;
        let (dirs_at, count_at) = match u16_at(&opt, 0)? {
            0x10B => (96, 92),
            0x20B => (112, 108),
            _ => return None,
        };
        if opt.len() < dirs_at {
            return None;
        }
        let headers = u64::from(u32_at(&opt, 60)?);
        let n = u32_at(&opt, count_at).unwrap_or(0).min(16) as usize;
        let dirs = (0..n).map_while(|i| Some((u32_at(&opt, dirs_at + i * 8)?, u32_at(&opt, dirs_at + i * 8 + 4)?))).collect();
        let table = f.at(pe + 24 + opt_len as u64, count * 40)?;
        let sections: Vec<Section> = (0..count).filter_map(|i| Some(Section { va: u32_at(&table, i * 40 + 12)?, size: u32_at(&table, i * 40 + 16)?, at: u32_at(&table, i * 40 + 20)? })).collect();
        let mut end = sections.iter().filter(|s| s.size > 0).map(|s| u64::from(s.at) + u64::from(s.size)).fold(headers, u64::max);
        // gcc and mingw leave a symbol table and its strings after the last section: they are part of the program (a claim that reaches outside is none).
        if symbols != 0 {
            let strings = symbols + 18 * symbol_count;
            if let Some(size) = f.at(strings, 4).and_then(|t| u32_at(&t, 0)).map(u64::from).filter(|&size| size >= 4 && strings + size <= f.len) {
                end = end.max(strings + size);
            }
        }
        Some(Pe { sections, dirs, end, len: f.len })
    }

    /// Where the `len` bytes at an address in the loaded program are in the file: in the first section whose data holds them all.
    fn offset(&self, rva: u32, len: u32) -> Option<u64> {
        let at = |s: &Section| (rva >= s.va).then(|| u64::from(s.at) + u64::from(rva - s.va)).filter(|at| u64::from(rva - s.va) + u64::from(len) <= u64::from(s.size) && at + u64::from(len) <= self.len);
        self.sections.iter().find_map(at)
    }
}

/// The program's version information as a card: `ProductName` is the name, `Comments` (else `FileDescription`) the description.
fn version<R: Read + Seek>(f: &mut Bytes<R>) -> Option<Card> {
    let pe = Pe::read(f)?;
    let &(rva, size) = pe.dirs.get(2)?;
    let data = version_resource(f, &pe, pe.offset(rva, 16)?, u64::from(size))?;
    strings(&data)
}

/// Set in the offset of a resource directory's entry that leads to another directory rather than to data.
const SUBDIRECTORY: u32 = 0x8000_0000;

/// The bytes of the program's `RT_VERSION` (16) resource: down the resource tree (type, name, language), taking the first entry after the type.
/// `base` is where the resources start in the file and `size` how far they reach. A directory that holds more than it says, more than 4096
/// entries or more than the resources do, a tree of any other shape, and a data entry that points outside, all read as nothing.
fn version_resource<R: Read + Seek>(f: &mut Bytes<R>, pe: &Pe, base: u64, size: u64) -> Option<Vec<u8>> {
    // The entries of the directory `off` bytes in: how many are named (they come first), and each as (id or name, offset of the data or of the
    // directory below, which has `SUBDIRECTORY` set).
    fn directory<R: Read + Seek>(f: &mut Bytes<R>, base: u64, size: u64, off: u32) -> Option<(usize, Vec<(u32, u32)>)> {
        let off = u64::from(off);
        let head = f.at(base.checked_add(off)?, 16)?;
        let named = usize::from(u16_at(&head, 12)?);
        let n = named + usize::from(u16_at(&head, 14)?);
        if n > 4096 || off + 16 + n as u64 * 8 > size {
            return None;
        }
        let entries = f.at(base + off + 16, n * 8)?;
        Some((named, (0..n).filter_map(|i| Some((u32_at(&entries, i * 8)?, u32_at(&entries, i * 8 + 4)?))).collect()))
    }
    let (named, types) = directory(f, base, size, 0)?;
    let names = types.iter().skip(named).find(|e| e.0 == 16 && e.1 & SUBDIRECTORY != 0)?.1;
    let languages = directory(f, base, size, names & !SUBDIRECTORY)?.1.first().map(|e| e.1).filter(|e| e & SUBDIRECTORY != 0)?;
    let data = directory(f, base, size, languages & !SUBDIRECTORY)?.1.first().map(|e| e.1).filter(|&e| e & SUBDIRECTORY == 0 && u64::from(e) + 16 <= size)?;
    let leaf = f.at(base + u64::from(data), 16)?;
    let (rva, len) = (u32_at(&leaf, 0)?, u32_at(&leaf, 4)?);
    if !(6..=MAX_VERSION as u32).contains(&len) {
        return None;
    }
    f.at(pe.offset(rva, len)?, len as usize)
}

/// One block of version information: `wLength`, `wValueLength` and `wType` (2 bytes each), the key in UTF-16 up to its NUL, then the value and
/// the child blocks each on a 4-byte boundary.
struct Block<'a> {
    key: String,
    /// The value read as `wValueLength` UTF-16 words, which is what a string is whatever `wType` says.
    words: &'a [u8],
    children: &'a [u8],
    next: usize,
}

fn block(data: &[u8], at: usize) -> Option<Block<'_>> {
    let len = usize::from(u16_at(data, at)?);
    let value_len = usize::from(u16_at(data, at.checked_add(2)?)?);
    let text = u16_at(data, at.checked_add(4)?)? == 1;
    let end = at.checked_add(len).filter(|&e| len >= 6 && e <= data.len())?;
    let body = data.get(at + 6..end)?;
    let key: Vec<u16> = units(body).take(65).collect();
    if key.len() > 64 || key.len() * 2 + 2 > body.len() {
        return None;
    }
    let value_at = ((at + 6 + key.len() * 2 + 2 + 3) & !3).min(end);
    let value_end = value_at.saturating_add(if text { value_len * 2 } else { value_len }).min(end);
    let children_at = ((value_end + 3) & !3).min(end);
    let words_end = value_at.saturating_add(value_len * 2).min(end);
    Some(Block { key: String::from_utf16_lossy(&key), words: data.get(value_at..words_end)?, children: data.get(children_at..end)?, next: (end + 3) & !3 })
}

/// The blocks one after another in `data` (at most 256).
fn blocks(data: &[u8]) -> impl Iterator<Item = Block<'_>> {
    std::iter::successors(block(data, 0), move |b| block(data, b.next)).take(256)
}

/// `ProductName`, `Comments` and `FileDescription` of the first string table of a `VS_VERSION_INFO` block, as a card. Values that say nothing
/// (empty, `application`, `game`, `app`) are ignored, and so is a `FileDescription` equal to the name.
fn strings(data: &[u8]) -> Option<Card> {
    let root = block(data, 0).filter(|b| b.key == "VS_VERSION_INFO")?;
    let info = blocks(root.children).find(|b| b.key == "StringFileInfo")?;
    let table = blocks(info.children).next()?;
    let (mut product, mut comments, mut description) = (None, None, None);
    for s in blocks(table.children) {
        let slot = match s.key.as_str() {
            "ProductName" => &mut product,
            "Comments" => &mut comments,
            "FileDescription" => &mut description,
            _ => continue,
        };
        slot.get_or_insert_with(|| String::from_utf16_lossy(&units(s.words).collect::<Vec<_>>()));
    }
    let say = |v: Option<String>| v.map(|s| clean(&s, usize::MAX)).filter(|s| !s.is_empty() && !["application", "game", "app"].iter().any(|j| s.eq_ignore_ascii_case(j)));
    let name = say(product);
    let description = say(comments).or_else(|| say(description).filter(|d| !name.as_ref().is_some_and(|n| n.to_lowercase() == d.to_lowercase())));
    Some(Card { name: name.map(|n| clean(&n, 60)), description: description.map(|d| clean(&d, 400)), ..Card::default() })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    fn card(json: &str) -> Card {
        Card::parse(json.as_bytes()).expect("a card")
    }

    // ---------- fixtures: a Windows program built byte by byte

    const OPT: usize = 0x58;
    const DIRS: usize = OPT + 112;
    const SECTIONS: usize = OPT + 240;

    fn put(f: &mut [u8], at: usize, bytes: &[u8]) {
        f[at..at + bytes.len()].copy_from_slice(bytes);
    }

    fn pad(v: &mut Vec<u8>) {
        v.resize(v.len().next_multiple_of(4), 0);
    }

    fn utf16(s: &str) -> Vec<u8> {
        s.encode_utf16().chain([0]).flat_map(u16::to_le_bytes).collect()
    }

    /// A block of version information (length, value length, type, key, value, children), padded to a 4-byte boundary after it.
    fn vblock(key: &str, text: bool, value: &[u8], value_len: usize, children: &[u8]) -> Vec<u8> {
        let mut b = vec![0, 0];
        b.extend((value_len as u16).to_le_bytes());
        b.extend(u16::from(text).to_le_bytes());
        b.extend(utf16(key));
        pad(&mut b);
        b.extend(value);
        pad(&mut b);
        b.extend(children);
        let len = b.len() as u16;
        put(&mut b, 0, &len.to_le_bytes());
        pad(&mut b);
        b
    }

    /// A `VS_VERSION_INFO` resource with one string table per slice of `tables`, then a `VarFileInfo` as real programs have.
    fn info(tables: &[&[(&str, &str)]]) -> Vec<u8> {
        let tables: Vec<u8> = tables
            .iter()
            .flat_map(|t| {
                let strings: Vec<u8> = t.iter().flat_map(|(k, v)| vblock(k, true, &utf16(v), v.encode_utf16().count() + 1, &[])).collect();
                vblock("040904B0", true, &[], 0, &strings)
            })
            .collect();
        let string_info = vblock("StringFileInfo", true, &[], 0, &tables);
        let var = vblock("VarFileInfo", true, &[], 0, &vblock("Translation", false, &[9, 4, 0xB0, 4], 4, &[]));
        let mut fixed = vec![0u8; 52];
        put(&mut fixed, 0, &0xFEEF_04BDu32.to_le_bytes());
        vblock("VS_VERSION_INFO", false, &fixed, 52, &[string_info, var].concat())
    }

    fn strings_info(strings: &[(&str, &str)]) -> Vec<u8> {
        info(&[strings])
    }

    fn section(f: &mut [u8], at: usize, name: &str, va: u32, size: usize, ptr: u32) {
        put(f, at, name.as_bytes());
        put(f, at + 8, &(size as u32).to_le_bytes());
        put(f, at + 12, &va.to_le_bytes());
        put(f, at + 16, &(size as u32).to_le_bytes());
        put(f, at + 20, &ptr.to_le_bytes());
    }

    /// A Windows program as a linker lays it out: headers (0x400 bytes), `.text`, and with `version` a `.rsrc` holding it as the version
    /// resource (type 16, name 1, language 0x409). Its last byte is the last byte of the last section.
    fn program(version: Option<&[u8]>) -> Vec<u8> {
        let mut tree = vec![];
        if let Some(v) = version {
            let table = |id: u32, to: u32| {
                let mut t = vec![0u8; 14];
                t.extend(1u16.to_le_bytes());
                t.extend(id.to_le_bytes());
                t.extend(to.to_le_bytes());
                t
            };
            tree = [table(16, SUBDIRECTORY | 24), table(1, SUBDIRECTORY | 48), table(0x409, 72)].concat();
            tree.extend(0x2058u32.to_le_bytes());
            tree.extend((v.len() as u32).to_le_bytes());
            tree.extend([0u8; 8]);
            tree.extend(v);
        }
        let raw = tree.len().div_ceil(0x200) * 0x200;
        let mut f = vec![0u8; 0x400];
        put(&mut f, 0, b"MZ");
        put(&mut f, 0x3C, &0x40u32.to_le_bytes());
        put(&mut f, 0x40, b"PE\0\0");
        put(&mut f, 0x46, &(if version.is_some() { 2u16 } else { 1 }).to_le_bytes());
        put(&mut f, 0x54, &240u16.to_le_bytes());
        put(&mut f, OPT, &0x20Bu16.to_le_bytes());
        put(&mut f, OPT + 108, &16u32.to_le_bytes());
        section(&mut f, SECTIONS, ".text", 0x1000, 0x200, 0x400);
        if version.is_some() {
            put(&mut f, DIRS + 16, &0x2000u32.to_le_bytes());
            put(&mut f, DIRS + 20, &(tree.len() as u32).to_le_bytes());
            section(&mut f, SECTIONS + 40, ".rsrc", 0x2000, raw, 0x600);
        }
        f.extend([0x90; 0x200]);
        f.extend(&tree);
        f.resize(0x600 + raw, 0);
        f
    }

    /// A record as the tool appends it: the card, its length, `REDGAME1`.
    fn trailer(json: &str) -> Vec<u8> {
        [json.as_bytes(), &(json.len() as u32).to_le_bytes(), MAGIC].concat()
    }

    fn version_of(bytes: Vec<u8>) -> Option<Card> {
        version(&mut Bytes::new(Cursor::new(bytes)).unwrap())
    }

    fn record_of(bytes: Vec<u8>) -> Option<Card> {
        record(&mut Bytes::new(Cursor::new(bytes)).unwrap())
    }

    /// A game folder with these files.
    fn game(files: &[(&str, &[u8])]) -> tempfile::TempDir {
        let dir = tempfile::tempdir().unwrap();
        for (name, data) in files {
            let path = dir.path().join(name);
            std::fs::create_dir_all(path.parent().unwrap()).unwrap();
            std::fs::write(path, data).unwrap();
        }
        dir
    }

    fn find(dir: &Path, zip: Option<Card>) -> Found {
        read_folder(dir, zip, &crate::upload::candidates(dir), false)
    }

    fn zip_of(path: &Path, files: &[(&str, &[u8])], comment: &[u8]) {
        let mut z = zip::ZipWriter::new(File::create(path).unwrap());
        for (name, data) in files {
            z.start_file(*name, zip::write::SimpleFileOptions::default()).unwrap();
            z.write_all(data).unwrap();
        }
        z.set_raw_comment(comment.into());
        z.finish().unwrap();
    }

    fn from(pairs: &[(&'static str, Source)]) -> BTreeMap<&'static str, Source> {
        pairs.iter().copied().collect()
    }

    // ---------- the card

    #[test]
    fn strings_are_cleaned_the_way_the_spec_says() {
        assert_eq!(clean("  a \t b\n\n c  ", 60), "a b c");
        assert_eq!(clean("a\u{7}b\u{0}c\u{7f}d\u{9b}e", 60), "abcde");
        assert_eq!(clean("a \u{7} b", 60), "a b");
        assert_eq!(clean("a\u{202E}b\u{202A}c\u{2066}d\u{2069}e\u{2068}", 60), "abcde");
        assert_eq!(clean("a\u{a0}b\u{2003}c", 60), "a b c");
        assert_eq!(clean(&"x".repeat(100), 60), "x".repeat(60));
        assert_eq!(clean(&"é🚀".repeat(100), 60).chars().count(), 60, "cut in characters, never in the middle of one");
        assert_eq!(clean("aaa bbb", 4), "aaa", "a cut never leaves white space at the end");
        assert_eq!(clean("   ", 10), "");
    }

    #[test]
    fn every_field_is_read_cleaned_and_cut_to_its_limit() {
        let long = "w ".repeat(300);
        let args: Vec<String> = (0..20).map(|i| format!("--a{i}")).collect();
        let notes: Vec<String> = (0..12).map(|i| format!("note {i}")).collect();
        let c = card(
            &serde_json::json!({"schema": 9, "name": format!("  {} ", "n".repeat(80)), "description": long, "presentation": "hybrid", "author": "ai", "online": "o".repeat(300),
                "entry": "bin/Game.exe", "args": args, "thumb": "shots/a.png", "notes": notes, "forked_from": {"slug": "snake", "version": 3}, "unknown": [1, 2]})
            .to_string(),
        );
        assert_eq!(c.name.as_deref(), Some("n".repeat(60).as_str()));
        assert_eq!(c.description.as_ref().unwrap().chars().count(), 399, "400 characters, the last one a space that is trimmed");
        assert_eq!((c.presentation.as_deref(), c.author.as_deref()), (Some("hybrid"), Some("ai")));
        assert_eq!(c.online.as_ref().unwrap().len(), 200);
        assert_eq!((c.entry.as_deref(), c.thumb.as_deref()), (Some("bin/Game.exe"), Some("shots/a.png")));
        assert_eq!(c.args.as_ref().unwrap().len(), 16);
        assert_eq!(c.notes.as_ref().unwrap().len(), 10);
        assert_eq!(c.forked_from, Some(Parent { slug: "snake".into(), version: 3 }));
        let items = card(&serde_json::json!({"args": ["a", "", "  ", "b".repeat(300)], "notes": ["x", 5]}).to_string());
        assert_eq!(items.args, Some(vec!["a".to_string(), "b".repeat(200)]), "an item empty once cleaned is skipped, the rest cut to 200");
        assert_eq!(items.notes, None, "a list holding anything but strings is of the wrong type");
        assert_eq!(card(r#"{"kind": "2d"}"#).presentation.as_deref(), Some("2d"), "`kind` is a synonym");
        assert_eq!(card(r#"{"kind": "2d", "presentation": "3d"}"#).presentation.as_deref(), Some("3d"));
        assert_eq!(card(r#"{"name": "A\u0007\u202eB\n C"}"#).name.as_deref(), Some("AB C"));
        assert_eq!(card("{}"), Card::default());
    }

    #[test]
    fn a_value_of_the_wrong_type_or_an_unusable_one_is_simply_not_found() {
        let bad = serde_json::json!({
            "name": 5, "description": ["x"], "presentation": "4d", "author": "robot", "online": {"a": 1}, "entry": "../x.exe", "args": "x", "thumb": "a.gif",
            "notes": {"a": 1}, "forked_from": "snake"
        });
        assert_eq!(card(&bad.to_string()), Card::default());
        for entry in ["/x.exe", "C:/x.exe", "C:x.exe", "a\\b.exe", "x.txt", "bin/", "a/../b.exe", "..", "x.exe:stream", ""] {
            assert_eq!(card(&serde_json::json!({ "entry": entry }).to_string()).entry, None, "{entry:?}");
        }
        for thumb in ["a.gif", "/a.png", "../a.png", "a\\b.png", "a.png:x", "shots", "a.PNG.txt"] {
            assert_eq!(card(&serde_json::json!({ "thumb": thumb }).to_string()).thumb, None, "{thumb:?}");
        }
        assert_eq!(card(r#"{"entry": " bin/Game.EXE "}"#).entry.as_deref(), Some("bin/Game.EXE"), "an extension is read in any case");
        for entry in ["./Game.exe", "bin//Game.exe", "bin/./Game.exe", &format!("{}.exe", "a/".repeat(130))] {
            assert_eq!(card(&serde_json::json!({ "entry": entry }).to_string()).entry, None, "{entry:?}");
        }
        for forked in [
            serde_json::json!({"slug": "Bad Slug", "version": 1}),
            serde_json::json!({"slug": "a--b", "version": 1}),
            serde_json::json!({"slug": "-a", "version": 1}),
            serde_json::json!({"slug": "a-", "version": 1}),
            serde_json::json!({"slug": "", "version": 1}),
            serde_json::json!({"slug": "snake", "version": 0}),
            serde_json::json!({"slug": "snake", "version": -1}),
            serde_json::json!({"slug": "snake", "version": "3"}),
            serde_json::json!({"slug": "snake", "version": 2.5}),
            serde_json::json!({"slug": "snake"}),
            serde_json::json!({"version": 2}),
            serde_json::json!({"slug": 5, "version": 2}),
        ] {
            assert_eq!(card(&serde_json::json!({ "forked_from": forked }).to_string()).forked_from, None, "{forked}");
        }
        assert!(card(r#"{"forked_from": {"slug": "snake-2d", "version": 1}}"#).forked_from.is_some());
    }

    #[test]
    fn a_card_that_is_too_big_or_not_a_json_object_is_ignored_whole() {
        let sized = |n: usize| format!(r#"{{"name": "x"{}}}"#, " ".repeat(n - r#"{"name": "x"}"#.len()));
        assert!(Card::parse(sized(MAX_CARD).as_bytes()).is_some());
        assert!(Card::parse(sized(MAX_CARD + 1).as_bytes()).is_none(), "16 KiB and one byte");
        for text in ["[1]", "null", "\"x\"", "5", "", "name: x", "{\"name\": \"x\"", "{\"name\": \"x\"} trailing"] {
            assert!(Card::parse(text.as_bytes()).is_none(), "{text:?}");
        }
        assert!(Card::parse(b"{\"name\": \"\xff\xfe\"}").is_none(), "not UTF-8");
        assert_eq!(Card::parse(b"\xEF\xBB\xBF{\"name\": \"x\"}").unwrap().name.as_deref(), Some("x"), "an editor's byte order mark");
        assert!(Card::parse("[".repeat(10_000).as_bytes()).is_none(), "deep nesting is refused, not recursed into");
        let deep = |n: usize| format!(r#"{{"name": "x", "deep": {}1{}}}"#, r#"{"a": "#.repeat(n), "}".repeat(n));
        assert!(Card::parse(deep(100).as_bytes()).is_some());
        assert!(Card::parse(deep(126).as_bytes()).is_some(), "127 levels, the card's own object the first");
        assert!(Card::parse(deep(127).as_bytes()).is_none(), "128 levels");
        assert!(Card::parse(deep(1000).as_bytes()).is_none());
        // A number that does not fit a 64-bit float makes the whole card unreadable (the command-line reader agrees); one that does, even a tiny or
        // huge one, is just a number in a field nobody reads.
        for (n, ok) in [("1.7976931348623157e308", true), ("-1e308", true), ("1e-999999", true), ("-0", true), ("18446744073709551616", true), ("1e999999", false), ("1.8e308", false), ("-1e999999", false)] {
            assert_eq!(Card::parse(format!(r#"{{"name": "x", "n": {n}}}"#).as_bytes()).is_some(), ok, "{n}");
        }
        assert!(Card::parse(format!(r#"{{"name": "x", "n": 1{}}}"#, "0".repeat(308)).as_bytes()).is_some(), "309 digits, 1e308");
        assert!(Card::parse(format!(r#"{{"name": "x", "n": 1{}}}"#, "0".repeat(309)).as_bytes()).is_none(), "310 digits");
        let many = format!(r#"{{"args": [{}], "notes": [{}], "name": "x"}}"#, vec!["\"a\""; 1900].join(","), vec!["\"b\""; 1900].join(","));
        let c = card(&many);
        assert_eq!((c.args.unwrap().len(), c.notes.unwrap().len()), (16, 10));
        assert_eq!(card(r#"{"name": "a", "name": "b"}"#).name.as_deref(), Some("b"), "the last of a repeated key, as everywhere");
    }

    #[test]
    fn a_card_is_written_pretty_with_its_schema_and_without_notes_and_reads_back() {
        let dir = tempfile::tempdir().unwrap();
        let c = Card {
            name: Some("Star  Miner".into()),
            description: Some("Mine asteroids.".into()),
            presentation: Some("3d".into()),
            author: Some("ai".into()),
            entry: Some("bin\\Game.exe".into()),
            args: Some(vec!["--fast".into()]),
            notes: Some(vec!["First release.".into()]),
            forked_from: Some(Parent { slug: "snake".into(), version: 2 }),
            ..Card::default()
        };
        write_card_file(dir.path(), &c).unwrap();
        let text = std::fs::read_to_string(dir.path().join(FILE)).unwrap();
        assert!(text.starts_with("{\n  \"schema\": 1,\n  \"name\": \"Star Miner\",\n"), "{text}");
        assert!(text.ends_with("}\n") && !text.contains("notes") && !text.contains("online"), "{text}");
        let back = read_card_file(dir.path()).unwrap();
        assert_eq!((back.name.as_deref(), back.entry.as_deref()), (Some("Star Miner"), None), "an entry with a backslash is not a card's entry");
        assert_eq!((back.args.clone(), back.notes.clone(), back.forked_from.clone()), (c.args.clone(), None, c.forked_from.clone()));
        let line = comment(&c);
        assert!(line.starts_with("redengine-game {\"schema\":1,\"name\":\"Star Miner\"") && !line.contains('\n'), "{line}");
        assert_eq!(Card::parse(line.strip_prefix("redengine-game ").unwrap().as_bytes()), Some(back));
    }

    // ---------- the places a card lives

    #[test]
    fn the_answer_has_the_shape_the_window_and_the_command_line_share() {
        let dir = game(&[("redengine-game.json", br#"{"name": "A", "args": ["-x"], "forked_from": {"slug": "snake", "version": 2}}"#), ("g.bat", b"x")]);
        let f = read_path(dir.path());
        assert_eq!(
            serde_json::to_value(&f).unwrap(),
            serde_json::json!({"card": {"name": "A", "args": ["-x"], "forked_from": {"slug": "snake", "version": 2}}, "from": {"name": "card", "args": "card", "forked_from": "card"}})
        );
        assert_eq!(serde_json::to_string(&Found::default()).unwrap(), r#"{"card":{},"from":{}}"#);
    }

    #[test]
    fn the_card_file_is_read_at_the_root_and_in_a_single_top_folder() {
        let dir = game(&[("Quest/redengine-game.json", br#"{"name": "Text Quest", "description": "A tiny adventure."}"#), ("Quest/quest.bat", b"@echo off")]);
        let f = read_path(dir.path());
        assert_eq!(f.card.name.as_deref(), Some("Text Quest"));
        assert_eq!(f.from, from(&[("name", Source::Card), ("description", Source::Card)]));
        let nested = game(&[("redengine-game.json", br#"{"name": "Root"}"#), ("sub/redengine-game.json", br#"{"name": "Deeper"}"#), ("sub/g.bat", b"x")]);
        assert_eq!(read_path(nested.path()).card.name.as_deref(), Some("Root"));
        assert_eq!(read_path(&nested.path().join("sub")).card.name.as_deref(), Some("Deeper"));
        let big = game(&[("redengine-game.json", &[b' '; MAX_CARD + 1][..]), ("g.bat", b"x")]);
        assert_eq!(read_path(big.path()), Found::default(), "a card file over 16 KiB is ignored");
    }

    #[test]
    fn a_zip_comment_is_read_before_unpacking_and_ranks_below_the_card_file() {
        let dir = tempfile::tempdir().unwrap();
        let comment = br#"redengine-game {"schema":1,"name":"Zip name","description":"From the comment.","entry":"Game/g.bat"}"#;
        let zip = dir.path().join("g.zip");
        zip_of(&zip, &[("Game/g.bat", b"@echo off"), ("Game/readme.txt", b"r")], comment);
        assert_eq!(zip_comment(&zip).unwrap().name.as_deref(), Some("Zip name"));
        let f = read_path(&zip);
        assert_eq!((f.card.name.as_deref(), f.card.entry), (Some("Zip name"), None), "the entry names no file inside the top folder");
        assert_eq!(f.from, from(&[("name", Source::Zip), ("description", Source::Zip)]));
        zip_of(&zip, &[("Game/g.bat", b"@echo off"), ("Game/redengine-game.json", br#"{"name": "File name", "entry": "g.bat"}"#)], comment);
        let f = read_path(&zip);
        assert_eq!((f.card.name.as_deref(), f.card.description.as_deref(), f.card.entry.as_deref()), (Some("File name"), Some("From the comment."), Some("g.bat")));
        assert_eq!(f.from, from(&[("name", Source::Card), ("description", Source::Zip), ("entry", Source::Card)]));
    }

    #[test]
    fn a_hostile_zip_comment_is_ignored() {
        let dir = tempfile::tempdir().unwrap();
        let zip = dir.path().join("g.zip");
        let padded = format!("redengine-game {{\"name\": \"x\"}}{}", " ".repeat(40_000));
        let too_big = format!("redengine-game {{\"name\": \"x\"{}}}", " ".repeat(20_000));
        let tail = format!("redengine-game {{\"name\": \"x\"}}{}", " ".repeat(3));
        for (text, ok) in [
            (b"redengine-game{\"name\": \"x\"}".to_vec(), false),
            (b"redengine-gamex {\"name\": \"x\"}".to_vec(), false),
            (b"Redengine-game {\"name\": \"x\"}".to_vec(), false),
            (b"redengine-game ".to_vec(), false),
            (b"redengine-game [1]".to_vec(), false),
            (b"redengine-game {\"name\": \"\xff\"}".to_vec(), false),
            (vec![b'a'; 65_535], false),
            (too_big.into_bytes(), false),
            (padded.into_bytes(), true),
            (b"  redengine-game {\"name\": \"x\"}".to_vec(), true),
            (b"redengine-game \t {\"name\": \"x\"}".to_vec(), true),
            (tail.into_bytes(), true),
        ] {
            zip_of(&zip, &[("g.bat", b"x")], &text);
            assert_eq!(zip_comment(&zip).is_some(), ok, "{}", String::from_utf8_lossy(&text[..text.len().min(40)]));
        }
        std::fs::write(&zip, b"PK\x03\x04 not really a zip").unwrap();
        assert_eq!(zip_comment(&zip), None);
        assert_eq!(read_path(&zip), Found::default());
        zip_of(&zip, &[("../evil-card-test.bat", b"x"), ("/abs-card-test.bat", b"x"), ("a//b-card-test.bat", b"x"), ("Quest.bat", b"@echo off")], b"redengine-game {\"name\": \"x\", \"entry\": \"Quest.bat\"}");
        let f = read_path(&zip);
        assert_eq!((f.card.name.as_deref(), f.card.entry.as_deref()), (Some("x"), Some("Quest.bat")), "a member with an unsafe name is left out, the rest is read");
        assert!(!std::env::temp_dir().join("evil-card-test.bat").exists() && !Path::new("/abs-card-test.bat").exists());
        let mut z = zip::ZipWriter::new(File::create(&zip).unwrap());
        z.start_file("Game.exe", zip::write::SimpleFileOptions::default()).unwrap();
        z.write_all(b"MZ").unwrap();
        z.add_symlink("l.exe", "Game.exe", zip::write::SimpleFileOptions::default()).unwrap();
        z.set_comment("redengine-game {\"entry\": \"l.exe\", \"name\": \"x\"}");
        z.finish().unwrap();
        let f = read_path(&zip);
        assert_eq!((f.card.entry, f.card.name.as_deref()), (None, Some("x")), "a link inside a ZIP is not a file");
    }

    fn header(lines: &[&str], eol: &str) -> Vec<u8> {
        lines.iter().flat_map(|l| format!("{l}{eol}").into_bytes()).collect()
    }

    #[test]
    fn a_script_header_block_is_read_whatever_the_line_ends() {
        let lines = [
            "@echo off", "REM redengine-game", "REM name: Text Quest", "REM description: A tiny text adventure about a lost key.", "REM presentation: 2d", "REM author: ai",
            "REM online: Co-op: two players", "REM entry: quest.bat", "REM thumb: shot.png", "REM notes: First release.", "REM notes: Second line.", "REM args: --fast", "REM args: --windowed",
            "echo Welcome...",
        ];
        let want = card(
            r#"{"name": "Text Quest", "description": "A tiny text adventure about a lost key.", "presentation": "2d", "author": "ai", "online": "Co-op: two players",
            "entry": "quest.bat", "thumb": "shot.png", "notes": ["First release.", "Second line."], "args": ["--fast", "--windowed"]}"#,
        );
        for eol in ["\r\n", "\n"] {
            assert_eq!(script_card(&header(&lines, eol)), Some(want.clone()), "{eol:?}");
        }
        let with_bom = [BOM.to_vec(), header(&lines[1..], "\r\n")].concat();
        assert_eq!(script_card(&with_bom), Some(want.clone()), "a byte order mark first");
        let kinds = header(&["::redengine-game", ":: kind: 3d", "@rem  name: Q", "@REM description:  two   words ", "Rem author: human"], "\r\n");
        let c = script_card(&kinds).unwrap();
        assert_eq!((c.presentation.as_deref(), c.name.as_deref(), c.description.as_deref(), c.author.as_deref()), (Some("3d"), Some("Q"), Some("two words"), Some("human")));
    }

    #[test]
    fn a_script_header_block_ends_where_the_spec_says() {
        assert_eq!(script_card(&header(&["REM redengine-game", "REM name: A", "", "REM description: after a blank line"], "\r\n")).unwrap(), card(r#"{"name": "A"}"#));
        assert_eq!(script_card(&header(&["REM redengine-game", "REM name: A", "echo hi", "REM description: after code"], "\n")).unwrap(), card(r#"{"name": "A"}"#));
        assert_eq!(script_card(&header(&["REM redengine-game", "REM nonsense", "REM unknown: x", "REM", "REM name: A"], "\n")).unwrap(), card(r#"{"name": "A"}"#), "other comments do not end it");
        assert_eq!(script_card(&header(&["REM redengine-game  ", "REM name: A"], "\n")).unwrap().name.as_deref(), Some("A"));
        assert_eq!(script_card(&header(&["REM name: A", "REM redengine-gamer", "REM redengine-game: x"], "\n")), None);
        assert_eq!(script_card(&header(&["REM Redengine-Game", "REM name: A"], "\n")), None, "the tag is exact");
        assert_eq!(script_card(&header(&["REM name: A"], "\n")), None, "no tag, no card");
        assert_eq!(script_card(&header(&["REM redengine-game", "REM name: first", "REM name: second"], "\n")).unwrap().name.as_deref(), Some("second"));
        let at = |n: usize, extra: &str| {
            let mut lines = vec!["echo"; n - 1];
            lines.push("REM redengine-game");
            lines.push(extra);
            script_card(&header(&lines, "\n"))
        };
        assert_eq!(at(63, "REM name: A").unwrap().name.as_deref(), Some("A"), "the tag on line 63 and the name on line 64");
        assert_eq!(at(64, "REM name: A").unwrap().name, None, "the tag on line 64 and nothing after it inside the 64 lines");
        assert_eq!(at(65, "REM name: A"), None, "the tag on line 65 is not looked for");
        assert_eq!(script_card(b""), None);
    }

    #[test]
    fn a_script_that_is_hostile_costs_nothing() {
        assert_eq!(script_card(&vec![b'x'; 5_000_000]), None);
        assert_eq!(script_card(&vec![b'\n'; 5_000_000]), None);
        let mut lines = vec![b"REM redengine-game\n".to_vec()];
        lines.extend((0..100_000).map(|i| format!("REM notes: n{i}\n").into_bytes()));
        let c = script_card(&lines.concat()).unwrap();
        assert_eq!(c.notes.unwrap().len(), 10, "at most 64 lines are read and 10 notes kept");
        let c = script_card(b"REM redengine-game\nREM name: caf\xe9 \xff\xfe bar\nREM description: ok\n").unwrap();
        assert!(c.name.unwrap().starts_with("caf"), "invalid UTF-8 is replaced, not fatal");
        let dir = game(&[("g.bat", &[b"REM redengine-game\r\nREM name: Big\r\n".to_vec(), vec![b'x'; 3_000_000]].concat())]);
        assert_eq!(find(dir.path(), None).card.name.as_deref(), Some("Big"));
    }

    #[test]
    fn an_exe_record_is_read_from_its_last_twelve_bytes() {
        let json = r#"{"schema":1,"name":"Star Miner","description":"Mine asteroids."}"#;
        let exe = [program(None), trailer(json)].concat();
        assert_eq!(record_of(exe).unwrap().name.as_deref(), Some("Star Miner"));
        assert_eq!(record_of([b"MZ not even a program".to_vec(), trailer(json)].concat()).unwrap().description.as_deref(), Some("Mine asteroids."), "reading never needs a whole program");
        let at_the_limit = format!(r#"{{"name": "x"{}}}"#, " ".repeat(MAX_CARD - r#"{"name": "x"}"#.len()));
        assert!(record_of(trailer(&at_the_limit)).is_some());
        assert!(record_of(trailer(&format!("{at_the_limit} "))).is_none(), "the length must fit in 16 KiB");
        let mut lying = trailer(json);
        let n = lying.len();
        put(&mut lying, n - 12, &(json.len() as u32 + 1).to_le_bytes());
        assert!(record_of(lying).is_none(), "a length that reaches before the file");
        let mut lying = [b"abc".to_vec(), trailer(json)].concat();
        let n = lying.len();
        put(&mut lying, n - 12, &u32::MAX.to_le_bytes());
        assert!(record_of(lying).is_none());
        let mut lying = trailer(json);
        let n = lying.len();
        put(&mut lying, n - 12, &(json.len() as u32 - 1).to_le_bytes());
        assert!(record_of(lying).is_none(), "the bytes it points at are not a card");
        assert!(record_of(trailer("[1, 2]")).is_none());
        assert!(record_of(trailer("{\"name\": \"\u{ff}")).is_none());
        let mut wrong = trailer(json);
        let n = wrong.len();
        wrong[n - 1] = b'2';
        assert!(record_of(wrong).is_none());
        for short in [&b""[..], b"REDGAME1", b"\0\0\0\0REDGAME1", b"MZ"] {
            assert!(record_of(short.to_vec()).is_none());
        }
    }

    #[test]
    fn a_record_is_written_replaced_and_refused_where_it_would_do_harm() {
        let dir = tempfile::tempdir().unwrap();
        let exe = dir.path().join("Game.exe");
        let plain = program(Some(&strings_info(&[("ProductName", "Program name")])));
        std::fs::write(&exe, &plain).unwrap();
        write_record(&exe, &card(r#"{"name": "First", "notes": ["gone"]}"#)).unwrap();
        let first = std::fs::read(&exe).unwrap();
        assert_eq!(&first[..plain.len()], &plain[..], "the program is not changed, only followed");
        assert!(first.ends_with(MAGIC) && first.len() > plain.len());
        let f = read_path(&exe);
        assert_eq!((f.card.name.as_deref(), f.card.notes), (Some("First"), None));
        assert_eq!(f.from, from(&[("name", Source::Exe)]));
        write_record(&exe, &card(r#"{"name": "Second", "description": "Longer than the first, so the record changes size.", "author": "ai"}"#)).unwrap();
        let second = std::fs::read(&exe).unwrap();
        assert_eq!(&second[..plain.len()], &plain[..]);
        assert_eq!(second.windows(8).filter(|w| *w == MAGIC).count(), 1, "its own record is replaced, not stacked");
        let f = read_path(&exe);
        assert_eq!((f.card.name.as_deref(), f.card.author.as_deref()), (Some("Second"), Some("ai")));
        assert_eq!(f.from, from(&[("name", Source::Exe), ("description", Source::Exe), ("author", Source::Exe)]));
        // Not a Windows program, cut short, an installer's overlay, a signature, or an overlay under a record of its own: refused and untouched.
        let signed = {
            let mut p = program(None);
            put(&mut p, DIRS + 32, &0x600u32.to_le_bytes());
            put(&mut p, DIRS + 36, &8u32.to_le_bytes());
            [p, vec![0; 8]].concat()
        };
        let cut = plain[..plain.len() - 1].to_vec();
        let overlay = [plain.clone(), b"installer payload".to_vec()].concat();
        let overlay_and_record = [overlay.clone(), trailer(r#"{"name": "x"}"#)].concat();
        for (what, bytes) in [("text", b"hello".to_vec()), ("empty", vec![]), ("cut", cut), ("overlay", overlay), ("signed", signed), ("overlay and record", overlay_and_record), ("dos only", b"MZ".repeat(40))] {
            std::fs::write(&exe, &bytes).unwrap();
            assert!(write_record(&exe, &card(r#"{"name": "x"}"#)).is_err(), "{what}");
            assert_eq!(std::fs::read(&exe).unwrap(), bytes, "{what}: untouched");
        }
        assert!(write_record(&dir.path().join("missing.exe"), &card("{}")).is_err());
    }

    #[test]
    fn version_information_names_the_game_when_nothing_else_does() {
        let of = |strings: &[(&str, &str)]| version_of(program(Some(&strings_info(strings)))).unwrap();
        let c = of(&[("CompanyName", "Acme"), ("FileDescription", "Star Miner game"), ("ProductName", "Star Miner"), ("Comments", "Mine asteroids, dodge pirates.")]);
        assert_eq!((c.name.as_deref(), c.description.as_deref()), (Some("Star Miner"), Some("Mine asteroids, dodge pirates.")));
        assert_eq!(of(&[("ProductName", "Star Miner"), ("FileDescription", "Mine asteroids.")]).description.as_deref(), Some("Mine asteroids."), "Comments, else FileDescription");
        assert_eq!(of(&[("ProductName", "Star Miner"), ("FileDescription", "Star Miner")]).description, None, "a FileDescription equal to the name says nothing");
        assert_eq!(of(&[("ProductName", "Star Miner"), ("Comments", "x"), ("FileDescription", "y")]).description.as_deref(), Some("x"));
        for junk in ["", "  ", "application", "Application", "GAME", "app"] {
            let c = of(&[("ProductName", junk), ("Comments", junk), ("FileDescription", "Real words")]);
            assert_eq!((c.name, c.description.as_deref()), (None, Some("Real words")), "{junk:?}");
        }
        let c = of(&[("ProductName", "  Star\u{7}   Miner\u{202e}"), ("Comments", &"c".repeat(500))]);
        assert_eq!((c.name.as_deref(), c.description.unwrap().len()), (Some("Star Miner"), 400));
        assert_eq!(of(&[("ProductName", &"p".repeat(100))]).name.unwrap().len(), 60);
        assert_eq!(of(&[("ProductName", "Space \u{1F680} Miner")]).name.as_deref(), Some("Space \u{1F680} Miner"), "UTF-16 pairs");
        let two = version_of(program(Some(&info(&[&[("ProductName", "First")], &[("ProductName", "Second"), ("Comments", "Other language")]])))).unwrap();
        assert_eq!((two.name.as_deref(), two.description), (Some("First"), None), "the first string table");
        assert_eq!(version_of(program(Some(&strings_info(&[("LegalCopyright", "x")])))).unwrap(), Card::default());
        assert_eq!(version_of(program(None)), None, "no resources");
        let overlay = [program(Some(&strings_info(&[("ProductName", "With Overlay")]))), vec![0xAB; 5000], trailer(r#"{"name": "x"}"#)].concat();
        assert_eq!(version_of(overlay.clone()).unwrap().name.as_deref(), Some("With Overlay"), "an installer's payload after the last section does not matter");
        assert_eq!(record_of(overlay).unwrap().name.as_deref(), Some("x"));
        let mut pe32 = program(Some(&strings_info(&[("ProductName", "Thirty Two")])));
        // The same program with a PE32 optional header: its data directories start 16 bytes earlier.
        put(&mut pe32, OPT, &0x10Bu16.to_le_bytes());
        put(&mut pe32, OPT + 92, &16u32.to_le_bytes());
        put(&mut pe32, OPT + 96 + 16, &0x2000u32.to_le_bytes());
        let size = pe32[DIRS + 20..DIRS + 24].to_vec();
        put(&mut pe32, OPT + 96 + 20, &size);
        assert_eq!(version_of(pe32).unwrap().name.as_deref(), Some("Thirty Two"));
    }

    fn assert_quiet(bytes: &[u8]) {
        let _ = version_of(bytes.to_vec());
        let _ = record_of(bytes.to_vec());
        let _ = Pe::read(&mut Bytes::new(Cursor::new(bytes.to_vec())).unwrap());
    }

    #[test]
    fn a_damaged_or_lying_program_is_read_as_nothing_and_never_panics() {
        let good = program(Some(&strings_info(&[("ProductName", "Star Miner"), ("Comments", "Mine asteroids.")])));
        assert_eq!(version_of(good.clone()).unwrap().name.as_deref(), Some("Star Miner"));
        for n in 0..good.len() {
            assert_quiet(&good[..n]);
        }
        for at in 0..good.len().min(0x900) {
            for byte in [0x00, 0x01, 0x7F, 0x80, 0xFF] {
                let mut bad = good.clone();
                bad[at] = byte;
                assert_quiet(&bad);
            }
        }
        // Headers that lie about where the next part is, or how many there are: not a program.
        let lies: [(usize, &[u8]); 6] = [
            (0x3C, &u32::MAX.to_le_bytes()),
            (0x3C, &0x600u32.to_le_bytes()),
            (0x46, &0xFFFFu16.to_le_bytes()),
            (0x46, &0u16.to_le_bytes()),
            (0x54, &0xFFFFu16.to_le_bytes()),
            (0x54, &0u16.to_le_bytes()),
        ];
        for (at, bytes) in lies {
            let mut bad = good.clone();
            put(&mut bad, at, bytes);
            assert!(Pe::read(&mut Bytes::new(Cursor::new(bad.clone())).unwrap()).is_none(), "{at:#x}");
            assert_eq!(version_of(bad), None);
        }
        // Counts, addresses and sizes that lie: read as nothing or as little, quickly.
        for at in [OPT + 108, DIRS + 16, DIRS + 20, SECTIONS + 40 + 12, SECTIONS + 40 + 16, SECTIONS + 40 + 20] {
            for value in [u32::MAX, 0x7FFF_FFFF, 0] {
                let mut bad = good.clone();
                put(&mut bad, at, &value.to_le_bytes());
                assert_quiet(&bad);
            }
        }
        // The resource tables: more entries than the file holds, a leaf that points outside, a data length that lies.
        for (at, bytes) in [(0x600 + 14, &0xFFFFu16.to_le_bytes()[..]), (0x600 + 12, &0xFFFFu16.to_le_bytes()), (0x600 + 24 + 14, &5000u16.to_le_bytes()), (0x600 + 72 + 4, &u32::MAX.to_le_bytes()), (0x600 + 72, &u32::MAX.to_le_bytes()), (0x600 + 20, &(SUBDIRECTORY).to_le_bytes())] {
            let mut bad = good.clone();
            put(&mut bad, at, bytes);
            assert_eq!(version_of(bad), None, "{at:#x}");
        }
        // Blocks of version information whose lengths lie: whole, out of the data, shorter than a header, with no end to their key.
        let root = 0x600 + 88;
        for len in [0u16, 1, 5, 6, 7, 0xFFFF, 100, 0x40] {
            let mut bad = good.clone();
            put(&mut bad, root, &len.to_le_bytes());
            assert_quiet(&bad);
        }
        for value_len in [0xFFFFu16, 1, 0x7FFF] {
            let mut bad = good.clone();
            put(&mut bad, root + 2, &value_len.to_le_bytes());
            assert_quiet(&bad);
        }
        let unending = vblock("VS_VERSION_INFO", false, &[], 0, &[]);
        let mut key_without_end = unending.clone();
        key_without_end.truncate(24);
        put(&mut key_without_end, 0, &24u16.to_le_bytes());
        assert!(strings(&key_without_end).is_none() && strings(&unending).is_none() && strings(&[]).is_none() && strings(&[0; 64]).is_none());
        assert_eq!(blocks(&[0; 4096]).count(), 0, "a zero length is not a block, and is never looped on");
        let long_key = vblock(&"k".repeat(200), true, &[], 0, &[]);
        assert!(block(&long_key, 0).is_none());
        // Many blocks: capped, and quick.
        let many: Vec<u8> = (0..5000).flat_map(|_| vblock("ProductName", true, &utf16("x"), 2, &[])).collect();
        assert_eq!(blocks(&many).count(), 256);
    }

    #[test]
    fn mutating_a_program_at_random_never_panics() {
        let good = [program(Some(&strings_info(&[("ProductName", "Star Miner"), ("Comments", "Mine asteroids.")]))), trailer(r#"{"name": "x"}"#)].concat();
        let mut x = 0x9E37_79B9_7F4A_7C15u64;
        let mut next = move || {
            x ^= x << 13;
            x ^= x >> 7;
            x ^= x << 17;
            x
        };
        for _ in 0..4000 {
            let mut bad = good.clone();
            for _ in 0..=(next() % 6) {
                let at = (next() % bad.len() as u64) as usize;
                bad[at] = next() as u8;
            }
            if next() % 7 == 0 {
                bad.truncate((next() % bad.len() as u64) as usize);
            }
            assert_quiet(&bad);
        }
    }

    // ---------- merging

    #[test]
    fn the_strongest_source_wins_field_by_field() {
        let exe = |record: Option<&str>| [program(Some(&strings_info(&[("ProductName", "Program name"), ("Comments", "Program description")]))), record.map(trailer).unwrap_or_default()].concat();
        let record = r#"{"name": "Exe name", "description": "Exe description", "presentation": "hybrid", "author": "ai"}"#;
        let zip = || Some(card(r#"{"name": "Zip name", "description": "Zip description", "presentation": "2d"}"#));
        let dir = game(&[("Game.exe", &exe(Some(record))), ("engine.name", b"Game.exe\n"), ("redengine-game.json", br#"{"name": "Card name"}"#)]);
        let f = find(dir.path(), zip());
        assert_eq!((f.card.name.as_deref(), f.card.description.as_deref(), f.card.presentation.as_deref(), f.card.author.as_deref()), (Some("Card name"), Some("Zip description"), Some("2d"), Some("ai")));
        assert_eq!(f.from, from(&[("name", Source::Card), ("description", Source::Zip), ("presentation", Source::Zip), ("author", Source::Exe)]));
        let dir = game(&[("Game.exe", &exe(Some(record))), ("engine.name", b"Game.exe\n")]);
        let f = find(dir.path(), None);
        assert_eq!(f.from, from(&[("name", Source::Exe), ("description", Source::Exe), ("presentation", Source::Exe), ("author", Source::Exe)]));
        let dir = game(&[("Game.exe", &exe(Some(r#"{"name": "Exe name"}"#))), ("engine.name", b"Game.exe\n")]);
        let f = find(dir.path(), None);
        assert_eq!((f.card.name.as_deref(), f.card.description.as_deref()), (Some("Exe name"), Some("Program description")));
        assert_eq!(f.from, from(&[("name", Source::Exe), ("description", Source::Program)]));
        let dir = game(&[("Game.exe", &exe(None))]);
        assert_eq!(find(dir.path(), None).from, from(&[("name", Source::Program), ("description", Source::Program)]));
        // A script's header outranks a record, which outranks the version information; with two candidates both are read.
        let dir = game(&[
            ("A.bat", &header(&["REM redengine-game", "REM description: Bat description"], "\r\n")),
            ("B.exe", &exe(Some(r#"{"description": "Exe description", "presentation": "3d"}"#))),
        ]);
        let f = find(dir.path(), None);
        assert_eq!((f.card.description.as_deref(), f.card.presentation.as_deref(), f.card.name.as_deref()), (Some("Bat description"), Some("3d"), Some("Program name")));
        assert_eq!(f.from, from(&[("description", Source::Bat), ("presentation", Source::Exe), ("name", Source::Program)]));
        assert_eq!(find(game(&[("g.bat", b"echo")]).path(), None), Found::default());
        let (a, b) = (card(r#"{"name": "a"}"#), card(r#"{"description": "b"}"#));
        let mut found = Found::default();
        let dir = tempfile::tempdir().unwrap();
        let g = Game { dir: dir.path(), only: None };
        found.add(Source::Exe, Some(a), &g);
        found.add(Source::Bat, Some(b), &g);
        found.add(Source::Card, None, &g);
        assert_eq!(found.from, from(&[("name", Source::Exe), ("description", Source::Bat)]), "adding is by field, in the order it is called");
    }

    #[test]
    fn the_program_that_starts_the_game_is_the_one_read() {
        let script = |name: &str, extra: &str| header(&["REM redengine-game", &format!("REM name: {name}"), extra], "\n");
        let files: [(&str, &[u8]); 2] = [("A.bat", &script("From A", "REM presentation: 2d")), ("B.bat", &script("From B", "REM description: Only B"))];
        // Several candidates and none chosen: each in name order, the first to carry a field wins it.
        let f = find(game(&files).path(), None);
        assert_eq!((f.card.name.as_deref(), f.card.presentation.as_deref(), f.card.description.as_deref()), (Some("From A"), Some("2d"), Some("Only B")));
        // The card's entry chooses.
        let chosen = game(&[files[0], files[1], ("redengine-game.json", br#"{"entry": "B.bat"}"#)]);
        let f = find(chosen.path(), None);
        assert_eq!((f.card.name.as_deref(), f.card.presentation.as_deref(), f.card.entry.as_deref()), (Some("From B"), None, Some("B.bat")));
        // `engine.name` comes before the card's entry; a bad `engine.name` is passed over.
        let own = game(&[files[0], files[1], ("redengine-game.json", br#"{"entry": "B.bat"}"#), ("engine.name", b"A.bat\r\n")]);
        let f = find(own.path(), None);
        assert_eq!((f.card.name.as_deref(), f.card.entry.as_deref()), (Some("From A"), Some("B.bat")));
        for bad in ["../A.bat", "Missing.bat", "A.txt", "C:\\A.bat", "/A.bat", "sub\\A.bat", ""] {
            let own = game(&[files[0], files[1], ("redengine-game.json", br#"{"entry": "B.bat"}"#), ("engine.name", bad.as_bytes())]);
            assert_eq!(find(own.path(), None).card.name.as_deref(), Some("From B"), "{bad:?}");
        }
        // A script that is not a candidate (an uninstaller) is not read; one that is alone is.
        let f = find(game(&[("unins000.bat", &script("Uninstall", "")), ("Game.bat", &script("Game", ""))]).path(), None);
        assert_eq!(f.card.name.as_deref(), Some("Game"));
        // Many candidates: only the first few are read.
        let many: Vec<(String, Vec<u8>)> = (0..40).map(|i| (format!("g{i:02}.bat"), script(&format!("Name {i}"), ""))).collect();
        let files: Vec<(&str, &[u8])> = many.iter().map(|(n, d)| (n.as_str(), d.as_slice())).collect();
        assert_eq!(find(game(&files).path(), None).card.name.as_deref(), Some("Name 0"));
    }

    #[test]
    fn a_program_dropped_alone_is_read_alone() {
        let dir = game(&[("Quest.bat", &header(&["REM redengine-game", "REM name: Text Quest", "REM entry: Quest.bat", "REM thumb: shot.png"], "\r\n")), ("shot.png", b"png"), ("Other.bat", b"x")]);
        let f = read_path(&dir.path().join("Quest.bat"));
        assert_eq!((f.card.name.as_deref(), f.card.entry.as_deref(), f.card.thumb), (Some("Text Quest"), Some("Quest.bat"), None), "the game is the one file, not its neighbours");
        assert_eq!(f.from, from(&[("name", Source::Bat), ("entry", Source::Bat)]));
        let exe = game(&[("Game.exe", &[program(Some(&strings_info(&[("ProductName", "Star Miner")]))), trailer(r#"{"description": "Mine."}"#)].concat())]);
        let f = read_path(&exe.path().join("Game.exe"));
        assert_eq!(f.from, from(&[("name", Source::Program), ("description", Source::Exe)]));
        assert_eq!(read_path(&exe.path().join("missing.exe")), Found::default());
        assert_eq!(read_path(&exe.path().join("readme.txt")), Found::default());
        assert_eq!(read_path(Path::new("")), Found::default());
    }

    #[test]
    fn an_entry_and_a_thumb_must_be_plain_files_inside_the_game() {
        let big = MAX_THUMB as usize + 1;
        let dir = game(&[("bin/Game.exe", b"MZ"), ("Quest.bat", b"x"), ("shot.png", b"png"), ("shots/b.jpg", b"jpg"), ("notes.txt", b"t"), ("empty/x", b"x")]);
        File::create(dir.path().join("huge.png")).unwrap().set_len(big as u64).unwrap();
        File::create(dir.path().join("fits.png")).unwrap().set_len(MAX_THUMB).unwrap();
        let of = |json: &str| find(dir.path(), Some(card(json))).card;
        assert_eq!(of(r#"{"entry": "bin/Game.exe", "thumb": "shots/b.jpg"}"#).entry.as_deref(), Some("bin/Game.exe"));
        assert_eq!(of(r#"{"entry": "./bin//Game.exe"}"#).entry, None);
        for entry in ["bin/Missing.exe", "bin", "bin/", "notes.txt", "../Game.exe", "empty", "Quest.BAT"] {
            assert_eq!(of(&serde_json::json!({ "entry": entry }).to_string()).entry, None, "{entry}");
        }
        assert_eq!(of(r#"{"thumb": "shot.png"}"#).thumb.as_deref(), Some("shot.png"));
        assert_eq!(of(r#"{"thumb": "fits.png"}"#).thumb.as_deref(), Some("fits.png"), "5 MB exactly");
        for thumb in ["huge.png", "missing.png", "notes.txt", "shots", "../shot.png"] {
            assert_eq!(of(&serde_json::json!({ "thumb": thumb }).to_string()).thumb, None, "{thumb}");
        }
        // A bad field in a stronger source does not hide a good one in a weaker.
        let f = find(dir.path(), Some(card(r#"{"entry": "Quest.bat"}"#)));
        assert_eq!(f.from["entry"], Source::Zip);
        std::fs::write(dir.path().join(FILE), r#"{"entry": "Missing.exe", "thumb": "huge.png"}"#).unwrap();
        let f = find(dir.path(), Some(card(r#"{"entry": "Quest.bat", "thumb": "shot.png"}"#)));
        assert_eq!((f.card.entry.as_deref(), f.card.thumb.as_deref()), (Some("Quest.bat"), Some("shot.png")));
        assert_eq!((f.from["entry"], f.from["thumb"]), (Source::Zip, Source::Zip));
    }

    #[cfg(unix)]
    #[test]
    fn a_link_never_leads_out_of_the_game() {
        use std::os::unix::fs::symlink;
        let outside = game(&[("secret.exe", &trailer(r#"{"name": "Outside"}"#)), ("secret.png", b"png"), ("dir/inner.exe", b"MZ")]);
        let dir = game(&[("Game.exe", b"MZ"), ("shot.png", b"png")]);
        symlink(outside.path().join("secret.exe"), dir.path().join("link.exe")).unwrap();
        symlink(outside.path().join("secret.png"), dir.path().join("link.png")).unwrap();
        symlink(outside.path().join("dir"), dir.path().join("linked")).unwrap();
        symlink("Game.exe", dir.path().join("inside.exe")).unwrap();
        symlink("nowhere", dir.path().join("dangling.exe")).unwrap();
        symlink(dir.path(), dir.path().join("loop")).unwrap();
        let of = |json: &str| find(dir.path(), Some(card(json))).card;
        assert_eq!(of(r#"{"entry": "link.exe"}"#).entry, None);
        assert_eq!(of(r#"{"entry": "inside.exe"}"#).entry, None, "even a link to a file of the game itself");
        assert_eq!(of(r#"{"entry": "dangling.exe"}"#).entry, None);
        assert_eq!(of(r#"{"entry": "linked/inner.exe"}"#).entry, None, "a folder that is a link");
        assert_eq!(of(r#"{"entry": "loop/Game.exe"}"#).entry, None);
        assert_eq!(of(r#"{"thumb": "link.png"}"#).thumb, None);
        assert_eq!(of(r#"{"thumb": "shot.png"}"#).thumb.as_deref(), Some("shot.png"));
        // Programs, `engine.name` and the card file reached through a link say nothing, and the app's own folder walk is not followed either.
        std::fs::write(dir.path().join("engine.name"), "link.exe\n").unwrap();
        assert_eq!(find(dir.path(), None).card.name, None);
        std::fs::remove_file(dir.path().join("engine.name")).unwrap();
        symlink(outside.path().join("secret.exe"), dir.path().join("redengine-game.json")).unwrap();
        assert_eq!(find(dir.path(), None).card.name, None);
        std::fs::remove_file(dir.path().join("redengine-game.json")).unwrap();
        let alone = game(&[("only", b"x")]);
        symlink(outside.path(), alone.path().join("shortcut")).unwrap();
        std::fs::remove_file(alone.path().join("only")).unwrap();
        assert_eq!(read_path(alone.path()), Found::default(), "a folder holding only a link to a folder is not entered");
        assert_eq!(read_path(&dir.path().join("link.exe")).card.name.as_deref(), Some("Outside"), "a link named on purpose is the person's own doing");
    }

    // ---------- limits that keep a hostile game cheap

    /// A ZIP member name of exactly `len` bytes that is only 13 parts deep.
    fn long_name(len: usize) -> String {
        let mut name = String::new();
        while name.len() + 100 < len - 4 {
            name += &format!("{}/", "d".repeat(99));
        }
        let rest = len - name.len() - 4;
        name + &"e".repeat(rest) + ".txt"
    }

    #[test]
    fn a_zip_member_with_a_long_or_deep_name_is_not_there_and_costs_nothing() {
        let dir = tempfile::tempdir().unwrap();
        let zip = dir.path().join("g.zip");
        // An extra member that counts makes the ZIP two things, so its card at the root is not at the root of one folder.
        let with = |extra: &str| {
            zip_of(&zip, &[("Game/redengine-game.json", br#"{"name": "Names"}"#), ("Game/Game.bat", b"@echo off"), (extra, b"x")], b"");
            read_path(&zip).card.name
        };
        let found = Some("Names".to_string());
        assert_eq!((with(&long_name(1024)), with(&long_name(1025))), (None, found.clone()), "1024 bytes count, 1025 do not");
        assert_eq!((with(&format!("{}y.txt", "x/".repeat(63))), with(&format!("{}y.txt", "x/".repeat(64)))), (None, found), "64 parts count, 65 do not");
        let start = std::time::Instant::now();
        zip_of(&zip, &[(&format!("{}x.bat", "a/".repeat(32_000)), b"@echo off")], b"");
        assert_eq!(read_path(&zip), Found::default());
        assert!(start.elapsed().as_secs() < 5, "a name of 64 000 bytes is dropped, not walked part by part");
    }

    #[test]
    fn a_path_that_names_a_device_is_not_a_cards_path() {
        for entry in ["aux.exe", "bin/CON.bat", "nul.cmd", "bin/com1.exe", "LPT9.EXE", "con .exe"] {
            assert_eq!(card(&serde_json::json!({ "entry": entry }).to_string()).entry, None, "{entry}");
        }
        assert_eq!(card(r#"{"thumb": "media/NUL.png"}"#).thumb, None);
        for entry in ["console.exe", "bin/auxiliary.bat", "com10.exe", "xcon.cmd"] {
            assert!(card(&serde_json::json!({ "entry": entry }).to_string()).entry.is_some(), "{entry}");
        }
        let dir = game(&[("Game.bat", b"x")]);
        assert!(Game { dir: dir.path(), only: None }.file("aux.bat").is_none() && Game { dir: dir.path(), only: None }.file("Game.bat").is_some());
    }

    #[test]
    fn a_card_over_16_kib_is_cut_when_written_so_that_it_still_reads_back() {
        let dir = tempfile::tempdir().unwrap();
        let emoji = |n: usize| "\u{1F600}".repeat(n);
        let part = emoji(60);
        let c = Card {
            name: Some(emoji(60)),
            description: Some(emoji(400)),
            online: Some(emoji(200)),
            entry: Some(format!("{part}/{part}/{part}/{part}/Game.exe")),
            args: Some(vec![emoji(200); 16]),
            ..Card::default()
        };
        assert!(serde_json::to_string(&c.normalized()).unwrap().len() > MAX_CARD, "the longest fields in 4-byte characters do not fit");
        write_card_file(dir.path(), &c).unwrap();
        assert!(std::fs::metadata(dir.path().join(FILE)).unwrap().len() <= MAX_CARD as u64);
        let back = read_card_file(dir.path()).expect("a reader takes the card that was written");
        assert_eq!((back.name, back.args, back.description.map(|d| d.chars().count())), (c.name.clone(), None, Some(400)), "the arguments (launch.args has them) go first");
        let line = comment(&c);
        assert!(line.len() <= TAG.len() + 1 + MAX_CARD && Card::parse(&line.as_bytes()[TAG.len() + 1..]).is_some());
        let small = Card { name: Some("Small".into()), args: Some(vec!["--x".into()]), ..Card::default() };
        write_card_file(dir.path(), &small).unwrap();
        assert_eq!(read_card_file(dir.path()).unwrap().args, small.args, "a card that fits is not cut");
    }

    #[test]
    fn an_online_note_that_is_an_address_or_a_key_is_not_found() {
        for note in [
            "Join 203.0.113.5:27015 with key hunter2", "https://example.com/join?k=abc", "play.example.com:27015", "localhost:8080", "discord.gg/abc123",
            "connect to 10.0.0.1", "www.mygame.net", "fe80::1", "2001:db8:0:0:0:0:0:1", "[::1]:27015", "token=abc", "user@host.io", "Join example.com.", "KEY=Secret", "(server:27016)",
        ] {
            assert!(looks_like_address(note), "{note}");
            assert_eq!(card(&serde_json::json!({"name": "G", "online": note}).to_string()).online, None, "{note}");
        }
        for note in [
            "Up to four players on one LAN.", "Co-op: two players", "2-4 players online (LAN or internet)", "Ratio 16:9 and 12:30 pm", "version 1.2.3 needed", "e.g. two friends",
            "Online play: ping 30ms", "Two players, same room.", "Supports 2-4 players (LAN)", "Co-op.Fun",
        ] {
            assert!(!looks_like_address(note), "{note}");
            assert_eq!(card(&serde_json::json!({"name": "G", "online": note}).to_string()).online.as_deref(), Some(note), "{note}");
        }
    }

    #[test]
    fn a_fork_takes_no_description_designer_online_note_or_notes_from_its_parents_script() {
        let script = header(
            &["REM redengine-game", "REM name: Parent Name", "REM description: The parent's words.", "REM presentation: 3d", "REM author: ai", "REM online: LAN", "REM notes: Parent's notes."],
            "\r\n",
        );
        let dir = game(&[("Game.bat", &script)]);
        let candidates = crate::upload::candidates(dir.path());
        let own = read_folder(dir.path(), None, &candidates, false).card;
        assert_eq!((own.description.as_deref(), own.author.as_deref(), own.online.as_deref(), own.notes.is_some()), (Some("The parent's words."), Some("ai"), Some("LAN"), true));
        let fork = read_folder(dir.path(), None, &candidates, true).card;
        assert_eq!((fork.name.as_deref(), fork.presentation.as_deref()), (Some("Parent Name"), Some("3d")), "its name and look still come from anywhere");
        assert_eq!((fork.description, fork.author, fork.online, fork.notes), (None, None, None, None));
        let said = Some(card(r#"{"description": "Its own words.", "forked_from": {"slug": "snake", "version": 1}}"#));
        let f = read_folder(dir.path(), said, &candidates, false);
        assert_eq!((f.card.description.as_deref(), f.card.author, f.from["description"]), (Some("Its own words."), None, Source::Zip), "a card or a ZIP comment that says forked_from is a fork");
    }

    #[test]
    fn the_folder_a_zip_is_unpacked_into_is_new_every_time() {
        let (a, b) = (new_folder().unwrap(), new_folder().unwrap());
        assert!(a != b && a.is_dir() && b.is_dir() && std::fs::read_dir(&a).unwrap().count() == 0);
        assert!(std::fs::create_dir(&a).is_err(), "a name that is taken is not reused");
        let _ = (std::fs::remove_dir(&a), std::fs::remove_dir(&b));
    }

    // ---------- the fixtures both readers share

    /// `distribution/testdata/game_meta`: small games of every kind and hostile ones, and `expected.json` saying what a reader must find in each.
    /// `distribution/test_game_meta.py` reads the same files with the other reader.
    fn shared() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../../distribution/testdata/game_meta")
    }

    fn expected() -> Value {
        serde_json::from_slice(&std::fs::read(shared().join("expected.json")).expect("expected.json")).expect("expected.json is JSON")
    }

    #[test]
    fn every_shared_fixture_reads_as_expected_json_says() {
        let expected = expected();
        let fixtures = expected["fixtures"].as_object().unwrap();
        let wrong: Vec<String> = fixtures
            .iter()
            .filter_map(|(path, want)| {
                let got = serde_json::to_value(read_path(&shared().join(path))).unwrap();
                (&got != want).then(|| format!("{path}\n  expected {want}\n  found    {got}"))
            })
            .collect();
        assert!(wrong.is_empty(), "{} of {} fixtures differ:\n{}", wrong.len(), fixtures.len(), wrong.join("\n"));
        // Not a reader that answers nothing to everything, and every source is met.
        assert!(fixtures.values().filter(|w| w["card"].as_object().is_some_and(|c| !c.is_empty())).count() > 40);
        let sources: std::collections::BTreeSet<&str> = fixtures.values().flat_map(|w| w["from"].as_object().unwrap().values().filter_map(Value::as_str)).collect();
        assert_eq!(sources.into_iter().collect::<Vec<_>>(), ["bat", "card", "exe", "program", "zip"]);
    }

    #[test]
    fn every_shared_fixture_on_disk_is_listed_and_every_listed_one_is_there() {
        let expected = expected();
        let listed: std::collections::BTreeSet<String> = expected["fixtures"].as_object().unwrap().keys().map(|p| p.split('/').next().unwrap().to_string()).collect();
        let on_disk: std::collections::BTreeSet<String> = std::fs::read_dir(shared())
            .unwrap()
            .map(|e| e.unwrap().file_name().to_string_lossy().into_owned())
            .filter(|n| !["build_fixtures.py", "expected.json", ".gitattributes", "__pycache__"].contains(&n.as_str()))
            .collect();
        assert_eq!(on_disk, listed);
        for path in expected["fixtures"].as_object().unwrap().keys() {
            assert!(shared().join(path).exists(), "{path}");
        }
    }

    #[test]
    fn a_record_is_refused_for_the_programs_the_shared_fixtures_list_and_written_to_every_other() {
        let expected = expected();
        let refused: Vec<&str> = expected["stamp_refused"].as_array().unwrap().iter().map(|p| p.as_str().unwrap()).collect();
        assert!(refused.len() >= 8);
        let dir = tempfile::tempdir().unwrap();
        let card = Card { name: Some("Stamped Name".into()), author: Some("human".into()), ..Card::default() };
        let mut stamped = 0;
        for path in expected["fixtures"].as_object().unwrap().keys().filter(|p| !p.contains('/') && p.ends_with(".exe")) {
            let copy = dir.path().join(path);
            std::fs::copy(shared().join(path), &copy).unwrap();
            let before = std::fs::read(&copy).unwrap();
            let done = write_record(&copy, &card);
            if refused.contains(&path.as_str()) {
                assert!(done.is_err(), "{path} is not a program a record may be added to");
                assert_eq!(std::fs::read(&copy).unwrap(), before, "{path}: refused and untouched");
            } else {
                done.unwrap_or_else(|e| panic!("{path}: {e}"));
                let f = read_path(&copy);
                assert_eq!((f.card.name.as_deref(), f.card.author.as_deref()), (Some("Stamped Name"), Some("human")), "{path}");
                assert_eq!((f.from["name"], f.from["author"]), (Source::Exe, Source::Exe), "{path}");
                stamped += 1;
            }
        }
        assert!(stamped >= 10);
    }
}
