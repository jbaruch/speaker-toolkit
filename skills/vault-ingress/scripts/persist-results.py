#!/usr/bin/env python3
"""Deterministically merge a batch of subagent return JSONs into the tracking DB.

Step 4 (Persist Subagent Results) historically relied on the orchestrator
hand-copying each subagent field into the talk record. Whatever it forgot was
silently dropped: the rich `structured_data` the subagents compute reached the
per-talk analysis files but almost never landed in `tracking-database.json`
(1/196 talks had slide_count, opening_type, etc.). This script removes the human
from the merge loop — every schema-declared field a subagent returns is persisted,
and the queryable scalars are promoted to the talk's top level.

For each return (matched to a talk by `filename`) it:
  1. Validates the complete batch against the shared return and catalog contract,
     requires its filenames to equal every live member of one run/batch claim,
     then matches every return to that talk's active queue generation.
  2. For an analysis return, sets the scalar result fields (status,
     processed_date, rhetoric_notes, areas_for_improvement,
     adherence_assessment, transcript_source, slide_source,
     slides_local_path). The writer-owned run date always supplies
     `processed_date`; a legacy return-side date cannot weaken a
     second-resolution batch stamp. Every terminal result clears the live
     `reprocess_reason` because that field describes only queued work. A skipped
     return otherwise changes only terminal status and queue-claim history;
     prior analysis, provenance, corrective clears and processed date remain
     untouched.
  3. Applies explicit `clear_fields`, then selects merge semantics from the
     return's version. Missing/version-1 returns retain the historical additive
     deep merge. Version 2 snapshot-replaces supplied declared scalars, arrays,
     complete structured maps and verbatim lanes (including empty values), while
     preserving omitted fields. Only the registered `structured_data.extensions`
     namespace remains additive; unknown incoming dictionaries fail closed.
  4. Normalizes `pattern_observations` from the subagent's
     {patterns_detected, antipatterns_detected, pattern_score:{score}} shape into
     the DB's {pattern_ids, antipattern_ids, pattern_score:int} shape, keeping the
     detailed arrays too (Section 15 aggregation reads antipatterns_detected).
  5. Promotes the declared queryable scalars (PROMOTE) to the talk's top level so
     they are directly queryable, not buried in structured_data or rhetoric_notes.
  6. Closes the matched queue lease as completed and preserves its generation
     record, so an older return cannot roll an intentional requeue backward.

It does NOT touch rhetoric-style-summary.md or the analysis files — those are
written elsewhere in Step 4/Step 5. It owns only the tracking-DB merge.

Usage:
    persist-results.py <tracking-database.json> <batch-returns.json>
                       [--run-date YYYY-MM-DD|<ISO-8601 timestamp>]

    batch-returns.json is a JSON array of subagent return objects (the shape in
    references/schemas-db.md -> "Per-Talk Subagent Return Schema"). The DB is
    replaced atomically; a structured JSON summary is printed to stdout:
        {"persisted": <int>, "db_path": "<path>",
         "run_date": "<YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS+00:00>",
         "current_adherence_baseline": {"active_batch_excluded": false, "...": "..."},
         "talks": [{"filename": "...", "status": "...", "promoted": ["..."],
                    "stamped_processed_date": <bool>,
                    "coerced_pattern_score": <bool>}]}
    Diagnostics and errors go to stderr; exit code is non-zero on failure.

    `coerced_pattern_score` is true when the return supplied `pattern_score` as a
    bare int and it was rebuilt into the declared dict. The coercion is reported
    rather than silent so the rate stays visible — a return shape that needs
    fixing this often is a schema problem, not a one-off.

    `stamped_processed_date` is true for every analysis return because the
    writer applied the authoritative batch stamp, and false for skipped returns
    whose prior analysis stamp is intentionally untouched.

    Absent --run-date, the stamp is the current UTC time at second resolution.
    --run-date pins it instead of reading the clock; the whole batch shares one
    stamp so a run that straddles midnight does not split across two. It accepts
    either a bare YYYY-MM-DD or an ISO-8601 timestamp; a timestamp must carry a
    timezone offset and is normalized to UTC at second resolution.

Example:
    persist-results.py ~/.claude/rhetoric-knowledge-vault/tracking-database.json batch-returns.json
"""

import copy
import json
import sys
from datetime import datetime, timezone

from failure_diagnostics import emit_unexpected_failure
from adherence_baseline import (
    AdherenceBaselineError,
    build_current_cohort_baseline,
)
from ingress_contract import (
    TALK_SCHEMA_VERSION,
    validate_talk_record_schemas,
)
from tracking_database import TrackingDatabaseError, require_current_tracking_database
from pattern_evidence import (
    PatternEvidenceError,
    admit_return_artifacts,
    assess_batch_artifact_capabilities,
    canonicalize_return_evidence,
    return_evidence_claim,
)
from video_evidence import VideoEvidenceAssessment
from return_validation import (
    ADDITIVE_MAP,
    ANALYSIS_STATUSES,
    CURRENT_PATTERN_SCORING_GENERATION_STATUS,
    IMAGE_SOURCE_GROUP,
    LEGACY_QUEUE_CLAIM_SCHEMA_VERSION,
    LEGACY_RETURN_SCHEMA_VERSION,
    LEGACY_UNBASELINEABLE_SCORING_STATUS,
    PATTERN_SCORING_SCHEMA_VERSION,
    PREVIOUS_QUEUE_CLAIM_SCHEMA_VERSION,
    RETURN_SCHEMA_VERSION,
    SNAPSHOT_RETURN_SCHEMA_VERSIONS,
    SOURCE_LOCATED_RETURN_SCHEMA_VERSIONS,
    STRUCTURED_FIELD_POLICIES,
    UNSCORED_PATTERN_SCORING_GENERATION_STATUS,
    ReturnValidationError,
    assess_current_persisted_pattern_evidence_freshness,
    assess_scoring_generation,
    canonical_persisted_pattern_observations,
    canonical_return_sha256,
    load_catalog,
    normalize_processing_stamp,
    resolve_return_schema_version,
    validate_batch_claims_against_talks,
    validate_claim_against_talk,
    validate_batch,
    validate_persisted_v2_analysis_state,
    validate_v2_structured_policy_shapes,
    validate_verbatim_examples,
    validate_v5_adherence_opportunity,
)
from tracking_database_io import (
    TrackingDatabaseIOError,
    TrackingDatabaseSnapshot,
    decode_json_object,
    snapshot_tracking_database,
    write_json_object,
)
from vault_root_authority import (
    VaultRootAuthorityError,
    materialize_native_authority,
    resolve_vault_root_authority,
)


def default_stamp(now=None):
    """Resolve the default run stamp: UTC, second resolution.

    `now` is injectable so a test can freeze it; the production call site passes
    nothing and reads the clock once per batch. Second resolution rather than
    day: a day-granular stamp cannot answer "was this talk scored before or
    after the fix that shipped this afternoon".
    """
    moment = datetime.now(timezone.utc) if now is None else now
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def normalize_stamp(value):
    """Normalize a --run-date value to the stamp to store, or raise ValueError.

    A bare YYYY-MM-DD passes through unchanged, so a caller can still pin a day
    and records written before second resolution stay readable. A timestamp must
    carry a timezone — ordering talks against a same-day fix is the whole point
    of the stamp, and a naive timestamp from another machine cannot be ordered
    against one from this one — and is normalized to UTC at second resolution.
    """
    return normalize_processing_stamp(value)


# Tracking-DB talk-record schema version, stamped by this writer on every merge.
#
# v1 is the implicit, unversioned shape every pre-2026-07-28 record carries:
# `transcript_source` was documented as always present, though 95 of 209 records
# never had it.
# v2 documents `transcript_source` as optional and gives ABSENT a meaning —
# provenance unknown, distinct from the explicit value `none` (no transcript).
#
# v3 adds optional scoring-generation identity fields and explicit corrective
# clear semantics. Existing readers ignore the new metadata; older records stay
# readable and acquire generation identity on their next validated analysis. The
# two historical v3 lineages are unified by v4's source-located evidence ledger.
# V5 adds exhaustive applicability/outcome state and opportunity identity. The
# shared constant lives in ingress_contract.py so readers reject future records
# against the same boundary this owner migrates.

# Queryable scalars promoted from the subagent return onto the talk's top level.
# (top_level_field, dotted source path within the return). To add a new queryable
# scalar, add it here AND to the return schema — never reintroduce hand-mapping.
PROMOTE = [
    ("slide_count", "structured_data.slide_count"),
    ("slide_design_style", "structured_data.slide_design_style"),
    ("illustration_style", "structured_data.illustration_style"),
    ("opening_type", "structured_data.opening_type"),
    ("closing_type", "structured_data.closing_type"),
    ("narrative_arc_type", "structured_data.narrative_arc_type"),
    ("audience_interaction_count", "structured_data.audience_interaction_count"),
    ("co_presenter", "structured_data.co_presenter"),
    ("co_presenters", "structured_data.co_presenters"),
    ("delivery_language", "structured_data.delivery_language"),
]

# NOT in PROMOTE: `pattern_score`. It is set explicitly in merge_talk from
# resolve_pattern_score, because a dotted-path lookup silently yields nothing
# when a subagent sends the bare int instead of the declared dict.

# Scalar result fields copied verbatim when present in the return.  The
# processing stamp is writer-owned and handled separately below: a subagent's
# legacy `processed_date` cannot override the batch timestamp.
SCALARS = [
    "status",
    "rhetoric_notes",
    "areas_for_improvement",
    "adherence_assessment",
    "transcript_source",
    "transcript_path",
    "slide_source",
    "slides_local_path",
]

PROMOTED_BY_STRUCTURED_KEY = {
    path.removeprefix("structured_data."): field
    for field, path in PROMOTE
    if path.startswith("structured_data.")
    and "." not in path.removeprefix("structured_data.")
}


def is_empty(v):
    # Note: False and 0 are meaningful values (co_presenter: false, a 0 count),
    # so they are NOT empty — only None and empty string/list/dict are.
    return v is None or v == "" or v == [] or v == {}


def dig(obj, dotted):
    cur = obj
    for key in dotted.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def deep_merge(dst, src):
    """Additive deep merge: recurse into dicts; new non-empty values win; never
    clobber existing data with empty/missing values."""
    if not isinstance(src, dict):
        return src if not is_empty(src) else dst
    if not isinstance(dst, dict):
        dst = {}
    for key, val in src.items():
        if isinstance(val, dict) and isinstance(dst.get(key), dict):
            dst[key] = deep_merge(dst[key], val)
        elif is_empty(val):
            continue  # don't overwrite with nothing
        else:
            dst[key] = val
    return dst


def require_stored_mapping(talk, field):
    """Return a persisted analysis block, rejecting wrong-typed prior state."""
    if field not in talk or talk[field] is None:
        return {}
    value = talk[field]
    if not isinstance(value, dict):
        raise ValueError(
            f"stored {field} is a {type(value).__name__}; refusing to merge a "
            "new analysis into malformed prior state"
        )
    return value


def merge_structured_v2(existing, incoming):
    """Apply the declared v2 structured-data policies to supplied fields only."""
    present_group = IMAGE_SOURCE_GROUP.intersection(incoming)
    if present_group and present_group != IMAGE_SOURCE_GROUP:
        missing = sorted(IMAGE_SOURCE_GROUP - present_group)
        raise ValueError(
            f"snapshot return image-source group is incomplete; missing {missing}"
        )

    validate_v2_structured_policy_shapes(incoming)
    merged = copy.deepcopy(existing)
    for field, value in incoming.items():
        policy = STRUCTURED_FIELD_POLICIES.get(field)
        if policy is None:
            # Future scalar/array fields cannot retain stale dictionary children,
            # so replacing them is safe while their formal policy is reviewed.
            merged[field] = copy.deepcopy(value)
            continue
        if policy == ADDITIVE_MAP:
            current = merged.get(field, {})
            if not isinstance(current, dict):
                raise ValueError(
                    f"stored structured_data.{field} is a "
                    f"{type(current).__name__}; additive namespaces must be objects"
                )
            merged[field] = deep_merge(copy.deepcopy(current), copy.deepcopy(value))
        else:
            merged[field] = copy.deepcopy(value)
    return merged


def merge_verbatim_v2(existing, incoming):
    """Snapshot-replace each supplied v2–v5 verbatim lane, including []."""
    validate_verbatim_examples(incoming, reject_unknown=True)
    merged = copy.deepcopy(existing)
    for field, value in incoming.items():
        merged[field] = copy.deepcopy(value)
    return merged


def _normalized_pattern_fields(
    patterns, antipatterns, not_evaluable, evidence_sources, score
):
    return normalize_pattern_observations(
        {},
        copy.deepcopy(patterns),
        copy.deepcopy(antipatterns),
        copy.deepcopy(not_evaluable),
        copy.deepcopy(evidence_sources),
        score,
    )


def _sync_v2_promotions(talk, incoming_structured):
    """Make every supplied promoted field exactly match its nested snapshot."""
    promoted = []
    for field, path in PROMOTE:
        structured_field = path.removeprefix("structured_data.")
        if structured_field in incoming_structured:
            talk[field] = copy.deepcopy(talk["structured_data"][structured_field])
            promoted.append(field)
    return promoted


def validate_effective_v2_state(
    talk, incoming_structured, *, pattern_snapshot_replaced
):
    """Validate a post-v2–v5 snapshot candidate before publication."""
    validate_talk_record_schemas([talk])
    try:
        validate_persisted_v2_analysis_state(talk)
    except ReturnValidationError as exc:
        raise ValueError(f"effective merged analysis is invalid: {exc}") from exc

    structured = require_stored_mapping(talk, "structured_data")

    for field, path in PROMOTE:
        structured_field = path.removeprefix("structured_data.")
        if structured_field in incoming_structured:
            nested = structured[structured_field]
            if field not in talk or talk[field] != nested:
                raise ValueError(
                    f"effective merged analysis has divergent promoted field {field}"
                )

    if not pattern_snapshot_replaced:
        raise ValueError("snapshot return did not replace pattern_observations")


def _delete_path(obj, parts):
    """Delete an existing dotted path. Missing paths are valid idempotent clears."""
    current = obj
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    if not isinstance(current, dict):
        return False
    return current.pop(parts[-1], None) is not None


def apply_clear_fields(talk, paths):
    """Apply validated corrective clears and keep promoted scalars consistent."""
    cleared = []
    for path in paths or []:
        parts = path.split(".")
        if _delete_path(talk, parts):
            cleared.append(path)
        if len(parts) == 2 and parts[0] == "structured_data":
            promoted = PROMOTED_BY_STRUCTURED_KEY.get(parts[1])
            if promoted and talk.pop(promoted, None) is not None:
                cleared.append(promoted)
        if (
            len(parts) == 2
            and parts[0] == "pattern_observations"
            and parts[1] == "pattern_score"
            and talk.pop("pattern_score", None) is not None
        ):
            cleared.append("pattern_score")
    return cleared


def completion_timestamp(run_date):
    """Return a queue-compatible timestamp from a date or timestamp run stamp."""
    if len(run_date) == 10:
        return f"{run_date}T00:00:00+00:00"
    return run_date


def close_queue_claim(talk, ret, run_date):
    claim = talk["_queue_claim"]
    if claim.get("schema_version") == LEGACY_QUEUE_CLAIM_SCHEMA_VERSION:
        claim["schema_version"] = PREVIOUS_QUEUE_CLAIM_SCHEMA_VERSION
    claim["state"] = "completed"
    claim["released_at"] = completion_timestamp(run_date)
    claim["release_reason"] = "return_persisted"
    claim["result_status"] = ret["status"]
    claim["result_payload_sha256"] = canonical_return_sha256(ret)


def require_mapping(ret, field):
    """Return `ret[field]` as a dict, or None when absent. Raise on any other type.

    The three blocks carrying a return's actual content — `structured_data`,
    `verbatim_examples`, `pattern_observations` — were each guarded by a bare
    `isinstance(..., dict)` test that SKIPPED a malformed block and reported
    success. A return whose `structured_data` arrived as a list lost the entire
    analysis and still exited 0.

    That is the silent-drop shape this script exists to eliminate, so a wrong
    type is now loud. Absent stays legal: a return need not carry every block.
    """
    if field not in ret or ret[field] is None:
        return None
    value = ret[field]
    if not isinstance(value, dict):
        raise ValueError(
            f"{field} is a {type(value).__name__}, but the return schema declares "
            f"it a JSON object. Refusing to skip it silently — a dropped {field} "
            "loses the whole block while the merge still reports success."
        )
    return value


def require_detections(observations, field):
    """Return a detection array as a list of dicts, or None when absent.

    Both consumers assume list-of-dicts: one calls `len()` on it to recompute the
    score, the other calls `p.get("pattern_id")` on each element. A list of bare
    id STRINGS — a plausible return shape — raises AttributeError mid-merge and
    kills the script before it prints its JSON, and a plain string makes `len()`
    count characters as detections.
    """
    if field not in observations or observations[field] is None:
        return None
    value = observations[field]
    if not isinstance(value, list):
        raise ValueError(
            f"pattern_observations.{field} is a {type(value).__name__}, but the "
            "return schema declares it an array of detection objects."
        )
    bad = next((e for e in value if not isinstance(e, dict)), None)
    if bad is not None:
        raise ValueError(
            f"pattern_observations.{field} contains {bad!r} "
            f"({type(bad).__name__}); every element must be an object carrying a "
            "`pattern_id`."
        )
    return value


def resolve_pattern_score(observations, patterns, antipatterns):
    """Single source of truth for the talk's `pattern_score`.

    Returns (score, coerced); `score` is None when the return carries none.

    Every defect here came from TWO functions independently deciding what a valid
    score was — one normalizing the nested DB value, the other resolving the
    promoted top-level scalar through a dotted path. Each review round tightened
    one and left the other, so they disagreed in a new way each time. One
    function decides now, and both consumers read its answer.

    Subagents emit `"pattern_score": 19` instead of the declared
    `{"patterns_used": N, "antipatterns_detected": M, "score": N-M}` on roughly a
    third of returns. The schema invites it twice over: the field is NAMED for a
    number but holds a dict, and `antipatterns_detected` means an array of
    objects one level up and an integer count inside `pattern_score`. Restating
    the requirement in the brief has not moved the rate across four batches, so
    the tooling absorbs the variant — and recomputes rather than trusting it.

    The score is count(patterns) minus count(antipatterns), so it is an INTEGER
    by construction. `True` satisfies `isinstance(x, int)` in Python and a float
    looks numeric; neither is a score.
    """
    if "pattern_score" not in observations or observations["pattern_score"] is None:
        return None, False

    raw = observations["pattern_score"]
    coerced = not isinstance(raw, dict)
    nested = raw if coerced else raw.get("score")
    if nested is None:
        if coerced:
            return None, False
        # A `pattern_score` object present but missing `score` is malformed, not
        # absent: the declared shape carries the number, so silently returning
        # "no score" here would drop it exactly like the bare int used to.
        raise ValueError(
            "pattern_score is an object with no `score` key "
            f"(got keys {sorted(raw)}). Emit "
            '{"patterns_used": N, "antipatterns_detected": M, "score": N-M}.'
        )

    label = "pattern_score" if coerced else "pattern_score.score"
    if isinstance(nested, bool) or not isinstance(nested, int):
        raise ValueError(
            f"{label} is {nested!r} ({type(nested).__name__}). It must be an "
            "integer — the score is count(patterns) minus count(antipatterns), "
            "so a float, a string and a bool are all wrong. Emit "
            '{"patterns_used": N, "antipatterns_detected": M, "score": N-M}.'
        )

    # Only the coerced form is cross-checked. It is the shape that arrived
    # without its accompanying counts, so the arrays are the only evidence that
    # the number is right.
    if coerced:
        used, against = len(patterns or []), len(antipatterns or [])
        if used - against != nested:
            raise ValueError(
                f"pattern_score is the bare int {nested}, but patterns_detected "
                f"({used}) minus antipatterns_detected ({against}) is "
                f"{used - against}. Refusing to guess which is right."
            )
    return nested, coerced


def normalize_pattern_observations(
    existing, patterns, antipatterns, not_evaluable, evidence_sources, score
):
    """Map the subagent return shape onto the DB shape, keeping both views.

    Takes already-validated inputs and decides nothing about their shape, so it
    cannot drift from the validator the way its predecessor did.
    """
    obs = dict(existing) if isinstance(existing, dict) else {}
    if patterns is not None:
        obs["patterns_detected"] = patterns
        obs["pattern_ids"] = [
            p.get("pattern_id") for p in patterns if p.get("pattern_id")
        ]
    if antipatterns is not None:
        obs["antipatterns_detected"] = antipatterns
        obs["antipattern_ids"] = [
            p.get("pattern_id") for p in antipatterns if p.get("pattern_id")
        ]
    if not_evaluable is not None:
        obs["not_evaluable"] = not_evaluable
        obs["not_evaluable_ids"] = [
            item.get("pattern_id") for item in not_evaluable if item.get("pattern_id")
        ]
    if evidence_sources is not None:
        obs["evidence_sources"] = evidence_sources
    if score is not None:
        obs["pattern_score"] = score
    return obs


def merge_talk(
    talk,
    ret,
    run_date=None,
    catalog_fingerprint=None,
    *,
    enforce_queue_claim=False,
    catalog=None,
    canonical_ret=None,
    artifact_capabilities=None,
):
    """Merge one return into its talk.

    Returns (promoted, stamped, coerced_score, cleared).

    Every block is validated BEFORE anything is written, so a malformed return
    leaves the talk untouched rather than half-merged.  When supplied,
    `run_date` is the authoritative processing stamp for every analysis return;
    the legacy return-side `processed_date` is advisory only.  The clock is
    never read inside the merge.
    """
    validate_talk_record_schemas([talk])
    return_schema_version = resolve_return_schema_version(ret)
    normalized_run_date = normalize_stamp(run_date) if run_date else None
    if enforce_queue_claim and normalized_run_date is None:
        raise ValueError(
            "run_date is required when closing a queue claim so released_at is "
            "deterministic"
        )
    if enforce_queue_claim:
        validate_claim_against_talk(
            talk, ret, artifact_capabilities=artifact_capabilities
        )

    if return_schema_version in SOURCE_LOCATED_RETURN_SCHEMA_VERSIONS:
        if not isinstance(canonical_ret, dict):
            raise ValueError(
                f"return-schema v{return_schema_version} requires source evidence canonicalization "
                "before merge"
            )
        if return_evidence_claim(canonical_ret) != return_evidence_claim(ret):
            raise ValueError("canonical evidence changed model-authored return fields")
        evidence_ret = canonical_ret
        if enforce_queue_claim:
            validate_v5_adherence_opportunity(talk, ret, canonical_ret)
    else:
        evidence_ret = ret

    candidate = copy.deepcopy(talk)
    # A terminal result closes the reason that put this talk in the queue. The
    # claim keeps the prior status as immutable generation evidence; leaving the
    # reason on a processed/skipped record would violate the live talk schema.
    candidate.pop("reprocess_reason", None)
    if ret.get("status") not in ANALYSIS_STATUSES:
        # A skipped attempt carries no new analysis. Preserve the prior
        # processed stamp, source provenance, content blocks and corrective
        # clears; only the terminal outcome and its queue-claim history change.
        candidate["status"] = ret["status"]
        if enforce_queue_claim:
            close_queue_claim(candidate, ret, normalized_run_date)
        talk.clear()
        talk.update(candidate)
        return [], False, False, []

    returned_stamp = ret.get("processed_date")
    if normalized_run_date and not is_empty(returned_stamp):
        normalized_returned_stamp = normalize_stamp(returned_stamp)
        if (
            len(normalized_returned_stamp) > 10
            and normalized_returned_stamp != normalized_run_date
        ):
            raise ValueError(
                "return processed_date is an explicit timestamp "
                f"{normalized_returned_stamp!r} that conflicts with authoritative "
                f"batch run_date {normalized_run_date!r}"
            )

    structured = require_mapping(ret, "structured_data")
    verbatim = require_mapping(ret, "verbatim_examples")
    observations = require_mapping(evidence_ret, "pattern_observations")
    observation_values = observations or {}
    patterns = require_detections(observation_values, "patterns_detected")
    antipatterns = require_detections(observation_values, "antipatterns_detected")
    not_evaluable = require_detections(observation_values, "not_evaluable")
    evidence_sources = observation_values.get("evidence_sources")
    resolved_catalog = catalog or load_catalog()
    if (
        catalog_fingerprint is not None
        and catalog_fingerprint != resolved_catalog.fingerprint
    ):
        raise ValueError(
            "catalog_fingerprint does not match the catalog used to assess the return"
        )
    scoring_assessment = assess_scoring_generation(evidence_ret, resolved_catalog)
    if (
        return_schema_version == RETURN_SCHEMA_VERSION
        and not scoring_assessment.current
    ):
        raise ValueError(
            f"return-schema v{return_schema_version} cannot satisfy the "
            "current scoring generation: "
            f"{list(scoring_assessment.reasons)}"
        )
    patterns = scoring_assessment.patterns_detected
    antipatterns = scoring_assessment.antipatterns_detected
    score, coerced_score = resolve_pattern_score(
        observation_values, patterns, antipatterns
    )

    if return_schema_version in SNAPSHOT_RETURN_SCHEMA_VERSIONS:
        # Validate persisted block types before a clear could conceal malformed
        # structured state, then apply every operation to the isolated candidate.
        # Verbatim and pattern blocks are supplied snapshots in every valid v2–v5
        # analysis, so they may repair legacy array containers atomically.
        require_stored_mapping(candidate, "structured_data")

    cleared = apply_clear_fields(candidate, ret.get("clear_fields"))
    candidate["schema_version"] = TALK_SCHEMA_VERSION
    for f in SCALARS:
        if f in ret and (
            return_schema_version in SNAPSHOT_RETURN_SCHEMA_VERSIONS
            or not is_empty(ret[f])
        ):
            candidate[f] = copy.deepcopy(ret[f])
    if (
        return_schema_version in SOURCE_LOCATED_RETURN_SCHEMA_VERSIONS
        and "adherence_comparison" in ret
    ):
        candidate["adherence_comparison"] = copy.deepcopy(ret["adherence_comparison"])
    elif return_schema_version in SNAPSHOT_RETURN_SCHEMA_VERSIONS:
        # A v2–v4 replay is archival prose, never an authenticated current
        # comparison. Snapshot replacement therefore clears any stale
        # comparison left by an earlier generation.
        candidate.pop("adherence_comparison", None)
    # A single owner supplies one exact stamp for every member.  This prevents a
    # return's day-granular timestamp from defeating a second-resolution batch
    # stamp and keeps processed_date, queue release, and rendered provenance in
    # lockstep.  Direct non-writer calls without run_date retain legacy support
    # for a canonical return-side timestamp.
    stamped = False
    if normalized_run_date:
        candidate["processed_date"] = normalized_run_date
        stamped = True
    elif not is_empty(ret.get("processed_date")):
        candidate["processed_date"] = normalize_stamp(ret["processed_date"])
    if structured is not None:
        if return_schema_version in SNAPSHOT_RETURN_SCHEMA_VERSIONS:
            candidate["structured_data"] = merge_structured_v2(
                require_stored_mapping(candidate, "structured_data"), structured
            )
        else:
            candidate["structured_data"] = deep_merge(
                candidate.get("structured_data") or {}, structured
            )
        if (
            return_schema_version == LEGACY_RETURN_SCHEMA_VERSION
            and "video_extraction" in structured
        ):
            # This owner-generated schema is a complete manifest, not a bag of
            # independently additive observations. Replacement prevents v1/v2
            # keys such as `output_pdf` from contaminating a validated v3 record.
            candidate["structured_data"]["video_extraction"] = copy.deepcopy(
                structured["video_extraction"]
            )
    if verbatim is not None:
        if return_schema_version in SNAPSHOT_RETURN_SCHEMA_VERSIONS:
            existing_verbatim = candidate.get("verbatim_examples")
            candidate["verbatim_examples"] = merge_verbatim_v2(
                existing_verbatim if isinstance(existing_verbatim, dict) else {},
                verbatim,
            )
        else:
            candidate["verbatim_examples"] = deep_merge(
                candidate.get("verbatim_examples") or {}, verbatim
            )
    if observations is not None:
        if return_schema_version in SNAPSHOT_RETURN_SCHEMA_VERSIONS:
            candidate["pattern_observations"] = (
                canonical_persisted_pattern_observations(
                    evidence_ret, resolved_catalog, scoring_assessment
                )
            )
        elif observations:
            candidate["pattern_observations"] = normalize_pattern_observations(
                candidate.get("pattern_observations"),
                patterns,
                antipatterns,
                not_evaluable,
                evidence_sources,
                score,
            )

    if return_schema_version not in SOURCE_LOCATED_RETURN_SCHEMA_VERSIONS:
        persisted_observations = candidate.get("pattern_observations")
        if isinstance(persisted_observations, dict):
            persisted_observations.pop("evidence_schema_version", None)
            for lane in ("patterns_detected", "antipatterns_detected"):
                detections = persisted_observations.get(lane)
                if not isinstance(detections, list):
                    continue
                for detection in detections:
                    if isinstance(detection, dict):
                        detection["evidence_citations"] = []

    if return_schema_version in SNAPSHOT_RETURN_SCHEMA_VERSIONS:
        promoted = _sync_v2_promotions(candidate, structured or {})
    else:
        promoted = []
        for field, path in PROMOTE:
            val = dig(ret, path)
            if not is_empty(val):
                candidate[field] = val
                promoted.append(field)
    # `pattern_score` is set from the resolved value rather than dug out of the
    # return. The dotted path `pattern_observations.pattern_score.score` is what
    # silently dropped the scalar whenever a subagent sent the bare int, because
    # `dig` returns None on an int — the promoted scalar and the nested value
    # must come from one decision, not two lookups.
    if score is not None:
        candidate["pattern_score"] = score
        promoted.append("pattern_score")
    elif (
        return_schema_version in SNAPSHOT_RETURN_SCHEMA_VERSIONS
        and observations is not None
    ):
        candidate.pop("pattern_score", None)
    if ret.get("status") in ANALYSIS_STATUSES:
        if scoring_assessment.current:
            candidate["pattern_scoring_generation_status"] = (
                CURRENT_PATTERN_SCORING_GENERATION_STATUS
            )
            candidate["pattern_scoring_generation_reasons"] = []
            candidate["pattern_scoring_schema_version"] = PATTERN_SCORING_SCHEMA_VERSION
            candidate["pattern_catalog_fingerprint"] = resolved_catalog.fingerprint
        else:
            candidate["pattern_scoring_generation_status"] = (
                LEGACY_UNBASELINEABLE_SCORING_STATUS
            )
            candidate["pattern_scoring_generation_reasons"] = list(
                scoring_assessment.reasons
            )
            candidate.pop("pattern_scoring_schema_version", None)
            candidate.pop("pattern_catalog_fingerprint", None)
    if return_schema_version in SNAPSHOT_RETURN_SCHEMA_VERSIONS:
        validate_effective_v2_state(
            candidate,
            structured or {},
            pattern_snapshot_replaced=observations is not None,
        )
    if enforce_queue_claim:
        close_queue_claim(candidate, ret, normalized_run_date)
    talk.clear()
    talk.update(candidate)
    return promoted, stamped, coerced_score, cleared


def atomic_write_json(
    path,
    payload,
    *,
    expected_snapshot: TrackingDatabaseSnapshot | None = None,
):
    """Commit JSON against the exact generation captured before validation."""
    try:
        snapshot = expected_snapshot or snapshot_tracking_database(path)
        return write_json_object(snapshot, payload)
    except TrackingDatabaseIOError as exc:
        raise ValueError(
            f"cannot safely write tracking database {path}: {exc}"
        ) from exc


def load_tracking_database(path):
    """Load strict JSON and retain the exact generation used for validation."""
    try:
        snapshot = snapshot_tracking_database(path)
        database = decode_json_object(snapshot)
    except TrackingDatabaseIOError as exc:
        message = str(exc)
        if "tracking database is missing at" in message:
            message = f"tracking database file not found: {path} — {message}"
        print(f"ERROR: {message}", file=sys.stderr)
        sys.exit(1)
    try:
        require_current_tracking_database(database)
    except TrackingDatabaseError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    return database, snapshot


def load_json(path, label):
    """Read and parse a JSON file, failing visibly with operator guidance.

    Turns the two expected input failures — file missing/unreadable and malformed
    JSON — into actionable stderr diagnostics + a non-zero exit, instead of a raw
    Python traceback.
    """
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: {label} file not found: {path}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"ERROR: cannot read {label} file {path}: {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: {label} file {path} is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)


def parse_args(argv):
    """Split positional paths from the optional --run-date flag.

    Returns (db_path, batch_path, run_date). An absent flag resolves to the
    current UTC timestamp at second resolution, so the common call site needs no
    extra argument and the stamp can order talks against a same-day fix.
    """
    args, run_date = [], None
    i = 0
    while i < len(argv):
        if argv[i] == "--run-date":
            if i + 1 >= len(argv):
                print(
                    "ERROR: --run-date requires a YYYY-MM-DD or ISO-8601 value",
                    file=sys.stderr,
                )
                sys.exit(1)
            run_date = argv[i + 1]
            i += 2
            continue
        args.append(argv[i])
        i += 1
    if len(args) != 2:
        print(
            f"Usage: {sys.argv[0]} <tracking-database.json> <batch-returns.json> "
            f"[--run-date YYYY-MM-DD|ISO-8601]",
            file=sys.stderr,
        )
        sys.exit(1)
    if run_date is None:
        # Second resolution, not day. A date-only stamp cannot order a talk
        # against a fix that shipped the same day, which is the normal case
        # during an active reparse: 90 talks in one run all stamped the same
        # date, and the re-check backlog had to flag every one of them because
        # ordering was unknowable.
        run_date = default_stamp()
    else:
        try:
            run_date = normalize_stamp(run_date)
        except ValueError as e:
            print(
                f"ERROR: --run-date must be YYYY-MM-DD or a timezone-aware "
                f"ISO-8601 timestamp: {e}",
                file=sys.stderr,
            )
            sys.exit(1)
    return args[0], args[1], run_date


# Whether the atomic database commit landed. The outer boundary reports this so
# an operator never has to guess whether a late failure replayed a write.
_COMMIT_STATE = {"database_written": False}


def main():
    # Reset per invocation: a stale True from an earlier run in the same process
    # would make a pre-commit failure claim the database was written.
    _COMMIT_STATE["database_written"] = False
    db_path, batch_path, run_date = parse_args(sys.argv[1:])

    try:
        db_path = str(
            materialize_native_authority(
                db_path,
                authority="database_path",
            )
        )
    except VaultRootAuthorityError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    db, database_snapshot = load_tracking_database(db_path)
    raw_config = db.get("config")
    source_roots: dict[str, object] = (
        copy.deepcopy(raw_config) if isinstance(raw_config, dict) else {}
    )
    try:
        vault_root = resolve_vault_root_authority(
            database_path=db_path,
            config=source_roots,
        )
    except VaultRootAuthorityError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    video_evidence_assessment = VideoEvidenceAssessment()
    returns = load_json(batch_path, "batch-returns")
    try:
        catalog = validate_batch(returns)
    except ReturnValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    artifact_capabilities_by_filename = assess_batch_artifact_capabilities(
        db["talks"],
        {
            ret["filename"]
            for ret in returns
            if isinstance(ret, dict) and isinstance(ret.get("filename"), str)
        },
        vault_root=vault_root,
        source_roots=source_roots,
        video_evidence_assessment=video_evidence_assessment,
    )
    try:
        by_name = validate_batch_claims_against_talks(
            db["talks"],
            returns,
            required_state="claimed",
            artifact_capabilities_by_filename=artifact_capabilities_by_filename,
        )
    except ReturnValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    # Resolve every model-authored location against the complete pre-return
    # batch before changing even the in-memory DB. The completed claim keeps a
    # SHA-256 receipt of the exact raw payload; canonical returns are
    # engine-owned enrichments whose claim projection must remain identical.
    canonical_returns = []
    for ret in returns:
        name = ret["filename"]
        try:
            if ret.get("status") in ANALYSIS_STATUSES:
                admit_return_artifacts(
                    vault_root,
                    by_name[name],
                    ret,
                    video_evidence_assessment=video_evidence_assessment,
                )
            if (
                ret.get("status") in ANALYSIS_STATUSES
                and resolve_return_schema_version(ret)
                in SOURCE_LOCATED_RETURN_SCHEMA_VERSIONS
            ):
                canonical = canonicalize_return_evidence(
                    ret,
                    by_name[name],
                    vault_root,
                    catalog,
                    source_roots=source_roots,
                    pattern_scoring_schema_version=(PATTERN_SCORING_SCHEMA_VERSION),
                    video_evidence_assessment=video_evidence_assessment,
                )
            else:
                canonical = copy.deepcopy(ret)
            if return_evidence_claim(canonical) != return_evidence_claim(ret):
                raise PatternEvidenceError(
                    "canonicalization changed model-authored return fields"
                )
        except PatternEvidenceError as exc:
            print(f"ERROR: {name}: {exc}", file=sys.stderr)
            sys.exit(1)
        canonical_returns.append(canonical)

    # All input, catalog and identity validation is complete before the in-memory
    # artifact changes. A bad final return cannot leave an earlier return applied.
    summary = []
    for ret, canonical_ret in zip(returns, canonical_returns):
        name = ret.get("filename")
        # Missing names were rejected as a complete batch above; indexing keeps
        # that invariant explicit for both readers and static analysis.
        talk = by_name[name]
        try:
            promoted, stamped, coerced, cleared = merge_talk(
                talk,
                ret,
                run_date,
                catalog.fingerprint,
                enforce_queue_claim=True,
                catalog=catalog,
                canonical_ret=canonical_ret,
                artifact_capabilities=(artifact_capabilities_by_filename.get(name)),
            )
        except ValueError as exc:
            print(f"ERROR: {name}: {exc}", file=sys.stderr)
            sys.exit(1)
        analysis_result = talk.get("status") in ANALYSIS_STATUSES
        summary.append(
            {
                "filename": name,
                "status": talk.get("status"),
                "promoted": promoted,
                "stamped_processed_date": stamped,
                "coerced_pattern_score": coerced,
                "cleared": cleared,
                "pattern_scoring_generation_status": (
                    talk.get("pattern_scoring_generation_status")
                    if analysis_result
                    else UNSCORED_PATTERN_SCORING_GENERATION_STATUS
                ),
                "pattern_scoring_generation_reasons": (
                    talk.get("pattern_scoring_generation_reasons", [])
                    if analysis_result
                    else []
                ),
            }
        )

    # This all-inclusive cohort is derived only after every member merged into
    # the isolated in-memory candidate. It is intentionally distinct from the
    # immutable preclaim snapshot carried by each claim (which excludes the
    # active batch).
    try:
        current_adherence_baseline = build_current_cohort_baseline(
            db["talks"],
            as_of=completion_timestamp(run_date),
            pattern_catalog_fingerprint=catalog.fingerprint,
            pattern_scoring_schema_version=PATTERN_SCORING_SCHEMA_VERSION,
            evidence_freshness_assessor=lambda talk: (
                assess_current_persisted_pattern_evidence_freshness(
                    talk,
                    vault_root=vault_root,
                    source_roots=source_roots,
                    video_evidence_assessment=video_evidence_assessment,
                )
            ),
        )
    except AdherenceBaselineError as exc:
        print(
            f"ERROR: cannot derive the post-batch current adherence cohort: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        write_result = atomic_write_json(
            db_path,
            db,
            expected_snapshot=database_snapshot,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    _COMMIT_STATE["database_written"] = bool(write_result.installed)

    json.dump(
        {
            "persisted": len(summary),
            "db_path": db_path,
            "run_date": run_date,
            "schema_version": TALK_SCHEMA_VERSION,
            "migrated_records": 0,
            "pattern_scoring_schema_version": PATTERN_SCORING_SCHEMA_VERSION,
            "pattern_catalog_fingerprint": catalog.fingerprint,
            "current_adherence_baseline": current_adherence_baseline,
            "input_sha256": write_result.input_sha256,
            "output_sha256": write_result.output_sha256,
            "database_written": write_result.installed,
            "durability_state": write_result.durability_state,
            "warnings": list(write_result.warnings),
            "talks": summary,
        },
        sys.stdout,
        ensure_ascii=False,
    )
    sys.stdout.write("\n")


def run_cli() -> int:
    """Run the CLI behind its failure boundary. Returns the process exit code.

    Importable so the boundary's contract is testable without executing the
    module as a script.
    """
    try:
        main()
    # Callers read a non-zero exit without this JSON as a silent persistence
    # failure; emit one closed document naming whether the atomic commit landed
    # because propagation would leave the operator unable to tell a pre-commit
    # abort from a post-commit reporting failure, and could replay writes.
    except Exception as exc:  # noqa: BLE001 - outer-boundary-process-contract
        emit_unexpected_failure(
            exc,
            "persist_results_unexpected_failure",
            "vault-ingress persistence failed unexpectedly. `database_written` "
            "above states whether the atomic commit landed: when true the "
            "database holds this batch and re-running would re-persist it; when "
            "false nothing was written and the batch can be retried.",
            state={
                "database_written": _COMMIT_STATE["database_written"],
                "persisted": None,
            },
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
