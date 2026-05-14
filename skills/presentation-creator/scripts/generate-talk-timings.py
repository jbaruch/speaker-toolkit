#!/usr/bin/env python3
"""Generate timemytalk.app timing files from outline.yaml.

Walks `chapters[]` from the validated Outline and emits one line per
chapter with cumulative MM:SS start timestamps. Adds an optional Q&A
chapter and a final FINISH marker.

Usage:
    python3 generate-talk-timings.py <outline.yaml>
    python3 generate-talk-timings.py <outline.yaml> --qa 5
    python3 generate-talk-timings.py <outline.yaml> --output timings.txt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import outline_schema as _os  # noqa: E402


def format_seconds(total_seconds: int) -> str:
    minutes = total_seconds // 60
    secs = total_seconds % 60
    return f"{minutes}:{secs:02d}"


def generate_timings(
    chapters: list[_os.Chapter],
    qa_minutes: int = 0,
) -> list[str]:
    """Emit cumulative MM:SS timing lines for each chapter + Q&A + FINISH."""
    lines: list[str] = []
    cumulative = 0
    for c in chapters:
        lines.append(f"{format_seconds(cumulative)} {c.title}")
        cumulative += int(c.target_min * 60)
    if qa_minutes > 0:
        lines.append(f"{format_seconds(cumulative)} Q&A")
        cumulative += qa_minutes * 60
    lines.append(f"{format_seconds(cumulative)} FINISH")
    return lines


def main():
    parser = argparse.ArgumentParser(
        description="Generate timemytalk.app timing file from outline.yaml.",
        epilog="Produces MM:SS chapter lines for the timemytalk.app timer.",
    )
    parser.add_argument("outline", help="Path to outline.yaml")
    parser.add_argument(
        "--qa", type=int, default=0,
        help="Q&A duration in minutes to add before FINISH",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output path (default: stdout)",
    )
    args = parser.parse_args()

    try:
        outline = _os.load_outline(args.outline)
    except Exception as exc:
        print(f"failed to load {args.outline}: {exc}", file=sys.stderr)
        sys.exit(1)

    lines = generate_timings(outline.chapters, qa_minutes=args.qa)
    output = "\n".join(lines) + "\n"

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Timings written to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(output)


if __name__ == "__main__":
    main()
