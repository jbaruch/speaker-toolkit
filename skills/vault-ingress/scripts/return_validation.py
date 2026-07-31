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
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import NoReturn

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
VIDEO_SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
VIDEO_EXTRACTION_SCHEMA_VERSION = 3
QUEUE_CLAIM_SCHEMA_VERSION = 1
RETURN_QUEUE_CLAIM_FIELDS = frozenset({
    "run_id",
    "batch_id",
    "reprocess_generation",
})
ACTIVE_QUEUE_CLAIM_FIELDS = frozenset({
    "schema_version",
    "run_id",
    "batch_id",
    "claimed_at",
    "previous_status",
    "reprocess_generation",
    "state",
})
COMPLETED_QUEUE_CLAIM_FIELDS = ACTIVE_QUEUE_CLAIM_FIELDS | frozenset({
    "released_at",
    "release_reason",
    "result_status",
})
CLAIMABLE_PREVIOUS_STATUSES = frozenset({
    "pending",
    "needs-reprocessing",
    "skipped_download_failed",
})
SKIPPED_RETURN_FIELDS = frozenset({
    "filename",
    "queue_claim",
    "status",
})
TRANSCRIPT_REFERENCE_FIELDS = ("transcript_path",)
PDF_REFERENCE_FIELDS = (
    "slides_url",
    "google_drive_id",
    "slides_local_path",
    "slides_pdf_path",
    "pdf_path",
)
AUTHORED_SLIDE_FIELDS = frozenset({
    "slide_count",
    "meme_count",
    "image_only_slide_count",
    "slide_design_style",
    "illustration_style",
    "illustration_coherence",
    "image_source_distribution",
    "visual_continuity_devices",
    "color_coded_backgrounds",
    "background_color_sequence",
    "per_slide_visual",
    "typography_observations",
    "footer_observations",
    "shape_observations",
})


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


@dataclass(frozen=True)
class VideoExtractionState:
    source_video_id: str
    trusted_slide_region: bool


def normalize_processing_stamp(value: object) -> str:
    """Validate and normalize a persistence timestamp.

    Bare dates remain valid for legacy and explicitly day-pinned runs. A full
    timestamp must be timezone-aware and is normalized to UTC at second
    resolution so both persistence surfaces can compare the same value.
    """
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError("processing stamp must be a non-empty string without edge whitespace")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"invalid calendar date {value!r}") from exc
        return value
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid ISO-8601 timestamp {value!r}") from exc
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(
            f"timestamp {value!r} has no timezone — append an explicit offset "
            "such as +00:00")
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


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


def _is_nonempty(value) -> bool:
    """Match persistence semantics: false and zero are meaningful values."""
    return value is not None and value != "" and value != [] and value != {}


def _validate_slides_local_path(ret: dict) -> str | None:
    """Validate the portable vault-relative path written by an ingress return."""
    if "slides_local_path" not in ret:
        return None
    value = _require_string(ret, "slides_local_path")
    if value != value.strip() or "\\" in value:
        raise ReturnValidationError(
            "slides_local_path must be a canonical vault-relative POSIX path")
    path = PurePosixPath(value)
    if (path.is_absolute() or path.as_posix() != value or len(path.parts) != 2 or
            path.parts[0] != "slides" or path.name in {".", ".."} or
            path.suffix.lower() != ".pdf"):
        raise ReturnValidationError(
            "slides_local_path must have the canonical form slides/<artifact>.pdf")
    return value


def _manifest_error(field: str, message: str) -> NoReturn:
    raise ReturnValidationError(
        f"structured_data.video_extraction.{field} {message}")


def _manifest_bool(manifest: dict, field: str) -> bool:
    value = manifest.get(field)
    if not isinstance(value, bool):
        _manifest_error(field, f"must be a boolean, got {value!r}")
    return value


def _manifest_nonnegative_int(manifest: dict, field: str, *, positive=False) -> int:
    value = manifest.get(field)
    if (isinstance(value, bool) or not isinstance(value, int) or value < int(positive)):
        qualifier = "positive" if positive else "non-negative"
        _manifest_error(field, f"must be a {qualifier} integer, got {value!r}")
    return value


def _validate_absolute_manifest_path(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        _manifest_error(field, f"must be a non-empty absolute path, got {value!r}")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        _manifest_error(field, f"must be an absolute path without traversal, got {value!r}")
    return value


def _validate_slide_region(value) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    if (not isinstance(value, list) or len(value) != 4 or
            any(isinstance(item, bool) or not isinstance(item, (int, float))
                for item in value)):
        _manifest_error(
            "slide_region", "must be null or four numeric normalized coordinates")
    left, top, right, bottom = value
    if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
        _manifest_error(
            "slide_region", "must satisfy 0 <= left < right <= 1 and "
            "0 <= top < bottom <= 1")
    return left, top, right, bottom


def validate_video_extraction_manifest(structured: dict) -> VideoExtractionState:
    """Validate a complete schema-v3 manifest and derive authored-slide trust.

    Trust is recomputed from mutually consistent top-level crop provenance and
    the scoped artifact record. A model cannot make context frames look like an
    authored deck merely by setting one optimistic boolean.
    """
    manifest = structured.get("video_extraction")
    if not isinstance(manifest, dict):
        raise ReturnValidationError(
            "slide_source video_extracted requires a complete "
            "structured_data.video_extraction schema-v3 manifest")
    if manifest.get("schema_version") != VIDEO_EXTRACTION_SCHEMA_VERSION:
        _manifest_error(
            "schema_version", f"must be {VIDEO_EXTRACTION_SCHEMA_VERSION}")
    if manifest.get("slide_source") != "video_extracted":
        _manifest_error("slide_source", "must be 'video_extracted'")
    pipeline_version = manifest.get("pipeline_version")
    if (not isinstance(pipeline_version, str) or not pipeline_version.strip() or
            pipeline_version != pipeline_version.strip() or
            any(char.isspace() for char in pipeline_version)):
        _manifest_error("pipeline_version", "must be a non-empty version token")

    source_video_id = manifest.get("source_video_id")
    if (not isinstance(source_video_id, str) or
            not VIDEO_SOURCE_ID_RE.fullmatch(source_video_id)):
        _manifest_error(
            "source_video_id", "must be a non-empty URL-safe identity token")
    source_video_path = _validate_absolute_manifest_path(
        manifest.get("source_video_path"), "source_video_path")
    total_frames = _manifest_nonnegative_int(
        manifest, "total_frames_extracted", positive=True)
    unique_count = _manifest_nonnegative_int(
        manifest, "unique_frame_count", positive=True)
    if unique_count > total_frames:
        _manifest_error(
            "unique_frame_count", "cannot exceed total_frames_extracted")
    if manifest.get("authored_slide_count", object()) is not None:
        _manifest_error(
            "authored_slide_count", "must remain null for sampled video frames")
    _manifest_nonnegative_int(manifest, "hash_threshold_used")
    fps = manifest.get("fps_used")
    if (isinstance(fps, bool) or not isinstance(fps, (int, float)) or fps <= 0):
        _manifest_error("fps_used", f"must be a positive number, got {fps!r}")

    retained = manifest.get("retained_frames")
    if not isinstance(retained, list) or len(retained) != unique_count:
        _manifest_error(
            "retained_frames", "must be an array whose length equals "
            "unique_frame_count")
    prior_frame_index = -1
    prior_timestamp = -1.0
    for index, frame in enumerate(retained, start=1):
        label = f"retained_frames[{index - 1}]"
        if not isinstance(frame, dict):
            _manifest_error(label, "must be an object")
        page_number = frame.get("page_number")
        if (isinstance(page_number, bool) or not isinstance(page_number, int) or
                page_number != index):
            _manifest_error(f"{label}.page_number", f"must be {index}")
        frame_index = frame.get("frame_index")
        if (isinstance(frame_index, bool) or not isinstance(frame_index, int) or
                frame_index < 0 or frame_index >= total_frames or
                frame_index <= prior_frame_index):
            _manifest_error(
                f"{label}.frame_index", "must be a strictly increasing "
                "zero-based index below total_frames_extracted")
        timestamp = frame.get("timestamp_seconds")
        if (isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or
                timestamp < 0 or timestamp < prior_timestamp):
            _manifest_error(
                f"{label}.timestamp_seconds", "must be a non-decreasing "
                "non-negative number")
        expected_timestamp = frame_index / fps
        if not math.isclose(
                float(timestamp), expected_timestamp, rel_tol=1e-9, abs_tol=5e-4):
            _manifest_error(
                f"{label}.timestamp_seconds",
                f"must equal frame_index / fps_used ({expected_timestamp})")
        prior_frame_index = frame_index
        prior_timestamp = float(timestamp)

    method = manifest.get("slide_region_method")
    if method not in {"auto", "manual", "none"}:
        _manifest_error(
            "slide_region_method", "must be one of 'auto', 'manual', or 'none'")
    region = _validate_slide_region(manifest.get("slide_region"))
    detected = _manifest_bool(manifest, "slide_region_detected")
    applied = _manifest_bool(manifest, "slide_region_applied")
    verified = _manifest_bool(manifest, "slide_region_verified")
    expected_applied = region is not None
    expected_detected = method == "auto" and expected_applied
    if applied is not expected_applied:
        _manifest_error(
            "slide_region_applied", "must agree with whether slide_region is present")
    if detected is not expected_detected:
        _manifest_error(
            "slide_region_detected", "must be true only for a detected auto region")
    if method == "none" and region is not None:
        _manifest_error("slide_region", "must be null when slide_region_method is none")
    if method == "manual" and region is None:
        _manifest_error("slide_region", "is required for a manual crop")
    if method != "manual" and verified:
        _manifest_error(
            "slide_region_verified", "can be true only for a manual crop")

    trusted = method == "manual" and verified and applied
    review_required = _manifest_bool(manifest, "review_required")
    expected_review_required = not trusted
    if review_required is not expected_review_required:
        _manifest_error(
            "review_required", "must be false exactly when a verified manual "
            "slide region is trusted")
    review_reason = manifest.get("review_reason")
    if review_required:
        if not isinstance(review_reason, str) or not review_reason.strip():
            _manifest_error(
                "review_reason", "must explain why operator review is required")
    elif review_reason is not None:
        _manifest_error("review_reason", "must be null after verified review")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        _manifest_error("artifacts", "must be a non-empty array")
    seen_scopes: set[str] = set()
    for index, artifact in enumerate(artifacts):
        label = f"artifacts[{index}]"
        if not isinstance(artifact, dict):
            _manifest_error(label, "must be an object")
        scope = artifact.get("artifact_scope")
        if scope not in {"slide_region", "full_frame_context"}:
            _manifest_error(
                f"{label}.artifact_scope",
                "must be 'slide_region' or 'full_frame_context'")
        if scope in seen_scopes:
            _manifest_error(f"{label}.artifact_scope", f"duplicates {scope!r}")
        seen_scopes.add(scope)
        artifact_path = _validate_absolute_manifest_path(
            artifact.get("path"), f"{label}.path")
        suffix = ".slide-region.pdf" if scope == "slide_region" else ".context.pdf"
        if Path(artifact_path).name != f"{source_video_id}{suffix}":
            _manifest_error(
                f"{label}.path", f"must end in {source_video_id}{suffix}")
        page_count = artifact.get("page_count")
        if (isinstance(page_count, bool) or not isinstance(page_count, int) or
                page_count != unique_count):
            _manifest_error(
                f"{label}.page_count", "must equal unique_frame_count")
        if artifact.get("source_video_id") != source_video_id:
            _manifest_error(
                f"{label}.source_video_id", "must match source_video_id")
        if artifact.get("source_video_path") != source_video_path:
            _manifest_error(
                f"{label}.source_video_path", "must match source_video_path")
        crop_method = artifact.get("crop_method")
        crop_verified = artifact.get("crop_verified")
        artifact_trusted = artifact.get("trusted_for_authored_slide_analysis")
        if not isinstance(crop_verified, bool):
            _manifest_error(f"{label}.crop_verified", "must be a boolean")
        if not isinstance(artifact_trusted, bool):
            _manifest_error(
                f"{label}.trusted_for_authored_slide_analysis",
                "must be a boolean")
        if scope == "full_frame_context":
            if crop_method != "none" or crop_verified or artifact_trusted:
                _manifest_error(
                    label, "full_frame_context must use crop_method none and "
                    "can never be verified or trusted as authored slides")
        elif (crop_method != method or crop_verified is not verified or
              artifact_trusted is not trusted):
            _manifest_error(
                label, "slide_region crop provenance and trust must match the "
                "top-level manifest")

    if applied and "slide_region" not in seen_scopes:
        _manifest_error("artifacts", "must contain the applied slide_region artifact")
    if not applied and "slide_region" in seen_scopes:
        _manifest_error(
            "artifacts", "cannot contain slide_region when no region was applied")
    if review_required and "full_frame_context" not in seen_scopes:
        _manifest_error(
            "artifacts", "must retain full_frame_context while review is required")
    if trusted and "slide_region" not in seen_scopes:
        _manifest_error("artifacts", "must contain the trusted slide_region artifact")
    return VideoExtractionState(
        source_video_id=source_video_id,
        trusted_slide_region=trusted,
    )


def _validate_video_return(ret: dict, structured: dict,
                           slides_local_path: str | None) -> bool:
    """Return whether the manifest carries trusted authored-slide evidence."""
    state = validate_video_extraction_manifest(structured)
    expected_path = f"slides/{state.source_video_id}.pdf"
    if slides_local_path is not None and slides_local_path != expected_path:
        raise ReturnValidationError(
            "video-extracted slides_local_path must be the promoted path "
            f"{expected_path!r}")
    if slides_local_path is not None and not state.trusted_slide_region:
        raise ReturnValidationError(
            "slides_local_path cannot promote an untrusted video extraction artifact")

    trusted_and_promoted = (
        state.trusted_slide_region and slides_local_path == expected_path)
    if ret["status"] == "processed" and not trusted_and_promoted:
        raise ReturnValidationError(
            "status processed with slide_source video_extracted requires a trusted "
            "schema-v3 slide_region manifest and promoted slides_local_path")
    if slides_local_path is None:
        clear_fields = set(ret.get("clear_fields") or [])
        if "slides_local_path" not in clear_fields:
            raise ReturnValidationError(
                "video_extracted returns without a promoted artifact must clear "
                "slides_local_path so a stale promoted deck cannot survive")
    if not state.trusted_slide_region:
        contaminated = sorted(
            field for field in AUTHORED_SLIDE_FIELDS
            if _is_nonempty(structured.get(field)))
        if contaminated:
            raise ReturnValidationError(
                "context-only video extraction cannot return authored-slide evidence "
                f"in structured_data: {contaminated}")
    return state.trusted_slide_region


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
                                transcript_source: str | None,
                                *, video_static_slides_available=False) -> set[str]:
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
    if (slide_source == "video_extracted" and "static_slides" in available and
            not video_static_slides_available):
        raise ReturnValidationError(
            "evidence_sources includes static_slides, but the video extraction has "
            "no trusted schema-v3 slide_region artifact")
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


def _validate_unavailable_catalog_gates(catalog: PatternCatalog,
                                        available_sources: set[str],
                                        not_evaluable: list[dict]) -> None:
    """Require an explicit outcome for every gate with no qualifying source."""
    recorded = {item["pattern_id"] for item in not_evaluable}
    required = {
        pattern_id for pattern_id, entry in catalog.entries.items()
        if (entry.observable and entry.evaluable_from is not None and
            entry.evaluable_from.isdisjoint(available_sources))
    }
    missing = sorted(required - recorded)
    if missing:
        raise ReturnValidationError(
            "source-gated catalog entries without a qualifying inspected source "
            f"must be marked not_evaluable: {missing}")


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
        "transcript_source", "slide_source", "slides_local_path",
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


def _validate_processed_date(value) -> None:
    if value is None:
        return
    try:
        normalize_processing_stamp(value)
    except (TypeError, ValueError) as exc:
        raise ReturnValidationError(
            "processed_date must be YYYY-MM-DD or a timezone-aware ISO-8601 "
            f"timestamp: {exc}") from exc


def _validate_skipped_return_fields(ret: dict) -> None:
    disallowed = sorted(set(ret) - SKIPPED_RETURN_FIELDS)
    if disallowed:
        raise ReturnValidationError(
            "skipped terminal returns may only close the queue claim; they cannot "
            "mutate or clear prior analysis fields. Remove "
            f"{disallowed}")


def _validate_exact_fields(value: dict, expected: frozenset[str], label: str) -> None:
    actual = set(value)
    if actual == expected:
        return
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    details = []
    if missing:
        details.append(f"missing {missing}")
    if unexpected:
        details.append(f"unexpected {unexpected}")
    raise ReturnValidationError(
        f"{label} must use exactly the schema fields {sorted(expected)}; "
        + "; ".join(details))


def _validate_queue_claim(
        value, *, expected_fields=RETURN_QUEUE_CLAIM_FIELDS,
        label="queue_claim") -> None:
    if not isinstance(value, dict):
        raise ReturnValidationError(
            "queue_claim is required and must copy run_id, batch_id, and "
            "reprocess_generation from the claimed talk")
    _validate_exact_fields(value, expected_fields, label)
    for field in ("run_id", "batch_id"):
        item = value.get(field)
        if (not isinstance(item, str) or not item or item.strip() != item or
                any(char.isspace() for char in item)):
            raise ReturnValidationError(
                f"{label}.{field} must be a non-empty token without whitespace")
    generation = value.get("reprocess_generation")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
        raise ReturnValidationError(
            f"{label}.reprocess_generation must be a positive integer")


def _nonempty_talk_string(talk: dict, field: str) -> bool:
    value = talk.get(field)
    return isinstance(value, str) and bool(value.strip())


def _talk_has_video_source(talk: dict) -> bool:
    return _nonempty_talk_string(talk, "video_url")


def _talk_has_transcript_source(talk: dict) -> bool:
    return (
        any(_nonempty_talk_string(talk, field)
            for field in TRANSCRIPT_REFERENCE_FIELDS)
        or _talk_has_video_source(talk)
    )


def _talk_has_pptx_source(talk: dict) -> bool:
    return _nonempty_talk_string(talk, "pptx_path")


def _talk_has_pdf_source(talk: dict) -> bool:
    return any(_nonempty_talk_string(talk, field) for field in PDF_REFERENCE_FIELDS)


def _validate_stored_claim(expected: dict, filename: str) -> None:
    state = expected.get("state")
    expected_fields = (
        ACTIVE_QUEUE_CLAIM_FIELDS
        if state == "claimed"
        else COMPLETED_QUEUE_CLAIM_FIELDS
    )
    label = f"{filename} queue claim"
    _validate_queue_claim(
        expected, expected_fields=expected_fields, label=label)
    if expected.get("schema_version") != QUEUE_CLAIM_SCHEMA_VERSION:
        raise ReturnValidationError(
            f"{filename} queue claim schema_version must be "
            f"{QUEUE_CLAIM_SCHEMA_VERSION}, got {expected.get('schema_version')!r}")
    claimed_at = expected.get("claimed_at")
    try:
        normalized_claimed_at = normalize_processing_stamp(claimed_at)
    except (TypeError, ValueError) as exc:
        raise ReturnValidationError(
            f"{filename} queue claim claimed_at must be timezone-aware: {exc}") from exc
    if len(normalized_claimed_at) == 10:
        raise ReturnValidationError(
            f"{filename} queue claim claimed_at must be a timezone-aware timestamp, "
            "not a bare date")
    previous = expected.get("previous_status")
    if previous not in CLAIMABLE_PREVIOUS_STATUSES:
        raise ReturnValidationError(
            f"{filename} queue claim previous_status {previous!r} is not claimable")
    if state == "claimed":
        return
    try:
        normalized_released_at = normalize_processing_stamp(expected.get("released_at"))
    except (TypeError, ValueError) as exc:
        raise ReturnValidationError(
            f"{filename} completed queue claim released_at must be timezone-aware: {exc}") from exc
    if len(normalized_released_at) == 10:
        raise ReturnValidationError(
            f"{filename} completed queue claim released_at must be a timezone-aware "
            "timestamp, not a bare date")
    if not _nonempty_talk_string(expected, "release_reason"):
        raise ReturnValidationError(
            f"{filename} completed queue claim must carry release_reason")
    if expected.get("result_status") not in RETURN_STATUSES:
        raise ReturnValidationError(
            f"{filename} completed queue claim has invalid result_status "
            f"{expected.get('result_status')!r}")


def _validate_return_sources_against_talk(talk: dict, ret: dict) -> None:
    """Bind returned provenance/evidence to sources reachable from the talk."""
    transcript_source = ret.get("transcript_source")
    observations = ret.get("pattern_observations")
    evidence_sources = (
        set(observations.get("evidence_sources") or [])
        if isinstance(observations, dict) else set()
    )
    if ((transcript_source in TRANSCRIPT_SOURCES - {"none"}
         or "transcript" in evidence_sources)
            and not _talk_has_transcript_source(talk)):
        raise ReturnValidationError(
            f"{talk.get('filename', '<unknown>')} return claims transcript provenance/evidence, "
            "but the claimed talk has no transcript reference or active video source")

    slide_source = ret.get("slide_source")
    has_pptx = _talk_has_pptx_source(talk)
    has_pdf = _talk_has_pdf_source(talk)
    if slide_source in {"pptx", "both"} and not has_pptx:
        raise ReturnValidationError(
            f"{talk.get('filename', '<unknown>')} return claims slide_source "
            f"{slide_source!r}, but the claimed talk has no pptx_path")
    if slide_source in {"pdf", "both"} and not has_pdf:
        raise ReturnValidationError(
            f"{talk.get('filename', '<unknown>')} return claims slide_source "
            f"{slide_source!r}, but the claimed talk has no independent PDF source")
    if slide_source == "video_extracted" and not _talk_has_video_source(talk):
        raise ReturnValidationError(
            f"{talk.get('filename', '<unknown>')} return claims video-extracted "
            "slides, but the claimed talk has no active video source")
    if "native_deck" in evidence_sources and not has_pptx:
        raise ReturnValidationError(
            f"{talk.get('filename', '<unknown>')} return claims native_deck evidence, "
            "but the claimed talk has no pptx_path")
    if "delivery_video" in evidence_sources and not _talk_has_video_source(talk):
        raise ReturnValidationError(
            f"{talk.get('filename', '<unknown>')} return claims delivery_video evidence, "
            "but the claimed talk has no active video source")


def validate_claim_against_talk(
        talk, ret, *, allow_completed=False, require_completed=False) -> None:
    """Match a validated return to the talk's current generation claim."""
    expected = talk.get("_queue_claim") if isinstance(talk, dict) else None
    supplied = ret.get("queue_claim") if isinstance(ret, dict) else None
    filename = talk.get("filename", "<unknown>") if isinstance(talk, dict) else "<unknown>"
    if require_completed:
        allowed_states = {"completed"}
    elif allow_completed:
        allowed_states = {"claimed", "completed"}
    else:
        allowed_states = {"claimed"}
    if not isinstance(expected, dict) or expected.get("state") not in allowed_states:
        required = "completed queue claim" if require_completed else "active queue claim"
        raise ReturnValidationError(
            f"{filename} has no {required}; refusing an unclaimed or replayed return")
    _validate_stored_claim(expected, filename)
    talk_generation = talk.get("reprocess_generation")
    if (isinstance(talk_generation, bool) or not isinstance(talk_generation, int)
            or talk_generation < 1):
        raise ReturnValidationError(
            f"{filename} talk reprocess_generation must be a positive integer")
    if expected.get("reprocess_generation") != talk_generation:
        raise ReturnValidationError(
            f"{filename} active claim generation "
            f"{expected.get('reprocess_generation')!r} disagrees with talk generation "
            f"{talk_generation!r}")
    if not isinstance(supplied, dict):
        raise ReturnValidationError(
            f"{filename} return has no validated queue_claim")
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
    if (ret.get("status") in ANALYSIS_STATUSES and
            ret.get("slide_source") == "video_extracted"):
        structured = ret.get("structured_data")
        manifest = (
            structured.get("video_extraction")
            if isinstance(structured, dict) else None)
        if not isinstance(manifest, dict):
            raise ReturnValidationError(
                f"{filename} return has no validated video_extraction manifest")
        returned_id = manifest.get("source_video_id")
        expected_id = talk.get("youtube_id")
        if not isinstance(expected_id, str) or not expected_id.strip():
            raise ReturnValidationError(
                f"{filename} has no youtube_id to bind the video extraction manifest")
        if returned_id != expected_id:
            raise ReturnValidationError(
                "structured_data.video_extraction.source_video_id "
                f"{returned_id!r} does not match talk youtube_id {expected_id!r}")
    _validate_return_sources_against_talk(talk, ret)


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
    _validate_processed_date(ret.get("processed_date"))
    slides_local_path = _validate_slides_local_path(ret)

    transcript_source = ret.get("transcript_source")
    if transcript_source is not None and transcript_source not in TRANSCRIPT_SOURCES:
        raise ReturnValidationError(
            f"transcript_source must be one of {sorted(TRANSCRIPT_SOURCES)}, "
            f"got {transcript_source!r}")

    slide_source = ret.get("slide_source")
    if slide_source is not None and slide_source not in SLIDE_SOURCES:
        raise ReturnValidationError(
            f"slide_source must be one of {sorted(SLIDE_SOURCES)}, got {slide_source!r}")

    if status not in ANALYSIS_STATUSES:
        _validate_skipped_return_fields(ret)
        return

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
    video_static_slides_available = False
    if slide_source == "video_extracted":
        video_static_slides_available = _validate_video_return(
            ret, structured, slides_local_path)
    verbatim = ret.get("verbatim_examples")
    if not isinstance(verbatim, dict):
        raise ReturnValidationError("verbatim_examples is required and must be an object")
    observations = ret.get("pattern_observations")
    if not isinstance(observations, dict):
        raise ReturnValidationError("pattern_observations is required and must be an object")

    resolved_catalog = catalog or load_catalog()
    available_sources = _validate_available_sources(
        observations, slide_source, transcript_source,
        video_static_slides_available=video_static_slides_available)
    patterns = _validate_detection_list(
        observations, "patterns_detected", "pattern", resolved_catalog,
        available_sources)
    antipatterns = _validate_detection_list(
        observations, "antipatterns_detected", "antipattern", resolved_catalog,
        available_sources)
    not_evaluable = _validate_not_evaluable(
        observations, resolved_catalog, available_sources)
    _validate_unavailable_catalog_gates(
        resolved_catalog, available_sources, not_evaluable)
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
