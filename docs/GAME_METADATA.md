# The game card: a game that describes itself

A ready-made game dropped on the RedEngine Games app (or given to `distribution/upload_game.py`) can carry its own description, so the person
publishing it types nothing: the app reads what the game says about itself and asks only about what is missing. The description is called the
**card**. It is data inside the game, in the place that suits each kind of file, and it travels with the game: a published ZIP carries it, the
installed copy carries it, and a game made from it by Fork… starts from it.

This page is the contract. `launcher/core/src/meta.rs` (the app) and `distribution/game_meta.py` (the command line) implement it separately,
and both read the same fixtures in `distribution/testdata/game_meta/` (`expected.json` says what each must find; `build_fixtures.py` writes
them). `cargo run -p redengine-games-core --example card -- <path>` prints the app's answer, `game_meta.py show --json` the tool's.

**What a game can be:** a ZIP, a folder, or one `.exe`, `.bat` or `.cmd`. Other archives (7z, RAR, `.tar.gz`) are not opened: the window copies
such a file as it is and finds nothing to start, and the tools refuse it. Repack the game as a ZIP.

## The card

A JSON object. Every field is optional; unknown fields are ignored.

| Field | Type | What it is |
|---|---|---|
| `schema` | `1` | The card's version. Written always; a reader accepts it missing, and reads the fields it knows when it is higher. |
| `name` | string, 60 | The game's name as players see it. |
| `description` | string, 400 | One or two sentences for the website and the app. |
| `presentation` | `"2d"` `"3d"` `"hybrid"` | How it looks. `kind` is read as a synonym. |
| `author` | `"ai"` `"human"` | Who designed it. |
| `online` | string, 200 | A note when it has online multiplayer. Never an address or a join key (see below). |
| `entry` | string | What starts the game: a path inside the game, `/`-separated, ending `.exe`, `.bat` or `.cmd`. |
| `args` | array of up to 16 strings, 200 each | What to start `entry` with. They are for the card's own `entry` only, never for another program the poster picks. |
| `thumb` | string | A screenshot inside the game: a `.png` or `.jpg` path, `/`-separated, a file of at most 5 MiB. |
| `notes` | array of up to 10 strings, 200 each | What changed in **this build**. Read to fill in "what changed"; never written into a published card or an `.exe` record. |
| `forked_from` | `{"slug": "snake", "version": 3}` | The game and version it was made from (as `fork.json`, which wins when both say). |

Cleaning, the same everywhere: a string loses control characters and the Unicode direction overrides (U+202A to U+202E, U+2066 to U+2069),
runs of Unicode white space become one space, the ends are trimmed, and a string longer than its limit is cut in characters (never refused). A
string or list item that is empty once cleaned is not there.

A field is **ignored** (simply not found) when it has the wrong type, a list holds anything but strings, `presentation` or `author` is not one of
its words, or:

- `entry` or `thumb` is over 260 characters, has a backslash, a colon, a NUL, an empty, `.` or `..` part, or a part Windows takes for a device
  (`CON`, `PRN`, `AUX`, `NUL`, `CONIN$`, `CONOUT$`, `COM1`-`COM9`, `LPT1`-`LPT9`, with any extension or trailing spaces), does not
  end with one of its endings (`.exe`, `.bat`, `.cmd`; `.png`, `.jpg`; any case), or names no regular file in the game; `thumb` also when the file is over 5 MiB.
- `online` looks like a place or a key: a word that is a URL, `www.`…, an IPv4 or IPv6 address, `name:port`, or a name ending in a well-known
  domain (`.com`, `.net`, `.org`, `.io`, `.gg` and a few more), or the note holds `key=`, `token=`, `password=`, `pass=` or `secret=`. The
  window, `upload_game.py --online` and `stamp` refuse such a note instead.
- `forked_from` has a slug that is not lower-case letters, digits and single hyphens, is over 64 characters, or a version under 1. A card that
  says a game is a fork of itself (its slug is the game's own) is not telling a lineage, and the app and `upload_game.py` drop it.

A card is ignored whole when it is over 16 KiB, is not UTF-8 (a leading byte order mark is allowed), is not a JSON object, is nested more than
127 deep (the object itself is the first level), or holds `NaN`, a lone surrogate or a number that does not fit a 64-bit float.

`maintainer` is not a card field: who publishes a game is the GitHub account of the token that published it, never what a file says.

## Where the card lives

| The game is | The card is | Format |
|---|---|---|
| a ZIP or a folder | `redengine-game.json` at its root (inside the one top folder, however deep, when it holds a single folder and at most `__MACOSX` and `.DS_Store` beside it) | the JSON object |
| a ZIP | also the archive comment | `redengine-game`, white space, then the JSON object on one line |
| a `.bat` or `.cmd` | a header block in the script | see below |
| an `.exe` | a record after the program's last byte | see below |
| an `.exe` made by someone else | the Windows version information it already has | `ProductName` is the `name`; `Comments`, else `FileDescription`, is the `description` |

White space in the ZIP comment and in a header block is ASCII only: space, tab, line ends, vertical tab and form feed.

**A ZIP is read as the app unpacks it.** A member is not there when its name is over 1024 bytes or 64 parts (a backslash separates parts too),
has an empty or `..` part, a NUL, a root or a drive, or names a device, and when it is encrypted or compressed other than stored or deflated. A
link in a ZIP is an empty folder, never a file. (Staging a dropped ZIP refuses the whole archive for such a member; reading it for its card only
leaves the member out.) A ZIP of more than 200 000 members says nothing. The app looks inside by unpacking into a new temporary folder (at
most 512 MiB written); the tool reads members in place, never opens a compressed member that declares more than 64 MiB, and decompresses at
most 256 MiB for the whole ZIP.

**Header block** in a `.bat` or `.cmd`: within the first 64 lines (lines end at LF, a CR before it is dropped; after an optional UTF-8 byte order
mark; at most 64 KiB read), a comment line whose text is `redengine-game` starts the block. A comment line is `REM` or `@REM` (in any case)
followed by a space, a tab or the line's end, or `::`, after any spaces and tabs. The comment lines right after it, `key: value` each, are the
card: the key is what comes before the first `:`, both sides trimmed. Keys are `name`, `description`, `presentation` (or `kind`), `author`,
`online`, `entry`, `thumb`, and the repeatable `notes` and `args` (each line adds one); a line with another key or no `:` is skipped. The first
line that is not a comment line (a blank line too) ends the block. The text is read as UTF-8.

```bat
@echo off
@REM redengine-game
@REM name: Text Quest
@REM description: A tiny text adventure about a lost key.
@REM presentation: 2d
@REM author: ai
@REM notes: First release.
echo Welcome...
```

The tool writes `@REM` lines (so the script prints exactly what it printed before) with CRLF ends, right after a first line `@echo off` or else at
the top, replacing the block it finds. It refuses a value holding `^ % & | < >` (cmd would read it as part of a command), a UTF-16 script, a
screenshot and `forked_from` (a script cannot hold them: stamp the folder or ZIP).

**Record** in an `.exe`: after the last byte of the program, the card as UTF-8 JSON on one line, then its length as 4 bytes little-endian, then
the 8 bytes `REDGAME1`. A reader looks at the last 12 bytes: the magic, then the length (which must fit in the file and in 16 KiB). When the
program was signed after it was stamped, the record sits just before the certificate table: when the last 12 bytes are no record and the program
has a certificate table, a reader looks for one ending where the table starts, or up to 7 bytes before (the table starts on a multiple of 8).
Windows runs the program as before, because it ignores what follows the last section. The tool never writes `notes` into a record (and says
so): what changed in one build would outlive it in the program and be read as the next build's.

The program's last byte is the last of: the end of its headers, the end of each section's data in the file, and, when the headers point to a COFF
symbol table (gcc and MinGW leave one), the end of its string table (a size of at least 4 that fits in the file; a claim that reaches outside is
none). The tool refuses to add a record to a file that is not a Windows program, is signed, ends before that byte (cut short), or has data after
it (an installer, a self-extracting archive, a signature); it replaces its own record when it finds one, and refuses a record over 16 KiB.

**A Windows program**, for the record and the version information alike: `MZ`, a PE header offset of at least 64, `PE\0\0` there, 1 to 96
sections, an optional header of at least 64 bytes whose magic is PE32 (`0x10B`) or PE32+ (`0x20B`) and that is long enough to hold its data
directories (at most 16 are read), and a section table inside the file. Anything else is not a Windows program, and says nothing.

**Version information** is read from the program's `VS_VERSION_INFO` resource (`RT_VERSION`, 16; its first name and first language). A resource
directory of more than 4096 entries or reaching past the resources, a version resource under 6 bytes or over 64 KiB or outside one section, and
a tree of any other shape read as nothing. Only the first string table counts; of a key that appears twice the first wins, and a key over 64
UTF-16 units ends the table. `ProductName`, `Comments` and `FileDescription` are read; these values are ignored: empty, `application`, `game`,
`app` (in any case), and a `FileDescription` equal to the whole `ProductName` (ignoring case, before either is cut). It is the lowest-ranked
source and only read for the program that starts the game.

## What the reader does

`read(path)` answers `{"card": {field: value}, "from": {field: source}}` where a source is `card` (the file), `zip` (the comment), `bat`, `exe`
(the record) or `program` (the version information). When a game has several, the field-by-field winner is, from first to last:
`card`, `zip`, `bat`, `exe`, `program`.

The `bat`, `exe` and `program` sources come from the file that starts the game, chosen in this order:

1. `engine.name`: a file of at most 1024 bytes, UTF-8, trimmed, naming a `.exe`, `.bat` or `.cmd` in the game by the rules of `entry`;
2. else the card's `entry` (from the card file or the ZIP comment);
3. else the **candidates**, each in name order (at most 16), the first to carry a field winning it: the files of the top folder whose names end
   `.exe`, `.bat` or `.cmd` in any case (a file called just `.bat` too), or those one folder down when the top holds none, leaving out names that
   start (in ASCII, any case) with `unins`, `setup`, `install`, `vc_redist`, `vcredist`, `dxsetup`, `unitycrashhandler`, `crashpad_handler` or
   `notification_helper`. A program dropped or given alone is the game whatever it is called (`Install_And_Play.bat`).

A **fork** (it has a `fork.json` naming its parent, or its card file or ZIP comment says `forked_from`) takes `description`, `author`, `online`
and `notes` only from its card file and ZIP comment, never from a script or a program: those were its parent's.

A reader never runs anything, never opens the network, never follows a link (a symbolic link or a junction is not a file of the game; only the one
file a person names is read through one), and reads at most: one card file (16 KiB and a byte), `engine.name` (1024 bytes), the first 64 lines
of a script (64 KiB), and a program's headers, last 12 bytes and resources (no read over 128 KiB). Whatever is hostile in a game is left out of
the answer, never an error.

## What the window does with it

The form starts from what the site already says about a game of that name (an update keeps its description, 2D/3D, designer and online note),
else the card of the copy of that name in the library, else the defaults. Then what the game says goes over it, except a description read only
from version information, which never replaces words the site or the library has.

- **Name:** the card's, unless it has no letters or digits (`星の旅` makes no id) or is the parent's name (a fork made before cards existed has
  its parent's card); then a fork's own name from `fork.json`; else the dropped file's name.
- **What starts it:** `engine.name`, else the card's `entry`, else the one candidate; with several, the poster picks.
- **Screenshot:** a picture dropped with the game wins over the card's `thumb`.

A field filled from the game is marked **from the game**; the mark's tooltip says where it was read (the game's card, the ZIP's comment, the
script's header, the program's record, the program's file information), it goes when the poster changes the field and comes back if they put
the game's words back. One line under the title says what was read ("Read from the game: name, description."). When the name (a name read
from a game can be anybody's) is a game on the site kept by somebody else, the note says so and the button reads "Publish as @them's version
N". With a name and something to start, the poster can publish without typing anything.

## What travels

On **Add to my games** and **Publish for everyone** the app writes the card, as the poster left it after the form, into the game's folder
before it is installed or zipped: `redengine-game.json` (pretty, `schema` 1, without `notes`). The published ZIP also carries it as its comment.
When the poster keeps the program the game started with, the card keeps its `args` (and they go into `launch.args`), or, when it had none,
takes the game's own `launch.args`; for another program it gets none. A card that would be over 16 KiB (only with fields of the longest, in
4-byte characters) loses its `args` (`launch.args` has them), then `online`, then `description`, then `thumb`, until it fits.

A dropped screenshot is copied into the folder as `redengine-game-thumb.png` or `.jpg` (the other kind is removed) and named by `thumb`. One over
5 MiB is uploaded as the release's screenshot but not copied into the game, and the card names none. With no screenshot dropped, the card's own
`thumb` stays and is uploaded as the release's screenshot. So the published ZIP, the installed game and a fork all carry the card, and dropping
that ZIP again fills in the form completely.

**Fork…** writes the fork's card: its own `name`, `forked_from`, and the parent's `presentation` (from the parent's card, else the site's
record); the parent's description, author, screenshot and notes are dropped, because the fork is somebody else's game. Its `FORK.md` asks the
player (or their AI) to keep the card and to give it a `description` and an `author`.

The app never edits a game's own files (programs and scripts): it adds `redengine-game.json` and the screenshot beside them. Putting the card
inside a program or a script is the creator's choice, made with the tool:

```text
python3 distribution/game_meta.py show Game.zip                       what the game says about itself (--json for the machine form)
python3 distribution/game_meta.py stamp Quest.bat --name "Text Quest" --description "A tiny text adventure." --kind 2d --author ai
python3 distribution/game_meta.py stamp Game.exe  --name "Star Miner" --description "Mine asteroids, dodge pirates."
python3 distribution/game_meta.py stamp Game.zip  --name "Star Miner" --thumb shot.png     card file + comment (rewrites the ZIP)
python3 distribution/game_meta.py stamp ./MyGame/ --name "Star Miner"                       writes redengine-game.json
```

`stamp` keeps what a game already says and changes only what it is given (an empty value removes a field). It refuses a value a reader would
ignore (with what the field takes), an `entry` or `thumb` that is not in the game, a screenshot over 5 MiB, and a card over 16 KiB, which a reader
would ignore whole (the app and `upload_game.py` cut such a card instead). It replaces a ZIP's other comment (and says so) and refuses a ZIP
with encrypted members.

`upload_game.py` reads the same card (a ZIP's comment too, read before the ZIP is unpacked): `--name` is only needed when the game does not say
its name. Each field comes from the flag, else the card,
else the game's previous release, else the default; the card's `entry` and `args` start the game when `--run` and `--args` are absent
(`engine.name` still wins), and its `notes` are "what changed" when there is no `--notes`. It writes the card (without notes) into the ZIP it
publishes, as the file and as the comment, under the same rules as the app, a `--thumb` over 5 MiB included.

## Left open

- A script header saved in a Windows code page (cp1252) rather than UTF-8: its non-ASCII letters read as U+FFFD.
- When several candidates start a game and none is chosen, the fields can come from different programs (the name from one, the description from
  another).
- A damaged or lying ZIP (local headers that disagree with its directory, a broken member) can read differently in the app, which unpacks it with
  the `zip` crate, and in the tool, which reads it with Python's `zipfile`.
