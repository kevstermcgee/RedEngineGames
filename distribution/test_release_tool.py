import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import release_tool as rt


def release(slug, version, content, commit="c0ffee"):
    meta = {"slug": slug, "name": slug.title(), "version": version, "content_hash": content, "repo_commit": commit}
    return {"tag_name": f"{slug}-v{version}", "html_url": "u", "body": f"notes\n\n<!-- redengine-release {json.dumps(meta)} -->\n"}


PLAYABLES = [{"slug": "a", "name": "A", "files": ["games/a"], "arguments": ["x"]}, {"slug": "b", "name": "B", "files": ["games/b"], "arguments": ["y"]}]


class Planning(unittest.TestCase):
    def test_history_is_read_from_the_marker_newest_first_and_ignores_other_releases(self):
        h = rt.release_history([release("a", 1, "h1"), release("a", 2, "h2"), {"tag_name": "redengine-abc", "body": "old bundle"}, {"tag_name": "x", "body": "<!-- redengine-release {broken -->"}])
        self.assertEqual([v["version"] for v in h["a"]], [2, 1])
        self.assertEqual(list(h), ["a"])

    def test_a_game_is_released_when_new_or_changed_and_left_alone_otherwise(self):
        hashes = {"a": "h2", "b": "hb"}
        history = rt.release_history([release("a", 1, "h1"), release("a", 2, "h2"), release("b", 1, "other")])
        todo = rt.decide(PLAYABLES, hashes, history)
        self.assertEqual([(t["slug"], t["version"], t["reason"]) for t in todo], [("b", 2, "content changed")])
        self.assertEqual(rt.decide(PLAYABLES, hashes, {}, only={"a"})[0]["version"], 1)
        again = rt.decide(PLAYABLES, {"a": "h2", "b": "other"}, history, force=True)
        self.assertEqual([(t["slug"], t["version"]) for t in again], [("a", 3), ("b", 2)], "an engine refresh bumps every game by one")

    def test_gh_api_pages_are_flattened(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.json"
            p.write_text(json.dumps([[release("a", 1, "h")], [release("b", 1, "h")]]))
            self.assertEqual(len(rt.load_releases(p)), 2)
            p.write_text(json.dumps([release("a", 1, "h")]))
            self.assertEqual(len(rt.load_releases(p)), 1)
            p.write_text(json.dumps([release("a", 1, "h")]) + "\n" + json.dumps([release("b", 1, "h"), release("c", 1, "h")]))
            self.assertEqual(len(rt.load_releases(p)), 3, "pages printed back to back")
            self.assertEqual(rt.load_releases(Path(d) / "none.json"), [])


class Identity(unittest.TestCase):
    def test_the_installer_identity_is_stable_per_game_and_different_between_games(self):
        self.assertEqual(rt.app_guid("marcel"), rt.app_guid("marcel"))
        self.assertNotEqual(rt.app_guid("marcel"), rt.app_guid("coin-run"))

    def test_the_save_folder_name_drops_what_windows_forbids(self):
        self.assertEqual(rt.clean_name('Who: "Me"?'), "Who Me")

    def test_play_cfg_tells_the_launcher_where_updates_live(self):
        text = rt.play_cfg({"name": "Marcel", "slug": "marcel", "version": 3}, installed=True)
        self.assertIn("version=3", text)
        self.assertIn("mode=installed", text)
        self.assertIn("/games/marcel/latest.json", text)
        self.assertIn("mode=portable", rt.play_cfg({"name": "M", "slug": "m", "version": 1}, installed=False))


class Content(unittest.TestCase):
    def test_the_fingerprint_follows_the_committed_content_not_the_working_copy(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            run = lambda *a: subprocess.run(["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t", *a], check=True, capture_output=True)
            run("init", "-q")
            (repo / "games/a").mkdir(parents=True)
            (repo / "games/a/m.json").write_text("{}\n")
            run("add", "."), run("commit", "-qm", "one")
            first = rt.content_hash(repo, PLAYABLES[0])
            (repo / "games/a/m.json").write_text("{ }\n")
            self.assertEqual(rt.content_hash(repo, PLAYABLES[0]), first, "uncommitted edits do not count")
            run("commit", "-qam", "Fix the door")
            self.assertNotEqual(rt.content_hash(repo, PLAYABLES[0]), first)
            self.assertEqual(rt.change_notes(repo, PLAYABLES[0], run("rev-parse", "HEAD~1") and subprocess.run(["git", "-C", d, "rev-parse", "HEAD~1"], capture_output=True, text=True).stdout.strip()), ["Fix the door"])

    def test_release_notes_carry_the_machine_readable_line_the_site_reads_back(self):
        meta = {"slug": "a", "name": "A", "version": 2, "notes": ["Fix the door"], "engine_revision": "e" * 40,
                "installer": {"name": "a-2-setup.exe"}, "zip": {"name": "a-2-windows-x64.zip"}, "content_hash": "h", "repo_commit": "c"}
        history = rt.release_history([{"tag_name": "a-v2", "body": rt.release_body(meta)}])
        self.assertEqual(history["a"][0]["notes"], ["Fix the door"])
        self.assertIn("- Fix the door", rt.release_body(meta))

    def test_a_2d_game_is_staged_with_the_2d_player_and_a_3d_game_with_the_3d_client(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "re2.exe").write_bytes(b"3d")
            (d / "re2d.exe").write_bytes(b"2d")
            (d / "Play.exe").write_bytes(b"launcher")
            repo = d / "repo"
            (repo / "g").mkdir(parents=True)
            (repo / "g/x.game2d.json").write_text("{}")
            (repo / "g/m.json").write_text("{}")
            rt.REPO = repo
            entry = {"slug": "x", "name": "X", "version": 1}
            two_d = {"slug": "x", "kind": "2d", "files": ["g/x.game2d.json"], "arguments": ["content/g/x.game2d.json"]}
            three_d = {"slug": "x", "files": ["g/m.json"], "arguments": ["content/g/m.json"]}
            rt.stage_game(entry, two_d, d / "re2d.exe", d / "Play.exe", d / "s2")
            rt.stage_game(entry, three_d, d / "re2.exe", d / "Play.exe", d / "s3")
            self.assertEqual((d / "s2/engine.name").read_text().strip(), "RedEngine2D.exe")
            self.assertEqual((d / "s2/RedEngine2D.exe").read_bytes(), b"2d")
            self.assertEqual((d / "s3/engine.name").read_text().strip(), "RedEngine.exe")
            self.assertEqual((d / "s2/launch.args").read_text().strip(), "content/g/x.game2d.json")


if __name__ == "__main__":
    unittest.main()
