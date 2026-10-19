//! The site's `catalog.json` (schema 2, written by `site/generate.py`): every game, its versions with their downloads, and its wiki page.

use serde::{Deserialize, Serialize};

use crate::{Error, Result};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Catalog {
    pub schema: u32,
    #[serde(default)]
    pub generated: String,
    /// Where player reviews are sent and read (`distribution/config.json`); older catalogs have none and the defaults apply.
    #[serde(default)]
    pub reviews: Option<crate::reviews::Settings>,
    pub games: Vec<Game>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Game {
    pub slug: String,
    pub name: String,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub added: String,
    #[serde(default)]
    pub online: String,
    #[serde(default = "human")]
    pub author: String,
    #[serde(default = "three_d")]
    pub presentation: String,
    /// Newest first.
    #[serde(default)]
    pub versions: Vec<Version>,
    /// The game's wiki page (`site/wiki.py`), passed to the window as it is.
    #[serde(default)]
    pub wiki: Option<serde_json::Value>,
}

fn human() -> String {
    "human".into()
}

fn three_d() -> String {
    "3d".into()
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Version {
    pub version: u64,
    #[serde(default)]
    pub released: String,
    #[serde(default)]
    pub notes: Vec<String>,
    /// The engine it was built with: what a version with no notes says it is.
    #[serde(default)]
    pub engine_revision: String,
    /// The portable build: what the launcher installs.
    pub zip: Asset,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Asset {
    pub name: String,
    pub size: u64,
    pub sha256: String,
    pub url: String,
}

impl Catalog {
    pub fn parse(text: &str) -> Result<Catalog> {
        let catalog: Catalog = serde_json::from_str(text).map_err(|e| Error::Catalog(e.to_string()))?;
        if catalog.schema != 2 {
            return Err(Error::Catalog(format!("schema {} (this launcher reads schema 2: please update it)", catalog.schema)));
        }
        Ok(catalog)
    }

    /// The catalog from the site; `cache` keeps the last good copy so the library still works offline.
    pub fn fetch(site: &str, cache: &std::path::Path) -> Result<Catalog> {
        let url = format!("{site}catalog.json");
        match crate::download::text(&url) {
            Ok(text) => {
                let catalog = Catalog::parse(&text)?;
                if let Some(dir) = cache.parent() {
                    std::fs::create_dir_all(dir)?;
                }
                let tmp = cache.with_extension("tmp");
                std::fs::write(&tmp, &text)?;
                std::fs::rename(&tmp, cache)?;
                Ok(catalog)
            }
            Err(e) => match std::fs::read_to_string(cache) {
                Ok(text) => Catalog::parse(&text),
                Err(_) => Err(e),
            },
        }
    }

    pub fn game(&self, slug: &str) -> Option<&Game> {
        self.games.iter().find(|g| g.slug == slug)
    }
}

impl Game {
    /// The newest version that has a portable build.
    pub fn latest(&self) -> Option<&Version> {
        self.versions.iter().max_by_key(|v| v.version)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE: &str = r#"{"schema": 2, "generated": "2026-10-18T03:43Z", "games": [
      {"slug": "coin-run", "name": "Coin Run", "description": "d", "added": "2026-09-26", "online": "", "author": "human", "presentation": "3d",
       "versions": [
         {"version": 1, "released": "2026-10-04", "notes": [], "zip": {"name": "coin-run-1-windows-x64.zip", "size": 10, "sha256": "aa", "url": "https://x/1.zip"}, "installer": {"name": "i", "size": 1, "sha256": "b", "url": "u"}},
         {"version": 2, "released": "2026-10-10", "notes": ["n"], "zip": {"name": "coin-run-2-windows-x64.zip", "size": 11, "sha256": "bb", "url": "https://x/2.zip"}}
       ], "earlier": [], "wiki": {"tagline": "t"}},
      {"slug": "old", "name": "Old", "versions": []}
    ]}"#;

    #[test]
    fn the_site_catalog_is_read_with_its_versions_and_wiki() {
        let c = Catalog::parse(SAMPLE).unwrap();
        let g = c.game("coin-run").unwrap();
        assert_eq!(g.latest().unwrap().version, 2);
        assert_eq!(g.latest().unwrap().zip.url, "https://x/2.zip");
        assert_eq!(g.wiki.as_ref().unwrap()["tagline"], "t");
        assert_eq!(c.game("old").unwrap().author, "human");
        assert!(c.game("old").unwrap().latest().is_none());
    }

    #[test]
    fn a_newer_catalog_schema_is_refused_with_a_reason() {
        let e = Catalog::parse(r#"{"schema": 3, "games": []}"#).unwrap_err().to_string();
        assert!(e.contains("schema 3"), "{e}");
    }

    #[test]
    fn the_real_site_catalog_parses() {
        // The catalog the site actually publishes, when the build left one next to the repository (site/dist); skipped otherwise.
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../site/dist/catalog.json");
        if let Ok(text) = std::fs::read_to_string(path) {
            let c = Catalog::parse(&text).unwrap();
            assert!(c.games.iter().all(|g| g.latest().map_or(true, |v| v.zip.sha256.len() == 64)));
        }
    }
}
