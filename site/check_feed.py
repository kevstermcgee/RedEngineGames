"""Checks the feed in a real browser: 2D and 3D in one grid, hearts persist and float to the top, the 2D/3D and favourites filters.
Usage: python3 site/check_feed.py [URL]   (needs Playwright; serve the generated site first, from site/dist)."""
from playwright.sync_api import sync_playwright
import sys
B = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8111/"
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(); pg=ctx.new_page()
    errs=[]; pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(B)
    ids=lambda: pg.evaluate("[...document.querySelectorAll('#games .game:not(.hidden)')].map(c=>c.dataset.id)")
    names=lambda: pg.evaluate("[...document.querySelectorAll('#games .game:not(.hidden)')].map(c=>c.dataset.name)")
    allc=ids(); print("shown", len(allc), "2d+3d in one grid:", any(i.startswith("web:") for i in allc) and any(i.startswith("win:") for i in allc))
    # heart a 3D game that is far down the list and a 2D game
    last3d=[i for i in allc if i.startswith("win:")][-1]
    pg.click(f'.game[data-id="{last3d}"] .heart'); 
    pg.click('.game[data-id="web:coin-dash"] .heart')
    top=ids()[:2]; print("favourites on top:", top, set(top)=={last3d,"web:coin-dash"})
    pg.reload(); top2=ids()[:2]; print("after reload:", set(top2)=={last3d,"web:coin-dash"}, pg.inner_text("#count"))
    pg.select_option("#pres","2d"); print("2D filter:", ids())
    pg.select_option("#pres","3d"); n3=len(ids()); print("3D filter count:", n3, all(i.startswith("win:") for i in ids()), ids()[0]==last3d)
    pg.select_option("#pres",""); pg.select_option("#kind","fav"); print("favourites only:", ids())
    pg.select_option("#sort","name-asc"); print("fav + sort keeps hearts first:", ids()[:2])
    pg.click(f'.game[data-id="web:coin-dash"] .heart'); print("unheart:", ids())
    print("aria-pressed:", pg.get_attribute(f'.game[data-id="{last3d}"] .heart',"aria-pressed"))
    print("errors:", errs)
    pg.screenshot(path="/tmp/feed.png", full_page=False)
    b.close()
