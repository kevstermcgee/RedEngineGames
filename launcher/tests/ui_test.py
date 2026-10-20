#!/usr/bin/env python3
"""The launcher's page in Chromium, against the real catalog, with the window replaced by tests/mock_tauri.js.

    pip install playwright && python -m playwright install chromium
    python3 launcher/tests/ui_test.py [--catalog site/dist/catalog.json] [--shots DIR]

Without --catalog it reads the live site's catalog.json. Pictures come from the live site either way.
"""
import argparse
import datetime
import json
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

HERE = Path(__file__).resolve().parent
UI = HERE.parent / "ui" / "index.html"
MOCK = HERE / "mock_tauri.js"
SITE = "https://kevstermcgee.github.io/RedEngineGames/"

ap = argparse.ArgumentParser()
ap.add_argument("--catalog")
ap.add_argument("--shots")
args = ap.parse_args()
catalog = json.loads(Path(args.catalog).read_text() if args.catalog else urllib.request.urlopen(SITE + "catalog.json", timeout=30).read())
games = catalog["games"]
shots = Path(args.shots) if args.shots else None
if shots:
    shots.mkdir(parents=True, exist_ok=True)

by_size = sorted((g for g in games if g["versions"]), key=lambda g: g["versions"][0]["zip"]["size"])
small, small2, small3 = by_size[0], by_size[1], by_size[2]
old = next(g for g in by_size if len(g["versions"]) > 1 and g not in (small, small2, small3))
ai_game = next(g for g in games if g["author"] == "ai" and g.get("wiki"))
with_prompt = next(g for g in games if g["author"] == "human" and g.get("wiki", {}).get("prompt"))
without_prompt = next((g for g in games if g["author"] == "human" and g.get("wiki") and not g["wiki"].get("prompt")), None)
UPDATE = {"version": "0.2.0", "installer": {"name": "RedEngineGames-0.2.0-setup.exe", "size": 4_200_000, "sha256": "00", "url": "https://example.invalid/x"}, "notes": ["Faster downloads."]}

failures = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        failures.append(what)


def card(page, g):
    return page.locator(f'.card[data-open="{g["slug"]}"]')


def act(page, g):
    return page.locator(f'[data-act-for="{g["slug"]}"]').first


def no_overflow(page, what):
    w = page.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth, document.querySelector('main').scrollWidth, document.querySelector('main').clientWidth]")
    check(w[0] <= w[1] and w[2] <= w[3], f"no sideways scrolling: {what} {w}")


def window_still(page, what):
    """Only <main> scrolls. The window stays exactly its own height and never moves, so the top bar is never cut off."""
    w = page.evaluate("() => [scrollY, document.scrollingElement.scrollHeight, innerHeight, document.querySelector('.top').getBoundingClientRect().top]")
    check(w[0] == 0 and w[1] <= w[2] and w[3] == 0, f"the window does not scroll, only the page in it: {what} {w}")


def day(iso):
    """A catalog date as the page shows it in an American English window ("Oct 4, 2026")."""
    d = datetime.date.fromisoformat(iso)
    return f"{d:%b} {d.day}, {d.year}"


def snap(page, name, full=False):
    if shots:
        page.screenshot(path=str(shots / f"{name}.png"), full_page=full)


with sync_playwright() as p:
    browser = p.chromium.launch()

    def boot(width=1240, height=800, **mock):
        page = browser.new_page(viewport={"width": width, "height": height}, locale="en-US")
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: m.type == "error" and "Failed to load resource" not in m.text and errors.append(m.text))
        page.add_init_script(f"window.__MOCK__ = {json.dumps({'catalog': catalog, **mock})};")
        page.add_init_script(path=str(MOCK))
        page.goto(UI.as_uri())
        page.wait_for_selector(".card, .empty, .row")
        return page, errors

    # Games: every game, filters, search.
    page, errors = boot(installed={old["slug"]: min(v["version"] for v in old["versions"])})
    expect(page.locator(".card")).to_have_count(len(games))
    check(page.locator("#shown").inner_text() == f"{len(games)} games", "Games lists every game")
    page.select_option("#who", "ai")
    n_ai = sum(g["author"] == "ai" for g in games)
    expect(page.locator(".card")).to_have_count(n_ai)
    check(page.locator(".card .badge.ai").count() == n_ai and page.locator(".card .badge.human").count() == 0, f"AI-designed filter shows only the {n_ai} AI games")
    page.select_option("#who", "human")
    expect(page.locator(".card")).to_have_count(len(games) - n_ai)
    page.select_option("#who", "")
    page.select_option("#kind", "2d")
    expect(page.locator(".card")).to_have_count(sum(g["presentation"] == "2d" for g in games))
    page.select_option("#kind", "")
    page.fill("#q", ai_game["name"])
    check(card(page, ai_game).count() == 1, f"search finds {ai_game['name']}")
    page.fill("#q", "zzzz no such game")
    expect(page.locator(".empty")).to_contain_text("No game matches")
    page.click('[data-act="clear-filters"]')
    expect(page.locator(".card")).to_have_count(len(games))
    check(page.locator(f'[data-owned-for="{old["slug"]}"]').inner_text() == "Update ready", "an outdated install is marked on its card")
    page.wait_for_timeout(800)
    snap(page, "games")
    no_overflow(page, "games")

    # Install from a card: progress, then Play; a second install waits its turn and can be taken out of the queue.
    card(page, small).scroll_into_view_if_needed()
    # Slow the stand-in's downloads (~5 s) so the second game is still queued when it is cancelled, however slow the machine running this.
    page.evaluate("window.__MOCK__.ms = 400")
    act(page, small).locator('[data-act="install"]').click()
    act(page, small2).locator('[data-act="install"]').click()
    expect(act(page, small)).to_contain_text("%")
    expect(act(page, small2)).to_contain_text("Queued")
    act(page, small2).locator('[data-act="cancel"]').click()
    expect(act(page, small2).locator('[data-act="install"]')).to_be_visible()
    expect(act(page, small).locator('[data-act="play"]')).to_be_visible(timeout=10_000)
    expect(page.locator(".toast").last).to_contain_text("ready to play")
    check(page.locator(f'[data-owned-for="{small["slug"]}"]').inner_text() == "Installed", "the card says Installed")

    # A game's page: the whole wiki, pictures from the site, the picture viewer.
    page.fill("#q", ai_game["name"])
    card(page, ai_game).click()
    expect(page.locator("h1")).to_have_text(ai_game["name"])
    for sec in ("overview", "story", "play", "characters", "gallery", "origin", "versions"):
        check(page.locator(f"section#{sec}").count() == 1, f"{ai_game['name']}: the {sec} section is there")
    check(page.locator("#origin h2").inner_text() == "Why this game exists", "an AI game says why it was made")
    check(page.locator(".char").count() == len(ai_game["wiki"]["characters"]), "every character has a picture card")
    check(page.locator(".gallery figure").count() == len(ai_game["wiki"]["gallery"]), "every gallery picture is shown")
    page.evaluate("() => document.querySelectorAll('img[loading=lazy]').forEach(i => i.loading = 'eager')")
    page.wait_for_function("() => [...document.querySelectorAll('.wiki img, .hero img')].every(i => i.complete)", timeout=30_000)
    broken = page.evaluate("() => [...document.querySelectorAll('.wiki img, .hero img')].filter(i => !i.naturalWidth).map(i => i.src)")
    check(not broken, f"every picture on the page loads {broken[:3]}")
    snap(page, "game")
    no_overflow(page, "game page")
    page.locator(".gallery [data-zoom]").first.click()
    expect(page.locator("#lightbox")).to_be_visible()
    first_src = page.locator("#lightbox img").get_attribute("src")
    page.keyboard.press("ArrowRight")
    check(page.locator("#lightbox img").get_attribute("src") != first_src, "the picture viewer steps to the next picture")
    snap(page, "lightbox")
    page.keyboard.press("Escape")
    expect(page.locator("#lightbox")).to_be_hidden()
    for sec in page.locator(".toc button").evaluate_all("bs => bs.map(b => b.dataset.scroll)"):
        page.click(f'.toc [data-scroll="{sec}"]')
        page.wait_for_timeout(700)
        window_still(page, f"after the contents link to {sec}")
        gap, at_end = page.evaluate(f"""() => {{ const m = document.querySelector('main');
            return [document.getElementById('{sec}').getBoundingClientRect().top - document.querySelector('.toc').getBoundingClientRect().bottom,
                    m.scrollTop + m.clientHeight >= m.scrollHeight - 1]; }}""")
        check(0 <= gap <= 30 or at_end, f"the contents link to {sec} puts it just under the contents list ({gap:.0f}px)")
        if sec == "characters":
            snap(page, "game-characters")
    page.evaluate("() => { document.body.insertAdjacentHTML('beforeend', '<div id=\"tall\" style=\"position:absolute;top:4000px;width:4px;height:4px\"></div>'); window.scrollTo(0, 900); }")
    page.wait_for_timeout(150)
    check(page.evaluate("() => scrollY") == 0, "the window snaps back if anything ever scrolls it")
    page.evaluate("() => document.getElementById('tall').remove()")
    page.keyboard.press("Escape")
    expect(page.locator(".toolbar")).to_be_visible()

    page.fill("#q", with_prompt["name"])
    card(page, with_prompt).click()
    check(page.locator("#origin h2").inner_text() == "The prompt" and page.locator("blockquote.prompt").count() == 1, f"{with_prompt['name']}: a human game shows its prompt")
    page.click('[data-act="back"]')
    if without_prompt:
        page.fill("#q", without_prompt["name"])
        card(page, without_prompt).click()
        check(without_prompt["wiki"]["prompt_unavailable"][:40] in page.locator("#origin").inner_text(), f"{without_prompt['name']}: an honest note where the prompt was not kept")
        page.click('[data-act="back"]')
    page.fill("#q", "")

    # The library: play, update all, uninstall.
    page.click('.tabs [data-view="library"]')
    expect(page.locator(".row")).to_have_count(2)
    check("update" in page.locator("#n-library").text_content(), "the Library tab says an update is ready")
    snap(page, "library")
    no_overflow(page, "library")
    page.click('[data-act="update-all"]')
    expect(page.locator(f'.row[data-open="{old["slug"]}"] .meta').first).to_contain_text("up to date", timeout=10_000)
    page.locator(f'.row[data-open="{small["slug"]}"] [data-act="play"]').click()
    expect(page.locator(".toast").last).to_contain_text("Starting")
    check(["play", {"slug": small["slug"]}] in page.evaluate("window.__CALLS__"), "Play starts the game")
    page.locator(f'.row[data-open="{small["slug"]}"]').click()
    page.click('[data-act="uninstall"]')
    expect(page.locator("#dialog")).to_contain_text("Saved Games")
    page.click('#dialog button[value="ok"]')
    expect(page.locator(".toast").last).to_contain_text("uninstalled")
    expect(page.locator('[data-act-for] [data-act="install"]').first).to_be_visible()
    check(not errors, f"no script errors {errors[:3]}")
    page.close()

    # A failed download says why, in a toast and in Downloads.
    page, errors = boot(fail=[small["slug"]])
    act(page, small).locator('[data-act="install"]').click()
    expect(page.locator(".toast.error")).to_contain_text("damaged", timeout=10_000)
    page.click('.tabs [data-view="library"]')
    expect(page.locator(".downloads .dl .state.bad")).to_contain_text("checksum")
    snap(page, "downloads-failed")
    page.click('.downloads [data-act="dismiss"]')
    check(page.locator(".downloads").count() == 0, "a failed install can be dismissed, and Library has no downloads section when nothing is happening")
    check(not errors, f"no script errors {errors[:3]}")
    page.close()

    # Player reviews on a game's page: the published ones, a review sent, the checks that spare a review the collector would drop.
    reviews = {"schema": 1, "games": {ai_game["slug"]: {"name": ai_game["name"], "author": "ai", "count": 2, "average": 7.5, "reviews": [
        {"id": "a", "version": 1, "score": 9, "liked": "Clever <b>idea</b>.\nShort rounds.", "disliked": "", "name": "Sam", "source": "app", "date": "2026-10-18"},
        {"id": "b", "version": 1, "score": 6, "liked": "", "disliked": "Too dark.", "name": "", "source": "site", "date": "2026-10-17"}]}}}
    page, errors = boot(reviews=reviews, installed={ai_game["slug"]: ai_game["versions"][0]["version"]})
    card(page, ai_game).click()
    expect(page.locator("#reviews .rv-avg")).to_have_text("7.5")
    expect(page.locator("#reviews .rv-count")).to_have_text("out of 10, from 2 reviews")
    check(page.locator(".rv").count() == 2 and "&lt;b&gt;" in page.locator(".rv").first.inner_html(), "published reviews are shown, their text escaped")
    check(page.locator('.toc [data-scroll="reviews"]').count() == 1, "the contents list links to the reviews")
    page.click('.toc [data-scroll="reviews"]')
    page.click(".rv-form button[type=submit]")
    expect(page.locator(".rv-status")).to_have_text("Pick a score from 1 to 10.")
    page.locator(".rv-score span").nth(7).click()
    page.wait_for_timeout(300)
    window_still(page, "after picking a score")
    page.fill(".rv-form textarea[name=liked]", "more at www.spam.com")
    page.click(".rv-form button[type=submit]")
    expect(page.locator(".rv-status")).to_contain_text("leave out links")
    page.fill(".rv-form textarea[name=liked]", "Swapping disguises is clever.")
    page.fill(".rv-form textarea[name=disliked]", "Hard to see the crates.")
    page.fill(".rv-form input[name=name]", "Jo")
    page.keyboard.press("Escape")
    check(page.locator("#reviews").count() == 1, "Escape while typing a review does not leave the page")
    page.click(".rv-form button[type=submit]")
    expect(page.locator(".rv-status")).to_contain_text("Thank you")
    sent = [c[1]["review"] for c in page.evaluate("window.__CALLS__") if c[0] == "review_send"]
    check(sent == [{"game": ai_game["slug"], "name_of_game": ai_game["name"], "version": ai_game["versions"][0]["version"], "score": 8,
                    "liked": "Swapping disguises is clever.", "disliked": "Hard to see the crates.", "name": "Jo"}], f"the review sent is the one written {sent}")
    expect(page.locator(".rv.pending")).to_contain_text("Swapping disguises is clever.")
    snap(page, "reviews")
    no_overflow(page, "reviews")
    check(not errors, f"no script errors {errors[:3]}")
    page.close()
    page, errors = boot(reviewFail="Could not send it (are you online?); try again.")
    card(page, ai_game).click()
    expect(page.locator("#reviews .rv-count")).to_have_text("No reviews yet: be the first.")
    page.locator(".rv-score span").nth(2).click()
    page.fill(".rv-form textarea[name=disliked]", "Confusing start.")
    page.click(".rv-form button[type=submit]")
    expect(page.locator(".rv-status")).to_have_text("Could not send it (are you online?); try again.")
    check(page.locator(".rv.pending").count() == 0, "a review that failed to send is not shown as sent")
    page.close()

    # A game's versions: at the top, which one is installed and when it came out, and a small button beside Play for a newer one that
    # updates the game; at the bottom, every version in a table as on the website. And favorites: a heart on every game, kept in a section.
    many = max((g for g in games if g.get("wiki")), key=lambda g: len(g["versions"]))
    mine, newest = many["versions"][-1], many["versions"][0]
    page, errors = boot(installed={many["slug"]: mine["version"]})
    check("Click the ♡ on any game" in page.locator("#favs").inner_text(), "with no favorites yet, the section says how to add one")
    card(page, many).locator(".heart").click()
    expect(page.locator("#favs .fav-tile")).to_have_count(1)
    check(page.locator(".hero").count() == 0, "a heart does not open the game")
    check("fav" in card(page, many).get_attribute("class") and card(page, many).locator('.heart[aria-pressed="true"]').inner_text() == "♥", "a hearted card is marked")
    check(["favorite", {"slug": many["slug"], "on": True}] in page.evaluate("window.__CALLS__"), "the heart is kept by the window")
    check(page.locator(f'#favs [data-act-for="{many["slug"]}"] .newer').inner_text().strip().endswith(f"v{newest['version']}"), "a favorite with an update says so")
    snap(page, "favorites")
    page.locator("#favs .fav-tile h3").click()
    expect(page.locator("h1")).to_have_text(many["name"])
    ver = page.locator(".ver-line").inner_text()
    check(f"Version {mine['version']} installed" in ver and f"Released {day(mine['released'])}" in ver and f"all {len(many['versions'])} versions" in ver,
          f"the top of the page says which version is installed and when it was released: {ver}")
    newer = page.locator(".hero .newer")
    check(newer.count() == 1 and f"New version {newest['version']} · {day(newest['released'])}" in newer.inner_text(), f"a newer version shows beside Play, with its date: {newer.all_inner_texts()}")
    check(page.locator(".hero .act .play").count() == 1, "the installed version still plays")
    rows = page.locator("table.versions tbody tr")
    check(rows.count() == len(many["versions"]), f"every version is in the versions table ({rows.count()} of {len(many['versions'])})")
    check("Latest" in rows.first.inner_text() and "Installed" in rows.last.inner_text() and day(mine["released"]) in rows.last.inner_text(), "the table marks the latest and the installed version, with dates")
    check(page.locator('.hero .heart[aria-pressed="true"]').count() == 1, "the game's page shows its heart")
    page.click('.ver-line [data-scroll="versions"]')
    page.wait_for_timeout(700)
    window_still(page, "after the link to all versions")
    check(page.locator("table.versions").is_visible() and page.evaluate("() => document.querySelector('table.versions').getBoundingClientRect().top < innerHeight"), "the link at the top shows the versions table")
    snap(page, "versions")
    page.evaluate("() => document.querySelector('main').scrollTop = 0")
    snap(page, "game-update")
    newer.click()
    expect(page.locator(".ver-line")).to_contain_text(f"Version {newest['version']} installed", timeout=10_000)
    check(["install", {"slug": many["slug"]}] in page.evaluate("window.__CALLS__"), "the newer-version button updates the game")
    check(page.locator(".hero .newer").count() == 0 and "Installed" in page.locator("table.versions tbody tr").first.inner_text(), "once up to date, the button is gone and the newest version is the installed one")
    page.locator(".hero .heart").click()
    check(["favorite", {"slug": many["slug"], "on": False}] in page.evaluate("window.__CALLS__"), "a second click takes the heart away")
    page.click('[data-act="back"]')
    expect(page.locator("#favs .fav-tile")).to_have_count(0)
    check(not errors, f"no script errors {errors[:3]}")
    page.close()
    page, errors = boot(favorites=[many["slug"], small["slug"]])
    expect(page.locator("#favs .fav-tile")).to_have_count(2)
    check(page.locator(".card.fav").count() == 2, "favorites kept by the window are there when the launcher starts")
    no_overflow(page, "games with favorites")
    page.close()

    # Downloads in progress, and closing the window while they run.
    page, errors = boot(ms=400)
    act(page, small).locator('[data-act="install"]').click()
    act(page, small3).locator('[data-act="install"]').click()
    check("2 downloading" in page.locator("#n-library").inner_text(), f"the Library tab counts the downloads: {page.locator('#n-library').inner_text()}")
    check(page.locator('.tabs [data-view="downloads"]').count() == 0, "there is no separate Downloads tab")
    page.click('.tabs [data-view="library"]')
    expect(page.locator(".downloads .dl")).to_have_count(2)
    check(page.locator(".downloads h2").first.text_content().startswith("Downloading"), "downloads show at the top of Library")
    snap(page, "downloads")
    page.evaluate("window.__EMIT__('close-requested', null)")
    expect(page.locator("#dialog")).to_contain_text("still downloading")
    page.click('#dialog button[value="ok"]')
    page.wait_for_timeout(200)
    check(["quit", {}] in page.evaluate("window.__CALLS__"), "quitting while downloading asks first, then quits")
    check(not errors, f"no script errors {errors[:3]}")
    page.close()

    # The launcher's own update: banner, later, update now.
    page, errors = boot(update=UPDATE)
    expect(page.locator(".banner.update")).to_contain_text("A new version of RedEngine Games is ready")
    snap(page, "update-banner")
    page.click('[data-act="update-later"]')
    expect(page.locator(".banner.update")).to_have_count(0)
    expect(page.locator("#version")).to_contain_text("update to 0.2.0")
    page.click("#version")
    page.click('[data-act="update-now"]')
    expect(page.locator(".banner.update")).to_contain_text("Installing version 0.2.0", timeout=10_000)
    snap(page, "update-installing")
    check(["launcher_update_apply", {}] in page.evaluate("window.__CALLS__"), "Update now downloads and installs the new launcher")
    check(not errors, f"no script errors {errors[:3]}")
    page.close()

    # Asked to update while a game downloads: it waits for the download, then updates.
    page, errors = boot(update=UPDATE, ms=150)
    expect(page.locator(".banner.update")).to_be_visible()
    act(page, small).locator('[data-act="install"]').click()
    page.click('[data-act="update-now"]')
    expect(page.locator(".banner.update")).to_contain_text("when your downloads finish")
    expect(page.locator(".banner.update")).to_contain_text("Installing version 0.2.0", timeout=15_000)
    check(page.evaluate("window.__CALLS__.map(c => c[0])").index("launcher_update_apply") > page.evaluate("window.__CALLS__.map(c => c[0])").index("install"), "the update waits for the download")
    check(not errors, f"no script errors {errors[:3]}")
    page.close()

    # A game dropped on the window: the form, adding it to this PC only, and publishing it once a token is set up.
    page, errors = boot()
    page.evaluate('window.__EMIT__("tauri://drag-enter", {paths: ["C:/Users/p/Downloads/Star_Miner.zip"]})')
    check(page.locator("#dropzone").is_visible(), "dragging a file over the window shows where to drop it")
    page.evaluate('window.__EMIT__("tauri://drag-drop", {paths: ["C:/Users/p/Downloads/Star_Miner.zip", "C:/Users/p/shot.png"]})')
    expect(page.locator("#drop")).to_be_visible()
    check(not page.locator("#dropzone").is_visible(), "the drop hint goes away on drop")
    check(page.locator("#drop input[name=name]").input_value() == "Star Miner" and page.locator("#drop select[name=entry]").input_value() == "StarMiner.exe", "the form starts from what was dropped")
    check("with a screenshot" in page.locator(".drop-what").inner_text(), "a dropped screenshot is noticed")
    check(page.locator('[data-drop="publish"]').inner_text() == "Set up publishing…", "without a token, publishing offers to be set up")
    page.fill("#drop input[name=name]", ai_game["name"])
    check("already a game on the site" in page.locator(".drop-note").inner_text() and page.locator('[data-drop="add"]').is_disabled(), "a built game's name is refused")
    page.fill("#drop input[name=name]", "Star Miner")
    snap(page, "drop-form")
    page.click('[data-drop="add"]')
    expect(page.locator("h1")).to_have_text("Star Miner")
    check(page.locator(".hero .badge.local").count() == 1 and "only on this PC" in page.locator(".wiki").inner_text(), "an added game is marked as this PC's own")
    check(page.locator('.hero [data-act="play"]').count() == 1, "an added game can be played at once")
    page.click('.tabs [data-view="library"]')
    check(page.locator(".row h3", has_text="Star Miner").count() == 1, "it is in the library")
    page.locator(".drop-hint .inline-link").first.click()
    expect(page.locator("#pub")).to_be_visible()
    page.click('[data-pub="save"]')
    expect(page.locator(".pub-status")).to_have_text("Paste the token first.")
    page.fill("#pub input", "github_pat_x")
    page.click('[data-pub="save"]')
    expect(page.locator(".toast").last).to_contain_text("can now publish")
    page.evaluate('window.__EMIT__("tauri://drag-drop", {paths: ["C:/Users/p/Downloads/StarMiner-1.1.zip"]})')
    expect(page.locator("#drop")).to_be_visible()
    check("version 2 of Star Miner" in page.locator(".drop-note").inner_text(), "dropping a game with the same name makes its next version")
    page.fill("#drop textarea[name=notes]", "Fixed the save bug.")
    page.click('[data-drop="publish"]')
    expect(page.locator(".toast").last).to_contain_text("Published Star Miner version 2", timeout=10_000)
    sent = [c[1]["details"] for c in page.evaluate("window.__CALLS__") if c[0] == "drop_publish"]
    check(sent and sent[0]["notes"] == "Fixed the save bug." and sent[0]["entry"] == "StarMiner.exe", f"the details published are the ones written {sent}")
    check(not errors, f"no script errors {errors[:3]}")
    page.close()

    # Engine feedback: notes about the engine, not one game.
    notes = {"schema": 1, "games": {}, "engine": {"count": 1, "notes": [{"id": "n1", "kind": "idea", "text": "Let me <b>rebind</b> keys.", "name": "Cuz", "source": "app", "date": "2026-10-18"}]}}
    page, errors = boot(reviews=notes)
    page.click('.tabs [data-view="feedback"]')
    expect(page.locator("#notes .note")).to_have_count(1)
    check("&lt;b&gt;" in page.locator("#notes .note").inner_html(), "published notes are shown, escaped")
    page.fill(".note-form textarea", "short")
    page.click(".note-form button[type=submit]")
    expect(page.locator(".note-form .rv-status")).to_contain_text("a little more")
    page.locator(".note-kind span", has_text="Bug").click()
    page.fill(".note-form textarea", "The gamepad stops working after alt-tab in every game.")
    page.fill(".note-form input[name=name]", "Cuz")
    page.click(".note-form button[type=submit]")
    expect(page.locator(".note-form .rv-status")).to_contain_text("Thank you")
    sent = [c[1]["note"] for c in page.evaluate("window.__CALLS__") if c[0] == "note_send"]
    check(sent == [{"kind": "bug", "text": "The gamepad stops working after alt-tab in every game.", "name": "Cuz"}], f"the note sent is the one written {sent}")
    expect(page.locator("#notes .note.pending")).to_contain_text("alt-tab")
    snap(page, "engine-feedback")
    no_overflow(page, "engine feedback")
    check(not errors, f"no script errors {errors[:3]}")
    page.close()

    # The refresh button checks the site again and says what it found.
    page, errors = boot()
    page.click("#refresh")
    expect(page.locator(".toast").last).to_contain_text("Up to date")
    check(page.evaluate("window.__CALLS__.filter(c => c[0] === 'overview' && c[1].refresh).length") == 1, "the button fetches the catalog again")
    page.evaluate("window.__MOCK__.catalog.games.unshift({...window.__MOCK__.catalog.games[0], slug: 'brand-new', name: 'Brand New'})")
    page.click("#refresh")
    expect(page.locator(".toast").last).to_contain_text("New game: Brand New")
    check(card(page, {"slug": "brand-new"}).count() == 1, "the new game appears without restarting")
    check(not errors, f"no script errors {errors[:3]}")
    page.close()

    # Offline: the last catalog with a notice, or a clear message on a first run.
    page, errors = boot(offline=True)
    expect(page.locator(".banner.offline")).to_contain_text("Can't reach the RedEngine Games site")
    page.close()
    page, errors = boot(offline=True, noCache=True)
    expect(page.locator(".empty")).to_contain_text("No connection")
    page.close()

    # The smallest window the launcher allows.
    page, errors = boot(width=820, height=560, installed={old["slug"]: 1})
    no_overflow(page, "games at 820px")
    snap(page, "games-narrow")
    card(page, ai_game).click()
    page.wait_for_timeout(500)
    no_overflow(page, "game page at 820px")
    snap(page, "game-narrow")
    page.click('[data-act="back"]')
    card(page, old).click()
    page.wait_for_timeout(500)
    no_overflow(page, "a game page with an update and its versions table at 820px")
    snap(page, "game-update-narrow")
    page.click('.tabs [data-view="library"]')
    no_overflow(page, "library at 820px")
    check(not errors, f"no script errors {errors[:3]}")
    page.close()
    browser.close()

print(f"\n{len(failures)} failed" if failures else "\nall passed")
sys.exit(1 if failures else 0)
