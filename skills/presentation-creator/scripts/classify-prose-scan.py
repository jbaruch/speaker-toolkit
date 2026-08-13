#!/usr/bin/env python3
"""Classify a blog-writer prose scan into a guardrail status.

The scan itself belongs to `blog-writer`, which owns the AI-writing-pattern
catalog. This script owns only what happens to its counts afterwards: a pure
mapping from (high, medium) to PASS / WARN / FAIL, plus the SKIP that reports an
absent scanner.

Thresholds live here rather than in skill prose because the mapping is a total
function of two integers, and prose thresholds drift from the ones anybody
actually applies.

Usage:
    classify-prose-scan.py --high N --medium N
    classify-prose-scan.py --unavailable

Output: one schema-v1 JSON object on stdout. Exits 0 for every classified
result, including FAIL — a FAIL is a finding, not a run failure. Malformed input
exits non-zero with a diagnostic on stderr.
"""

from __future__ import annotations

import argparse
import json
import sys

REPORT_SCHEMA_VERSION = 1

STATUS_PASS = "PASS"
STATUS_WARN = "WARN"
STATUS_FAIL = "FAIL"
STATUS_SKIP = "SKIP"

# A high finding is a phrasing the catalog is confident about; a medium is a
# suspicion. One high is worth reading, four is a rewrite. Mediums only escalate
# in a cluster, because any long prose passage collects a few.
MAX_PASS_MEDIUM = 2
MIN_FAIL_HIGH = 4

INSTALL_HINT = "tessl install jbaruch/blog-writer"


def classify(high: int, medium: int) -> str:
    """Map finding counts to a guardrail status."""
    if high >= MIN_FAIL_HIGH:
        return STATUS_FAIL
    if high > 0 or medium > MAX_PASS_MEDIUM:
        return STATUS_WARN
    return STATUS_PASS


def report(*, high: int, medium: int) -> dict:
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "status": classify(high, medium),
        "high": high,
        "medium": medium,
        "scanner_available": True,
    }


def unavailable_report() -> dict:
    """The scanner is not installed, which is a skip and never a pass."""
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "status": STATUS_SKIP,
        "high": None,
        "medium": None,
        "scanner_available": False,
        "remedy": INSTALL_HINT,
    }


def _non_negative(raw: str) -> int:
    value = int(raw)
    if value < 0:
        raise argparse.ArgumentTypeError("finding counts cannot be negative")
    return value


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--high", type=_non_negative)
    parser.add_argument("--medium", type=_non_negative)
    parser.add_argument(
        "--unavailable",
        action="store_true",
        help="blog-writer is not installed; emit the SKIP report",
    )
    args = parser.parse_args(argv)

    if args.unavailable:
        if args.high is not None or args.medium is not None:
            print(
                "--unavailable takes no counts: an absent scanner produced none",
                file=sys.stderr,
            )
            return 2
        print(json.dumps(unavailable_report(), sort_keys=True))
        return 0

    if args.high is None or args.medium is None:
        print(
            "supply both --high and --medium, or --unavailable when blog-writer "
            f"is not installed ({INSTALL_HINT})",
            file=sys.stderr,
        )
        return 2

    print(json.dumps(report(high=args.high, medium=args.medium), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
