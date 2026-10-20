import contextlib
import importlib.util
import io
import json
import os
import random
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import time
import tracemalloc
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import game_meta as gm

DATA = Path(__file__).resolve().parent / "testdata" / "game_meta"
EXPECTED = json.loads((DATA / "expected.json").read_text(encoding="utf-8"))


def builder():
    """build_fixtures.py as a module (without leaving a bytecode file in the fixtures folder)."""
    spec = importlib.util.spec_from_file_location("build_fixtures", DATA / "build_fixtures.py")
    module = importlib.util.module_from_spec(spec)
    keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = keep
    return module


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = gm.main([str(a) for a in argv])
    return code, out.getvalue(), err.getvalue()


class Scratch(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def copy(self, fixture: str, as_name: str | None = None) -> Path:
        src = DATA / fixture
        dst = self.tmp / (as_name or Path(fixture).name)
        shutil.copytree(src, dst) if src.is_dir() else shutil.copyfile(src, dst)
        return dst

    def folder(self, files: dict[str, bytes | str]) -> Path:
        root = self.tmp / f"game{len(list(self.tmp.iterdir()))}"
        for rel, data in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data.encode() if isinstance(data, str) else data)
        root.mkdir(exist_ok=True)
        return root


class Conformance(unittest.TestCase):
    """The fixtures shared with the app: what is committed is what the builder writes, and the reader finds what `expected.json` says."""

    def test_the_committed_fixtures_are_what_the_builder_writes(self):
        made = builder().files()
        there = {p.relative_to(DATA).as_posix(): p.read_bytes() for p in DATA.rglob("*")
                 if p.is_file() and "__pycache__" not in p.parts and p.name != "build_fixtures.py"}
        hint = "run `python3 distribution/testdata/game_meta/build_fixtures.py` and commit the result"
        self.assertEqual(sorted(there), sorted(made), hint)
        for path, data in made.items():
            self.assertEqual(there[path], data, f"{path} differs: {hint}")

    def test_the_builder_is_deterministic(self):
        self.assertEqual(builder().files(), builder().files())

    def test_every_fixture_reads_as_expected(self):
        for path, want in EXPECTED["fixtures"].items():
            with self.subTest(path):
                self.assertEqual(gm.read(DATA / path), want)

    def test_every_fixture_is_in_expected_json(self):
        listed = {p.split("/")[0] for p in EXPECTED["fixtures"]}
        on_disk = {p.name for p in DATA.iterdir() if p.name not in ("build_fixtures.py", "expected.json", ".gitattributes", "__pycache__")}
        self.assertEqual(on_disk, listed)

    def test_the_cases_the_spec_lists_are_all_there(self):
        for name in ("folder-card", "zip-top-folder.zip", "zip-comment-only.zip", "header-rem-crlf.bat", "header-atrem-lf.bat", "header-colons-bom.bat", "stamped.exe",
                     "versioned.exe", "both.exe", "overlay.exe", "signed.exe", "hostile-bad-json", "hostile-json-array", "hostile-control-bidi", "truncated.exe",
                     "lying-record-length.exe", "hostile-entry-dotdot", "hostile-entry-absolute", "hostile-entry-drive-abs", "hostile-thumb-escape", "hostile-deep-json"):
            self.assertTrue(any(p == name or p.startswith(name + "/") for p in EXPECTED["fixtures"]), name)

    def test_the_reader_is_not_just_answering_nothing(self):
        found = [p for p, want in EXPECTED["fixtures"].items() if want["card"]]
        self.assertGreater(len(found), 40)
        self.assertEqual({s for want in EXPECTED["fixtures"].values() for s in want["from"].values()}, set(gm.SOURCES))

    def test_the_stamp_refusals_are_the_ones_listed_and_change_nothing(self):
        self.assertGreaterEqual(len(EXPECTED["stamp_refused"]), 8)
        for path in EXPECTED["stamp_refused"]:
            with self.subTest(path):
                tmp = Path(tempfile.mkdtemp())
                self.addCleanup(shutil.rmtree, tmp, True)
                copy = tmp / Path(path).name
                shutil.copyfile(DATA / path, copy)
                with self.assertRaises(SystemExit) as e:
                    gm.stamp(copy, {"name": "Nope"})
                self.assertTrue(str(e.exception))
                self.assertEqual(copy.read_bytes(), (DATA / path).read_bytes())
                self.assertEqual([p.name for p in tmp.iterdir()], [copy.name], "no half-written file is left")

    def test_every_other_single_file_can_be_stamped_and_reads_back_stamped(self):
        for path in EXPECTED["fixtures"]:
            if "/" in path or not path.endswith((".exe", ".bat", ".cmd")) or path in EXPECTED["stamp_refused"]:
                continue
            with self.subTest(path):
                tmp = Path(tempfile.mkdtemp())
                self.addCleanup(shutil.rmtree, tmp, True)
                copy = tmp / Path(path).name
                shutil.copyfile(DATA / path, copy)
                gm.stamp(copy, {"name": "Stamped Name", "author": "human"})
                found = gm.read(copy)
                self.assertEqual(found["card"]["name"], "Stamped Name")
                self.assertEqual(found["card"]["author"], "human")


class Cleaning(unittest.TestCase):
    def test_white_space_controls_and_direction_overrides(self):
        self.assertEqual(gm.clean("  a \t\n  b  "), "a b")
        self.assertEqual(gm.clean("a\x00b\x07c\x7fd"), "abcd")
        self.assertEqual(gm.clean("a\x85b\u00a0c\u3000d\u2029e\u202fg"), "a b c d e g")
        self.assertEqual(gm.clean("a\x1fb"), "ab", "separator controls are controls, not white space")
        for c in [*range(0x202A, 0x202F), *range(0x2066, 0x206A)]:
            self.assertEqual(gm.clean(f"a{chr(c)}b"), "ab", hex(c))
        for c in (0x2029, 0x2065, 0x206A, 0x200B, 0xFEFF):  # next to the overrides, or invisible but not on the list
            self.assertEqual(gm.clean(f"a{chr(c)}b"), "a b" if c == 0x2029 else f"a{chr(c)}b", hex(c))
        self.assertEqual(gm.clean("a\ud800b"), "ab")

    def test_a_long_string_is_cut_never_refused(self):
        self.assertEqual(gm.clean("abcdef", 3), "abc")
        self.assertEqual(gm.clean("abc def", 4), "abc", "a cut does not leave a space at the end")
        self.assertEqual(gm.clean("é" * 10, 4), "é" * 4, "the limit counts characters")
        self.assertEqual(gm.clean("x" * 10, 10), "x" * 10)

    def test_cleaning_twice_changes_nothing(self):
        rng = random.Random(7)
        alphabet = "ab \t\n\x00\x85\u00a0\u202e\u2066\ud800.-"
        for _ in range(300):
            text = "".join(rng.choice(alphabet) for _ in range(rng.randrange(40)))
            for limit in (None, 5, 17):
                once = gm.clean(text, limit)
                self.assertEqual(gm.clean(once, limit), once, repr(text))


class FakeGame:
    def __init__(self, *files: str):
        self.files = set(files)

    def is_file(self, rel, max_size=None):
        return rel in self.files


class Rules(unittest.TestCase):
    def test_types_and_enumerations(self):
        card = gm.check_card({"schema": 9, "name": 5, "description": ["x"], "presentation": "2D", "author": "Human", "online": True, "future": 1})
        self.assertEqual(card, {})
        self.assertEqual(gm.check_card({"presentation": "hybrid", "author": " ai "}), {"presentation": "hybrid", "author": "ai"})
        self.assertEqual(gm.check_card({"kind": "3d"}), {"presentation": "3d"})
        self.assertEqual(gm.check_card({"presentation": "4d", "kind": "2d"}), {"presentation": "2d"}, "the first of the two that is one of the three")
        self.assertEqual(gm.check_card({"presentation": "2d", "kind": "3d"}), {"presentation": "2d"})

    def test_args_and_notes(self):
        self.assertEqual(gm.check_card({"args": ["a", " ", " b  c "]}), {"args": ["a", "b c"]})
        self.assertEqual(gm.check_card({"args": ["a", 1]}), {}, "an array that is not all strings is not found")
        self.assertEqual(gm.check_card({"notes": "x"}), {})
        self.assertEqual(len(gm.check_card({"args": [str(i) for i in range(30)]})["args"]), 16)
        self.assertEqual(len(gm.check_card({"notes": [str(i) for i in range(30)]})["notes"]), 10)
        self.assertEqual(gm.check_card({"notes": ["y" * 300]})["notes"], ["y" * 200])

    def test_forked_from(self):
        good = {"slug": "neon-snake2", "version": 1}
        self.assertEqual(gm.check_card({"forked_from": good}), {"forked_from": good})
        for bad in ({"slug": "Snake", "version": 1}, {"slug": "a--b", "version": 1}, {"slug": "-a", "version": 1}, {"slug": "a-", "version": 1}, {"slug": "a b", "version": 1},
                    {"slug": "a\n", "version": 1}, {"slug": "", "version": 1}, {"slug": "a", "version": 0}, {"slug": "a", "version": -1}, {"slug": "a", "version": "3"},
                    {"slug": "a", "version": 3.0}, {"slug": "a", "version": True}, {"slug": "a", "version": 2**64}, {"slug": "a"}, {"version": 1}, "a@1", ["a", 1], 3):
            self.assertEqual(gm.check_card({"forked_from": bad}), {}, bad)

    def test_an_entry_is_a_runnable_file_inside_the_game(self):
        game = FakeGame("Game.exe", "bin/Run.bat", "Up.CMD", "Game.txt", "a b/c.exe", "../Game.exe", "bin/../Game.exe", "C:/Game.exe", "C:Game.exe", "bin\\Run.bat", "/Game.exe",
                        "Game.exe:stream", "./Game.exe", "bin//Run.bat", "Game.exe/", "x" * 300 + ".exe")
        for entry in ("Game.exe", "bin/Run.bat", "Up.CMD", "a b/c.exe"):
            self.assertEqual(gm.check_card({"entry": entry}, game), {"entry": entry}, entry)
        for entry in ("/Game.exe", "../Game.exe", "bin/../Game.exe", "C:/Game.exe", "C:Game.exe", "bin\\Run.bat", "Game.txt", "Missing.exe", "", "bin//Run.bat", "./Game.exe",
                      "Game.exe/", "Game.exe:stream", "bin/", "..", "x" * 300 + ".exe", 5):
            self.assertEqual(gm.check_card({"entry": entry}, game), {}, entry)
        self.assertEqual(gm.check_card({"entry": "Anything.exe"}), {"entry": "Anything.exe"}, "not asked: not checked")

    def test_a_thumb_is_a_picture_inside_the_game(self):
        game = FakeGame("shot.png", "media/a.jpg", "a.jpeg", "a.gif", "Game.exe", "../shot.png", "/shot.png", "media\\a.jpg", "C:shot.png")
        for thumb in ("shot.png", "media/a.jpg"):
            self.assertEqual(gm.check_card({"thumb": thumb}, game), {"thumb": thumb})
        for thumb in ("a.jpeg", "a.gif", "Game.exe", "../shot.png", "/shot.png", "media\\a.jpg", "nope.png", "C:shot.png"):
            self.assertEqual(gm.check_card({"thumb": thumb}, game), {}, thumb)

    def test_a_card_text_that_is_not_one_is_ignored_whole(self):
        ok = b'{"name": "Fine"}'
        self.assertEqual(gm.parse_card(ok), {"name": "Fine"})
        self.assertEqual(gm.parse_card(b"\xef\xbb\xbf" + ok), {"name": "Fine"}, "a byte order mark is allowed")
        self.assertEqual(gm.parse_card(b'{"name": "a", "name": "b"}'), {"name": "b"}, "the last duplicate wins, as in JSON readers generally")
        for bad in (b"", b"[]", b"3", b'"x"', b"null", b'{"a": NaN}', b'{"a": Infinity}', b'{"a": -Infinity}', b'{"a": ', b'{"a": 1}}', b"\xff\xfe{}", b'{"a": "\xff"}',
                    b'{"a": "\\ud800"}', b'{"a": "\\udc00x"}', b'{"a": ' + b"[" * 200 + b"]" * 200 + b"}", b"{" * 5000, b'{"a": ' + b"9" * 20000 + b"}"):
            self.assertIsNone(gm.parse_card(bad), bad[:40])
        self.assertEqual(gm.parse_card(b'{"a": "\\ud83d\\ude00"}'), {"a": "\U0001F600"}, "a surrogate pair is a character")
        self.assertIsNotNone(gm.parse_card(b'{"a": ' + b"[" * 100 + b"]" * 100 + b"}"))
        big = b'{"name": "x", "pad": "' + b"p" * (gm.MAX_CARD - 24) + b'"}'
        self.assertEqual(len(big), gm.MAX_CARD)
        self.assertIsNotNone(gm.parse_card(big))
        self.assertIsNone(gm.parse_card(big + b" "))


class Newer(Scratch):
    """Rules added when the first ones were attacked."""

    def test_a_device_name_is_no_path_a_card_may_name(self):
        for text in ("aux.exe", "bin/CON.bat", "nul.cmd", "bin/com1.exe", "LPT9.EXE", "con .exe", "Conout$.exe"):
            self.assertIsNone(gm.safe_path(text), text)
        for text in ("console.exe", "bin/auxiliary.bat", "com10.exe", "xcon.cmd", "game.con"):
            self.assertEqual(gm.safe_path(text), text, text)

    def test_online_notes_that_are_addresses_or_keys_are_not_found(self):
        for note in ("Join 203.0.113.5:27015 with key hunter2", "https://example.com/join?k=abc", "play.example.com:27015", "localhost:8080", "discord.gg/abc123",
                     "connect to 10.0.0.1", "www.mygame.net", "fe80::1", "2001:db8:0:0:0:0:0:1", "[::1]:27015", "token=abc", "user@host.io", "Join example.com.", "KEY=Secret",
                     "(server:27016)"):
            self.assertTrue(gm.looks_like_address(note), note)
            self.assertEqual(gm.check_card({"name": "G", "online": note}), {"name": "G"}, note)
        for note in ("Up to four players on one LAN.", "Co-op: two players", "2-4 players online (LAN or internet)", "Ratio 16:9 and 12:30 pm", "version 1.2.3 needed",
                     "e.g. two friends", "Online play: ping 30ms", "Two players, same room.", "Supports 2-4 players (LAN)", "Co-op.Fun"):
            self.assertFalse(gm.looks_like_address(note), note)
            self.assertEqual(gm.check_card({"name": "G", "online": note})["online"], note, note)
        root = self.folder({"Game.bat": "x"})
        with self.assertRaises(SystemExit) as e:
            gm.stamp(root, {"online": "Join 203.0.113.5"})
        self.assertIn("never an address", str(e.exception))

    def test_a_fork_takes_none_of_its_parents_words_from_a_script_or_program(self):
        script = "REM redengine-game\nREM name: Parent\nREM description: Parent's words.\nREM author: ai\nREM online: LAN\nREM notes: n\nREM presentation: 3d\n"
        root = self.folder({"Game.bat": script})
        self.assertEqual(gm.read(root)["card"], {"name": "Parent", "description": "Parent's words.", "presentation": "3d", "author": "ai", "online": "LAN", "notes": ["n"]})
        self.assertEqual(gm.read(root, fork=True)["card"], {"name": "Parent", "presentation": "3d"}, "the caller knows it is a fork")
        card = self.folder({"Game.bat": script, gm.CARD_FILE: json.dumps({"forked_from": {"slug": "snake", "version": 1}})})
        self.assertEqual(gm.read(card)["card"], {"forked_from": {"slug": "snake", "version": 1}, "name": "Parent", "presentation": "3d"}, "so does a card that says it")
        self.assertEqual(gm.read(self.folder({"Game.bat": script, gm.CARD_FILE: json.dumps({"description": "Its own."})}))["card"]["description"], "Its own.")

    def test_a_program_that_was_signed_after_it_was_stamped_still_says_what_it_said(self):
        for name in ("signed-after-record.exe", "signed-after-record-padded.exe"):
            program = self.copy(name)
            found = gm.read(program)
            self.assertTrue(found["card"]["name"].startswith("Signed After") and found["from"]["name"] == "exe", name)
            with self.assertRaises(SystemExit) as e:
                gm.stamp(program, {"name": "Again"})
            self.assertIn("signed", str(e.exception))
        self.assertEqual(gm.read(self.copy("signed.exe"))["card"], {}, "a signed program with no record says nothing")


class Comments(Scratch):
    def test_the_comment_is_the_name_of_the_tool_a_space_and_the_card(self):
        build = builder()
        for comment, found in ((b'redengine-game {"name": "A"}', {"name": "A"}), (b'redengine-game\t{"name": "A"}', {"name": "A"}), (b'redengine-game   {"name": "A"}\n', {"name": "A"}),
                               (b'redengine-game{"name": "A"}', {}), (b'redengine-gamex {"name": "A"}', {}), (b'Redengine-Game {"name": "A"}', {}), (b'{"name": "A"}', {}),
                               (b"redengine-game", {}), (b"redengine-game ", {}), (b"redengine-game [1]", {}), (b'a redengine-game {"name": "A"}', {})):
            archive = self.tmp / "c.zip"
            archive.write_bytes(build.zip_bytes([("Game.bat", b"x", "stored")], comment))
            self.assertEqual(gm.read(archive)["card"], found, comment)


class Scripts(Scratch):
    def header(self, *lines: str, eol: str = "\n", bom: bool = False) -> dict | None:
        data = (b"\xef\xbb\xbf" if bom else b"") + eol.join(lines).encode()
        return gm._header(data)

    def test_the_marker(self):
        for marker in ("REM redengine-game", "rem redengine-game", "@REM redengine-game", "@rem\tredengine-game", "::redengine-game", ":: redengine-game", "  REM  redengine-game  ",
                       "\tREM redengine-game"):
            self.assertEqual(self.header(marker, "REM name: X"), {"name": " X"}, marker)
        for marker in ("REMARK redengine-game", "REM redengine-game2", "REM Redengine-game", "REM: redengine-game", "ECHO REM redengine-game", "REM redengine game", "@@REM redengine-game"):
            self.assertIsNone(self.header(marker, "REM name: X"), marker)

    def test_a_block_ends_at_the_first_line_that_is_not_a_comment(self):
        self.assertEqual(self.header("REM redengine-game", "REM name: A", "", "REM author: ai"), {"name": " A"})
        self.assertEqual(self.header("REM redengine-game", "REM name: A", "REM", "::", "@REM author: ai"), {"name": " A", "author": " ai"}, "comment lines without a key go on")
        self.assertEqual(self.header("REM redengine-game", "REM name: A", "echo x", "REM author: ai"), {"name": " A"})
        self.assertEqual(self.header("REM redengine-game", "REM name: A", "REM name: B"), {"name": " B"}, "the last one wins")
        self.assertEqual(self.header("REM redengine-game", "REM notes: a", "REM notes: b", "REM args: --x", "REM args:y", "REM bogus: z"),
                         {"notes": [" a", " b"], "args": [" --x", "y"]})
        self.assertEqual(self.header("REM redengine-game", "REM name: A", "REM redengine-game", "REM name: B"), {"name": " B"}, "a second marker is a comment line")
        self.assertEqual(self.header("REM redengine-game", "REM thumb: C:\\x.png", "REM description: a: b"), {"thumb": " C:\\x.png", "description": " a: b"}, "split at the first colon")

    def test_a_comment_line_is_a_comment_to_cmd(self):
        self.assertEqual(self.header("REM redengine-game", "REMname: X"), {}, "`REMname:` is no comment: it ends the block")
        self.assertIsNone(self.header("REMredengine-game", "REM name: X"))
        self.assertEqual(self.header("REM redengine-game", "@REM name: X", "  ::author: ai"), {"name": " X", "author": " ai"})

    def test_line_ends_and_the_byte_order_mark(self):
        for eol in ("\n", "\r\n"):
            self.assertEqual(self.header("@echo off", "REM redengine-game", "REM name: A", "echo x", eol=eol), {"name": " A"})
            self.assertEqual(self.header("@echo off", "REM redengine-game", "REM name: A", "echo x", eol=eol, bom=True), {"name": " A"})
        self.assertEqual(self.header("REM redengine-game\rREM name: A", "echo x"), None, "a lone carriage return is not a line end")

    def test_only_the_first_64_lines_are_read(self):
        lines = ["echo x"] * 63
        self.assertEqual(self.header(*lines, "REM redengine-game"), {}, "a marker on line 64 starts a block of nothing")
        self.assertEqual(self.header(*lines[:-1], "REM redengine-game", "REM name: A", "REM author: ai"), {"name": " A"})
        self.assertIsNone(self.header(*lines, "echo y", "REM redengine-game", "REM name: A"))

    def test_the_header_of_a_huge_line_is_not_read_whole(self):
        script = self.tmp / "big.bat"
        script.write_bytes(b"REM redengine-game\nREM name: A\nREM description: " + b"d" * 20_000_000 + b"\n")
        self.assertEqual(gm.read(script)["card"], {"name": "A", "description": "d" * 400})

    def test_the_line_after_a_block_is_never_taken_for_part_of_it(self):
        script = self.tmp / "q.bat"
        script.write_bytes(b"REM This script starts the game.\r\n@echo off\r\n")
        gm.stamp(script, {"name": "Q"})
        data = script.read_bytes()
        self.assertEqual(data, b"@REM redengine-game\r\n@REM name: Q\r\n\r\nREM This script starts the game.\r\n@echo off\r\n")
        self.assertEqual(gm.read(script)["card"], {"name": "Q"})
        script.write_bytes(b"@echo off\r\nREM Usage: Quest.bat\r\n")
        gm.stamp(script, {"name": "Q"})
        self.assertEqual(script.read_bytes(), b"@echo off\r\n@REM redengine-game\r\n@REM name: Q\r\n\r\nREM Usage: Quest.bat\r\n")
        self.assertEqual(gm.read(script)["card"], {"name": "Q"})


class Programs(Scratch):
    def test_the_record_and_its_limits(self):
        build = builder()
        card = {"name": "Rec"}
        for data, ok in ((build.pe(tail=build.record(card)), True), (build.pe(tail=build.record(card, length=len(build.compact(card)) + 1)), False),
                         (build.pe(tail=build.record(b"x" * gm.MAX_CARD)), False), (b"REDGAME1", False), (b"\0\0\0\0REDGAME1", False)):
            program = self.tmp / "p.exe"
            program.write_bytes(data)
            found = gm.read(program)["card"]
            self.assertEqual(found, {"name": "Rec"} if ok else {}, data[-20:])

    def test_a_record_in_a_program_of_any_other_kind_still_reads_as_a_record(self):
        build = builder()
        program = self.tmp / "p.exe"
        program.write_bytes(b"not a PE file at all" + build.record({"name": "Odd"}))
        self.assertEqual(gm.read(program)["card"], {"name": "Odd"})

    def test_version_information_rules(self):
        build = builder()

        def info(*pairs):
            program = self.tmp / "v.exe"
            program.write_bytes(build.pe(build.resources(build.version_info(list(pairs)))))
            return gm.read(program)["card"]
        self.assertEqual(info(("ProductName", "Star  Miner"), ("Comments", "C"), ("FileDescription", "F")), {"name": "Star Miner", "description": "C"})
        self.assertEqual(info(("ProductName", "Star Miner"), ("FileDescription", "F")), {"name": "Star Miner", "description": "F"})
        self.assertEqual(info(("ProductName", "Application"), ("FileDescription", "Game")), {}, "ignored whatever the case")
        self.assertEqual(info(("ProductName", " APP "), ("Comments", "gAmE"), ("FileDescription", "Real")), {"description": "Real"})
        self.assertEqual(info(("ProductName", "Star Miner"), ("FileDescription", "star miner")), {"name": "Star Miner"})
        self.assertEqual(info(("ProductName", "N" * 100), ("Comments", "D" * 500)), {"name": "N" * 60, "description": "D" * 400})
        self.assertEqual(info(("ProductName", "A\x00B")), {"name": "A"}, "a value ends at its terminator")
        self.assertEqual(info(("CompanyName", "Nobody"), ("ProductName", "X")), {"name": "X"})

    def test_a_version_resource_of_more_than_64_kib_is_not_read(self):
        build = builder()
        blob = build.version_info([("ProductName", "Big")])
        program = self.tmp / "big.exe"
        for size, found in ((len(blob), {"name": "Big"}), (0x10000, {"name": "Big"}), (0x10001, {})):
            program.write_bytes(build.pe(build.resources(blob, size=size) + b"\0" * 0x20000))
            self.assertEqual(gm.read(program)["card"], found, hex(size))

    def test_version_information_is_only_read_for_the_program_that_starts_the_game(self):
        build = builder()
        versioned = build.pe(build.resources(build.version_info([("ProductName", "Editor")])))
        root = self.folder({"Game.exe": b"MZ", "Editor.exe": versioned, "engine.name": "Game.exe\n"})
        self.assertEqual(gm.read(root)["card"], {})
        (root / "engine.name").unlink()
        self.assertEqual(gm.read(root)["card"], {"name": "Editor"}, "the only candidate that says anything")

    def test_programs_that_are_never_the_game_are_not_looked_at(self):
        build = builder()
        root = self.folder({"Setup.exe": build.pe(tail=build.record({"name": "Installer"})), "Game.exe": b"MZ"})
        self.assertEqual(gm.read(root)["card"], {})

    def test_hostile_programs_never_raise_or_hang(self):
        rng = random.Random(2026)
        seeds = [(DATA / n).read_bytes() for n in ("versioned.exe", "versioned32.exe", "both.exe", "stamped.exe", "signed.exe", "overlay-with-record.exe")]
        program = self.tmp / "fuzz.exe"
        for i in range(600):
            data = bytearray(rng.choice(seeds))
            for _ in range(rng.randint(1, 8)):
                kind = rng.random()
                if kind < 0.55:
                    data[rng.randrange(len(data))] = rng.randrange(256)
                elif kind < 0.85 and len(data) > 4:
                    at = rng.randrange(len(data) - 3)
                    data[at:at + 4] = rng.choice([b"\xff\xff\xff\xff", b"\0\0\0\0", b"\xff\xff\xff\x7f", b"\0\0\0\x80", b"\x01\0\0\0"])
                elif len(data) > 8:
                    del data[rng.randrange(8, len(data)):]
            program.write_bytes(bytes(data))
            found = gm.read(program)
            self.assertEqual(set(found), {"card", "from"})
            self.assertEqual(set(found["card"]), set(found["from"]))
            try:
                gm.stamp(program, {"name": "Fuzz"})
            except SystemExit:
                pass

    def test_what_is_read_is_few_and_small_whatever_the_headers_claim(self):
        class Counting:
            def __init__(self, data):
                self.data, self.size, self.asked = data, len(data), []

            def read_at(self, off, n):
                self.asked.append(n)
                return self.data[off:off + n] if off >= 0 and n > 0 else b""

        rng = random.Random(5)
        build = builder()
        seed = (DATA / "versioned.exe").read_bytes() + b"\0" * 100_000
        cases = [seed, build.patched(seed, 0x80 + 6, struct.pack("<H", 5000)), build.patched(seed, 0x80 + 6, struct.pack("<H", 97)), build.patched(seed, 0x80 + 20, struct.pack("<H", 0xFFFF)),
                 build.patched(seed, 0x80 + 24 + 108, struct.pack("<I", 0xFFFFFFFF))]
        for _ in range(300):
            data = bytearray(seed)
            for _ in range(rng.randint(1, 6)):
                data[rng.randrange(0x400)] = rng.randrange(256)
            cases.append(bytes(data))
        for data in cases:
            f = Counting(data)
            gm._pe(f)
            gm._record_length(f)
            gm._program(f)
            self.assertLessEqual(max(f.asked), 0x10000)
            self.assertLessEqual(len(f.asked), 24)

    def test_members_with_unsafe_names_are_not_there(self):
        build = builder()
        archive = self.tmp / "u.zip"
        archive.write_bytes(build.zip_bytes([("Game/redengine-game.json", build.j({"name": "Safe"}), "stored"), ("Game/Game.bat", b"x", "stored"), ("../evil.txt", b"x", "stored"),
                                             ("/abs.txt", b"x", "stored"), ("Game/../up.txt", b"x", "stored")]))
        self.assertEqual(gm.read(archive)["card"], {"name": "Safe"})

    def test_hostile_zips_never_raise(self):
        rng = random.Random(11)
        seeds = [(DATA / n).read_bytes() for n in ("zip-top-folder.zip", "zip-stamped-exe.zip", "zip-card-and-comment.zip", "zip-engine-name.zip", "zip-macosx.zip")]
        archive = self.tmp / "fuzz.zip"
        for _ in range(400):
            data = bytearray(rng.choice(seeds))
            for _ in range(rng.randint(1, 6)):
                if rng.random() < 0.8 or len(data) < 16:
                    data[rng.randrange(len(data))] = rng.randrange(256)
                else:
                    del data[rng.randrange(8, len(data)):]
            archive.write_bytes(bytes(data))
            found = gm.read(archive)
            self.assertEqual(set(found), {"card", "from"})

    def test_a_member_that_would_take_too_long_to_unpack_is_not_looked_into(self):
        build = builder()
        archive = self.tmp / "bomb.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("Game.exe", build.pe(tail=b"\0" * (5 << 20) + build.record({"name": "Hidden"})))
        keep, gm._Member.BUDGET = gm._Member.BUDGET, 1 << 20
        try:
            self.assertEqual(gm.read(archive)["card"], {})
        finally:
            gm._Member.BUDGET = keep
        self.assertEqual(gm.read(archive)["card"], {"name": "Hidden"}, "within the budget it reads")

    def test_a_stored_member_is_read_in_place_whatever_its_size(self):
        build = builder()
        archive = self.tmp / "stored.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as z:
            z.writestr("Game.exe", build.pe(tail=b"\0" * (5 << 20) + build.record({"name": "Seen"})))
        keep, gm._Member.BUDGET = gm._Member.BUDGET, 1 << 10
        try:
            self.assertEqual(gm.read(archive)["card"], {"name": "Seen"})
        finally:
            gm._Member.BUDGET = keep


class Hardening(Scratch):
    """What a hostile game may cost: time, memory and decompression are bounded, whatever the headers and the names claim."""

    def card_zip(self, extra: str, name: str = "g.zip") -> Path:
        """A ZIP of one folder with its card at the root of it, and one more member that makes it two things when it counts."""
        archive = self.tmp / name
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("Game/redengine-game.json", json.dumps({"name": "Names"}))
            z.writestr("Game/Game.bat", "@echo off\n")
            z.writestr(extra, "x")
        return archive

    def test_a_member_with_a_name_of_tens_of_thousands_of_parts_costs_little(self):
        archive = self.tmp / "deep.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("a/" * 16_000 + "x.bat", "@echo off\n")
        tracemalloc.start()
        start = time.process_time()
        try:
            self.assertEqual(gm.read(archive), {"card": {}, "from": {}})
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        self.assertLess(time.process_time() - start, 3, "a name of 32 000 bytes was once 3 seconds and 266 MB")
        self.assertLess(peak, 32 << 20)
        with zipfile.ZipFile(archive, "w") as z:  # many members that are each as deep as they may be: a folder costs what its name does
            for i in range(300):
                z.writestr(f"d{i}/" + "/".join(f"p{k}" for k in range(60)) + "/x.txt", "x")
        tracemalloc.start()
        try:
            gm.read(archive)
            self.assertLess(tracemalloc.get_traced_memory()[1], 64 << 20)
        finally:
            tracemalloc.stop()

    def test_a_member_name_may_be_1024_bytes_and_64_parts_and_no_more(self):
        def seen(extra: str) -> str | None:
            return gm.read(self.card_zip(extra))["card"].get("name")
        long = lambda n: ("d" * 99 + "/") * ((n - 4) // 100) + "e" * (n - 4 - 100 * ((n - 4) // 100)) + ".txt"  # noqa: E731
        self.assertEqual((len(long(1024)), len(long(1025))), (1024, 1025))
        self.assertEqual((seen(long(1024)), seen(long(1025))), (None, "Names"), "1024 bytes are a member, 1025 are not")
        self.assertEqual((seen("x/" * 63 + "y.txt"), seen("x/" * 64 + "y.txt")), (None, "Names"), "64 parts are a member, 65 are not")
        self.assertEqual(gm.read(self.card_zip("aux.txt"))["card"], {"name": "Names"}, "a device's name is not a member")
        self.assertEqual(gm.read(self.card_zip("Game/COM1"))["card"], {"name": "Names"})

    def counting(self):
        """Patch the decompressor so the bytes it hands out are counted: (the counter, the patch)."""
        done, real = [0], zipfile.ZipExtFile.read

        def read(f, n=-1):
            data = real(f, n)
            done[0] += len(data)
            return data
        return done, mock.patch.object(zipfile.ZipExtFile, "read", read)

    def test_decompression_is_budgeted_for_the_whole_zip_not_for_each_member(self):
        archive = self.tmp / "many.zip"
        program = builder().pe(tail=b"\0" * (4 << 20))
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for i in range(8):
                z.writestr(f"g{i:02d}.exe", program)
        done, patch = self.counting()
        keep, gm._Member.BUDGET = gm._Member.BUDGET, 6 << 20
        try:
            with patch:
                self.assertEqual(gm.read(archive)["card"], {})
        finally:
            gm._Member.BUDGET = keep
        self.assertGreater(done[0], 0)
        self.assertLessEqual(done[0], 6 << 20, "eight members of 4 MiB took 32 MiB when each had a budget of its own")

    def test_a_compressed_member_that_says_it_is_over_64_mib_is_not_opened(self):
        archive = self.tmp / "big.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("Game.exe", builder().pe(tail=b"\0" * (gm._Member.MAX_PACKED + 1) + builder().record({"name": "Hidden"})))
        done, patch = self.counting()
        with patch:
            self.assertEqual(gm.read(archive)["card"], {})
        self.assertEqual(done[0], 0, "nothing of it was decompressed")

    def test_a_member_the_app_could_not_unpack_is_not_there(self):
        for method in (zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA):
            archive = self.tmp / f"m{method}.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("Game/Game.bat", "@echo off\n")
                z.writestr("Game/redengine-game.json", json.dumps({"name": "Packed"}), method)
            self.assertEqual(gm.read(archive)["card"], {}, method)
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("Game.bat", "REM redengine-game\nREM name: Quest\n", zipfile.ZIP_LZMA)
            z.writestr("readme.txt", "r")
        self.assertEqual(gm.read(archive)["card"], {}, "nor is a script that is the only candidate")

    def test_a_name_with_a_nul_is_not_read_up_to_it(self):
        build = builder()
        archive = self.tmp / "nul.zip"
        archive.write_bytes(build.zip_bytes([("Game.bat\0.txt", build.bat(["REM redengine-game", "REM name: Nul"]), "stored")]))
        self.assertEqual(zipfile.ZipFile(archive).namelist(), ["Game.bat"], "what zipfile shows")
        self.assertEqual(gm.read(archive)["card"], {})

    def test_what_is_read_of_a_program_signed_after_it_was_stamped_is_few_and_small(self):
        class Counting:
            def __init__(self, data):
                self.data, self.size, self.asked = data, len(data), []

            def read_at(self, off, n):
                self.asked.append(n)
                return self.data[off:off + n] if off >= 0 and n > 0 else b""

        for name in ("signed-after-record.exe", "signed-after-record-padded.exe", "signed.exe", "unstripped.exe", "symbols-out-of-file.exe"):
            f = Counting((DATA / name).read_bytes())
            gm._record(f)
            gm._pe(f)
            self.assertLessEqual(max(f.asked), 0x10000, name)
            self.assertLessEqual(len(f.asked), 24, name)

    def test_a_junction_is_a_link(self):
        def stat_of(mode: int, attributes: int | None):
            return type("St", (), {"st_mode": mode, **({} if attributes is None else {"st_file_attributes": attributes})})()
        self.assertTrue(gm._link(stat_of(stat.S_IFLNK, None)))
        self.assertTrue(gm._link(stat_of(stat.S_IFDIR, 0x410)), "a Windows reparse point, which a junction is")
        self.assertFalse(gm._link(stat_of(stat.S_IFDIR, 0x10)))
        self.assertFalse(gm._link(stat_of(stat.S_IFREG, None)))

    def test_a_card_that_would_be_over_16_kib_is_refused_and_nothing_is_written(self):
        emoji = "\U0001F600"
        part = emoji * 60
        deep = "/".join([part] * 4)
        root = self.folder({f"{deep}/Game.exe": b"MZ", "readme.txt": "r"})
        fields = {"name": emoji * 60, "description": emoji * 400, "online": emoji * 200, "entry": f"{deep}/Game.exe", "args": [emoji * 200] * 16}
        with self.assertRaises(SystemExit) as e:
            gm.stamp(root, fields)
        self.assertIn("16 KiB", str(e.exception))
        self.assertEqual(sorted(p.name for p in root.iterdir()), sorted([part, "readme.txt"]), "no card file, no half-written file")
        card = gm.check_card(fields)
        self.assertGreater(len(gm._pretty(card).encode()), gm.MAX_CARD)
        cut = gm.fit(card)
        self.assertLessEqual(len(gm.card_text(cut).encode()), gm.MAX_CARD)
        self.assertEqual((cut["name"], "args" in cut, len(cut["description"])), (card["name"], False, 400), "the arguments go first, then the note, the description, the screenshot")
        small = {"name": "Small", "args": ["--x"]}
        self.assertEqual(gm.fit(small), small)
        archive = self.tmp / "g.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr(f"{deep}/Game.exe", b"MZ")
            z.writestr("readme.txt", "r")
        before = archive.read_bytes()
        with self.assertRaises(SystemExit):
            gm.stamp(archive, fields)
        self.assertEqual((archive.read_bytes(), [p.name for p in self.tmp.glob("*.stamping")]), (before, []), "a ZIP is left alone too")

    def test_a_new_screenshot_of_the_other_kind_replaces_the_old_one(self):
        shot = self.tmp / "new.jpg"
        shot.write_bytes(b"jpeg")
        root = self.folder({"Game.bat": "x", "redengine-game-thumb.png": b"png"})
        card = gm.stamp(root, {"name": "G"}, thumb=shot)
        self.assertEqual((card["thumb"], sorted(p.name for p in root.iterdir())), ("redengine-game-thumb.jpg", sorted([gm.CARD_FILE, "Game.bat", "redengine-game-thumb.jpg"])))
        archive = self.tmp / "g.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("Game/Game.bat", "x")
            z.writestr("Game/redengine-game-thumb.png", b"png")
        gm.stamp(archive, {"name": "G"}, thumb=shot)
        with zipfile.ZipFile(archive) as z:
            self.assertEqual(sorted(z.namelist()), ["Game/Game.bat", "Game/redengine-game-thumb.jpg", "Game/redengine-game.json"])

    def test_a_card_member_is_a_plain_file_and_a_comment_that_is_not_a_card_is_said_to_go(self):
        archive = self.tmp / "g.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("Game.bat", "x")
            z.comment = b"Made with love, in 2026."
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            gm.stamp(archive, {"name": "G"})
        self.assertIn("comment is replaced", err.getvalue())
        with zipfile.ZipFile(archive) as z:
            info = z.getinfo("redengine-game.json")
            self.assertEqual(stat.S_IFMT(info.external_attr >> 16), stat.S_IFREG, "a file of its own kind, not a mode with no kind")
            self.assertEqual(stat.S_IMODE(info.external_attr >> 16), 0o644)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            gm.stamp(archive, {"author": "ai"})
        self.assertEqual(err.getvalue(), "", "a card's own comment is replaced without a word")

    def test_a_value_that_starts_with_dashes_goes_with_args_and_notes(self):
        root = self.folder({"Game.bat": "x"})
        code, out, err = run("stamp", root, "--name", "G", "--args", "--fullscreen", "--args", "-w", "--notes", "- one", "--args=--x=1")
        self.assertEqual(code, 0, err)
        self.assertEqual(gm.read(root)["card"], {"name": "G", "args": ["--fullscreen", "-w", "--x=1"], "notes": ["- one"]})
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run("stamp", root, "--args", "--name", "X")  # an option of the tool is still an option
        self.assertEqual(gm.glue_dashed(["stamp", "--args", "-x", "--thumb", "a.png", "--notes"], [], "--args", "--notes"), ["stamp", "--args=-x", "--thumb", "a.png", "--notes"])


class Links(Scratch):
    """Nothing the game's folder points at outside itself is read."""

    def link(self, target: Path, at: Path) -> None:
        at.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(target, at)
        except (OSError, NotImplementedError):
            self.skipTest("this machine does not allow symbolic links")

    def test_a_card_file_that_is_a_link_is_not_read(self):
        outside = self.tmp / "outside.json"
        outside.write_text('{"name": "Outside"}')
        root = self.folder({"Game.bat": "@echo off\n", "other.txt": "x"})
        self.link(outside, root / gm.CARD_FILE)
        self.assertEqual(gm.read(root)["card"], {})

    def test_an_entry_or_a_thumb_that_is_a_link_or_goes_through_one_is_not_found(self):
        outside = self.folder({"Game.exe": b"MZ", "shot.png": b"png"})
        root = self.folder({"redengine-game.json": json.dumps({"name": "G", "entry": "link.exe", "thumb": "dir/shot.png"}), "Real.exe": b"MZ"})
        self.link(outside / "Game.exe", root / "link.exe")
        self.link(outside, root / "dir")
        self.assertEqual(gm.read(root)["card"], {"name": "G"})

    def test_what_a_stamp_writes_first_is_never_written_through_a_link(self):
        victim = self.tmp / "victim.txt"
        victim.write_text("PRECIOUS")
        build = builder()
        archive = self.tmp / "g.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("Game.bat", "@echo off\n")
        files = {"Game.exe": (build.pe(), None), "Quest.bat": (b"@echo off\n", None), "g.zip": (archive.read_bytes(), None)}
        for name, (data, _) in files.items():
            target = self.folder({name: data}) / name
            self.link(victim, target.with_name(name + ".stamping"))
            gm.stamp(target, {"name": "Stamped"})
            self.assertEqual(victim.read_text(), "PRECIOUS", name)
            self.assertEqual(gm.read(target)["card"], {"name": "Stamped"}, name)
            self.assertEqual([p.name for p in target.parent.iterdir()], [name], f"{name}: the planted link is gone, not followed")
        root = self.folder({"Game.exe": b"MZ"})
        self.link(victim, root / (gm.CARD_FILE + ".stamping"))
        self.link(victim, root / (gm.THUMB_STEM + ".png.stamping"))
        shot = self.tmp / "shot.png"
        shot.write_bytes(b"png")
        gm.stamp(root, {"name": "Stamped"}, thumb=shot)
        self.assertEqual((victim.read_text(), gm.read(root)["card"]), ("PRECIOUS", {"name": "Stamped", "thumb": "redengine-game-thumb.png"}))

    def test_a_script_that_is_a_link_is_not_a_candidate(self):
        outside = self.tmp / "outside.bat"
        outside.write_text("REM redengine-game\nREM name: Outside\n")
        root = self.folder({"readme.txt": "x"})
        self.link(outside, root / "Game.bat")
        self.assertEqual(gm.read(root)["card"], {})

    def test_a_folder_holding_one_link_is_not_entered(self):
        outside = self.folder({"redengine-game.json": '{"name": "Outside"}', "Game.bat": "x"})
        root = self.folder({})
        self.link(outside, root / "inner")
        self.assertEqual(gm.read(root)["card"], {})


class Files(Scratch):
    def test_limits_of_a_card_file_and_a_thumb_and_engine_name(self):
        root = self.folder({"redengine-game.json": json.dumps({"name": "G", "thumb": "big.png"}), "Game.exe": b"MZ", "big.png": b"\0" * (5 * 1024 * 1024)})
        self.assertEqual(gm.read(root)["card"], {"name": "G", "thumb": "big.png"})
        (root / "big.png").write_bytes(b"\0" * (5 * 1024 * 1024 + 1))
        self.assertEqual(gm.read(root)["card"], {"name": "G"}, "a screenshot of more than 5 MB is not found")
        (root / "A.bat").write_bytes(b"REM redengine-game\nREM name: Run\n")
        (root / "engine.name").write_bytes(b"A.bat" + b" " * 2000)
        self.assertEqual(gm.read(root)["card"], {"name": "G"}, "an engine.name of more than a kilobyte is not read")

    def test_a_name_counts_only_in_the_case_it_is_written_on_a_disk_that_ignores_case(self):
        # A Windows disk answers for `Quest.BAT` with `Quest.bat`; a ZIP read in place does not. Every reader finds the same files: names as written.
        root = self.folder({"Quest.bat": "@echo off\n", "bin/Game.exe": b"MZ", "shot.png": b"png", gm.CARD_FILE: "{}"})
        real = os.lstat

        def any_case(path, *args, **kwargs):  # what a disk that ignores case answers
            path = Path(path)
            with os.scandir(path.parent) as it:
                same = next((e.name for e in it if e.name.lower() == path.name.lower()), path.name)
            return real(path.parent / same, *args, **kwargs)

        with mock.patch.object(gm.os, "lstat", any_case):
            game = gm._Dir(root)
            self.assertTrue(game.is_file("Quest.bat") and game.is_file("bin/Game.exe") and game.is_file("shot.png"))
            for rel in ("Quest.BAT", "quest.bat", "BIN/Game.exe", "bin/game.exe", "Shot.png"):
                self.assertFalse(game.is_file(rel), rel)
            (root / gm.CARD_FILE).write_text(json.dumps({"entry": "QUEST.bat", "thumb": "SHOT.PNG", "name": "Case"}))
            self.assertEqual(gm.read(root)["card"], {"name": "Case"})

    def test_the_path_must_be_a_game(self):
        with self.assertRaises(SystemExit):
            gm.read(self.tmp / "nowhere")
        (self.tmp / "notes.txt").write_text("x")
        with self.assertRaises(SystemExit):
            gm.read(self.tmp / "notes.txt")
        (self.tmp / "broken.zip").write_bytes(b"PK\x03\x04 not really")
        self.assertEqual(gm.read(self.tmp / "broken.zip"), {"card": {}, "from": {}})
        (self.tmp / "empty").mkdir()
        self.assertEqual(gm.read(self.tmp / "empty"), {"card": {}, "from": {}})

    def test_names_that_look_like_other_names_do_not_confuse_candidates(self):
        root = self.folder({"A.bat": "REM redengine-game\nREM name: Run\n", "unins000.bat": "REM redengine-game\nREM name: Un\n", "Vcredist_x64.exe": b"MZ", "b.txt": "x"})
        self.assertEqual(gm.read(root)["card"], {"name": "Run"})


class Stamping(Scratch):
    def test_a_folder_gets_the_card_file_and_keeps_what_it_had(self):
        root = self.folder({"Game.bat": "@echo off\n", "shots/one.png": b"png"})
        card = gm.stamp(root, {"name": "Star Miner", "description": "Mine rocks.", "kind": "2d"})
        self.assertEqual(card, {"name": "Star Miner", "description": "Mine rocks.", "presentation": "2d"})
        text = (root / gm.CARD_FILE).read_text(encoding="utf-8")
        self.assertEqual(json.loads(text), {"schema": 1, **card})
        self.assertTrue(text.startswith('{\n  "schema": 1,\n') and text.endswith("}\n"))
        gm.stamp(root, {"author": "ai", "entry": "Game.bat", "args": ["--fast"], "notes": ["N"], "forked_from": {"slug": "snake", "version": 2}})
        self.assertEqual(gm.read(root)["card"], {"name": "Star Miner", "description": "Mine rocks.", "presentation": "2d", "author": "ai", "entry": "Game.bat",
                                                 "args": ["--fast"], "notes": ["N"], "forked_from": {"slug": "snake", "version": 2}})
        gm.stamp(root, {"description": "", "args": [], "name": "Star Miner II"})
        self.assertEqual(gm.read(root)["card"]["name"], "Star Miner II")
        self.assertNotIn("description", gm.read(root)["card"])
        self.assertNotIn("args", gm.read(root)["card"])
        self.assertEqual((root / "Game.bat").read_text(), "@echo off\n")

    def test_a_folder_holding_one_folder_gets_the_card_inside_it(self):
        root = self.folder({"Star Miner/Game.bat": "@echo off\n"})
        gm.stamp(root, {"name": "Star Miner"})
        self.assertTrue((root / "Star Miner" / gm.CARD_FILE).is_file())
        self.assertFalse((root / gm.CARD_FILE).exists())
        self.assertEqual(gm.read(root)["card"], {"name": "Star Miner"})

    def test_a_screenshot_goes_into_the_game_and_is_named_by_the_card(self):
        root = self.folder({"Game.bat": "x"})
        shot = self.tmp / "shot.JPEG"
        shot.write_bytes(b"jpeg")
        gm.stamp(root, {"name": "G"}, thumb=shot)
        self.assertEqual((root / "redengine-game-thumb.jpg").read_bytes(), b"jpeg")
        self.assertEqual(gm.read(root)["card"], {"name": "G", "thumb": "redengine-game-thumb.jpg"})
        with self.assertRaises(SystemExit):
            gm.stamp(root, {"name": "G"}, thumb=self.tmp / "missing.png")
        (self.tmp / "x.gif").write_bytes(b"gif")
        with self.assertRaises(SystemExit):
            gm.stamp(root, {"name": "G"}, thumb=self.tmp / "x.gif")

    def test_a_screenshot_is_never_written_through_a_link(self):
        root = self.folder({"Game.bat": "x"})
        victim = self.tmp / "victim.png"
        victim.write_bytes(b"precious")
        try:
            os.symlink(victim, root / "redengine-game-thumb.png")
            os.symlink(victim, root / gm.CARD_FILE)
        except (OSError, NotImplementedError):
            self.skipTest("this machine does not allow symbolic links")
        shot = self.tmp / "shot.png"
        shot.write_bytes(b"png")
        gm.stamp(root, {"name": "G"}, thumb=shot)
        self.assertEqual(victim.read_bytes(), b"precious")
        self.assertEqual((root / "redengine-game-thumb.png").read_bytes(), b"png")
        self.assertEqual(gm.read(root)["card"], {"name": "G", "thumb": "redengine-game-thumb.png"})

    def test_what_cannot_be_kept_is_an_error_not_a_silent_drop(self):
        root = self.folder({"Game.bat": "x", "readme.txt": "r"})
        for fields in ({"presentation": "4d"}, {"author": "robot"}, {"entry": "Missing.exe"}, {"entry": "readme.txt"}, {"entry": "../x.exe"}, {"thumb": "none.png"},
                       {"forked_from": {"slug": "Bad", "version": 1}}, {"bogus": "x"}, {"name": 5}):
            with self.assertRaises(SystemExit, msg=fields):
                gm.stamp(root, fields)
        self.assertFalse((root / gm.CARD_FILE).exists())

    def test_a_cut_is_said_aloud(self):
        root = self.folder({"Game.bat": "x"})
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            card = gm.stamp(root, {"name": "N" * 80})
        self.assertEqual(card["name"], "N" * 60)
        self.assertIn("name is cut to 60", err.getvalue())

    def test_a_zip_is_rewritten_with_the_card_file_and_comment(self):
        archive = self.tmp / "g.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("Star Miner/", b"")
            z.writestr("Star Miner/Game.bat", "@echo off\r\n", zipfile.ZIP_DEFLATED)
            z.writestr("Star Miner/data/a.pak", b"\1\2\3" * 1000, zipfile.ZIP_STORED)
            z.writestr("Star Miner/data/", b"")
            z.comment = b"an old comment"
        before = {i.filename: zipfile.ZipFile(archive).read(i) for i in zipfile.ZipFile(archive).infolist()}
        shot = self.tmp / "shot.png"
        shot.write_bytes(b"png")
        card = gm.stamp(archive, {"name": "Star Miner", "description": "Mine rocks."}, thumb=shot)
        self.assertEqual(card, {"name": "Star Miner", "description": "Mine rocks.", "thumb": "redengine-game-thumb.png"})
        with zipfile.ZipFile(archive) as z:
            self.assertIsNone(z.testzip())
            after = {i.filename: z.read(i) for i in z.infolist()}
            self.assertEqual(json.loads(after["Star Miner/redengine-game.json"]), {"schema": 1, **card})
            self.assertEqual(after["Star Miner/redengine-game-thumb.png"], b"png")
            self.assertEqual(z.comment, gm.card_comment(card))
            self.assertEqual({k: v for k, v in after.items() if not k.startswith("Star Miner/redengine-game")}, before)
            self.assertEqual([i.compress_type for i in z.infolist() if i.filename.endswith(("Game.bat", "a.pak"))], [zipfile.ZIP_DEFLATED, zipfile.ZIP_STORED])
        self.assertTrue(gm.card_comment(card).startswith(b"redengine-game {"))
        self.assertEqual(gm.read(archive), {"card": card, "from": {k: "card" for k in card}})
        gm.stamp(archive, {"author": "ai"})
        with zipfile.ZipFile(archive) as z:
            self.assertEqual(sum(1 for n in z.namelist() if n.endswith("redengine-game.json")), 1, "the card file is replaced, not added again")
        self.assertEqual(gm.read(archive)["card"], {**card, "author": "ai"})

    def test_a_zip_with_only_a_comment_keeps_it_as_a_starting_point(self):
        archive = self.copy("zip-comment-only.zip")
        gm.stamp(archive, {"author": "ai"})
        self.assertEqual(gm.read(archive)["card"], {"name": "Comment Quest", "description": "Only the ZIP comment says this.", "presentation": "hybrid", "author": "ai"})

    def test_a_zip_with_encrypted_members_is_refused_and_left_alone(self):
        data = bytearray((DATA / "zip-no-card.zip").read_bytes())
        for sig, at in ((b"PK\3\4", 6), (b"PK\1\2", 8)):
            for i in range(len(data)):
                if data[i:i + 4] == sig:
                    data[i + at] |= 1
        archive = self.tmp / "enc.zip"
        archive.write_bytes(bytes(data))
        with self.assertRaises(SystemExit) as e:
            gm.stamp(archive, {"name": "X"})
        self.assertIn("encrypted", str(e.exception))
        self.assertEqual(archive.read_bytes(), bytes(data))
        self.assertEqual([p.name for p in self.tmp.iterdir()], ["enc.zip"])

    def test_a_script_gets_a_header_block_and_every_line_it_had(self):
        for original in (b"@echo off\r\necho hi\r\npause\r\n", b"@echo off\necho hi\n", b"echo hi", b"", b"\xef\xbb\xbf@echo off\r\necho hi\r\n", b"@echo off\r\n\r\n:loop\r\ngoto loop\r\n",
                         b"  @ECHO OFF  \r\necho hi", b"setlocal\r\n@echo off\r\n"):
            script = self.tmp / "q.bat"
            script.write_bytes(original)
            gm.stamp(script, {"name": "Text Quest", "description": "A tiny text adventure.", "kind": "2d", "author": "ai", "notes": ["First release."], "args": ["--x"]})
            data = script.read_bytes()
            block = (b"@REM redengine-game\r\n@REM name: Text Quest\r\n@REM description: A tiny text adventure.\r\n@REM presentation: 2d\r\n@REM author: ai\r\n"
                     b"@REM args: --x\r\n@REM notes: First release.\r\n")
            self.assertEqual(data.count(block), 1, data)
            self.assertEqual(data.startswith(b"\xef\xbb\xbf"), original.startswith(b"\xef\xbb\xbf"))
            self.assertEqual(data.replace(block, b"", 1), original, "every line the script had is still there, in order")
            self.assertEqual(gm.read(script)["card"], {"name": "Text Quest", "description": "A tiny text adventure.", "presentation": "2d", "author": "ai",
                                                       "args": ["--x"], "notes": ["First release."]})

    def test_the_block_goes_after_echo_off_when_a_script_starts_with_it(self):
        script = self.tmp / "q.bat"
        script.write_bytes(b"@echo off\r\necho hi\r\n")
        gm.stamp(script, {"name": "Q"})
        self.assertEqual(script.read_bytes(), b"@echo off\r\n@REM redengine-game\r\n@REM name: Q\r\necho hi\r\n")
        script.write_bytes(b"@echo off")
        gm.stamp(script, {"name": "Q"})
        self.assertEqual(script.read_bytes(), b"@echo off\n@REM redengine-game\r\n@REM name: Q\r\n", "a script with no line end gets one, not a stray carriage return")
        self.assertEqual(gm.read(script)["card"], {"name": "Q"})

    def test_stamping_a_script_again_replaces_its_block_and_nothing_else(self):
        script = self.copy("header-rem-crlf.bat", "again.bat")
        original = script.read_bytes()
        gm.stamp(script, {"name": "New Name", "online": ""})
        data = script.read_bytes()
        self.assertEqual(data.count(b"redengine-game"), 1)
        found = gm.read(script)["card"]
        self.assertEqual(found["name"], "New Name")
        self.assertNotIn("online", found)
        self.assertEqual(found["description"], "A tiny text adventure about a lost key.")
        self.assertEqual(found["notes"], ["First release.", "Added a second key."])
        kept = [x for x in original.split(b"\r\n") if not x.startswith(b"REM ") and x != b"REM redengine-game"]
        self.assertEqual([x for x in data.split(b"\r\n") if not x.startswith(b"@REM ")], kept, "the lines that are not the block are the same lines")
        self.assertTrue(data.startswith(b"@echo off\r\n@REM redengine-game\r\n"))
        self.assertTrue(all(x.endswith(b"\r") for x in data.split(b"\n")[:-1]), "the block is written with CRLF")

    def test_a_header_never_holds_what_cmd_would_read_as_a_command(self):
        script = self.tmp / "q.bat"
        script.write_bytes(b"@echo off\r\n")
        for c in "^%&|<>":
            with self.assertRaises(SystemExit, msg=c) as e:
                gm.stamp(script, {"description": f"fish {c} chips"})
            self.assertIn(c, str(e.exception))
            self.assertEqual(script.read_bytes(), b"@echo off\r\n")
        gm.stamp(script, {"description": "Rock, paper (and scissors): 100 per cent! It's \"fun\"; really."})
        self.assertIn("100 per cent", gm.read(script)["card"]["description"])

    def test_a_script_that_is_not_plain_text_is_left_alone(self):
        for data in ("@echo off\r\necho hi\r\n".encode("utf-16"), b"\xfe\xff\0@\0e", b"@echo off\r\n\0\0\0"):
            script = self.tmp / "u.bat"
            script.write_bytes(data)
            with self.assertRaises(SystemExit) as e:
                gm.stamp(script, {"name": "U"})
            self.assertIn("plain-text", str(e.exception))
            self.assertEqual(script.read_bytes(), data)

    def test_a_script_header_has_no_room_for_a_screenshot_or_a_family(self):
        script = self.tmp / "q.bat"
        script.write_bytes(b"@echo off\r\n")
        with self.assertRaises(SystemExit):
            gm.stamp(script, {"name": "Q"}, thumb=self.tmp / "x.png")
        with self.assertRaises(SystemExit):
            gm.stamp(script, {"name": "Q", "forked_from": {"slug": "snake", "version": 1}})
        self.assertEqual(script.read_bytes(), b"@echo off\r\n")

    def test_a_program_gets_a_record_after_its_last_byte(self):
        original = (DATA / "plain.exe").read_bytes()
        program = self.copy("plain.exe")
        gm.stamp(program, {"name": "Star Miner", "description": "Mine rocks."})
        data = program.read_bytes()
        self.assertTrue(data.startswith(original), "not one byte of the program changed")
        tail = data[len(original):]
        self.assertTrue(tail.endswith(gm.MAGIC))
        (length,) = struct.unpack("<I", tail[-12:-8])
        self.assertEqual(len(tail), length + 12)
        self.assertEqual(json.loads(tail[:length]), {"schema": 1, "name": "Star Miner", "description": "Mine rocks."})
        self.assertEqual(gm.read(program)["card"], {"name": "Star Miner", "description": "Mine rocks."})
        gm.stamp(program, {"author": "ai", "name": "Star Miner 2"})
        again = program.read_bytes()
        self.assertTrue(again.startswith(original))
        self.assertEqual(gm.read(program)["card"], {"name": "Star Miner 2", "description": "Mine rocks.", "author": "ai"})
        self.assertEqual(again.count(gm.MAGIC), 1, "it replaces its own record")

    def test_a_stamped_program_is_still_a_program_with_the_same_resources(self):
        program = self.copy("versioned.exe")
        gm.stamp(program, {"name": "Record Wins"})
        with gm._Disk(program) as f:
            pe = gm._pe(f)
            self.assertEqual(pe["end"], len((DATA / "versioned.exe").read_bytes()))
            self.assertEqual(gm._program(f), {"name": "Version Quest", "description": "A game that only has version information."})
        found = gm.read(program)
        self.assertEqual(found["card"], {"name": "Record Wins", "description": "A game that only has version information."})
        self.assertEqual(found["from"], {"name": "exe", "description": "program"})

    def test_a_program_keeps_its_permissions(self):
        program = self.copy("plain.exe")
        program.chmod(0o751)
        gm.stamp(program, {"name": "X"})
        if os.name == "posix":
            self.assertEqual(program.stat().st_mode & 0o777, 0o751)

    def test_the_refusals_say_why(self):
        reasons = {"overlay.exe": "after its last section", "signed.exe": "is signed", "tiny.exe": "not a Windows program", "not-a-program.exe": "not a Windows program",
                   "truncated.exe": "cut short", "lying-record-length.exe": "after its last section", "overlay-with-record.exe": "after its last section"}
        for name, reason in reasons.items():
            program = self.copy(name)
            with self.assertRaises(SystemExit) as e:
                gm.stamp(program, {"name": "X"})
            self.assertIn(reason, str(e.exception), name)
        with self.assertRaises(SystemExit):
            gm.stamp(self.tmp / "missing.exe", {"name": "X"})
        with self.assertRaises(SystemExit):
            gm.stamp(self.tmp / "overlay.exe", {"thumb": "x"}, thumb=self.tmp / "x.png")
        (self.tmp / "x.txt").write_text("x")
        with self.assertRaises(SystemExit):
            gm.stamp(self.tmp / "x.txt", {"name": "X"})


class CommandLine(Scratch):
    def test_show(self):
        code, out, _ = run("show", DATA / "zip-card-and-comment.zip")
        self.assertEqual(code, 0)
        self.assertIn("File Name   (card file)", out)
        self.assertIn("From the comment.   (ZIP comment)", out)
        code, out, _ = run("show", DATA / "folder-no-card", "--json")
        self.assertEqual(json.loads(out), {"card": {}, "from": {}})
        code, out, _ = run("show", DATA / "both.exe", "--json")
        self.assertEqual(json.loads(out), EXPECTED["fixtures"]["both.exe"])
        self.assertIn("says nothing about itself", run("show", DATA / "plain.exe")[1])
        with self.assertRaises(SystemExit):
            run("show", self.tmp / "nowhere")

    def test_the_stamp_examples_of_the_spec(self):
        bat = self.tmp / "Quest.bat"
        bat.write_bytes(b"@echo off\r\necho Welcome...\r\n")
        code, out, _ = run("stamp", bat, "--name", "Text Quest", "--description", "A tiny text adventure.", "--kind", "2d", "--author", "ai")
        self.assertEqual(code, 0)
        self.assertIn("stamped", out)
        self.assertEqual(gm.read(bat)["card"], {"name": "Text Quest", "description": "A tiny text adventure.", "presentation": "2d", "author": "ai"})
        exe = self.copy("plain.exe", "Game.exe")
        run("stamp", exe, "--name", "Star Miner", "--description", "Mine asteroids, dodge pirates.")
        self.assertEqual(gm.read(exe)["card"], {"name": "Star Miner", "description": "Mine asteroids, dodge pirates."})
        archive = self.copy("zip-no-card.zip", "Game.zip")
        shot = self.tmp / "shot.png"
        shot.write_bytes(b"png")
        run("stamp", archive, "--name", "Star Miner", "--thumb", shot)
        self.assertEqual(gm.read(archive)["card"], {"name": "Star Miner", "thumb": "redengine-game-thumb.png"})
        root = self.folder({"Game.exe": b"MZ"})
        run("stamp", root, "--name", "Star Miner", "--args=--fast", "--args", "x y", "--notes", "One", "--forked-from", "snake@v3", "--presentation", "hybrid", "--entry", "Game.exe", "--online", "LAN")
        self.assertEqual(gm.read(root)["card"], {"name": "Star Miner", "presentation": "hybrid", "online": "LAN", "entry": "Game.exe", "args": ["--fast", "x y"], "notes": ["One"],
                                                 "forked_from": {"slug": "snake", "version": 3}})

    def test_it_runs_as_a_script_from_anywhere(self):
        script = str(Path(gm.__file__))
        done = subprocess.run([sys.executable, "-B", script, "show", str(DATA / "zip-comment-only.zip"), "--json"], capture_output=True, text=True, cwd=self.tmp)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout), EXPECTED["fixtures"]["zip-comment-only.zip"])
        done = subprocess.run([sys.executable, "-B", script, "stamp", str(self.copy("overlay.exe")), "--name", "X"], capture_output=True, text=True, cwd=self.tmp)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("after its last section", done.stderr)

    def test_stamp_needs_something_to_say_and_a_game(self):
        with self.assertRaises(SystemExit) as e:
            run("stamp", self.copy("plain.exe"))
        self.assertIn("nothing to stamp", str(e.exception))
        with self.assertRaises(SystemExit):
            run("stamp", self.tmp / "nowhere.exe", "--name", "X")
        with self.assertRaises(SystemExit):
            run("stamp", self.copy("overlay.exe"), "--name", "X")
        with self.assertRaises(SystemExit):
            run("stamp", self.copy("plain.exe"), "--forked-from", "Bad Slug@1")


if __name__ == "__main__":
    unittest.main()
