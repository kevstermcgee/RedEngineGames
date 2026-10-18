//! RedEngine Games: the window. All the work is in `redengine-games-core`; this file turns it into commands the page (`../ui`) calls and
//! events it listens to (`job` for a game being installed, `launcher` for the launcher's own update, `close-requested` when the player closes
//! the window while games are downloading).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

use redengine_games_core::{self as core, launch, library::Library, reviews, update, Catalog, SITE};
use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, State, WindowEvent};

const VERSION: &str = env!("CARGO_PKG_VERSION");

struct App {
    library: Mutex<Library>,
    catalog: Mutex<Option<Catalog>>,
    jobs: Mutex<HashMap<String, Arc<AtomicBool>>>,
}

/// `%LOCALAPPDATA%\RedEngineGames` (elsewhere, for development, the user's data folder).
fn library_root() -> PathBuf {
    if let Some(local) = std::env::var_os("LOCALAPPDATA") {
        return PathBuf::from(local).join("RedEngineGames");
    }
    let home = std::env::var_os("HOME").map(PathBuf::from).unwrap_or_else(std::env::temp_dir);
    home.join(".local/share/RedEngineGames")
}

fn profile() -> PathBuf {
    std::env::var_os("USERPROFILE").or_else(|| std::env::var_os("HOME")).map(PathBuf::from).unwrap_or_else(std::env::temp_dir)
}

fn err(e: impl std::fmt::Display) -> String {
    e.to_string()
}

#[derive(Serialize)]
struct Overview {
    games: Vec<serde_json::Value>,
    offline: bool,
    error: Option<String>,
    launcher_version: &'static str,
    site: &'static str,
}

/// The catalog with each game's install state. `refresh` fetches the site again (otherwise the copy from this session is reused).
#[tauri::command]
async fn overview(state: State<'_, App>, refresh: bool) -> Result<Overview, String> {
    let root = state.library.lock().unwrap().root().to_path_buf();
    let mut error = None;
    let mut offline = false;
    if refresh || state.catalog.lock().unwrap().is_none() {
        let cache = root.join("catalog.json");
        let fetched = tauri::async_runtime::spawn_blocking(move || core::download::text(&format!("{SITE}catalog.json")).and_then(|t| {
            let c = Catalog::parse(&t)?;
            let _ = std::fs::write(&cache, &t);
            Ok(c)
        }))
        .await
        .map_err(err)?;
        match fetched {
            Ok(c) => *state.catalog.lock().unwrap() = Some(c),
            Err(e) => {
                offline = true;
                error = Some(e.to_string());
                if state.catalog.lock().unwrap().is_none() {
                    if let Ok(text) = std::fs::read_to_string(root.join("catalog.json")) {
                        *state.catalog.lock().unwrap() = Catalog::parse(&text).ok();
                    }
                }
            }
        }
    }
    let catalog = state.catalog.lock().unwrap().clone();
    let library = state.library.lock().unwrap();
    let mut games = vec![];
    for g in catalog.iter().flat_map(|c| c.games.iter()) {
        let mut v = serde_json::to_value(g).map_err(err)?;
        v["status"] = serde_json::to_value(library.status(g)).map_err(err)?;
        v["installed"] = serde_json::to_value(library.installed(&g.slug)).map_err(err)?;
        games.push(v);
    }
    // A game removed from the site stays playable while it is installed (and with no catalog at all, offline on the first run, every
    // installed game is listed this way, without being called retired).
    for (slug, i) in library.all() {
        if !catalog.as_ref().is_some_and(|c| c.game(slug).is_some()) {
            games.push(serde_json::json!({"slug": slug, "name": i.name, "versions": [], "status": {"state": "installed", "version": i.version}, "installed": i, "retired": catalog.is_some()}));
        }
    }
    Ok(Overview { games, offline, error, launcher_version: VERSION, site: SITE })
}

#[derive(Clone, Serialize)]
struct Job {
    slug: String,
    phase: &'static str,
    done: u64,
    total: u64,
    message: String,
}

/// Download and install the latest version of `slug` (an update when an older one is installed). Progress arrives as `job` events.
#[tauri::command]
async fn install(app: AppHandle, state: State<'_, App>, slug: String) -> Result<(), String> {
    let game = state.catalog.lock().unwrap().as_ref().and_then(|c| c.game(&slug).cloned()).ok_or("the game is not in the catalog")?;
    let cancel = Arc::new(AtomicBool::new(false));
    {
        let mut jobs = state.jobs.lock().unwrap();
        if jobs.contains_key(&slug) {
            return Err("already installing".into());
        }
        jobs.insert(slug.clone(), cancel.clone());
    }
    let handle = app.clone();
    let s = slug.clone();
    let result = tauri::async_runtime::spawn_blocking(move || {
        let state = handle.state::<App>();
        let emit = |phase, done, total, message: String| {
            let _ = handle.emit("job", Job { slug: s.clone(), phase, done, total, message });
        };
        let v = game.latest().cloned().ok_or_else(|| core::Error::NoBuild(game.name.clone()))?;
        let root = state.library.lock().unwrap().root().to_path_buf();
        let zip = root.join("downloads").join(&v.zip.name);
        core::download::file(&v.zip.url, &zip, v.zip.size, &v.zip.sha256, &game.name, &cancel, &mut |p| emit("download", p.done, p.total, String::new()))?;
        emit("unpack", v.zip.size, v.zip.size, String::new());
        let r = state.library.lock().unwrap().install_zip(&game, &v, &zip, &core::today());
        let _ = std::fs::remove_file(&zip);
        r
    })
    .await
    .map_err(err)?;
    state.jobs.lock().unwrap().remove(&slug);
    let (phase, message) = match &result {
        Ok(()) => ("done", String::new()),
        Err(core::Error::Cancelled) => ("cancelled", String::new()),
        Err(e) => ("error", e.to_string()),
    };
    let _ = app.emit("job", Job { slug, phase, done: 0, total: 0, message: message.clone() });
    result.map_err(err)
}

#[tauri::command]
fn cancel(state: State<'_, App>, slug: String) {
    if let Some(flag) = state.jobs.lock().unwrap().get(&slug) {
        flag.store(true, Ordering::Relaxed);
    }
}

#[tauri::command]
fn uninstall(state: State<'_, App>, slug: String) -> Result<(), String> {
    state.library.lock().unwrap().uninstall(&slug).map_err(err)
}

#[tauri::command]
fn play(state: State<'_, App>, slug: String) -> Result<(), String> {
    let mut library = state.library.lock().unwrap();
    let installed = library.installed(&slug).cloned().ok_or_else(|| format!("{slug} is not installed"))?;
    let plan = launch::plan(&library.dir(&slug).map_err(err)?, &installed.name, &profile()).map_err(err)?;
    launch::start(&plan).map_err(err)?;
    library.mark_played(&slug, &core::today()).map_err(err)
}

/// Open the game's saves folder, its installed folder, or its page on the site.
#[tauri::command]
fn open(state: State<'_, App>, slug: String, what: String) -> Result<(), String> {
    let library = state.library.lock().unwrap();
    let target = match what.as_str() {
        "saves" => {
            let name = library.installed(&slug).map(|i| i.name.clone()).unwrap_or_else(|| slug.clone());
            let dir = launch::save_dir(&profile(), &name);
            std::fs::create_dir_all(&dir).map_err(err)?;
            dir.display().to_string()
        }
        "folder" => library.dir(&slug).map_err(err)?.display().to_string(),
        _ => format!("{SITE}games/{slug}/"),
    };
    open_with_shell(&target)
}

fn open_with_shell(target: &str) -> Result<(), String> {
    #[cfg(windows)]
    let mut c = {
        let mut c = std::process::Command::new("explorer");
        c.arg(target);
        c
    };
    #[cfg(not(windows))]
    let mut c = {
        let mut c = std::process::Command::new("xdg-open");
        c.arg(target);
        c
    };
    c.spawn().map(|_| ()).map_err(err)
}

fn review_settings(state: &App) -> reviews::Settings {
    state.catalog.lock().unwrap().as_ref().and_then(|c| c.reviews.clone()).unwrap_or_default()
}

/// Every game's published player reviews (RedEngine's `docs/player-reviews/public.json`).
#[tauri::command]
async fn reviews_published(state: State<'_, App>) -> Result<serde_json::Value, String> {
    let settings = review_settings(&state);
    tauri::async_runtime::spawn_blocking(move || reviews::published(&settings)).await.map_err(err)?.map_err(err)
}

/// Send the player's review, anonymously. An error is a sentence the page shows as it is.
#[tauri::command]
async fn review_send(state: State<'_, App>, review: reviews::Review) -> Result<(), String> {
    let settings = review_settings(&state);
    tauri::async_runtime::spawn_blocking(move || reviews::send(&settings, &review, VERSION)).await.map_err(err)?.map_err(err)
}

/// The newer launcher on the site, if any.
#[tauri::command]
async fn launcher_update() -> Result<Option<update::Latest>, String> {
    tauri::async_runtime::spawn_blocking(|| update::check(SITE, VERSION)).await.map_err(err)?.map_err(err)
}

/// Download the newer launcher, check it, then quit and let it install itself (see `hand_over`). Progress arrives as `launcher` events.
#[tauri::command]
async fn launcher_update_apply(app: AppHandle) -> Result<(), String> {
    let handle = app.clone();
    let installer = tauri::async_runtime::spawn_blocking(move || -> core::Result<PathBuf> {
        let latest = update::check(SITE, VERSION)?.ok_or_else(|| core::Error::Catalog("no newer launcher".into()))?;
        let dest = std::env::temp_dir().join(&latest.installer.name);
        let never = AtomicBool::new(false);
        core::download::file(&latest.installer.url, &dest, latest.installer.size, &latest.installer.sha256, "the launcher update", &never, &mut |p| {
            let _ = handle.emit("launcher", Job { slug: String::new(), phase: "download", done: p.done, total: p.total, message: String::new() });
        })?;
        Ok(dest)
    })
    .await
    .map_err(err)?
    .map_err(err)?;
    let _ = app.emit("launcher", Job { slug: String::new(), phase: "installing", done: 0, total: 0, message: String::new() });
    hand_over(&installer)?;
    app.exit(0);
    Ok(())
}

/// Start a copy of this program as the updater: it waits for this process to end, runs the installer silently, and starts the new launcher.
/// A copy, because the installer replaces this file.
fn hand_over(installer: &std::path::Path) -> Result<(), String> {
    let me = std::env::current_exe().map_err(err)?;
    let helper = std::env::temp_dir().join("RedEngineGames-update-helper.exe");
    std::fs::copy(&me, &helper).map_err(err)?;
    std::process::Command::new(&helper)
        .arg(core::update::HELPER_FLAG)
        .arg(std::process::id().to_string())
        .arg(installer)
        .arg(&me)
        .spawn()
        .map(|_| ())
        .map_err(err)
}

/// Quit now (the page asks first when games are downloading).
#[tauri::command]
fn quit(app: AppHandle) {
    app.exit(0);
}

fn main() {
    // The updater helper (see `hand_over`): no window.
    let args: Vec<String> = std::env::args().collect();
    if args.get(1).map(String::as_str) == Some(core::update::HELPER_FLAG) {
        std::process::exit(core::update::run_helper(&args[2..]));
    }
    tauri::Builder::default()
        // Opening the launcher again brings the open window forward instead of starting a second copy that would share the library.
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.unminimize();
                let _ = w.show();
                let _ = w.set_focus();
            }
        }))
        // After the single-instance check, so a second copy never touches the files of the one already open.
        .setup(|app| {
            let root = library_root();
            // Downloads that were cut off when the launcher last closed start again from the beginning.
            let _ = std::fs::remove_dir_all(root.join("downloads"));
            let library = Library::open(&root)?;
            app.manage(App { library: Mutex::new(library), catalog: Mutex::new(None), jobs: Mutex::new(HashMap::new()) });
            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                if !window.state::<App>().jobs.lock().unwrap().is_empty() {
                    api.prevent_close();
                    let _ = window.emit("close-requested", ());
                }
            }
        })
        .invoke_handler(tauri::generate_handler![overview, install, cancel, uninstall, play, open, launcher_update, launcher_update_apply, quit, reviews_published, review_send])
        .run(tauri::generate_context!())
        .expect("the window opens");
}
