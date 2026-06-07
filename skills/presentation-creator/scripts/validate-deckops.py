#!/usr/bin/env python3
"""Validate a deck op-sequence before BuildDeck (the VBA interpreter) runs it.

The op sequence (see references/deckops-spec.md) is newline-separated; each line
is an op name then US (Chr 31, "\\x1f")-delimited fields. The agent emits it by
judgment, so a fast deterministic check catches typos / wrong arity / bad state
(e.g. CELL before a TABLE) up front instead of part-building a deck in PowerPoint.

This is the deterministic, unit-tested half of #57 Phase D; BuildDeck itself is
manual-validation-only (it drives PowerPoint).

Usage:
    validate-deckops.py <ops-file>   # exit 0 + JSON summary, or exit 1 + errors on stderr
"""
import json
import sys
from pathlib import Path

US = "\x1f"

# op -> (exact field count including the op) or (min count, None) for variadic.
ARITY = {
    "SLIDE": (2, 2), "TITLE": (2, 2), "SUBTITLE": (2, 2), "BODY": (2, 2),
    "FOOTER": (2, 2), "CAT": (2, 2), "BULLET": (3, 3), "TEXT": (6, 6),
    "IMAGE": (6, 6), "SHAPE": (6, 6), "BG": (4, 4), "OPTIMIZE": (1, 1),
    "TABLE": (7, 7), "CELL": (4, 4), "CHART": (6, 6), "SERIES": (3, None),
}
# 1-based field indices that must parse as int / float.
INT_FIELDS = {
    "SLIDE": [1], "BULLET": [1], "SHAPE": [1], "BG": [1, 2, 3],
    "TABLE": [1, 2], "CELL": [1, 2], "CHART": [1],
}
FLOAT_FIELDS = {
    "TEXT": [1, 2, 3, 4], "IMAGE": [1, 2, 3, 4], "SHAPE": [2, 3, 4, 5],
    "TABLE": [3, 4, 5, 6], "CHART": [2, 3, 4, 5],
}
NEEDS_SLIDE = set(ARITY) - {"SLIDE"}


def validate_ops(text: str) -> list[str]:
    """Return a list of human-readable error strings (empty == valid)."""
    errors = []
    have_slide = have_table = have_chart = False
    chart_open_line = 0          # line of the current CHART, 0 == none open
    chart_has_series = False

    def close_chart():
        # A CHART with no SERIES keeps PowerPoint's default sample data.
        if chart_open_line and not chart_has_series:
            errors.append(f"line {chart_open_line}: CHART has no SERIES (the chart "
                          "would keep PowerPoint's default sample data)")

    for n, raw in enumerate(text.split("\n"), start=1):
        line = raw.rstrip("\r")
        if not line.strip():
            continue
        fields = line.split(US)
        op = fields[0].strip().upper()
        if op not in ARITY:
            errors.append(f"line {n}: unknown op {op!r}")
            continue
        lo, hi = ARITY[op]
        if len(fields) < lo or (hi is not None and len(fields) > hi):
            want = f"{lo}" if lo == hi else (f">={lo}" if hi is None else f"{lo}-{hi}")
            errors.append(f"line {n}: op {op} expects {want} fields, got {len(fields)}")
            continue
        for idx in INT_FIELDS.get(op, []):
            try:
                int(fields[idx])
            except ValueError:
                errors.append(f"line {n}: op {op} field {idx} must be an integer, got {fields[idx]!r}")
        for idx in FLOAT_FIELDS.get(op, []):
            try:
                float(fields[idx])
            except ValueError:
                errors.append(f"line {n}: op {op} field {idx} must be a number, got {fields[idx]!r}")
        if op == "SERIES":
            for idx in range(2, len(fields)):
                try:
                    float(fields[idx])
                except ValueError:
                    errors.append(f"line {n}: SERIES value {idx} must be a number, got {fields[idx]!r}")
        if op == "BG":
            for idx in (1, 2, 3):
                try:
                    if not 0 <= int(fields[idx]) <= 255:
                        errors.append(f"line {n}: BG channel {idx} must be 0-255, got {fields[idx]}")
                except ValueError:
                    pass  # already reported by INT_FIELDS
        # state rules
        if op == "SLIDE":
            try:
                if int(fields[1]) < 0:
                    errors.append(f"line {n}: SLIDE layout index must be >= 0, got {fields[1]}")
            except (ValueError, IndexError):
                pass  # already reported by INT_FIELDS / arity
            close_chart()
            chart_open_line, chart_has_series = 0, False
            have_slide, have_table, have_chart = True, False, False
        elif op in NEEDS_SLIDE and not have_slide:
            errors.append(f"line {n}: {op} before any SLIDE")
        if op == "TABLE":
            have_table = True
        elif op == "CELL" and not have_table:
            errors.append(f"line {n}: CELL before any TABLE on the current slide")
        if op == "CHART":
            close_chart()
            have_chart = True
            chart_open_line, chart_has_series = n, False
        elif op in ("CAT", "SERIES") and not have_chart:
            errors.append(f"line {n}: {op} before any CHART on the current slide")
        if op == "SERIES":
            chart_has_series = True
    close_chart()
    return errors


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: validate-deckops.py <ops-file>", file=sys.stderr)
        sys.exit(2)
    path = Path(sys.argv[1])
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"ERROR: ops file not found: {path} — emit it per "
              "references/deckops-spec.md.", file=sys.stderr)
        sys.exit(1)
    except UnicodeDecodeError as e:
        print(f"ERROR: ops file {path} is not valid UTF-8 ({e}) — re-emit it as "
              "UTF-8 per references/deckops-spec.md.", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"ERROR: cannot read ops file {path}: {e.strerror or e} — check the "
              "path and permissions.", file=sys.stderr)
        sys.exit(1)
    errors = validate_ops(text)
    if errors:
        print("ERROR: invalid deck op sequence:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        sys.exit(1)
    slides = sum(1 for ln in text.split("\n") if ln.split(US)[0].strip().upper() == "SLIDE")
    ops = sum(1 for ln in text.split("\n") if ln.strip())
    print(json.dumps({"slides": slides, "ops": ops}))


if __name__ == "__main__":
    main()
