"""python3 -m unittest discover -s site: game families (forks) on the website and in `catalog.json`: a fork names the game and version it came from
(its playable's `forked_from`, or its first release's record), its parent lists it under Forks, and /family/ draws every family."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate  # noqa: E402


def game(slug, name, added, versions=(1,), **extra):
    vs = [{"version": n, "released": added, "notes": [], "installer": None, "zip": {"url": "z", "size": 1, "sha256": "s"}} for n in sorted(versions, reverse=True)]
    return {"slug": slug, "name": name, "added": added, "versions": vs, "earlier": [], "description": "d", "online": "", "author": "human", "thumb": "",
            "presentation": "2d", "wiki": None, "maintainer": "", "forked_from": None, "forkable": "repo", **extra}


def family():
    games = [game("snake", "Snake", "2026-10-20", (1, 2, 3), maintainer="meastwood13"),
             game("neon-snake", "Neon Snake", "2026-10-21", forked_from={"slug": "snake", "version": 3}, maintainer="kevstermcgee"),
             game("night-snake", "Night Snake", "2026-10-22", forked_from={"slug": "neon-snake", "version": 1}),
             game("wormhole", "Wormhole", "2026-10-11", forkable=""),
             game("lost-fork", "Lost Fork", "2026-10-22", forked_from={"slug": "gone", "version": 1})]
    generate.link_families(games)
    return games, {g["slug"]: g for g in games}


class Families(unittest.TestCase):
    def test_a_parent_lists_its_forks_oldest_first_and_an_unlisted_parent_links_nowhere(self):
        games, by = family()
        self.assertEqual((by["snake"]["forks"], by["neon-snake"]["forks"], by["wormhole"]["forks"]), (["neon-snake"], ["night-snake"], []))
        self.assertEqual(generate.root_of(by["night-snake"], by), "snake")
        self.assertEqual(generate.root_of(by["lost-fork"], by), "lost-fork")

    def test_a_forks_page_names_its_parent_and_version_and_its_own_forks(self):
        games, by = family()
        page = generate.game_page(by["neon-snake"], None, by)
        self.assertIn('Forked from <a href="../../games/snake/">Snake</a> <span class="who">by @meastwood13</span>, version 3.', page)
        self.assertIn('Forks: <a href="../../games/night-snake/">Night Snake</a>', page)
        self.assertIn('href="../../family/#snake"', page)

    def test_every_page_says_how_to_fork_it(self):
        games, by = family()
        page = generate.game_page(by["snake"], None, by)
        self.assertIn("python3 scripts/games.py fork snake@v3 my-game", page)
        self.assertIn("Fork this game", page)
        self.assertIn("Forks:", page)
        self.assertNotIn("An original", page)
        self.assertIn("own client, which is engine code", generate.game_page(by["wormhole"], None, by))
        self.assertIn("An original: not made from another game, and not forked yet.", generate.game_page(by["wormhole"], None, by))
        self.assertIn("<code>gone</code>", generate.game_page(by["lost-fork"], None, by))

    def test_an_uploaded_fork_reads_its_parent_from_its_first_release(self):
        meta = lambda v, **x: {"kind": "upload", "slug": "my-cart", "name": "My Cart", "version": v, "released": f"2026-10-2{v}", "entry": "a.exe", "notes": [],
                               "zip": {"name": f"z{v}", "size": 1, "sha256": "s"}, "tag": f"my-cart-v{v}", **x}
        [g] = generate.upload_games({"my-cart": [meta(2), meta(1, forked_from={"slug": "kart", "version": 4}, maintainer="meastwood13")]}, set())
        self.assertEqual((g["forked_from"], g["forkable"]), ({"slug": "kart", "version": 4}, "app"))

    def test_the_family_page_draws_each_family_from_its_original(self):
        games, _ = family()
        page = generate.family_page(games)
        snake = page.index('id="snake"')
        self.assertLess(snake, page.index("Neon Snake"))
        self.assertLess(page.index("Neon Snake"), page.index("Night Snake"))
        self.assertNotIn('id="neon-snake"', page, "a fork is drawn inside its original's family, not as a family of its own")
        self.assertIn("from v3", page)
        self.assertIn("1 game(s) have no family yet.", page)

    def test_a_card_names_the_parent(self):
        games, by = family()
        self.assertIn('fork of <a href="games/snake/">snake</a> v3', generate.card(by["neon-snake"], 0))
        self.assertNotIn("fork of", generate.card(by["snake"], 0))


if __name__ == "__main__":
    unittest.main()
