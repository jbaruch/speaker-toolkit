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
from collections import Counter
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
    PPTX_CATALOG_RECORD_SCHEMA_VERSION,
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
MUTATION_PLAN_SCHEMA_VERSION = 1
# The owner writer's missing-value sentinel, restated here because the plan
# is JSON handed to that writer rather than a Python call into it.
MISSING_MARKER = {"$missing": True}

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


# Every disposition that leaves a talk bound to a deck nothing proved.
# `binding_unassessable` belongs here too: "the assessment could not run" is the
# strongest form of "not proven", and leaving those bound while the plan reads
# as complete is the failure the plan exists to prevent.
SEVERABLE_DISPOSITIONS = frozenset(
    {
        DISPOSITION_CONTRADICTED,
        DISPOSITION_REVIEW_REQUIRED,
        DISPOSITION_UNPROVEN,
        DISPOSITION_UNASSESSABLE,
    }
)


def _catalog_record(
    catalog: Sequence[Any],
    row: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    """Resolve a report row back to the exact catalog record it describes.

    By INDEX, never by path. A row's `pptx_path` is the deck-facts reading's
    normalized text — whitespace collapsed, length-capped — so a stored path
    carrying internal double spaces would not match the catalog key, and the
    binding would drop out of the plan without a word.
    """
    index = row.get("index")
    if not isinstance(index, int) or isinstance(index, bool):
        return None
    if index < 0 or index >= len(catalog):
        return None
    record = catalog[index]
    return record if isinstance(record, Mapping) else None


def _writer_refusal(
    record: Mapping[str, Any],
    stored_talk: object,
    talks: Mapping[Any, Any],
) -> str | None:
    """Say why the owner writer would refuse this row, or None if it would not.

    Checked while BUILDING the plan, not left to the apply. A plan is a file a
    human reviews and then runs; one that looks actionable and dies partway
    through on a precondition the builder could have seen is worse than one that
    says up front which rows it cannot address.

    Mirrors the writer's own guards — `_nonempty` on the path, `_talk_by_filename`
    on the talk — so a row that survives here is a row the writer accepts.
    """
    pptx_path = record.get("pptx_path")
    if (
        not isinstance(pptx_path, str)
        or not pptx_path.strip()
        or pptx_path != pptx_path.strip()
    ):
        return "catalog row has no usable pptx_path"
    if not isinstance(stored_talk, str) or not stored_talk.strip():
        return "no stored binding this plan can address"
    if stored_talk not in talks:
        return f"binds a talk no record carries ({stored_talk})"
    return None


def sever_mutations(
    database: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build the owner plan that breaks every binding this sweep could not prove.

    One mutation per unproven binding, each carrying the exact prior catalog row
    and the talk's exact prior `pptx_path`. The preconditions are the point: the
    plan is built from an assessment made at one moment and applied at another,
    so anything that moved in between must make the apply fail rather than
    silently sever a binding nobody assessed.

    Confirmed bindings are absent by construction. Proving a binding is
    `record_pptx`'s job — it writes the assessment alongside the receipt — and a
    sever plan that also carried proofs would be two decisions in one file.

    Returns `(mutations, unseverable)`. A row whose binding cannot be turned
    into a mutation — a malformed catalog entry, a path no stored row carries —
    is reported rather than skipped: a plan that quietly drops what it cannot
    handle reads as complete while leaving a binding in place.
    """
    talks = {
        talk.get("filename"): talk
        for talk in (database.get("talks") or [])
        if isinstance(talk, Mapping)
    }
    catalog = list(database.get("pptx_catalog") or [])
    mutations: list[dict[str, Any]] = []
    # Several unproven rows can name ONE talk — the live catalog has exactly
    # that, two UberConf 2024 decks bound to the same delivery. The talk's
    # `pptx_path` is cleared by whichever sever reaches it first, so every later
    # sever for that talk must expect it already gone. Snapshotting the stored
    # value for all of them makes the second mutation fail a precondition the
    # first one made false, and the whole plan aborts.
    cleared_talks: set[str] = set()
    unseverable: list[dict[str, Any]] = []
    for row in rows:
        if row.get("disposition") not in SEVERABLE_DISPOSITIONS:
            continue
        record = _catalog_record(catalog, row)
        stored_talk = row.get("stored_talk_filename")
        refusal = (
            "no catalog row at this index"
            if record is None
            else _writer_refusal(record, stored_talk, talks)
        )
        if record is None or refusal is not None:
            unseverable.append(
                {
                    "index": row.get("index"),
                    "pptx_path": (
                        record.get("pptx_path") if isinstance(record, Mapping) else None
                    ),
                    "stored_talk_filename": stored_talk,
                    "disposition": row.get("disposition"),
                    "reason": refusal,
                }
            )
            continue
        pptx_path = record["pptx_path"]
        assert isinstance(stored_talk, str)  # guaranteed by _writer_refusal
        talk = talks.get(stored_talk)
        if stored_talk in cleared_talks:
            expect_talk_pptx_path: Any = MISSING_MARKER
        elif isinstance(talk, Mapping) and "pptx_path" in talk:
            expect_talk_pptx_path = talk["pptx_path"]
        else:
            # A talk that never carried the field expects the missing marker,
            # which is a different precondition from expecting null.
            expect_talk_pptx_path = MISSING_MARKER
        cleared_talks.add(stored_talk)
        mutations.append(
            {
                "kind": "sever_pptx_talk_binding",
                "pptx_path": pptx_path,
                "expect": dict(record),
                "expect_talk_pptx_path": expect_talk_pptx_path,
            }
        )
    return mutations, unseverable


def proof_mutations(
    database: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Build the owner plan that stores the proof behind every confirmed binding.

    A confirmed binding is not yet a proven one. Preflight blocks a row that
    names a talk without an assessment, so the 30 rows this sweep confirms stay
    blocking until the assessment they earned is actually written down.

    Separate from the sever plan on purpose: keeping a binding and breaking one
    are different owner decisions, and a single file carrying both invites
    applying half of what was reviewed.

    The record advances to v3 with `visual_evidence: null`. The v1 rows being
    replaced claim `visual_extracted: true` with no receipt behind it — which
    `classify_pptx_visual_evidence` already reads as unknown-generation evidence,
    never current — so nothing verifiable is discarded, and the reparse
    re-extracts regardless.
    """
    talks = {
        talk.get("filename"): talk
        for talk in (database.get("talks") or [])
        if isinstance(talk, Mapping)
    }
    catalog = list(database.get("pptx_catalog") or [])
    confirmed = [row for row in rows if row.get("disposition") == DISPOSITION_CONFIRMED]
    # Two decks cannot both be one talk's delivery deck, and the live catalog
    # has exactly that pair. The per-deck assessment cannot see it — each deck
    # is assessed alone, and each agrees — so the contradiction is only visible
    # here, across rows. Proving either would assert something the other
    # disproves, so neither is proven and both stay blocking for owner review.
    claims = Counter(
        row.get("stored_talk_filename")
        for row in confirmed
        if isinstance(row.get("stored_talk_filename"), str)
    )
    mutations: list[dict[str, Any]] = []
    for row in confirmed:
        record = _catalog_record(catalog, row)
        assessment = row.get("assessment")
        talk_filename = row.get("stored_talk_filename")
        if record is None or not isinstance(assessment, Mapping):
            continue
        # The same writer preconditions the sever plan checks. A proof the owner
        # writer would refuse is not a proof, and `record_pptx` reads both.
        if _writer_refusal(record, talk_filename, talks) is not None:
            continue
        if claims[talk_filename] != 1:
            continue
        pptx_path = record["pptx_path"]
        talk = talks.get(talk_filename)
        # `candidates_assessed` is this report's own reading aid. The owner gate
        # validates a closed key set, so carrying it would fail the write.
        proof = {
            key: value
            for key, value in assessment.items()
            if key != "candidates_assessed"
        }
        mutations.append(
            {
                "kind": "record_pptx",
                "expect": dict(record),
                "expect_talk_pptx_path": (
                    talk["pptx_path"]
                    if isinstance(talk, Mapping) and "pptx_path" in talk
                    else MISSING_MARKER
                ),
                "record": {
                    "schema_version": PPTX_CATALOG_RECORD_SCHEMA_VERSION,
                    "pptx_path": pptx_path,
                    "talk_filename": talk_filename,
                    "matched": True,
                    "slide_count": record.get("slide_count"),
                    "visual_extracted": False,
                    "visual_evidence": None,
                    "identity_assessment": proof,
                },
            }
        )
    return mutations


def execute(
    value: str | Path,
    *,
    dispositions: Sequence[str] = (),
    emit_mutations: bool = False,
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
    reported = frozenset(dispositions)
    selected = (
        rows
        if not reported
        else [row for row in rows if row["disposition"] in reported]
    )
    report: dict[str, Any] = {
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
    if emit_mutations:
        # Built from every row, never from the filtered view: a plan that
        # inherited `--dispositions` would silently sever only what the operator
        # happened to be reading.
        severs, unseverable = sever_mutations(database, rows)
        report["mutation_plan"] = {
            "schema_version": MUTATION_PLAN_SCHEMA_VERSION,
            "mutations": severs,
            # Never empty-by-omission: a row this plan cannot address is named
            # here so a complete-looking plan cannot hide a binding it left.
            "unseverable": unseverable,
        }
        report["proof_plan"] = {
            "schema_version": MUTATION_PLAN_SCHEMA_VERSION,
            "mutations": proof_mutations(database, rows),
        }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("vault", type=Path)
    parser.add_argument(
        "--emit-mutations",
        action="store_true",
        help=(
            "add a mutation_plan severing every binding this sweep could not "
            "prove; built from the whole catalog, never the --dispositions view"
        ),
    )
    parser.add_argument(
        "--dispositions",
        nargs="+",
        choices=DISPOSITIONS,
        default=(),
        help="report only rows with these dispositions; counts stay whole-catalog",
    )
    args = parser.parse_args(argv)
    try:
        report = execute(
            args.vault,
            dispositions=args.dispositions,
            emit_mutations=args.emit_mutations,
        )
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
