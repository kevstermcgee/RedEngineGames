//! Downloads: small texts (the catalog, `latest.json`) and large files streamed to disk while their SHA-256 is computed.

use std::fs::File;
use std::io::{Read, Write};
use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};

use sha2::{Digest, Sha256};

use crate::{Error, Result};

fn agent() -> ureq::Agent {
    ureq::Agent::config_builder()
        .timeout_connect(Some(std::time::Duration::from_secs(15)))
        .timeout_recv_response(Some(std::time::Duration::from_secs(30)))
        // A stalled download must end (cancel is checked between reads): even a slow line moves a game in far less than this.
        .timeout_recv_body(Some(std::time::Duration::from_secs(30 * 60)))
        .user_agent(concat!("RedEngineGames-launcher/", env!("CARGO_PKG_VERSION")))
        .build()
        .into()
}

pub fn text(url: &str) -> Result<String> {
    let mut response = agent().get(url).call().map_err(|e| Error::Network { url: url.into(), reason: e.to_string() })?;
    response.body_mut().read_to_string().map_err(|e| Error::Network { url: url.into(), reason: e.to_string() })
}

/// What a download reports as it goes: bytes so far and the expected total.
/// POST `body` as plain text; any answer but 2xx is an error.
pub fn post_text(url: &str, body: &str) -> Result<()> {
    agent()
        .post(url)
        .header("Content-Type", "text/plain; charset=utf-8")
        .send(body)
        .map(|_| ())
        .map_err(|e| Error::Network { url: url.into(), reason: e.to_string() })
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Progress {
    pub done: u64,
    pub total: u64,
}

/// Stream `url` into `dest`, checking it is exactly `size` bytes with SHA-256 `sha256` (hex). A damaged or short file is deleted.
/// `progress` is called about every 256 KiB; setting `cancel` stops the download and removes the partial file.
pub fn file(url: &str, dest: &Path, size: u64, sha256: &str, name: &str, cancel: &AtomicBool, progress: &mut dyn FnMut(Progress)) -> Result<()> {
    let response = agent().get(url).call().map_err(|e| Error::Network { url: url.into(), reason: e.to_string() })?;
    let reader = response.into_body().into_reader();
    let result = save(reader, dest, size, sha256, name, cancel, progress);
    if result.is_err() {
        let _ = std::fs::remove_file(dest);
    }
    result
}

/// The part of [`file`] that does not need the network (tested with an in-memory reader).
pub fn save(mut reader: impl Read, dest: &Path, size: u64, sha256: &str, name: &str, cancel: &AtomicBool, progress: &mut dyn FnMut(Progress)) -> Result<()> {
    if let Some(dir) = dest.parent() {
        std::fs::create_dir_all(dir)?;
    }
    let mut out = File::create(dest)?;
    let mut hasher = Sha256::new();
    let mut buf = vec![0u8; 64 * 1024];
    let mut done = 0u64;
    let mut reported = 0u64;
    progress(Progress { done: 0, total: size });
    loop {
        if cancel.load(Ordering::Relaxed) {
            return Err(Error::Cancelled);
        }
        let n = reader.read(&mut buf).map_err(|e| Error::Network { url: name.into(), reason: e.to_string() })?;
        if n == 0 {
            break;
        }
        out.write_all(&buf[..n])?;
        hasher.update(&buf[..n]);
        done += n as u64;
        if done - reported >= 256 * 1024 {
            reported = done;
            progress(Progress { done, total: size });
        }
    }
    out.sync_all()?;
    progress(Progress { done, total: size });
    if done != size {
        return Err(Error::Truncated { name: name.into(), got: done, want: size });
    }
    if hex(&hasher.finalize()) != sha256.to_ascii_lowercase() {
        return Err(Error::Checksum { name: name.into() });
    }
    Ok(())
}

pub fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

pub fn sha256_of(bytes: &[u8]) -> String {
    hex(&Sha256::digest(bytes))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_good_download_is_kept_and_reports_progress() {
        let dir = tempfile::tempdir().unwrap();
        let data = vec![7u8; 700_000];
        let mut seen = vec![];
        let dest = dir.path().join("g.zip");
        save(&data[..], &dest, data.len() as u64, &sha256_of(&data), "g", &AtomicBool::new(false), &mut |p| seen.push(p.done)).unwrap();
        assert_eq!(std::fs::read(&dest).unwrap(), data);
        assert_eq!(*seen.last().unwrap(), 700_000);
        assert!(seen.len() >= 3, "{seen:?}");
    }

    #[test]
    fn a_damaged_or_short_download_is_refused_by_name() {
        let dir = tempfile::tempdir().unwrap();
        let dest = dir.path().join("g.zip");
        let e = save(&b"hello"[..], &dest, 5, &sha256_of(b"other"), "Coin Run", &AtomicBool::new(false), &mut |_| {}).unwrap_err();
        assert!(e.to_string().contains("Coin Run") && e.to_string().contains("checksum"), "{e}");
        let e = save(&b"hel"[..], &dest, 5, &sha256_of(b"hel"), "Coin Run", &AtomicBool::new(false), &mut |_| {}).unwrap_err();
        assert!(matches!(e, Error::Truncated { got: 3, want: 5, .. }), "{e}");
    }

    #[test]
    fn cancelling_stops_the_download() {
        let dir = tempfile::tempdir().unwrap();
        let e = save(&[0u8; 10][..], &dir.path().join("x"), 10, "", "x", &AtomicBool::new(true), &mut |_| {}).unwrap_err();
        assert!(matches!(e, Error::Cancelled));
    }
}
