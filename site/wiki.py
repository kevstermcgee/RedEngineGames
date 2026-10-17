"""The per-game wiki: what a game is, its rules, story, characters and pictures, and why it exists.

A game's page is data: `site/wiki/<slug>/wiki.json` plus the PNGs it names beside it. `problems()` is the rule every page must meet; `site/generate.py` fails the build on a
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
  prompt         human-designed games only: the prompt that created the game, as written
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
        return isinstance(name, str) and "/" not in name and "\\" not in name and (folder / name).is_file() and (folder / name).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    chars = data.get("characters")
    if not (isinstance(chars, list) and len(chars) >= MIN_CHARACTERS):
        out.append(f"`characters` needs at least {MIN_CHARACTERS} entry")
    else:
        for i, c in enumerate(chars):
            if not (isinstance(c, dict) and all(text_ok(c.get(k)) for k in ("name", "role", "description"))):
                out.append(f"character {i + 1} needs name, role and description")
            elif not image_ok(c.get("image")):
                out.append(f"character `{c['name']}` needs an `image` that is a PNG in the page's folder")
    gallery = data.get("gallery")
    if not (isinstance(gallery, list) and len(gallery) >= MIN_GALLERY):
        out.append(f"`gallery` needs at least {MIN_GALLERY} pictures of different moments")
    else:
        for i, g in enumerate(gallery):
            if not (isinstance(g, dict) and text_ok(g.get("caption")) and image_ok(g.get("image"))):
                out.append(f"gallery picture {i + 1} needs a caption and an `image` that is a PNG in the page's folder")
        names = [g.get("image") for g in gallery if isinstance(g, dict)]
        if len(set(names)) != len(names):
            out.append("`gallery` repeats a picture")
    if author == "ai":
        if not text_ok(data.get("why_made"), MIN["why_made"]):
            out.append(f"an AI-designed game needs `why_made` (why the AI chose this game, at least {MIN['why_made']} characters)")
    elif not text_ok(data.get("prompt")):
        out.append("a human-designed game needs `prompt` (the prompt that created it)")
    return out


def paras(text: str) -> str:
    return "".join(f"<p>{e(p.strip())}</p>" for p in text.split("\n") if p.strip())


def render(data: dict, author: str) -> str:
    """The wiki sections of a game's page, with a contents list that links to each."""
    secs = [("overview", "Overview"), ("story", "Story"), ("play", "How to play"), ("characters", "Characters"), ("gallery", "Gallery"), ("origin", "Why this game exists" if author == "ai" else "The prompt")]
    if data.get("tips"):
        secs.insert(4, ("tips", "Tips"))
    toc = "".join(f'<a href="#{i}">{t}</a>' for i, t in secs)
    controls = "".join(f"<tr><td><kbd>{e(c['input'])}</kbd></td><td>{e(c['action'])}</td></tr>" for c in data["controls"])
    chars = "".join(f'<figure class="char"><img src="{e(c["image"])}" alt="{e(c["name"])}" loading="lazy"><figcaption><strong>{e(c["name"])}</strong> <span>{e(c["role"])}</span><p>{e(c["description"])}</p></figcaption></figure>' for c in data["characters"])
    gallery = "".join(f'<figure><a href="{e(g["image"])}"><img src="{e(g["image"])}" alt="{e(g["caption"])}" loading="lazy"></a><figcaption>{e(g["caption"])}</figcaption></figure>' for g in data["gallery"])
    tips = f'<section id="tips"><h2>Tips</h2><ul>{"".join(f"<li>{e(t)}</li>" for t in data["tips"])}</ul></section>' if data.get("tips") else ""
    if author == "ai":
        origin = f'<section id="origin"><h2>Why this game exists</h2><p class="fine">This game was designed by an AI on its own. Its reason, in its words:</p><blockquote>{paras(data["why_made"])}</blockquote></section>'
    else:
        origin = f'<section id="origin"><h2>The prompt</h2><p class="fine">This game was designed by a person. The prompt that created it:</p><blockquote class="prompt">{paras(data["prompt"])}</blockquote></section>'
    return f'''
  <nav class="toc" aria-label="On this page"><strong>Contents</strong>{toc}</nav>
  <section id="overview"><h2>Overview</h2><p class="lead">{e(data["tagline"])}</p>{paras(data["overview"])}</section>
  <section id="story"><h2>Story</h2>{paras(data["story"])}</section>
  <section id="play"><h2>How to play</h2><p><strong>Goal.</strong> {e(data["goal"])}</p><h3>Rules</h3><ol>{"".join(f"<li>{e(r)}</li>" for r in data["rules"])}</ol>
    <h3>Controls</h3><table class="versions"><tr><th>Input</th><th>Does</th></tr>{controls}</table></section>
  <section id="characters"><h2>Characters</h2><div class="chars">{chars}</div></section>{tips}
  <section id="gallery"><h2>Gallery</h2><div class="gallery">{gallery}</div></section>
  {origin}'''


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
blockquote.prompt { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: .9rem; white-space: pre-wrap; }
.soon { color: var(--muted); font-style: italic; }
'''
