#!/usr/bin/env python3
"""Carry deck text across `run VB macro` without losing a character.

PowerPoint's `run VB macro` converts every string parameter to Mac Roman, so a
character outside it reaches VBA as `?`: a slide titled "Port -> GitHub" with a
real arrow builds as "Port ? GitHub". Em dashes survive the conversion, which is
what kept this hidden.

This script rewrites text so that nothing outside printable ASCII crosses the
bridge. Each other UTF-16 code unit becomes the marker U+001C plus four hex
digits, and `DecodeBridgeText` in RunDeckOps.bas turns it back at the top of each
macro. ASCII-only output means the result doesn't depend on any Mac Roman table.

A macro imported before the decoder existed would put the escapes on the slide, so
text that needed escaping requires the running macro to match the shipped module.
Pure-ASCII text never asks PowerPoint anything.

Usage:
    deck-text-bridge.py scalar <input> <output>
    deck-text-bridge.py file <input> <output>

    scalar  one macro argument, such as a title. Every control character is escaped.
    file    a line-oriented op sequence or packed spec. Tab, CR, LF and the U+001D,
            U+001E and U+001F separators stay raw, since the macro splits on them.

Input is read as UTF-8 and output is written as ASCII.

Stdout: one JSON object, {"output": "<path>", "escaped": <code units escaped>}.
Stderr: an actionable diagnostic. Exit 0 on success, 1 when refused with nothing
written (input that isn't UTF-8, input holding the reserved marker, or a macro that
can't decode the result), and 2 on usage error. Running PowerPoint is only asked
for its macro version, through deckops-doctor.py's read-only probe.
"""

from __future__ import annotations

import argparse
import json
import sys
from importlib import util as importlib_util
from pathlib import Path
from typing import NoReturn

MARKER = "\x1c"
PRINTABLE_ASCII = frozenset(chr(code) for code in range(0x20, 0x7F))
FILE_STRUCTURE = frozenset("\t\r\n\x1d\x1e\x1f")
STAMP_DRIVER = "RunDeckOps.bas"
SETUP_DOC = "skills/presentation-builder/references/deck-editing-setup.md"


class BridgeRefusal(Exception):
    """The text can't safely cross the bridge; the message says what to do."""


def escape_text(text: str, *, keep: frozenset[str]) -> tuple[str, int]:
    """Return the ASCII form of `text` and how many UTF-16 code units it escaped."""
    if MARKER in text:
        raise BridgeRefusal(
            "the text holds U+001C, which the macro bridge reserves as its escape "
            "marker; remove that character and re-run"
        )
    pieces: list[str] = []
    escaped = 0
    for character in text:
        if character in keep:
            pieces.append(character)
            continue
        units = character.encode("utf-16-be")
        for offset in range(0, len(units), 2):
            pieces.append(f"{MARKER}{units[offset : offset + 2].hex().upper()}")
            escaped += 1
    return "".join(pieces), escaped


def _load_sibling(name: str, filename: str):
    """Import a sibling script whose filename is not a valid module name."""
    path = Path(__file__).resolve().parent / filename
    spec = importlib_util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path} — reinstall the plugin")
    module = importlib_util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def require_decoding_macro(scripts_dir: Path) -> None:
    """Refuse unless the running PowerPoint holds the module shipped beside this."""
    doctor = _load_sibling("deckops_doctor", "deckops-doctor.py")
    expected = doctor.sync_deck_drivers.read_stamp(
        (scripts_dir / STAMP_DRIVER).read_text(encoding="utf-8")
    )
    probe = doctor.run_probe(scripts_dir)
    state = probe.get("state")
    if state == "ok" and probe.get("stamp") == expected:
        return
    if state == "ok":
        problem = (
            "DeckOps.pptm holds an older macro that would put escape codes on the "
            f"slide. Re-import RunDeckOps.bas ({SETUP_DOC} Step 3)"
        )
    elif state == "not_running":
        problem = "PowerPoint isn't running. Open DeckOps.pptm with macros enabled"
    elif state == "macro_unreachable":
        problem = (
            "PowerPoint can't reach the DeckOps macro. Open DeckOps.pptm with macros "
            f"enabled ({SETUP_DOC} Step 1)"
        )
    else:
        problem = (
            f"the macro version probe failed: {probe.get('detail', 'no detail')}. "
            "Run deckops-doctor.py and follow its next_step"
        )
    raise BridgeRefusal(
        f"this text needs the current DeckOps macro: {problem}, then re-run. "
        "No deck was changed."
    )


def bridge(mode: str, input_path: Path, output_path: Path, scripts_dir: Path) -> dict:
    try:
        text = input_path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BridgeRefusal(
            f"{input_path} is not valid UTF-8 ({exc.reason} at byte {exc.start}); "
            "re-encode it and re-run"
        ) from exc
    keep = PRINTABLE_ASCII | FILE_STRUCTURE if mode == "file" else PRINTABLE_ASCII
    bridged, escaped = escape_text(text, keep=keep)
    if escaped:
        require_decoding_macro(scripts_dir)
    output_path.write_bytes(bridged.encode("ascii"))
    return {"output": str(output_path), "escaped": escaped}


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Carry deck text across `run VB macro` without losing a character."
    )
    parser.add_argument("mode", choices=("scalar", "file"))
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    return parser.parse_args(argv)


def _refuse(message: str) -> NoReturn:
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = bridge(
            args.mode,
            args.input,
            args.output,
            Path(__file__).resolve().parent,
        )
    except BridgeRefusal as exc:
        _refuse(str(exc))
    except OSError as exc:
        _refuse(f"cannot read {args.input} or write {args.output}: {exc}")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
