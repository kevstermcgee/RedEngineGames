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
  return `<div class="badges">${g.retired ? "" : who + pres}${online}${retired}</div>`;
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

/** The main button(s) for a game. `big` is the game's own page. */
function actHtml(g, big) {
  const s = h(g.slug);
  const size = big ? " big" : "";
  if (S.jobs.has(g.slug)) return jobHtml(g.slug);
  const v = latest(g);
  const st = state(g);
  const starting = S.playing.has(g.slug);
  const playBtn = `<button class="btn play${size}" data-act="play" data-slug="${s}"${starting ? " disabled" : ""}>${starting ? "Starting…" : "&#x25B6; Play"}</button>`;
  if (st === "update_available") {
    const upd = `<button class="btn primary${size}" data-act="install" data-slug="${s}">Update <span class="sub">v${g.status.latest} · ${mb(v.zip.size)}</span></button>`;
    return big ? playBtn + upd : upd + `<button class="btn link" data-act="play" data-slug="${s}" title="Play the installed version">Play</button>`;
  }
  if (st === "installed") return playBtn;
  if (!v) return `<button class="btn${size}" disabled>Not available</button>`;
  return `<button class="btn primary${size}" data-act="install" data-slug="${s}">Install <span class="sub">${mb(v.zip.size)}</span></button>`;
}

function ownedHtml(g) {
  const st = state(g);
  if (st === "installed") return `<span class="owned">Installed</span>`;
  if (st === "update_available") return `<span class="owned upd">Update ready</span>`;
  return "";
}

function card(g) {
  return `<article class="card" data-open="${h(g.slug)}">
    ${shot(thumb(g), g.name, `<span data-owned-for="${h(g.slug)}">${ownedHtml(g)}</span>`)}
    <div class="body">${badges(g)}<h3>${h(g.name)}</h3><p class="tagline">${h(tagline(g))}</p>
    <div class="act" data-act-for="${h(g.slug)}">${actHtml(g, false)}</div></div></article>`;
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
  return `<p class="intro">Every game says who designed it. <strong>Human-designed</strong> games were designed by a person, and each page shows the prompt that made it.
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
      <button class="btn primary big" data-view-go="games">Browse the games</button></div>`;
  }
  const ups = updatable();
  const busy = ups.filter((g) => S.jobs.has(g.slug)).length;
  const upAll = ups.length ? `<button class="btn primary" data-act="update-all"${busy === ups.length ? " disabled" : ""}>Update all <span class="sub">${ups.length}</span></button>` : "";
  const rows = mine.map((g) => {
    const i = g.installed || {};
    const st = state(g);
    const meta = st === "update_available" ? `<p class="meta upd">Version ${i.version} installed · version ${g.status.latest} is ready</p>` : `<p class="meta">Version ${i.version}${g.retired ? "" : " · up to date"}</p>`;
    return `<div class="row" data-open="${h(g.slug)}">${shot(thumb(g), g.name)}
      <div><h3>${h(g.name)}</h3>${badges(g)}${meta}<p class="meta">${i.played ? `Last played ${h(i.played)}` : "Not played yet"}</p></div>
      <div class="act" data-act-for="${h(g.slug)}">${actHtml(g, false)}</div></div>`;
  }).join("");
  return `<div class="lib-head"><h2>Installed games <span class="count">${mine.length}</span></h2>${upAll}</div><div class="rows">${rows}</div>`;
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
      const again = r.phase === "done" ? actHtml(g, false) : state(g) !== "installed" && latest(g) ? `<button class="btn" data-act="install" data-slug="${h(g.slug)}">Try again</button>` : "";
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
  secs.push(["gallery", "Gallery"], ["origin", g.author === "ai" ? "Why this game exists" : "The prompt"], ["versions", "Versions"]);
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
  ${versionsHtml(g)}
  </div>`;
}

function versionsHtml(g) {
  const mine = g.installed && g.installed.version;
  const vs = (g.versions || []).map((v) => `<div class="v"><strong>Version ${v.version}</strong><span class="fine">${h(v.released)} · ${mb(v.zip.size)}</span>${v.version === mine ? `<span class="tag">Installed</span>` : ""}
    ${v.notes && v.notes.length ? `<ul>${v.notes.map((x) => `<li>${h(x)}</li>`).join("")}</ul>` : ""}</div>`).join("");
  return `<section id="versions"><h2>Versions</h2>${vs ? `<div class="versions">${vs}</div><p class="fine">The launcher always installs the newest version and keeps it up to date.</p>` : `<p class="fine">No version of this game is on the site.</p>`}</section>`;
}

function factsHtml(g) {
  const v = latest(g);
  const i = g.installed;
  const rows = [];
  if (i) rows.push(["Installed", `version ${i.version}${i.installed ? ` on ${h(i.installed)}` : ""}`], ["Last played", i.played ? h(i.played) : "not yet"]);
  if (v) rows.push(["Latest", `version ${v.version}, ${h(v.released)}`], ["Download", mb(v.zip.size)]);
  if (g.added) rows.push(["On the site since", h(g.added)]);
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
  const body = g.wiki ? wikiHtml(g) : g.retired
    ? `<p class="fine">This game has been taken off the site. Your installed copy still plays; once you uninstall it, it cannot be installed again.</p>`
    : `<div class="wiki"><p class="fine">This game has no wiki page yet.</p>${versionsHtml(g)}</div>`;
  return `<button class="btn link back" data-act="back">&#x2039; Back</button>
  <section class="hero">
    <div ${first ? `data-zoom="hero" data-src="${h(hero)}" data-caption="${h(first.caption)}"` : ""}>${shot(hero, g.name)}</div>
    <div><h1>${h(g.name)}</h1>${badges(g)}<p class="lead">${h(tagline(g))}</p>
      <div class="act" data-act-for="${h(g.slug)}" data-big="1">${actHtml(g, true)}</div>
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
  } else if (S.view === "library") {
    main.innerHTML = libraryView();
  } else if (S.view === "downloads") {
    main.innerHTML = downloadsView();
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
  document.querySelectorAll(`[data-act-for="${CSS.escape(slug)}"]`).forEach((el) => { if (!el.dataset.finished) el.innerHTML = actHtml(g, !!el.dataset.big); });
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
  if (scroll) return document.getElementById(scroll.dataset.scroll).scrollIntoView({ behavior: "smooth" });
  const act = t.closest("[data-act]");
  if (act) {
    e.stopPropagation();
    const slug = act.dataset.slug;
    switch (act.dataset.act) {
      case "install": return enqueue(slug);
      case "cancel": return cancel(slug);
      case "play": return play(slug);
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
  if ($("#dialog").open) return;
  const typing = /INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName);
  if (e.key === "Escape" && S.slug) back();
  else if (e.key === "/" && !typing && S.view === "games" && !S.slug) { e.preventDefault(); $("#q").focus(); }
  else if (e.key === "F5") { e.preventDefault(); refresh(); }
});

// The mouse's back button.
document.addEventListener("mouseup", (e) => { if (e.button === 3 && S.slug) back(); });

// A picture that cannot load (offline) leaves a plain panel instead of a broken-image icon.
document.addEventListener("error", (e) => { if (e.target.tagName === "IMG") e.target.classList.add("broken"); }, true);

// No browser context menu or text-selection look on the chrome, like any desktop app.
document.addEventListener("contextmenu", (e) => { if (!e.target.closest("input, blockquote, .wiki p, .wiki li")) e.preventDefault(); });

async function refresh() {
  await load(true);
  paintAll();
  checkUpdate();
}

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
  await load(false);
  paintAll();
  setTimeout(checkUpdate, 1500);
  setInterval(checkUpdate, 4 * 3600 * 1000);
  // New games and updates appear while the launcher stays open.
  setInterval(async () => { await load(true); paintTabs(); paintBanners(); if (!S.slug && S.view === "games") keepScroll(paintGrid); else changed(S.slug || ""); }, 30 * 60 * 1000);
})();
