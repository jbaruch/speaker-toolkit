#!/usr/bin/env python3
"""Flag talks whose analyses predate the image-text extraction fix (issue #116).

`pptx-extraction.py` reads text out of PPTX shapes. Text rendered inside a
picture — the norm for AI-generated illustration decks — was invisible to it,
and analyses produced from that output recorded the *absence* of extractable
text as evidence of wordless slides. That inverts Dimension 8 for exactly the
decks whose slides carry the most.

This marks the affected talks `needs-reprocessing` so a selective reparse
covers them. A full reparse of the vault covers them anyway; this exists so
that a partial one does not silently leave them stale.

Reads both extraction shapes (dual-accept per stateful-artifacts):
  - new: `text_extraction_confidence == "low"`
  - old: `has_image` true AND `has_text_placeholder` false — the pre-fix
    signature of the same slide. Over-flags a decorative-image slide, which is
    the safe direction: a needless reparse costs time, a missed one keeps a
    wrong analysis.

Usage:
    flag-image-text-reprocess.py <tracking-db.json> <pptx-extraction-results.json>
    flag-image-text-reprocess.py ... --apply    # write; default is a dry run

Output: JSON summary on stdout. Exit 0 on success, non-zero on failure.
Idempotent — a talk already flagged for this reason is left alone.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPROCESS_REASON = "image_text_extraction_fixed"


def slide_is_unreadable(slide: dict) -> bool:
    """True when the extractor could not see text the slide may be showing."""
    if "text_extraction_confidence" in slide:
        return slide["text_extraction_confidence"] == "low"
    # Pre-fix shape: a picture present and no text-frame shape reached.
    return bool(slide.get("has_image")) and not slide.get(
        "has_text_placeholder", slide.get("has_text_frame_shapes", False),
    )


def affected_decks(extraction: dict | list) -> dict[str, int]:
    """Map deck path → count of slides the extractor could not read."""
    decks = extraction if isinstance(extraction, list) else extraction.get(
        "decks", extraction.get("results", []),
    )
    out: dict[str, int] = {}
    for deck in decks:
        if not isinstance(deck, dict):
            continue
        path = deck.get("pptx_path")
        if not path:
            continue
        n = sum(
            1 for s in deck.get("per_slide_visual", []) if slide_is_unreadable(s)
        )
        if n:
            out[path] = n
    return out


def flag(db: dict, decks: dict[str, int]) -> list[dict]:
    """Mark matching talks needs-reprocessing. Returns what changed."""
    changed = []
    for talk in db.get("talks", []):
        path = talk.get("pptx_path")
        if not path or path not in decks:
            continue
        if talk.get("reprocess_reason") == REPROCESS_REASON:
            continue  # already flagged — idempotent
        talk["status"] = "needs-reprocessing"
        talk["reprocess_reason"] = REPROCESS_REASON
        changed.append({
            "filename": talk.get("filename"),
            "pptx_path": path,
            "unreadable_slides": decks[path],
        })
    return changed


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tracking_db", type=Path)
    ap.add_argument("extraction_results", type=Path)
    ap.add_argument(
        "--apply", action="store_true",
        help="write the tracking DB (default: dry run)",
    )
    args = ap.parse_args(argv[1:])

    for p in (args.tracking_db, args.extraction_results):
        if not p.is_file():
            print(f"not a file: {p}", file=sys.stderr)
            return 1

    db = json.loads(args.tracking_db.read_text(encoding="utf-8"))
    extraction = json.loads(args.extraction_results.read_text(encoding="utf-8"))

    decks = affected_decks(extraction)
    changed = flag(db, decks)

    if args.apply and changed:
        args.tracking_db.write_text(
            json.dumps(db, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    print(json.dumps({
        "affected_decks": len(decks),
        "talks_flagged": len(changed),
        "applied": bool(args.apply and changed),
        "reprocess_reason": REPROCESS_REASON,
        "talks": changed,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
