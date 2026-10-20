import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import release_tool as rt
import upload_game as up


def make_zip(path: Path, files: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return path


def packed(archive: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(archive) as z:
        return {n: z.read(n) for n in z.namelist()}


class Packing(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_a_zip_of_one_folder_is_played_from_inside_it_and_its_one_exe_is_found(self):
        src = make_zip(self.tmp / "g.zip", {"Star Miner/StarMiner.exe": b"MZ", "Star Miner/unins000.exe": b"MZ", "Star Miner/data/a.pak": b"x"})
        entry = up.pack(src, [], None, [], self.tmp / "out.zip")
        files = packed(self.tmp / "out.zip")
        self.assertEqual(entry, "StarMiner.exe")
        self.assertEqual(files["engine.name"], b"StarMiner.exe\n")
        self.assertEqual(files["launch.args"], b"")
        self.assertIn("data/a.pak", files)

    def test_a_bat_with_companion_files_and_arguments(self):
        (self.tmp / "quest.bat").write_text("@echo off\n")
        (self.tmp / "story.txt").write_text("once")
        entry = up.pack(self.tmp / "quest.bat", [self.tmp / "story.txt"], None, ["--fast", "level 2"], self.tmp / "out.zip")
        files = packed(self.tmp / "out.zip")
        self.assertEqual(entry, "quest.bat")
        self.assertEqual(set(files), {"quest.bat", "story.txt", "engine.name", "launch.args"})
        self.assertEqual(files["launch.args"], b"--fast\nlevel 2\n")

    def test_a_game_that_keeps_its_program_one_folder_down_is_found_there(self):
        src = make_zip(self.tmp / "g.zip", {"bin/Game.exe": b"MZ", "assets/x": b"x", "readme.txt": b"r"})
        self.assertEqual(up.pack(src, [], None, [], self.tmp / "out.zip"), "bin/Game.exe")

    def test_several_candidates_need_run_and_run_must_be_inside(self):
        src = make_zip(self.tmp / "g.zip", {"Game.exe": b"MZ", "Editor.exe": b"MZ"})
        with self.assertRaises(SystemExit) as e:
            up.pack(src, [], None, [], self.tmp / "out.zip")
        self.assertIn("Editor.exe", str(e.exception))
        self.assertEqual(up.pack(src, [], "Game.exe", [], self.tmp / "out.zip"), "Game.exe")
        with self.assertRaises(SystemExit):
            up.pack(src, [], "../Game.exe", [], self.tmp / "out.zip")

    def test_nothing_to_start_and_unsafe_archives_are_refused(self):
        with self.assertRaises(SystemExit):
            up.pack(make_zip(self.tmp / "a.zip", {"readme.txt": b"r"}), [], None, [], self.tmp / "out.zip")
        with self.assertRaises(SystemExit) as e:
            up.pack(make_zip(self.tmp / "b.zip", {"../evil.exe": b"MZ"}), [], None, [], self.tmp / "out.zip")
        self.assertIn("unsafe", str(e.exception))

    def test_a_redengine_portable_build_keeps_its_own_engine_and_arguments(self):
        src = make_zip(self.tmp / "g.zip", {"RedEngine.exe": b"MZ", "Play-x.exe": b"MZ", "engine.name": b"RedEngine.exe\n", "launch.args": b"map.json\n"})
        self.assertEqual(up.pack(src, [], None, [], self.tmp / "out.zip"), "RedEngine.exe")
        self.assertEqual(packed(self.tmp / "out.zip")["launch.args"], b"map.json\n")


class Versions(unittest.TestCase):
    def history(self, *metas):
        return rt.release_history([{"tag_name": f"{m['slug']}-v{m['version']}", "body": f"<!-- redengine-release {json.dumps(m)} -->"} for m in metas])

    def test_the_next_version_follows_the_newest_upload(self):
        h = self.history({"kind": "upload", "slug": "star-miner", "version": 1}, {"kind": "upload", "slug": "star-miner", "version": 2, "description": "d"})
        self.assertEqual(up.plan_version("star-miner", h, set())[0], 3)
        self.assertEqual(up.plan_version("star-miner", h, set())[1]["description"], "d")
        self.assertEqual(up.plan_version("new-game", h, set()), (1, None))

    def test_a_built_games_slug_is_never_taken_over(self):
        with self.assertRaises(SystemExit):
            up.plan_version("coin-run", {}, {"coin-run"})
        with self.assertRaises(SystemExit):
            up.plan_version("old", self.history({"slug": "old", "version": 4}), set())

    def test_release_notes_carry_the_marker_the_site_reads(self):
        meta = {"kind": "upload", "slug": "q", "name": "Q", "version": 1, "description": "d", "notes": ["First release."], "entry": "bin/q.bat",
                "zip": {"name": "q-1-windows-x64.zip", "size": 1, "sha256": "ab"}}
        h = rt.release_history([{"tag_name": "q-v1", "body": up.release_body(meta)}])
        self.assertEqual(h["q"][0]["entry"], "bin/q.bat")
        self.assertIn("run `q.bat`", up.release_body(meta))

    def test_slugs_come_from_names(self):
        self.assertEqual(up.slugify("Star Miner: Deluxe!"), "star-miner-deluxe")


if __name__ == "__main__":
    unittest.main()
