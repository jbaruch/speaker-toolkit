#!/usr/bin/env python3
"""Shared validation for vault-ingress subagent returns.

Both persistence surfaces import this module. A return is either valid for both
the tracking database and the rendered analysis, or neither surface is changed.
The pattern catalog is loaded from the installed plugin by default; callers may
inject another catalog directory for tests.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml


ANALYSIS_STATUSES = frozenset({"processed", "processed_partial"})
SKIPPED_STATUSES = frozenset({
    "skipped_no_sources",
    "skipped_download_failed",
    "skipped_duplicate",
})
RETURN_STATUSES = ANALYSIS_STATUSES | SKIPPED_STATUSES
SLIDE_SOURCES = frozenset({"pptx", "pdf", "both", "video_extracted", "none"})
TRANSCRIPT_SOURCES = frozenset({"youtube_auto", "whisper", "manual", "none"})
CONFIDENCE_LEVELS = frozenset({"strong", "moderate", "weak"})
EVIDENCE_SOURCES = frozenset({
    "static_slides",
    "native_deck",
    "delivery_video",
    "transcript",
    "source_comparison",
})
CATALOG_FEEDBACK_LISTS = frozenset({
    "unmatched_observations",
    "confusable_pairs",
    "definition_problems",
    "scoring_problems",
    "tensions",
})
PROSE_FIELDS = (
    "rhetoric_notes",
    "areas_for_improvement",
    "adherence_assessment",
    "new_patterns",
    "summary_updates",
)
LANGUAGE_RE = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$")


class ReturnValidationError(ValueError):
    """A subagent return violates the shared ingress contract."""


@dataclass(frozen=True)
class CatalogEntry:
    pattern_id: str
    entry_type: str
    observable: bool
    evaluable_from: frozenset[str] | None
    path: str


@dataclass(frozen=True)
class PatternCatalog:
    entries: dict[str, CatalogEntry]
    fingerprint: str


def default_catalog_dir() -> Path:
    """Return the bundled Presentation Patterns catalog directory."""
    return (Path(__file__).resolve().parents[2] / "presentation-creator" /
            "references" / "patterns")


def _frontmatter(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReturnValidationError(f"cannot read catalog entry {path}: {exc}") from exc
    if not text.startswith("---\n"):
        raise ReturnValidationError(f"catalog entry {path} has no YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ReturnValidationError(f"catalog entry {path} has unterminated frontmatter")
    try:
        front = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError as exc:
        raise ReturnValidationError(
            f"catalog entry {path} has invalid YAML frontmatter: {exc}") from exc
    if not isinstance(front, dict):
        raise ReturnValidationError(f"catalog entry {path} frontmatter is not an object")
    return front


@lru_cache(maxsize=8)
def load_catalog(catalog_dir: str | Path | None = None) -> PatternCatalog:
    """Load catalog identity, polarity and observability plus a content hash."""
    root = Path(catalog_dir) if catalog_dir is not None else default_catalog_dir()
    paths = sorted(path for path in root.glob("*/*.md") if path.is_file())
    if not paths:
        raise ReturnValidationError(f"no pattern entries found under {root}")

    entries: dict[str, CatalogEntry] = {}
    digest = hashlib.sha256()
    for path in paths:
        front = _frontmatter(path)
        pattern_id = front.get("id")
        entry_type = front.get("type")
        if not isinstance(pattern_id, str) or not pattern_id:
            raise ReturnValidationError(f"catalog entry {path} has no string `id`")
        if pattern_id in entries:
            raise ReturnValidationError(
                f"duplicate catalog id {pattern_id!r}: {entries[pattern_id].path} and {path}")
        if entry_type not in {"pattern", "antipattern"}:
            raise ReturnValidationError(
                f"catalog entry {path} has invalid type {entry_type!r}")
        observable = front.get("observable", True)
        if not isinstance(observable, bool):
            raise ReturnValidationError(
                f"catalog entry {path} has non-boolean observable={observable!r}")
        gate_fields = {
            "evaluable_from", "evidence_requirements", "not_evaluable_when"}
        present_gates = gate_fields.intersection(front)
        evaluable_from = None
        if present_gates:
            if present_gates != gate_fields:
                raise ReturnValidationError(
                    f"catalog entry {path} has a partial evidence gate: "
                    f"{sorted(present_gates)}")
            raw_sources = front["evaluable_from"]
            if (not isinstance(raw_sources, list) or not raw_sources or
                    any(source not in EVIDENCE_SOURCES for source in raw_sources)):
                raise ReturnValidationError(
                    f"catalog entry {path} has invalid evaluable_from={raw_sources!r}")
            evaluable_from = frozenset(raw_sources)
        relative = path.relative_to(root).as_posix()
        entries[pattern_id] = CatalogEntry(
            pattern_id=pattern_id,
            entry_type=entry_type,
            observable=observable,
            evaluable_from=evaluable_from,
            path=relative,
        )
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return PatternCatalog(entries=entries, fingerprint=digest.hexdigest())


def _require_string(obj: dict, field: str, *, allow_empty: bool = False) -> str:
    value = obj.get(field)
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        suffix = "a string" if allow_empty else "a non-empty string"
        raise ReturnValidationError(f"{field} must be {suffix}, got {value!r}")
    return value


def _validate_detection_list(
        observations: dict, field: str, expected_type: str,
        catalog: PatternCatalog, available_sources: set[str]) -> list[dict]:
    value = observations.get(field)
    if not isinstance(value, list):
        raise ReturnValidationError(
            f"pattern_observations.{field} must be an array of detection objects")

    seen: set[str] = set()
    for index, detection in enumerate(value):
        label = f"pattern_observations.{field}[{index}]"
        if not isinstance(detection, dict):
            raise ReturnValidationError(f"{label} must be an object")
        pattern_id = _require_string(detection, "pattern_id")
        if pattern_id in seen:
            raise ReturnValidationError(f"{field} contains duplicate id {pattern_id!r}")
        seen.add(pattern_id)
        entry = catalog.entries.get(pattern_id)
        if entry is None:
            raise ReturnValidationError(
                f"{label}.pattern_id {pattern_id!r} is not in the Presentation Patterns catalog")
        if entry.entry_type != expected_type:
            raise ReturnValidationError(
                f"{pattern_id!r} is a catalog {entry.entry_type}, so it cannot appear in {field}")
        if not entry.observable:
            raise ReturnValidationError(
                f"{pattern_id!r} is observable:false and cannot be scored from ingress artifacts")
        confidence = detection.get("confidence")
        if confidence not in CONFIDENCE_LEVELS:
            raise ReturnValidationError(
                f"{label}.confidence must be one of {sorted(CONFIDENCE_LEVELS)}, "
                f"got {confidence!r}")
        evidence_source = detection.get("evidence_source")
        if evidence_source not in EVIDENCE_SOURCES:
            raise ReturnValidationError(
                f"{label}.evidence_source must be one of {sorted(EVIDENCE_SOURCES)}, "
                f"got {evidence_source!r}")
        if evidence_source not in available_sources:
            raise ReturnValidationError(
                f"{label}.evidence_source {evidence_source!r} is not listed in "
                "pattern_observations.evidence_sources")
        if entry.evaluable_from is not None and evidence_source not in entry.evaluable_from:
            raise ReturnValidationError(
                f"{pattern_id!r} cannot be evaluated from {evidence_source!r}; "
                f"catalog allows {sorted(entry.evaluable_from)}")
        _require_string(detection, "evidence")
        dimensions = detection.get("dimensions")
        if dimensions is not None:
            if (not isinstance(dimensions, list) or
                    any(isinstance(item, bool) or not isinstance(item, int) or
                        item < 1 or item > 14 for item in dimensions)):
                raise ReturnValidationError(
                    f"{label}.dimensions must be an array of integers from 1 through 14")
    return value


def _validate_available_sources(observations: dict, slide_source: str,
                                transcript_source: str | None) -> set[str]:
    sources = observations.get("evidence_sources")
    if (not isinstance(sources, list) or not sources or
            any(source not in EVIDENCE_SOURCES for source in sources)):
        raise ReturnValidationError(
            "pattern_observations.evidence_sources is required and must be a "
            f"non-empty array drawn from {sorted(EVIDENCE_SOURCES)}")
    if len(sources) != len(set(sources)):
        raise ReturnValidationError("pattern_observations.evidence_sources contains duplicates")
    available = set(sources)
    if transcript_source == "none" and "transcript" in available:
        raise ReturnValidationError(
            "evidence_sources includes transcript but transcript_source is none")
    if slide_source == "none" and available.intersection(
            {"static_slides", "native_deck", "delivery_video", "source_comparison"}):
        raise ReturnValidationError(
            "slide_source none cannot support visual evidence_sources")
    if slide_source not in {"pptx", "both"} and "native_deck" in available:
        raise ReturnValidationError(
            f"evidence_sources includes native_deck but slide_source is {slide_source!r}")
    if "source_comparison" in available:
        comparable = available.intersection(
            {"static_slides", "native_deck", "delivery_video"})
        if len(comparable) < 2:
            raise ReturnValidationError(
                "source_comparison requires at least two visual sources in "
                "pattern_observations.evidence_sources")
    return available


def _validate_not_evaluable(observations: dict, catalog: PatternCatalog,
                            available_sources: set[str]) -> list[dict]:
    entries = observations.get("not_evaluable")
    if not isinstance(entries, list):
        raise ReturnValidationError(
            "pattern_observations.not_evaluable is required and must be an array")
    seen = set()
    for index, item in enumerate(entries):
        label = f"pattern_observations.not_evaluable[{index}]"
        if not isinstance(item, dict):
            raise ReturnValidationError(f"{label} must be an object")
        pattern_id = _require_string(item, "pattern_id")
        if pattern_id in seen:
            raise ReturnValidationError(f"not_evaluable contains duplicate id {pattern_id!r}")
        seen.add(pattern_id)
        entry = catalog.entries.get(pattern_id)
        if entry is None:
            raise ReturnValidationError(f"{label}.pattern_id {pattern_id!r} is not in the catalog")
        if entry.evaluable_from is None:
            raise ReturnValidationError(
                f"{pattern_id!r} has no source-aware evidence gate and cannot be "
                "classified as not_evaluable")
        source = item.get("evidence_source")
        if source not in EVIDENCE_SOURCES:
            raise ReturnValidationError(
                f"{label}.evidence_source must be one of {sorted(EVIDENCE_SOURCES)}")
        if source not in available_sources:
            raise ReturnValidationError(
                f"{label}.evidence_source {source!r} is not listed in evidence_sources")
        _require_string(item, "reason")
    return entries


def _validate_score(observations: dict, pattern_count: int, antipattern_count: int) -> None:
    if "pattern_score" not in observations:
        raise ReturnValidationError("pattern_observations.pattern_score is required")
    raw = observations["pattern_score"]
    expected = pattern_count - antipattern_count
    if isinstance(raw, bool):
        raise ReturnValidationError("pattern_observations.pattern_score cannot be a boolean")
    if isinstance(raw, int):
        if raw != expected:
            raise ReturnValidationError(
                f"pattern_score is {raw}, but {pattern_count} patterns minus "
                f"{antipattern_count} antipatterns is {expected}")
        return
    if not isinstance(raw, dict):
        raise ReturnValidationError(
            "pattern_observations.pattern_score must be an integer or the declared score object")

    required = {
        "patterns_used": pattern_count,
        "antipatterns_detected": antipattern_count,
        "score": expected,
    }
    for field, wanted in required.items():
        value = raw.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ReturnValidationError(f"pattern_score.{field} must be an integer")
        if value != wanted:
            raise ReturnValidationError(
                f"pattern_score.{field} is {value}, but the detection arrays require {wanted}")


def _validate_structured_data(structured: dict) -> None:
    if "co_presenter" in structured and not isinstance(structured["co_presenter"], bool):
        raise ReturnValidationError("structured_data.co_presenter must be a boolean")
    if "co_presenters" in structured:
        names = structured["co_presenters"]
        if (not isinstance(names, list) or
                any(not isinstance(name, str) or not name.strip() for name in names)):
            raise ReturnValidationError(
                "structured_data.co_presenters must be an array of non-empty names")
    if structured.get("co_presenter") is True and not structured.get("co_presenters"):
        raise ReturnValidationError(
            "structured_data.co_presenter is true, so co_presenters must name the speakers")
    language = structured.get("delivery_language")
    if language is not None and (not isinstance(language, str) or
                                 not LANGUAGE_RE.fullmatch(language)):
        raise ReturnValidationError(
            "structured_data.delivery_language must be a lowercase language code "
            f"such as 'en' or 'pt-br', got {language!r}")


def _validate_catalog_feedback(feedback) -> None:
    if not isinstance(feedback, dict):
        raise ReturnValidationError("catalog_feedback is required and must be an object")
    for field in CATALOG_FEEDBACK_LISTS:
        if field not in feedback:
            raise ReturnValidationError(f"catalog_feedback.{field} is required")
        if not isinstance(feedback[field], list):
            raise ReturnValidationError(f"catalog_feedback.{field} must be an array")


def _validate_clear_fields(value) -> None:
    if value is None:
        return
    if not isinstance(value, list) or any(not isinstance(path, str) or not path for path in value):
        raise ReturnValidationError("clear_fields must be an array of non-empty dotted paths")
    if len(value) != len(set(value)):
        raise ReturnValidationError("clear_fields contains duplicate paths")
    scalar_roots = {
        "rhetoric_notes", "areas_for_improvement", "adherence_assessment",
        "transcript_source", "slide_source",
    }
    nested_roots = {"structured_data", "verbatim_examples", "pattern_observations"}
    for path in value:
        parts = path.split(".")
        if any(not part for part in parts):
            raise ReturnValidationError(f"clear_fields path {path!r} has an empty segment")
        if parts[0] in scalar_roots and len(parts) == 1:
            continue
        if parts[0] in nested_roots and len(parts) >= 2:
            continue
        raise ReturnValidationError(
            f"clear_fields path {path!r} is outside the analysis-owned allowlist")


def _validate_queue_claim(value) -> None:
    if not isinstance(value, dict):
        raise ReturnValidationError(
            "queue_claim is required and must copy run_id, batch_id, and "
            "reprocess_generation from the claimed talk")
    for field in ("run_id", "batch_id"):
        item = value.get(field)
        if (not isinstance(item, str) or not item or item.strip() != item or
                any(char.isspace() for char in item)):
            raise ReturnValidationError(
                f"queue_claim.{field} must be a non-empty token without whitespace")
    generation = value.get("reprocess_generation")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
        raise ReturnValidationError(
            "queue_claim.reprocess_generation must be a positive integer")


def validate_claim_against_talk(talk, ret, *, allow_completed=False) -> None:
    """Match a validated return to the talk's active generation lease."""
    expected = talk.get("_queue_claim") if isinstance(talk, dict) else None
    supplied = ret.get("queue_claim") if isinstance(ret, dict) else None
    filename = talk.get("filename", "<unknown>") if isinstance(talk, dict) else "<unknown>"
    allowed_states = {"claimed", "completed"} if allow_completed else {"claimed"}
    if not isinstance(expected, dict) or expected.get("state") not in allowed_states:
        raise ReturnValidationError(
            f"{filename} has no active queue claim; refusing an unclaimed or replayed return")
    for field in ("run_id", "batch_id", "reprocess_generation"):
        if supplied.get(field) != expected.get(field):
            raise ReturnValidationError(
                f"queue_claim.{field} {supplied.get(field)!r} does not match active "
                f"claim value {expected.get(field)!r}")
    if expected.get("state") == "claimed" and talk.get("status") != "reprocessing-inflight":
        raise ReturnValidationError(
            f"{filename} has an active claim but status is {talk.get('status')!r}, "
            "expected 'reprocessing-inflight'")
    if expected.get("state") == "completed":
        if expected.get("result_status") != ret.get("status"):
            raise ReturnValidationError(
                f"{filename} completed claim result {expected.get('result_status')!r} "
                f"does not match return status {ret.get('status')!r}")
        if talk.get("status") != ret.get("status"):
            raise ReturnValidationError(
                f"{filename} DB status {talk.get('status')!r} does not match completed "
                f"return status {ret.get('status')!r}")


def validate_return(ret, catalog: PatternCatalog | None = None) -> None:
    """Validate one return completely, raising before either writer mutates state."""
    if not isinstance(ret, dict):
        raise ReturnValidationError(
            f"subagent return must be an object, got {type(ret).__name__}")
    _require_string(ret, "filename")
    status = ret.get("status")
    if status not in RETURN_STATUSES:
        raise ReturnValidationError(
            f"status is required and must be one of {sorted(RETURN_STATUSES)}, got {status!r}")
    _validate_queue_claim(ret.get("queue_claim"))
    _validate_clear_fields(ret.get("clear_fields"))

    transcript_source = ret.get("transcript_source")
    if transcript_source is not None and transcript_source not in TRANSCRIPT_SOURCES:
        raise ReturnValidationError(
            f"transcript_source must be one of {sorted(TRANSCRIPT_SOURCES)}, "
            f"got {transcript_source!r}")

    if status not in ANALYSIS_STATUSES:
        return

    slide_source = ret.get("slide_source")
    if slide_source not in SLIDE_SOURCES:
        raise ReturnValidationError(
            f"slide_source is required for {status} and must be one of "
            f"{sorted(SLIDE_SOURCES)}, got {slide_source!r}")
    if status == "processed" and slide_source == "none":
        raise ReturnValidationError(
            "status processed requires slide evidence; use processed_partial for slide_source none")

    for field in PROSE_FIELDS:
        if field not in ret:
            raise ReturnValidationError(f"{field} is required and must be a string")
        if not isinstance(ret[field], str):
            raise ReturnValidationError(f"{field} must be a string, got {type(ret[field]).__name__}")

    structured = ret.get("structured_data")
    if not isinstance(structured, dict):
        raise ReturnValidationError("structured_data is required and must be an object")
    _validate_structured_data(structured)
    verbatim = ret.get("verbatim_examples")
    if not isinstance(verbatim, dict):
        raise ReturnValidationError("verbatim_examples is required and must be an object")
    observations = ret.get("pattern_observations")
    if not isinstance(observations, dict):
        raise ReturnValidationError("pattern_observations is required and must be an object")

    resolved_catalog = catalog or load_catalog()
    available_sources = _validate_available_sources(
        observations, slide_source, transcript_source)
    patterns = _validate_detection_list(
        observations, "patterns_detected", "pattern", resolved_catalog,
        available_sources)
    antipatterns = _validate_detection_list(
        observations, "antipatterns_detected", "antipattern", resolved_catalog,
        available_sources)
    not_evaluable = _validate_not_evaluable(
        observations, resolved_catalog, available_sources)
    overlap = ({item["pattern_id"] for item in patterns} &
               {item["pattern_id"] for item in antipatterns})
    if overlap:
        raise ReturnValidationError(
            f"pattern ids cannot appear in both detection lanes: {sorted(overlap)}")
    evaluated = ({item["pattern_id"] for item in patterns} |
                 {item["pattern_id"] for item in antipatterns})
    unavailable_overlap = evaluated & {item["pattern_id"] for item in not_evaluable}
    if unavailable_overlap:
        raise ReturnValidationError(
            "pattern ids cannot be both detected and not_evaluable: "
            f"{sorted(unavailable_overlap)}")
    _validate_score(observations, len(patterns), len(antipatterns))
    _validate_catalog_feedback(ret.get("catalog_feedback"))


def audit_batch(returns, catalog: PatternCatalog | None = None):
    """Return (catalog, errors) after checking every entry and duplicate name."""
    if not isinstance(returns, list):
        raise ReturnValidationError(
            f"batch-returns must be a JSON array, got {type(returns).__name__}")
    resolved_catalog = catalog or load_catalog()
    seen: set[str] = set()
    errors = []
    for index, ret in enumerate(returns):
        try:
            validate_return(ret, resolved_catalog)
        except ReturnValidationError as exc:
            name = ret.get("filename") if isinstance(ret, dict) else None
            label = name or f"entry {index}"
            errors.append({"index": index, "filename": name, "error": f"{label}: {exc}"})
        name = ret.get("filename") if isinstance(ret, dict) else None
        if not isinstance(name, str) or not name:
            continue
        if name in seen:
            errors.append({
                "index": index,
                "filename": name,
                "error": f"duplicate return filename {name!r}",
            })
        seen.add(name)
    return resolved_catalog, errors


def validate_batch(returns, catalog: PatternCatalog | None = None) -> PatternCatalog:
    """Validate a full batch, including duplicate filenames, and return catalog metadata."""
    resolved_catalog, errors = audit_batch(returns, catalog)
    if errors:
        raise ReturnValidationError(errors[0]["error"])
    return resolved_catalog


def validation_report(returns, catalog: PatternCatalog) -> dict:
    """Build the stable JSON result emitted by the validator CLI."""
    return {
        "valid": True,
        "returns": len(returns),
        "filenames": [ret["filename"] for ret in returns],
        "catalog_entries": len(catalog.entries),
        "catalog_fingerprint": catalog.fingerprint,
    }


def load_json(path: str | Path, label: str):
    """Load JSON with an exception suitable for a CLI diagnostic."""
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise ReturnValidationError(f"{label} file not found: {path}") from exc
    except OSError as exc:
        raise ReturnValidationError(f"cannot read {label} file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ReturnValidationError(f"{label} file {path} is not valid JSON: {exc}") from exc
