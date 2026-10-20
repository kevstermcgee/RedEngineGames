// RedEngine Games launcher: the page. The window (app/src/main.rs) does the work; this asks it for the catalog and the library
// (`overview`), starts installs one at a time from a queue, shows their `job` progress, and offers the launcher's own updates.
"use strict";

const TAURI = window.__TAURI__;
const invoke = (cmd, args) => TAURI.core.invoke(cmd, args || {});
const listen = (name, f) => TAURI.event.listen(name, (e) => f(e.payload));

const S = {
  site: "", version: "", games: [], bySlug: new Map(), offline: false, error: null, loaded: false,
  view: "games", slug: null, history: [],
  jobs: new Map(),      // slug -> {phase: queued|download|unpack, done, total}
  queue: [], active: null,
  recent: [],           // finished this session, newest first: {slug, phase, message}
  filters: { q: "", who: "", kind: "", show: "", sort: "new" },
  update: null,         // the newer launcher ({version, installer, notes}) when there is one
  updateState: null,    // null | {phase: "waiting"|"download"|"installing"|"error", done, total, message}
  updateLater: false,
  playing: new Set(),
  canPublish: false,    // this PC has a GitHub token that may publish (learned when a game is dropped, or set up)
};

try {
  const saved = JSON.parse(localStorage.getItem("filters") || "null");
  if (saved) Object.assign(S.filters, saved, { q: "" });
} catch (_) { /* no storage: defaults */ }

// ---------- helpers

const $ = (sel, root) => (root || document).querySelector(sel);
const h = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const paras = (text) => String(text || "").split("\n").map((p) => p.trim()).filter(Boolean).map((p) => `<p>${h(p)}</p>`).join("");
const mb = (bytes) => bytes >= 1e9 ? `${(bytes / 1e9).toFixed(2)} GB` : `${(bytes / 1e6).toFixed(bytes < 1e7 ? 1 : 0)} MB`;
const plural = (n, one, many) => `${n} ${n === 1 ? one : many || one + "s"}`;
const state = (g) => (g.status && g.status.state) || "not_installed";
const latest = (g) => (g.versions && g.versions[0]) || null;
const pic = (g, name) => `${S.site}games/${encodeURIComponent(g.slug)}/${encodeURIComponent(name)}`;
const tagline = (g) => (g.wiki && g.wiki.tagline) || g.description || "";

/** "2026-10-18" as the player's own short date ("Oct 18, 2026"); anything else as it is. Read as a local date: `new Date("2026-10-18")` is
 *  UTC midnight, which is still the 17th in America. */
function day(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ""));
  if (!m) return String(iso || "");
  return new Date(+m[1], +m[2] - 1, +m[3]).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function thumb(g) {
  if (g.thumb) return S.site + g.thumb;
  const first = g.wiki && g.wiki.gallery && g.wiki.gallery[0];
  return first ? pic(g, first.image) : "";
}

function shot(src, alt, extra) {
  return `<div class="shot">${extra || ""}${src ? `<img src="${h(src)}" alt="${h(alt)}" loading="lazy">` : ""}</div>`;
}

function badges(g) {
  const who = !g.author ? "" : g.author === "ai" ? `<span class="badge ai" title="Invented and built by an AI on its own">AI-designed</span>` : `<span class="badge human" title="Designed by a person">Human-designed</span>`;
  const pres = g.presentation ? `<span class="badge pres">${h(g.presentation.toUpperCase())}</span>` : "";
  const online = g.online ? `<span class="badge online" title="${h(g.online)}">Online multiplayer</span>` : "";
  const retired = g.retired ? `<span class="badge retired">No longer on the site</span>` : "";
  const local = g.local ? `<span class="badge local" title="You added it by dropping it on this window">On this PC only</span>` : "";
  return `<div class="badges">${g.retired ? "" : who + pres}${online}${retired}${local}</div>`;
}

function toast(text, kind) {
  const t = document.createElement("div");
  t.className = `toast ${kind || ""}`;
  t.textContent = text;
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), kind === "error" ? 9000 : 4500);
}

function ask(title, body, ok, cancel) {
  const d = $("#dialog");
  $("h2", d).textContent = title;
  $(".body", d).innerHTML = body;
  $('button[value="ok"]', d).textContent = ok;
  $('button[value="cancel"]', d).textContent = cancel || "Cancel";
  d.returnValue = "";
  d.showModal();
  return new Promise((resolve) => d.addEventListener("close", () => resolve(d.returnValue === "ok"), { once: true }));
}

// ---------- data

async function load(refresh) {
  const btn = $("#refresh");
  btn.classList.add("spin");
  try {
    const o = await invoke("overview", { refresh: !!refresh });
    S.site = o.site;
    S.version = o.launcher_version;
    S.games = o.games;
    S.bySlug = new Map(o.games.map((g) => [g.slug, g]));
    S.offline = o.offline;
    S.error = o.error;
    S.canPublish = !!o.can_publish;
    S.loaded = true;
  } catch (e) {
    S.offline = true;
    S.error = String(e);
  } finally {
    btn.classList.remove("spin");
  }
}

function sortedInstalled() {
  return S.games.filter((g) => state(g) !== "not_installed").sort((a, b) =>
    ((b.installed && b.installed.played) || "").localeCompare((a.installed && a.installed.played) || "") || a.name.localeCompare(b.name));
}

const updatable = () => S.games.filter((g) => state(g) === "update_available");

// ---------- installs: one at a time, the rest wait in a queue

function enqueue(slug) {
  if (S.active === slug || S.queue.includes(slug)) return;
  S.queue.push(slug);
  S.jobs.set(slug, { phase: "queued", done: 0, total: 0 });
  changed(slug);
  pump();
}

async function pump() {
  if (S.active) return;
  if (!S.queue.length) {
    if (S.updateState && S.updateState.phase === "waiting") applyUpdate();
    return;
  }
  const slug = (S.active = S.queue.shift());
  const v = latest(S.bySlug.get(slug) || {});
  S.jobs.set(slug, { phase: "download", done: 0, total: v ? v.zip.size : 0 });
  changed(slug);
  try {
    await invoke("install", { slug });
  } catch (_) {
    // The `job` event already said what went wrong.
  }
  S.jobs.delete(slug);
  S.active = null;
  await load(false);
  changed(slug, true);
  pump();
}

async function cancel(slug) {
  const i = S.queue.indexOf(slug);
  if (i >= 0) {
    S.queue.splice(i, 1);
    S.jobs.delete(slug);
    changed(slug);
    return;
  }
  await invoke("cancel", { slug });
}

function onJob(p) {
  const g = S.bySlug.get(p.slug);
  const name = g ? g.name : p.slug;
  if (p.phase === "download" || p.phase === "unpack") {
    S.jobs.set(p.slug, p);
    paintJob(p.slug);
    return;
  }
  S.recent = [{ slug: p.slug, phase: p.phase, message: p.message }, ...S.recent.filter((r) => r.slug !== p.slug)].slice(0, 20);
  if (p.phase === "done") toast(`${name} is installed and ready to play.`);
  if (p.phase === "error") toast(`${name}: ${p.message}`, "error");
}

async function play(slug) {
  if (S.playing.has(slug)) return;
  const g = S.bySlug.get(slug);
  S.playing.add(slug);
  changed(slug);
  try {
    await invoke("play", { slug });
    toast(`Starting ${g ? g.name : slug}…`);
    await load(false);
  } catch (e) {
    toast(`${g ? g.name : slug} could not start: ${e}`, "error");
  }
  setTimeout(() => { S.playing.delete(slug); changed(slug); }, 4000);
  changed(slug, true);
}

async function uninstall(slug) {
  const g = S.bySlug.get(slug);
  const name = g ? g.name : slug;
  const ok = await ask(`Uninstall ${name}?`, `<p>Its files are removed from this PC. Your saves stay in <strong>Saved Games\\${h(name)}</strong>, so reinstalling picks up where you left off.</p>`, "Uninstall", "Keep it");
  if (!ok) return;
  try {
    await invoke("uninstall", { slug });
    toast(`${name} was uninstalled.`);
  } catch (e) {
    toast(`${name} could not be uninstalled: ${e}`, "error");
  }
  await load(false);
  changed(slug, true);
}

// ---------- the launcher's own updates

async function checkUpdate() {
  try {
    const l = await invoke("launcher_update");
    if (l && (!S.update || S.update.version !== l.version)) S.updateLater = false;
    S.update = l || null;
  } catch (_) {
    // Offline or the site is busy: the next check tries again.
  }
  paintTabs();
  paintBanners();
}

async function applyUpdate() {
  if (!S.update) return;
  if (S.active || S.queue.length) {
    S.updateState = { phase: "waiting" };
    paintBanners();
    return;
  }
  S.updateState = { phase: "download", done: 0, total: S.update.installer.size };
  paintBanners();
  try {
    await invoke("launcher_update_apply");
  } catch (e) {
    S.updateState = { phase: "error", message: String(e) };
    paintBanners();
  }
}

// ---------- drawing

function jobHtml(slug) {
  const j = S.jobs.get(slug);
  const queued = j.phase === "queued";
  const unpack = j.phase === "unpack";
  const pct = j.total ? Math.min(100, (100 * j.done) / j.total) : 0;
  const what = queued ? "Queued" : unpack ? "Installing…" : `${Math.floor(pct)}%`;
  const cancelBtn = unpack ? "" : `<button class="btn link" data-act="cancel" data-slug="${h(slug)}" title="Cancel">Cancel</button>`;
  return `<div class="job"><div class="bar${unpack ? " busy" : ""}"><i style="width:${queued ? 0 : pct}%"></i></div><span class="what">${what}</span>${cancelBtn}</div>`;
}

/** The main button(s) for a game. `size` is "big" on the game's own page, "mini" in Favorites, "" on cards and rows. */
function actHtml(g, size) {
  const s = h(g.slug);
  const big = size === "big" ? " big" : "";
  if (S.jobs.has(g.slug)) return jobHtml(g.slug);
  const v = latest(g);
  const st = state(g);
  const starting = S.playing.has(g.slug);
  const playBtn = `<button class="btn play${big}" data-act="play" data-slug="${s}"${starting ? " disabled" : ""}>${starting ? "Starting…" : "&#x25B6; Play"}</button>`;
  if (st === "update_available") {
    if (size) return playBtn + newerHtml(g, size);
    return `<button class="btn primary" data-act="install" data-slug="${s}">Update <span class="sub">v${g.status.latest} · ${mb(v.zip.size)}</span></button>`
      + `<button class="btn link" data-act="play" data-slug="${s}" title="Play the installed version">Play</button>`;
  }
  if (st === "installed") return playBtn;
  if (!v) return `<button class="btn${big}" disabled>Not available</button>`;
  return `<button class="btn primary${big}" data-act="install" data-slug="${s}">Install <span class="sub">${mb(v.zip.size)}</span></button>`;
}

/** The small button beside Play when a newer version is out: which one and when, and a click updates the game. */
function newerHtml(g, size) {
  const v = latest(g);
  const tip = `Version ${v.version} is ready (released ${day(v.released)}, ${mb(v.zip.size)}). Click to update; your saves stay.`;
  const text = size === "big" ? `New version ${v.version} · ${h(day(v.released))}` : `v${v.version}`;
  return `<button class="newer" data-act="install" data-slug="${h(g.slug)}" title="${h(tip)}" aria-label="${h(tip)}"><span class="up" aria-hidden="true">&#x2191;</span>${text}</button>`;
}

function heartHtml(g) {
  const on = !!g.favorite;
  return `<button class="heart" data-act="heart" data-slug="${h(g.slug)}" data-heart-for="${h(g.slug)}" aria-pressed="${on}" aria-label="Favorite ${h(g.name)}"
    title="${on ? "In your Favorites: click to remove it" : "Add to your Favorites"}">${on ? "&#x2665;" : "&#x2661;"}</button>`;
}

function ownedHtml(g) {
  const st = state(g);
  if (st === "installed") return `<span class="owned">Installed</span>`;
  if (st === "update_available") return `<span class="owned upd">Update ready</span>`;
  return "";
}

function card(g) {
  return `<article class="card${g.favorite ? " fav" : ""}" data-open="${h(g.slug)}">
    ${shot(thumb(g), g.name, `<span data-owned-for="${h(g.slug)}">${ownedHtml(g)}</span>${heartHtml(g)}`)}
    <div class="body">${badges(g)}<h3>${h(g.name)}</h3><p class="tagline">${h(tagline(g))}</p>
    <div class="act" data-act-for="${h(g.slug)}">${actHtml(g, "")}</div></div></article>`;
}

// ---------- favorites: the hearted games, in a small section at the top of Games (kept in library.json by the window)

function favoritesHtml() {
  const favs = S.games.filter((g) => g.favorite).sort((a, b) => a.name.localeCompare(b.name));
  if (!favs.length) return `<h2 class="section">&#x2665; Favorites</h2><p class="fine">Click the &#x2661; on any game to keep it here.</p>`;
  const tile = (g) => `<article class="fav-tile" data-open="${h(g.slug)}">${shot(thumb(g), g.name)}
    <div class="body"><h3 title="${h(g.name)}">${h(g.name)}</h3><div class="act" data-act-for="${h(g.slug)}" data-size="mini">${actHtml(g, "mini")}</div></div>${heartHtml(g)}</article>`;
  return `<h2 class="section">&#x2665; Favorites <span class="count">${favs.length}</span></h2><div class="fav-list">${favs.map(tile).join("")}</div>`;
}

async function setFavorite(slug, on) {
  const g = S.bySlug.get(slug);
  if (!g) return;
  g.favorite = on;
  paintHearts(slug);
  try {
    await invoke("favorite", { slug, on });
  } catch (e) {
    g.favorite = !on;
    paintHearts(slug);
    toast(`${g.name} could not be ${on ? "added to" : "removed from"} your Favorites: ${e}`, "error");
  }
}

function paintHearts(slug) {
  const g = S.bySlug.get(slug);
  document.querySelectorAll(`[data-heart-for="${CSS.escape(slug)}"]`).forEach((b) => { b.outerHTML = heartHtml(g); });
  document.querySelectorAll(`.card[data-open="${CSS.escape(slug)}"]`).forEach((c) => c.classList.toggle("fav", !!g.favorite));
  const favs = $("#favs");
  if (favs) favs.innerHTML = favoritesHtml();
}

function matches(g) {
  const f = S.filters;
  if (g.retired) return false;
  if (f.who && g.author !== f.who) return false;
  if (f.kind && g.presentation !== f.kind) return false;
  const st = state(g);
  if (f.show === "installed" && st === "not_installed") return false;
  if (f.show === "not_installed" && st !== "not_installed") return false;
  if (f.show === "updates" && st !== "update_available") return false;
  if (f.show === "online" && !g.online) return false;
  if (f.q) {
    const text = `${g.name} ${tagline(g)} ${g.description} ${g.author === "ai" ? "ai-designed" : "human-designed"}`.toLowerCase();
    if (!f.q.toLowerCase().split(/\s+/).every((w) => text.includes(w))) return false;
  }
  return true;
}

function gamesView() {
  const f = S.filters;
  const opt = (value, label, cur) => `<option value="${value}"${cur === value ? " selected" : ""}>${label}</option>`;
  return `<section class="favs" id="favs">${favoritesHtml()}</section>
  <p class="intro">Every game says who designed it. <strong>Human-designed</strong> games were designed by a person, and each page shows the prompt that made it.
    <strong>AI-designed</strong> games were invented and built by an AI on its own, a new one most days, so they vary; each page says why the AI made it.</p>
  <div class="toolbar">
    <input id="q" type="search" placeholder="Search games" value="${h(f.q)}" aria-label="Search games">
    <select id="who" aria-label="Designed by">${opt("", "Designed by anyone", f.who)}${opt("human", "Human-designed", f.who)}${opt("ai", "AI-designed", f.who)}</select>
    <select id="kind" aria-label="2D or 3D">${opt("", "2D and 3D", f.kind)}${opt("2d", "2D only", f.kind)}${opt("3d", "3D only", f.kind)}</select>
    <select id="show" aria-label="Show">${opt("", "All games", f.show)}${opt("not_installed", "Not installed", f.show)}${opt("installed", "Installed", f.show)}${opt("updates", "Updates ready", f.show)}${opt("online", "Online multiplayer", f.show)}</select>
    <select id="sort" aria-label="Sort">${opt("new", "Newest first", f.sort)}${opt("name", "A to Z", f.sort)}</select>
    <span class="shown" id="shown"></span>
  </div>
  <div class="grid" id="grid"></div>`;
}

function paintGrid() {
  const grid = $("#grid");
  if (!grid) return;
  const list = S.games.filter(matches).sort(S.filters.sort === "name"
    ? (a, b) => a.name.localeCompare(b.name)
    : (a, b) => (b.added || "").localeCompare(a.added || "") || a.name.localeCompare(b.name));
  const all = S.games.filter((g) => !g.retired).length;
  $("#shown").textContent = list.length === all ? plural(all, "game") : `${list.length} of ${all} games`;
  grid.innerHTML = list.length ? list.map(card).join("") : `<div class="empty"><p>No game matches. <button class="btn link" data-act="clear-filters">Clear the filters</button></p></div>`;
}

function libraryView() {
  const mine = sortedInstalled();
  if (!mine.length) {
    return `<div class="empty"><h2>No games installed yet</h2><p>Pick one under Games: it downloads, installs and stays up to date here. No installers, no warnings.</p>
      <button class="btn primary big" data-view-go="games">Browse the games</button><p class="drop-hint">${DROP_HINT}</p></div>`;
  }
  const ups = updatable();
  const busy = ups.filter((g) => S.jobs.has(g.slug)).length;
  const upAll = ups.length ? `<button class="btn primary" data-act="update-all"${busy === ups.length ? " disabled" : ""}>Update all <span class="sub">${ups.length}</span></button>` : "";
  const rows = mine.map((g) => {
    const i = g.installed || {};
    const st = state(g);
    const meta = st === "update_available" ? `<p class="meta upd">Version ${i.version} installed · version ${g.status.latest} is ready</p>` : `<p class="meta">Version ${i.version}${g.retired ? "" : " · up to date"}</p>`;
    return `<div class="row" data-open="${h(g.slug)}">${shot(thumb(g), g.name)}
      <div><h3>${h(g.name)}</h3>${badges(g)}${meta}<p class="meta">${i.played ? `Last played ${h(day(i.played))}` : "Not played yet"}</p></div>
      <div class="act" data-act-for="${h(g.slug)}">${actHtml(g, "")}</div></div>`;
  }).join("");
  return `<div class="lib-head"><h2>Installed games <span class="count">${mine.length}</span></h2>${upAll}</div><p class="drop-hint">${DROP_HINT}</p><div class="rows">${rows}</div>`;
}

function downloadsView() {
  const live = [S.active, ...S.queue].filter(Boolean).map((slug) => S.bySlug.get(slug)).filter(Boolean);
  const item = (g, inner) => `<div class="dl">${shot(thumb(g), g.name)}<div><h3>${h(g.name)}</h3>${inner}</div><div class="act"><button class="btn link" data-open="${h(g.slug)}">Details</button></div></div>`;
  let out = `<h2 class="section">Downloading</h2>`;
  out += live.length ? `<div class="dl-list">${live.map((g) => item(g, `<div data-act-for="${h(g.slug)}">${jobHtml(g.slug)}</div><div class="state" data-bytes-for="${h(g.slug)}">${bytesText(g.slug)}</div>`)).join("")}</div>`
    : `<p class="fine">Nothing is downloading. Installs and updates you start appear here, one at a time.</p>`;
  const done = S.recent.map((r) => [r, S.bySlug.get(r.slug)]).filter(([, g]) => g);
  if (done.length) {
    out += `<h2 class="section">Finished</h2><div class="dl-list">${done.map(([r, g]) => {
      const text = r.phase === "done" ? `<div class="state good">Installed</div>` : r.phase === "cancelled" ? `<div class="state">Cancelled</div>` : `<div class="state bad">Failed: ${h(r.message)}</div>`;
      const again = r.phase === "done" ? actHtml(g, "") : state(g) !== "installed" && latest(g) ? `<button class="btn" data-act="install" data-slug="${h(g.slug)}">Try again</button>` : "";
      return `<div class="dl">${shot(thumb(g), g.name)}<div><h3>${h(g.name)}</h3>${text}</div><div class="act" data-act-for="${h(g.slug)}" data-finished="1">${again}</div></div>`;
    }).join("")}</div>`;
  }
  return out;
}

function bytesText(slug) {
  const j = S.jobs.get(slug);
  if (!j || j.phase === "queued") return "Waiting for the download before it";
  if (j.phase === "unpack") return "Unpacking into your library…";
  return `${mb(j.done)} of ${mb(j.total)}`;
}

function wikiHtml(g) {
  const w = g.wiki;
  const secs = [["overview", "Overview"], ["story", "Story"], ["play", "How to play"], ["characters", "Characters"]];
  if (w.tips && w.tips.length) secs.push(["tips", "Tips"]);
  secs.push(["gallery", "Gallery"], ["origin", g.author === "ai" ? "Why this game exists" : "The prompt"]);
  if (latest(g)) secs.push(["reviews", "Player reviews"]);
  secs.push(["versions", "Versions"]);
  const note = (k) => (w[k] && String(w[k]).trim() ? `<p class="fine">${h(w[k])}</p>` : "");
  let origin;
  if (g.author === "ai") {
    origin = `<p class="fine">This game was designed by an AI on its own. ${note("why_made_note") ? "Why it was made:" : "Its reason, in its words:"}</p><blockquote>${paras(w.why_made)}</blockquote>${note("why_made_note")}`;
  } else if (w.prompt && w.prompt.trim()) {
    origin = `<p class="fine">This game was designed by a person. The prompt that created it:</p><blockquote class="prompt">${h(w.prompt.trim())}</blockquote>${note("prompt_source")}`;
  } else {
    origin = `<p class="fine">This game was designed by a person.</p><p>${h(w.prompt_unavailable)}</p>`;
  }
  let n = 0;
  const zoom = (image, caption) => `data-zoom="${n++}" data-src="${h(pic(g, image))}" data-caption="${h(caption)}"`;
  const chars = (w.characters || []).map((c) => `<figure class="char"><div ${zoom(c.image, `${c.name}: ${c.description}`)}>${shot(pic(g, c.image), c.name)}</div>
    <figcaption><strong>${h(c.name)}</strong><span>${h(c.role)}</span><p>${h(c.description)}</p></figcaption></figure>`).join("");
  const gallery = (w.gallery || []).map((p) => `<figure><div ${zoom(p.image, p.caption)}>${shot(pic(g, p.image), p.caption)}</div><figcaption>${h(p.caption)}</figcaption></figure>`).join("");
  const controls = (w.controls || []).map((c) => `<tr><td><kbd>${h(c.input)}</kbd></td><td>${h(c.action)}</td></tr>`).join("");
  return `<nav class="toc" aria-label="On this page">${secs.map(([id, t]) => `<button data-scroll="${id}">${t}</button>`).join("")}</nav>
  <div class="wiki">
  <section id="overview"><h2>Overview</h2>${paras(w.overview)}</section>
  <section id="story"><h2>Story</h2>${paras(w.story)}</section>
  <section id="play"><h2>How to play</h2><p><strong>Goal.</strong> ${h(w.goal)}</p><h3>Rules</h3><ol>${(w.rules || []).map((r) => `<li>${h(r)}</li>`).join("")}</ol>
    <h3>Controls</h3><table class="controls"><tr><th>Input</th><th>Does</th></tr>${controls}</table></section>
  <section id="characters"><h2>Characters</h2><div class="chars">${chars}</div></section>
  ${w.tips && w.tips.length ? `<section id="tips"><h2>Tips</h2><ul>${w.tips.map((t) => `<li>${h(t)}</li>`).join("")}</ul></section>` : ""}
  <section id="gallery"><h2>Gallery</h2><div class="gallery">${gallery}</div></section>
  <section id="origin"><h2>${g.author === "ai" ? "Why this game exists" : "The prompt"}</h2>${origin}</section>
  ${reviewsHtml(g)}
  ${versionsHtml(g)}
  </div>`;
}

// ---------- player reviews: a score out of 10 and what the player enjoyed and did not, anonymous (launcher/core/src/reviews.rs)

const RV = { data: null, at: 0 };
const RV_LINK = /https?:\/\/|www\.|\b[a-z0-9-]+\.(com|net|org|io|ru|xyz|top|info|biz)\b/i;
const rvKey = (slug) => `rv-sent-${slug}`;

function reviewsHtml(g) {
  if (g.retired || !latest(g)) return "";
  const scores = Array.from({ length: 10 }, (_, i) => `<label><input type="radio" name="score" value="${i + 1}"><span>${i + 1}</span></label>`).join("");
  return `<section id="reviews" data-game="${h(g.slug)}"><h2>Player reviews</h2>
    <div class="rv-summary"><span class="rv-avg">–</span><span class="rv-count">Loading the reviews…</span></div>
    <form class="rv-form" data-slug="${h(g.slug)}"><h3>Review ${h(g.name)}</h3>
      <fieldset class="rv-score"><legend>Your score out of 10</legend><div>${scores}</div></fieldset>
      <label>What did you enjoy?<textarea name="liked" maxlength="2000" rows="3"></textarea></label>
      <label>What didn't you enjoy?<textarea name="disliked" maxlength="2000" rows="3"></textarea></label>
      <label><span>Your name <span class="fine">(optional)</span></span><input name="name" maxlength="40"></label>
      <p class="fine">No account needed. Your review is public and goes to the engine's developers too, so the next games get better. Please leave out links. It shows here within about half an hour.</p>
      <p><button class="btn primary" type="submit">Send review</button> <span class="rv-status" role="status"></span></p>
    </form>
    <div class="rv-list"></div></section>`;
}

function ownReview(slug) {
  try { return JSON.parse(localStorage.getItem(rvKey(slug)) || "null"); } catch (_) { return null; }
}

function reviewCard(r, pending) {
  const text = (s) => h(s).replace(/\n/g, "<br>");
  const meta = pending ? "your review: it shows for everyone within about half an hour"
    : `${h(day(r.date))}${r.version ? ` · version ${r.version}` : ""}${r.source === "app" ? " · in the app" : ""}`;
  return `<article class="rv${pending ? " pending" : ""}"><header><span class="rv-n">${r.score}<small>/10</small></span><span><strong>${h(r.name || "Anonymous player")}</strong> <span class="fine">${meta}</span></span></header>
    ${r.liked ? `<p><span class="rv-k">Enjoyed</span>${text(r.liked)}</p>` : ""}${r.disliked ? `<p><span class="rv-k">Didn't enjoy</span>${text(r.disliked)}</p>` : ""}</article>`;
}

function paintReviews(slug) {
  const sec = $("#reviews");
  if (!sec || sec.dataset.game !== slug) return;
  const g = RV.data && RV.data.games ? RV.data.games[slug] : null;
  const list = (g && g.reviews) || [];
  let own = ownReview(slug);
  if (own && list.some((r) => r.liked === own.liked && r.disliked === own.disliked)) {
    try { localStorage.removeItem(rvKey(slug)); } catch (_) { /* fine */ }
    own = null;
  }
  $(".rv-avg", sec).textContent = g && g.count ? g.average.toFixed(1) : "–";
  if (RV.data) $(".rv-count", sec).textContent = g && g.count ? `out of 10, from ${plural(g.count, "review")}` : "No reviews yet: be the first.";
  $(".rv-list", sec).innerHTML = (own ? reviewCard(own, true) : "") + list.map((r) => reviewCard(r, false)).join("");
}

async function loadReviews(slug) {
  try {
    if (!RV.data || Date.now() - RV.at > 120000) {
      RV.data = await invoke("reviews_published");
      RV.at = Date.now();
    }
  } catch (_) {
    const sec = $("#reviews");
    if (sec && sec.dataset.game === slug) $(".rv-count", sec).textContent = "The reviews could not be loaded right now.";
  }
  paintReviews(slug);
}

async function sendReview(form) {
  const g = S.bySlug.get(form.dataset.slug);
  const f = new FormData(form);
  const status = $(".rv-status", form);
  const review = {
    game: g.slug, name_of_game: g.name, version: g.installed ? g.installed.version : latest(g).version,
    score: parseInt(f.get("score"), 10) || 0, liked: String(f.get("liked") || "").trim(), disliked: String(f.get("disliked") || "").trim(), name: String(f.get("name") || "").trim(),
  };
  if (!(review.score >= 1 && review.score <= 10)) { status.textContent = "Pick a score from 1 to 10."; return; }
  if (review.liked.length < 3 && review.disliked.length < 3) { status.textContent = "Say a little about what you enjoyed or didn't."; return; }
  if (RV_LINK.test(`${review.liked} ${review.disliked} ${review.name}`)) { status.textContent = "Please leave out links (they are not accepted)."; return; }
  const btn = $("button", form);
  btn.disabled = true;
  status.textContent = "Sending…";
  try {
    await invoke("review_send", { review });
    try { localStorage.setItem(rvKey(g.slug), JSON.stringify({ score: review.score, liked: review.liked, disliked: review.disliked, name: review.name })); } catch (_) { /* fine */ }
    form.reset();
    status.textContent = "Thank you! Your review is on its way.";
    paintReviews(g.slug);
  } catch (e) {
    status.textContent = String(e);
  } finally {
    btn.disabled = false;
  }
}

document.addEventListener("submit", (e) => {
  const form = e.target.closest(".rv-form");
  if (!form || form.classList.contains("note-form")) return;
  e.preventDefault();
  sendReview(form);
});

/** Every version of the game, newest first, as on the website's game page: when it came out and what changed. */
function versionsHtml(g) {
  const mine = g.installed && g.installed.version;
  const vs = g.versions || [];
  if (!vs.length) return `<section id="versions"><h2>Versions</h2><p class="fine">No version of this game is on the site.</p></section>`;
  const rows = vs.map((v, n) => {
    const tags = (n === 0 ? `<span class="tag latest">Latest</span>` : "") + (v.version === mine ? `<span class="tag">Installed</span>` : "");
    const notes = v.notes && v.notes.length ? `<ul>${v.notes.map((x) => `<li>${h(x)}</li>`).join("")}</ul>`
      : `<span class="fine">${v.engine_revision ? `Built with RedEngine ${h(v.engine_revision.slice(0, 12))}` : "No notes"}</span>`;
    return `<tr${v.version === mine ? ' class="mine"' : ""}><td><strong>Version ${v.version}</strong>${tags}</td><td>${h(day(v.released))}</td><td>${notes}</td><td>${mb(v.zip.size)}</td></tr>`;
  }).join("");
  const older = g.retired ? "" : ` Every version can still be downloaded from the game's <button class="inline-link" data-act="page" data-slug="${h(g.slug)}">web page</button>.`;
  return `<section id="versions"><h2>Versions</h2>
    <table class="versions"><thead><tr><th>Version</th><th>Released</th><th>What changed</th><th>Download</th></tr></thead><tbody>${rows}</tbody></table>
    <p class="fine">The app installs the newest version and keeps it up to date; your saves stay when it updates.${older}</p></section>`;
}

/** Under the title: the version the player has (or would get) and when it was released. */
function verLineHtml(g) {
  const vs = g.versions || [];
  const i = g.installed;
  const all = vs.length > 1 ? ` · <button class="inline-link" data-scroll="versions">all ${vs.length} versions</button>` : "";
  if (i) {
    const mine = vs.find((v) => v.version === i.version);
    const when = mine && mine.released ? `Released ${h(day(mine.released))}` : i.installed ? `Installed ${h(day(i.installed))}` : "";
    return `<strong>Version ${i.version} installed</strong>${when ? ` · ${when}` : ""}${all}`;
  }
  const v = latest(g);
  return v ? `<strong>Version ${v.version}</strong> · Released ${h(day(v.released))}${all}` : "";
}

function factsHtml(g) {
  const v = latest(g);
  const i = g.installed;
  const rows = [];
  if (i) rows.push(["Installed on", i.installed ? h(day(i.installed)) : "–"], ["Last played", i.played ? h(day(i.played)) : "not yet"]);
  if (v) rows.push(["Download", mb(v.zip.size)]);
  if (g.added) rows.push(["On the site since", h(day(g.added))]);
  return rows.map(([k, val]) => `<dt>${k}</dt><dd>${val}</dd>`).join("");
}

function moreHtml(g) {
  const s = h(g.slug);
  const installed = state(g) !== "not_installed";
  return (installed ? `<button class="btn link" data-act="saves" data-slug="${s}">Saves folder</button><button class="btn link" data-act="folder" data-slug="${s}">Game files</button>` : "")
    + (g.retired ? "" : `<button class="btn link" data-act="page" data-slug="${s}">Web page</button>`)
    + (installed && !S.jobs.has(g.slug) ? `<button class="btn link danger" data-act="uninstall" data-slug="${s}">Uninstall</button>` : "");
}

function gameView(g) {
  const first = g.wiki && g.wiki.gallery && g.wiki.gallery[0];
  const hero = first ? pic(g, first.image) : thumb(g);
  const online = g.online ? `<p class="online-note"><strong>Online multiplayer.</strong> ${h(g.online)}</p>` : "";
  const body = g.wiki ? wikiHtml(g) : g.local
    ? `<div class="wiki"><p class="fine">You added this game by dropping it on this window, so it is only on this PC${S.canPublish ? " until you publish it" : ""}. To update it, drop a newer build with the same name.</p></div>`
    : g.retired
    ? `<p class="fine">This game has been taken off the site. Your installed copy still plays; once you uninstall it, it cannot be installed again.</p>`
    : `<div class="wiki"><p class="fine">This game has no wiki page yet.</p>${versionsHtml(g)}</div>`;
  return `<button class="btn link back" data-act="back">&#x2039; Back</button>
  <section class="hero">
    <div ${first ? `data-zoom="hero" data-src="${h(hero)}" data-caption="${h(first.caption)}"` : ""}>${shot(hero, g.name)}</div>
    <div><div class="title-row"><h1>${h(g.name)}</h1>${heartHtml(g)}</div>${badges(g)}<p class="lead">${h(tagline(g))}</p>
      <p class="ver-line" data-ver-for="${h(g.slug)}">${verLineHtml(g)}</p>
      <div class="act" data-act-for="${h(g.slug)}" data-size="big">${actHtml(g, "big")}</div>
      <div class="more" data-more-for="${h(g.slug)}">${moreHtml(g)}</div>
      <dl class="facts" data-facts-for="${h(g.slug)}">${factsHtml(g)}</dl>${online}</div>
  </section>${body}`;
}

function paintTabs() {
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.view === S.view && !S.slug));
  const mine = S.games.filter((g) => state(g) !== "not_installed").length;
  const nl = $("#n-library");
  nl.textContent = mine ? (updatable().length ? `${mine} · ${updatable().length} update${updatable().length === 1 ? "" : "s"}` : mine) : "";
  nl.classList.toggle("hot", updatable().length > 0);
  const nd = $("#n-downloads");
  const live = (S.active ? 1 : 0) + S.queue.length;
  nd.textContent = live || "";
  nd.classList.toggle("hot", live > 0);
  const ver = $("#version");
  const later = S.update && S.updateLater && !S.updateState;
  ver.textContent = S.version ? (later ? `v${S.version} · update to ${S.update.version}` : `v${S.version}`) : "";
  ver.classList.toggle("hot", !!later);
  ver.title = later ? "Show the launcher update" : "The launcher's version";
}

function paintBanners() {
  let out = "";
  const u = S.update;
  const us = S.updateState;
  if (u && (!S.updateLater || us)) {
    const notes = u.notes && u.notes.length ? `<span class="fine"> ${h(u.notes.join(" "))}</span>` : "";
    let right = `<button class="btn link" data-act="update-later">Later</button><button class="btn primary" data-act="update-now">Update now</button>`;
    let text = `<strong>A new version of RedEngine Games is ready</strong> (version ${h(u.version)}; you have ${h(S.version)}).${notes}`;
    if (us && us.phase === "waiting") {
      text = `<strong>The launcher will update when your downloads finish.</strong> It closes, installs version ${h(u.version)} and opens again by itself.`;
      right = "";
    } else if (us && us.phase === "download") {
      const pct = us.total ? Math.floor((100 * us.done) / us.total) : 0;
      text = `<strong>Downloading version ${h(u.version)}…</strong> ${pct}% of ${mb(u.installer.size)}`;
      right = `<div class="bar"><i style="width:${pct}%"></i></div>`;
    } else if (us && us.phase === "installing") {
      text = `<strong>Installing version ${h(u.version)}.</strong> The launcher closes now and opens again by itself in a few seconds.`;
      right = `<div class="bar busy"><i></i></div>`;
    } else if (us && us.phase === "error") {
      text = `<strong>The update did not download.</strong> <span class="fine">${h(us.message)}</span>`;
      right = `<button class="btn link" data-act="update-later">Later</button><button class="btn primary" data-act="update-now">Try again</button>`;
    }
    out += `<div class="banner update"><p>${text}</p>${right}</div>`;
  }
  if (S.offline) {
    const have = S.games.length
      ? "Showing the games from your last visit; your installed games still play."
      : "The game list could not be loaded yet.";
    out += `<div class="banner offline"><p><strong>Can't reach the RedEngine Games site.</strong> ${have} <span class="fine">${h(S.error || "")}</span></p><button class="btn" data-act="refresh">Try again</button></div>`;
  }
  $("#banners").innerHTML = out;
}

function paintView() {
  const main = $("#view");
  if (!S.games.length) {
    main.innerHTML = S.offline ? `<div class="empty"><h2>No connection</h2><p>The launcher needs the internet the first time, to fetch the list of games.</p><button class="btn primary" data-act="refresh">Try again</button></div>`
      : S.loaded ? `<div class="empty"><h2>No games yet</h2><p>The site has no games to install right now.</p></div>` : `<p class="loading">Loading the games…</p>`;
    return;
  }
  if (S.slug) {
    const g = S.bySlug.get(S.slug);
    if (!g) { S.slug = null; return paintView(); }
    main.innerHTML = gameView(g);
    loadReviews(g.slug);
  } else if (S.view === "library") {
    main.innerHTML = libraryView();
  } else if (S.view === "downloads") {
    main.innerHTML = downloadsView();
  } else if (S.view === "feedback") {
    main.innerHTML = feedbackView();
    loadNotes();
  } else {
    main.innerHTML = gamesView();
    paintGrid();
  }
}

/** Repaint what depends on one game's state without rebuilding the page (images stay put). `statusChanged` also rebuilds lists whose
 *  membership may have changed. */
function changed(slug, statusChanged) {
  paintTabs();
  const g = S.bySlug.get(slug);
  if (S.view === "downloads" && !S.slug) return keepScroll(paintView);
  if (S.view === "library" && !S.slug && statusChanged) return keepScroll(paintView);
  if (!S.slug && S.view === "games" && statusChanged && S.filters.show && S.filters.show !== "online") return keepScroll(paintGrid);
  if (S.view === "library" && !S.slug) {
    const up = $('[data-act="update-all"]');
    if (up) up.disabled = updatable().every((u) => S.jobs.has(u.slug));
  }
  if (!g) return;
  document.querySelectorAll(`[data-act-for="${CSS.escape(slug)}"]`).forEach((el) => { if (!el.dataset.finished) el.innerHTML = actHtml(g, el.dataset.size || ""); });
  document.querySelectorAll(`[data-ver-for="${CSS.escape(slug)}"]`).forEach((el) => { el.innerHTML = verLineHtml(g); });
  document.querySelectorAll(`[data-owned-for="${CSS.escape(slug)}"]`).forEach((el) => { el.innerHTML = ownedHtml(g); });
  document.querySelectorAll(`[data-facts-for="${CSS.escape(slug)}"]`).forEach((el) => { el.innerHTML = factsHtml(g); });
  document.querySelectorAll(`[data-more-for="${CSS.escape(slug)}"]`).forEach((el) => { el.innerHTML = moreHtml(g); });
  if (S.slug === slug && statusChanged) {
    const v = $("#versions");
    if (v) v.outerHTML = versionsHtml(g);
  }
}

/** Progress only: move the bar. */
function paintJob(slug) {
  const j = S.jobs.get(slug);
  document.querySelectorAll(`[data-act-for="${CSS.escape(slug)}"]`).forEach((el) => {
    if (el.dataset.finished) return;
    const bar = $(".bar", el);
    const what = $(".what", el);
    if (!bar || !what || (j.phase === "unpack") !== bar.classList.contains("busy")) {
      el.innerHTML = jobHtml(slug);
      return;
    }
    const pct = j.total ? Math.min(100, (100 * j.done) / j.total) : 0;
    $("i", bar).style.width = `${pct}%`;
    what.textContent = `${Math.floor(pct)}%`;
  });
  document.querySelectorAll(`[data-bytes-for="${CSS.escape(slug)}"]`).forEach((el) => { el.textContent = bytesText(slug); });
}

/** A wiki section, just under the sticky contents list (however many lines it wraps to). Only <main> scrolls: `scrollIntoView` would
 *  scroll every scrollable box around the section, the window too. */
function scrollToSection(id) {
  const main = $("#view");
  const el = document.getElementById(id);
  if (!el) return;
  const toc = $(".toc", main);
  const top = el.getBoundingClientRect().top - main.getBoundingClientRect().top + main.scrollTop - (toc ? toc.offsetHeight + 12 : 0);
  main.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
}

function keepScroll(f) {
  const main = $("#view");
  const top = main.scrollTop;
  f();
  main.scrollTop = top;
}

function paintAll() {
  paintTabs();
  paintBanners();
  keepScroll(paintView);
}

// ---------- navigation

function go(view) {
  S.history = [];
  S.view = view;
  S.slug = null;
  paintAll();
  $("#view").scrollTop = 0;
}

function openGame(slug) {
  if (S.slug === slug) return;
  S.history.push({ view: S.view, slug: S.slug, top: $("#view").scrollTop });
  S.slug = slug;
  paintAll();
  $("#view").scrollTop = 0;
}

function back() {
  const prev = S.history.pop();
  if (!prev) return go(S.view);
  S.view = prev.view;
  S.slug = prev.slug;
  paintTabs();
  paintView();
  $("#view").scrollTop = prev.top;
}

// ---------- the picture viewer

const LB = { items: [], i: 0 };

function zoom(el) {
  const scope = el.closest(".wiki") || el.closest(".hero");
  const all = el.dataset.zoom === "hero" ? [el] : [...scope.querySelectorAll("[data-zoom]")];
  LB.items = all.map((x) => ({ src: x.dataset.src, caption: x.dataset.caption }));
  LB.i = Math.max(0, all.indexOf(el));
  showLightbox();
}

function showLightbox() {
  const lb = $("#lightbox");
  const it = LB.items[LB.i];
  $("img", lb).src = it.src;
  $("img", lb).alt = it.caption;
  $("figcaption", lb).textContent = it.caption;
  $(".prev", lb).hidden = $(".next", lb).hidden = LB.items.length < 2;
  lb.hidden = false;
}

function stepLightbox(d) {
  LB.i = (LB.i + d + LB.items.length) % LB.items.length;
  showLightbox();
}

// ---------- input

document.addEventListener("click", async (e) => {
  const t = e.target;
  const lb = $("#lightbox");
  if (!lb.hidden) {
    if (t.closest(".prev")) stepLightbox(-1);
    else if (t.closest(".next")) stepLightbox(1);
    else if (!t.closest("img")) lb.hidden = true;
    return;
  }
  const tab = t.closest(".tabs button");
  if (tab) return go(tab.dataset.view);
  const goBtn = t.closest("[data-view-go]");
  if (goBtn) return go(goBtn.dataset.viewGo);
  const scroll = t.closest("[data-scroll]");
  if (scroll) return scrollToSection(scroll.dataset.scroll);
  const act = t.closest("[data-act]");
  if (act) {
    e.stopPropagation();
    const slug = act.dataset.slug;
    switch (act.dataset.act) {
      case "install": return enqueue(slug);
      case "cancel": return cancel(slug);
      case "play": return play(slug);
      case "heart": return setFavorite(slug, !(S.bySlug.get(slug) || {}).favorite);
      case "uninstall": return uninstall(slug);
      case "saves": case "folder": case "page":
        return invoke("open", { slug, what: act.dataset.act }).catch((err) => toast(String(err), "error"));
      case "update-all": updatable().forEach((g) => enqueue(g.slug)); return;
      case "back": return back();
      case "refresh": return refresh();
      case "clear-filters":
        Object.assign(S.filters, { q: "", who: "", kind: "", show: "" });
        saveFilters();
        return paintView();
      case "update-now": return applyUpdate();
      case "update-later": S.updateLater = true; S.updateState = null; paintTabs(); return paintBanners();
      case "show-update": if (S.update && S.updateLater) { S.updateLater = false; paintTabs(); paintBanners(); } return;
      case "publish-setup": return openPublishSetup();
    }
    return;
  }
  const z = t.closest("[data-zoom]");
  if (z) return zoom(z);
  const open = t.closest("[data-open]");
  if (open) return openGame(open.dataset.open);
});

function saveFilters() {
  try { localStorage.setItem("filters", JSON.stringify({ ...S.filters, q: "" })); } catch (_) { /* fine */ }
}

document.addEventListener("input", (e) => {
  const id = e.target.id;
  if (!["q", "who", "kind", "show", "sort"].includes(id)) return;
  S.filters[id] = e.target.value;
  saveFilters();
  paintGrid();
});

document.addEventListener("keydown", (e) => {
  const lb = $("#lightbox");
  if (!lb.hidden) {
    if (e.key === "Escape") lb.hidden = true;
    if (e.key === "ArrowLeft") stepLightbox(-1);
    if (e.key === "ArrowRight") stepLightbox(1);
    return;
  }
  if (document.querySelector("dialog[open]")) return;
  const typing = /INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName) && document.activeElement.type !== "radio";
  if (e.key === "Escape" && S.slug && !typing) back();
  else if (e.key === "/" && !typing && S.view === "games" && !S.slug) { e.preventDefault(); $("#q").focus(); }
  else if (e.key === "F5") { e.preventDefault(); refresh(); }
});

// The mouse's back button.
document.addEventListener("mouseup", (e) => { if (e.button === 3 && S.slug) back(); });

// The window itself never scrolls (only <main> does): if anything ever scrolls it, the top bar would be cut off with no way back.
window.addEventListener("scroll", () => { if (window.scrollX || window.scrollY) window.scrollTo(0, 0); });

// A picture that cannot load (offline) leaves a plain panel instead of a broken-image icon.
document.addEventListener("error", (e) => { if (e.target.tagName === "IMG") e.target.classList.add("broken"); }, true);

// No browser context menu or text-selection look on the chrome, like any desktop app.
document.addEventListener("contextmenu", (e) => { if (!e.target.closest("input, textarea, blockquote, .wiki p, .wiki li")) e.preventDefault(); });

/** Check the site again (the button, F5, or "Try again") and say what changed: new games, updates ready, or nothing. */
async function refresh() {
  if ($("#refresh").classList.contains("spin")) return;
  const before = new Set(S.games.map((g) => g.slug));
  await load(true);
  paintAll();
  checkUpdate();
  if (S.offline) return toast("Can't reach the RedEngine Games site right now; try again in a moment.", "error");
  const fresh = S.games.filter((g) => !before.has(g.slug) && !g.local);
  const ups = updatable().length;
  const parts = [];
  if (fresh.length) parts.push(fresh.length === 1 ? `New game: ${fresh[0].name}` : `${fresh.length} new games: ${fresh.slice(0, 3).map((g) => g.name).join(", ")}${fresh.length > 3 ? "…" : ""}`);
  if (ups) parts.push(`${plural(ups, "update")} ready in Library`);
  toast(parts.length ? parts.join(" · ") : `Up to date: no new games (${plural(S.games.filter((g) => !g.retired && !g.local).length, "game")} on the site).`);
}

// ---------- a game of the player's own: drop it on the window to add it to this PC's library, or publish it for everyone

const DROP_HINT = `Have a game of your own? Drop its ZIP, folder, .exe or .bat anywhere on this window to add it. <button class="inline-link" data-act="publish-setup">Publishing…</button>`;
const DROP = { info: null, busy: false };

/** The game's id in addresses, as the window makes it (`upload::slugify`). */
const slugify = (name) => String(name || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");

async function dropped(paths) {
  if (DROP.busy || document.querySelector("dialog[open]")) return;
  DROP.busy = true;
  toast("Looking at the game…");
  try {
    DROP.info = await invoke("drop_inspect", { paths });
    S.canPublish = DROP.info.can_publish;
  } catch (e) {
    toast(String(e), "error");
    return;
  } finally {
    DROP.busy = false;
  }
  openDropDialog(paths);
}

function openDropDialog(paths) {
  const d = $("#drop");
  const f = $("form", d);
  const info = DROP.info;
  f.reset();
  f.name.value = info.name;
  const names = paths.map((p) => p.split(/[\\/]/).pop());
  $(".drop-what", d).textContent = `${names.slice(0, 3).join(", ")}${names.length > 3 ? ` and ${names.length - 3} more` : ""} · ${mb(info.size)}${info.thumb ? " · with a screenshot" : ""}`;
  const sel = f.entry;
  sel.innerHTML = info.candidates.map((c) => `<option${c === info.entry ? " selected" : ""}>${h(c)}</option>`).join("")
    || `<option value="">Nothing to start: it needs an .exe, .bat or .cmd</option>`;
  if (info.entry && !info.candidates.includes(info.entry)) sel.insertAdjacentHTML("afterbegin", `<option selected>${h(info.entry)}</option>`);
  prefill(f);
  $(".drop-progress", d).hidden = true;
  $(".drop-status", d).textContent = "";
  $(".drop-status", d).className = "drop-status";
  paintDropNote();
  d.showModal();
}

/** A new version of a game already on the site or in the library starts from what it says now. */
function prefill(f) {
  const g = S.bySlug.get(slugify(f.name.value));
  if (!g || !(g.uploaded || g.local)) return;
  if (g.description) f.description.value = g.description;
  if (g.presentation) f.presentation.value = g.presentation;
  if (g.author) f.author.value = g.author;
}

/** Under the form: what adding or publishing will do with this name. */
function paintDropNote() {
  const d = $("#drop");
  const f = $("form", d);
  const note = $(".drop-note", d);
  const slug = slugify(f.name.value);
  const g = S.bySlug.get(slug);
  const add = $('[data-drop="add"]', d);
  const pub = $('[data-drop="publish"]', d);
  pub.textContent = S.canPublish ? "Publish for everyone" : "Set up publishing…";
  let text = S.canPublish ? "Publishing puts it on the website and in everyone's app within a few minutes." : "Add it to play it on this PC. Publishing it for everyone needs the site owner's GitHub token.";
  let bad = !slug || !f.entry.value;
  if (!slug) text = "Give the game a name.";
  else if (!f.entry.value) text = "There is nothing in it that starts the game.";
  else if (g && !g.uploaded && !g.local) { text = `“${g.name}” is already a game on the site: give this one another name.`; bad = true; }
  else if (g) {
    const next = Math.max((latest(g) || {}).version || 0, (g.installed || {}).version || 0) + 1;
    text = `This becomes version ${next} of ${g.name}. ${g.uploaded ? "Everyone who installed it is offered the update once you publish it." : "It replaces your copy."}`;
  }
  note.textContent = text;
  note.classList.toggle("warn", bad);
  add.disabled = bad || DROP.busy;
  pub.disabled = (bad && S.canPublish) || DROP.busy;
}

function dropDetails() {
  const f = $("#drop form");
  return { name: f.name.value.trim(), entry: f.entry.value, description: f.description.value.trim(), presentation: f.presentation.value, author: f.author.value, notes: f.notes.value.trim() };
}

async function dropCommit(kind) {
  const d = $("#drop");
  const status = $(".drop-status", d);
  if (kind === "publish" && !S.canPublish) return openPublishSetup();
  DROP.busy = true;
  paintDropNote();
  status.className = "drop-status good";
  status.textContent = kind === "publish" ? "Publishing… keep the app open." : "Adding it to your library…";
  try {
    let slug;
    if (kind === "publish") {
      const p = await invoke("drop_publish", { details: dropDetails() });
      slug = p.slug;
      toast(`Published ${dropDetails().name} version ${p.version}. It appears on the site and in everyone's app in a few minutes.`);
    } else {
      slug = await invoke("drop_add", { details: dropDetails() });
      toast(`${dropDetails().name} is in your library.`);
    }
    d.close();
    await load(false);
    paintTabs();
    openGame(slug);
  } catch (e) {
    status.className = "drop-status";
    status.textContent = String(e);
    $(".drop-progress", d).hidden = true;
  } finally {
    DROP.busy = false;
    if (d.open) paintDropNote();
  }
}

function onPublish(p) {
  const box = $("#drop .drop-progress");
  if (!box) return;
  box.hidden = p.phase === "done";
  const pct = p.total ? Math.min(100, (100 * p.done) / p.total) : 0;
  $(".bar", box).classList.toggle("busy", p.phase === "pack");
  $(".bar i", box).style.width = p.phase === "pack" ? "100%" : `${pct}%`;
  $("span", box).textContent = p.phase === "pack" ? "Packing the game…" : `Uploading: ${mb(p.done)} of ${mb(p.total)}`;
}

function openPublishSetup() {
  const d = $("#pub");
  $("form", d).reset();
  $(".pub-status", d).textContent = S.canPublish ? "This PC can publish already. Save another token to replace it." : "";
  $(".pub-status", d).className = "pub-status good";
  $('[data-pub="forget"]', d).hidden = !S.canPublish;
  d.showModal();
}

async function publishSave() {
  const d = $("#pub");
  const status = $(".pub-status", d);
  const token = $("input", d).value.trim();
  if (!token) { status.className = "pub-status"; status.textContent = "Paste the token first."; return; }
  status.className = "pub-status good";
  status.textContent = "Checking it with GitHub…";
  try {
    const login = await invoke("publish_setup", { token });
    S.canPublish = true;
    d.close();
    toast(`This PC can now publish games${login ? ` (as ${login})` : ""}.`);
    if ($("#drop").open) paintDropNote();
  } catch (e) {
    status.className = "pub-status";
    status.textContent = String(e);
  }
}

$("#drop").addEventListener("input", (e) => { if (e.target.name === "name" || e.target.name === "entry") paintDropNote(); });
$("#drop").addEventListener("click", (e) => { const b = e.target.closest("[data-drop]"); if (b && !b.disabled) dropCommit(b.dataset.drop); });
$("#drop").addEventListener("cancel", (e) => { if (DROP.busy) e.preventDefault(); });
$("#pub").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-pub]");
  if (!b) return;
  if (b.dataset.pub === "save") return publishSave();
  await invoke("publish_forget");
  S.canPublish = false;
  $("#pub").close();
  toast("The token is forgotten: this PC can no longer publish.");
  if ($("#drop").open) paintDropNote();
});

// ---------- engine feedback: notes about RedEngine itself, not one game

const NOTE_KINDS = [["tip", "Tip"], ["idea", "Idea"], ["bug", "Bug"], ["other", "Other"]];
const NOTES_KEY = "engine-notes-sent";

function feedbackView() {
  const kinds = NOTE_KINDS.map(([v, l], i) => `<label><input type="radio" name="kind" value="${v}"${i === 0 ? " checked" : ""}><span>${l}</span></label>`).join("");
  return `<section class="feedback"><h1>Engine feedback</h1>
    <p class="intro">Notes about <strong>RedEngine</strong> itself rather than one game: how its games feel to play, what the engine could do better, tips for the people building it, a bug you keep meeting in several games. Every note is read.</p>
    <form class="rv-form note-form"><h3>Leave a note</h3>
      <fieldset class="note-kind"><legend>What kind of note?</legend><div>${kinds}</div></fieldset>
      <label>Your note<textarea name="text" maxlength="2000" rows="5" placeholder="For example: the camera turns too fast with a gamepad in every 3D game."></textarea></label>
      <label><span>Your name <span class="fine">(optional)</span></span><input name="name" maxlength="40"></label>
      <p class="fine">No account needed. Notes are public and go to the engine's developers. Please leave out links. Yours shows here within about half an hour.</p>
      <p><button class="btn primary" type="submit">Send note</button> <span class="rv-status" role="status"></span></p>
    </form>
    <h2 class="section">Notes so far <span class="count" id="n-notes"></span></h2><div class="rv-list" id="notes"><p class="fine">Loading the notes…</p></div></section>`;
}

function ownNotes() {
  try { const v = JSON.parse(localStorage.getItem(NOTES_KEY) || "[]"); return Array.isArray(v) ? v : []; } catch (_) { return []; }
}

function noteCard(n, pending) {
  const label = (NOTE_KINDS.find(([v]) => v === n.kind) || [n.kind, n.kind])[1];
  const meta = pending ? "your note: it shows for everyone within about half an hour" : `${h(day(n.date))}${n.source === "app" ? " · in the app" : ""}`;
  return `<article class="rv note${pending ? " pending" : ""}"><header><span class="kind ${h(n.kind)}">${h(label)}</span><span><strong>${h(n.name || "Anonymous player")}</strong> <span class="fine">${meta}</span></span></header>
    <p>${h(n.text).replace(/\n/g, "<br>")}</p></article>`;
}

function paintNotes() {
  const list = $("#notes");
  if (!list) return;
  const e = RV.data && RV.data.engine;
  const published = (e && e.notes) || [];
  const own = ownNotes().filter((o) => !published.some((n) => n.text === o.text));
  try { localStorage.setItem(NOTES_KEY, JSON.stringify(own)); } catch (_) { /* fine */ }
  $("#n-notes").textContent = (e && e.count) || "";
  list.innerHTML = own.map((n) => noteCard(n, true)).join("") + published.map((n) => noteCard(n, false)).join("")
    || `<p class="fine">${RV.data ? "No notes yet: be the first." : "The notes could not be loaded right now."}</p>`;
}

async function loadNotes() {
  try {
    if (!RV.data || Date.now() - RV.at > 120000) {
      RV.data = await invoke("reviews_published");
      RV.at = Date.now();
    }
  } catch (_) { /* paintNotes says so */ }
  paintNotes();
}

async function sendNote(form) {
  const f = new FormData(form);
  const status = $(".rv-status", form);
  const note = { kind: String(f.get("kind") || ""), text: String(f.get("text") || "").trim(), name: String(f.get("name") || "").trim() };
  if (note.text.length < 10) { status.textContent = "Write a little more (at least a sentence)."; return; }
  if (RV_LINK.test(`${note.text} ${note.name}`)) { status.textContent = "Please leave out links (they are not accepted)."; return; }
  const btn = $("button", form);
  btn.disabled = true;
  status.textContent = "Sending…";
  try {
    await invoke("note_send", { note });
    try { localStorage.setItem(NOTES_KEY, JSON.stringify([note, ...ownNotes()].slice(0, 5))); } catch (_) { /* fine */ }
    form.reset();
    status.textContent = "Thank you! Your note is on its way.";
    paintNotes();
  } catch (e) {
    status.textContent = String(e);
  } finally {
    btn.disabled = false;
  }
}

document.addEventListener("submit", (e) => {
  const form = e.target.closest(".note-form");
  if (!form) return;
  e.preventDefault();
  sendNote(form);
});

// ---------- start

(async function start() {
  await listen("job", onJob);
  await listen("launcher", (p) => {
    S.updateState = p;
    paintTabs();
    paintBanners();
  });
  await listen("close-requested", async () => {
    const n = (S.active ? 1 : 0) + S.queue.length;
    const quit = await ask("Quit while downloading?", `<p>${plural(n, "game is", "games are")} still downloading. Quitting stops ${n === 1 ? "it" : "them"}; start again any time.</p>`, "Quit", "Keep downloading");
    if (quit) invoke("quit");
  });
  await listen("publish", onPublish);
  // Files dragged over the window (the window's own drag and drop: the page gets the paths, not the files).
  await listen("tauri://drag-enter", () => { if (!document.querySelector("dialog[open]")) $("#dropzone").hidden = false; });
  await listen("tauri://drag-leave", () => { $("#dropzone").hidden = true; });
  await listen("tauri://drag-drop", (p) => { $("#dropzone").hidden = true; if (p && p.paths && p.paths.length) dropped(p.paths); });
  await load(false);
  paintAll();
  setTimeout(checkUpdate, 1500);
  setInterval(checkUpdate, 4 * 3600 * 1000);
  // New games and updates appear while the launcher stays open.
  setInterval(async () => { await load(true); paintTabs(); paintBanners(); if (!S.slug && S.view === "games") keepScroll(paintGrid); else changed(S.slug || ""); }, 30 * 60 * 1000);
})();
