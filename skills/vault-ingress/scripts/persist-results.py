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
  1. Sets the scalar result fields (status, processed_date, rhetoric_notes,
     areas_for_improvement, adherence_assessment, transcript_source). A return
     that omits `processed_date` is stamped with the run date, because otherwise
     the talk keeps whatever date the previous run set and the DB cannot answer
     "which talks has this reparse actually covered".
  2. Deep-merges the full `structured_data` and `verbatim_examples` blocks —
     additive: dicts recurse, new non-empty values win, existing data is never
     clobbered by missing/empty values (re-runs refine, never wipe).
  3. Normalizes `pattern_observations` from the subagent's
     {patterns_detected, antipatterns_detected, pattern_score:{score}} shape into
     the DB's {pattern_ids, antipattern_ids, pattern_score:int} shape, keeping the
     detailed arrays too (Section 15 aggregation reads antipatterns_detected).
  4. Promotes the declared queryable scalars (PROMOTE) to the talk's top level so
     they are directly queryable, not buried in structured_data or rhetoric_notes.

It does NOT touch rhetoric-style-summary.md or the analysis files — those are
written elsewhere in Step 4/Step 5. It owns only the tracking-DB merge.

Usage:
    persist-results.py <tracking-database.json> <batch-returns.json>
                       [--run-date YYYY-MM-DD|<ISO-8601 timestamp>]

    batch-returns.json is a JSON array of subagent return objects (the shape in
    references/schemas-db.md -> "Per-Talk Subagent Return Schema"). The DB is
    rewritten in place; a structured JSON summary is printed to stdout:
        {"persisted": <int>, "db_path": "<path>",
         "run_date": "<YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS+00:00>",
         "talks": [{"filename": "...", "status": "...", "promoted": ["..."],
                    "stamped_processed_date": <bool>}]}
    Diagnostics and errors go to stderr; exit code is non-zero on failure.

    Absent --run-date, the stamp is the current UTC time at second resolution.
    --run-date pins it instead of reading the clock; the whole batch shares one
    stamp so a run that straddles midnight does not split across two. It accepts
    either a bare YYYY-MM-DD or an ISO-8601 timestamp; a timestamp must carry a
    timezone offset and is normalized to UTC at second resolution.

Example:
    persist-results.py ~/.claude/rhetoric-knowledge-vault/tracking-database.json batch-returns.json
"""

import json
import sys
from datetime import datetime, timezone


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
    ("delivery_language",          "structured_data.delivery_language"),
    ("pattern_score",              "pattern_observations.pattern_score.score"),
]

# Scalar result fields copied verbatim when present in the return.
SCALARS = [
    "status", "processed_date", "rhetoric_notes", "areas_for_improvement",
    "adherence_assessment", "transcript_source",
]


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


def normalize_pattern_observations(existing, incoming):
    """Map the subagent return shape onto the DB shape, keeping both views.

    Subagent returns {patterns_detected, antipatterns_detected, pattern_score:{score}}.
    The DB declares {pattern_ids, antipattern_ids, pattern_score:int}. Section 15
    aggregation reads the detailed *_detected arrays, so keep those too.
    """
    obs = dict(existing) if isinstance(existing, dict) else {}
    patterns = incoming.get("patterns_detected")
    antipatterns = incoming.get("antipatterns_detected")
    if patterns is not None:
        obs["patterns_detected"] = patterns
        obs["pattern_ids"] = [p.get("pattern_id") for p in patterns if p.get("pattern_id")]
    if antipatterns is not None:
        obs["antipatterns_detected"] = antipatterns
        obs["antipattern_ids"] = [p.get("pattern_id") for p in antipatterns if p.get("pattern_id")]
    score = incoming.get("pattern_score")
    if isinstance(score, dict) and "score" in score:
        obs["pattern_score"] = score["score"]
    elif isinstance(score, (int, float)):
        obs["pattern_score"] = score
    return obs


def merge_talk(talk, ret, run_date=None):
    """Merge one return into its talk. Returns (promoted_fields, stamped_date).

    `run_date` stamps `processed_date` when the return omits it. Callers that
    care about reproducibility pass it explicitly; it is never read from the
    clock inside the merge.
    """
    for f in SCALARS:
        if f in ret and not is_empty(ret[f]):
            talk[f] = ret[f]
    # A return that reports a status but no date would otherwise leave the
    # previous run's date in place, making the talk look untouched by this run.
    stamped = False
    if run_date and is_empty(ret.get("processed_date")):
        talk["processed_date"] = run_date
        stamped = True
    if isinstance(ret.get("structured_data"), dict):
        talk["structured_data"] = deep_merge(talk.get("structured_data") or {}, ret["structured_data"])
    if isinstance(ret.get("verbatim_examples"), dict):
        talk["verbatim_examples"] = deep_merge(talk.get("verbatim_examples") or {}, ret["verbatim_examples"])
    if isinstance(ret.get("pattern_observations"), dict):
        talk["pattern_observations"] = normalize_pattern_observations(
            talk.get("pattern_observations"), ret["pattern_observations"])
    promoted = []
    for field, path in PROMOTE:
        val = dig(ret, path)
        if not is_empty(val):
            talk[field] = val
            promoted.append(field)
    return promoted, stamped


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
    if not isinstance(returns, list):
        print(f"ERROR: {batch_path} must be a JSON array of subagent returns, "
              f"got {type(returns).__name__}", file=sys.stderr)
        sys.exit(1)

    by_name = {t.get("filename"): t for t in db.get("talks", [])}
    summary = []
    for ret in returns:
        name = ret.get("filename")
        talk = by_name.get(name)
        if talk is None:
            # Fail visibly — a return with no matching talk means an upstream
            # mismatch, not something to silently skip.
            print(f"ERROR: no talk in DB matches return filename: {name!r}", file=sys.stderr)
            sys.exit(1)
        promoted, stamped = merge_talk(talk, ret, run_date)
        summary.append({"filename": name, "status": talk.get("status"),
                        "promoted": promoted, "stamped_processed_date": stamped})

    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

    json.dump({"persisted": len(summary), "db_path": db_path, "run_date": run_date,
               "talks": summary}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
