#!/usr/bin/env python3
"""Report which PPTX catalog decks need visual re-extraction (#229).

Selection is deterministic, so it is a script rather than something the agent
reproduces (`script-delegation` -> The Core Principle). For every
`pptx_catalog` record this makes the two live observations the classifier
requires — the deck's fingerprint under `config.pptx_source_dir`, and the
extraction artifact's SHA-256 under the vault root — and reports the resulting
class. Only `current` may skip extraction; every other class regenerates.

A persisted receipt is a hint, never authority: an unreadable deck or a
deleted artifact reports `unverified`, not `current`.

Usage: classify-pptx-evidence.py <vault-root-or-database-path>
Stdout: one JSON object; `records[]` carries `pptx_path`, `classification`,
        `needs_extraction`, and which observations were available.
Stderr: one actionable line when the database cannot be read.
Exit 0 when the catalog was classified, 2 when the database is unusable.
Exit 0 with `needs_extraction: true` rows is the normal "work to do" result —
this is a reporting tool, not a gate.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from pptx_catalog_selection import (
    SELECTION_SCHEMA_VERSION,
    classify_catalog,
)
from pptx_evidence import (
    PPTX_EXTRACTION_PIPELINE_VERSION,
    PPTX_EXTRACTION_SCHEMA_VERSION,
)
from tracking_database import (
    TrackingDatabaseError,
    assess_tracking_database,
)
from tracking_database_io import (
    TrackingDatabaseIOError,
    decode_json_object,
    snapshot_tracking_database,
)

REPORT_SCHEMA_VERSION = 1
DATABASE_BASENAME = "tracking-database.json"


def resolve_input(value: str | Path) -> tuple[Path, Path]:
    """Bind a vault root to its canonical database, as preflight does."""
    path = Path(value).expanduser().absolute()
    if path.name.lower() == DATABASE_BASENAME:
        return path.parent, path
    return path, path / DATABASE_BASENAME


def execute(value: str | Path) -> dict[str, object]:
    vault_root, database_path = resolve_input(value)
    snapshot = snapshot_tracking_database(database_path)
    database = decode_json_object(snapshot)
    try:
        assessment = assess_tracking_database(database)
    except TrackingDatabaseError as exc:
        raise TrackingDatabaseIOError(
            f"tracking database owner assessment failed: {exc}"
        ) from exc
    if not assessment.usable:
        reasons = ", ".join(assessment.reason_codes) or "unsupported_owner_state"
        raise TrackingDatabaseIOError(
            f"tracking database has no usable legacy/current owner state ({reasons})"
        )

    config = database.get("config")
    pptx_source_dir = (
        config.get("pptx_source_dir") if isinstance(config, dict) else None
    )
    records = classify_catalog(
        database,
        vault_root=vault_root,
        pptx_source_dir=pptx_source_dir,
    )
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "selection_schema_version": SELECTION_SCHEMA_VERSION,
        "ok": True,
        "database_path": str(snapshot.path),
        "sha256": snapshot.sha256,
        "extractor_schema_version": PPTX_EXTRACTION_SCHEMA_VERSION,
        "pipeline_version": PPTX_EXTRACTION_PIPELINE_VERSION,
        "needs_extraction_count": sum(
            1 for record in records if record["needs_extraction"]
        ),
        "records": records,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("vault", type=Path)
    args = parser.parse_args(argv)
    try:
        report = execute(args.vault)
    except TrackingDatabaseIOError as exc:
        print(
            json.dumps(
                {
                    "schema_version": REPORT_SCHEMA_VERSION,
                    "ok": False,
                    "error": str(exc),
                }
            )
        )
        print(f"pptx evidence classification failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
