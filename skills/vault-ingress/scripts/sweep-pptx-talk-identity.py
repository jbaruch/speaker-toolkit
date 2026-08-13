#!/usr/bin/env python3
"""Assess every stored PPTX-to-talk binding in the catalog (#176).

`_apply_record_pptx` refuses a NEW binding nothing proved, and preflight blocks
a row whose binding is unproven. Neither assesses the rows already there: they
were bound before any assessment existed, so they are all unproven and all
blocking, and nothing in the toolkit could say which of them are actually
right. This is that sweep.

Every catalog row is assessed against every talk in the vault, from facts both
sides already carry — the deck's path, document properties, and title slide
against the catalog's title, conference, and delivery date. The result is one
disposition per row:

* `binding_confirmed` — the assessment selects the talk the row already names.
* `binding_contradicted` — the assessment selects a DIFFERENT talk. The row is
  feeding one talk's slide counts, OCR, and pattern observations to another.
* `binding_review_required` — candidates are ambiguous or contradictory. Nothing
  is proven either way, which is not the same as the binding being wrong.
* `binding_unproven` — no signal agreed with any talk.
* `unbound_row` — the row names no talk. Reported with its assessment so a
  catalog-only deck is visible, never as a proposal to bind it.

Read-only by construction. The sweep decides nothing and writes nothing; a
disposition is evidence for an owner decision, and severing a binding is a
typed owner mutation made elsewhere.

Signals observed: the path's venue and delivery year, the deck's document
properties, its title slide, and filename similarity. The published-PDF signal
`pptx_talk_identity` accepts is NOT observed — no deterministic deck-to-PDF
binding exists to read, and guessing one would manufacture the evidence the
identity module exists to require.

Determinism: the report depends only on the database's bytes and the decks'
bytes. No clock is consulted, so the same inputs give the same report.

Usage: sweep-pptx-talk-identity.py <vault-root-or-database-path>
       sweep-pptx-talk-identity.py <vault-root> --dispositions binding_contradicted
Stdout: one JSON object; `rows[]` carries the disposition, verdict, reason
        codes, the deck facts that were readable, and the candidate table.
Stderr: one actionable, path-neutral line when the database cannot be read.
Exit 0 when the catalog was assessed, 2 when the database is unusable.
Exit 0 with contradicted rows is the normal "work to do" result — this is a
reporting tool, not a gate. Preflight is the gate.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

from pptx_deck_facts import (
    DECK_FACTS_SCHEMA_VERSION,
    read_deck_identity_facts,
)
from pptx_talk_identity import (
    PPTX_TALK_IDENTITY_SCHEMA_VERSION,
    SIGNAL_UNKNOWN,
    VERDICT_MATCHED,
    VERDICT_REVIEW_REQUIRED,
    PptxTalkIdentityError,
    assess_pptx_talk_identity,
)
from tracking_database import (
    TrackingDatabaseError,
    assess_tracking_database,
)
from tracking_database_io import (
    DATABASE_READ_DIAGNOSTICS,
    DATABASE_READ_FALLBACK,
    TrackingDatabaseIOError,
    decode_json_object,
    snapshot_tracking_database,
)

REPORT_SCHEMA_VERSION = 1
DATABASE_BASENAME = "tracking-database.json"

DISPOSITION_CONFIRMED = "binding_confirmed"
DISPOSITION_CONTRADICTED = "binding_contradicted"
DISPOSITION_REVIEW_REQUIRED = "binding_review_required"
DISPOSITION_UNPROVEN = "binding_unproven"
DISPOSITION_UNBOUND = "unbound_row"
DISPOSITION_UNASSESSABLE = "binding_unassessable"

DISPOSITIONS = (
    DISPOSITION_CONFIRMED,
    DISPOSITION_CONTRADICTED,
    DISPOSITION_REVIEW_REQUIRED,
    DISPOSITION_UNPROVEN,
    DISPOSITION_UNBOUND,
    DISPOSITION_UNASSESSABLE,
)

# Every disposition but these two leaves a talk bound to a deck nothing proved
# it belongs to. Counted separately so the report's headline is the number of
# bindings that must be resolved before a reparse re-derives evidence through
# them, not the number of rows.
RESOLVED_DISPOSITIONS = frozenset({DISPOSITION_CONFIRMED, DISPOSITION_UNBOUND})


def resolve_input(value: str | Path) -> tuple[Path, Path]:
    """Bind a vault root to its canonical database, as preflight does."""
    path = Path(value).expanduser().absolute()
    if path.name.lower() == DATABASE_BASENAME:
        return path.parent, path
    return path, path / DATABASE_BASENAME


def resolve_pptx_source_dir(
    database: Mapping[str, Any],
    *,
    vault_root: Path,
) -> object:
    """Resolve where catalog decks live, falling back to the vault root.

    `config.pptx_source_dir` is optional, and `schemas-db.md` documents that a
    null or absent value falls back to the vault root. Passing the absent value
    straight through would report every deck in such a vault unreadable —
    a configuration default read as universal damage, and one that would put
    every binding into `binding_unproven` on evidence nobody looked for.
    """
    config = database.get("config")
    configured = config.get("pptx_source_dir") if isinstance(config, Mapping) else None
    if isinstance(configured, str) and configured.strip():
        return configured
    return vault_root


def _candidate_talks(database: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every talk carrying a filename, in stored order.

    The whole vault is the candidate set on purpose. Narrowing it first — to
    the same year, or the same conference — would decide the question the
    assessment exists to answer, and would hide exactly the cross-talk
    assignment this sweep looks for.
    """
    talks = database.get("talks")
    if not isinstance(talks, list):
        return []
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for talk in talks:
        if not isinstance(talk, Mapping):
            continue
        filename = talk.get("filename")
        if not isinstance(filename, str) or not filename or filename in seen:
            continue
        seen.add(filename)
        candidates.append(dict(talk))
    return candidates


def _material_assessment(assessment: Any) -> dict[str, Any]:
    """Serialize the assessment with only its material candidates.

    The candidate set is every talk in the vault — 215 of them against 82 rows
    — and a talk sharing no signal with the deck reads as six `unknown`
    verdicts. Emitting those is not evidence, it is 215 rows of noise per deck
    hiding the handful that decided the verdict.

    A candidate is material when any signal reads something. That keeps
    everything a reader needs to re-derive the verdict: the selected candidate
    is material because it agrees, and so is every rival that could have
    contested it, since contesting requires agreement.
    """
    serialized = assessment.as_json()
    candidates = serialized.get("candidates")
    if not isinstance(candidates, list):
        return serialized
    material = [
        candidate
        for candidate in candidates
        if isinstance(candidate, Mapping)
        and any(
            verdict != SIGNAL_UNKNOWN
            for verdict in (candidate.get("signals") or {}).values()
        )
    ]
    serialized["candidates"] = material
    serialized["candidates_assessed"] = len(candidates)
    return serialized


def _disposition(
    verdict: str,
    selected: str | None,
    stored_talk: str | None,
) -> str:
    if stored_talk is None:
        return DISPOSITION_UNBOUND
    if verdict == VERDICT_MATCHED:
        return (
            DISPOSITION_CONFIRMED
            if selected == stored_talk
            else DISPOSITION_CONTRADICTED
        )
    if verdict == VERDICT_REVIEW_REQUIRED:
        return DISPOSITION_REVIEW_REQUIRED
    return DISPOSITION_UNPROVEN


def sweep_catalog(
    database: Mapping[str, Any],
    *,
    pptx_source_dir: object,
) -> list[dict[str, Any]]:
    """Assess every catalog row's stored binding, in stored order.

    A row that cannot be assessed is reported as `binding_unassessable` rather
    than dropped: a missing row would read as a binding with nothing wrong.
    """
    catalog = database.get("pptx_catalog")
    if not isinstance(catalog, list):
        return []
    candidates = _candidate_talks(database)
    rows: list[dict[str, Any]] = []
    for index, record in enumerate(catalog):
        if not isinstance(record, Mapping):
            rows.append(
                {
                    "index": index,
                    "pptx_path": None,
                    "stored_talk_filename": None,
                    "disposition": DISPOSITION_UNASSESSABLE,
                    "reason_codes": ["catalog_row_not_an_object"],
                }
            )
            continue
        stored_talk = record.get("talk_filename")
        stored_talk = stored_talk if isinstance(stored_talk, str) else None
        reading = read_deck_identity_facts(record.get("pptx_path"), pptx_source_dir)
        try:
            assessment = assess_pptx_talk_identity(reading.facts, candidates)
        except PptxTalkIdentityError as exc:
            # The prose names the rejected value, which came out of the
            # database (`no-secrets` -> Logging). Report the closed code.
            rows.append(
                {
                    "index": index,
                    "pptx_path": reading.pptx_path or None,
                    "stored_talk_filename": stored_talk,
                    "disposition": DISPOSITION_UNASSESSABLE,
                    "reason_codes": ["identity_assessment_refused"],
                    "deck_facts_reason_code": reading.reason_code,
                    "error": type(exc).__name__,
                }
            )
            continue
        rows.append(
            {
                "index": index,
                "pptx_path": reading.pptx_path,
                "stored_talk_filename": stored_talk,
                "disposition": _disposition(
                    assessment.verdict,
                    assessment.selected_talk_filename,
                    stored_talk,
                ),
                "verdict": assessment.verdict,
                "artifact_role": assessment.artifact_role,
                "selected_talk_filename": assessment.selected_talk_filename,
                "reason_codes": list(assessment.reason_codes),
                "deck_facts_reason_code": reading.reason_code,
                "deck_slide_count": reading.slide_count,
                "stored_slide_count": record.get("slide_count"),
                "observed_facts": sorted(
                    key for key in reading.facts if key != "pptx_path"
                ),
                # The candidate table, not a summary. It is what makes the
                # verdict checkable by someone who was not here when it ran.
                "assessment": _material_assessment(assessment),
            }
        )
    return rows


def execute(
    value: str | Path,
    *,
    dispositions: Sequence[str] = (),
) -> dict[str, Any]:
    vault_root, database_path = resolve_input(value)
    snapshot = snapshot_tracking_database(database_path)
    database = decode_json_object(snapshot)
    try:
        assessment = assess_tracking_database(database)
    except TrackingDatabaseError as exc:
        # Reason codes are a closed vocabulary; the exception prose is not.
        raise TrackingDatabaseIOError(
            "tracking database owner assessment failed",
            reason_code="owner_assessment_failed",
        ) from exc
    if not assessment.usable:
        raise TrackingDatabaseIOError(
            "tracking database has no usable legacy/current owner state",
            reason_code="owner_state_unusable",
        )
    rows = sweep_catalog(
        database,
        pptx_source_dir=resolve_pptx_source_dir(database, vault_root=vault_root),
    )
    counts = {name: 0 for name in DISPOSITIONS}
    for row in rows:
        counts[str(row["disposition"])] += 1
    selected = (
        rows
        if not dispositions
        else [row for row in rows if row["disposition"] in set(dispositions)]
    )
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "identity_schema_version": PPTX_TALK_IDENTITY_SCHEMA_VERSION,
        "deck_facts_schema_version": DECK_FACTS_SCHEMA_VERSION,
        "ok": True,
        "database_path": str(snapshot.path),
        "sha256": snapshot.sha256,
        "catalog_row_count": len(rows),
        "disposition_counts": counts,
        # The headline: bindings a reparse would carry forward unproven.
        "unresolved_binding_count": sum(
            count for name, count in counts.items() if name not in RESOLVED_DISPOSITIONS
        ),
        "rows": selected,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("vault", type=Path)
    parser.add_argument(
        "--dispositions",
        nargs="+",
        choices=DISPOSITIONS,
        default=(),
        help="report only rows with these dispositions; counts stay whole-catalog",
    )
    args = parser.parse_args(argv)
    try:
        report = execute(args.vault, dispositions=args.dispositions)
    except TrackingDatabaseIOError as exc:
        # Never echo the exception: decoder messages carry the host database
        # path and the rejected key or value verbatim. Route the typed reason
        # code through the shared closed vocabulary instead.
        code, message = DATABASE_READ_DIAGNOSTICS.get(
            exc.reason_code, DATABASE_READ_FALLBACK
        )
        print(
            json.dumps(
                {
                    "schema_version": REPORT_SCHEMA_VERSION,
                    "ok": False,
                    "code": code,
                    "error": message,
                }
            )
        )
        print(f"pptx talk-identity sweep failed: {message}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
