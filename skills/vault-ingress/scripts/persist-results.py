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
     areas_for_improvement, adherence_assessment, transcript_source).
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

    batch-returns.json is a JSON array of subagent return objects (the shape in
    references/schemas-db.md -> "Per-Talk Subagent Return Schema"). The DB is
    rewritten in place; a structured JSON summary is printed to stdout:
        {"persisted": <int>, "db_path": "<path>",
         "talks": [{"filename": "...", "status": "...", "promoted": ["..."]}]}
    Diagnostics and errors go to stderr; exit code is non-zero on failure.

Example:
    persist-results.py ~/.claude/rhetoric-knowledge-vault/tracking-database.json batch-returns.json
"""

import json
import sys

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


def merge_talk(talk, ret):
    for f in SCALARS:
        if f in ret and not is_empty(ret[f]):
            talk[f] = ret[f]
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
    return promoted


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <tracking-database.json> <batch-returns.json>", file=sys.stderr)
        sys.exit(1)
    db_path, batch_path = sys.argv[1], sys.argv[2]

    with open(db_path, encoding="utf-8") as f:
        db = json.load(f)
    with open(batch_path, encoding="utf-8") as f:
        returns = json.load(f)
    if not isinstance(returns, list):
        print("batch-returns.json must be a JSON array of subagent returns", file=sys.stderr)
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
        promoted = merge_talk(talk, ret)
        summary.append({"filename": name, "status": talk.get("status"), "promoted": promoted})

    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

    json.dump({"persisted": len(summary), "db_path": db_path, "talks": summary},
              sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
