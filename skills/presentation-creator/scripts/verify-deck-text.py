#!/usr/bin/env python3
"""Check that every text op of an op sequence reached the built deck intact.

A character lost on the way into PowerPoint leaves a valid deck and a `?` nobody
reads, so the setup smoke test compares the text instead of trusting the exit code.
Each TITLE, SUBTITLE, BODY, BULLET, TEXT and CELL value must appear in the slide
built from its SLIDE op. A slide's runs are joined first, since PowerPoint may split
one string into several runs, such as around an emoji.

Usage:
    verify-deck-text.py <deck.pptx> <opsFile>

Stdout: one JSON object, {"ok": true, "slides": <n>, "checked": <n>}, on success.
Stderr: each mismatch, with its slide and expected text. Exit 0 when all text is
intact, 1 on a mismatch or an unreadable deck, and 2 on usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ElementTree
import zipfile
from pathlib import Path

DRAWING_TEXT = "{http://schemas.openxmlformats.org/drawingml/2006/main}t"
SLIDE_PART = re.compile(r"ppt/slides/slide(\d+)\.xml")
US = "\x1f"
# The op's text field, counted from the op name.
TEXT_FIELD = {"TITLE": 1, "SUBTITLE": 1, "BODY": 1, "BULLET": 2, "TEXT": 5, "CELL": 3}


def expected_text_by_slide(ops: str) -> list[list[str]]:
    """The text values each SLIDE op's slide must show, in deck order."""
    slides: list[list[str]] = []
    for line in ops.splitlines():
        fields = line.split(US)
        op = fields[0].strip().upper()
        if op == "SLIDE":
            slides.append([])
        elif op in TEXT_FIELD and slides and len(fields) > TEXT_FIELD[op]:
            slides[-1].append(fields[TEXT_FIELD[op]])
    return slides


def deck_text_by_slide(deck: Path) -> list[str]:
    """Each slide's joined text, ordered by slide part number.

    A freshly built deck numbers its parts in slide order, which is the only deck
    this reads.
    """
    with zipfile.ZipFile(deck) as archive:
        numbered = sorted(
            (int(match.group(1)), match.group(0))
            for match in map(SLIDE_PART.fullmatch, archive.namelist())
            if match is not None
        )
        return [
            "".join(
                element.text or ""
                for element in ElementTree.fromstring(archive.read(name)).iter(
                    DRAWING_TEXT
                )
            )
            for _, name in numbered
        ]


def mismatches(expected: list[list[str]], actual: list[str]) -> list[str]:
    problems = []
    if len(expected) != len(actual):
        problems.append(
            f"the ops build {len(expected)} slides; the deck has {len(actual)}"
        )
    for number, (values, text) in enumerate(zip(expected, actual), start=1):
        problems.extend(
            f"slide {number} is missing {value!r}"
            for value in values
            if value not in text
        )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check that every text op reached the built deck intact."
    )
    parser.add_argument("deck", type=Path)
    parser.add_argument("ops", type=Path)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        expected = expected_text_by_slide(args.ops.read_text(encoding="utf-8"))
        actual = deck_text_by_slide(args.deck)
    except (
        OSError,
        UnicodeDecodeError,
        zipfile.BadZipFile,
        ElementTree.ParseError,
    ) as exc:
        print(
            f"ERROR: cannot compare {args.deck} with {args.ops}: {exc}. Confirm the "
            "deck was built, then re-run.",
            file=sys.stderr,
        )
        return 1
    problems = mismatches(expected, actual)
    if problems:
        for problem in problems:
            print(f"ERROR: {problem}", file=sys.stderr)
        print(
            "ERROR: text was lost on the way into PowerPoint. Run deckops-doctor.py; "
            "a stale macro is the usual cause.",
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "slides": len(actual),
                "checked": sum(len(values) for values in expected),
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
