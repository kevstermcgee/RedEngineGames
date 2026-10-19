"""python3 -m unittest discover -s site: which RedEngine Games app release the site offers, and what `launcher/latest.json` says about it."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate  # noqa: E402


def release(tag, assets, body="", draft=False):
    return {"tag_name": tag, "draft": draft, "prerelease": False, "published_at": "2026-10-18T10:00:00Z", "body": body, "assets": assets}


def setup(version, digest="sha256:" + "ab" * 32):
    return {"name": f"RedEngineGames-{version}-setup.exe", "size": 4_000_000, "digest": digest}


class AppRelease(unittest.TestCase):
    def test_the_newest_version_wins_by_number_not_by_text(self):
        app = generate.launcher_release([
            release("launcher-v0.9.0", [setup("0.9.0")]),
            release("launcher-v0.10.0", [setup("0.10.0")], body="What changed:\n- Faster downloads.\n- A bigger play button.\n"),
            release("restless-tide-v1", [setup("1")]),
        ])
        self.assertEqual(app["version"], "0.10.0")
        self.assertEqual(app["installer"]["sha256"], "ab" * 32)
        self.assertEqual(app["installer"]["url"], f"https://github.com/{generate.CONFIG['repository']}/releases/download/launcher-v0.10.0/RedEngineGames-0.10.0-setup.exe")
        self.assertEqual(app["notes"], ["Faster downloads.", "A bigger play button."])

    def test_drafts_and_installers_without_a_checksum_are_never_offered(self):
        self.assertIsNone(generate.launcher_release([
            release("launcher-v0.3.0", [setup("0.3.0")], draft=True),
            release("launcher-v0.2.0", [setup("0.2.0", digest=None)]),
        ]))

    def test_the_front_page_offers_the_app_only_when_there_is_one(self):
        self.assertEqual(generate.app_box(None), "")
        app = generate.launcher_release([release("launcher-v0.1.0", [setup("0.1.0")])])
        self.assertIn("Download the app for Windows", generate.app_box(app))


if __name__ == "__main__":
    unittest.main()
