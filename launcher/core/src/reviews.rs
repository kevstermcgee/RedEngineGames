//! Player reviews: a score out of 10 and what the player enjoyed and did not, sent anonymously and shown on a game's page. The catalog names where
//! they go (`reviews.send`, a public relay topic) and where the published ones are read (`reviews.read`, RedEngine's
//! `docs/player-reviews/public.json`). RedEngine's `scripts/player_reviews.py` collects them from the relay into the repo; it is the judge, and
//! these checks only spare a player a review that would be dropped.
//!
//! Engine feedback goes the same way: a note about RedEngine itself, not one game (a tip, an idea, a bug or anything else), which the collector
//! keeps apart from the reviews (`engine` in `public.json`).

use serde::{Deserialize, Serialize};

use crate::{Error, Result};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Settings {
    pub send: String,
    pub read: String,
}

impl Default for Settings {
    fn default() -> Settings {
        Settings {
            send: "https://ntfy.sh/redenginegames-reviews-8xoazi8l7d".into(),
            read: "https://raw.githubusercontent.com/kevstermcgee/RedEngine/main/docs/player-reviews/public.json".into(),
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct Review {
    pub game: String,
    pub name_of_game: String,
    #[serde(default)]
    pub version: Option<u64>,
    pub score: u8,
    #[serde(default)]
    pub liked: String,
    #[serde(default)]
    pub disliked: String,
    #[serde(default)]
    pub name: String,
}

pub const MAX_TEXT: usize = 2000;
pub const MAX_NAME: usize = 40;

/// A link anywhere: `http://`, `https://`, `www.` or a bare `word.com`-style address (the collector drops reviews with one).
pub fn has_link(text: &str) -> bool {
    let t = text.to_ascii_lowercase();
    if t.contains("http://") || t.contains("https://") || t.contains("www.") {
        return true;
    }
    const TLDS: [&str; 9] = ["com", "net", "org", "io", "ru", "xyz", "top", "info", "biz"];
    t.split(|c: char| !(c.is_ascii_alphanumeric() || c == '.' || c == '-')).any(|word| {
        let word = word.trim_matches('.');
        word.rsplit_once('.').is_some_and(|(host, tld)| {
            !host.is_empty() && TLDS.contains(&tld) && host.rsplit('.').next().is_some_and(|label| !label.is_empty() && label.chars().all(|c| c.is_ascii_alphanumeric() || c == '-'))
        })
    })
}

/// Why the collector would drop this review, as a sentence for the player; `None` when it is fine.
pub fn problem(r: &Review) -> Option<&'static str> {
    if !(1..=10).contains(&r.score) {
        return Some("Pick a score from 1 to 10.");
    }
    if r.liked.trim().chars().count() < 3 && r.disliked.trim().chars().count() < 3 {
        return Some("Say a little about what you enjoyed or didn't.");
    }
    if r.liked.chars().count() > MAX_TEXT || r.disliked.chars().count() > MAX_TEXT || r.name.trim().chars().count() > MAX_NAME {
        return Some("That is a bit long: keep each answer under 2000 characters and the name under 40.");
    }
    if has_link(&r.liked) || has_link(&r.disliked) || has_link(&r.name) {
        return Some("Please leave out links (they are not accepted).");
    }
    None
}

/// The relay message (v1, as `scripts/player_reviews.py` reads it).
pub fn message(r: &Review, app_version: &str) -> String {
    serde_json::json!({
        "v": 1, "game": r.game, "version": r.version, "score": r.score, "liked": r.liked.trim(), "disliked": r.disliked.trim(),
        "name": r.name.trim(), "source": "app", "app": app_version,
    })
    .to_string()
}

fn encode(s: &str) -> String {
    s.bytes().map(|b| if b.is_ascii_alphanumeric() || b"-_.~".contains(&b) { (b as char).to_string() } else { format!("%{b:02X}") }).collect()
}

/// Send a review. The relay's answer is checked: a review the player was told was sent was received.
pub fn send(settings: &Settings, r: &Review, app_version: &str) -> Result<()> {
    if let Some(p) = problem(r) {
        return Err(Error::Review(p.into()));
    }
    if !settings.send.starts_with("https://") {
        return Err(Error::Review("the review address in the catalog is not https".into()));
    }
    let url = format!("{}?title={}", settings.send, encode(&format!("{}: {}/10", r.name_of_game, r.score)));
    match crate::download::post_text(&url, &message(r, app_version)) {
        Ok(()) => Ok(()),
        Err(Error::Network { reason, .. }) if reason.contains("429") => Err(Error::Review("Too many reviews from your connection just now; try again in a minute.".into())),
        Err(_) => Err(Error::Review("Could not send it (are you online?); try again.".into())),
    }
}

/// A note about the engine, not one game.
#[derive(Debug, Clone, Deserialize)]
pub struct EngineNote {
    /// `tip`, `idea`, `bug` or `other`.
    pub kind: String,
    pub text: String,
    #[serde(default)]
    pub name: String,
}

pub const NOTE_KINDS: [&str; 4] = ["tip", "idea", "bug", "other"];

/// Why the collector would drop this note, as a sentence for the player; `None` when it is fine.
pub fn note_problem(n: &EngineNote) -> Option<&'static str> {
    if !NOTE_KINDS.contains(&n.kind.as_str()) {
        return Some("Pick what kind of note it is.");
    }
    if n.text.trim().chars().count() < 10 {
        return Some("Write a little more (at least a sentence).");
    }
    if n.text.chars().count() > MAX_TEXT || n.name.trim().chars().count() > MAX_NAME {
        return Some("That is a bit long: keep it under 2000 characters and the name under 40.");
    }
    if has_link(&n.text) || has_link(&n.name) {
        return Some("Please leave out links (they are not accepted).");
    }
    None
}

/// The relay message for an engine note (v1 with `about: engine`, as `scripts/player_reviews.py` reads it).
pub fn note_message(n: &EngineNote, app_version: &str) -> String {
    serde_json::json!({"v": 1, "about": "engine", "kind": n.kind, "text": n.text.trim(), "name": n.name.trim(), "source": "app", "app": app_version}).to_string()
}

/// Send an engine note, anonymously.
pub fn send_note(settings: &Settings, n: &EngineNote, app_version: &str) -> Result<()> {
    if let Some(p) = note_problem(n) {
        return Err(Error::Review(p.into()));
    }
    if !settings.send.starts_with("https://") {
        return Err(Error::Review("the feedback address in the catalog is not https".into()));
    }
    let url = format!("{}?title={}", settings.send, encode(&format!("Engine feedback: {}", n.kind)));
    match crate::download::post_text(&url, &note_message(n, app_version)) {
        Ok(()) => Ok(()),
        Err(Error::Network { reason, .. }) if reason.contains("429") => Err(Error::Review("Too many notes from your connection just now; try again in a minute.".into())),
        Err(_) => Err(Error::Review("Could not send it (are you online?); try again.".into())),
    }
}

/// The published reviews of every game (`{"games": {slug: {count, average, reviews}}}`), passed to the page as they are.
pub fn published(settings: &Settings) -> Result<serde_json::Value> {
    let text = crate::download::text(&settings.read)?;
    serde_json::from_str(&text).map_err(|e| Error::Catalog(e.to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn review(score: u8, liked: &str) -> Review {
        Review { game: "restless-tide".into(), name_of_game: "Restless Tide".into(), version: Some(2), score, liked: liked.into(), disliked: String::new(), name: " Jo ".into() }
    }

    #[test]
    fn links_are_spotted_like_the_collector_does() {
        for t in ["see https://x.y", "www.example.org", "go to spam.com now", "cheap.xyz!", "Visit Foo-Bar.IO."] {
            assert!(has_link(t), "{t}");
        }
        for t in ["e.g. the boss", "it was 9.5 out of 10", "the .com era", "Great game.Loved it", "version 1.2"] {
            assert!(!has_link(t), "{t}");
        }
    }

    #[test]
    fn a_review_needs_a_score_and_a_few_words() {
        assert_eq!(problem(&review(0, "nice game")), Some("Pick a score from 1 to 10."));
        assert_eq!(problem(&review(11, "nice game")), Some("Pick a score from 1 to 10."));
        assert_eq!(problem(&review(7, "  ")), Some("Say a little about what you enjoyed or didn't."));
        assert!(problem(&review(7, "see www.x.com")).is_some());
        assert!(problem(&review(7, &"x".repeat(MAX_TEXT + 1))).is_some());
        assert_eq!(problem(&review(7, "Fun")), None);
    }

    #[test]
    fn the_message_is_what_the_collector_reads() {
        let m: serde_json::Value = serde_json::from_str(&message(&review(8, " Clever swaps "), "0.2.0")).unwrap();
        assert_eq!(m["v"], 1);
        assert_eq!(m["game"], "restless-tide");
        assert_eq!(m["version"], 2);
        assert_eq!(m["score"], 8);
        assert_eq!(m["liked"], "Clever swaps");
        assert_eq!(m["name"], "Jo");
        assert_eq!(m["source"], "app");
    }

    #[test]
    fn an_engine_note_needs_a_kind_and_a_sentence() {
        let note = |kind: &str, text: &str| EngineNote { kind: kind.into(), text: text.into(), name: " Sam ".into() };
        assert_eq!(note_problem(&note("rant", "The jump feels floaty in every game.")), Some("Pick what kind of note it is."));
        assert_eq!(note_problem(&note("tip", "ok")), Some("Write a little more (at least a sentence)."));
        assert!(note_problem(&note("idea", "add mods at www.mods.com please")).is_some());
        assert_eq!(note_problem(&note("bug", "The gamepad stops working after alt-tab.")), None);
        let m: serde_json::Value = serde_json::from_str(&note_message(&note("tip", " Let cameras ease in. "), "0.4.0")).unwrap();
        assert_eq!((m["v"].as_u64(), m["about"].as_str(), m["kind"].as_str(), m["text"].as_str(), m["name"].as_str()), (Some(1), Some("engine"), Some("tip"), Some("Let cameras ease in."), Some("Sam")));
        assert!(m.get("game").is_none(), "never mistaken for a game review");
    }

    #[test]
    fn titles_are_url_encoded() {
        assert_eq!(encode("Restless Tide: 8/10"), "Restless%20Tide%3A%208%2F10");
    }
}
