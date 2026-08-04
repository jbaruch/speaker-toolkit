#!/usr/bin/env python3
"""Load vault source files for speaker-profile generation.

Reads the rhetoric vault and emits a single JSON payload to stdout containing
all source data needed to construct speaker-profile.json. The skill orchestrator
calls this script once and then aggregates the payload into the profile. Pattern
baselines are selected by exact active catalog/scoring-generation identity and
current persisted evidence artifacts; extractor instrumentation cohorts remain
a separate concern.

Contract
--------
Args:
    vault_root: optional path to vault root. Defaults to
                ~/.claude/rhetoric-knowledge-vault.
    --as-of:    optional timezone-aware ISO-8601 snapshot observation time.
                Defaults to the current UTC time and is normalized to whole
                seconds.

Stdout (JSON):
    {
      "vault_root":        "<absolute path>",
      "config":            { ... }   # tracking-database.json `config` block
      "confirmed_intents": [ ... ]   # projected semantic intent fields
      "talks":             [ ... ]   # all talks
      "processed_talks":   [ ... ]   # talks with status processed* only
      "baseline_talks":    [ ... ]   # exact active pattern-scoring generation
      "excluded_pattern_scoring_talks": [ ... ] # legacy/mismatched generation
      "pattern_scoring_exclusions": [ ... ] # deterministic per-talk reasons
      "pattern_baseline":  { ... }   # exact-cohort count/sum/average + provenance
      "pattern_opportunities": { ... } # deterministic exhaustive per-pattern rows
      "pattern_classification": { ... } # policy-bound deterministic derived fields
      "current_instrumentation_talks": [ ... ]  # current extractor cohort
      "stale_instrumentation_talks": [ ... ]    # pre-epoch extractor cohort
      "baseline_note":     "...",    # exact pattern-cohort semantics
      "instrumentation_note": "...", # extractor cohort is independent
      "summary":           "...",    # rhetoric-style-summary.md contents
      "design_spec":       "..."     # slide-design-spec.md contents (or "")
    }

Exit codes:
    0   success
    1   arguments, vault inputs, catalog, or scoring-generation metadata are
        missing/malformed. Diagnostic message goes to stderr.
"""

from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime, timezone


INGRESS_SCRIPTS = (
    pathlib.Path(__file__).resolve().parents[2] / "vault-ingress" / "scripts"
)
if str(INGRESS_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(INGRESS_SCRIPTS))

# Pyright cannot resolve this sibling script module added to sys.path at runtime.
from adherence_baseline import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    AdherenceBaselineError,
    normalize_as_of,
)
from pattern_cohort_snapshot import (  # noqa: E402
    PatternCohortSnapshotError,
    build_current_pattern_snapshot,
    configured_evidence_freshness_assessor,
)
from pattern_classification_runtime import (  # noqa: E402
    classify_pattern_profile,
    resolve_classification_policy,
)
# Pyright cannot resolve this sibling script module added to sys.path at runtime.
from return_validation import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    PATTERN_SCORING_SCHEMA_VERSION,
    ReturnValidationError,
    load_catalog,
)
# Pyright cannot resolve this sibling script module added to sys.path at runtime.
from tracking_database import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    TrackingDatabaseError,
    assess_tracking_database,
)
# Pyright cannot resolve this sibling script module added to sys.path at runtime.
from tracking_database_io import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    TrackingDatabaseIOError,
    decode_json_object,
    snapshot_tracking_database,
)
# Pyright cannot resolve this sibling script module added to sys.path at runtime.
from vault_root_authority import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    VaultRootAuthorityError,
    materialize_native_authority,
    resolve_vault_root_authority,
)


DEFAULT_VAULT = pathlib.Path.home() / ".claude" / "rhetoric-knowledge-vault"

# Talks processed on or after this date used the current extractor generation.
# This partition supports extractor- and pacing-sensitive analysis only. Pattern
# baseline eligibility is determined independently by exact catalog/scoring
# identity through ``partition_pattern_scoring_cohort``.
INSTRUMENTATION_EPOCH = "2026-07-26"
_CONFIRMED_INTENT_PROFILE_FIELDS = ("pattern", "intent", "rule", "note")


def partition_by_instrumentation(processed_talks, epoch=INSTRUMENTATION_EPOCH):
    """Split processed talks into (current-instrumentation, stale) cohorts.

    A talk with no `processed_date` cannot be dated and is treated as stale — the
    safe direction, since including it would silently contaminate a baseline
    while excluding it only narrows the sample.
    """
    current, stale = [], []
    for talk in processed_talks:
        date = talk.get("processed_date") or ""
        (current if date >= epoch else stale).append(talk)
    return current, stale


def default_as_of(now: datetime | None = None) -> str:
    """Return a canonical UTC whole-second observation timestamp.

    ``now`` is injectable so tests and replay tools never need to depend on the
    wall clock.
    """
    moment = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(moment, datetime):
        raise AdherenceBaselineError("now must be a datetime")
    return normalize_as_of(moment.isoformat())


def project_confirmed_intents(records):
    """Remove tracking-storage metadata from the public profile projection."""
    projected = []
    for record in records:
        projected.append({
            field: record[field]
            for field in _CONFIRMED_INTENT_PROFILE_FIELDS
            if field in record
        })
    return projected


def _parse_args(argv: list[str]) -> tuple[pathlib.Path, str | None]:
    vault_root_arg: str | None = None
    as_of: str | None = None
    index = 1
    while index < len(argv):
        arg = argv[index]
        if arg == "--as-of":
            if as_of is not None:
                raise ValueError("--as-of may be supplied only once")
            index += 1
            if index >= len(argv):
                raise ValueError("--as-of requires a timezone-aware ISO-8601 value")
            as_of = argv[index]
        elif arg.startswith("-"):
            raise ValueError(f"unknown option {arg!r}")
        elif vault_root_arg is None:
            vault_root_arg = arg
        else:
            raise ValueError(f"unexpected extra argument {arg!r}")
        index += 1

    raw_vault_root: object = (
        DEFAULT_VAULT if vault_root_arg is None else vault_root_arg
    )
    return (
        materialize_native_authority(raw_vault_root, authority="cli_root"),
        as_of,
    )


def main(argv: list[str]) -> int:
    try:
        vault_root, supplied_as_of = _parse_args(argv)
        as_of = (
            normalize_as_of(supplied_as_of)
            if supplied_as_of is not None
            else default_as_of()
        )
    except (AdherenceBaselineError, ValueError) as exc:
        print(f"ERROR: invalid arguments: {exc}", file=sys.stderr)
        return 1

    db_path = vault_root / "tracking-database.json"
    if not db_path.exists():
        print(
            f"ERROR: tracking-database.json not found at {db_path} — "
            "vault may be missing or unconfigured.",
            file=sys.stderr,
        )
        return 1
    try:
        database_snapshot = snapshot_tracking_database(db_path)
        db = decode_json_object(database_snapshot)
    except TrackingDatabaseIOError as exc:
        print(f"ERROR: tracking-database.json is malformed: {exc}", file=sys.stderr)
        return 1
    try:
        database_assessment = assess_tracking_database(db)
    except TrackingDatabaseError as exc:
        print(
            f"ERROR: tracking-database.json schema is invalid: {exc}", file=sys.stderr
        )
        return 1
    if not database_assessment.usable:
        print(
            "ERROR: tracking-database.json is not usable by this reader: "
            + ", ".join(database_assessment.reason_codes),
            file=sys.stderr,
        )
        return 1
    try:
        vault_root = resolve_vault_root_authority(
            database_path=db_path,
            config=db.get("config"),
            cli_vault_root=vault_root,
        )
    except VaultRootAuthorityError as exc:
        print(f"ERROR: trusted vault root is invalid: {exc}", file=sys.stderr)
        return 1

    summary_path = vault_root / "rhetoric-style-summary.md"
    if not summary_path.exists():
        print(
            "ERROR: rhetoric-style-summary.md not found. "
            "Run vault-ingress first to process talks.",
            file=sys.stderr,
        )
        return 1
    try:
        summary = summary_path.read_text()
    except OSError as exc:
        print(f"ERROR: cannot read rhetoric-style-summary.md: {exc}", file=sys.stderr)
        return 1

    design_spec_path = vault_root / "slide-design-spec.md"
    try:
        design_spec = design_spec_path.read_text() if design_spec_path.exists() else ""
    except OSError as exc:
        print(f"ERROR: cannot read slide-design-spec.md: {exc}", file=sys.stderr)
        return 1

    talks = db.get("talks", [])
    if not isinstance(talks, list) or any(not isinstance(talk, dict) for talk in talks):
        print(
            "ERROR: tracking-database.json `talks` must be an array of objects",
            file=sys.stderr,
        )
        return 1
    processed_statuses = {"processed", "processed_partial"}
    processed_talks = [t for t in talks if t.get("status") in processed_statuses]
    current_instrumentation, stale_instrumentation = partition_by_instrumentation(
        processed_talks
    )
    try:
        catalog = load_catalog()
        snapshot = build_current_pattern_snapshot(
            talks,
            as_of=as_of,
            evidence_freshness_assessor=configured_evidence_freshness_assessor(
                vault_root,
                db.get("config"),
                catalog=catalog,
            ),
            catalog=catalog,
        )
        baseline_talks = snapshot["baseline_talks"]
        excluded_pattern_talks = snapshot["excluded_pattern_scoring_talks"]
        pattern_scoring_exclusions = snapshot["pattern_scoring_exclusions"]
        pattern_baseline = snapshot["pattern_baseline"]
        pattern_opportunities = snapshot["pattern_opportunities"]
        policy_stamp = resolve_classification_policy(vault_root)
        pattern_classification = classify_pattern_profile(
            baseline_talks,
            policy_stamp,
            catalog=catalog,
        )
    except (
        AdherenceBaselineError,
        PatternCohortSnapshotError,
        ReturnValidationError,
        RuntimeError,
        ValueError,
    ) as exc:
        print(
            "ERROR: cannot build current pattern-scoring/classification "
            f"payload: {exc}",
            file=sys.stderr,
        )
        return 1

    payload = {
        "vault_root": str(vault_root),
        "config": db.get("config", {}),
        "confirmed_intents": project_confirmed_intents(
            db.get("confirmed_intents", [])
        ),
        "talks": talks,
        "processed_talks": processed_talks,
        "baseline_talks": baseline_talks,
        "excluded_pattern_scoring_talks": excluded_pattern_talks,
        "pattern_scoring_exclusions": pattern_scoring_exclusions,
        "pattern_baseline": pattern_baseline,
        "pattern_opportunities": pattern_opportunities,
        "pattern_classification": pattern_classification,
        "current_instrumentation_talks": current_instrumentation,
        "stale_instrumentation_talks": stale_instrumentation,
        "baseline_note": (
            "Pattern-score baselines MUST use baseline_talks only "
            f"({len(baseline_talks)} talks): each record exactly matches the "
            "active pattern catalog fingerprint, scoring schema "
            f"{PATTERN_SCORING_SCHEMA_VERSION}, current "
            "generation contract, and unchanged source-located evidence "
            "artifacts. excluded_pattern_scoring_talks contains "
            f"{len(excluded_pattern_talks)} eligible records with a missing, "
            "legacy, or different valid generation, or stale persisted evidence. "
            "pattern_baseline.as_of is "
            "the snapshot observation time; each talk's processed_date remains "
            "talk-processing metadata and never determines pattern eligibility."
        ),
        "instrumentation_note": (
            "current_instrumentation_talks and stale_instrumentation_talks are "
            "separate extractor/pacing cohorts partitioned at "
            f"{INSTRUMENTATION_EPOCH}. Membership in either instrumentation "
            "cohort does not confer pattern-scoring baseline eligibility."
        ),
        "summary": summary,
        "design_spec": design_spec,
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
