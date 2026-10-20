"""The per-game wiki: what a game is, its rules, story, characters and pictures, and why it exists.

A game's page is data: `site/wiki/<slug>/wiki.json` plus the PNGs it names beside it. A page whose RedEngine playable names a `page` folder is published from there
(with `thumb.png` as `site/thumbs/<slug>.png`) by RedEngine's content sync, which checks it against these rules first: edit it in RedEngine, not here. `problems()` is the rule every page must meet; `site/generate.py` fails the build on a
page that breaks it, and on a game that has no page and is not on `site/wiki-pending.json` (the games that predate the wiki: remove a slug from that list when its page lands).

wiki.json:
  tagline        one sentence
  overview       what the game is and what makes it different (at least 200 characters)
  story          the setting and what is going on (at least 150 characters)
  goal           how you win and how you lose, in a sentence or two
  rules          list of at least 3 rules, one per line
  controls       list of {input, action}
  characters     list of at least 1 {name, role, description, image}: everyone and everything you meet (player, enemies, helpers, key objects); `image` is a file in the folder
  tips           optional list of strings
  gallery        list of at least 3 {image, caption}: different moments of play, not three copies of one view
  why_made       AI-designed games only: why the AI chose to make this game (at least 100 characters)
  why_made_note  optional: where `why_made` comes from, when it was not written by the AI at the time (e.g. reconstructed from its design notes)
  prompt         human-designed games only: the prompt that created the game, exactly as written (several prompts: separate them with a line of their own)
  prompt_source  optional: where and when the prompt was given
  prompt_unavailable  instead of `prompt` when it was not recorded: say so honestly and say what is known (at least 40 characters)

Pictures are PNG or JPEG. An entry may carry a `shot` saying how its picture was drawn (`site/wiki_build.py` draws them); the page ignores it.
"""
import html
from pathlib import Path

e = html.escape
MIN = {"overview": 200, "story": 150, "why_made": 100}
MIN_RULES, MIN_GALLERY, MIN_CHARACTERS = 3, 3, 1


def text_ok(v, n=1) -> bool:
    return isinstance(v, str) and len(v.strip()) >= n


def problems(data, author: str, folder: Path) -> list[str]:
    """Everything wrong with a wiki page, as sentences a person can act on; an empty list means it is complete."""
    out = []
    if not isinstance(data, dict):
        return ["wiki.json must be a JSON object"]
    for key in ("tagline", "overview", "story", "goal"):
        if not text_ok(data.get(key), MIN.get(key, 1)):
            out.append(f"`{key}` is missing" + (f" or shorter than {MIN[key]} characters" if key in MIN else ""))
    rules = data.get("rules")
    if not (isinstance(rules, list) and len(rules) >= MIN_RULES and all(text_ok(r) for r in rules)):
        out.append(f"`rules` needs at least {MIN_RULES} non-empty rules")
    controls = data.get("controls")
    if not (isinstance(controls, list) and controls and all(isinstance(c, dict) and text_ok(c.get("input")) and text_ok(c.get("action")) for c in controls)):
        out.append("`controls` needs at least one {input, action}")

    def image_ok(name):
        if not (isinstance(name, str) and "/" not in name and "\\" not in name and (folder / name).is_file()):
            return False
        head = (folder / name).read_bytes()[:8]
        return head == b"\x89PNG\r\n\x1a\n" or head[:3] == b"\xff\xd8\xff"

    chars = data.get("characters")
    if not (isinstance(chars, list) and len(chars) >= MIN_CHARACTERS):
        out.append(f"`characters` needs at least {MIN_CHARACTERS} entry")
    else:
        for i, c in enumerate(chars):
            if not (isinstance(c, dict) and all(text_ok(c.get(k)) for k in ("name", "role", "description"))):
                out.append(f"character {i + 1} needs name, role and description")
            elif not image_ok(c.get("image")):
                out.append(f"character `{c['name']}` needs an `image` that is a PNG or JPEG in the page's folder")
    gallery = data.get("gallery")
    if not (isinstance(gallery, list) and len(gallery) >= MIN_GALLERY):
        out.append(f"`gallery` needs at least {MIN_GALLERY} pictures of different moments")
    else:
        for i, g in enumerate(gallery):
            if not (isinstance(g, dict) and text_ok(g.get("caption")) and image_ok(g.get("image"))):
                out.append(f"gallery picture {i + 1} needs a caption and an `image` that is a PNG or JPEG in the page's folder")
        names = [g.get("image") for g in gallery if isinstance(g, dict)]
        if len(set(names)) != len(names):
            out.append("`gallery` repeats a picture")
    if author == "ai":
        if not text_ok(data.get("why_made"), MIN["why_made"]):
            out.append(f"an AI-designed game needs `why_made` (why the AI chose this game, at least {MIN['why_made']} characters)")
    elif not text_ok(data.get("prompt")) and not text_ok(data.get("prompt_unavailable"), 40):
        out.append("a human-designed game needs `prompt` (the prompt that created it) or, when it was not recorded, `prompt_unavailable` saying so (at least 40 characters)")
    return out


def paras(text: str) -> str:
    return "".join(f"<p>{e(p.strip())}</p>" for p in text.split("\n") if p.strip())


def render(data: dict, author: str, reviews: dict | None = None) -> str:
    """The wiki sections of a game's page, with a contents list that links to each. `reviews` ({game, name, version, send, read}) adds the
    player reviews: the score and every review, and a form to leave one (`reviews_section`)."""
    secs = [("overview", "Overview"), ("story", "Story"), ("play", "How to play"), ("characters", "Characters"), ("gallery", "Gallery"), ("origin", "Why this game exists" if author == "ai" else "The prompt")]
    if reviews:
        secs.append(("reviews", "Player reviews"))
    if data.get("tips"):
        secs.insert(4, ("tips", "Tips"))
    toc = "".join(f'<a href="#{i}">{t}</a>' for i, t in secs)
    controls = "".join(f"<tr><td><kbd>{e(c['input'])}</kbd></td><td>{e(c['action'])}</td></tr>" for c in data["controls"])
    chars = "".join(f'<figure class="char"><img src="{e(c["image"])}" alt="{e(c["name"])}" loading="lazy"><figcaption><strong>{e(c["name"])}</strong> <span>{e(c["role"])}</span><p>{e(c["description"])}</p></figcaption></figure>' for c in data["characters"])
    gallery = "".join(f'<figure><a href="{e(g["image"])}"><img src="{e(g["image"])}" alt="{e(g["caption"])}" loading="lazy"></a><figcaption>{e(g["caption"])}</figcaption></figure>' for g in data["gallery"])
    tips = f'<section id="tips"><h2>Tips</h2><ul>{"".join(f"<li>{e(t)}</li>" for t in data["tips"])}</ul></section>' if data.get("tips") else ""
    note = lambda key: f'<p class="fine">{e(data[key])}</p>' if text_ok(data.get(key)) else ""   # noqa: E731
    if author == "ai":
        intro = "Why it was made:" if text_ok(data.get("why_made_note")) else "Its reason, in its words:"
        origin = f'<section id="origin"><h2>Why this game exists</h2><p class="fine">This game was designed by an AI on its own. {intro}</p><blockquote>{paras(data["why_made"])}</blockquote>{note("why_made_note")}</section>'
    elif text_ok(data.get("prompt")):
        origin = f'<section id="origin"><h2>The prompt</h2><p class="fine">This game was designed by a person. The prompt that created it:</p><blockquote class="prompt">{e(data["prompt"].strip())}</blockquote>{note("prompt_source")}</section>'
    else:
        origin = f'<section id="origin"><h2>The prompt</h2><p class="fine">This game was designed by a person.</p><p>{e(data["prompt_unavailable"])}</p></section>'
    return f'''
  <nav class="toc" aria-label="On this page"><strong>Contents</strong>{toc}</nav>
  <section id="overview"><h2>Overview</h2><p class="lead">{e(data["tagline"])}</p>{paras(data["overview"])}</section>
  <section id="story"><h2>Story</h2>{paras(data["story"])}</section>
  <section id="play"><h2>How to play</h2><p><strong>Goal.</strong> {e(data["goal"])}</p><h3>Rules</h3><ol>{"".join(f"<li>{e(r)}</li>" for r in data["rules"])}</ol>
    <h3>Controls</h3><table class="controls"><tr><th>Input</th><th>Does</th></tr>{controls}</table></section>
  <section id="characters"><h2>Characters</h2><div class="chars">{chars}</div></section>{tips}
  <section id="gallery"><h2>Gallery</h2><div class="gallery">{gallery}</div></section>
  {origin}{reviews_section(**reviews) if reviews else ""}'''


def reviews_section(game: str, name: str, version: int, send: str, read: str) -> str:
    """Player reviews: the average score, every review, and a form to leave one, anonymously. The page reads the reviews from the engine repo's
    `docs/player-reviews/public.json` and posts a new one to the relay (`send`), where RedEngine's `scripts/player_reviews.py` collects it."""
    scores = "".join(f'<label><input type="radio" name="score" value="{n}" required><span>{n}</span></label>' for n in range(1, 11))
    return f'''
  <section id="reviews" class="reviews" data-game="{e(game)}" data-name="{e(name)}" data-version="{version}" data-send="{e(send)}" data-read="{e(read)}">
    <h2>Player reviews</h2>
    <div class="rv-summary"><span class="rv-avg" aria-hidden="true">&ndash;</span><span class="rv-count">Loading the reviews&hellip;</span></div>
    <form class="rv-form">
      <h3>Review {e(name)}</h3>
      <fieldset class="rv-score"><legend>Your score out of 10</legend><div>{scores}</div></fieldset>
      <label>What did you enjoy?<textarea name="liked" maxlength="2000" rows="3"></textarea></label>
      <label>What didn't you enjoy?<textarea name="disliked" maxlength="2000" rows="3"></textarea></label>
      <label><span>Your name <span class="fine">(optional)</span></span><input name="name" maxlength="40" autocomplete="nickname"></label>
      <p class="fine">No account needed. Your review is public and goes to the engine's developers too, so the next games get better. Please leave out links. It shows here within about half an hour.</p>
      <p><button type="submit">Send review</button> <span class="rv-status" role="status"></span></p>
    </form>
    <div class="rv-list"></div>
  </section>
  <script>{REVIEWS_JS}</script>'''


def engine_feedback_section(send: str, read: str) -> str:
    """Engine feedback: notes about RedEngine itself rather than one game (a tip, an idea, a bug, anything else), sent anonymously to the same
    relay as reviews (`{"v": 1, "about": "engine", ...}`) and shown from `public.json`'s `engine`, as in the app."""
    kinds = "".join(f'<label><input type="radio" name="kind" value="{v}"{" checked" if i == 0 else ""}><span>{l}</span></label>'
                    for i, (v, l) in enumerate([("tip", "Tip"), ("idea", "Idea"), ("bug", "Bug"), ("other", "Other")]))
    return f'''
  <section id="engine-notes" class="reviews" data-send="{e(send)}" data-read="{e(read)}">
    <form class="rv-form">
      <h3>Leave a note</h3>
      <fieldset class="note-kind"><legend>What kind of note?</legend><div>{kinds}</div></fieldset>
      <label>Your note<textarea name="text" maxlength="2000" rows="5" placeholder="For example: the camera turns too fast with a gamepad in every 3D game."></textarea></label>
      <label><span>Your name <span class="fine">(optional)</span></span><input name="name" maxlength="40" autocomplete="nickname"></label>
      <p class="fine">No account needed. Notes are public and go to the engine's developers. Please leave out links. Yours shows here within about half an hour.</p>
      <p><button type="submit">Send note</button> <span class="rv-status" role="status"></span></p>
    </form>
    <h2>Notes so far</h2>
    <div class="rv-list"><p class="fine">Loading the notes&hellip;</p></div>
  </section>
  <script>{ENGINE_NOTES_JS}</script>'''


# The page's side of engine feedback: the same rules as the app (`reviews::note_problem`) and the collector.
ENGINE_NOTES_JS = r'''
(function () {
  var sec = document.getElementById("engine-notes");
  if (!sec || !window.fetch) return;
  var d = sec.dataset, form = sec.querySelector(".rv-form"), status = sec.querySelector(".rv-status"), list = sec.querySelector(".rv-list");
  var LINK = /https?:\/\/|www\.|\b[a-z0-9-]+\.(com|net|org|io|ru|xyz|top|info|biz)\b/i, KEY = "engine-notes-sent";
  var LABEL = {tip: "Tip", idea: "Idea", bug: "Bug", other: "Other"};
  function h(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]; }); }
  function mine() { try { var v = JSON.parse(localStorage.getItem(KEY) || "[]"); return Array.isArray(v) ? v : []; } catch (e) { return []; } }
  function card(n, pending) {
    return '<article class="rv note' + (pending ? " pending" : "") + '"><header><span class="kind ' + h(n.kind) + '">' + h(LABEL[n.kind] || n.kind) + "</span><span><strong>" + h(n.name || "Anonymous player") + "</strong> " +
      '<span class="fine">' + (pending ? "your note: it shows for everyone within about half an hour" : h(n.date) + (n.source === "app" ? " · in the app" : "")) + "</span></span></header><p>" + h(n.text).replace(/\n/g, "<br>") + "</p></article>";
  }
  var shown = null;
  function paint() {
    var notes = (shown && shown.notes) || [];
    var own = mine().filter(function (o) { return !notes.some(function (n) { return n.text === o.text; }); });
    try { localStorage.setItem(KEY, JSON.stringify(own)); } catch (e) {}
    list.innerHTML = own.map(function (n) { return card(n, true); }).join("") + notes.map(function (n) { return card(n, false); }).join("") || '<p class="fine">No notes yet: be the first.</p>';
  }
  fetch(d.read, {cache: "no-cache"}).then(function (r) { return r.ok ? r.json() : null; }).then(function (all) { shown = all ? all.engine : null; paint(); })
    .catch(function () { list.innerHTML = '<p class="fine">The notes could not be loaded right now.</p>'; });
  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var f = new FormData(form), note = {v: 1, about: "engine", kind: f.get("kind") || "other", text: (f.get("text") || "").trim(), name: (f.get("name") || "").trim(), source: "site"};
    if (note.text.length < 10) { status.textContent = "Write a little more (at least a sentence)."; return; }
    if (LINK.test(note.text + " " + note.name)) { status.textContent = "Please leave out links (they are not accepted)."; return; }
    var btn = form.querySelector("button"); btn.disabled = true; status.textContent = "Sending\u2026";
    fetch(d.send + "?title=" + encodeURIComponent("Engine feedback: " + note.kind), {method: "POST", body: JSON.stringify(note)}).then(function (r) {
      if (!r.ok) throw new Error(r.status === 429 ? "Too many notes from your connection just now; try again in a minute." : "The feedback service answered " + r.status + "; try again later.");
      try { localStorage.setItem(KEY, JSON.stringify([{kind: note.kind, text: note.text, name: note.name}].concat(mine()).slice(0, 5))); } catch (e) {}
      form.reset(); status.textContent = "Thank you! Your note is on its way."; if (shown !== undefined) paint();
    }).catch(function (e) { status.textContent = e.message && /notes|service/.test(e.message) ? e.message : "Could not send it (are you online?); try again."; })
      .then(function () { btn.disabled = false; });
  });
})();
'''


# The page's side of player reviews. The same rules as `scripts/player_reviews.py` in RedEngine (the judge): a score, a write-up, no links.
REVIEWS_JS = r'''
(function () {
  var sec = document.getElementById("reviews");
  if (!sec || !window.fetch) return;
  var d = sec.dataset, form = sec.querySelector(".rv-form"), status = sec.querySelector(".rv-status");
  var LINK = /https?:\/\/|www\.|\b[a-z0-9-]+\.(com|net|org|io|ru|xyz|top|info|biz)\b/i;
  var KEY = "rv-sent-" + d.game;
  function h(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]; }); }
  function text(s) { return h(s).replace(/\n/g, "<br>"); }
  function mine() { try { return JSON.parse(localStorage.getItem(KEY) || "null"); } catch (e) { return null; } }
  function card(r, pending) {
    return '<article class="rv' + (pending ? " pending" : "") + '"><header><span class="rv-n">' + r.score + '<small>/10</small></span><span><strong>' + h(r.name || "Anonymous player") + "</strong> " +
      '<span class="fine">' + (pending ? "your review: it shows for everyone within about half an hour" : h(r.date) + (r.version ? " · version " + r.version : "") + (r.source === "app" ? " · in the app" : "")) + "</span></span></header>" +
      (r.liked ? '<p><span class="rv-k">Enjoyed</span>' + text(r.liked) + "</p>" : "") + (r.disliked ? '<p><span class="rv-k">Didn\u2019t enjoy</span>' + text(r.disliked) + "</p>" : "") + "</article>";
  }
  function paint(g) {
    var list = (g && g.reviews) || [], own = mine();
    if (own && list.some(function (r) { return r.liked === own.liked && r.disliked === own.disliked; })) { try { localStorage.removeItem(KEY); } catch (e) {} own = null; }
    sec.querySelector(".rv-avg").textContent = g && g.count ? g.average.toFixed(1) : "\u2013";
    sec.querySelector(".rv-count").textContent = g && g.count ? "out of 10, from " + g.count + " review" + (g.count === 1 ? "" : "s") : "No reviews yet: be the first.";
    sec.querySelector(".rv-list").innerHTML = (own ? card(own, true) : "") + list.map(function (r) { return card(r, false); }).join("");
  }
  var shown = null;
  fetch(d.read, {cache: "no-cache"}).then(function (r) { return r.ok ? r.json() : null; }).then(function (all) { shown = all && all.games ? all.games[d.game] : null; paint(shown); })
    .catch(function () { sec.querySelector(".rv-count").textContent = "The reviews could not be loaded right now."; paint(null); });
  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var f = new FormData(form), score = parseInt(f.get("score"), 10), liked = (f.get("liked") || "").trim(), disliked = (f.get("disliked") || "").trim(), name = (f.get("name") || "").trim();
    if (!(score >= 1 && score <= 10)) { status.textContent = "Pick a score from 1 to 10."; return; }
    if (liked.length < 3 && disliked.length < 3) { status.textContent = "Say a little about what you enjoyed or didn't."; return; }
    if (LINK.test(liked + " " + disliked + " " + name)) { status.textContent = "Please leave out links (they are not accepted)."; return; }
    var review = {v: 1, game: d.game, version: parseInt(d.version, 10) || null, score: score, liked: liked, disliked: disliked, name: name, source: "site"};
    var btn = form.querySelector("button"); btn.disabled = true; status.textContent = "Sending\u2026";
    fetch(d.send + "?title=" + encodeURIComponent(d.name + ": " + score + "/10"), {method: "POST", body: JSON.stringify(review)}).then(function (r) {
      if (!r.ok) throw new Error(r.status === 429 ? "Too many reviews from your connection just now; try again in a minute." : "The review service answered " + r.status + "; try again later.");
      try { localStorage.setItem(KEY, JSON.stringify({score: score, liked: liked, disliked: disliked, name: name})); } catch (e) {}
      form.reset(); status.textContent = "Thank you! Your review is on its way."; paint(shown);
    }).catch(function (e) { status.textContent = e.message && e.message.indexOf("review") !== -1 ? e.message : "Could not send it (are you online?); try again."; })
      .then(function () { btn.disabled = false; });
  });
})();
'''


WIKI_CSS = '''
.toc { display: flex; gap: 6px 16px; flex-wrap: wrap; align-items: baseline; background: var(--surface); border: 1px solid var(--card); border-radius: 8px; padding: 10px 14px; margin: 18px 0; position: sticky; top: 0; z-index: 3; }
.toc a { font-size: .9rem; }
section[id] { scroll-margin-top: 70px; }
.lead { font-size: 1.1rem; color: #F3E6EC; }
kbd { background: var(--surface); border: 1px solid var(--card); border-radius: 4px; padding: 1px 6px; font-size: .85rem; }
.chars { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }
.char { margin: 0; background: var(--card); border-radius: 8px; overflow: hidden; }
.char img, .gallery img { width: 100%; height: auto; display: block; background: var(--surface); }
.char figcaption { padding: 10px 12px; font-size: .9rem; } .char figcaption span { color: var(--muted); font-size: .8rem; } .char figcaption p { margin: 6px 0 0; }
.gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }
.gallery figure { margin: 0; } .gallery figcaption { color: var(--muted); font-size: .85rem; padding-top: 4px; }
blockquote { margin: 8px 0; padding: 4px 16px; border-left: 4px solid var(--accent); background: var(--surface); border-radius: 0 8px 8px 0; }
blockquote.prompt { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: .9rem; white-space: pre-wrap; overflow-wrap: anywhere; }
blockquote, .lead, section p { overflow-wrap: anywhere; }
.soon { color: var(--muted); font-style: italic; }
table.controls { width: 100%; table-layout: fixed; border-collapse: collapse; margin: 8px 0 18px; font-size: .92rem; }
table.controls th, table.controls td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--card); vertical-align: top; overflow-wrap: anywhere; }
table.controls th { color: var(--muted); font-weight: 500; font-size: .8rem; }
kbd { white-space: normal; }
.reviews .rv-summary { display: flex; align-items: baseline; gap: 10px; margin: 4px 0 14px; }
.rv-avg { font-size: 2.2rem; font-weight: 800; color: var(--accent); line-height: 1; }
.rv-count { color: var(--muted); }
.rv-form { background: var(--surface); border: 1px solid var(--card); border-radius: 8px; padding: 14px 16px; margin: 0 0 18px; display: grid; gap: 10px; }
.rv-form h3 { margin: 0; }
.rv-form label { display: grid; gap: 4px; font-size: .92rem; }
.rv-form textarea, .rv-form input[name=name] { background: var(--bg); color: inherit; border: 1px solid var(--card); border-radius: 6px; padding: 8px 10px; font: inherit; width: 100%; }
.rv-form p { margin: 0; }
.rv-score { border: 0; padding: 0; margin: 0; }
.rv-score legend { font-size: .92rem; margin-bottom: 6px; }
.rv-score div { display: grid; grid-template-columns: repeat(10, minmax(0, 1fr)); gap: 6px; max-width: 470px; }
.rv-score label { display: block; }
.rv-score input { position: absolute; opacity: 0; width: 1px; height: 1px; }
.rv-score span { display: flex; align-items: center; justify-content: center; height: 40px; border-radius: 6px; background: var(--card); cursor: pointer; font-weight: 700; }
.rv-score input:checked + span { background: var(--accent); color: #1C0810; }
.rv-score input:focus-visible + span { outline: 2px solid var(--accent); outline-offset: 2px; }
.rv-form button { background: var(--accent); color: #1C0810; border: 0; border-radius: 6px; padding: 10px 18px; font: inherit; font-weight: 700; cursor: pointer; }
.rv-form button:disabled { opacity: .6; }
.rv-status { color: var(--muted); font-size: .9rem; }
.rv-form .fine, .rv .fine { color: var(--muted); font-size: .85rem; }
.rv-list { display: grid; gap: 10px; }
.rv { background: var(--card); border-radius: 8px; padding: 10px 14px; }
.rv.pending { outline: 1px dashed var(--accent); }
.rv header { display: flex; gap: 12px; align-items: center; }
.rv-n { font-size: 1.4rem; font-weight: 800; color: var(--accent); white-space: nowrap; }
.rv-n small { font-size: .7rem; color: var(--muted); font-weight: 500; }
.rv p { margin: 8px 0 0; overflow-wrap: anywhere; }
.rv-k { display: block; font-size: .75rem; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
.note-kind { border: 0; padding: 0; margin: 0; }
.note-kind legend { font-size: .92rem; margin-bottom: 6px; }
.note-kind div { display: flex; gap: 8px; flex-wrap: wrap; }
.note-kind label { display: block; }
.note-kind input { position: absolute; opacity: 0; width: 1px; height: 1px; }
.note-kind span { display: inline-flex; padding: 8px 16px; border-radius: 6px; background: var(--card); cursor: pointer; font-weight: 700; }
.note-kind input:checked + span { background: var(--accent); color: #1C0810; }
.note-kind input:focus-visible + span { outline: 2px solid var(--accent); outline-offset: 2px; }
.note .kind { display: inline-block; border-radius: 4px; padding: 0 6px; font-size: .72rem; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; background: var(--accent); color: #1C0810; }
.note .kind.bug { background: #FF8A80; } .note .kind.idea { background: #9CC8FF; } .note .kind.other { background: var(--muted); }
@media (max-width: 640px) { table.versions { display: block; overflow-x: auto; } .toc { position: static; } .rv-score div { gap: 4px; } .rv-score span { height: 36px; } }
'''
