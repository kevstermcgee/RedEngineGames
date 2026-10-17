"""Checks the Designer filter in a real browser: AI-designed and human-designed games are badged, the filter separates them, it combines with 2D/3D, and it is shareable by URL.
Usage: python3 site/check_authors.py [URL]   (needs Playwright; serve the generated site first, from site/dist)."""
from playwright.sync_api import sync_playwright
import sys
B = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8111/"
bad = []
def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        bad.append(name)
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B)
    authors = lambda: pg.evaluate("[...document.querySelectorAll('#games .game:not(.hidden)')].map(c=>c.dataset.author)")
    badges = lambda: pg.evaluate("[...document.querySelectorAll('#games .game:not(.hidden) .by')].map(c=>c.textContent)")
    allc = authors()
    check("both kinds are listed", "ai" in allc and "human" in allc)
    check("every card carries a visible badge", len(badges()) == len(allc) and set(badges()) == {"AI-designed", "Human-designed"})
    pg.select_option("#who", "ai"); a = authors()
    check("AI filter shows only AI-designed", a and set(a) == {"ai"} and set(badges()) == {"AI-designed"})
    check("count text follows", pg.inner_text("#count").startswith(f"{len(a)} of {len(allc)}"))
    check("filter is in the URL", "by=ai" in pg.url)
    pg.select_option("#who", "human"); h = authors()
    check("human filter shows only human-designed", h and set(h) == {"human"} and len(h) + len(a) == len(allc))
    pg.select_option("#pres", "3d"); check("combines with 2D/3D", set(authors()) <= {"human"})
    pg.select_option("#pres", ""); pg.select_option("#who", "")
    pg.goto(B + "?by=ai"); check("a shared link opens filtered", set(authors()) == {"ai"} and pg.input_value("#who") == "ai")
    check("no page errors", not errs)
    b.close()
sys.exit(1 if bad else 0)
