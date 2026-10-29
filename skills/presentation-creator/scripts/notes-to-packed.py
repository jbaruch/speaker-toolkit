#!/usr/bin/env python3
"""Turn a 0-based speaker-notes JSON map into the notes driver's input.

Input JSON: `{"<0-based slide #>": "notes text", ...}` — the historical
inject-speaker-notes.py format. Slide numbers are converted 0-based -> 1-based
(python-pptx uses 0-based indices; PowerPoint uses 1-based). Empty notes are
dropped.

Two output formats:

- Packed (default): a UTF-8 file of records `<1-based #>US<text>` joined by RS,
  where US=Chr(31), RS=Chr(30). This is the SetSpeakerNotes VBA macro's wire
  format, kept for that macro.
- Driver arguments (`--driver-args --deck <base.pptx>`): a file of exactly one
  NUL-terminated item per deck slide, in slide order: that slide's note, or an
  empty item to leave its notes unchanged. inject-notes.sh passes the items to
  inject-notes.applescript as plain osascript arguments, so the driver parses
  nothing; item N is slide N. Every note is checked against the deck's slide
  count first.

Usage:
    notes-to-packed.py <notes.json> <out.packed>
    notes-to-packed.py --driver-args --deck <base.pptx> <notes.json> <out.args>

Exit 0 prints `{"records": N, "output": "<path>"}`; exit 1 prints `ERROR: ...`
with the repair on stderr; exit 2 is a usage error.
"""

import argparse
import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

RS = "\x1e"  # record separator
US = "\x1f"  # unit separator
NUL = "\x00"  # driver-argument terminator
# macOS ARG_MAX is 1 MiB and covers argv plus the environment; leave room for both.
DRIVER_ARGS_BUDGET = 768 * 1024
# Transitional and Strict OOXML name the PresentationML namespace differently.
PRESENTATION_NAMESPACES = (
    "http://schemas.openxmlformats.org/presentationml/2006/main",
    "http://purl.oclc.org/ooxml/presentationml/main",
)


def note_pairs(notes_map: object) -> list[tuple[int, str]]:
    """Return `(1-based slide #, text)` pairs, sorted by slide number.

    0-based keys become 1-based; empty notes are dropped. Raises ValueError with
    an actionable message on malformed input (non-object map, non-integer key,
    negative key, or non-string text).
    """
    if not isinstance(notes_map, dict):
        raise ValueError(
            'notes JSON must be an object {"<0-based slide #>": "text", ...}'
        )

    def slide_num(key: object) -> int:
        # JSON object keys are strings; an int key can only come from a manifest
        # built in-process. Anything else takes the same rejection path it
        # always did, now without asking int() to consume an arbitrary object.
        if isinstance(key, (str, int)):
            try:
                return int(key)
            except ValueError:
                pass
        raise ValueError(
            f"notes key {key!r} is not an integer; key each note by its 0-based "
            'slide number, e.g. "0" for the first slide'
        )

    pairs = []
    for key in sorted(notes_map, key=slide_num):
        num = slide_num(key)
        if num < 0:
            raise ValueError(
                f"notes key {key!r} is negative; slide indices are 0-based (>= 0)"
            )
        text = notes_map[key]
        if text is None or text == "":
            continue
        if not isinstance(text, str):
            raise ValueError(
                f"notes for slide {key} must be a string, got {type(text).__name__}; "
                "write the note as a JSON string"
            )
        try:
            text.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError(
                f"notes for slide {key} contain {text[exc.start]!r} at offset "
                f"{exc.start}, a lone surrogate that is not valid Unicode; replace or "
                "remove it in notes.json"
            ) from exc
        pairs.append((num + 1, text))
    return pairs


def pack_notes(notes_map: object) -> str:
    """Return RS-joined `<1-based #>US<text>` records, sorted by slide number.

    Same validation as note_pairs, plus a rejection of text containing the
    RS/US control chars.
    """
    records = []
    for num, text in note_pairs(notes_map):
        if RS in text or US in text:
            raise ValueError(
                f"notes for slide {num - 1} contain a reserved control char (RS/US); "
                "remove it from the note"
            )
        records.append(f"{num}{US}{text}")
    return RS.join(records)


def read_notes_map(notes_path: Path) -> object:
    """Return the decoded notes JSON. Raises ValueError with the repair."""
    try:
        raw = notes_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(
            f"cannot read notes JSON {notes_path} ({exc}); pass the path of an "
            "existing, readable notes.json"
        ) from exc
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"notes JSON {notes_path} is not UTF-8 ({exc}); re-save it as UTF-8"
        ) from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"notes JSON {notes_path} is not valid JSON ({exc}); regenerate it "
            'as a {"<0-based slide #>": "text"} map'
        ) from exc


def deck_slide_count(deck_path: Path) -> int:
    """Return the number of slides in a .pptx, read from ppt/presentation.xml.

    Raises ValueError with the repair when the deck cannot be read or parsed.
    """
    try:
        with zipfile.ZipFile(deck_path) as deck:
            presentation = deck.read("ppt/presentation.xml")
    except OSError as exc:
        raise ValueError(
            f"cannot read deck {deck_path} ({exc}); pass the path of the built "
            "deck copy"
        ) from exc
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ValueError(
            f"{deck_path} is not a .pptx deck ({exc}); pass the built deck copy"
        ) from exc
    try:
        root = ET.fromstring(presentation)
    except ET.ParseError as exc:
        raise ValueError(
            f"{deck_path} has a malformed ppt/presentation.xml ({exc}); re-save "
            "the deck from PowerPoint"
        ) from exc
    for ns in PRESENTATION_NAMESPACES:
        if root.tag == f"{{{ns}}}presentation":
            slide_list = root.find(f"{{{ns}}}sldIdLst")
            if slide_list is None:
                return 0
            return len(slide_list.findall(f"{{{ns}}}sldId"))
    raise ValueError(
        f"{deck_path} has an unrecognized presentation.xml root {root.tag!r}; "
        "re-save it from PowerPoint as a .pptx"
    )


def driver_args(notes_map: object, slide_count: int) -> list[str]:
    """Return one driver argument per slide: its note, or "" to leave it unchanged.

    Raises ValueError when a note targets a slide past slide_count, contains
    NUL (which an argument cannot carry), or the items exceed the argument
    budget.
    """
    items = [""] * slide_count
    for num, text in note_pairs(notes_map):
        if num > slide_count:
            raise ValueError(
                f"notes for 0-based slide {num - 1} target slide {num}, but the deck "
                f"has {slide_count} slides; rebuild notes.json against the "
                "post-expansion deck"
            )
        if NUL in text:
            raise ValueError(
                f"notes for slide {num - 1} contain a NUL character; remove it from "
                "the note"
            )
        items[num - 1] = text
    # Every run passes one item per slide, so each run also carries a 1-byte
    # terminator for every slide whose note it leaves empty.
    sizes = [len(item.encode("utf-8")) + 1 for item in items]
    size = sum(sizes)
    if size > DRIVER_ARGS_BUDGET:
        # Bytes of note text one run can carry after every slide's terminator.
        capacity = DRIVER_ARGS_BUDGET - slide_count
        note_bytes = [sizes[i] - 1 for i in range(slide_count)]
        largest = max(range(slide_count), key=lambda i: note_bytes[i])
        if note_bytes[largest] > capacity:
            raise ValueError(
                f"notes for slide {largest} are {note_bytes[largest]} bytes, over "
                f"the {capacity} bytes one run can carry for a {slide_count}-slide "
                f"deck ({DRIVER_ARGS_BUDGET}-byte budget less one terminator per "
                "slide); shorten that note in notes.json"
            )
        plan = "; ".join(
            f"map {n}: slides {', '.join(str(i) for i in batch)}"
            for n, batch in enumerate(split_into_runs(note_bytes, capacity), 1)
        )
        raise ValueError(
            f"notes total {size} bytes, over the {DRIVER_ARGS_BUDGET}-byte argument "
            f"budget; split notes.json by 0-based slide into {plan}, then run "
            "inject-notes.sh once per map, passing each run's output deck as the "
            "next run's base"
        )
    return items


def split_into_runs(note_bytes: list[int], capacity: int) -> list[list[int]]:
    """Group the non-empty slides' notes into runs of at most capacity bytes.

    First-fit decreasing: every returned run fits, and each slide appears in
    exactly one. note_bytes holds each slide's note size, 0 for no note; every
    size must already be at most capacity.
    """
    runs: list[list[int]] = []
    room: list[int] = []
    for slide in sorted(
        (i for i, n in enumerate(note_bytes) if n), key=lambda i: -note_bytes[i]
    ):
        for r, left in enumerate(room):
            if note_bytes[slide] <= left:
                runs[r].append(slide)
                room[r] -= note_bytes[slide]
                break
        else:
            runs.append([slide])
            room.append(capacity - note_bytes[slide])
    return [sorted(run) for run in runs]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Turn a 0-based speaker-notes JSON map into the notes driver's input."
    )
    parser.add_argument("notes", type=Path, help="0-based notes JSON map")
    parser.add_argument("out", type=Path, help="output file")
    parser.add_argument(
        "--driver-args",
        action="store_true",
        help="write NUL-terminated driver arguments instead of the packed format",
    )
    parser.add_argument(
        "--deck", type=Path, help="deck whose slide count bounds the notes"
    )
    args = parser.parse_args(argv)
    if args.driver_args and args.deck is None:
        parser.error("--driver-args requires --deck")
    # Every ValueError below carries its own repair.
    try:
        notes_map = read_notes_map(args.notes)
        if args.driver_args:
            items = driver_args(notes_map, deck_slide_count(args.deck))
            payload = "".join(item + NUL for item in items)
            count = sum(1 for item in items if item)
        else:
            payload = pack_notes(notes_map)
            count = 0 if payload == "" else payload.count(RS) + 1
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    try:
        args.out.write_text(payload, encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        print(
            f"ERROR: cannot write {args.out} ({exc}); pass an output path in an "
            "existing, writable directory with free space",
            file=sys.stderr,
        )
        return 1
    print(json.dumps({"records": count, "output": str(args.out)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
