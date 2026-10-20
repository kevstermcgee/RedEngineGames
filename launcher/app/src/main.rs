//! RedEngine Games: the window. All the work is in `redengine-games-core`; this file turns it into commands the page (`../ui`) calls and
//! events it listens to (`job` for a game being installed, `launcher` for the launcher's own update, `publish` for a dropped game being
//! published, `close-requested` when the player closes the window while games are downloading).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

use redengine_games_core::{self as core, launch, library::Library, publish, reviews, update, upload, Catalog, SITE};
use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, State, WindowEvent};

const VERSION: &str = env!("CARGO_PKG_VERSION");

struct App {
    library: Mutex<Library>,
    catalog: Mutex<Option<Catalog>>,
    jobs: Mutex<HashMap<String, Arc<AtomicBool>>>,
    /// The game last dropped on the window, copied into `uploads/staging` and waiting for the player's details.
    dropped: Mutex<Option<upload::Staged>>,
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
    /// This PC has a GitHub token that may publish dropped games.
    can_publish: bool,
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
        v["favorite"] = library.is_favorite(&g.slug).into();
        games.push(v);
    }
    // A game removed from the site stays playable while it is installed (and with no catalog at all, offline on the first run, every
    // installed game is listed this way, without being called retired).
    // A game the player dropped on the window is theirs until the site lists it (if they published it).
    for (slug, i) in library.all() {
        if !catalog.as_ref().is_some_and(|c| c.game(slug).is_some()) {
            games.push(serde_json::json!({"slug": slug, "name": i.name, "versions": [], "status": {"state": "installed", "version": i.version}, "installed": i,
                "retired": catalog.is_some() && !i.local, "local": i.local, "favorite": library.is_favorite(slug)}));
        }
    }
    Ok(Overview { games, offline, error, launcher_version: VERSION, site: SITE, can_publish: publish::token(library.root()).is_some() })
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

/// Heart (`on`) or unheart a game.
#[tauri::command]
fn favorite(state: State<'_, App>, slug: String, on: bool) -> Result<(), String> {
    state.library.lock().unwrap().set_favorite(&slug, on).map_err(err)
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

/// Send a note about the engine itself, anonymously. An error is a sentence the page shows as it is.
#[tauri::command]
async fn note_send(state: State<'_, App>, note: reviews::EngineNote) -> Result<(), String> {
    let settings = review_settings(&state);
    tauri::async_runtime::spawn_blocking(move || reviews::send_note(&settings, &note, VERSION)).await.map_err(err)?.map_err(err)
}

/// What the page needs to ask about a dropped game.
#[derive(Serialize)]
struct Dropped {
    name: String,
    candidates: Vec<String>,
    entry: Option<String>,
    size: u64,
    thumb: bool,
    /// Whether this app may publish (it has a token).
    can_publish: bool,
}

/// Copy what was dropped (`paths`) aside and look at it. Nothing the player dropped is changed.
#[tauri::command]
async fn drop_inspect(state: State<'_, App>, paths: Vec<String>) -> Result<Dropped, String> {
    let root = state.library.lock().unwrap().root().to_path_buf();
    let paths: Vec<PathBuf> = paths.into_iter().map(PathBuf::from).collect();
    let work = root.join("uploads").join("staging");
    let staged = tauri::async_runtime::spawn_blocking(move || upload::stage(&paths, &work)).await.map_err(err)?.map_err(err)?;
    let out = Dropped {
        name: staged.name.clone(),
        candidates: staged.candidates.clone(),
        entry: staged.entry.clone(),
        size: staged.size,
        thumb: staged.thumb.is_some(),
        can_publish: publish::token(&root).is_some(),
    };
    *state.dropped.lock().unwrap() = Some(staged);
    Ok(out)
}

/// The slug a dropped game gets, and the version after the newest one on the site or in the library. A name the site already uses for a
/// game built there is refused.
fn local_version(state: &App, slug: &str) -> Result<u64, String> {
    let catalog = state.catalog.lock().unwrap();
    let on_site = catalog.as_ref().and_then(|c| c.game(slug));
    if on_site.is_some_and(|g| !g.uploaded) {
        return Err("A game on the site already has that name: give this one another.".into());
    }
    let site = on_site.and_then(|g| g.latest()).map(|v| v.version).unwrap_or(0);
    let mine = state.library.lock().unwrap().installed(slug).map(|i| i.version).unwrap_or(0);
    Ok(site.max(mine) + 1)
}

/// Add the dropped game to this PC's library only.
#[tauri::command]
async fn drop_add(state: State<'_, App>, details: upload::Details) -> Result<String, String> {
    let d = details.checked().map_err(err)?;
    let slug = upload::slugify(&d.name);
    let version = local_version(&state, &slug)?;
    let staged = state.dropped.lock().unwrap().take().ok_or("Drop the game again.")?;
    upload::prepare(&staged.folder, &d.entry, &[]).map_err(err)?;
    state.library.lock().unwrap().install_folder(&slug, &d.name, version, &staged.folder, &core::today(), true).map_err(err)?;
    Ok(slug)
}

#[derive(Clone, Serialize)]
struct Published {
    slug: String,
    version: u64,
    url: String,
}

/// Publish the dropped game for everyone (a release on GitHub, which the site and every app then list), and add it to this PC's library.
/// Progress arrives as `publish` events (`phase`: pack, upload, done).
#[tauri::command]
async fn drop_publish(app: AppHandle, state: State<'_, App>, details: upload::Details) -> Result<Published, String> {
    let d = details.checked().map_err(err)?;
    let slug = upload::slugify(&d.name);
    local_version(&state, &slug)?;
    let root = state.library.lock().unwrap().root().to_path_buf();
    let token = publish::token(&root).ok_or("Set up publishing first.")?;
    let staged = state.dropped.lock().unwrap().clone().ok_or("Drop the game again.")?;
    let handle = app.clone();
    let result = tauri::async_runtime::spawn_blocking(move || -> core::Result<Published> {
        let emit = |phase: &str, done: u64, total: u64| {
            let _ = handle.emit("publish", serde_json::json!({"phase": phase, "done": done, "total": total}));
        };
        emit("pack", 0, 0);
        let (version, previous) = publish::next_version(&publish::records(&publish::releases(&token)?), &slug)?;
        upload::prepare(&staged.folder, &d.entry, &[])?;
        let out = root.join("uploads").join("out");
        let _ = std::fs::remove_dir_all(&out);
        let zip_name = format!("{slug}-{version}-windows-x64.zip");
        let (size, sha) = upload::zip_folder(&staged.folder, &out.join(&zip_name))?;
        let tag = format!("{slug}-v{version}");
        let mut files = vec![(out.join(&zip_name), "application/zip")];
        let thumb_url = match &staged.thumb {
            Some(t) => {
                let ext = t.extension().and_then(|e| e.to_str()).unwrap_or("png").to_string();
                let name = format!("{slug}-{version}-thumb.{ext}");
                std::fs::copy(t, out.join(&name))?;
                files.push((out.join(&name), if ext == "png" { "image/png" } else { "image/jpeg" }));
                Some(publish::asset_url(&tag, &name))
            }
            None => previous.as_ref().and_then(|p| p["thumb_url"].as_str().map(String::from)),
        };
        let meta = upload::record(&d, &slug, version, &core::today(), (&zip_name, size, &sha), thumb_url);
        let url = publish::publish(&token, &tag, &format!("{} {version}", d.name), &upload::release_body(&meta), &files, &mut |done, total| emit("upload", done, total))?;
        let _ = std::fs::remove_dir_all(&out);
        let state = handle.state::<App>();
        state.library.lock().unwrap().install_folder(&slug, &d.name, version, &staged.folder, &core::today(), true)?;
        *state.dropped.lock().unwrap() = None;
        emit("done", 0, 0);
        Ok(Published { slug, version, url })
    })
    .await
    .map_err(err)?;
    result.map_err(err)
}

/// Save a GitHub token that may publish, after checking it with GitHub; returns the account's name.
#[tauri::command]
async fn publish_setup(state: State<'_, App>, token: String) -> Result<String, String> {
    let root = state.library.lock().unwrap().root().to_path_buf();
    let token = token.trim().to_string();
    let t = token.clone();
    let login = tauri::async_runtime::spawn_blocking(move || publish::check(&t)).await.map_err(err)?.map_err(err)?;
    std::fs::write(publish::token_file(&root), token).map_err(err)?;
    Ok(login)
}

/// Forget the saved token.
#[tauri::command]
fn publish_forget(state: State<'_, App>) -> Result<(), String> {
    let root = state.library.lock().unwrap().root().to_path_buf();
    match std::fs::remove_file(publish::token_file(&root)) {
        Err(e) if e.kind() != std::io::ErrorKind::NotFound => Err(err(e)),
        _ => Ok(()),
    }
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
            let _ = std::fs::remove_dir_all(root.join("uploads"));
            app.manage(App { library: Mutex::new(library), catalog: Mutex::new(None), jobs: Mutex::new(HashMap::new()), dropped: Mutex::new(None) });
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
        .invoke_handler(tauri::generate_handler![overview, install, cancel, uninstall, play, favorite, open, launcher_update, launcher_update_apply, quit, reviews_published, review_send, note_send,
            drop_inspect, drop_add, drop_publish, publish_setup, publish_forget])
        .run(tauri::generate_context!())
        .expect("the window opens");
}
