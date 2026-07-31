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
     then matches every return to the talk's active queue generation.
  2. Sets the scalar result fields (status, processed_date, rhetoric_notes,
     areas_for_improvement, adherence_assessment, transcript_source). A return
     that omits `processed_date` is stamped with the run date, because otherwise
     the talk keeps whatever date the previous run set and the DB cannot answer
     "which talks has this reparse actually covered".
  3. Applies explicit `clear_fields`, then deep-merges the full `structured_data`
     and `verbatim_examples` blocks —
     additive: dicts recurse, new non-empty values win, existing data is never
     clobbered by missing/empty values (re-runs refine, never wipe).
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
         "talks": [{"filename": "...", "status": "...", "promoted": ["..."],
                    "stamped_processed_date": <bool>,
                    "coerced_pattern_score": <bool>}]}
    Diagnostics and errors go to stderr; exit code is non-zero on failure.

    `coerced_pattern_score` is true when the return supplied `pattern_score` as a
    bare int and it was rebuilt into the declared dict. The coercion is reported
    rather than silent so the rate stays visible — a return shape that needs
    fixing this often is a schema problem, not a one-off.

    Absent --run-date, the stamp is the current UTC time at second resolution.
    --run-date pins it instead of reading the clock; the whole batch shares one
    stamp so a run that straddles midnight does not split across two. It accepts
    either a bare YYYY-MM-DD or an ISO-8601 timestamp; a timestamp must carry a
    timezone offset and is normalized to UTC at second resolution.

Example:
    persist-results.py ~/.claude/rhetoric-knowledge-vault/tracking-database.json batch-returns.json
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone

from return_validation import (
    ANALYSIS_STATUSES,
    ReturnValidationError,
    validate_claim_against_talk,
    validate_batch,
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
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return value
    except ValueError:
        pass
    moment = datetime.fromisoformat(value)  # raises ValueError on anything else
    if moment.tzinfo is None:
        raise ValueError(
            f"timestamp {value!r} has no timezone — append an offset "
            f"(e.g. {value}+00:00) so stamps from different machines order")
    return default_stamp(moment)

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
# readable and acquire generation identity on their next validated analysis.
TALK_SCHEMA_VERSION = 3

# Incremented when score meaning or observation validation changes. The catalog
# content hash below identifies the exact taxonomy snapshot; this integer names
# the scoring contract applied to that snapshot.
PATTERN_SCORING_SCHEMA_VERSION = 2

# Queryable scalars promoted from the subagent return onto the talk's top level.
# (top_level_field, dotted source path within the return). To add a new queryable
# scalar, add it here AND to the return schema — never reintroduce hand-mapping.
PROMOTE = [
    ("slide_count",                "structured_data.slide_count"),
    ("slide_design_style",         "structured_data.slide_design_style"),
    ("illustration_style",         "structured_data.illustration_style"),
    ("opening_type",               "structured_data.opening_type"),
    ("closing_type",               "structured_data.closing_type"),
    ("narrative_arc_type",         "structured_data.narrative_arc_type"),
    ("audience_interaction_count", "structured_data.audience_interaction_count"),
    ("co_presenter",               "structured_data.co_presenter"),
    ("co_presenters",              "structured_data.co_presenters"),
    ("delivery_language",          "structured_data.delivery_language"),
]

# NOT in PROMOTE: `pattern_score`. It is set explicitly in merge_talk from
# resolve_pattern_score, because a dotted-path lookup silently yields nothing
# when a subagent sends the bare int instead of the declared dict.

# Scalar result fields copied verbatim when present in the return.
SCALARS = [
    "status", "processed_date", "rhetoric_notes", "areas_for_improvement",
    "adherence_assessment", "transcript_source", "slide_source",
]

PROMOTED_BY_STRUCTURED_KEY = {
    path.removeprefix("structured_data."): field
    for field, path in PROMOTE
    if path.startswith("structured_data.") and "." not in path.removeprefix("structured_data.")
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
        if (len(parts) == 2 and parts[0] == "pattern_observations" and
                parts[1] == "pattern_score" and talk.pop("pattern_score", None) is not None):
            cleared.append("pattern_score")
    return cleared


def completion_timestamp(run_date):
    """Return a queue-compatible timestamp from a date or timestamp run stamp."""
    if len(run_date) == 10:
        return f"{run_date}T00:00:00+00:00"
    return run_date


def close_queue_claim(talk, status, run_date):
    claim = talk["_queue_claim"]
    claim["state"] = "completed"
    claim["released_at"] = completion_timestamp(run_date)
    claim["release_reason"] = "return_persisted"
    claim["result_status"] = status


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
            "loses the whole block while the merge still reports success.")
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
            "return schema declares it an array of detection objects.")
    bad = next((e for e in value if not isinstance(e, dict)), None)
    if bad is not None:
        raise ValueError(
            f"pattern_observations.{field} contains {bad!r} "
            f"({type(bad).__name__}); every element must be an object carrying a "
            "`pattern_id`.")
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
            '{"patterns_used": N, "antipatterns_detected": M, "score": N-M}.')

    label = "pattern_score" if coerced else "pattern_score.score"
    if isinstance(nested, bool) or not isinstance(nested, int):
        raise ValueError(
            f"{label} is {nested!r} ({type(nested).__name__}). It must be an "
            "integer — the score is count(patterns) minus count(antipatterns), "
            "so a float, a string and a bool are all wrong. Emit "
            '{"patterns_used": N, "antipatterns_detected": M, "score": N-M}.')

    # Only the coerced form is cross-checked. It is the shape that arrived
    # without its accompanying counts, so the arrays are the only evidence that
    # the number is right.
    if coerced:
        used, against = len(patterns or []), len(antipatterns or [])
        if used - against != nested:
            raise ValueError(
                f"pattern_score is the bare int {nested}, but patterns_detected "
                f"({used}) minus antipatterns_detected ({against}) is "
                f"{used - against}. Refusing to guess which is right.")
    return nested, coerced


def normalize_pattern_observations(existing, patterns, antipatterns,
                                   not_evaluable, evidence_sources, score):
    """Map the subagent return shape onto the DB shape, keeping both views.

    Takes already-validated inputs and decides nothing about their shape, so it
    cannot drift from the validator the way its predecessor did.
    """
    obs = dict(existing) if isinstance(existing, dict) else {}
    if patterns is not None:
        obs["patterns_detected"] = patterns
        obs["pattern_ids"] = [p.get("pattern_id") for p in patterns if p.get("pattern_id")]
    if antipatterns is not None:
        obs["antipatterns_detected"] = antipatterns
        obs["antipattern_ids"] = [p.get("pattern_id") for p in antipatterns if p.get("pattern_id")]
    if not_evaluable is not None:
        obs["not_evaluable"] = not_evaluable
        obs["not_evaluable_ids"] = [
            item.get("pattern_id") for item in not_evaluable if item.get("pattern_id")]
    if evidence_sources is not None:
        obs["evidence_sources"] = evidence_sources
    if score is not None:
        obs["pattern_score"] = score
    return obs


def merge_talk(talk, ret, run_date=None, catalog_fingerprint=None,
               *, enforce_queue_claim=False):
    """Merge one return into its talk.

    Returns (promoted, stamped, coerced_score, cleared).

    Every block is validated BEFORE anything is written, so a malformed return
    leaves the talk untouched rather than half-merged. `run_date` stamps
    `processed_date` when the return omits it; it is never read from the clock
    inside the merge.
    """
    if enforce_queue_claim:
        validate_claim_against_talk(talk, ret)
    structured = require_mapping(ret, "structured_data")
    verbatim = require_mapping(ret, "verbatim_examples")
    observations = require_mapping(ret, "pattern_observations") or {}
    patterns = require_detections(observations, "patterns_detected")
    antipatterns = require_detections(observations, "antipatterns_detected")
    not_evaluable = require_detections(observations, "not_evaluable")
    evidence_sources = observations.get("evidence_sources")
    score, coerced_score = resolve_pattern_score(observations, patterns, antipatterns)

    cleared = apply_clear_fields(talk, ret.get("clear_fields"))
    talk["schema_version"] = TALK_SCHEMA_VERSION
    for f in SCALARS:
        if f in ret and not is_empty(ret[f]):
            talk[f] = ret[f]
    # A return that reports a status but no date would otherwise leave the
    # previous run's date in place, making the talk look untouched by this run.
    stamped = False
    if run_date and is_empty(ret.get("processed_date")):
        talk["processed_date"] = run_date
        stamped = True
    if structured is not None:
        talk["structured_data"] = deep_merge(talk.get("structured_data") or {}, structured)
    if verbatim is not None:
        talk["verbatim_examples"] = deep_merge(talk.get("verbatim_examples") or {}, verbatim)
    if observations:
        talk["pattern_observations"] = normalize_pattern_observations(
            talk.get("pattern_observations"), patterns, antipatterns,
            not_evaluable, evidence_sources, score)

    promoted = []
    for field, path in PROMOTE:
        val = dig(ret, path)
        if not is_empty(val):
            talk[field] = val
            promoted.append(field)
    # `pattern_score` is set from the resolved value rather than dug out of the
    # return. The dotted path `pattern_observations.pattern_score.score` is what
    # silently dropped the scalar whenever a subagent sent the bare int, because
    # `dig` returns None on an int — the promoted scalar and the nested value
    # must come from one decision, not two lookups.
    if score is not None:
        talk["pattern_score"] = score
        promoted.append("pattern_score")
    if ret.get("status") in ANALYSIS_STATUSES:
        talk["pattern_scoring_schema_version"] = PATTERN_SCORING_SCHEMA_VERSION
        if catalog_fingerprint:
            talk["pattern_catalog_fingerprint"] = catalog_fingerprint
    if enforce_queue_claim:
        close_queue_claim(talk, ret["status"], run_date)
    return promoted, stamped, coerced_score, cleared


def migrate_records(db):
    """Bring every talk record to the current schema version. Returns the count.

    `stateful-artifacts` puts migration on the OWNER skill, and this script is
    the tracking DB's only writer. Stamping just the talks a batch happened to
    touch would leave the file permanently mixed-version — a reader could not
    tell an unversioned record from one this writer had never seen, which is the
    ambiguity the version exists to remove.

    The migration is a stamp, not a transform: v2 to v3 adds optional generation
    metadata written only when a validated analysis is merged. No existing field
    changes representation, so records need no content rewrite.
    """
    migrated = 0
    for talk in db.get("talks", []):
        if talk.get("schema_version") != TALK_SCHEMA_VERSION:
            talk["schema_version"] = TALK_SCHEMA_VERSION
            migrated += 1
    return migrated


def atomic_write_json(path, payload):
    """Replace a JSON artifact atomically after flushing the complete temp file."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    basename = os.path.basename(path)
    try:
        fd, temp_path = tempfile.mkstemp(prefix=f".{basename}.", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        except BaseException:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            raise
    except OSError as exc:
        raise ValueError(f"cannot atomically write tracking database {path}: {exc}") from exc


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
                print("ERROR: --run-date requires a YYYY-MM-DD or ISO-8601 value",
                      file=sys.stderr)
                sys.exit(1)
            run_date = argv[i + 1]
            i += 2
            continue
        args.append(argv[i])
        i += 1
    if len(args) != 2:
        print(f"Usage: {sys.argv[0]} <tracking-database.json> <batch-returns.json> "
              f"[--run-date YYYY-MM-DD|ISO-8601]", file=sys.stderr)
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
            print(f"ERROR: --run-date must be YYYY-MM-DD or a timezone-aware "
                  f"ISO-8601 timestamp: {e}", file=sys.stderr)
            sys.exit(1)
    return args[0], args[1], run_date


def main():
    db_path, batch_path, run_date = parse_args(sys.argv[1:])

    db = load_json(db_path, "tracking database")
    returns = load_json(batch_path, "batch-returns")
    try:
        catalog = validate_batch(returns)
    except ReturnValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(db, dict) or not isinstance(db.get("talks"), list):
        print(f"ERROR: {db_path} is not a tracking database — expected a JSON "
              "object with a `talks` array", file=sys.stderr)
        sys.exit(1)
    names = [talk.get("filename") for talk in db["talks"] if isinstance(talk, dict)]
    duplicates = sorted({name for name in names if name and names.count(name) > 1})
    if duplicates:
        print(f"ERROR: tracking database has duplicate filenames: {duplicates}", file=sys.stderr)
        sys.exit(1)
    by_name = {talk.get("filename"): talk for talk in db["talks"] if isinstance(talk, dict)}
    missing = [ret["filename"] for ret in returns if ret["filename"] not in by_name]
    if missing:
        print(f"ERROR: no talk in DB matches return filename(s): {missing}", file=sys.stderr)
        sys.exit(1)

    # All input, catalog and identity validation is complete before the in-memory
    # artifact changes. A bad final return cannot leave an earlier return applied.
    migrated = migrate_records(db)
    summary = []
    for ret in returns:
        name = ret.get("filename")
        talk = by_name.get(name)
        try:
            promoted, stamped, coerced, cleared = merge_talk(
                talk, ret, run_date, catalog.fingerprint,
                enforce_queue_claim=True)
        except ValueError as exc:
            print(f"ERROR: {name}: {exc}", file=sys.stderr)
            sys.exit(1)
        summary.append({"filename": name, "status": talk.get("status"),
                        "promoted": promoted, "stamped_processed_date": stamped,
                        "coerced_pattern_score": coerced, "cleared": cleared})

    try:
        atomic_write_json(db_path, db)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    json.dump({"persisted": len(summary), "db_path": db_path, "run_date": run_date,
               "schema_version": TALK_SCHEMA_VERSION, "migrated_records": migrated,
               "pattern_scoring_schema_version": PATTERN_SCORING_SCHEMA_VERSION,
               "pattern_catalog_fingerprint": catalog.fingerprint,
               "talks": summary}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
