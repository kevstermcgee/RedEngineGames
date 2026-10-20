#!/usr/bin/env python3
"""The game card: what a ready-made Windows game says about itself (name, description, 2D/3D, designer, ...), read from inside the game and written into it.
The contract is docs/GAME_METADATA.md; the app (launcher/core/src/meta.rs) implements it separately and both read the fixtures in testdata/game_meta/.

  python3 distribution/game_meta.py show Game.zip                       what the game says about itself (--json for the machine form)
  python3 distribution/game_meta.py stamp Quest.bat --name "Text Quest" --description "A tiny text adventure." --kind 2d --author ai
  python3 distribution/game_meta.py stamp Game.exe  --name "Star Miner" --description "Mine asteroids, dodge pirates."
  python3 distribution/game_meta.py stamp Game.zip  --name "Star Miner" --thumb shot.png     card file + comment (rewrites the ZIP)
  python3 distribution/game_meta.py stamp ./MyGame/ --name "Star Miner"                       writes redengine-game.json

`read` never runs anything, never opens the network, never unpacks a ZIP, never follows a link out of the game's folder and reads only the card file,
the first 64 lines of a script, and the end and the resources of a program (a hand-written, bounds-checked parser); whatever is hostile in a game is
left out of the answer, never an error. `stamp` never changes what a game does: a script keeps every line it had, a program keeps every byte (the
record goes after the last one), and it refuses a program it cannot add to without changing it, and a card that a reader would ignore for its size.
A ZIP is read as the app unpacks it: a member it could not unpack (encrypted, not stored or deflated, a name over 1024 bytes or 64 parts, a NUL, a
device's name) is not there, and what is decompressed to look inside is capped for the whole ZIP.

Run the tests with `python3 -m unittest discover distribution`.
"""

import argparse
import json
import os
import re
import shutil
import stat
import struct
import sys
import unicodedata
import zipfile
from pathlib import Path

CARD_FILE = "redengine-game.json"
THUMB_STEM = "redengine-game-thumb"
COMMENT = b"redengine-game"
MAGIC = b"REDGAME1"
MAX_CARD = 16 * 1024
MAX_THUMB = 5 * 1024 * 1024
HEADER_LINES = 64
HEADER_BYTES = 64 * 1024
RUNNABLE = (".exe", ".bat", ".cmd")
PICTURES = (".png", ".jpg")
# Executables a ready-made game often carries that are never the game itself (the start of the name, as `upload::NOT_THE_GAME` in the app).
NOT_THE_GAME = re.compile(r"^(unins|setup|install|vc_?redist|dxsetup|unitycrashhandler|crashpad_handler|notification_helper)[^/]*\.(exe|bat|cmd)$", re.I | re.A)
KINDS = ("2d", "3d", "hybrid")
AUTHORS = ("ai", "human")
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
FIELDS = ("name", "description", "presentation", "author", "online", "entry", "args", "thumb", "notes", "forked_from")
LIMITS = {"name": 60, "description": 400, "online": 200}
ITEM, MAX_ARGS, MAX_NOTES = 200, 16, 10
SOURCES = ("card", "zip", "bat", "exe", "program")
LABELS = {"card": "card file", "zip": "ZIP comment", "bat": "script header", "exe": "record in the program", "program": "version information"}
HEADER_KEYS = ("name", "description", "presentation", "kind", "author", "online", "entry", "thumb", "notes", "args")
JUNK = ("application", "game", "app")  # version information that says nothing
MAX_ENTRIES = 200_000  # a ZIP with more members than this is not looked into
MAX_STARTS = 16
PARENTS_WORDS = ("description", "author", "online", "notes")  # what a fork does not take from its parent's script or program
MAX_NAME = 1024  # a ZIP member whose name is longer than this many bytes, or sits deeper than MAX_DEPTH folders, is not there: the app could not unpack it either
MAX_DEPTH = 64
MAX_SLUG = 64
MAX_VERSION_KEY = 64  # UTF-16 units in the key of a version-information block
MAX_DIRECTORY = 4096  # entries in one resource directory of a program
JUNK_FOLDERS = ("__MACOSX", ".DS_Store")
DEVICES = frozenset(["con", "prn", "aux", "nul", "conin$", "conout$", *(f"com{n}" for n in range(1, 10)), *(f"lpt{n}" for n in range(1, 10))])
# Characters a script header cannot hold: cmd reads them as part of a command (or a line that goes on) even in a comment.
CMD_SPECIAL = "^%&|<>"

# Unicode White_Space, so that every reader agrees on what a run of white space is.
_SPACE = frozenset(map(chr, [*range(9, 14), 0x20, 0x85, 0xA0, 0x1680, *range(0x2000, 0x200B), 0x2028, 0x2029, 0x202F, 0x205F, 0x3000]))
_BIDI = frozenset(map(chr, [*range(0x202A, 0x202F), *range(0x2066, 0x206A)]))
_WHITE = "".join(sorted(_SPACE))


# ---- cleaning and checking ---------------------------------------------------------------------------------------------------------------


def clean(text: str, limit: int | None = None) -> str:
    """A string as the card keeps it: no control characters or direction overrides, runs of white space as one space, trimmed, cut to `limit`."""
    kept = "".join(" " if c in _SPACE else "" if c in _BIDI or unicodedata.category(c) in ("Cc", "Cs") else c for c in text)
    kept = re.sub(" +", " ", kept).strip(" ")
    return kept[:limit].rstrip(" ") if limit else kept


_ASCII_LOWER = {c: c + 32 for c in range(ord("A"), ord("Z") + 1)}
DOMAINS = ("com", "net", "org", "io", "gg", "tv", "me", "us", "uk", "de", "eu", "xyz", "dev", "app", "ly", "gl", "info")  # well-known endings of a place's name


def looks_like_address(note: str) -> bool:
    """Whether an online note is a place or a key rather than words (a card says how a game is played online, never where to join it): a URL, an IPv4 or
    an IPv6 address, `name:port`, a name ending in a well-known domain, or a secret given as `key=...`. The note is cleaned; the check is on ASCII only."""
    note = note.translate(_ASCII_LOWER)
    if any(k in note for k in ("key=", "token=", "password=", "pass=", "secret=")):
        return True
    for word in note.split():
        t = word.lstrip(",;!?()[]{}<>\"'").rstrip(",;!?()[]{}<>\"'.:")
        host = t.split("/")[0].rsplit("@", 1)[-1]
        name, _, port = host.rpartition(":") if ":" in host else (host, "", "")
        labels = name.split(".")
        digits = lambda s, most: 1 <= len(s) <= most and all(c in "0123456789" for c in s)  # noqa: E731
        if ("://" in t or t.startswith("www.") or "::" in t
                or (t.count(":") >= 3 and all(c in "0123456789abcdef:" for c in t))
                or (len(labels) == 4 and all(digits(label, 3) for label in labels))
                or (digits(port, 5) and len(port) >= 2 and name[-1:] and (name[-1] in "abcdefghijklmnopqrstuvwxyz]"))
                or (len(labels) >= 2 and all(label and all(c in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in label) for label in labels) and labels[-1] in DOMAINS)):
            return True
    return False


def _text(value, limit: int | None = None) -> str | None:
    return (clean(value, limit) or None) if isinstance(value, str) else None


def device(part: str) -> bool:
    """A name Windows takes for a device (`CON`, `aux.txt`, `Com1 .bat`): opening it is not opening a file."""
    return part.split(".", 1)[0].rstrip(" ").lower() in DEVICES


def safe_path(text: str | None) -> str | None:
    """A path inside a game as a card may name it: relative, `/`-separated, no `..`, no drive, no backslash, no device name."""
    if not text or len(text) > 260 or "\\" in text or ":" in text or "\0" in text:
        return None
    return None if any(p in ("", ".", "..") or device(p) for p in text.split("/")) else text


def _items(value, most: int) -> list[str] | None:
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        return None
    return [t for x in value if (t := clean(x, ITEM))][:most] or None


def check_card(raw: dict, game=None) -> dict:
    """The fields of a card that hold up, cleaned, in the card's order; what does not is left out. `game` says which files exist (None: not asked)."""
    card: dict = {}
    for key in ("name", "description"):
        if (v := _text(raw.get(key), LIMITS[key])):
            card[key] = v
    for field, allowed, synonyms in (("presentation", KINDS, ("presentation", "kind")), ("author", AUTHORS, ("author",))):
        for key in synonyms:
            if (v := _text(raw.get(key), 20)) in allowed:
                card[field] = v
                break
    if (v := _text(raw.get("online"), LIMITS["online"])) and not looks_like_address(v):
        card["online"] = v
    entry = safe_path(_text(raw.get("entry")))
    if entry and entry.lower().endswith(RUNNABLE) and (game is None or game.is_file(entry)):
        card["entry"] = entry
    if (v := _items(raw.get("args"), MAX_ARGS)):
        card["args"] = v
    thumb = safe_path(_text(raw.get("thumb")))
    if thumb and thumb.lower().endswith(PICTURES) and (game is None or game.is_file(thumb, MAX_THUMB)):
        card["thumb"] = thumb
    if (v := _items(raw.get("notes"), MAX_NOTES)):
        card["notes"] = v
    fork = raw.get("forked_from")
    if isinstance(fork, dict):
        slug, version = fork.get("slug"), fork.get("version")
        if isinstance(slug, str) and len(slug) <= MAX_SLUG and SLUG.fullmatch(slug) and type(version) is int and 1 <= version < 2**64:
            card["forked_from"] = {"slug": slug, "version": version}
    return card


def _no_constant(name):
    raise ValueError(name)


def _finite(text: str) -> float:
    """A JSON number as the app reads it: one that does not fit a 64-bit float (1e999999, an integer of 309 digits) makes the card unreadable."""
    if abs(value := float(text)) == float("inf"):
        raise ValueError(text)
    return value


def _whole(text: str) -> int:
    _finite(text)
    return int(text)


def _too_deep(value, limit: int = 127) -> bool:
    stack = [(value, 1)]
    while stack:
        v, depth = stack.pop()
        if isinstance(v, (dict, list)):
            if depth > limit:
                return True
            stack.extend((x, depth + 1) for x in (v.values() if isinstance(v, dict) else v))
    return False


def parse_card(data: bytes) -> dict | None:
    """The JSON object in `data`, or None: too large, not UTF-8, not JSON (NaN is not), not an object, nested more than 127 deep (the object itself is the
    first level), a number that does not fit a 64-bit float, a lone surrogate."""
    if len(data) > MAX_CARD:
        return None
    try:
        raw = json.loads(data.decode("utf-8-sig"), parse_constant=_no_constant, parse_float=_finite, parse_int=_whole)
        if isinstance(raw, dict) and not _too_deep(raw):
            json.dumps(raw, ensure_ascii=False).encode("utf-8")  # a lone surrogate cannot be kept
            return raw
    except (ValueError, RecursionError):
        pass
    return None


# ---- the three places a card lives besides a file ---------------------------------------------------------------------------------------


_COMMENT_LINE = re.compile(rb"[ \t]*(?:@?rem(?=[ \t]|\Z)|::)(.*)", re.I | re.S)


def _lines(data: bytes, most: int | None = None) -> list[bytes]:
    lines = data.split(b"\n") if most is None else data.split(b"\n", most)[:most]
    return [x[:-1] if x.endswith(b"\r") else x for x in lines]


def _block(lines: list[bytes]) -> tuple[int, int, dict] | None:
    """The header block among the first 64 lines of a script: (its first line, the line after its last, the fields as written), or None."""
    lines = lines[:HEADER_LINES]
    for i, line in enumerate(lines):
        m = _COMMENT_LINE.fullmatch(line)
        if not (m and m.group(1).strip() == COMMENT):
            continue
        fields: dict = {}
        j = i + 1
        while j < len(lines) and (m := _COMMENT_LINE.fullmatch(lines[j])):
            key, colon, value = m.group(1).decode("utf-8", "replace").partition(":")
            key = key.strip(" \t\r\n\x0b\x0c")  # ASCII white space only, as around the tag
            if colon and key in HEADER_KEYS:
                if key in ("notes", "args"):
                    fields.setdefault(key, []).append(value)
                else:
                    fields[key] = value
            j += 1
        return i, j, fields
    return None


def _header(head: bytes) -> dict | None:
    body = head[3:] if head.startswith(b"\xef\xbb\xbf") else head
    found = _block(_lines(body, HEADER_LINES))
    return found[2] if found else None


def _record_length(f, end: int | None = None) -> int | None:
    """The length of the card record that ends at `end` (default: the end of a program; `f` has `size` and `read_at`), or None when nothing there is one."""
    end = f.size if end is None else end
    if end < 12 or end > f.size:
        return None
    tail = f.read_at(end - 12, 12)
    if len(tail) != 12 or tail[4:] != MAGIC:
        return None
    (length,) = struct.unpack_from("<I", tail)
    return length if length <= MAX_CARD and length + 12 <= end else None


def _record_end(f) -> int | None:
    """Where the card record of a program ends: at the end of the file, or, when the program was signed after it was stamped, where the certificate
    table starts (which is on a multiple of 8 bytes, so up to 7 bytes of padding come first)."""
    if _record_length(f) is not None:
        return f.size
    pe = _pe(f)
    if pe and len(pe["dirs"]) > 4 and pe["dirs"][4][1]:
        table = pe["dirs"][4][0]
        for end in range(table, table - 8, -1):
            if _record_length(f, end) is not None:
                return end
    return None


def _record(f) -> bytes | None:
    end = _record_end(f)
    length = _record_length(f, end) if end is not None else None
    if length is None:
        return None
    data = f.read_at(end - 12 - length, length)
    return data if len(data) == length else None


# ---- a Windows program: headers, resources, version information ----------------------------------------------------------------------


def _pe(f) -> dict | None:
    """The parts of a program's headers that matter here (sections, data directories, where the image ends); None if it is no PE file or they do not fit."""
    dos = f.read_at(0, 64)
    if len(dos) < 64 or dos[:2] != b"MZ":
        return None
    (lfanew,) = struct.unpack_from("<I", dos, 60)
    if lfanew < 64 or lfanew + 24 > f.size:
        return None
    head = f.read_at(lfanew, 24)
    if len(head) < 24 or head[:4] != b"PE\0\0":
        return None
    (count,), (opt_size,) = struct.unpack_from("<H", head, 6), struct.unpack_from("<H", head, 20)
    (symbols,), (symbol_count,) = struct.unpack_from("<I", head, 12), struct.unpack_from("<I", head, 16)
    if not 1 <= count <= 96 or opt_size < 64:
        return None
    opt = f.read_at(lfanew + 24, min(opt_size, 240))
    if len(opt) < min(opt_size, 240):
        return None
    (magic,) = struct.unpack_from("<H", opt)
    dirs_at, count_at = {0x10B: (96, 92), 0x20B: (112, 108)}.get(magic, (0, 0))
    if not dirs_at or len(opt) < dirs_at:
        return None
    (headers,), (ndirs,) = struct.unpack_from("<I", opt, 60), struct.unpack_from("<I", opt, count_at)
    dirs = [struct.unpack_from("<II", opt, dirs_at + 8 * i) for i in range(min(ndirs, 16, (len(opt) - dirs_at) // 8))]
    table = f.read_at(lfanew + 24 + opt_size, 40 * count)
    if len(table) < 40 * count:
        return None
    sections = [struct.unpack_from("<8xIIII", table, 40 * i) for i in range(count)]  # virtual size, address, raw size, raw offset
    end = max([headers] + [ptr + raw for _, _, raw, ptr in sections if raw])
    if symbols:  # gcc and mingw leave a symbol table and its strings after the last section: they are part of the program (a claim that reaches outside is none)
        strings = symbols + 18 * symbol_count
        tail = f.read_at(strings, 4)
        size = struct.unpack("<I", tail)[0] if len(tail) == 4 else 0
        if size >= 4 and strings + size <= f.size:
            end = max(end, strings + size)
    return {"size": f.size, "dirs": dirs, "sections": sections, "end": end}


def _rva(pe: dict, rva: int, length: int) -> int | None:
    """Where in the file the `length` bytes at `rva` are, when one section's raw data holds them all."""
    for _, va, raw, ptr in pe["sections"]:
        if va <= rva and rva - va + length <= raw and ptr + rva - va + length <= pe["size"]:
            return ptr + rva - va
    return None


def _entries(f, base: int, at: int, total: int) -> tuple[list[tuple[int, int]], int]:
    """The entries (name or id, offset) of the resource directory `at` bytes into the resources at file offset `base`, and how many are named."""
    head = f.read_at(base + at, 16) if at + 16 <= total else b""
    if len(head) < 16:
        return [], 0
    named, ids = struct.unpack_from("<HH", head, 12)
    n = named + ids
    raw = f.read_at(base + at + 16, 8 * n) if n <= MAX_DIRECTORY and at + 16 + 8 * n <= total else b""
    if len(raw) < 8 * n:  # a directory that holds more than it says, or more than the resources do, is not read
        return [], 0
    return [struct.unpack_from("<II", raw, 8 * i) for i in range(n)], named


def _version_blob(f, pe: dict) -> bytes | None:
    """The bytes of the program's first version resource (`RT_VERSION`, 16)."""
    if len(pe["dirs"]) <= 2 or not all(pe["dirs"][2]):
        return None
    rva, total = pe["dirs"][2]
    base = _rva(pe, rva, 16)
    if base is None:
        return None
    entries, named = _entries(f, base, 0, total)
    kind = next((o & 0x7FFFFFFF for n, o in entries[named:] if n == 16 and o >> 31), None)
    if kind is None:
        return None
    entries, _ = _entries(f, base, kind, total)
    if not entries or not entries[0][1] >> 31:
        return None
    entries, _ = _entries(f, base, entries[0][1] & 0x7FFFFFFF, total)
    if not entries or entries[0][1] >> 31 or entries[0][1] + 16 > total:
        return None
    leaf = f.read_at(base + entries[0][1], 16)
    if len(leaf) < 16:
        return None
    data_rva, size = struct.unpack_from("<II", leaf)
    start = _rva(pe, data_rva, size) if 6 <= size <= 0x10000 else None
    blob = f.read_at(start, size) if start is not None else b""
    return blob if len(blob) == size else None


def _node(b: bytes, at: int, end: int) -> tuple[str, int, int, int, int] | None:
    """The version-resource node at `at`: (key, value length, type, where its value starts, where it ends); None if it does not fit before `end`."""
    if at + 6 > end:
        return None
    length, vlen, kind = struct.unpack_from("<HHH", b, at)
    if length < 6 or at + length > end:
        return None
    stop = at + length
    j = at + 6
    while (j := b.find(b"\0\0", j, stop)) >= 0 and (j - at - 6) % 2:
        j += 1
    if j < 0 or (j - at - 6) // 2 > MAX_VERSION_KEY:
        return None
    return b[at + 6:j].decode("utf-16-le", "replace"), vlen, kind, (j + 2 + 3) & ~3, stop


def _kids(b: bytes, node: tuple[str, int, int, int, int]):
    """The children of a version-resource node, in order (at most 256)."""
    _, vlen, kind, value_at, end = node
    at = (value_at + (vlen * 2 if kind == 1 else vlen) + 3) & ~3
    for _ in range(256):
        kid = _node(b, at, end)
        if kid is None:
            return
        yield kid
        at = (kid[4] + 3) & ~3


def _version_strings(b: bytes) -> dict[str, str]:
    """`ProductName`, `Comments` and `FileDescription` of the first string table of a `VS_VERSION_INFO` resource."""
    root = _node(b, 0, len(b))
    if not root or root[0] != "VS_VERSION_INFO":
        return {}
    for info in _kids(b, root):
        if info[0] != "StringFileInfo":
            continue
        for table in _kids(b, info):
            out = {}
            for key, vlen, _, value_at, end in _kids(b, table):
                if key in ("ProductName", "Comments", "FileDescription"):
                    whole = (min(value_at + 2 * vlen, end) - value_at) // 2 * 2  # half a character at the end is not one
                    out.setdefault(key, b[value_at:value_at + whole].decode("utf-16-le", "replace").split("\0")[0])
            return out
        break
    return {}


def _program(f) -> dict:
    """What a program's version information says: its `ProductName` as the name, `Comments` else `FileDescription` as the description."""
    pe = _pe(f)
    blob = _version_blob(f, pe) if pe else None
    strings = _version_strings(blob) if blob else {}
    name = clean(strings.get("ProductName", ""))
    name = "" if name.lower() in JUNK else name
    description = ""
    for key in ("Comments", "FileDescription"):
        text = clean(strings.get(key, ""))
        if text and text.lower() not in JUNK and not (key == "FileDescription" and text.lower() == name.lower()):
            description = text
            break
    return {k: v for k, v in (("name", clean(name, LIMITS["name"])), ("description", clean(description, LIMITS["description"]))) if v}


# ---- a game to read: a folder, a ZIP or one file --------------------------------------------------------------------------------------


def _link(st: os.stat_result) -> bool:
    """A symbolic link or, on Windows, any reparse point (a junction too): never followed out of the game's folder."""
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & 0x400)


def _named_exactly(path: Path) -> bool:
    """Whether `path` is in its folder by exactly that name. A Windows disk finds `Quest.bat` when asked for `Quest.BAT`, and a ZIP read in place does
    not: a name in a card counts only as it is written, so every reader on every disk finds the same files (as `meta::named_exactly` in the app)."""
    try:
        with os.scandir(path.parent) as it:
            return any(e.name == path.name for e in it)
    except OSError:
        return False


class _Disk:
    """A file read at offsets."""

    def __init__(self, path):
        self.f = open(path, "rb")
        self.size = os.fstat(self.f.fileno()).st_size

    def read_at(self, off: int, n: int) -> bytes:
        if off < 0 or n <= 0 or off >= self.size:
            return b""
        self.f.seek(off)
        return self.f.read(min(n, self.size - off))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.f.close()


class _Member(_Disk):
    """A ZIP member read at offsets without unpacking it. What decompressing members may cost is capped for the whole ZIP (`budget`, bytes still to
    spend, shared by every member opened), and a compressed member that declares more than `MAX_PACKED` is not opened, so a bomb ends the look, not the program."""

    BUDGET = 256 << 20
    MAX_PACKED = 64 << 20

    def __init__(self, zf: zipfile.ZipFile, info: zipfile.ZipInfo, budget: list[int]):
        if info.compress_type != zipfile.ZIP_STORED and info.file_size > self.MAX_PACKED:
            raise OSError("too large to look into")
        self.f, self.info, self.size, self.pos, self.budget = zf.open(info), info, info.file_size, 0, budget

    def read_at(self, off: int, n: int) -> bytes:
        n = min(n, self.size - off)
        if off < 0 or n <= 0:
            return b""
        if self.info.compress_type != zipfile.ZIP_STORED:
            self.budget[0] -= (off if off < self.pos else off - self.pos) + n
            if self.budget[0] < 0:
                raise OSError("too large to look into")
        if off != self.pos:
            self.f.seek(off)
        data = self.f.read(n)
        self.pos = off + len(data)
        return data


def _slurp(game, rel: str, n: int) -> bytes:
    with game.open(rel) as f:
        return f.read_at(0, n)


def _candidates(scan) -> list[str]:
    """What could start a game, as `upload::candidates` finds it: the top folder's runnable files, else those one folder down (`scan(dir)` lists a folder)."""
    for depth in (1, 2):
        found: list[str] = []

        def walk(rel: str, left: int) -> None:
            for name, is_dir, is_file in sorted(scan(rel)):
                if is_dir and left > 1:
                    walk(f"{rel}{name}/", left - 1)
                elif is_file and name.lower().endswith(RUNNABLE) and not NOT_THE_GAME.match(name):
                    found.append(f"{rel}{name}")

        walk("", depth)
        if found:
            return found
    return []


class _Dir:
    """A folder game. Nothing is followed through a link, so what a card names is a file in the folder or nothing."""

    comment = b""

    def __init__(self, folder):
        self.root = Path(folder)
        while True:  # a folder holding one folder is played from inside it, however deep, as `upload_game.collect` does
            items = [(n, d) for n, d, _ in self.scan("") if n not in JUNK_FOLDERS]
            if len(items) != 1 or not items[0][1]:
                break
            self.root = self.root / items[0][0]

    def scan(self, rel: str) -> list[tuple[str, bool, bool]]:
        out = []
        try:
            with os.scandir(self.root / rel) as it:
                for _, e in zip(range(MAX_ENTRIES), it):
                    try:
                        st = e.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    out.append((e.name, stat.S_ISDIR(st.st_mode) and not _link(st), stat.S_ISREG(st.st_mode) and not _link(st)))
        except OSError:
            pass
        return out

    def is_file(self, rel: str, max_size: int | None = None) -> bool:
        p = self.root
        try:
            for part in rel.split("/"):
                p = p / part
                st = os.lstat(p)
                if _link(st) or not _named_exactly(p):
                    return False
            return stat.S_ISREG(st.st_mode) and (max_size is None or st.st_size <= max_size)
        except (OSError, ValueError):
            return False

    def open(self, rel: str) -> _Disk:
        return _Disk(self.root / rel)

    def candidates(self) -> list[str]:
        return _candidates(self.scan)

    def close(self) -> None:
        pass


class _Lone(_Dir):
    """One `.exe`, `.bat` or `.cmd` as a game of one file."""

    def __init__(self, path):
        self.path, self.root = Path(path), Path(path).parent

    def scan(self, rel: str) -> list[tuple[str, bool, bool]]:
        return [(self.path.name, False, True)] if rel == "" else []

    def is_file(self, rel: str, max_size: int | None = None) -> bool:
        return rel == self.path.name and self.path.is_file() and (max_size is None or self.path.stat().st_size <= max_size)

    def open(self, rel: str) -> _Disk:
        return _Disk(self.path)

    def candidates(self) -> list[str]:
        return [self.path.name]


class _Zip:
    """A ZIP game, read in place: members are listed and read at offsets, never unpacked. Members with unsafe names are not there."""

    def __init__(self, path):
        self.zf = zipfile.ZipFile(path)
        try:
            self._list(self.zf.infolist())
        except BaseException:
            self.zf.close()
            raise

    def _list(self, infos: list[zipfile.ZipInfo]) -> None:
        if len(infos) > MAX_ENTRIES:
            raise zipfile.BadZipFile("too many members")
        self.comment = self.zf.comment
        self.budget = [_Member.BUDGET]
        self.files: dict[str, zipfile.ZipInfo] = {}
        self.tree: dict = {}  # name -> [is a folder, is a file, what it holds (the same)]: a folder costs what its name does, however deep it sits
        for info in infos:
            # A member the app could not unpack is not there: one that is encrypted or neither stored nor deflated (its zip library has no more), and one
            # whose name has a NUL (`orig_filename` keeps what `zipfile` cuts at it), is over 1024 bytes, is more than 64 parts deep or names a device.
            name = info.orig_filename
            if info.flag_bits & 1 or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) or "\0" in name or len(name.encode("utf-8", "replace")) > MAX_NAME:
                continue
            parts = name.replace("\\", "/").split("/")  # a backslash separates, as it does where the app unpacks the game
            is_dir = parts[-1] in ("", ".")
            if is_dir:
                parts.pop()
            if len(parts) > MAX_DEPTH or any(p in ("", "..") or device(p) for p in parts):
                continue
            parts = [p for p in parts if p != "."]  # `./Game.bat` is `Game.bat`, as unpacked
            if not parts:
                continue
            is_file = not is_dir and not (info.create_system == 3 and stat.S_ISLNK(info.external_attr >> 16))
            if is_file:
                self.files["/".join(parts)] = info
            folder = self.tree
            for k, part in enumerate(parts):
                here = folder.setdefault(part, [False, False, {}])
                if k < len(parts) - 1 or is_dir:
                    here[0] = True
                elif is_file:
                    here[1] = True
                folder = here[2]
        self.prefix = ""
        while True:
            items = [(n, d) for n, d, _ in self.scan("", self.prefix) if n not in JUNK_FOLDERS]
            if len(items) != 1 or not items[0][1]:
                break
            self.prefix += items[0][0] + "/"

    def scan(self, rel: str, prefix: str | None = None) -> list[tuple[str, bool, bool]]:
        folder = self.tree
        for part in ((self.prefix if prefix is None else prefix) + rel).split("/"):
            if part:
                folder = folder.get(part, (0, 0, {}))[2]
        return [(n, d, f) for n, (d, f, _) in folder.items()]

    def is_file(self, rel: str, max_size: int | None = None) -> bool:
        info = self.files.get(self.prefix + rel)
        return info is not None and (max_size is None or info.file_size <= max_size)

    def open(self, rel: str) -> _Disk:
        return _Member(self.zf, self.files[self.prefix + rel], self.budget)

    def candidates(self) -> list[str]:
        return _candidates(self.scan)

    def close(self) -> None:
        self.zf.close()


def _open(path: Path):
    if path.is_dir():
        return _Dir(path)
    if not path.is_file():
        raise SystemExit(f"{path}: no such file or folder")
    ext = path.suffix.lower()
    if ext == ".zip":
        try:
            return _Zip(path)
        except Exception:  # a ZIP that cannot be opened says nothing
            return None
    if ext in RUNNABLE:
        return _Lone(path)
    raise SystemExit(f"{path}: not a game (a folder, a .zip, or one .exe, .bat or .cmd)")


# ---- reading ---------------------------------------------------------------------------------------------------------------------------


def _card_file(game) -> dict | None:
    if not game.is_file(CARD_FILE):  # what a ZIP's header says its size is does not matter: no more than 16 KiB and a byte is read, and that is too much
        return None
    raw = parse_card(_slurp(game, CARD_FILE, MAX_CARD + 1))
    return check_card(raw, game) if raw is not None else None


def _comment_card(comment: bytes) -> dict | None:
    m = re.fullmatch(rb"\s*redengine-game\s+(.*)", comment, re.S)
    return parse_card(m.group(1).strip()) if m else None


def _comment(game) -> dict | None:
    raw = _comment_card(game.comment)
    return check_card(raw, game) if raw is not None else None


def zip_comment(path) -> dict | None:
    """The card in the comment of the ZIP at `path`, as written (`read` checks it against the game), or None. Unpacking a ZIP loses its comment, so a
    tool that unpacks one reads this first and hands it to `read`, as the app does (`meta::zip_comment`)."""
    try:
        with zipfile.ZipFile(path) as z:
            return _comment_card(z.comment)
    except Exception:  # a ZIP that cannot be opened says nothing
        return None


def _starts(game, found: dict, lone: str | None = None) -> list[str]:
    """The files that start the game: `engine.name`, else the card's `entry`, else the one candidate, else every candidate in name order. `lone` is a
    program given as the game itself: it is the one when nothing else could be (a name like `Install_And_Play.bat` is a candidate only on its own)."""
    if game.is_file("engine.name", 1024):
        try:
            own = safe_path(_slurp(game, "engine.name", 1024).decode("utf-8").strip(_WHITE))
        except UnicodeDecodeError:
            own = None
        if own and own.lower().endswith(RUNNABLE) and game.is_file(own):
            return [own]
    entry = (found.get("card") or {}).get("entry") or (found.get("zip") or {}).get("entry")
    return [entry] if entry else game.candidates() or ([lone] if lone and game.is_file(lone) else [])


def _guard(fn, *args):
    try:
        return fn(*args)
    except Exception:  # whatever is wrong with a hostile game is left out, never raised
        return None


def _merge_into(found: dict, source: str, card: dict | None) -> None:
    for key, value in (card or {}).items():
        found.setdefault(source, {}).setdefault(key, value)


def _script_card(game, rel: str) -> dict | None:
    raw = _header(_slurp(game, rel, HEADER_BYTES))
    return check_card(raw, game) if raw else None


def _record_card(game, f) -> dict | None:
    record = _record(f)
    raw = parse_card(record) if record else None
    return check_card(raw, game) if raw is not None else None


def _look_into(game, rel: str, found: dict) -> None:
    """Add what the program `rel` says (its record, its version information) to `found`; each part is looked at on its own."""
    with game.open(rel) as f:
        _merge_into(found, "exe", _guard(_record_card, game, f))
        _merge_into(found, "program", _guard(_program, f))


def read(path, fork: bool = False, lone: str | None = None, comment: dict | None = None) -> dict:
    """What the game at `path` (a ZIP, a folder, or one .exe, .bat or .cmd) says about itself: {"card": {field: value}, "from": {field: source}}.
    The fields come from the card file (`card`), the ZIP comment (`zip`), the script header (`bat`), the program's record (`exe`) and its version
    information (`program`), the first of these to have a field winning it. A fork (`fork`, or a card file or ZIP comment that says `forked_from`) has
    no description, designer, online note or notes of its own in a script or program: those were its parent's. `lone` names a program of a folder that
    is the game itself, whatever it is called. `comment` is the card in the comment of the ZIP a folder was unpacked from (`zip_comment`)."""
    game = _open(Path(path))
    found: dict[str, dict] = {}
    if game is not None:
        try:
            _merge_into(found, "card", _guard(_card_file, game))
            _merge_into(found, "zip", _guard(_comment, game) if comment is None else _guard(check_card, comment, game))
            fork = fork or any("forked_from" in found.get(source, {}) for source in ("card", "zip"))
            for rel in (_guard(_starts, game, found, lone) or [])[:MAX_STARTS]:
                if rel.lower().endswith((".bat", ".cmd")):
                    _merge_into(found, "bat", _guard(_script_card, game, rel))
                elif rel.lower().endswith(".exe"):
                    _guard(_look_into, game, rel, found)
        finally:
            game.close()
        for source in ("bat", "exe", "program") if fork else ():
            for key in PARENTS_WORDS:
                found.get(source, {}).pop(key, None)
    card: dict = {}
    origin: dict = {}
    for field in FIELDS:
        for source in SOURCES:
            if field in found.get(source, {}):
                card[field], origin[field] = found[source][field], source
                break
    return {"card": card, "from": origin}


# ---- writing ---------------------------------------------------------------------------------------------------------------------------


def _pretty(card: dict) -> str:
    return json.dumps({"schema": 1, **card}, indent=2, ensure_ascii=False) + "\n"


def _no_room(text: str | bytes) -> None:
    """A reader ignores a card of more than 16 KiB whole, so a card that long is never written."""
    if len(text if isinstance(text, bytes) else text.encode("utf-8")) > MAX_CARD:
        raise SystemExit("the card is larger than 16 KiB, which a reader would ignore whole: shorten the description, the online note, the arguments or the paths")


def card_text(card: dict) -> str:
    """The card as `redengine-game.json` holds it: pretty, `schema` first."""
    text = _pretty(card)
    _no_room(text)
    return text


def card_comment(card: dict) -> bytes:
    """The card as a ZIP's comment: `redengine-game ` and the JSON on one line."""
    comment = COMMENT + b" " + json.dumps({"schema": 1, **card}, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    _no_room(comment)
    return comment


def fit(card: dict) -> dict:
    """`card` cut to what a reader takes, for a publisher that must go on: while its file would be over 16 KiB (only with fields of the longest, in
    4-byte characters), the arguments (`launch.args` has them), the online note, the description and the screenshot go, in that order."""
    card = dict(card)
    for key in ("args", "online", "description", "thumb"):
        if len(_pretty(card).encode("utf-8")) <= MAX_CARD:
            break
        card.pop(key, None)
    return card


def _atomic(path: Path, write) -> None:
    """Write a file beside `path`, then put it in place of `path` (which keeps its permissions); a link at `path` is replaced, never written through."""
    tmp = path.with_name(path.name + ".stamping")
    try:
        tmp.unlink(missing_ok=True)  # what a stamp that was cut short left; a link is removed, never followed
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        with os.fdopen(os.open(tmp, flags, 0o666), "wb") as out:  # new, so nothing a hostile folder put there is written through
            write(out)
        if path.exists():
            shutil.copymode(path, tmp)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


class _Plus:
    """A game and the files about to be added to it."""

    def __init__(self, game, extra: tuple[str, ...]):
        self.game, self.extra = game, extra

    def is_file(self, rel: str, max_size: int | None = None) -> bool:
        return rel in self.extra or self.game.is_file(rel, max_size)


def _merge(existing: dict, fields: dict, game=None) -> dict:
    """`existing` with `fields` laid over it; a field given but unusable is an error, one given empty is removed. `game` (None: not asked) must hold the files named."""
    given = {k: v for k, v in fields.items() if v is not None}
    if "kind" in given:
        given.setdefault("presentation", given.pop("kind"))
    unknown = set(given) - set(FIELDS)
    if unknown:
        raise SystemExit(f"not a card field: {', '.join(sorted(unknown))}")
    new = check_card(given, None)
    gone = set()
    for key, value in given.items():
        if key in new:
            continue
        if value == [] or (isinstance(value, str) and not clean(value)):
            gone.add(key)
        else:
            hint = {"presentation": "2d, 3d or hybrid", "author": "ai or human", "forked_from": "a game's slug and a version of 1 or more",
                    "entry": "a path inside the game ending .exe, .bat or .cmd", "thumb": "a .png or .jpg path inside the game",
                    "online": "a note on how it is played online, never an address or a join key"}.get(key, "text")
            raise SystemExit(f"{key}: {value!r} cannot be used (it takes {hint})")
    for key, limit in LIMITS.items():
        if isinstance(given.get(key), str) and len(clean(given[key])) > limit:
            print(f"note: {key} is cut to {limit} characters", file=sys.stderr)
    card = {k: v for k, v in {**existing, **new}.items() if k not in gone}
    if game is not None:
        kept = check_card(card, game)
        for key in ("entry", "thumb"):
            if key in new and key not in kept:
                raise SystemExit(f"{key}: {new[key]!r} is not a {'program or script' if key == 'entry' else 'picture'} inside the game")
        card = kept
    return {k: card[k] for k in FIELDS if k in card}


def _picture(thumb: Path) -> str:
    """The name a screenshot gets inside a game (after checking it)."""
    ext = thumb.suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg"):
        raise SystemExit(f"{thumb}: a screenshot is a .png or .jpg")
    if not thumb.is_file() or thumb.stat().st_size > MAX_THUMB:
        raise SystemExit(f"{thumb}: not a picture file of 5 MB or less")
    return THUMB_STEM + (".jpg" if ext == ".jpeg" else ext)


def _existing(game) -> dict:
    """The card a game already has in its file and its ZIP comment, as far as it goes."""
    out: dict = {}
    for read_one in (_card_file, _comment):
        out = {**(_guard(read_one, game) or {}), **out}
    return out


def _stamp_folder(path: Path, fields: dict, thumb: Path | None) -> dict:
    game = _Dir(path)
    name = _picture(thumb) if thumb else None
    card = _merge(_existing(game), {**fields, **({"thumb": name} if name else {})}, _Plus(game, (name,) if name else ()))
    text = card_text(card).encode("utf-8")
    if thumb:
        _atomic(game.root / name, lambda out: out.write(thumb.read_bytes()))
        for other in {THUMB_STEM + ext for ext in (".png", ".jpg")} - {name}:  # the other kind of picture would be dead weight
            (game.root / other).unlink(missing_ok=True)
    _atomic(game.root / CARD_FILE, lambda out: out.write(text))
    return card


def _stamp_zip(path: Path, fields: dict, thumb: Path | None) -> dict:
    try:
        zin = _Zip(path)
    except (zipfile.BadZipFile, OSError, ValueError) as e:
        raise SystemExit(f"{path}: not a ZIP archive that can be rewritten ({e})")
    with zin.zf:
        name = _picture(thumb) if thumb else None
        card = _merge(_existing(zin), {**fields, **({"thumb": name} if name else {})}, _Plus(zin, (name,) if name else ()))
        text, comment = card_text(card).encode("utf-8"), card_comment(card)
        if zin.comment.strip() and not re.match(rb"\s*redengine-game\s", zin.comment):
            print("note: the ZIP's comment is replaced by the card", file=sys.stderr)
        replaced = {zin.prefix + CARD_FILE} | ({zin.prefix + THUMB_STEM + ext for ext in (".png", ".jpg")} if name else set())  # the other kind of picture too
        plain = zipfile.ZipInfo(zin.prefix + CARD_FILE, (1980, 1, 1, 0, 0, 0))
        plain.external_attr = 0o100644 << 16

        def rewrite(out) -> None:
            with zipfile.ZipFile(out, "w") as zout:
                for info in zin.zf.infolist():
                    if info.filename in replaced:
                        continue
                    if info.flag_bits & 1:
                        raise SystemExit(f"{path.name}: has encrypted members, which cannot be rewritten")
                    copy = zipfile.ZipInfo(info.filename, info.date_time)
                    copy.compress_type, copy.external_attr, copy.create_system, copy.comment = info.compress_type, info.external_attr, info.create_system, info.comment
                    if info.is_dir():
                        zout.writestr(copy, b"")
                        continue
                    copy.file_size = info.file_size
                    with zin.zf.open(info) as src, zout.open(copy, "w") as dst:
                        shutil.copyfileobj(src, dst, 1 << 20)
                if thumb:
                    zout.write(thumb, zin.prefix + name, compress_type=zipfile.ZIP_STORED)
                zout.writestr(plain, text, zipfile.ZIP_DEFLATED)
                zout.comment = comment

        _atomic(path, rewrite)
    return card


def _stamp_script(path: Path, fields: dict, thumb: Path | None) -> dict:
    if thumb or fields.get("forked_from") is not None:
        raise SystemExit("a script header holds no screenshot and no forked_from: stamp the folder or ZIP the game ships in, or the program's .exe")
    data = path.read_bytes()
    if len(data) > 16 << 20:
        raise SystemExit(f"{path.name}: too large to be a script")
    if data[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\0" in data[:1024]:
        raise SystemExit(f"{path.name}: is not a plain-text script (UTF-16?): save it as ANSI or UTF-8, or stamp the folder or ZIP it ships in")
    bom = b"\xef\xbb\xbf" if data.startswith(b"\xef\xbb\xbf") else b""
    lines = data[len(bom):].split(b"\n")
    stripped = [x[:-1] if x.endswith(b"\r") else x for x in lines]
    found = _block(stripped)
    card = _merge(check_card(found[2], None) if found else {}, fields)
    # `@REM` lines: the `@` keeps cmd from echoing them, so the script prints exactly what it printed before.
    block = ["@REM redengine-game"]
    for key in FIELDS:
        value = card.get(key)
        for item in [] if value is None or key == "forked_from" else value if isinstance(value, list) else [value]:
            bad = [c for c in CMD_SPECIAL if c in item]
            if bad:
                raise SystemExit(f"{key}: a script header cannot hold {bad[0]!r} (cmd would read it as part of a command); rephrase it, or stamp the game's folder or ZIP")
            block.append(f"@REM {key}: {item}")
    if found:
        del lines[found[0]:found[1]]
        del stripped[found[0]:found[1]]
    at = 1 if stripped and stripped[0].strip().lower() == b"@echo off" else 0  # where the spec's example has it: after `@echo off`
    if at < len(stripped) and _COMMENT_LINE.fullmatch(stripped[at]):  # the line after the block must not look like part of it
        block.append("")
    new = bom + b"\n".join(lines[:at] + [x.encode("utf-8") + b"\r" for x in block] + (lines[at:] or [b""]))
    _atomic(path, lambda out: out.write(new))
    return card


def _stamp_program(path: Path, fields: dict, thumb: Path | None) -> dict:
    if thumb:
        raise SystemExit("a program cannot hold a screenshot: stamp the folder or ZIP it ships in")
    with _Disk(path) as f:
        length = _record_length(f)
        end = f.size - 12 - length if length is not None else f.size
        existing = {}
        if length is not None:
            raw = parse_card(_record(f) or b"")
            existing = check_card(raw, None) if raw else {}
        pe = _pe(f)
    if pe is None:
        raise SystemExit(f"{path.name}: not a Windows program (it has no PE headers), so a record cannot be added")
    if len(pe["dirs"]) > 4 and any(pe["dirs"][4]):
        raise SystemExit(f"{path.name} is signed: a record would break its signature; stamp the folder or ZIP it ships in instead (the card file does the same job)")
    if end < pe["end"]:
        raise SystemExit(f"{path.name} ends before its last section (it is cut short), so a record cannot be added")
    if end > pe["end"]:
        raise SystemExit(f"{path.name} has data after its last section (an installer, a self-extracting archive or a signature), so a record cannot be added; "
                         "stamp the folder or ZIP it ships in instead")
    card = _merge(existing, fields)
    if card.pop("notes", None) and fields.get("notes"):  # what changed in this build would outlive it in the program, and be read as the next build's
        print("note: a program's record does not keep notes: put them in the folder's or ZIP's card, or a script's header", file=sys.stderr)
    record = json.dumps({"schema": 1, **card}, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(record) > MAX_CARD:
        raise SystemExit("the card is larger than 16 KiB")

    def write(out) -> None:
        with open(path, "rb") as src:
            remaining = end
            while remaining:
                chunk = src.read(min(remaining, 1 << 20))
                if not chunk:
                    raise SystemExit(f"{path.name} changed while it was being read")
                out.write(chunk)
                remaining -= len(chunk)
        out.write(record + struct.pack("<I", len(record)) + MAGIC)

    _atomic(path, write)
    return card


def stamp(path, fields: dict, thumb=None) -> dict:
    """Write the card made of `fields` (card fields; None leaves one alone, empty removes it) into the game at `path`, over the card it already has:
    a folder gets `redengine-game.json`, a ZIP that and its comment, a `.bat`/`.cmd` a header block, an `.exe` a record. Returns the card written."""
    path = Path(path)
    thumb = Path(thumb) if thumb else None
    if path.is_dir():
        return _stamp_folder(path, fields, thumb)
    if not path.is_file():
        raise SystemExit(f"{path}: no such file or folder")
    ext = path.suffix.lower()
    if ext == ".zip":
        return _stamp_zip(path, fields, thumb)
    if ext in (".bat", ".cmd"):
        return _stamp_script(path, fields, thumb)
    if ext == ".exe":
        return _stamp_program(path, fields, thumb)
    raise SystemExit(f"{path}: not a game (a folder, a .zip, or one .exe, .bat or .cmd)")


# ---- the command line ------------------------------------------------------------------------------------------------------------------


def _forked_from(text: str) -> dict:
    parent, _, version = text.partition("@")
    if not SLUG.fullmatch(parent) or not version.lstrip("v").isdigit() or int(version.lstrip("v")) < 1:
        raise argparse.ArgumentTypeError("SLUG@N, the game and the version it was forked from")
    return {"slug": parent, "version": int(version.lstrip("v"))}


def glue_dashed(argv: list[str], parsers: list, *options: str) -> list[str]:
    """`argv` with `--args --fullscreen` made `--args=--fullscreen`: argparse takes a value that starts with dashes only joined with `=`, and most arguments a
    game starts with are like that. Only when the word after `options` is no option of any of `parsers`."""
    known = {opt for p in parsers for action in p._actions for opt in action.option_strings}
    out: list[str] = []
    for arg in argv:
        if out and out[-1] in options and arg.startswith("-") and len(arg) > 1 and arg.split("=")[0] not in known:
            out[-1] += "=" + arg
        else:
            out.append(arg)
    return out


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("show", help="what a game says about itself")
    p.add_argument("path", type=Path, help="a .zip, a folder, or one .exe, .bat or .cmd")
    p.add_argument("--json", action="store_true", help="the machine form: {\"card\": {...}, \"from\": {...}}")
    p = sub.add_parser("stamp", help="write the card into a game (what is not given stays as it is)")
    p.add_argument("path", type=Path, help="a .zip, a folder, or one .exe, .bat or .cmd")
    p.add_argument("--name", help="the game's name as players see it")
    p.add_argument("--description", help="one or two sentences for the website and the app")
    p.add_argument("--kind", "--presentation", dest="presentation", choices=KINDS, help="2d, 3d or hybrid")
    p.add_argument("--author", choices=AUTHORS, help="who designed it")
    p.add_argument("--online", help="a note shown when it has online multiplayer (never an address or a join key)")
    p.add_argument("--entry", help="what starts the game, a path inside it (.exe, .bat or .cmd)")
    p.add_argument("--args", action="append", help="an argument to start it with (repeatable; `--args --fullscreen` works as `--args=--fullscreen`)")
    p.add_argument("--notes", action="append", help="a line of \"what changed in this build\" (repeatable)")
    p.add_argument("--forked-from", type=_forked_from, help="SLUG@N: the game and version this one was made from")
    p.add_argument("--thumb", type=Path, help="a screenshot (.png or .jpg) to put in the game (a folder or ZIP)")
    a = ap.parse_args(glue_dashed(sys.argv[1:] if argv is None else list(argv), [ap, *sub.choices.values()], "--args", "--notes"))
    try:
        if a.cmd == "show":
            found = read(a.path)
            if a.json:
                print(json.dumps(found, indent=2))
            elif not found["card"]:
                print(f"{a.path}: says nothing about itself")
            else:
                print(a.path)
                for key, value in found["card"].items():
                    print(f"  {key:13}{value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)}   ({LABELS[found['from'][key]]})")
            return 0
        fields = {k: getattr(a, k) for k in ("name", "description", "presentation", "author", "online", "entry", "args", "notes")}
        fields["forked_from"] = a.forked_from
        if all(v is None for v in fields.values()) and not a.thumb:
            raise SystemExit("nothing to stamp: give --name, --description, --kind, --author, --online, --entry, --args, --notes, --forked-from or --thumb")
        card = stamp(a.path, fields, a.thumb)
        print(f"stamped {a.path}: " + ", ".join(f"{k} = {v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)}" for k, v in card.items()))
        return 0
    except OSError as e:
        raise SystemExit(f"{a.path}: {e.strerror or e}")


if __name__ == "__main__":
    sys.exit(main())
