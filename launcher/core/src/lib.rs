//! The RedEngine Games launcher's library. Everything the window does that is not drawing: read the site's catalog, download a game's portable
//! build and check it against its published SHA-256, unpack it into the player's library, remember what is installed, start a game, update or
//! remove it, send and show player reviews, and update the launcher itself. It has no window and no Tauri, so it builds and is tested on any platform.
//!
//! Where things live (Windows): `%LOCALAPPDATA%\RedEngineGames\` holds `library.json`, `games\<slug>\v<N>\` (one folder per installed game)
//! and `downloads\` (partial downloads, removed when done). Saves are never here: a game keeps them in `Saved Games\<name>`, the same folder its
//! stand-alone installer uses, so a player can move between the two and uninstalling a game never touches them.

pub mod archive;
pub mod catalog;
pub mod download;
pub mod launch;
pub mod library;
pub mod publish;
pub mod reviews;
pub mod update;
pub mod upload;

pub use catalog::{Asset, Catalog, Game, Version};
pub use library::{Installed, Library, Status};

/// Everything that can go wrong, as sentences a player can read.
#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("could not reach {url}: {reason}")]
    Network { url: String, reason: String },
    #[error("the download of {name} was damaged (its checksum did not match); try again")]
    Checksum { name: String },
    #[error("the download of {name} stopped early ({got} of {want} bytes); try again")]
    Truncated { name: String, got: u64, want: u64 },
    #[error("the game archive is not usable: {0}")]
    Archive(String),
    #[error("{0} is not installed")]
    NotInstalled(String),
    #[error("{0} has no version that can be installed")]
    NoBuild(String),
    #[error("cancelled")]
    Cancelled,
    #[error("the catalog could not be read: {0}")]
    Catalog(String),
    #[error("{0}")]
    Review(String),
    /// A dropped game that cannot be added or published, as a sentence for the player.
    #[error("{0}")]
    Upload(String),
    #[error("{0}")]
    Io(#[from] std::io::Error),
}

pub type Result<T> = std::result::Result<T, Error>;

/// Today as `YYYY-MM-DD` (UTC), for the library's records.
pub fn today() -> String {
    let secs = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
    civil(secs / 86_400)
}

/// Days since 1970-01-01 as a calendar date (Howard Hinnant's algorithm).
fn civil(days: u64) -> String {
    let z = days as i64 + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = yoe + era * 400 + i64::from(m <= 2);
    format!("{y:04}-{m:02}-{d:02}")
}

#[cfg(test)]
#[test]
fn dates_are_calendar_dates() {
    assert_eq!(civil(0), "1970-01-01");
    assert_eq!(civil(20_744), "2026-10-18");
    assert_eq!(civil(11_016), "2000-02-29");
}

/// The site the catalog and the launcher's own updates come from.
pub const SITE: &str = "https://kevstermcgee.github.io/RedEngineGames/";

/// The repository whose releases are the site's record of every version (`distribution/config.json`); a published game becomes a release here.
pub const REPOSITORY: &str = "kevstermcgee/RedEngineGames";
