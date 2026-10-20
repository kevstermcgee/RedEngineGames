"""python3 -m unittest discover -s site: games uploaded ready-made (`distribution/upload_game.py`) on the website and in `catalog.json`."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate  # noqa: E402

rt = generate.rt


def upload(version, released, **extra):
    meta = {"kind": "upload", "slug": "star-miner", "name": "Star Miner", "version": version, "released": released, "description": "Mine asteroids.",
            "presentation": "2d", "author": "human", "online": "", "entry": "bin/StarMiner.exe", "notes": [f"note {version}"],
            "zip": {"name": f"star-miner-{version}-windows-x64.zip", "size": 5_000_000, "sha256": "cd" * 32}} | extra
    return {"tag_name": f"star-miner-v{version}", "html_url": "u", "body": f"x\n<!-- redengine-release {json.dumps(meta)} -->\n"}


class Uploads(unittest.TestCase):
    def games(self, releases, taken=()):
        return generate.upload_games(rt.release_history(releases), set(taken))

    def test_an_uploaded_game_is_listed_from_its_releases_with_zips_and_no_installer(self):
        [g] = self.games([upload(1, "2026-10-01"), upload(2, "2026-10-19", thumb_url="https://github.com/x/releases/download/star-miner-v2/t.png")])
        self.assertEqual((g["name"], g["presentation"], g["added"]), ("Star Miner", "2d", "2026-10-01"))
        self.assertEqual([v["version"] for v in g["versions"]], [2, 1])
        self.assertIsNone(g["versions"][0]["installer"])
        self.assertTrue(g["versions"][0]["zip"]["url"].endswith("/releases/download/star-miner-v2/star-miner-2-windows-x64.zip"))
        self.assertEqual(g["thumb_url"], "https://github.com/x/releases/download/star-miner-v2/t.png")
        self.assertIsNone(generate.latest_json(g))

    def test_a_built_game_with_the_same_slug_wins(self):
        self.assertEqual(self.games([upload(1, "2026-10-01")], taken={"star-miner"}), [])

    def test_its_card_and_page_offer_the_zip_and_the_app(self):
        [g] = self.games([upload(1, "2026-10-01")])
        card = generate.card(g, 0)
        self.assertIn("Download ZIP for Windows", card)
        self.assertIn("star-miner-1-windows-x64.zip", card)
        self.assertIn('href="#app"', card)
        page = generate.game_page(g, {"version": "0.4.0"})
        self.assertIn("Download version 1", page)
        self.assertIn("not built with RedEngine", page)
        self.assertIn("<code>StarMiner.exe</code>", page)
        self.assertIn("unzip and play", page)


if __name__ == "__main__":
    unittest.main()
