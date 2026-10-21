#!/usr/bin/env python3
"""Generates the shared conformance data of the game card (docs/GAME_METADATA.md): small games of every kind, hostile ones, and `expected.json`, which says
what a reader must find in each. Both readers, `distribution/game_meta.py` and `launcher/core/src/meta.rs`, are tested against these files.

Everything here is made from constants and nothing else (no toolchain, no clock, no compressor), so every run writes the same bytes; the tests fail when
the files in this folder are not what this script writes. The case table is the oracle: `expected.json` is written from what is typed below, never from
what a reader answered.

  python3 distribution/testdata/game_meta/build_fixtures.py        rewrites this folder (everything but this script)
  python3 distribution/testdata/game_meta/build_fixtures.py DIR    writes them into DIR instead: a new or empty folder, or one it wrote before

`expected.json`: {"fixtures": {path: {"card": {field: value}, "from": {field: source}}}, "stamp_refused": [paths]}. A path is a folder, a .zip or a single
file, relative to this folder; `stamp_refused` lists the programs `game_meta.py stamp` must refuse to change.
"""

import base64
import json
import shutil
import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
MAGIC = b"REDGAME1"
PACKED = base64.b64decode("QlpoMTFBWSZTWQyrrq8AAAjbgAAQUAAAEEAALgsACiAAIobUeo0fqEAAAXUS7cJYCZihdyRThQkAyrrq8A==")  # bzip2 of PACKED_CARD
PACKED_CARD = b'{"name": "Packed"}\n'


# ---- bytes -------------------------------------------------------------------------------------------------------------------------------


def j(obj) -> bytes:
    return (json.dumps(obj, indent=2) + "\n").encode("utf-8")


def compact(obj) -> bytes:
    return json.dumps(obj, separators=(",", ":")).encode("utf-8")


def pad(data: bytes, n: int) -> bytes:
    return data + b"\0" * (-len(data) % n)


def bat(lines: list[str], eol: bytes = b"\r\n", bom: bool = False) -> bytes:
    return (b"\xef\xbb\xbf" if bom else b"") + b"".join(line.encode("utf-8") + eol for line in lines)


def record(card: dict | bytes, length: int | None = None) -> bytes:
    """What follows a program's last byte: the card, its length (`length` lies when given), the magic."""
    body = card if isinstance(card, bytes) else compact(card)
    return body + struct.pack("<I", len(body) if length is None else length) + MAGIC


def deflate_stored(data: bytes) -> bytes:
    """A valid deflate stream that stores `data` in blocks: the same bytes on every machine, whatever zlib is there."""
    out, at = b"", 0
    while True:
        chunk, at = data[at:at + 65535], at + 65535
        out += bytes([at >= len(data)]) + struct.pack("<HH", len(chunk), len(chunk) ^ 0xFFFF) + chunk
        if at >= len(data):
            return out


def zip_bytes(members: list[tuple], comment: bytes = b"") -> bytes:
    """A ZIP of (name, data, method[, unix mode]) members; method is "stored", "deflated" (stored blocks) or "bzip2" (`data` is then (the bytes, their
    bzip2 stream)); a name ending in `/` is a folder."""
    out, central = bytearray(), bytearray()
    for name, data, method, *mode in members:
        raw = name.encode("utf-8")
        data, body = data if method == "bzip2" else (data, deflate_stored(data) if method == "deflated" else data)
        code, crc, at = {"stored": 0, "deflated": 8, "bzip2": 12}[method], zlib.crc32(data), len(out)
        out += struct.pack("<4sHHHHHIIIHH", b"PK\3\4", 20, 0, code, 0, 0x21, crc, len(body), len(data), len(raw), 0) + raw + body
        attr = (0o40755 << 16 | 0x10) if name.endswith("/") else ((mode[0] if mode else 0o100644) << 16)
        central += struct.pack("<4sHHHHHHIIIHHHHHII", b"PK\1\2", 0x031E, 20, 0, code, 0, 0x21, crc, len(body), len(data), len(raw), 0, 0, 0, 0, attr, at) + raw
    end = struct.pack("<4sHHHHIIH", b"PK\5\6", 0, 0, len(members), len(members), len(central), len(out), len(comment))
    return bytes(out) + bytes(central) + end + comment


# ---- a Windows program -------------------------------------------------------------------------------------------------------------------


def vs_node(key: str, value: bytes = b"", kind: int = 1, kids: tuple | list = (), vlen: int | None = None) -> bytes:
    """One node of a version resource: lengths, type, key, value, children (each padded to four bytes)."""
    count = vlen if vlen is not None else len(value) // 2 if kind == 1 else len(value)
    body = pad(struct.pack("<HHH", 0, count, kind) + key.encode("utf-16-le") + b"\0\0", 4) + value
    if kids:
        body = pad(body, 4) + b"".join(pad(k, 4) for k in kids)
    return struct.pack("<H", len(body)) + body[2:]


def version_info(*tables: list[tuple[str, str]], short: str = "") -> bytes:
    """A `VS_VERSION_INFO` with a string table for each list of (name, value) given; the node called `short` says it is one byte shorter than it is."""
    fixed = struct.pack("<13I", 0xFEEF04BD, 0x10000, 0x10000, 0, 0x10000, 0, 0x3F, 0, 4, 1, 0, 0, 0)

    def string(k: str, v: str) -> bytes:
        node = vs_node(k, v.encode("utf-16-le") + b"\0\0")
        return struct.pack("<H", len(node) - 1) + node[2:] if k == short else node
    strings = [vs_node(f"0409{0x4B0 + i:04x}", kids=[string(k, v) for k, v in t]) for i, t in enumerate(tables)]
    var = vs_node("VarFileInfo", kids=[vs_node("Translation", struct.pack("<HH", 0x409, 0x4B0), kind=0, vlen=4)])
    return vs_node("VS_VERSION_INFO", fixed, kind=0, kids=[vs_node("StringFileInfo", kids=strings), var])


def resources(blob: bytes, rva: int | None = None, size: int | None = None, loop: bool = False) -> bytes:
    """The resource section: type 16 -> name 1 -> language 0x409 -> the blob (`rva`, `size` and `loop` make it lie)."""
    def directory(entry: tuple[int, int]) -> bytes:
        return struct.pack("<IIHHHH", 0, 0, 0, 0, 0, 1) + struct.pack("<II", *entry)
    start = 0x2000 + 0x58
    return (directory((16, 0x80000000 | (0 if loop else 0x18))) + directory((1, 0x80000030)) + directory((0x409, 0x48))
            + struct.pack("<IIII", start if rva is None else rva, len(blob) if size is None else size, 0x4B0, 0) + blob)


SUBDIR = 0x80000000


def directory(entries: list[tuple[int, int]], named: int = 0, counts: tuple[int, int] | None = None) -> bytes:
    """A resource directory: `named` of the entries come first and are named; `counts` (named, ids) lies about how many there are."""
    n, ids = counts if counts else (named, len(entries) - named)
    return struct.pack("<IIHHHH", 0, 0, 0, 0, n, ids) + b"".join(struct.pack("<II", *e) for e in entries)


def tree(blob: bytes, *, named_types: int = 0, top: tuple[int, int] | None = None, names: tuple[int, int] | None = None, shape: str = "normal", size: int = 0) -> bytes:
    """The resource section made of `directory` calls: a top directory of `named_types` named entries, a picture type (3) and the version type (16), then
    a directory of names, one of languages, the data entry and `blob`, padded to `size` bytes. `top` and `names` lie about the counts of the first two
    directories. `shape` leaves out the languages ("no-language"), adds a directory ("extra-level"), has the version type lead straight to the data entry
    ("type-is-data") or leaves the flag that says "a directory below" off the entry for the version type or for the name."""
    below = {"normal": 2, "extra-level": 3, "no-language": 1, "type-is-data": 0, "type-flag-missing": 2, "name-flag-missing": 2}[shape]  # directories under the top
    head = 16 + 8 * (named_types + 2)
    entries = [(0x80000000 | 8 * k, SUBDIR | head) for k in range(named_types)]
    entries += [(3, SUBDIR | head), (16, (SUBDIR if below and shape != "type-flag-missing" else 0) | head)]
    lower = b"".join(
        directory([(1 if k == 0 else 0x409, (SUBDIR if k + 1 < below and (k, shape) != (0, "name-flag-missing") else 0) | head + 24 * (k + 1))], counts=names if k == 0 else None)
        for k in range(below))
    data = struct.pack("<IIII", 0x2000 + head + 24 * below + 16, len(blob), 0x4B0, 0)
    return (directory(entries, named_types, top) + lower + data + blob).ljust(size, b"\0")


def symbol_table(count: int = 3) -> bytes:
    """What gcc and mingw leave after the last section of a program they did not strip: `count` symbols of 18 bytes, then the string table (its length first)."""
    strings = b"".join(b"_symbol_with_a_long_name_%d\0" % i for i in range(count))
    return b"".join(struct.pack("<8sIHHBB", b"_sym%d" % i, 0, 1, 0, 2, 0) for i in range(count)) + struct.pack("<I", 4 + len(strings)) + strings


def pe(rsrc: bytes | None = None, *, plus: bool = True, tail: bytes = b"", cert: bool = False, symbols: tuple[int, bytes] | None = None, before_cert: bytes = b"") -> bytes:
    """A small Windows program image: DOS and PE headers, a `.text` section and, with `rsrc`, a `.rsrc` section; then `symbols` ((count, bytes) of a symbol
    table and its strings, which the COFF header points to), `before_cert` (what was appended before it was signed), a certificate table that the headers
    point to (with `cert`, or with `before_cert`) and `tail` (data after all of it)."""
    sections = [(b".text", pad(b"\x31\xc0\xc3", 0x200), 3, 0x1000, 0x60000020)]  # xor eax, eax; ret
    if rsrc is not None:
        sections.append((b".rsrc", pad(rsrc, 0x200), len(rsrc), 0x2000, 0x40000040))
    lfanew, opt_size = 0x80, 240 if plus else 224
    offset = 0x200
    table = b""
    for name, raw, vsize, va, flags in sections:
        table += struct.pack("<8sIIIIIIHHI", name, vsize, va, len(raw), offset, 0, 0, 0, 0, flags)
        offset += len(raw)
    certificate = struct.pack("<IHH", 24, 0x200, 2) + b"\x01" * 16 if cert or before_cert else b""
    count_syms, symbol_bytes = symbols or (0, b"")
    middle = pad(symbol_bytes + before_cert, 8) if before_cert else symbol_bytes  # the certificate table starts on a multiple of 8 bytes
    dos = bytearray(lfanew)
    dos[0:2] = b"MZ"
    struct.pack_into("<I", dos, 60, lfanew)
    dos[64:64 + 40] = b"This program cannot be run in DOS mode.\r\n"[:40]
    o = bytearray(opt_size)
    struct.pack_into("<HBB", o, 0, 0x20B if plus else 0x10B, 14, 0)
    struct.pack_into("<IIII", o, 4, 0x200, len(sections[1][1]) if rsrc is not None else 0, 0, 0x1000)
    struct.pack_into("<I", o, 20, 0x1000)
    ndirs_at, dirs_at = (108, 112) if plus else (92, 96)
    if plus:
        struct.pack_into("<Q", o, 24, 0x140000000)
        struct.pack_into("<QQQQ", o, 72, 0x100000, 0x1000, 0x100000, 0x1000)
    else:
        struct.pack_into("<II", o, 24, 0x2000, 0x400000)
        struct.pack_into("<IIII", o, 72, 0x100000, 0x1000, 0x100000, 0x1000)
    struct.pack_into("<II", o, 32, 0x1000, 0x200)
    struct.pack_into("<HHHHHH", o, 40, 6, 0, 0, 0, 6, 0)
    struct.pack_into("<II", o, 56, 0x1000 + sum((len(s[1]) + 0xFFF) & ~0xFFF for s in sections), 0x200)
    struct.pack_into("<HH", o, 68, 3, 0)
    struct.pack_into("<I", o, ndirs_at, 16)
    if rsrc is not None:
        struct.pack_into("<II", o, dirs_at + 16, 0x2000, len(rsrc))
    if certificate:
        struct.pack_into("<II", o, dirs_at + 32, offset + len(middle), len(certificate))
    coff = b"PE\0\0" + struct.pack("<HHIIIHH", 0x8664 if plus else 0x14C, len(sections), 0, offset if symbols else 0, count_syms, opt_size, 0x22 if plus else 0x102)
    return pad(bytes(dos) + coff + bytes(o) + table, 0x200) + b"".join(s[1] for s in sections) + middle + certificate + tail


def patched(data: bytes, at: int, value: bytes) -> bytes:
    return data[:at] + value + data[at + len(value):]


def aligned_card(name: str, aligned: bool) -> dict:
    """A card whose record is (`aligned`) or is not a whole number of 8-byte units, so that a certificate table after it does or does not need padding."""
    for k in range(16):
        card = {"name": name + "x" * k}
        if ((len(compact(card)) + 12) % 8 == 0) == aligned:
            return card
    raise AssertionError("unreachable")


def lfanew_inside_dos(data: bytes) -> bytes:
    """The PE header of `data` moved to offset 0x20, inside the DOS header's 64 bytes, with `e_lfanew` saying so."""
    out = bytearray(data)
    out[0x20:0x20 + 0x180] = data[0x80:0x80 + 0x180]
    struct.pack_into("<I", out, 60, 0x20)
    return bytes(out)


# ---- the cases ---------------------------------------------------------------------------------------------------------------------------


class Fixtures:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.expected: dict[str, dict] = {}
        self.refused: list[str] = []

    def says(self, path: str, card: dict | None, source: str = "card", by: dict | None = None) -> None:
        """What a reader must find at `path`: `card`, every field from `source` but those `by` names (field -> source)."""
        self.expected[path] = {"card": card or {}, "from": {k: (by or {}).get(k, source) for k in (card or {})}}

    def folder(self, path: str, tree: dict[str, bytes], card: dict | None = None, source: str = "card", by: dict | None = None, game: str = "") -> None:
        for rel, data in tree.items():
            self.files[f"{path}/{rel}"] = data
        self.says(f"{path}/{game}" if game else path, card, source, by)

    def single(self, path: str, data: bytes, card: dict | None = None, source: str = "card", by: dict | None = None, refused: bool = False) -> None:
        self.files[path] = data
        self.says(path, card, source, by)
        if refused:
            self.refused.append(path)

    def zipped(self, path: str, members: list[tuple], card: dict | None = None, source: str = "card", by: dict | None = None, comment: bytes = b"") -> None:
        self.files[path] = zip_bytes(members, comment)
        self.says(path, card, source, by)


FULL = {"schema": 1, "name": "Star Miner", "description": "Mine asteroids, dodge pirates.", "presentation": "3d", "author": "human",
        "online": "Up to four players on one LAN.", "entry": "Quest.bat", "args": ["--fast", "level 2"], "thumb": "media/shot.png",
        "notes": ["First release.", "Fixed the save bug."], "forked_from": {"slug": "snake", "version": 3}, "future_field": {"anything": [1, 2]}}
PLAIN_BAT = bat(["@echo off", "echo hi"])
EXAMPLE = ["@echo off", "REM redengine-game", "REM name: Text Quest", "REM description: A tiny text adventure about a lost key.",
           "REM presentation: 2d", "REM author: ai", "REM notes: First release.", "echo Welcome..."]
# A script or a program ships unchanged in every later build, so a reader never takes notes from one: they would be read as the next build's.
EXAMPLE_CARD = {"name": "Text Quest", "description": "A tiny text adventure about a lost key.", "presentation": "2d", "author": "ai"}
STAMPED = {"schema": 1, "name": "Stamped Quest", "description": "A game with a record in its program.", "presentation": "3d", "author": "ai",
           "notes": ["Built with the tool."]}
RUNTIME = [("CompanyName", "The NWJS Community"), ("FileDescription", "nwjs"), ("InternalName", "nw_exe"), ("OriginalFilename", "nw.exe"), ("ProductName", "nwjs")]
VERSION = [("Comments", "A game that only has version information."), ("CompanyName", "Nobody Ltd"), ("FileDescription", "Version Quest Launcher"),
           ("FileVersion", "1.0.0.0"), ("InternalName", "vq"), ("ProductName", "Version Quest"), ("ProductVersion", "1.0")]


def header(name: str, **more: str) -> bytes:
    return bat(["@echo off", "REM redengine-game", f"REM name: {name}", *[f"REM {k}: {v}" for k, v in more.items()], "echo running"])


def sized_card(size: int) -> bytes:
    """A card of exactly `size` bytes: a name and an unknown field that fills the rest."""
    head, end = b'{"name": "Exactly sixteen KiB", "pad": "', b'"}'
    return head + b"p" * (size - len(head) - len(end)) + end


def build() -> Fixtures:
    x = Fixtures()

    # -- folders: where the card is, and which source wins
    full = {k: v for k, v in FULL.items() if k not in ("schema", "future_field")}
    x.folder("folder-card", {"redengine-game.json": j(FULL), "Quest.bat": PLAIN_BAT, "media/shot.png": PNG}, full)
    x.folder("folder-card-bom", {"redengine-game.json": b"\xef\xbb\xbf" + j({"name": "With a byte order mark"}), "Game.exe": b"MZ"}, {"name": "With a byte order mark"})
    x.folder("folder-no-card", {"Game.exe": b"MZ", "readme.txt": b"hello"})
    x.folder("folder-bat-header", {"Quest.bat": bat(EXAMPLE), "story.txt": b"once"}, EXAMPLE_CARD, "bat")
    x.folder("folder-card-beats-bat", {"redengine-game.json": j({"name": "Card Name", "presentation": "2d"}),
                                       "Quest.bat": header("Bat Name", description="From the bat.", presentation="3d", author="ai")},
             {"name": "Card Name", "description": "From the bat.", "presentation": "2d", "author": "ai"}, "bat", {"name": "card", "presentation": "card"})
    two = {"A.bat": header("Alpha", description="Alpha's description."), "B.bat": header("Beta", description="Beta's description.", author="ai")}
    x.folder("folder-two-candidates", dict(two), {"name": "Alpha", "description": "Alpha's description.", "author": "ai"}, "bat")
    x.folder("folder-engine-name", {**two, "engine.name": b"B.bat\n"}, {"name": "Beta", "description": "Beta's description.", "author": "ai"}, "bat")
    x.folder("folder-card-entry", {**two, "redengine-game.json": j({"entry": "B.bat"})},
             {"entry": "B.bat", "name": "Beta", "description": "Beta's description.", "author": "ai"}, "bat", {"entry": "card"})
    x.folder("folder-engine-name-beats-entry", {**two, "redengine-game.json": j({"entry": "B.bat"}), "engine.name": b"A.bat\n"},
             {"entry": "B.bat", "name": "Alpha", "description": "Alpha's description."}, "bat", {"entry": "card"})
    x.folder("folder-nested-top", {"Star Miner/redengine-game.json": j({"name": "Star Miner"}), "Star Miner/Game.bat": PLAIN_BAT}, {"name": "Star Miner"})
    x.folder("folder-depth-two", {"bin/Game.bat": header("Deep Game"), "readme.txt": b"x"}, {"name": "Deep Game"}, "bat")
    exe = pe(tail=record(STAMPED))
    program = pe(resources(version_info(VERSION)))
    stamped = {k: v for k, v in STAMPED.items() if k not in ("schema", "notes")}  # a record's notes are not read
    x.folder("folder-stamped-exe", {"Game.exe": exe, "data/x.pak": b"x"}, stamped, "exe")
    x.folder("folder-version-info", {"Game.exe": program, "data/x.pak": b"x"},
             {"name": "Version Quest", "description": "A game that only has version information."}, "program")
    x.folder("folder-card-16k-exact", {"redengine-game.json": sized_card(16384), "Game.exe": b"MZ"}, {"name": "Exactly sixteen KiB"})
    x.folder("folder-card-16k-over", {"redengine-game.json": sized_card(16385), "Game.exe": b"MZ"})
    x.folder("folder-kind-synonym", {"redengine-game.json": j({"name": "Synonym", "kind": "hybrid"})}, {"name": "Synonym", "presentation": "hybrid"})

    # -- cleaning and limits
    x.folder("hostile-control-bidi", {"redengine-game.json": j({
        "name": "  Star\u202e\u0000 Miner\t\n ", "description": "Line one.\nLine\ttwo\u2066 \u00a0 \u3000end\u0007.\u0085Done\u001f", "online": "\u200bkeep zero width"})},
        {"name": "Star Miner", "description": "Line one. Line two end. Done", "online": "\u200bkeep zero width"})
    x.folder("hostile-long-fields", {"redengine-game.json": j({
        "name": "0123456789" * 10, "description": "d" * 500, "online": "o" * 300,
        "args": [f"arg{i:02d}" + "x" * 300 for i in range(20)], "notes": [f"note{i:02d}" + "y" * 300 for i in range(12)]})},
        {"name": "0123456789" * 6, "description": "d" * 400, "online": "o" * 200,
         "args": [(f"arg{i:02d}" + "x" * 300)[:200] for i in range(16)], "notes": [(f"note{i:02d}" + "y" * 300)[:200] for i in range(10)]})
    x.folder("hostile-wrong-types", {"redengine-game.json": j({
        "schema": "one", "name": 42, "description": "Only this survives.", "presentation": "4d", "author": "robot", "online": {"a": 1}, "entry": 7,
        "args": "--fast", "thumb": ["a.png"], "notes": [1, 2], "forked_from": "snake@3"})}, {"description": "Only this survives."})

    # -- hostile card text
    for name, text in (("hostile-bad-json", b'{"name": "Broken"'), ("hostile-json-array", b'[{"name": "Array"}]'),
                       ("hostile-deep-json", b'{"name": "Deep", "x": ' + b"[" * 5000 + b"]" * 5000 + b"}"), ("hostile-nan", b'{"name": "NaN", "x": NaN}'),
                       ("hostile-not-utf8", b'{"name": "Bad \xff byte"}'), ("hostile-lone-surrogate", b'{"name": "Lone \\ud800 surrogate"}')):
        x.folder(name, {"redengine-game.json": text, "Game.exe": b"MZ"})
    for name, fork in (("slug", {"slug": "snake--x", "version": 1}), ("version", {"slug": "snake", "version": 0}),
                       ("float", {"slug": "snake", "version": 3.5}), ("bool", {"slug": "snake", "version": True})):
        x.folder(f"hostile-forked-{name}", {"redengine-game.json": j({"name": "Fork", "forked_from": fork})}, {"name": "Fork"})

    # -- limits of the JSON itself: 127 levels (the card's own object is the first) and numbers that fit a 64-bit float; one more of either, the whole card is ignored
    def nested(levels: int) -> bytes:
        return b'{"name": "Nested", "deep": ' + b'{"a": ' * (levels - 1) + b"1" + b"}" * (levels - 1) + b"}"
    x.folder("folder-json-depth-127", {"redengine-game.json": nested(127), "Game.exe": b"MZ"}, {"name": "Nested"})
    x.folder("hostile-json-depth-128", {"redengine-game.json": nested(128), "Game.exe": b"MZ"})
    fits = b"[1.7976931348623157e308, -1.7976931348623157e308, 1e-999999, 1" + b"0" * 308 + b", -0, 18446744073709551616, 0.5e-3]"
    x.folder("folder-card-big-numbers", {"redengine-game.json": b'{"name": "Big numbers", "n": ' + fits + b"}", "Game.exe": b"MZ"}, {"name": "Big numbers"})
    for name, number in (("1e999999", b"1e999999"), ("minus-1e999999", b"-1e999999"), ("1.8e308", b"1.8e308"), ("310-digits", b"1" + b"0" * 309)):
        x.folder(f"hostile-number-{name}", {"redengine-game.json": b'{"name": "Huge", "n": ' + number + b"}", "Game.exe": b"MZ"})

    # -- hostile paths: the field is not found, the rest of the card is
    only = {"name": "Hostile"}
    base = {"Game.exe": b"MZ", "bin/Game.exe": b"MZ", "readme.txt": b"r", "media/shot.png": PNG, "bin.exe/inner.txt": b"x"}
    for name, entry in (("dotdot-inner", "bin/../Game.exe"), ("absolute", "/Game.exe"), ("drive-abs", "C:/Game.exe"), ("drive-rel", "C:Game.exe"),
                        ("backslash", "bin\\Game.exe"), ("not-runnable", "readme.txt"), ("missing", "Nope.exe"), ("directory", "bin.exe")):
        x.folder(f"hostile-entry-{name}", {**base, "redengine-game.json": j({"name": "Hostile", "entry": entry})}, only)
    for name, thumb in (("not-picture", "Game.exe"), ("absolute", "/media/shot.png"), ("backslash", "media\\shot.png"), ("missing", "media/none.png")):
        x.folder(f"hostile-thumb-{name}", {**base, "redengine-game.json": j({"name": "Hostile", "thumb": thumb})}, only)
    x.folder("hostile-entry-dotdot", {"game/redengine-game.json": j({"name": "Hostile", "entry": "../Outside.exe"}), "game/Game.exe": b"MZ", "Outside.exe": b"MZ"},
             only, game="game")
    x.folder("hostile-thumb-escape", {"game/redengine-game.json": j({"name": "Hostile", "thumb": "../shot.png"}), "game/Game.exe": b"MZ", "shot.png": PNG},
             only, game="game")
    x.folder("hostile-engine-name-escape", {"game/A.bat": header("Inside"), "game/engine.name": b"../Outside.bat\n", "Outside.bat": header("Outside")},
             {"name": "Inside"}, "bat", game="game")

    # -- ZIPs
    card = {"schema": 1, "name": "Star Miner", "description": "Mine asteroids, dodge pirates.", "entry": "StarMiner.exe", "thumb": "shots/one.png"}
    x.zipped("zip-top-folder.zip", [("Star Miner/", b"", "stored"), ("Star Miner/redengine-game.json", j(card), "stored"),
                                    ("Star Miner/StarMiner.exe", b"MZ", "stored"), ("Star Miner/unins000.exe", b"MZ", "stored"),
                                    ("Star Miner/shots/", b"", "stored"), ("Star Miner/shots/one.png", PNG, "stored")],
             {k: v for k, v in card.items() if k != "schema"})
    x.zipped("zip-comment-only.zip", [("Game.bat", PLAIN_BAT, "deflated"), ("readme.txt", b"r", "stored")],
             {"name": "Comment Quest", "description": "Only the ZIP comment says this.", "presentation": "hybrid"}, "zip",
             comment=b"redengine-game " + compact({"schema": 1, "name": "Comment Quest", "description": "Only the ZIP comment says this.", "presentation": "hybrid"}))
    x.zipped("zip-card-and-comment.zip", [("redengine-game.json", j({"name": "File Name", "presentation": "2d"}), "stored"), ("Game.bat", PLAIN_BAT, "stored")],
             {"name": "File Name", "description": "From the comment.", "presentation": "2d", "author": "ai"}, "zip", {"name": "card", "presentation": "card"},
             comment=b"redengine-game " + compact({"name": "Comment Name", "description": "From the comment.", "author": "ai", "presentation": "3d"}))
    x.zipped("zip-no-card.zip", [("Game.exe", b"MZ", "stored"), ("readme.txt", b"r", "stored")])
    x.zipped("zip-bat-header.zip", [("Quest.bat", bat(EXAMPLE), "deflated")], EXAMPLE_CARD, "bat")
    x.zipped("zip-stamped-exe.zip", [("Game.exe", exe, "deflated"), ("data/x.pak", b"x", "stored")], stamped, "exe")
    x.zipped("zip-versioned-exe.zip", [("Game.exe", program, "stored")], {"name": "Version Quest", "description": "A game that only has version information."}, "program")
    x.zipped("zip-comment-garbage.zip", [("Game.bat", PLAIN_BAT, "stored")], comment=b"redengine-game [1, 2]")
    x.zipped("zip-comment-over-16k.zip", [("Game.bat", PLAIN_BAT, "stored")], comment=b"redengine-game " + sized_card(16385))
    x.zipped("zip-unsafe-names.zip", [("../redengine-game.json", j({"name": "Evil"}), "stored"), ("/redengine-game.json", j({"name": "Evil"}), "stored"),
                                      ("Game.bat", PLAIN_BAT, "stored")])
    x.zipped("zip-nested-top.zip", [("Outer/", b"", "stored"), ("Outer/Inner/", b"", "stored"), ("Outer/Inner/redengine-game.json", j({"name": "Deep Down"}), "stored"),
                                    ("Outer/Inner/Game.bat", PLAIN_BAT, "stored")], {"name": "Deep Down"})
    x.zipped("zip-macosx.zip", [("__MACOSX/._Game.bat", b"x", "stored"), (".DS_Store", b"x", "stored"), ("Game/redengine-game.json", j({"name": "From a Mac"}), "stored"),
                                ("Game/Game.bat", PLAIN_BAT, "stored")], {"name": "From a Mac"})
    x.zipped("zip-engine-name.zip", [("A.bat", two["A.bat"], "stored"), ("B.bat", two["B.bat"], "deflated"), ("engine.name", b"B.bat\n", "stored")],
             {"name": "Beta", "description": "Beta's description.", "author": "ai"}, "bat")
    x.zipped("zip-two-top-items.zip", [("redengine-game.json", j({"name": "Root Card"}), "stored"), ("Game/Game.bat", header("Bat Name", description="Down one folder."), "stored")],
             {"name": "Root Card", "description": "Down one folder."}, "bat", {"name": "card"})
    x.zipped("zip-symlink-card.zip", [("redengine-game.json", b"elsewhere.json", "stored", 0o120777), ("Game.bat", PLAIN_BAT, "stored")])

    x.zipped("zip-backslash-names.zip", [("Star Miner\\redengine-game.json", j({"name": "Backslash Quest", "entry": "bin/Game.bat"}), "stored"),
                                         ("Star Miner\\bin\\Game.bat", PLAIN_BAT, "stored")], {"name": "Backslash Quest", "entry": "bin/Game.bat"})
    x.zipped("zip-backslash-unsafe.zip", [("..\\redengine-game.json", j({"name": "Evil"}), "stored"), ("sub\\..\\..\\redengine-game.json", j({"name": "Evil"}), "stored"),
                                          ("\\redengine-game.json", j({"name": "Evil"}), "stored"), ("Game.bat", PLAIN_BAT, "stored")])

    deep = "a/" * 34  # a ZIP of one folder in one folder in ..., however deep, is played from the innermost
    x.zipped("zip-deep-chain.zip", [(deep + "redengine-game.json", j({"name": "Deep Chain"}), "stored"), (deep + "Game.bat", PLAIN_BAT, "stored")], {"name": "Deep Chain"})
    x.zipped("zip-dot-members.zip", [("./redengine-game.json", j({"name": "Dot Card"}), "stored"), ("Top/Game.bat", header("Bat Name", description="From the bat."), "stored")],
             {"name": "Dot Card", "description": "From the bat."}, "bat", {"name": "card"})  # `./x` is `x`, so the ZIP holds two things and the card is at its root
    x.zipped("zip-link-beside-folder.zip", [("Top/redengine-game.json", j({"name": "Not Read"}), "stored"), ("Top/Game.bat", PLAIN_BAT, "stored"),
                                            ("link", b"Top", "stored", 0o120777)])  # a folder and a link are two things, so there is no one top folder to look in

    # -- scripts
    x.single("plain.bat", PLAIN_BAT)
    x.single("header-rem-crlf.bat", bat([*EXAMPLE[:2], "REM name: Text Quest", "REM description: A tiny text adventure about a lost key.", "REM presentation: 2d",
                                         "REM author: ai", "REM online: Two players, same room.", "REM entry: header-rem-crlf.bat", "REM thumb: shot.png",
                                         "REM args: --fast", "REM args: level 2", "REM notes: First release.", "REM notes: Added a second key.", "echo Welcome..."]),
             {"name": "Text Quest", "description": "A tiny text adventure about a lost key.", "presentation": "2d", "author": "ai", "online": "Two players, same room.",
              "entry": "header-rem-crlf.bat", "args": ["--fast", "level 2"]}, "bat")  # its notes are not read
    x.single("header-atrem-lf.bat", bat(["@echo off", "@REM Some license text here", "@rEm   redengine-game   ", "@REM kind: 3d", "@REM name:Colonel   Mustard's  Quest",
                                         "rem author: human", "echo hi"], eol=b"\n"),
             {"name": "Colonel Mustard's Quest", "presentation": "3d", "author": "human"}, "bat")
    x.single("header-colons-bom.bat", bat(["@echo off", ":: Text Adventure", ":: redengine-game", ":: name: Colons Quest", ":: description: Uses double colons.",
                                           "::presentation: hybrid", "", ":: name: after the blank line, ignored", "echo hi"], bom=True),
             {"name": "Colons Quest", "description": "Uses double colons.", "presentation": "hybrid"}, "bat")
    x.single("header-cmd.cmd", bat(["REM redengine-game", "REM name: A Cmd Game", "REM author: human", "set X=1"], eol=b"\n"), {"name": "A Cmd Game", "author": "human"}, "bat")
    x.single("header-ended-by-code.bat", bat(["REM redengine-game", "REM name: Before", "echo code", "REM description: after the code, ignored"]), {"name": "Before"}, "bat")
    filler = [f"echo filler {i}" for i in range(1, 60)]  # 59 lines: the block starts on line 60
    x.single("header-cut-at-64.bat", bat([*filler, "REM redengine-game", "REM name: Line 61", "REM description: Line 62", "REM presentation: 3d", "REM author: ai",
                                          "REM online: line 65, not read", "REM notes: line 66, not read"]),
             {"name": "Line 61", "description": "Line 62", "presentation": "3d", "author": "ai"}, "bat")
    x.single("header-after-64.bat", bat([*filler, "echo filler 60", "echo filler 61", "echo filler 62", "echo filler 63", "echo filler 64", "REM redengine-game", "REM name: Late"]))
    x.single("header-remark-not-a-marker.bat", bat(["REMARK redengine-game", "REM name: Nope", "echo hi"]))
    # white space in a header is ASCII only: a space, tab, line end, vertical tab or form feed; any other Unicode space makes the line something else
    x.single("header-ascii-space.bat", bat(["REM redengine-game\x0c", "REM \x0bname\x0c: Vt Quest", "echo hi"]), {"name": "Vt Quest"}, "bat")
    x.single("header-tag-unicode-space.bat", bat(["REM redengine-game\u3000", "REM name: Nope", "echo hi"]))
    x.single("header-key-unicode-space.bat", bat(["REM redengine-game", "REM name\u3000: Nope", "REM description: Yes", "echo hi"]), {"description": "Yes"}, "bat")
    x.single("header-rem-nbsp.bat", bat(["REM\u00a0redengine-game", "REM name: Nope", "echo hi"]))
    x.single("header-rem-vt.bat", bat(["REM\x0bredengine-game", "REM name: Nope", "echo hi"]))
    x.single("header-lf-cr.bat", bat(["@echo off", "REM redengine-game", "REM name: Nope", "echo hi"], eol=b"\n\r"))  # only CRLF and LF end a line
    x.single("header-cr-only.bat", bat(["@echo off", "REM redengine-game", "REM name: Nope", "echo hi"], eol=b"\r"))
    x.single("header-hostile.bat", b"\n".join([b"REM redengine-game", b"REM name: Caf\xe9 (latin-1 byte)", b"REM bogus: ignored", b"REM no colon on this line",
                                               b"REM description: " + b"x" * 500, b"REM presentation: 4d", b"REM author: ai", b"REM online: bell\x07 here",
                                               *[f"REM notes: n{i:02d}".encode() for i in range(1, 13)], b"REM args:", *[f"REM args: a{i:02d}".encode() for i in range(1, 21)],
                                               b"echo hi", b""]),
             {"name": "Caf\ufffd (latin-1 byte)", "description": "x" * 400, "author": "ai", "online": "bell here",
              "args": [f"a{i:02d}" for i in range(1, 17)]}, "bat")

    # -- programs: a record, version information, both, and the ones a record cannot be added to
    x.single("plain.exe", pe())
    x.single("stamped.exe", exe, stamped, "exe")
    x.single("versioned.exe", program, {"name": "Version Quest", "description": "A game that only has version information."}, "program")
    x.single("versioned32.exe", pe(resources(version_info([("FileDescription", "A 32-bit program with a description."), ("ProductName", "Thirty Two")])), plus=False),
             {"name": "Thirty Two", "description": "A 32-bit program with a description."}, "program")
    x.single("both.exe", pe(resources(version_info([("Comments", "Version comment."), ("ProductName", "Version Name")])), tail=record({"name": "Record Name", "presentation": "2d"})),
             {"name": "Record Name", "presentation": "2d", "description": "Version comment."}, "exe", {"description": "program"})
    x.single("versioned-junk.exe", pe(resources(version_info([("Comments", "game"), ("FileDescription", "Cool Little Game"), ("ProductName", "application")]))),
             {"description": "Cool Little Game"}, "program")
    x.single("versioned-same.exe", pe(resources(version_info([("FileDescription", "Same Name"), ("ProductName", "Same Name")]))), {"name": "Same Name"}, "program")
    x.single("versioned-empty.exe", pe(resources(version_info([("Comments", ""), ("FileDescription", "app"), ("ProductName", "")]))))
    x.single("versioned-two-tables.exe", pe(resources(version_info([("FileDescription", "First Table Wins")], [("ProductName", "Second Table")]))),
             {"description": "First Table Wins"}, "program")
    x.single("overlay.exe", pe(tail=b"INSTALLER PAYLOAD " * 8), refused=True)
    x.single("overlay-with-record.exe", pe(tail=b"INSTALLER PAYLOAD " * 8 + record({"name": "Overlay Record"})), {"name": "Overlay Record"}, "exe", refused=True)
    x.single("signed.exe", pe(cert=True), refused=True)
    x.single("truncated.exe", program[:0x2C0], refused=True)
    x.single("tiny.exe", b"MZ" + b"\0" * 20, refused=True)
    x.single("not-a-program.exe", b"hello, this is not a program\n", refused=True)
    x.single("lying-record-length.exe", pe(tail=compact({"name": "Lie"}) + struct.pack("<I", 0x00FFFFFF) + MAGIC), refused=True)
    x.single("lying-record-huge.exe", pe(tail=record(b"x" * 20000)), refused=True)
    x.single("record-not-json.exe", pe(tail=record(b"not json at all")))
    x.single("record-array.exe", pe(tail=record(b"[1, 2]")))
    x.single("record-empty.exe", pe(tail=record(b"")))
    blob = version_info(VERSION)
    x.single("hostile-rsrc-bad-rva.exe", pe(resources(blob, rva=0x7FFF0000)))
    x.single("hostile-rsrc-size.exe", pe(resources(blob, size=0xFFFFFFFF)))
    x.single("hostile-rsrc-loop.exe", pe(resources(blob, loop=True)))
    x.single("hostile-version-zero-length.exe", pe(resources(b"\0" * len(blob))))
    x.single("hostile-version-overrun.exe", pe(resources(patched(blob, 0, b"\xff\xff"))))
    both = {"name": "Version Quest", "description": "A game that only has version information."}
    x.single("versioned-named-types.exe", pe(tree(blob, named_types=2)), both, "program")
    for name, rsrc in (("no-language", tree(blob, shape="no-language")), ("extra-level", tree(blob, shape="extra-level")), ("type-is-data", tree(blob, shape="type-is-data")),
                       ("names-count-lies", tree(blob, names=(255, 1))), ("names-count-past-resources", tree(blob, names=(120, 0))), ("top-count-fits-not", tree(blob, top=(0, 4096))), ("top-count-over-cap", tree(blob, top=(0, 5000))),
                       ("top-count-short", tree(blob, top=(0, 1))), ("named-count-lies", tree(blob, named_types=1, top=(3, 0))),
                       ("type-flag-missing", tree(blob, shape="type-flag-missing")), ("name-flag-missing", tree(blob, shape="name-flag-missing")),
                       ("names-count-over-cap", tree(blob, names=(0, 4097), size=33000))):
        x.single(f"hostile-rsrc-{name}.exe", pe(rsrc))
    x.single("versioned-names-count-at-cap.exe", pe(tree(blob, names=(0, 4096), size=33000)), both, "program")  # 4096 entries are read, 4097 are not
    x.single("hostile-version-odd-value.exe", pe(resources(version_info([("ProductName", "Odd Name"), ("Comments", "After it.")], short="ProductName"))),
             {"name": "Odd Name", "description": "After it."}, "program")  # a value cut in the middle of a character loses that half character
    x.single("hostile-pe-sections.exe", patched(program, 0x80 + 6, b"\xff\xff"), refused=True)
    x.single("hostile-pe-lfanew.exe", patched(program, 60, b"\xf0\xff\xff\xff"), refused=True)
    x.single("hostile-pe-optional-size.exe", patched(program, 0x80 + 20, b"\x0a\x00"), refused=True)
    more(x)
    return x


def more(x: Fixtures) -> None:
    """The cases added when the first ones were attacked: limits on names, a program built unstripped, signed after it was stamped, a fork that still
    holds its parent's script or program, and the places where a reader once guessed."""
    plain = pe()
    parent = {"slug": "snake", "version": 3}
    by_card = {"name": "card", "forked_from": "card"}

    # -- a ZIP member whose name is over 1024 bytes or has more than 64 parts is not there (so the ZIP is still one folder, with its card at the root)
    one = [("Game/redengine-game.json", j({"name": "Deep Names"}), "stored"), ("Game/Game.bat", PLAIN_BAT, "stored")]
    x.zipped("zip-name-too-long.zip", [*one, (("d" * 99 + "/") * 11 + "y.bat", PLAIN_BAT, "stored")], {"name": "Deep Names"})  # 1105 bytes, 12 parts
    x.zipped("zip-name-too-deep.zip", [*one, ("x/" * 64 + "y.bat", PLAIN_BAT, "stored")], {"name": "Deep Names"})  # 133 bytes, 65 parts
    x.zipped("zip-name-deepest-allowed.zip", [("a/" * 63 + "redengine-game.json", j({"name": "Deepest"}), "stored"), ("a/" * 63 + "Game.bat", PLAIN_BAT, "stored")],
             {"name": "Deepest"})  # 64 parts
    # a member the app cannot unpack (not stored or deflated) or whose name has a NUL is not there; the comment's white space is ASCII white space
    x.zipped("zip-bzip2-member.zip", [("Game/Game.bat", PLAIN_BAT, "stored"), ("Game/redengine-game.json", (PACKED_CARD, PACKED), "bzip2")])
    x.zipped("zip-nul-name.zip", [("Game.bat\0.txt", header("Nul Name"), "stored"), ("readme.txt", b"r", "stored")])
    # a header that says the card is 2 GiB does not hide it: what is there is read, as the app reads it when it unpacks it
    lying = bytearray(zip_bytes([("Game/redengine-game.json", j({"name": "Declared Big"}), "stored"), ("Game/Game.bat", PLAIN_BAT, "stored")]))
    for signature, at in ((b"PK\3\4", 22), (b"PK\1\2", 24)):  # where a local header and a central one keep the size
        for i in range(len(lying) - 4):
            if lying[i:i + 4] == signature:
                struct.pack_into("<I", lying, i + at, 0x80000000)
    x.files["zip-card-declares-2-gib.zip"] = bytes(lying)
    x.says("zip-card-declares-2-gib.zip", {"name": "Declared Big"})
    x.zipped("zip-device-name.zip", [("Game/Game.bat", PLAIN_BAT, "stored"), ("Game/aux.bat", header("Aux Quest"), "stored"), ("Game/COM1.txt", b"x", "stored")])  # not files
    x.zipped("zip-comment-vt.zip", [("Game.bat", PLAIN_BAT, "stored")], {"name": "Vertical Tab", "description": "Whatever the white space."}, "zip",
             comment=b"\x0bredengine-game\x0b" + compact({"name": "Vertical Tab", "description": "Whatever the white space."}) + b"\x0b")

    # -- a fork takes its description, designer, online note and notes from its card file or ZIP comment only: a script or program in it is its parent's
    own = header("Parent Name", description="The parent's words.", presentation="3d", author="ai", online="The parent's online note.", notes="The parent's notes.")
    x.folder("folder-fork-ignores-parents-script", {"redengine-game.json": j({"name": "My Fork", "presentation": "2d", "forked_from": parent}), "Game.bat": own},
             {"name": "My Fork", "presentation": "2d", "forked_from": parent})
    x.folder("folder-fork-ignores-parents-program", {"redengine-game.json": j({"name": "My Fork", "forked_from": parent}),
                                                    "Game.exe": pe(resources(version_info(VERSION)), tail=record(STAMPED))},
             {"name": "My Fork", "presentation": "3d", "forked_from": parent}, "exe", by_card)
    x.zipped("zip-fork-description-from-comment.zip", [("redengine-game.json", j({"name": "My Fork", "forked_from": parent}), "stored"), ("Game.bat", own, "stored")],
             {"name": "My Fork", "description": "Its own words.", "presentation": "3d", "forked_from": parent}, "zip", {**by_card, "presentation": "bat"},
             comment=b"redengine-game " + compact({"description": "Its own words.", "forked_from": {"slug": "other", "version": 1}}))
    x.zipped("zip-fork-comment-only.zip", [("Game.bat", own, "stored")], {"name": "My Fork", "presentation": "3d", "forked_from": parent}, "zip", {"presentation": "bat"},
             comment=b"redengine-game " + compact({"name": "My Fork", "forked_from": parent}))

    # -- a forked_from slug is at most 64 characters
    for n, ok in ((64, True), (65, False)):
        fork = {"slug": "a" * n, "version": 1}
        x.folder(f"{'folder' if ok else 'hostile'}-forked-slug-{n}", {"redengine-game.json": j({"name": "Long Slug", "forked_from": fork}), "Game.exe": b"MZ"},
                 {"name": "Long Slug", **({"forked_from": fork} if ok else {})})

    # -- engine.name: at most 1024 bytes; only Unicode white space is trimmed (not the separator controls U+001C to U+001F)
    two = {"A.bat": header("Alpha", description="Alpha's description."), "B.bat": header("Beta", description="Beta's description.", author="ai")}
    alpha = {"name": "Alpha", "description": "Alpha's description.", "author": "ai"}
    x.folder("folder-engine-name-1024", {**two, "engine.name": b"B.bat\n" + b" " * 1018}, {"name": "Beta", "description": "Beta's description.", "author": "ai"}, "bat")
    x.folder("folder-engine-name-1025", {**two, "engine.name": b"B.bat\n" + b" " * 1019}, alpha, "bat")
    x.folder("folder-engine-name-unicode-space", {**two, "engine.name": "\u3000B.bat\u00a0\n".encode()}, {"name": "Beta", "description": "Beta's description.", "author": "ai"}, "bat")
    x.folder("hostile-engine-name-separator-controls", {**two, "engine.name": b"\x1cB.bat\x1d\n"}, alpha, "bat")

    # -- which files could start a game: ASCII case rules for the names that are not the game, and a name that is only an extension
    x.folder("folder-unicode-setup-name", {"\u017fetup.bat": header("Long S"), "\u0200z.bat": header("Zed", description="Zed's description.")},
             {"name": "Long S", "description": "Zed's description."}, "bat")
    x.folder("folder-dot-bat", {".bat": header("Dot Bat"), "readme.txt": b"r"}, {"name": "Dot Bat"}, "bat")

    # -- version information: the first of a repeated key, a key of more than 64 units ends the table, a description equal to the whole (uncut) name says nothing
    x.single("versioned-duplicate-key.exe", pe(resources(version_info([("ProductName", "First"), ("ProductName", "Second"), ("Comments", "One"), ("Comments", "Two")]))),
             {"name": "First", "description": "One"}, "program")
    x.single("versioned-long-key-64.exe", pe(resources(version_info([("K" * 64, "x"), ("ProductName", "After")]))), {"name": "After"}, "program")
    x.single("versioned-long-key-65.exe", pe(resources(version_info([("K" * 65, "x"), ("ProductName", "After")]))))
    x.single("versioned-long-name.exe", pe(resources(version_info([("FileDescription", "A" * 70), ("ProductName", "A" * 70)]))), {"name": "A" * 60}, "program")
    x.single("versioned-long-name-cut.exe", pe(resources(version_info([("FileDescription", "A" * 60), ("ProductName", "A" * 60 + " tail")]))),
             {"name": "A" * 60, "description": "A" * 60}, "program")

    # -- what an engine calls the program it ships as every game's own (NW.js, which RPG Maker MV and MZ ship as Game.exe; Electron; LOVE; Godot) names no
    # game, whatever its case and a version number after it; a value that says something keeps its version number
    x.single("versioned-runtime-nwjs.exe", pe(resources(version_info(RUNTIME))))
    x.single("versioned-runtime-electron.exe", pe(resources(version_info([("FileDescription", "Electron"), ("OriginalFilename", "electron.exe"), ("ProductName", "Electron")]))))
    x.single("versioned-runtime-love.exe", pe(resources(version_info([("FileDescription", "LÖVE 11.5"), ("ProductName", "LÖVE")]))))
    x.single("versioned-runtime-godot.exe", pe(resources(version_info([("FileDescription", "Godot Engine v3.5.1"), ("ProductName", "GODOT ENGINE")]))))
    x.single("versioned-runtime-own-words.exe", pe(resources(version_info([("Comments", "A quest by moonlight."), ("FileDescription", "nwjs"), ("ProductName", "nwjs")]))),
             {"description": "A quest by moonlight."}, "program")
    x.single("versioned-version-number.exe", pe(resources(version_info([("FileDescription", "Electron 28.1"), ("ProductName", "Star Miner 2")]))), {"name": "Star Miner 2"}, "program")
    x.zipped("zip-runtime-program.zip", [("Moonlit Quest/", b"", "stored"), ("Moonlit Quest/Game.exe", pe(resources(version_info(RUNTIME))), "deflated"),
                                         ("Moonlit Quest/www/index.html", b"<title>Moonlit Quest</title>", "stored")])

    # -- a program built by gcc or mingw keeps its symbol table and strings after the last section, which are part of it; other data there is not
    symbols = (3, symbol_table(3))
    x.single("unstripped.exe", pe(symbols=symbols))
    stamped = {k: v for k, v in STAMPED.items() if k not in ("schema", "notes")}  # a record's notes are not read
    x.single("unstripped-stamped.exe", pe(resources(version_info(VERSION)), symbols=symbols, tail=record(STAMPED)), stamped, "exe")
    x.single("unstripped-then-overlay.exe", pe(symbols=symbols, tail=b"INSTALLER PAYLOAD " * 8), refused=True)
    x.single("symbols-out-of-file.exe", patched(plain, 0x80 + 12, struct.pack("<II", 0x7FFFFFF0, 0xFFFFFFFF)))  # a claim that reaches nothing is no symbol table
    x.single("symbols-lying-string-table.exe", patched(pe(symbols=symbols), 0x400 + 18 * 3, struct.pack("<I", 0xFFFFFF)), refused=True)

    # -- an online note says how a game is played online, never where: an address or a key makes the field not found
    for name, note in (("ipv4", "Join 203.0.113.5:27015 with key hunter2"), ("url", "https://example.com/join?k=abc"), ("port", "Play at server:27016."),
                       ("domain", "Meet on discord.gg/abc123"), ("key", "The key=hunter2 opens it"), ("ipv6", "Go to [fe80::1]:27015")):
        x.folder(f"hostile-online-{name}", {"redengine-game.json": j({"name": "Online", "description": "Words.", "online": note}), "Game.exe": b"MZ"},
                 {"name": "Online", "description": "Words."})
    words = "Co-op: 2-4 players on one LAN (ping 30ms, 16:9 screens, v1.2.3)."
    x.folder("folder-online-words", {"redengine-game.json": j({"name": "Online", "online": words}), "Game.exe": b"MZ"}, {"name": "Online", "online": words})

    # -- stamped, then signed: the record ends where the certificate table starts (after up to 7 bytes of padding)
    for name, aligned in (("signed-after-record.exe", True), ("signed-after-record-padded.exe", False)):
        card = aligned_card("Signed After", aligned)
        x.single(name, pe(before_cert=record(card), cert=True), card, "exe", refused=True)
    x.single("signed-address-only.exe", patched(plain, 0x80 + 24 + 112 + 32, struct.pack("<II", 0x400, 0)), refused=True)  # any field of the signature entry says "signed"

    # -- headers that do not hold together are not a program
    x.single("hostile-pe-lfanew-small.exe", lfanew_inside_dos(plain), refused=True)
    x.single("hostile-pe-headers-past-end.exe", patched(plain, 0x80 + 24 + 60, struct.pack("<I", len(plain) + 0x1000)), refused=True)
    x.single("hostile-pe-optional-63.exe", patched(plain, 0x80 + 20, struct.pack("<H", 63)), refused=True)
    x.single("hostile-pe-optional-100.exe", patched(plain, 0x80 + 20, struct.pack("<H", 100)), refused=True)
    x.single("headers-only.exe", patched(plain, 0x80 + 24 + 240 + 16, struct.pack("<I", 0))[:0x200])  # no section holds anything: the program is its headers


def files() -> dict[str, bytes]:
    """Every file of this folder but this script, by path: the fixtures, `expected.json` and `.gitattributes`."""
    x = build()
    expected = {"about": "What a reader of the game card must find in each fixture; written by build_fixtures.py (docs/GAME_METADATA.md).",
                "fixtures": x.expected, "stamp_refused": sorted(x.refused)}
    return {**x.files, "expected.json": (json.dumps(expected, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            ".gitattributes": b"# Fixtures are bytes: no line-end or encoding conversion on any machine.\n* -text\n"}


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE
    # Everything in the folder is replaced: only a new or empty folder, or one this script wrote (it holds expected.json), is.
    if out.exists() and not out.is_dir():
        raise SystemExit(f"{out}: not a folder")
    if out.is_dir() and not (out / "expected.json").is_file() and any(e.name not in ("build_fixtures.py", "__pycache__") for e in out.iterdir()):
        raise SystemExit(f"{out} holds files but no expected.json, so it is not a fixtures folder: give a new or empty folder (everything in it is replaced)")
    out.mkdir(parents=True, exist_ok=True)
    for entry in out.iterdir():
        if entry.name not in ("build_fixtures.py", "__pycache__"):
            shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
    for rel, data in files().items():
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    print(f"wrote {len(files())} files to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
