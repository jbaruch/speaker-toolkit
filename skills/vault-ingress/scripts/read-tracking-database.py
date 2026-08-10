#!/usr/bin/env python3
"""Read one tracking database through the owner strict snapshot contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from pptx_evidence import (
    PPTX_EXTRACTION_PIPELINE_VERSION,
    PPTX_EXTRACTION_SCHEMA_VERSION,
)
from tracking_database import (
    TrackingDatabaseError,
    assess_tracking_database,
    classify_pptx_visual_evidence,
    pptx_visual_evidence_needs_extraction,
)
from tracking_database_io import (
    TrackingDatabaseIOError,
    decode_json_object,
    snapshot_tracking_database,
)


REPORT_SCHEMA_VERSION = 2


def pptx_visual_evidence_selection(
    database: dict[str, object],
) -> list[dict[str, object]]:
    """Classify every catalog record's visual evidence for downstream readers.

    Derived, never stored: consumers get one authoritative classification from
    the owner reader instead of each interpreting `visual_extracted`, which a
    v1 record cannot attribute to any extractor generation (#229). A record
    whose receipt cannot be read is reported as unreadable rather than dropped
    — a silently missing row would read as "nothing to regenerate".
    """
    catalog = database.get("pptx_catalog")
    if not isinstance(catalog, list):
        return []
    selection: list[dict[str, object]] = []
    for index, record in enumerate(catalog):
        if not isinstance(record, dict):
            continue
        entry: dict[str, object] = {
            "index": index,
            "pptx_path": record.get("pptx_path"),
        }
        try:
            classification = classify_pptx_visual_evidence(
                record,
                extractor_schema_version=PPTX_EXTRACTION_SCHEMA_VERSION,
                pipeline_version=PPTX_EXTRACTION_PIPELINE_VERSION,
            )
        except TrackingDatabaseError as exc:
            entry["classification"] = None
            entry["needs_extraction"] = True
            entry["error"] = str(exc)
        else:
            entry["classification"] = classification
            entry["needs_extraction"] = pptx_visual_evidence_needs_extraction(
                classification
            )
        selection.append(entry)
    return selection


def execute(path: Path) -> dict[str, object]:
    snapshot = snapshot_tracking_database(path)
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
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "ok": True,
        "database_path": str(snapshot.path),
        "sha256": snapshot.sha256,
        "database": database,
        "pptx_visual_evidence": {
            "extractor_schema_version": PPTX_EXTRACTION_SCHEMA_VERSION,
            "pipeline_version": PPTX_EXTRACTION_PIPELINE_VERSION,
            "records": pptx_visual_evidence_selection(database),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("database", type=Path)
    args = parser.parse_args(argv)
    try:
        report = execute(args.database)
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
        print(f"tracking-database read failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
