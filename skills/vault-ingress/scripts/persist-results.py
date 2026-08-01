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
     areas_for_improvement, adherence_assessment, transcript_source,
     transcript_path). A return
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
     New detections must cite direct, catalog-permitted evidence. Transcript
     quotes, slide ranges, and metadata are verified against local artifacts;
     source-owned locations replace any model-supplied line/time/value fields.
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
import math
import re
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import yaml

from transcript_timing import load_verified_segments, resolve_quote


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
# v3 adds optional `transcript_path`,
# `pattern_observations.evidence_schema_version`, and each detection's additive
# `evidence_citations` array. Existing evidence prose remains readable; migration
# adds an empty array to old detections, explicitly distinguishing legacy
# unlocated evidence from source-verified new observations.
TALK_SCHEMA_VERSION = 3
PATTERN_EVIDENCE_SCHEMA_VERSION = 1

EVIDENCE_CHANNELS = frozenset(
    {
        "transcript",
        "timed_transcript",
        "slides",
        "slide_sequence",
        "video",
        "talk_metadata",
    }
)
EVIDENCE_CITATION_FIELDS = {
    "transcript": frozenset(
        {
            "channel",
            "quote",
            "translation",
            "line_start",
            "line_end",
            "start_seconds",
            "end_seconds",
        }
    ),
    "timed_transcript": frozenset(
        {
            "channel",
            "quote",
            "translation",
            "line_start",
            "line_end",
            "start_seconds",
            "end_seconds",
        }
    ),
    "slides": frozenset({"channel", "slide_numbers"}),
    "slide_sequence": frozenset({"channel", "slide_numbers"}),
    "video": frozenset({"channel", "start_seconds", "end_seconds"}),
    "talk_metadata": frozenset({"channel", "field", "value"}),
}
USABLE_SLIDE_SOURCES = frozenset({"pptx", "pdf", "both", "video_extracted"})
CONFIDENCE_VALUES = frozenset({"strong", "moderate", "weak"})
MIN_TRANSCRIPT_QUOTE_WORDS = 4
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
_YOUTUBE_ID = re.compile(r"[A-Za-z0-9_-]{11}")
TALK_METADATA_FIELDS = frozenset(
    {
        "filename",
        "title",
        "conference",
        "date",
        "slides_url",
        "video_url",
        "youtube_id",
        "google_drive_id",
        "pptx_path",
        "transcript_path",
        "transcript_source",
        "slide_source",
        "slide_count",
        "co_presenter",
        "delivery_language",
    }
)
_PATTERN_ROOT = (
    Path(__file__).resolve().parents[2]
    / "presentation-creator"
    / "references"
    / "patterns"
)

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
]

# NOT in PROMOTE: `pattern_score`. It is set explicitly in merge_talk from
# resolve_pattern_score, because a dotted-path lookup silently yields nothing
# when a subagent sends the bare int instead of the declared dict.

# Scalar result fields copied verbatim when present in the return.
SCALARS = [
    "status", "processed_date", "rhetoric_notes", "areas_for_improvement",
    "adherence_assessment", "transcript_source", "transcript_path",
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


def load_pattern_catalog(pattern_root=_PATTERN_ROOT):
    """Load stable IDs plus observability/evidence-channel policy from frontmatter."""
    catalog = {}
    for path in sorted(Path(pattern_root).glob("*/*.md")):
        text = path.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        if len(parts) < 3:
            raise ValueError(f"pattern entry has no YAML frontmatter: {path}")
        try:
            metadata = yaml.safe_load(parts[1])
        except yaml.YAMLError as exc:
            raise ValueError(f"pattern entry has invalid YAML frontmatter: {path}: {exc}") from exc
        if (
            not isinstance(metadata, dict)
            or not isinstance(metadata.get("id"), str)
            or not metadata["id"].strip()
        ):
            raise ValueError(f"pattern entry has no string `id`: {path}")
        pattern_id = metadata["id"]
        pattern_type = metadata.get("type")
        if pattern_type not in {"pattern", "antipattern"}:
            raise ValueError(
                f"pattern entry {pattern_id!r} has invalid type {pattern_type!r}: {path}"
            )
        if pattern_id in catalog:
            raise ValueError(
                f"duplicate pattern id {pattern_id!r}: {catalog[pattern_id]['path']} and {path}"
            )
        observable = metadata.get("observable") is not False
        channels = metadata.get("evidence_channels")
        if channels is None:
            if observable:
                raise ValueError(
                    f"observable pattern {pattern_id!r} has no evidence_channels: {path}"
                )
            channels = []
        if (
            not isinstance(channels, list)
            or (observable and not channels)
            or not all(
                isinstance(channel, str) and channel in EVIDENCE_CHANNELS
                for channel in channels
            )
            or len(set(channels)) != len(channels)
        ):
            raise ValueError(
                f"pattern {pattern_id!r} has invalid evidence_channels {channels!r}; "
                f"allowed values are {sorted(EVIDENCE_CHANNELS)}"
            )
        metadata_fields = metadata.get("evidence_metadata_fields", [])
        if (
            not isinstance(metadata_fields, list)
            or not all(
                isinstance(field, str) and field in TALK_METADATA_FIELDS
                for field in metadata_fields
            )
            or len(set(metadata_fields)) != len(metadata_fields)
            or ("talk_metadata" in channels and not metadata_fields)
            or ("talk_metadata" not in channels and metadata_fields)
        ):
            raise ValueError(
                f"pattern {pattern_id!r} has invalid evidence_metadata_fields "
                f"{metadata_fields!r}; declare a non-empty subset of "
                f"{sorted(TALK_METADATA_FIELDS)} iff talk_metadata is permitted"
            )
        catalog[pattern_id] = {
            "type": pattern_type,
            "observable": observable,
            "evidence_channels": frozenset(channels),
            "evidence_metadata_fields": frozenset(metadata_fields),
            "path": str(path),
        }
    return catalog


def validate_transcript_path(value):
    """Return a safe vault-relative transcript path or raise ``ValueError``."""
    if not isinstance(value, str):
        raise ValueError("transcript_path must be a vault-relative string")
    relative = Path(value)
    if (
        relative.is_absolute()
        or "\\" in value
        or ".." in relative.parts
        or not relative.parts
        or relative.parts[0] != "transcripts"
        or relative.suffix.lower() != ".txt"
    ):
        raise ValueError(
            "transcript_path must name a .txt file under the vault's "
            "transcripts/ directory (for example transcripts/talk-id.txt)"
        )
    return relative


def resolve_transcript_path(vault_root, talk, ret):
    """Resolve a transcript path inside the vault, including non-YouTube talks."""
    vault_root = Path(vault_root)
    explicit = ret.get("transcript_path")
    if is_empty(explicit):
        explicit = talk.get("transcript_path")
    if not is_empty(explicit):
        relative = validate_transcript_path(explicit)
        youtube_id = talk.get("youtube_id")
        if isinstance(youtube_id, str) and _YOUTUBE_ID.fullmatch(youtube_id):
            canonical = Path("transcripts") / f"{youtube_id}.txt"
            if relative != canonical:
                raise ValueError(
                    f"transcript_path {explicit!r} does not match this talk's "
                    f"youtube_id; expected {str(canonical)!r}"
                )
        return vault_root / relative, f"resolved explicit transcript_path {explicit}"

    youtube_id = talk.get("youtube_id")
    if isinstance(youtube_id, str) and youtube_id:
        if _YOUTUBE_ID.fullmatch(youtube_id) is None:
            raise ValueError(
                f"youtube_id {youtube_id!r} is not an 11-character YouTube id; "
                "set a safe transcript_path explicitly for non-YouTube talks"
            )
        path = vault_root / "transcripts" / f"{youtube_id}.txt"
        return path, f"resolved transcript from youtube_id {youtube_id}"

    filename = talk.get("filename") or ret.get("filename")
    if isinstance(filename, str) and filename:
        safe_name = Path(filename.replace("\\", "/")).name
        candidate = vault_root / "transcripts" / f"{Path(safe_name).stem}.txt"
        if candidate.exists():
            return candidate, f"resolved legacy non-YouTube transcript from {filename}"
    return None, (
        "talk has neither youtube_id nor transcript_path, and no transcript named "
        "after its filename was found"
    )


def build_evidence_context(vault_root, talk, ret):
    """Resolve the local artifacts a deterministic evidence validator may inspect."""
    transcript_text = None
    timed_segments = []
    timing_reason = "timed transcript is unavailable"
    transcript_path, transcript_reason = resolve_transcript_path(vault_root, talk, ret)
    if transcript_path is not None:
        try:
            transcript_text = transcript_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            transcript_reason = f"transcript file is missing: {transcript_path}"
        except OSError as exc:
            transcript_reason = f"cannot read transcript file {transcript_path}: {exc}"
        else:
            transcript_reason = f"loaded transcript {transcript_path}"
            timed_segments, timing_reason = load_verified_segments(
                transcript_path, transcript_text
            )

    slide_count = dig(ret, "structured_data.slide_count")
    if slide_count is None:
        slide_count = talk.get("slide_count")
    slide_source = ret.get("slide_source") or talk.get("slide_source")
    metadata = {
        field: talk[field]
        for field in TALK_METADATA_FIELDS
        if field in talk and not is_empty(talk[field])
    }
    if not is_empty(ret.get("transcript_path")):
        metadata["transcript_path"] = ret["transcript_path"]
    if not is_empty(ret.get("transcript_source")):
        metadata["transcript_source"] = ret["transcript_source"]
    if not is_empty(slide_source):
        metadata["slide_source"] = slide_source
    if not is_empty(slide_count):
        metadata["slide_count"] = slide_count
    for field, path in PROMOTE:
        if field not in TALK_METADATA_FIELDS:
            continue
        value = dig(ret, path)
        if not is_empty(value):
            metadata[field] = value
    return {
        "transcript_text": transcript_text,
        "transcript_reason": transcript_reason,
        "timed_segments": timed_segments,
        "timing_reason": timing_reason,
        "slide_count": slide_count,
        "slide_source": slide_source,
        "video_url": talk.get("video_url"),
        "metadata": metadata,
    }


def _nonnegative_number(value):
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and value >= 0
    )


def _validate_transcript_citation(citation, *, timed, context):
    quote = citation.get("quote")
    if not isinstance(quote, str) or not quote.strip():
        raise ValueError("transcript evidence requires a non-empty verbatim `quote`")
    if len(_WORD.findall(quote)) < MIN_TRANSCRIPT_QUOTE_WORDS:
        raise ValueError(
            f"transcript evidence quote {quote!r} has fewer than "
            f"{MIN_TRANSCRIPT_QUOTE_WORDS} words; use a distinctive, auditable span"
        )
    translation = citation.get("translation")
    if translation is not None and (
        not isinstance(translation, str) or not translation.strip()
    ):
        raise ValueError(
            "transcript evidence `translation` must be a non-empty string when present"
        )
    for model_owned in ("line_start", "line_end", "start_seconds", "end_seconds"):
        citation.pop(model_owned, None)
    if context is None:
        return
    transcript_text = context.get("transcript_text")
    if not isinstance(transcript_text, str):
        raise ValueError(
            f"transcript evidence cannot be verified: {context.get('transcript_reason')}"
        )
    try:
        resolved = resolve_quote(
            transcript_text,
            quote,
            segments=context.get("timed_segments") or [],
        )
    except ValueError as exc:
        raise ValueError(f"transcript evidence quote {quote!r}: {exc}") from exc
    citation.update(resolved)
    if timed and "start_seconds" not in citation:
        raise ValueError(
            f"timing-dependent evidence quote {quote!r} has no verified timestamp: "
            f"{context.get('timing_reason')}"
        )


def _validate_slide_citation(citation, *, sequence, context):
    slide_numbers = citation.get("slide_numbers")
    if not isinstance(slide_numbers, list) or not slide_numbers:
        raise ValueError("slide evidence requires a non-empty `slide_numbers` array")
    if any(
        isinstance(number, bool) or not isinstance(number, int) or number < 1
        for number in slide_numbers
    ):
        raise ValueError("slide_numbers must contain positive integer slide numbers")
    if len(set(slide_numbers)) != len(slide_numbers):
        raise ValueError("slide_numbers must not contain duplicates")
    if sequence and (
        len(slide_numbers) < 2
        or any(right != left + 1 for left, right in zip(slide_numbers, slide_numbers[1:]))
    ):
        raise ValueError(
            "slide_sequence evidence requires at least two consecutive, ascending slide numbers"
        )
    if context is None:
        return
    source = context.get("slide_source")
    count = context.get("slide_count")
    if (
        source not in USABLE_SLIDE_SOURCES
        or isinstance(count, bool)
        or not isinstance(count, int)
        or count < 1
    ):
        raise ValueError(
            "slide evidence cannot be verified because this talk has no usable slide source/count"
        )
    if any(number > count for number in slide_numbers):
        raise ValueError(
            f"slide evidence cites {slide_numbers!r}, but the talk has {count} slides"
        )


def _validate_video_citation(citation, context):
    start = citation.get("start_seconds")
    end = citation.get("end_seconds")
    if not _nonnegative_number(start) or not _nonnegative_number(end) or end <= start:
        raise ValueError(
            "video evidence requires numeric start_seconds/end_seconds with end after start"
        )
    if context is not None and not context.get("video_url"):
        raise ValueError("video evidence cannot be verified because the talk has no video_url")


def _validate_metadata_citation(citation, context, allowed_fields):
    field = citation.get("field")
    if not isinstance(field, str) or not field.strip():
        raise ValueError("talk_metadata evidence requires a non-empty `field`")
    if field not in TALK_METADATA_FIELDS:
        raise ValueError(
            f"talk_metadata evidence field {field!r} is not source metadata; "
            f"expected one of {sorted(TALK_METADATA_FIELDS)}"
        )
    if field not in allowed_fields:
        raise ValueError(
            f"talk_metadata field {field!r} is not permitted for this pattern; "
            f"expected one of {sorted(allowed_fields)}"
        )
    citation.pop("value", None)
    if context is None:
        return
    metadata = context.get("metadata") or {}
    if field not in metadata or is_empty(metadata[field]):
        raise ValueError(
            f"talk_metadata evidence cites absent/empty field {field!r}"
        )
    citation["value"] = metadata[field]


def validate_detection(detection, *, field, catalog=None, evidence_context=None):
    """Validate one new detection and stamp deterministic citation locations."""
    pattern_id = detection.get("pattern_id")
    if not isinstance(pattern_id, str) or not pattern_id:
        raise ValueError(f"pattern_observations.{field} entry has no string `pattern_id`")
    policy = catalog.get(pattern_id) if catalog is not None else None
    if catalog is not None and policy is None:
        raise ValueError(f"pattern_observations.{field} references unknown id {pattern_id!r}")
    expected_type = {
        "patterns_detected": "pattern",
        "antipatterns_detected": "antipattern",
    }.get(field)
    if policy is not None and expected_type is not None and policy["type"] != expected_type:
        raise ValueError(
            f"pattern {pattern_id!r} is cataloged as {policy['type']!r}, so it cannot "
            f"appear in pattern_observations.{field}"
        )
    if policy is not None and not policy["observable"]:
        raise ValueError(
            f"pattern {pattern_id!r} is observable:false and cannot be auto-scored; "
            "surface it as a preparation/clarification item instead"
        )
    confidence = detection.get("confidence")
    if confidence not in CONFIDENCE_VALUES:
        raise ValueError(
            f"pattern {pattern_id!r} has confidence {confidence!r}; "
            f"expected one of {sorted(CONFIDENCE_VALUES)}"
        )
    evidence = detection.get("evidence")
    if not isinstance(evidence, str) or not evidence.strip():
        raise ValueError(f"pattern {pattern_id!r} requires a non-empty evidence summary")
    citations = detection.get("evidence_citations")
    if not isinstance(citations, list) or not citations:
        raise ValueError(
            f"pattern {pattern_id!r} requires a non-empty evidence_citations array"
        )
    allowed_channels = policy["evidence_channels"] if policy is not None else EVIDENCE_CHANNELS
    validated = []
    for raw_citation in citations:
        if not isinstance(raw_citation, dict):
            raise ValueError(
                f"pattern {pattern_id!r} evidence_citations entries must be objects"
            )
        citation = dict(raw_citation)
        channel = citation.get("channel")
        if channel not in EVIDENCE_CHANNELS:
            raise ValueError(
                f"pattern {pattern_id!r} has unsupported evidence channel {channel!r}; "
                f"expected one of {sorted(EVIDENCE_CHANNELS)}"
            )
        unknown_fields = sorted(set(citation) - EVIDENCE_CITATION_FIELDS[channel])
        if unknown_fields:
            raise ValueError(
                f"pattern {pattern_id!r} {channel!r} citation has unknown fields "
                f"{unknown_fields!r}; expected only "
                f"{sorted(EVIDENCE_CITATION_FIELDS[channel])}"
            )
        if channel not in allowed_channels:
            raise ValueError(
                f"pattern {pattern_id!r} cannot be proved through {channel!r}; "
                f"its catalog permits {sorted(allowed_channels)}"
            )
        if channel in {"transcript", "timed_transcript"}:
            _validate_transcript_citation(
                citation,
                timed=channel == "timed_transcript",
                context=evidence_context,
            )
        elif channel in {"slides", "slide_sequence"}:
            _validate_slide_citation(
                citation,
                sequence=channel == "slide_sequence",
                context=evidence_context,
            )
        elif channel == "video":
            _validate_video_citation(citation, evidence_context)
        else:
            metadata_fields = (
                policy["evidence_metadata_fields"]
                if policy is not None
                else TALK_METADATA_FIELDS
            )
            _validate_metadata_citation(
                citation,
                evidence_context,
                metadata_fields,
            )
        validated.append(citation)
    detection["evidence_citations"] = validated
    return detection


def require_detections(
    observations,
    field,
    *,
    catalog=None,
    evidence_context=None,
):
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
    copied = deepcopy(value)
    validated = [
        validate_detection(
            detection,
            field=field,
            catalog=catalog,
            evidence_context=evidence_context,
        )
        for detection in copied
    ]
    seen = set()
    duplicates = set()
    for detection in validated:
        pattern_id = detection["pattern_id"]
        if pattern_id in seen:
            duplicates.add(pattern_id)
        seen.add(pattern_id)
    if duplicates:
        raise ValueError(
            f"pattern_observations.{field} contains duplicate pattern IDs "
            f"{sorted(duplicates)!r}"
        )
    return validated


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


def normalize_pattern_observations(existing, patterns, antipatterns, score):
    """Map the subagent return shape onto the DB shape, keeping both views.

    Takes already-validated inputs and decides nothing about their shape, so it
    cannot drift from the validator the way its predecessor did.
    """
    obs = dict(existing) if isinstance(existing, dict) else {}
    obs["evidence_schema_version"] = PATTERN_EVIDENCE_SCHEMA_VERSION
    if patterns is not None:
        obs["patterns_detected"] = patterns
        obs["pattern_ids"] = [p.get("pattern_id") for p in patterns if p.get("pattern_id")]
    if antipatterns is not None:
        obs["antipatterns_detected"] = antipatterns
        obs["antipattern_ids"] = [p.get("pattern_id") for p in antipatterns if p.get("pattern_id")]
    if score is not None:
        obs["pattern_score"] = score
    return obs


def merge_talk(
    talk,
    ret,
    run_date=None,
    *,
    catalog=None,
    evidence_context=None,
):
    """Merge one return into its talk. Returns (promoted, stamped, coerced_score).

    Every block is validated BEFORE anything is written, so a malformed return
    leaves the talk untouched rather than half-merged. `run_date` stamps
    `processed_date` when the return omits it; it is never read from the clock
    inside the merge.
    """
    structured = require_mapping(ret, "structured_data")
    verbatim = require_mapping(ret, "verbatim_examples")
    observations = require_mapping(ret, "pattern_observations") or {}
    if not is_empty(ret.get("transcript_path")):
        validate_transcript_path(ret["transcript_path"])
    patterns = require_detections(
        observations,
        "patterns_detected",
        catalog=catalog,
        evidence_context=evidence_context,
    )
    antipatterns = require_detections(
        observations,
        "antipatterns_detected",
        catalog=catalog,
        evidence_context=evidence_context,
    )
    score, coerced_score = resolve_pattern_score(observations, patterns, antipatterns)

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
            talk.get("pattern_observations"), patterns, antipatterns, score)

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
    return promoted, stamped, coerced_score


def migrate_records(db):
    """Bring every talk record to the current schema version. Returns the count.

    `stateful-artifacts` puts migration on the OWNER skill, and this script is
    the tracking DB's only writer. Stamping just the talks a batch happened to
    touch would leave the file permanently mixed-version — a reader could not
    tell an unversioned record from one this writer had never seen, which is the
    ambiguity the version exists to remove.

    v1 to v2 was a stamp-only migration. v3 adds a citation array, so older
    detections receive the additive empty default. Empty is deliberate: legacy
    prose was never source-located and must not be relabeled as verified.
    """
    if not isinstance(db, dict) or not isinstance(db.get("talks"), list):
        raise ValueError("tracking database must be an object with a `talks` array")
    talks = db["talks"]

    # Validate every version before mutating the first record. A future-version
    # entry late in the file must not leave an in-memory caller half-migrated.
    for talk in talks:
        if not isinstance(talk, dict):
            raise ValueError("tracking database `talks` entries must be objects")
        version = talk.get("schema_version")
        if version == TALK_SCHEMA_VERSION:
            continue
        if isinstance(version, bool) or (
            version is not None and not isinstance(version, int)
        ):
            raise ValueError(
                f"talk {talk.get('filename')!r} has invalid schema_version {version!r}"
            )
        if isinstance(version, int) and version > TALK_SCHEMA_VERSION:
            raise ValueError(
                f"talk {talk.get('filename')!r} has future schema_version {version}; "
                f"this writer supports at most {TALK_SCHEMA_VERSION} and will not downgrade it"
            )
        if isinstance(version, int) and version < 0:
            raise ValueError(
                f"talk {talk.get('filename')!r} has invalid schema_version {version}"
            )

    migrated = 0
    for talk in talks:
        if talk.get("schema_version") == TALK_SCHEMA_VERSION:
            continue
        observations = talk.get("pattern_observations")
        if isinstance(observations, dict):
            observations["evidence_schema_version"] = PATTERN_EVIDENCE_SCHEMA_VERSION
            for field in ("patterns_detected", "antipatterns_detected"):
                detections = observations.get(field)
                if isinstance(detections, list):
                    for detection in detections:
                        if isinstance(detection, dict):
                            detection.setdefault("evidence_citations", [])
        talk["schema_version"] = TALK_SCHEMA_VERSION
        migrated += 1
    return migrated


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

    try:
        catalog = load_pattern_catalog()
    except (OSError, ValueError) as exc:
        print(f"ERROR: cannot load the pattern catalog: {exc}", file=sys.stderr)
        sys.exit(1)

    # Migrate the whole artifact, not just the talks this batch touches.
    try:
        migrated = migrate_records(db)
    except ValueError as exc:
        print(f"ERROR: cannot migrate tracking database: {exc}", file=sys.stderr)
        sys.exit(1)

    by_name = {t.get("filename"): t for t in db.get("talks", [])}
    summary = []
    for ret in returns:
        if not isinstance(ret, dict):
            print(
                f"ERROR: batch return entry is a {type(ret).__name__}, not an object",
                file=sys.stderr,
            )
            sys.exit(1)
        name = ret.get("filename")
        talk = by_name.get(name)
        if talk is None:
            # Fail visibly — a return with no matching talk means an upstream
            # mismatch, not something to silently skip.
            print(f"ERROR: no talk in DB matches return filename: {name!r}", file=sys.stderr)
            sys.exit(1)
        try:
            evidence_context = build_evidence_context(Path(db_path).parent, talk, ret)
            promoted, stamped, coerced = merge_talk(
                talk,
                ret,
                run_date,
                catalog=catalog,
                evidence_context=evidence_context,
            )
        except ValueError as exc:
            print(f"ERROR: {name}: {exc}", file=sys.stderr)
            sys.exit(1)
        summary.append({"filename": name, "status": talk.get("status"),
                        "promoted": promoted, "stamped_processed_date": stamped,
                        "coerced_pattern_score": coerced})

    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

    json.dump({"persisted": len(summary), "db_path": db_path, "run_date": run_date,
               "schema_version": TALK_SCHEMA_VERSION, "migrated_records": migrated,
               "talks": summary}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
