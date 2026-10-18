// A stand-in for the window (app/src/main.rs) so the page can be tested in a plain browser: the same commands and events, backed by
// `window.__MOCK__` = {catalog, installed: {slug: version}, update: Latest | null, offline, fail: [slug], ms}. Every call is recorded in
// `window.__CALLS__`.
(function () {
  const M = window.__MOCK__;
  const calls = (window.__CALLS__ = []);
  const handlers = {};
  const lib = {};
  const cancelled = new Set();
  for (const [slug, version] of Object.entries(M.installed || {})) {
    const g = M.catalog.games.find((x) => x.slug === slug);
    lib[slug] = { name: g.name, version, dir: `games/${slug}/v${version}`, installed: "2026-10-01", played: "" };
  }
  const emit = (name, payload) => (handlers[name] || []).forEach((f) => f({ event: name, payload }));
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const status = (g) => {
    const i = lib[g.slug];
    const l = g.versions[0];
    if (!i) return { state: "not_installed" };
    if (l && l.version > i.version) return { state: "update_available", version: i.version, latest: l.version };
    return { state: "installed", version: i.version };
  };
  const commands = {
    overview() {
      const games = M.offline && M.noCache ? [] : M.catalog.games.map((g) => ({ ...g, status: status(g), installed: lib[g.slug] || null }));
      return { games, offline: !!M.offline, error: M.offline ? "could not reach https://kevstermcgee.github.io/RedEngineGames/catalog.json: dns failed" : null, launcher_version: "0.1.0", site: "https://kevstermcgee.github.io/RedEngineGames/" };
    },
    async install({ slug }) {
      const g = M.catalog.games.find((x) => x.slug === slug);
      const v = g.versions[0];
      const total = v.zip.size;
      for (let i = 0; i <= 10; i++) {
        if (cancelled.delete(slug)) {
          emit("job", { slug, phase: "cancelled", done: 0, total: 0, message: "" });
          throw "cancelled";
        }
        emit("job", { slug, phase: "download", done: Math.round((total * i) / 10), total, message: "" });
        await sleep(M.ms || 60);
      }
      if ((M.fail || []).includes(slug)) {
        const message = `the download of ${g.name} was damaged (its checksum did not match); try again`;
        emit("job", { slug, phase: "error", done: 0, total: 0, message });
        throw message;
      }
      emit("job", { slug, phase: "unpack", done: total, total, message: "" });
      await sleep(M.ms || 60);
      lib[slug] = { name: g.name, version: v.version, dir: `games/${slug}/v${v.version}`, installed: "2026-10-18", played: "" };
      emit("job", { slug, phase: "done", done: 0, total: 0, message: "" });
    },
    cancel({ slug }) { cancelled.add(slug); },
    uninstall({ slug }) { delete lib[slug]; },
    play({ slug }) { if (!lib[slug]) throw `${slug} is not installed`; lib[slug].played = "2026-10-18"; },
    open() {},
    launcher_update() { if (M.offline) throw "offline"; return M.update || null; },
    async launcher_update_apply() {
      const total = M.update.installer.size;
      for (let i = 0; i <= 5; i++) {
        emit("launcher", { slug: "", phase: "download", done: Math.round((total * i) / 5), total, message: "" });
        await sleep(M.ms || 60);
      }
      emit("launcher", { slug: "", phase: "installing", done: 0, total: 0, message: "" });
      return new Promise(() => {}); // The real launcher quits here.
    },
    quit() {},
  };
  window.__TAURI__ = {
    core: {
      async invoke(cmd, args) {
        calls.push([cmd, args || {}]);
        if (!commands[cmd]) throw `unknown command ${cmd}`;
        return commands[cmd](args || {});
      },
    },
    event: {
      async listen(name, f) {
        (handlers[name] = handlers[name] || []).push(f);
        return () => {};
      },
    },
  };
  window.__EMIT__ = emit;
})();
