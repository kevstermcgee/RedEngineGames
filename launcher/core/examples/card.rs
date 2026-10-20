//! `cargo run -p redengine-games-core --example card -- <path>...`: what a ZIP, a folder or a single `.exe` / `.bat` / `.cmd` says about itself
//! (the game card, `docs/GAME_METADATA.md`), as one JSON line `{"card": {...}, "from": {...}}` for each path. The same answer as
//! `python3 distribution/game_meta.py show --json`, for cross-checking the two readers.
use std::path::PathBuf;

fn main() {
    let paths: Vec<PathBuf> = std::env::args_os().skip(1).map(PathBuf::from).collect();
    if paths.is_empty() {
        eprintln!("usage: card <a .zip, a folder, or an .exe/.bat/.cmd>...");
        std::process::exit(2);
    }
    for path in paths {
        println!("{}", serde_json::to_string(&redengine_games_core::meta::read_path(&path)).expect("a card serializes"));
    }
}
