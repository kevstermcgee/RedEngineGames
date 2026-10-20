//! Publishing a dropped game for everyone, from the window: the same release `distribution/upload_game.py` makes, `<slug>-v<N>` with the
//! portable ZIP (and a screenshot) and the `redengine-release` record, made through GitHub's API. It needs a GitHub token that may write to
//! the repository: anyone can add a game to their own library, only the site's owner can put one on the site.
//!
//! The release is made as a draft, the files are uploaded to it, and only then is it published, so a failed upload never leaves a version
//! on the site without its download (the draft is deleted). Publishing fires the site's rebuild (`pages.yml`, `release: published`).

use std::fs::File;
use std::io::Read;
use std::path::{Path, PathBuf};

use crate::{Error, Result, REPOSITORY};

const API: &str = "https://api.github.com";
const UPLOADS: &str = "https://uploads.github.com";

/// Where the token is kept: a file in the library folder, which only this Windows account can read.
pub fn token_file(root: &Path) -> PathBuf {
    root.join("publish-token")
}

/// The token to publish with: `GH_TOKEN` / `GITHUB_TOKEN` when set, else the one saved in the library folder.
pub fn token(root: &Path) -> Option<String> {
    ["GH_TOKEN", "GITHUB_TOKEN"]
        .iter()
        .filter_map(|k| std::env::var(k).ok())
        .chain(std::fs::read_to_string(token_file(root)).ok())
        .map(|t| t.trim().to_string())
        .find(|t| !t.is_empty())
}

fn agent() -> ureq::Agent {
    ureq::Agent::config_builder()
        .http_status_as_error(false)
        .timeout_connect(Some(std::time::Duration::from_secs(15)))
        .timeout_recv_response(Some(std::time::Duration::from_secs(60 * 30)))
        .user_agent(concat!("RedEngineGames-launcher/", env!("CARGO_PKG_VERSION")))
        .build()
        .into()
}

fn failed(what: &str, status: u16, body: &str) -> Error {
    let message = serde_json::from_str::<serde_json::Value>(body).ok().and_then(|v| v["message"].as_str().map(String::from)).unwrap_or_default();
    Error::Upload(match status {
        401 => "GitHub refused the token (it may have expired): set up publishing again.".into(),
        403 | 404 => format!("The token may not publish to {REPOSITORY} ({what}: {status} {message})."),
        _ => format!("GitHub could not {what} ({status} {message})."),
    })
}

fn call(method: &str, url: &str, token: &str, json: Option<&serde_json::Value>) -> Result<(u16, String)> {
    let a = agent();
    let auth = format!("Bearer {token}");
    let net = |e: ureq::Error| Error::Network { url: url.into(), reason: e.to_string() };
    let mut response = match (method, json) {
        ("GET", _) => a.get(url).header("Authorization", &auth).header("Accept", "application/vnd.github+json").call().map_err(net)?,
        ("DELETE", _) => a.delete(url).header("Authorization", &auth).call().map_err(net)?,
        (m, body) => {
            let req = if m == "PATCH" { a.patch(url) } else { a.post(url) };
            req.header("Authorization", &auth).header("Accept", "application/vnd.github+json").header("Content-Type", "application/json").send(body.map(|b| b.to_string()).unwrap_or_default()).map_err(net)?
        }
    };
    let status = response.status().as_u16();
    let text = response.body_mut().read_to_string().unwrap_or_default();
    Ok((status, text))
}

/// File a note as a GitHub issue in the repository, by the token's account (a signed note: trusted, and its author hears when it is fixed);
/// returns the issue's address.
pub fn issue(token: &str, title: &str, body: &str) -> Result<String> {
    let (status, text) = call("POST", &format!("{API}/repos/{REPOSITORY}/issues"), token, Some(&serde_json::json!({"title": title, "body": body})))?;
    if status != 201 {
        return Err(failed("file the note", status, &text));
    }
    Ok(serde_json::from_str::<serde_json::Value>(&text).ok().and_then(|v| v["html_url"].as_str().map(String::from)).unwrap_or_default())
}

/// Check that `token` may publish (write to the repository); returns the GitHub account it belongs to.
pub fn check(token: &str) -> Result<String> {
    let (status, body) = call("GET", &format!("{API}/repos/{REPOSITORY}"), token, None)?;
    if status != 200 {
        return Err(failed("read the repository", status, &body));
    }
    let repo: serde_json::Value = serde_json::from_str(&body).map_err(|e| Error::Upload(e.to_string()))?;
    if repo["permissions"]["push"].as_bool() != Some(true) {
        return Err(Error::Upload(format!("That token can read {REPOSITORY} but not publish to it.")));
    }
    let (_, user) = call("GET", &format!("{API}/user"), token, None)?;
    Ok(serde_json::from_str::<serde_json::Value>(&user).ok().and_then(|u| u["login"].as_str().map(String::from)).unwrap_or_default())
}

/// The `redengine-release` records in a set of releases' notes (drafts left out: they are not on the site).
pub fn records(releases: &[serde_json::Value]) -> Vec<serde_json::Value> {
    releases
        .iter()
        .filter(|r| r["draft"].as_bool() != Some(true))
        .filter_map(|r| {
            let body = r["body"].as_str()?;
            let start = body.find("<!-- redengine-release ")? + "<!-- redengine-release ".len();
            let end = start + body[start..].find("-->")?;
            serde_json::from_str::<serde_json::Value>(body[start..end].trim()).ok()
        })
        .collect()
}

/// The version to publish `slug` as, and its newest release's record (`None` for a new game). A slug of a game built from the repository
/// (any release of it that was not uploaded) is refused.
pub fn next_version(records: &[serde_json::Value], slug: &str) -> Result<(u64, Option<serde_json::Value>)> {
    let mine: Vec<&serde_json::Value> = records.iter().filter(|r| r["slug"] == slug).collect();
    if mine.iter().any(|r| r["kind"] != "upload") {
        return Err(Error::Upload(format!("“{slug}” is already a game built for the site: give this one another name.")));
    }
    let newest = mine.iter().max_by_key(|r| r["version"].as_u64().unwrap_or(0)).map(|r| (*r).clone());
    Ok((newest.as_ref().and_then(|r| r["version"].as_u64()).unwrap_or(0) + 1, newest))
}

/// Every release of the repository, newest first.
pub fn releases(token: &str) -> Result<Vec<serde_json::Value>> {
    let mut all = vec![];
    for page in 1..=50 {
        let (status, body) = call("GET", &format!("{API}/repos/{REPOSITORY}/releases?per_page=100&page={page}"), token, None)?;
        if status != 200 {
            return Err(failed("list the releases", status, &body));
        }
        let batch: Vec<serde_json::Value> = serde_json::from_str(&body).map_err(|e| Error::Upload(e.to_string()))?;
        let done = batch.len() < 100;
        all.extend(batch);
        if done {
            break;
        }
    }
    Ok(all)
}

/// The address a release file is downloaded from.
pub fn asset_url(tag: &str, name: &str) -> String {
    format!("https://github.com/{REPOSITORY}/releases/download/{tag}/{name}")
}

/// A reader that reports how much of the file has been sent.
struct Counting<'a> {
    file: File,
    done: u64,
    report: &'a mut dyn FnMut(u64),
}

impl Read for Counting<'_> {
    fn read(&mut self, buf: &mut [u8]) -> std::io::Result<usize> {
        let n = self.file.read(buf)?;
        self.done += n as u64;
        (self.report)(self.done);
        Ok(n)
    }
}

/// Make the release `tag` with `body` and the `files` (path, content type), then publish it. `progress(sent, total)` follows the upload.
/// Returns the release's page.
pub fn publish(token: &str, tag: &str, title: &str, body: &str, files: &[(PathBuf, &str)], progress: &mut dyn FnMut(u64, u64)) -> Result<String> {
    let (status, text) = call(
        "POST",
        &format!("{API}/repos/{REPOSITORY}/releases"),
        token,
        Some(&serde_json::json!({"tag_name": tag, "name": title, "body": body, "draft": true, "make_latest": "false"})),
    )?;
    if status != 201 {
        return Err(failed("make the release", status, &text));
    }
    let release: serde_json::Value = serde_json::from_str(&text).map_err(|e| Error::Upload(e.to_string()))?;
    let id = release["id"].as_u64().ok_or_else(|| Error::Upload("GitHub's answer had no release id".into()))?;
    let result = upload_and_publish(token, id, files, progress);
    if result.is_err() {
        let _ = call("DELETE", &format!("{API}/repos/{REPOSITORY}/releases/{id}"), token, None);
    }
    result
}

fn upload_and_publish(token: &str, id: u64, files: &[(PathBuf, &str)], progress: &mut dyn FnMut(u64, u64)) -> Result<String> {
    let total: u64 = files.iter().map(|(p, _)| std::fs::metadata(p).map(|m| m.len()).unwrap_or(0)).sum();
    let mut before = 0u64;
    for (path, content_type) in files {
        let name = path.file_name().and_then(|n| n.to_str()).unwrap_or("file");
        let size = std::fs::metadata(path)?.len();
        let url = format!("{UPLOADS}/repos/{REPOSITORY}/releases/{id}/assets?name={name}");
        let mut report = |done: u64| progress(before + done, total);
        let mut reader = Counting { file: File::open(path)?, done: 0, report: &mut report };
        let mut response = agent()
            .post(&url)
            .header("Authorization", &format!("Bearer {token}"))
            .header("Accept", "application/vnd.github+json")
            .header("Content-Type", *content_type)
            .header("Content-Length", &size.to_string())
            .send(ureq::SendBody::from_reader(&mut reader))
            .map_err(|e| Error::Network { url: url.clone(), reason: e.to_string() })?;
        let status = response.status().as_u16();
        if status != 201 {
            return Err(failed(&format!("upload {name}"), status, &response.body_mut().read_to_string().unwrap_or_default()));
        }
        before += size;
    }
    let (status, text) = call("PATCH", &format!("{API}/repos/{REPOSITORY}/releases/{id}"), token, Some(&serde_json::json!({"draft": false})))?;
    if status != 200 {
        return Err(failed("publish the release", status, &text));
    }
    Ok(serde_json::from_str::<serde_json::Value>(&text).ok().and_then(|r| r["html_url"].as_str().map(String::from)).unwrap_or_default())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn rel(slug: &str, version: u64, kind: &str, draft: bool) -> serde_json::Value {
        let meta = serde_json::json!({"kind": kind, "slug": slug, "version": version, "description": format!("v{version}")});
        serde_json::json!({"draft": draft, "body": format!("notes\n\n<!-- redengine-release {meta} -->\n")})
    }

    #[test]
    fn the_next_version_follows_the_newest_published_upload() {
        let r = records(&[rel("star-miner", 1, "upload", false), rel("star-miner", 2, "upload", false), rel("star-miner", 3, "upload", true), serde_json::json!({"body": "old bundle"})]);
        let (v, prev) = next_version(&r, "star-miner").unwrap();
        assert_eq!(v, 3, "a draft does not count");
        assert_eq!(prev.unwrap()["description"], "v2");
        assert_eq!(next_version(&r, "new-game").unwrap(), (1, None));
    }

    #[test]
    fn a_built_games_slug_is_refused() {
        let r = records(&[rel("coin-run", 4, "", false)]);
        assert!(next_version(&r, "coin-run").unwrap_err().to_string().contains("another name"));
    }

    #[test]
    fn the_saved_token_is_read_trimmed() {
        let dir = tempfile::tempdir().unwrap();
        if std::env::var("GH_TOKEN").is_err() && std::env::var("GITHUB_TOKEN").is_err() {
            assert_eq!(token(dir.path()), None);
            std::fs::write(token_file(dir.path()), " ghp_x \n").unwrap();
            assert_eq!(token(dir.path()).as_deref(), Some("ghp_x"));
        }
    }
}
