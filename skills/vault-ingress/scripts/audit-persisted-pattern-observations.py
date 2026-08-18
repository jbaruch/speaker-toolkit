#!/usr/bin/env python3
"""Audit a tracking database's persisted pattern observations, read-only.

`persisted_pattern_observations.assess_persisted_pattern_observations` already
classifies one talk, and seven consumers call it in-flow — migration, preflight,
analysis rendering, queue normalization, persistence, the adherence baseline and
the cohort snapshot. Every one of them assesses a talk to decide something about
that talk, then moves on. None of them can answer "what is wrong with this
corpus, in total, before anyone touches it", which is what #167's last
acceptance criterion asks for:

    Run the validator against a copy of the live database and attach the
    deterministic counts to the repair/reparse report.

This is that entry point. It opens a database, assesses every talk, and emits
stable JSON with per-reason-code counts and the affected filenames.

Read-only on purpose. It takes a path and writes nothing, so it is safe to point
at a copy of a live vault — and pointing it at a copy is the intended use, since
the reparse decision wants the counts before the migration runs, not after.

Exit codes follow `audit-pattern-catalog.py`, whose shape this mirrors:

* 0 — every talk's observations are usable.
* 1 — at least one talk is unusable. The report is on stdout; this is a finding
  about the corpus, not a failure of the audit.
* 2 — argparse owns malformed invocations.
* 3 — unexpected failure. One JSON document on stderr, stdout left empty, so a
  caller can tell a broken auditor from a corpus with defects.

A talk carrying no `pattern_observations` at all is reported as
`observations_absent` rather than skipped: on a corpus where 9 of 209 talks had
no block, silence would have read as nine clean talks.

Usage::

    python3 skills/vault-ingress/scripts/audit-persisted-pattern-observations.py \\
        path/to/tracking-database.json
    python3 skills/vault-ingress/scripts/audit-persisted-pattern-observations.py \\
        path/to/tracking-database.json --catalog path/to/patterns
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from failure_diagnostics import emit_unexpected_failure
from persisted_pattern_observations import assess_persisted_pattern_observations
from return_validation import load_catalog
from tracking_database_io import decode_json_object_bytes, snapshot_tracking_database

# Bumped when the emitted shape changes. A consumer that pins a version and
# receives another must refuse the report rather than read fields positionally
# (`rules/stateful-artifacts.md` -> Migration Policy).
REPORT_SCHEMA_VERSION = 1


def audit_database(
    database_path: str | Path,
    catalog_path: str | Path | None = None,
) -> dict[str, Any]:
    """Assess every talk's persisted observations and return the report.

    Separate from `main` so the report can be built and asserted without a
    process boundary, which is what the tests do.
    """
    snapshot = snapshot_tracking_database(database_path)
    database = decode_json_object_bytes(snapshot.raw, snapshot.path)
    catalog = load_catalog(catalog_path)

    talks = database.get("talks")
    if not isinstance(talks, list):
        raise ValueError(
            "tracking database has no talks array; point this at a tracking "
            "database, not a talk file or a profile"
        )

    reason_counts: Counter[str] = Counter()
    # Filenames per reason code, so a count can be acted on rather than only
    # reported. A count alone tells an owner how bad it is and not where.
    reason_filenames: dict[str, list[str]] = {}
    unusable: list[str] = []
    assessed = 0

    for index, talk in enumerate(talks):
        filename = talk.get("filename") if isinstance(talk, dict) else None
        # Index-derived identity for a talk whose own filename is unusable —
        # a malformed record is exactly the kind this audit exists to surface,
        # so it must not be the one entry the report cannot name.
        label = (
            filename if isinstance(filename, str) and filename else f"talks[{index}]"
        )
        assessment = assess_persisted_pattern_observations(talk, catalog)
        assessed += 1
        if assessment.usable:
            continue
        unusable.append(label)
        for code in sorted({finding.reason_code for finding in assessment.findings}):
            reason_counts[code] += 1
            reason_filenames.setdefault(code, []).append(label)

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "database": str(Path(database_path).resolve()),
        "summary": {
            "talks_assessed": assessed,
            "talks_usable": assessed - len(unusable),
            "talks_unusable": len(unusable),
        },
        # Sorted so two runs over one database produce byte-identical reports
        # and a diff between two runs is a real change, not dict ordering.
        "reason_counts": dict(sorted(reason_counts.items())),
        "reason_filenames": {
            code: sorted(names) for code, names in sorted(reason_filenames.items())
        },
        "unusable_filenames": sorted(unusable),
        "usable": not unusable,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit persisted pattern observations in a tracking database "
            "without modifying it."
        ),
    )
    parser.add_argument(
        "database",
        type=Path,
        help="tracking-database.json to audit; safe to point at a copy",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=None,
        help="pattern catalog directory; defaults to the repo's own catalog",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return its process status."""
    args = _parser().parse_args(argv)
    report = audit_database(args.database, args.catalog)
    # Serialize before writing: a `json.dump` straight to stdout that fails
    # partway leaves a truncated document the caller would try to parse.
    rendered = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False)
    sys.stdout.write(rendered + "\n")
    if not report["usable"]:
        print(
            f"{report['summary']['talks_unusable']} of "
            f"{report['summary']['talks_assessed']} talks carry unusable "
            "persisted pattern observations; inspect JSON stdout before "
            "migration or reparse",
            file=sys.stderr,
        )
        return 1
    return 0


def run_cli(argv: list[str] | None = None) -> int:
    """Run the CLI behind its failure boundary. Returns the process exit code.

    Importable so the boundary's contract is testable without executing the
    module as a script.
    """
    try:
        return main(argv)
    # The reparse decision reads this report, so a non-zero exit without the
    # stdout document must still say what happened; a traceback would leak vault
    # paths and read an unreadable database as a corpus full of defects.
    except Exception as exc:  # noqa: BLE001 - outer-boundary-process-contract
        emit_unexpected_failure(
            exc,
            "persisted_observation_audit_unexpected_failure",
            "The persisted pattern-observation audit failed unexpectedly. This "
            "command is read-only, so the database is unchanged — but it is "
            "UNAUDITED. Do not begin migration or reparse until a clean run "
            "reports on stdout.",
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(run_cli())
