import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import game_meta as gm
import release_tool as rt
import upload_game as up

DATA = Path(__file__).resolve().parent / "testdata" / "game_meta"


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

    def test_a_ready_made_fork_names_its_parent(self):
        self.assertEqual(up.parse_forked_from("snake@v3", "neon-snake"), {"slug": "snake", "version": 3})
        self.assertEqual(up.parse_forked_from("snake@2", "neon-snake"), {"slug": "snake", "version": 2})
        for bad in ("snake", "snake@0", "Snake@1", "neon-snake@1", "snake@x"):
            with self.assertRaises(SystemExit):
                up.parse_forked_from(bad, "neon-snake")

    def test_release_notes_carry_the_marker_the_site_reads(self):
        meta = {"kind": "upload", "slug": "q", "name": "Q", "version": 1, "description": "d", "notes": ["First release."], "entry": "bin/q.bat",
                "zip": {"name": "q-1-windows-x64.zip", "size": 1, "sha256": "ab"}}
        h = rt.release_history([{"tag_name": "q-v1", "body": up.release_body(meta)}])
        self.assertEqual(h["q"][0]["entry"], "bin/q.bat")
        self.assertIn("run `q.bat`", up.release_body(meta))

    def test_slugs_come_from_names(self):
        self.assertEqual(up.slugify("Star Miner: Deluxe!"), "star-miner-deluxe")


class Cards(unittest.TestCase):
    """A game that carries its own card: the flags, the card, the previous release and the defaults, in that order."""

    PREVIOUS = {"kind": "upload", "slug": "star-miner", "name": "Star Miner", "version": 2, "description": "Previous description.", "presentation": "2d", "author": "ai",
                "online": "Previous online note.", "thumb_url": "https://example.test/old.png", "maintainer": "someone", "forked_from": {"slug": "snake", "version": 1}}

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def dry(self, source, *flags, history=None):
        """Run the tool on `source` as a dry run: (the release record, the folder the files went to, what it printed)."""
        out = self.tmp / "out"
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed), mock.patch.object(up.rt, "release_history", return_value=history or {}):
            self.assertEqual(up.main([str(source), "--dry-run", "--out", str(out), *flags]), 0)
        meta = json.loads(rt.MARKER.search((out / "notes.md").read_text(encoding="utf-8")).group(1))
        return meta, out, printed.getvalue()

    def folder(self, files: dict[str, bytes | str]) -> Path:
        root = self.tmp / f"game{len(list(self.tmp.glob('game*')))}"
        for rel, data in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_bytes(data.encode() if isinstance(data, str) else data)
        return root

    def test_a_game_that_says_its_name_needs_no_name_flag(self):
        meta, out, printed = self.dry(DATA / "zip-top-folder.zip")
        self.assertEqual((meta["slug"], meta["name"], meta["version"], meta["entry"], meta["description"]), ("star-miner", "Star Miner", 1, "StarMiner.exe", "Mine asteroids, dodge pirates."))
        self.assertEqual((meta["presentation"], meta["author"], meta["online"], meta["notes"]), ("3d", "human", "", ["First release."]))
        self.assertIn("star-miner-v1: Star Miner, starts StarMiner.exe", printed)
        self.assertEqual(meta["thumb"], "star-miner-1-thumb.png", "the card's screenshot is the release's")
        self.assertEqual((out / meta["thumb"]).read_bytes(), zipfile.ZipFile(DATA / "zip-top-folder.zip").read("Star Miner/shots/one.png"))

    def test_it_runs_as_a_script_and_a_card_is_all_it_needs(self):
        done = subprocess.run([sys.executable, "-B", str(Path(up.__file__)), str(DATA / "zip-top-folder.zip"), "--dry-run"], capture_output=True, text=True, cwd=self.tmp)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("star-miner-v1: Star Miner, starts StarMiner.exe", done.stdout)
        self.assertTrue((self.tmp / "dist-upload" / "notes.md").is_file())

    def test_a_script_or_program_that_carries_a_card_needs_none_either(self):
        meta, out, _ = self.dry(DATA / "header-rem-crlf.bat")
        self.assertEqual((meta["name"], meta["slug"], meta["presentation"], meta["author"], meta["online"], meta["entry"]),
                         ("Text Quest", "text-quest", "2d", "ai", "Two players, same room.", "header-rem-crlf.bat"))
        self.assertEqual(meta["notes"], ["First release."], "notes in a script are never a build's: the script ships unchanged in the next one")
        self.assertEqual(packed(out / meta["zip"]["name"])["launch.args"], b"--fast\nlevel 2\n")
        meta, _, _ = self.dry(DATA / "stamped.exe")
        self.assertEqual((meta["name"], meta["description"], meta["author"], meta["notes"]), ("Stamped Quest", "A game with a record in its program.", "ai", ["First release."]))
        meta, _, _ = self.dry(DATA / "versioned.exe")
        self.assertEqual((meta["name"], meta["description"]), ("Version Quest", "A game that only has version information."))

    def test_flags_beat_the_card(self):
        meta, _, _ = self.dry(DATA / "zip-top-folder.zip", "--name", "Other Name", "--description", "From a flag.", "--kind", "hybrid", "--author", "ai", "--online", "LAN", "--notes", "Mine.")
        self.assertEqual((meta["slug"], meta["name"], meta["description"], meta["presentation"], meta["author"], meta["online"], meta["notes"]),
                         ("other-name", "Other Name", "From a flag.", "hybrid", "ai", "LAN", ["Mine."]))

    def test_the_card_beats_the_previous_release_which_beats_the_defaults(self):
        history = {"star-miner": [self.PREVIOUS]}
        meta, _, _ = self.dry(DATA / "zip-top-folder.zip", history=history)
        self.assertEqual(meta["version"], 3)
        self.assertEqual(meta["description"], "Mine asteroids, dodge pirates.", "the card says it")
        self.assertEqual((meta["presentation"], meta["author"], meta["online"]), ("2d", "ai", "Previous online note."), "the card is silent: the release is not")
        self.assertEqual((meta["maintainer"], meta["forked_from"], meta["notes"]), ("someone", {"slug": "snake", "version": 1}, ["A new build."]))
        plain = self.folder({"Game.bat": "@echo off\n"})
        meta, _, _ = self.dry(plain, "--name", "Star Miner", history=history)
        self.assertEqual((meta["description"], meta["presentation"], meta["author"], meta["online"]), ("Previous description.", "2d", "ai", "Previous online note."))
        meta, _, _ = self.dry(plain, "--name", "Brand New")
        self.assertEqual((meta["description"], meta["presentation"], meta["author"], meta["online"], meta["notes"]), ("Brand New, a Windows game.", "3d", "human", "", ["First release."]))
        self.assertNotIn("forked_from", meta)

    def test_the_cards_notes_are_what_changed_unless_notes_are_given(self):
        meta, _, _ = self.dry(DATA / "folder-card", "--run", "Quest.bat")
        self.assertEqual(meta["notes"], ["First release.", "Fixed the save bug."])
        self.assertEqual(meta["forked_from"], {"slug": "snake", "version": 3})
        meta, _, _ = self.dry(DATA / "folder-card", "--notes", "A flag line.")
        self.assertEqual(meta["notes"], ["A flag line."])

    def test_the_cards_entry_and_args_start_the_game_but_flags_and_engine_name_win(self):
        files = {"A.bat": "@echo off\n", "B.bat": "@echo off\n"}
        card = json.dumps({"name": "Two Bats", "entry": "B.bat", "args": ["--fast", "level 2"]})
        meta, out, _ = self.dry(self.folder({**files, gm.CARD_FILE: card}))
        self.assertEqual(meta["entry"], "B.bat")
        self.assertEqual(packed(out / meta["zip"]["name"])["engine.name"], b"B.bat\n")
        self.assertEqual(packed(out / meta["zip"]["name"])["launch.args"], b"--fast\nlevel 2\n")
        meta, out, _ = self.dry(self.folder({**files, gm.CARD_FILE: card}), "--run", "A.bat", "--args", "z")
        self.assertEqual((meta["entry"], packed(out / meta["zip"]["name"])["launch.args"]), ("A.bat", b"z\n"))
        meta, _, _ = self.dry(self.folder({**files, gm.CARD_FILE: card, "engine.name": "A.bat\n"}))
        self.assertEqual(meta["entry"], "A.bat", "engine.name still wins")
        with self.assertRaises(SystemExit) as e:
            self.dry(self.folder({**files, gm.CARD_FILE: json.dumps({"name": "Two Bats", "entry": "../C.bat"})}))
        self.assertIn("B.bat", str(e.exception), "a card entry that is not usable is not used: the game still needs --run")

    def test_the_published_zip_carries_the_card_without_notes_in_file_and_comment(self):
        meta, out, _ = self.dry(DATA / "folder-card", "--description", "From a flag.")
        archive = out / meta["zip"]["name"]
        files = packed(archive)
        card = json.loads(files["redengine-game.json"])
        self.assertEqual(card, {"schema": 1, "name": "Star Miner", "description": "From a flag.", "presentation": "3d", "author": "human", "online": "Up to four players on one LAN.",
                                "entry": "Quest.bat", "args": ["--fast", "level 2"], "thumb": "media/shot.png", "forked_from": {"slug": "snake", "version": 3}})
        self.assertNotIn("notes", card)
        with zipfile.ZipFile(archive) as z:
            self.assertEqual(z.comment, gm.card_comment({k: v for k, v in card.items() if k != "schema"}))
            self.assertTrue(z.comment.startswith(b"redengine-game {"))
        self.assertIn("media/shot.png", files)
        # dropping the published ZIP again fills in the form completely
        again, _, _ = self.dry(archive)
        for key in ("slug", "name", "description", "presentation", "author", "online", "entry", "forked_from"):
            self.assertEqual(again[key], meta[key], key)

    def test_a_screenshot_flag_travels_in_the_game_too(self):
        shot = self.tmp / "shot.JPEG"
        shot.write_bytes(b"jpeg bytes")
        meta, out, _ = self.dry(DATA / "folder-card", "--thumb", str(shot))
        self.assertEqual(meta["thumb"], "star-miner-1-thumb.jpg")
        self.assertEqual((out / meta["thumb"]).read_bytes(), b"jpeg bytes")
        files = packed(out / meta["zip"]["name"])
        self.assertEqual(files["redengine-game-thumb.jpg"], b"jpeg bytes")
        self.assertEqual(json.loads(files["redengine-game.json"])["thumb"], "redengine-game-thumb.jpg")
        self.assertEqual(gm.read(out / meta["zip"]["name"])["card"]["thumb"], "redengine-game-thumb.jpg")
        with self.assertRaises(SystemExit):
            self.dry(DATA / "folder-card", "--thumb", str(self.tmp / "missing.png"))

    def test_a_game_without_a_card_still_packs_and_publishes_the_same_record(self):
        meta, out, _ = self.dry(self.folder({"Game.bat": "@echo off\n"}), "--name", "Plain Game", "--description", "d")
        self.assertEqual((meta["entry"], meta["description"], meta["presentation"], meta["author"]), ("Game.bat", "d", "3d", "human"))
        self.assertEqual(set(packed(out / meta["zip"]["name"])), {"Game.bat", "engine.name", "launch.args", "redengine-game.json"})
        self.assertEqual(gm.read(out / meta["zip"]["name"])["card"], {"name": "Plain Game", "description": "d", "presentation": "3d", "author": "human", "entry": "Game.bat"})

    def test_no_name_anywhere_is_a_clear_error(self):
        plain = self.folder({"Game.bat": "@echo off\n"})
        with self.assertRaises(SystemExit) as e:
            self.dry(plain)
        self.assertIn("no name", str(e.exception))
        self.assertIn("--name", str(e.exception))
        meta, _, _ = self.dry(plain, "--slug", "star-miner", history={"star-miner": [self.PREVIOUS]})
        self.assertEqual((meta["name"], meta["version"]), ("Star Miner", 3), "a slug that has releases has a name")
        with self.assertRaises(SystemExit):
            self.dry(plain, "--name", "   ")

    def test_a_card_that_names_the_game_as_its_own_parent_is_not_kept_as_a_fork(self):
        card = json.dumps({"name": "Neon Racer", "forked_from": {"slug": "neon-racer", "version": 2}})
        meta, _, _ = self.dry(self.folder({"Game.bat": "x", gm.CARD_FILE: card}))
        self.assertNotIn("forked_from", meta)
        meta, _, _ = self.dry(self.folder({"Game.bat": "x", gm.CARD_FILE: card}), "--slug", "turbo-racer")
        self.assertEqual(meta["forked_from"], {"slug": "neon-racer", "version": 2})

    def test_a_link_in_a_game_folder_is_left_behind_so_a_card_and_a_screenshot_cannot_come_from_outside(self):
        outside = self.folder({"card.json": json.dumps({"name": "Leak", "description": "Leaked."}), "shot.png": "outside picture"})
        root = self.folder({"Game.bat": "@echo off\n", gm.CARD_FILE: json.dumps({"name": "Real", "thumb": "shot.png"})})
        try:
            (root / "shot.png").symlink_to(outside / "shot.png")
            (self.tmp / "linked").mkdir()
            (self.tmp / "linked" / "Game.bat").write_text("@echo off\n")
            (self.tmp / "linked" / gm.CARD_FILE).symlink_to(outside / "card.json")
        except (OSError, NotImplementedError):
            self.skipTest("this machine does not allow symbolic links")
        meta, out, _ = self.dry(root)
        self.assertEqual((meta["name"], "thumb" in meta), ("Real", False), "a screenshot that is a link is not published")
        self.assertNotIn("redengine-game-thumb.png", packed(out / meta["zip"]["name"]))
        with self.assertRaises(SystemExit) as e:
            self.dry(self.tmp / "linked")
        self.assertIn("no name", str(e.exception), "a card that is a link says nothing")

    def test_fork_json_names_the_parent_and_wins_over_the_card_and_the_fork_has_none_of_its_parents_words(self):
        script = "REM redengine-game\nREM name: Text Quest\nREM description: The parent's words.\nREM author: ai\nREM notes: Parent notes.\n"
        card = {"name": "Card Name", "forked_from": {"slug": "snake", "version": 2}}
        fork = {"forked_from": {"slug": "other", "version": 9}, "name": "Fork Name"}
        meta, _, _ = self.dry(self.folder({"Quest.bat": script, gm.CARD_FILE: json.dumps(card), "fork.json": json.dumps(fork)}))
        self.assertEqual((meta["name"], meta["forked_from"]), ("Card Name", {"slug": "other", "version": 9}), "fork.json says the parent, as in the window")
        self.assertEqual((meta["description"], meta["author"], meta["notes"]), ("Card Name, a Windows game.", "human", ["First release."]), "its parent's script's words are not its own")
        meta, _, _ = self.dry(self.folder({"Quest.bat": script, "fork.json": json.dumps(fork)}))
        self.assertEqual((meta["name"], meta["description"], meta["forked_from"]["slug"]), ("Text Quest", "Text Quest, a Windows game.", "other"), "a fork.json beside a script is a fork")
        parents_card = json.dumps({"name": "Text Quest", "description": "The parent's."})
        fork = {"forked_from": {"slug": "text-quest", "version": 1}, "name": "Quest Remix"}
        meta, _, _ = self.dry(self.folder({"Quest.bat": "@echo off\n", gm.CARD_FILE: parents_card, "fork.json": json.dumps(fork)}))
        self.assertEqual((meta["name"], meta["slug"], meta["forked_from"]), ("Quest Remix", "quest-remix", {"slug": "text-quest", "version": 1}), "the parent's card does not rename the fork")
        with self.assertRaises(SystemExit) as e:
            self.dry(self.folder({"Quest.bat": "@echo off\n", "fork.json": json.dumps(fork)}), "--name", "Text Quest")
        self.assertIn("give your version its own", str(e.exception))
        for bad in ('{"forked_from": {"slug": "Bad Slug", "version": 1}, "name": "x"}', '{"forked_from": {"slug": "snake", "version": 0}, "name": "x"}', '{"forked_from": {"slug": "snake", "version": 1}}',
                    "not json", '{"forked_from": {"slug": "' + "a" * 65 + '", "version": 1}, "name": "x"}'):
            meta, _, _ = self.dry(self.folder({"Quest.bat": "@echo off\n", "fork.json": bad}), "--name", "Plain")
            self.assertNotIn("forked_from", meta, bad)

    def test_a_program_given_as_the_game_is_the_game_whatever_it_is_called(self):
        script = self.tmp / "Install_And_Play.bat"
        script.write_text("REM redengine-game\nREM name: Install And Play\n", encoding="utf-8")
        meta, out, _ = self.dry(script)
        self.assertEqual((meta["name"], meta["entry"]), ("Install And Play", "Install_And_Play.bat"))
        self.assertEqual(packed(out / meta["zip"]["name"])["engine.name"], b"Install_And_Play.bat\n")
        with self.assertRaises(SystemExit) as e:  # inside a ZIP with other things, a name like that is still not the game
            self.dry(make_zip(self.tmp / "g.zip", {"Install_And_Play.bat": b"x", "readme.txt": b"r"}), "--name", "G")
        self.assertIn("nothing to start", str(e.exception))

    def test_a_card_of_the_longest_fields_is_cut_to_fit_16_kib_and_the_game_still_publishes(self):
        emoji = "\U0001F600"
        deep = "/".join([emoji * 60] * 4) + "/Game.bat"
        flags = ["--name", emoji * 60, "--slug", "emoji", "--description", emoji * 400, "--online", emoji * 200, "--run", deep, *[f for _ in range(16) for f in ("--args", emoji * 200)]]
        meta, out, _ = self.dry(self.folder({deep: "@echo off\n", "readme.txt": "r"}), *flags)
        archive = out / meta["zip"]["name"]
        written = packed(archive)[gm.CARD_FILE]
        self.assertLessEqual(len(written), gm.MAX_CARD)
        self.assertEqual(gm.read(archive)["card"]["name"], emoji * 60, "a reader takes the card that was written")
        self.assertNotIn("args", json.loads(written))
        self.assertEqual(packed(archive)["launch.args"].decode().count("\n"), 16, "the arguments are still the game's, in launch.args")

    def test_an_online_note_that_is_an_address_is_refused(self):
        plain = self.folder({"Game.bat": "@echo off\n"})
        with self.assertRaises(SystemExit) as e:
            self.dry(plain, "--name", "G", "--online", "Join 203.0.113.5:27015")
        self.assertIn("never an address", str(e.exception))
        meta, _, _ = self.dry(plain, "--name", "G", "--online", "Co-op for two.")
        self.assertEqual(meta["online"], "Co-op for two.")

    def test_a_new_screenshot_of_the_other_kind_leaves_no_old_one_in_the_zip(self):
        shot = self.tmp / "new.jpg"
        shot.write_bytes(b"jpeg")
        source = make_zip(self.tmp / "g.zip", {"Game.bat": b"@echo off\n", "redengine-game-thumb.png": b"old png", gm.CARD_FILE: json.dumps({"name": "G", "thumb": "redengine-game-thumb.png"}).encode()})
        meta, out, _ = self.dry(source, "--thumb", str(shot))
        files = packed(out / meta["zip"]["name"])
        self.assertEqual((sorted(n for n in files if n.startswith("redengine-game-thumb")), json.loads(files[gm.CARD_FILE])["thumb"]), (["redengine-game-thumb.jpg"], "redengine-game-thumb.jpg"))

    def test_the_card_in_a_zips_comment_is_read_though_unpacking_loses_it(self):
        # As the app reads it (`upload::stage` reads the comment first): the comment ranks below the card file and above a script's header.
        source = self.tmp / "g.zip"
        with zipfile.ZipFile(source, "w") as z:
            z.writestr("Game/Game.bat", "@echo off\r\nREM redengine-game\r\nREM name: From The Header\r\nREM author: ai\r\n")
            z.comment = b'redengine-game {"name": "From The Comment", "description": "Said in the comment.", "presentation": "2d", "entry": "Game.bat"}'
        meta, out, _ = self.dry(source)
        self.assertEqual((meta["name"], meta["description"], meta["presentation"], meta["author"], meta["entry"]), ("From The Comment", "Said in the comment.", "2d", "ai", "Game.bat"))
        self.assertEqual(json.loads(packed(out / meta["zip"]["name"])[gm.CARD_FILE])["name"], "From The Comment")
        with zipfile.ZipFile(source, "a") as z:
            z.writestr("Game/" + gm.CARD_FILE, json.dumps({"name": "From The File"}))
        meta, _, _ = self.dry(source)
        self.assertEqual((meta["name"], meta["description"]), ("From The File", "Said in the comment."))

    def test_a_screenshot_over_5_mb_is_the_releases_but_does_not_go_into_the_game(self):
        # As the app does (`upload::write_card`): a reader ignores a card's picture that big, so the game carries none and its card names none.
        shot = self.tmp / "big.png"
        shot.write_bytes(b"\x89PNG" + b"\0" * gm.MAX_THUMB)
        source = make_zip(self.tmp / "g.zip", {"Game.bat": b"@echo off\n", "redengine-game-thumb.jpg": b"old jpg", gm.CARD_FILE: json.dumps({"name": "G", "thumb": "redengine-game-thumb.jpg"}).encode()})
        meta, out, _ = self.dry(source, "--thumb", str(shot))
        self.assertEqual(meta["thumb"], "g-1-thumb.png")
        self.assertEqual((out / meta["thumb"]).read_bytes(), shot.read_bytes())
        files = packed(out / meta["zip"]["name"])
        self.assertEqual([n for n in files if n.startswith(gm.THUMB_STEM)], [], "neither the big picture nor the old one it replaces")
        self.assertNotIn("thumb", json.loads(files[gm.CARD_FILE]))
        self.assertNotIn("thumb", gm.read(out / meta["zip"]["name"])["card"])

    def test_a_game_with_its_own_launch_args_says_so_in_its_card_and_keeps_the_file(self):
        source = make_zip(self.tmp / "g.zip", {"RedEngine.exe": b"MZ", "engine.name": b"RedEngine.exe\n", "launch.args": b"content/map.json\n  --windowed  \n"})
        meta, out, _ = self.dry(source, "--name", "Engine Game")
        files = packed(out / meta["zip"]["name"])
        self.assertEqual(json.loads(files[gm.CARD_FILE])["args"], ["content/map.json", "--windowed"])
        self.assertEqual(files["launch.args"], b"content/map.json\n  --windowed  \n", "the file the game came with is not rewritten")
        meta, out, _ = self.dry(source, "--name", "Engine Game", "--run", "RedEngine.exe")
        self.assertNotIn("args", json.loads(packed(out / meta["zip"]["name"])[gm.CARD_FILE]), "with --run the arguments are not known to be for it")

    def test_an_argument_that_starts_with_dashes_goes_with_args(self):
        meta, out, _ = self.dry(self.folder({"Game.bat": "@echo off\n"}), "--name", "G", "--args", "--fullscreen", "--args", "level 2", "--notes", "- fixed")
        self.assertEqual(packed(out / meta["zip"]["name"])["launch.args"], b"--fullscreen\nlevel 2\n")
        self.assertEqual(meta["notes"], ["- fixed"])

    def test_a_name_that_only_the_game_gave_says_which_game_it_makes_a_new_version_of(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            meta, _, _ = self.dry(DATA / "zip-top-folder.zip", history={"star-miner": [self.PREVIOUS]})
        self.assertEqual(meta["version"], 3)
        self.assertIn("version 3 of star-miner", err.getvalue())
        self.assertIn("kept by someone", err.getvalue())
        self.assertIn("--slug", err.getvalue())
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.dry(DATA / "zip-top-folder.zip", "--name", "Star Miner", history={"star-miner": [self.PREVIOUS]})
        self.assertEqual(err.getvalue(), "", "a name that was typed is meant")

    def test_a_scripts_notes_are_not_the_next_builds(self):
        # The script ships unchanged inside the published ZIP: notes in its header would come back as the next build's "what changed".
        script = self.tmp / "Quest.bat"
        script.write_text("@echo off\r\nREM redengine-game\r\nREM name: Text Quest\r\nREM notes: First release.\r\nREM notes: Fixed the door.\r\necho hi\r\n", encoding="utf-8")
        meta, out, _ = self.dry(script)
        self.assertEqual((meta["version"], meta["notes"]), (1, ["First release."]))
        first = self.tmp / "text-quest-1-windows-x64.zip"
        shutil.copy2(out / meta["zip"]["name"], first)
        self.assertIn(b"REM notes: Fixed the door.", packed(first)["Quest.bat"], "the script is published as it is")
        with contextlib.redirect_stderr(io.StringIO()):
            again, _, _ = self.dry(first, history={"text-quest": [meta]})
        self.assertEqual((again["version"], again["notes"]), (2, ["A new build."]))

    def test_a_cards_args_are_for_its_own_entry_only(self):
        # GAME_METADATA.md: they are for the card's own entry, never for another program the poster picks (as `Staged::args_for` in the app).
        card = json.dumps({"name": "Fast Game", "entry": "Game.exe", "args": ["--fast", "--level=9"]})
        root = self.folder({"Game.exe": "MZ", "Editor.exe": "MZ", gm.CARD_FILE: card})
        meta, out, _ = self.dry(root, "--run", "Editor.exe")
        files = packed(out / meta["zip"]["name"])
        self.assertEqual((meta["entry"], files["launch.args"]), ("Editor.exe", b""))
        self.assertNotIn("args", json.loads(files[gm.CARD_FILE]), "the other program does not start with the card's arguments")
        for flags in ((), ("--run", "Game.exe")):
            meta, out, _ = self.dry(root, *flags)
            files = packed(out / meta["zip"]["name"])
            self.assertEqual((meta["entry"], files["launch.args"], json.loads(files[gm.CARD_FILE])["args"]), ("Game.exe", b"--fast\n--level=9\n", ["--fast", "--level=9"]), flags)
        # engine.name starts another program than the card's entry: the card's arguments are not for it either.
        card = json.dumps({"name": "Two Bats", "entry": "B.bat", "args": ["--for-b-only"]})
        meta, out, _ = self.dry(self.folder({"A.bat": "@echo off\n", "B.bat": "@echo off\n", "engine.name": "A.bat\n", gm.CARD_FILE: card}))
        files = packed(out / meta["zip"]["name"])
        self.assertEqual((meta["entry"], files["launch.args"]), ("A.bat", b""))
        self.assertNotIn("args", json.loads(files[gm.CARD_FILE]))
        # A card that names no program speaks for the one the game starts with.
        meta, out, _ = self.dry(self.folder({"Game.bat": "@echo off\n", gm.CARD_FILE: json.dumps({"name": "One Bat", "args": ["--x"]})}))
        self.assertEqual(packed(out / meta["zip"]["name"])["launch.args"], b"--x\n")

    def test_a_description_from_version_information_never_replaces_the_previous_releases(self):
        # As the window keeps the site's words over the program's file information (app.js applyGameSays).
        previous = {"kind": "upload", "slug": "version-quest", "name": "Version Quest", "version": 1, "description": "The site's own words."}
        with contextlib.redirect_stderr(io.StringIO()):
            meta, _, _ = self.dry(DATA / "versioned.exe", history={"version-quest": [previous]})
            self.assertEqual((meta["version"], meta["description"]), (2, "The site's own words."))
            meta, _, _ = self.dry(DATA / "versioned.exe", "--description", "Typed.", history={"version-quest": [previous]})
            self.assertEqual(meta["description"], "Typed.")
        meta, _, _ = self.dry(DATA / "versioned.exe")
        self.assertEqual(meta["description"], "A game that only has version information.", "a new game takes it")
        stamped = self.tmp / "Game.exe"  # words the creator put in the game itself still replace the site's
        shutil.copy2(DATA / "versioned.exe", stamped)
        with contextlib.redirect_stderr(io.StringIO()):
            gm.stamp(stamped, {"description": "Stamped words."})
            meta, _, _ = self.dry(stamped, history={"version-quest": [previous]})
        self.assertEqual(meta["description"], "Stamped words.")

    def test_the_name_an_engine_gives_its_own_program_does_not_name_the_game(self):
        # Moonlit Quest/Game.exe is NW.js's own program, as RPG Maker MV ships it: "nwjs" is no game's name, and the tool asks for one.
        with self.assertRaises(SystemExit) as e:
            self.dry(DATA / "zip-runtime-program.zip")
        self.assertIn("no name", str(e.exception))
        meta, _, _ = self.dry(DATA / "zip-runtime-program.zip", "--name", "Moonlit Quest")
        self.assertEqual((meta["slug"], meta["description"], meta["entry"]), ("moonlit-quest", "Moonlit Quest, a Windows game.", "Game.exe"))

    def test_a_name_that_makes_no_id_is_not_the_games(self):
        card = json.dumps({"name": "\u661f\u306e\u65c5", "description": "Words."}, ensure_ascii=False)
        with self.assertRaises(SystemExit) as e:
            self.dry(self.folder({"Game.bat": "@echo off\n", gm.CARD_FILE: card}))
        self.assertIn("no name", str(e.exception))
        meta, _, _ = self.dry(self.folder({"Game.bat": "@echo off\n", gm.CARD_FILE: card}), "--name", "Star Journey")
        self.assertEqual((meta["slug"], meta["description"]), ("star-journey", "Words."))


if __name__ == "__main__":
    unittest.main()
