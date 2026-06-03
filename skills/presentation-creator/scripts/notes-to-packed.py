#!/usr/bin/env python3
"""Pack a 0-based speaker-notes JSON map into the SetSpeakerNotes wire format.

Input JSON: `{"<0-based slide #>": "notes text", ...}` — the historical
inject-speaker-notes.py format. Output: a UTF-8 file of records
`<1-based #>US<text>` joined by RS, where US=Chr(31), RS=Chr(30) (non-printing
control chars that don't occur in prose notes). AppleScript reads the file as
UTF-8 and passes it to the SetSpeakerNotes VBA macro, which splits it.

Slide numbers are converted 0-based -> 1-based (python-pptx uses 0-based
indices; PowerPoint VBA uses 1-based). Empty notes are dropped.

Usage:
    notes-to-packed.py <notes.json> <out.packed>
"""
import json
import sys
from pathlib import Path

RS = "\x1e"  # record separator
US = "\x1f"  # unit separator


def pack_notes(notes_map: object) -> str:
    """Return RS-joined `<1-based #>US<text>` records, sorted by slide number.

    0-based keys become 1-based; empty notes are dropped. Raises ValueError with
    an actionable message on malformed input (non-object map, non-integer key,
    non-string text, or text containing the RS/US control chars).
    """
    if not isinstance(notes_map, dict):
        raise ValueError('notes JSON must be an object {"<0-based slide #>": "text", ...}')

    def slide_num(key: object) -> int:
        try:
            return int(key)
        except (TypeError, ValueError):
            raise ValueError(f"notes key {key!r} is not an integer") from None

    records = []
    for key in sorted(notes_map, key=slide_num):
        text = notes_map[key]
        if text is None or text == "":
            continue
        if not isinstance(text, str):
            raise ValueError(f"notes for slide {key} must be a string, got {type(text).__name__}")
        if RS in text or US in text:
            raise ValueError(f"notes for slide {key} contain a reserved control char (RS/US)")
        records.append(f"{slide_num(key) + 1}{US}{text}")
    return RS.join(records)


def main() -> None:
    if len(sys.argv) != 3:
        print("usage: notes-to-packed.py <notes.json> <out.packed>", file=sys.stderr)
        sys.exit(2)
    try:
        notes_map = json.loads(Path(sys.argv[1]).read_text())
        packed = pack_notes(notes_map)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    Path(sys.argv[2]).write_text(packed, encoding="utf-8")
    count = 0 if packed == "" else packed.count(RS) + 1
    print(f"packed {count} note record(s) -> {sys.argv[2]}")


if __name__ == "__main__":
    main()
