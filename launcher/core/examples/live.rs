//! `cargo run -p redengine-games-core --example live`: the whole install path against the real site, into a temporary library.
use std::sync::atomic::AtomicBool;

use redengine_games_core::{launch, update, Catalog, Library, SITE};

fn main() {
    let tmp = std::env::temp_dir().join(format!("rg-live-{}", std::process::id()));
    let catalog = Catalog::fetch(SITE, &tmp.join("catalog.json")).expect("catalog");
    println!("catalog: {} games ({} with a portable build)", catalog.games.len(), catalog.games.iter().filter(|g| g.latest().is_some()).count());
    let smallest = catalog.games.iter().filter(|g| g.latest().is_some()).min_by_key(|g| g.latest().unwrap().zip.size).unwrap();
    let v = smallest.latest().unwrap();
    println!("installing {} v{} ({} bytes)", smallest.name, v.version, v.zip.size);
    let mut lib = Library::open(&tmp).unwrap();
    let mut last = 0;
    let t = std::time::Instant::now();
    lib.install(smallest, None, "2026-10-18", &AtomicBool::new(false), &mut |p| last = p.done).expect("install");
    println!("installed in {:.1}s, {} bytes checked, status {:?}", t.elapsed().as_secs_f32(), last, lib.status(smallest));
    let plan = launch::plan(&lib.dir(&smallest.slug).unwrap(), &smallest.name, std::path::Path::new("C:/Users/player")).unwrap();
    println!("launch: {} {:?} saves in {}", plan.program.display(), plan.args, plan.save_dir.display());
    // An older version of a game that has one: install it, then update to the latest.
    if let Some(g) = catalog.games.iter().filter(|g| g.versions.len() > 1).min_by_key(|g| g.latest().unwrap().zip.size) {
        let old = g.versions.iter().map(|v| v.version).min().unwrap();
        lib.install(g, Some(old), "d", &AtomicBool::new(false), &mut |_| {}).unwrap();
        println!("{} v{old}: {:?}", g.name, lib.status(g));
        lib.install(g, None, "d", &AtomicBool::new(false), &mut |_| {}).unwrap();
        println!("after update: {:?}", lib.status(g));
    }
    lib.uninstall(&smallest.slug).unwrap();
    println!("uninstalled: {:?}", lib.status(smallest));
    println!("launcher update: {:?}", update::check(SITE, "0.0.1").map(|o| o.map(|l| l.version)));
    let _ = std::fs::remove_dir_all(&tmp);
}
