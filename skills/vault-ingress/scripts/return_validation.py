#!/usr/bin/env python3
"""Shared validation for vault-ingress subagent returns.

Both persistence surfaces import this module. A return is either valid for both
the tracking database and the rendered analysis, or neither surface is changed.
The pattern catalog is loaded from the installed plugin by default; callers may
inject another catalog directory for tests.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Mapping, NoReturn, cast

from yaml import YAMLError

from artifact_locator import (
    ArtifactLocatorError,
    materialize_native_root,
)
from adherence_baseline import (
    ADHERENCE_BASELINE_SCHEMA_VERSION,
    AdherenceBaselineError,
    LEGACY_ADHERENCE_BASELINE_SCHEMA_VERSION,
    validate_adherence_baseline,
)
from catalog_io import (
    DuplicateYAMLKeyError,
    EvidenceSourceGroups,
    catalog_entry_paths,
    catalog_fingerprint,
    evidence_source_satisfies_gate,
    load_catalog_yaml,
    parse_evidence_source_groups,
    qualifying_evidence_groups,
)
from ingress_contract import (
    IngressContractError,
    has_local_source_artifact,
    has_pdf_source,
    has_pptx_source,
    has_remote_acquisition_source,
    has_transcript_source,
    has_video_source,
    source_capabilities,
    validate_talk_record_schemas,
)
from pattern_evidence import (
    APPLICABILITY_INSPECTION_REASON_CODE,
    EVIDENCE_CHANNELS,
    EVIDENCE_CITATION_FIELDS,
    EVIDENCE_SOURCE_CHANNELS,
    LEGACY_PATTERN_EVIDENCE_SCHEMA_VERSION,
    PATTERN_EVIDENCE_SCHEMA_VERSION,
    POSITIVE_ONLY_ABSENCE_REASON_CODE,
    PatternEvidenceError,
    SOURCE_GATE_PENDING_REASON_CODE,
    SOURCE_INSPECTION_RAW_FIELDS,
    SOURCE_INSPECTION_REASON_CODE,
    TALK_METADATA_FIELDS,
    assess_persisted_pattern_evidence_freshness as assess_artifact_freshness,
    opportunity_coverage_identity,
    required_pptx_evidence_blocking_reason,
    validate_transcript_path,
)
from pptx_evidence import (
    PptxEvidenceError,
    ranges_cover_pages,
    validate_native_deck_audit,
)
from video_evidence import VideoEvidenceAssessment


ANALYSIS_STATUSES = frozenset({"processed", "processed_partial"})
SKIPPED_STATUSES = frozenset(
    {
        "skipped_no_sources",
        "skipped_download_failed",
        "skipped_duplicate",
    }
)
RETURN_STATUSES = ANALYSIS_STATUSES | SKIPPED_STATUSES
SLIDE_SOURCES = frozenset({"pptx", "pdf", "both", "video_extracted", "none"})
TRANSCRIPT_SOURCES = frozenset({"youtube_auto", "whisper", "manual", "none"})
CONFIDENCE_LEVELS = frozenset({"strong", "moderate", "weak"})
EVIDENCE_SOURCE_ORDER = (
    "static_slides",
    "native_deck",
    "delivery_video",
    "transcript",
    "source_comparison",
)
EVIDENCE_SOURCES = frozenset(EVIDENCE_SOURCE_ORDER)
CATALOG_FEEDBACK_LISTS = frozenset(
    {
        "unmatched_observations",
        "confusable_pairs",
        "definition_problems",
        "scoring_problems",
        "tensions",
    }
)
VERBATIM_EXAMPLE_FIELDS = frozenset(
    {
        "signature_phrases",
        "jokes",
        "transitions",
        "audience_addresses",
        "opening_lines",
        "closing_lines",
    }
)
PATTERN_OBSERVATION_RETURN_FIELDS = frozenset(
    {
        "evidence_sources",
        "source_inspection",
        "patterns_detected",
        "antipatterns_detected",
        "not_evaluable",
        "pattern_score",
    }
)
V5_PATTERN_OBSERVATION_RETURN_FIELDS = PATTERN_OBSERVATION_RETURN_FIELDS | {
    "applicability_assessments"
}
PERSISTED_PATTERN_OBSERVATION_FIELDS = frozenset(
    {
        "evidence_schema_version",
        "patterns_detected",
        "pattern_ids",
        "antipatterns_detected",
        "antipattern_ids",
        "not_evaluable",
        "not_evaluable_ids",
        "evidence_sources",
        "source_inspection",
        "pattern_score",
    }
)
V5_PERSISTED_PATTERN_OBSERVATION_FIELDS = PERSISTED_PATTERN_OBSERVATION_FIELDS | {
    "applicability_assessments",
    "pattern_outcomes",
    "opportunity_coverage_identity",
}
LEGACY_PERSISTED_PATTERN_OBSERVATION_FIELDS = PERSISTED_PATTERN_OBSERVATION_FIELDS - {
    "evidence_schema_version",
    "source_inspection",
}
REPLACE_SCALAR = "replace_scalar"
REPLACE_LIST = "replace_list"
ATOMIC_MAP = "atomic_map"
ATOMIC_LIST = "atomic_list"
ADDITIVE_MAP = "additive_map"
STRUCTURED_FIELD_POLICIES = {
    **{
        field: REPLACE_SCALAR
        for field in (
            "delivery_language",
            "co_presenter",
            "slide_count",
            "talk_duration_estimate",
            "meme_count",
            "image_only_slide_count",
            "audience_interaction_count",
            "opening_type",
            "closing_type",
            "narrative_arc_type",
            "slide_design_style",
            "illustration_style",
            "illustration_coherence",
            "image_source_distribution_basis",
        )
    },
    **{
        field: REPLACE_LIST
        for field in (
            "co_presenters",
            "visual_continuity_devices",
            "opening_sequence",
            "closing_sequence",
            "background_color_sequence",
        )
    },
    "per_slide_visual": ATOMIC_LIST,
    **{
        field: ATOMIC_MAP
        for field in (
            "image_source_distribution",
            "color_coded_backgrounds",
            "typography_observations",
            "footer_observations",
            "shape_observations",
            "video_extraction",
            "key_data_points",
            "named_authorities",
            "time_bound_promotion",
            "native_deck_audit",
            "native_timing_audit",
            "source_comparison",
            "source_identity",
            "animation_observations",
            "pptx_pdf_reconciliation",
        )
    },
    "extensions": ADDITIVE_MAP,
}
IMAGE_SOURCE_GROUP = frozenset(
    {
        "image_source_distribution",
        "image_source_distribution_basis",
    }
)
PROSE_FIELDS = (
    "rhetoric_notes",
    "areas_for_improvement",
    "adherence_assessment",
    "new_patterns",
    "summary_updates",
)
SUBSTANTIVE_PROSE_FIELDS = frozenset(
    {
        "rhetoric_notes",
        "areas_for_improvement",
    }
)
LANGUAGE_RE = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$")
CONDITION_ID_RE = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
VIDEO_SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
VIDEO_EXTRACTION_SCHEMA_VERSION = 3
QUEUE_CLAIM_SCHEMA_VERSION = 5
SOURCE_LOCATED_QUEUE_CLAIM_SCHEMA_VERSION = 4
BASELINE_QUEUE_CLAIM_SCHEMA_VERSION = 3
PREVIOUS_QUEUE_CLAIM_SCHEMA_VERSION = 2
LEGACY_QUEUE_CLAIM_SCHEMA_VERSION = 1
LEGACY_RETURN_SCHEMA_VERSION = 1
PREVIOUS_RETURN_SCHEMA_VERSION = 2
BASELINE_RETURN_SCHEMA_VERSION = 3
SOURCE_LOCATED_RETURN_SCHEMA_VERSION = 4
RETURN_SCHEMA_VERSION = 5
# The first return schema whose aggregate is weighted. Below it the flat +1/-1
# contract stands, because that is the arithmetic its worker used.
WEIGHTED_SCORE_RETURN_SCHEMA_VERSION = 6
SUPPORTED_RETURN_SCHEMA_VERSIONS = frozenset(
    {
        LEGACY_RETURN_SCHEMA_VERSION,
        PREVIOUS_RETURN_SCHEMA_VERSION,
        BASELINE_RETURN_SCHEMA_VERSION,
        SOURCE_LOCATED_RETURN_SCHEMA_VERSION,
        RETURN_SCHEMA_VERSION,
    }
)
SNAPSHOT_RETURN_SCHEMA_VERSIONS = frozenset(
    {
        PREVIOUS_RETURN_SCHEMA_VERSION,
        BASELINE_RETURN_SCHEMA_VERSION,
        SOURCE_LOCATED_RETURN_SCHEMA_VERSION,
        RETURN_SCHEMA_VERSION,
    }
)
OUTCOME_GATE_RETURN_SCHEMA_VERSIONS = frozenset(
    {
        BASELINE_RETURN_SCHEMA_VERSION,
        SOURCE_LOCATED_RETURN_SCHEMA_VERSION,
        RETURN_SCHEMA_VERSION,
    }
)
SOURCE_LOCATED_RETURN_SCHEMA_VERSIONS = frozenset(
    {
        SOURCE_LOCATED_RETURN_SCHEMA_VERSION,
        RETURN_SCHEMA_VERSION,
    }
)
EXHAUSTIVE_OUTCOME_RETURN_SCHEMA_VERSIONS = frozenset({RETURN_SCHEMA_VERSION})
# Stays at 5 until a return actually emits a weighted score. The weight table
# below is part of the NEXT scoring generation; bumping this constant now would
# strand every persisted talk on a generation nothing has produced yet, forcing
# a reparse to adopt arithmetic no worker is using.
PATTERN_SCORING_SCHEMA_VERSION = 5
WEIGHTED_PATTERN_SCORING_SCHEMA_VERSION = 6
# Owner decision (#153): the aggregate stays one number, but a strong detection
# and a moderate one stop counting the same. Flat +1/-1 made a slides-only talk
# and a full-evidence talk emit scores that read as equivalent.
#
# The weights are PART OF the scoring schema version — changing a value here is
# a scoring-generation bump under #160, not a tuning knob, because every
# persisted score was computed under the table in force at the time.
DETECTION_WEIGHTS: dict[str, float] = {
    "strong": 1.0,
    "moderate": 0.5,
    "weak": 0.25,
}
ADHERENCE_COMPARISON_SCHEMA_VERSION = 1
MIN_ADHERENCE_BASELINE_TALKS = 10
CURRENT_PATTERN_SCORING_GENERATION_STATUS = "current"
LEGACY_UNBASELINEABLE_SCORING_STATUS = "legacy_unbaselineable"
UNSCORED_PATTERN_SCORING_GENERATION_STATUS = "not_applicable"
RETURN_QUEUE_CLAIM_FIELDS = frozenset(
    {
        "run_id",
        "batch_id",
        "reprocess_generation",
    }
)
BASE_ACTIVE_QUEUE_CLAIM_FIELDS = frozenset(
    {
        "schema_version",
        "run_id",
        "batch_id",
        "claimed_at",
        "previous_status",
        "reprocess_generation",
        "state",
    }
)
ACTIVE_QUEUE_CLAIM_FIELDS = BASE_ACTIVE_QUEUE_CLAIM_FIELDS | frozenset(
    {
        "required_return_schema_version",
        "adherence_baseline",
    }
)
COMPLETED_QUEUE_CLAIM_SUFFIX_FIELDS = frozenset(
    {
        "released_at",
        "release_reason",
        "result_payload_sha256",
        "result_status",
    }
)
COMPLETED_QUEUE_CLAIM_FIELDS = (
    ACTIVE_QUEUE_CLAIM_FIELDS | COMPLETED_QUEUE_CLAIM_SUFFIX_FIELDS
)
PREVIOUS_COMPLETED_QUEUE_CLAIM_FIELDS = (
    BASE_ACTIVE_QUEUE_CLAIM_FIELDS | COMPLETED_QUEUE_CLAIM_SUFFIX_FIELDS
)
LEGACY_COMPLETED_QUEUE_CLAIM_FIELDS = BASE_ACTIVE_QUEUE_CLAIM_FIELDS | (
    COMPLETED_QUEUE_CLAIM_SUFFIX_FIELDS - {"result_payload_sha256"}
)
BASELINE_BOUND_QUEUE_CLAIM_SCHEMA_VERSIONS = frozenset(
    {
        BASELINE_QUEUE_CLAIM_SCHEMA_VERSION,
        SOURCE_LOCATED_QUEUE_CLAIM_SCHEMA_VERSION,
        QUEUE_CLAIM_SCHEMA_VERSION,
    }
)
RECEIPT_QUEUE_CLAIM_SCHEMA_VERSIONS = frozenset(
    {
        PREVIOUS_QUEUE_CLAIM_SCHEMA_VERSION,
        BASELINE_QUEUE_CLAIM_SCHEMA_VERSION,
        SOURCE_LOCATED_QUEUE_CLAIM_SCHEMA_VERSION,
        QUEUE_CLAIM_SCHEMA_VERSION,
    }
)
ADHERENCE_COMPARISON_FIELDS = frozenset(
    {
        "schema_version",
        "baseline",
        "talk_pattern_score",
    }
)
_ADHERENCE_SENTENCE_TERMINATOR = re.compile(r"[.!?]+(?:[\"')\]]+)?(?=\s|$)")
CLAIMABLE_PREVIOUS_STATUSES = frozenset(
    {
        "pending",
        "needs-reprocessing",
        "skipped_download_failed",
    }
)
SKIPPED_RETURN_FIELDS = frozenset(
    {
        "filename",
        "queue_claim",
        "return_schema_version",
        "status",
    }
)
AUTHORED_SLIDE_FIELDS = frozenset(
    {
        "slide_count",
        "meme_count",
        "image_only_slide_count",
        "slide_design_style",
        "illustration_style",
        "illustration_coherence",
        "image_source_distribution",
        "image_source_distribution_basis",
        "visual_continuity_devices",
        "color_coded_backgrounds",
        "background_color_sequence",
        "per_slide_visual",
        "typography_observations",
        "footer_observations",
        "shape_observations",
    }
)
PPTX_RENDER_DEPENDENT_FIELDS = AUTHORED_SLIDE_FIELDS - {"slide_count"}
PER_SLIDE_VISUAL_FIELDS = frozenset(
    {
        "slide_number",
        "background_color_name",
        "content_type",
        "image_composition",
        "has_speech_bubble",
        "has_starburst",
        "has_footer",
    }
)
PER_SLIDE_VISUAL_BOOLEAN_FIELDS = (
    "has_speech_bubble",
    "has_starburst",
    "has_footer",
)
PER_SLIDE_CONTENT_TYPES = frozenset(
    {
        "title",
        "bio",
        "shownotes",
        "content_bullets",
        "data_chart",
        "quote",
        "meme_only",
        "meme_with_text",
        "section_divider",
        "progressive_reveal",
        "comparison_table",
        "hot_take",
        "cta",
        "thanks",
    }
)
PER_SLIDE_IMAGE_COMPOSITIONS = frozenset(
    {
        "full_bleed",
        "full_bleed_with_text",
        "image_left_text_right",
        "image_right_text_left",
        "centered_image_with_title",
        "inset_image",
        "progressive_reveal",
        "screenshot",
        "meme_with_caption",
        "none",
    }
)
MEME_CONTENT_TYPES = frozenset({"meme_only", "meme_with_text"})


class ReturnValidationError(ValueError):
    """A subagent return violates the shared ingress contract.

    ``reason_code`` is the stable, typed classification. Its message may quote
    the rejected input value, so a consumer publishing a public diagnostic
    routes on the reason and never forwards the text.
    """

    def __init__(self, message: str, *, reason_code: str | None = None) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def resolve_return_schema_version(ret: dict) -> int:
    """Return the supported merge-contract version for a subagent result.

    Historical return artifacts had no version field and used the v1 additive
    merge contract.  Keep those artifacts replayable by treating ABSENT as v1,
    while making every declared version exact and fail-closed.
    """
    version = ret.get("return_schema_version", LEGACY_RETURN_SCHEMA_VERSION)
    if isinstance(version, bool) or not isinstance(version, int):
        raise ReturnValidationError(
            "return_schema_version must be one of the supported integers "
            f"{sorted(SUPPORTED_RETURN_SCHEMA_VERSIONS)}, "
            f"got {version!r}"
        )
    if version not in SUPPORTED_RETURN_SCHEMA_VERSIONS:
        raise ReturnValidationError(
            f"unsupported return_schema_version {version}; this reader supports "
            f"{sorted(SUPPORTED_RETURN_SCHEMA_VERSIONS)}"
        )
    return version


@dataclass(frozen=True)
class CatalogEntry:
    pattern_id: str
    entry_type: str
    observable: bool
    evaluable_from: EvidenceSourceGroups | None
    strong_evaluable_from: EvidenceSourceGroups | None
    absence_evaluable_from: EvidenceSourceGroups | None
    evidence_channels: frozenset[str]
    evidence_metadata_fields: frozenset[str]
    vault_dimensions: tuple[int, ...]
    path: str
    not_applicable_when: tuple["NotApplicableCondition", ...] | None = None
    applicability_evaluable_from: EvidenceSourceGroups | None = None

    def detection_gate(self, confidence: str) -> EvidenceSourceGroups | None:
        """Return the effective positive gate for one confidence outcome."""
        if confidence == "strong":
            return self.strong_evaluable_from
        return self.evaluable_from


@dataclass(frozen=True)
class NotApplicableCondition:
    """One stable catalog-authorized reason an observable pattern is inapplicable."""

    condition_id: str
    description: str


@dataclass(frozen=True)
class PatternCatalog:
    entries: dict[str, CatalogEntry]
    fingerprint: str


@dataclass(frozen=True)
class ScoringGenerationAssessment:
    """Canonical detections plus eligibility for the current scoring epoch."""

    patterns_detected: list[dict]
    antipatterns_detected: list[dict]
    reasons: tuple[str, ...]

    @property
    def current(self) -> bool:
        return not self.reasons


@dataclass(frozen=True)
class VideoExtractionState:
    source_video_id: str
    trusted_slide_region: bool


def canonical_return_sha256(ret: dict) -> str:
    """Return a stable receipt for the exact JSON return payload.

    Object key order and insignificant JSON whitespace are normalized; array
    order, strings, numbers, booleans, and null values remain part of the
    payload identity. Both persistence surfaces call this helper so a return
    substituted after the DB merge cannot render a divergent analysis file.
    """
    try:
        encoded = json.dumps(
            ret,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReturnValidationError(
            f"return payload cannot be canonically encoded as JSON: {exc}"
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def normalize_processing_stamp(value: object) -> str:
    """Validate and normalize a persistence timestamp.

    Bare dates remain valid for legacy and explicitly day-pinned runs. A full
    timestamp must be timezone-aware and is normalized to UTC at second
    resolution so both persistence surfaces can compare the same value.
    """
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(
            "processing stamp must be a non-empty string without edge whitespace"
        )
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
            "such as +00:00"
        )
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def default_catalog_dir() -> Path:
    """Return the bundled Presentation Patterns catalog directory."""
    return (
        Path(__file__).resolve().parents[2]
        / "presentation-creator"
        / "references"
        / "patterns"
    )


def _frontmatter(path: Path, content: bytes) -> dict:
    try:
        text = content.decode("utf-8")
    except UnicodeError as exc:
        raise ReturnValidationError(
            f"catalog entry {path} cannot be decoded as UTF-8: {exc}"
        ) from exc
    if not text.startswith("---\n"):
        raise ReturnValidationError(f"catalog entry {path} has no YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ReturnValidationError(
            f"catalog entry {path} has unterminated frontmatter"
        )
    try:
        front = load_catalog_yaml(text[4:end]) or {}
    except DuplicateYAMLKeyError as exc:
        raise ReturnValidationError(
            f"catalog entry {path} has duplicate YAML frontmatter keys: {exc}"
        ) from exc
    except YAMLError as exc:
        raise ReturnValidationError(
            f"catalog entry {path} has invalid YAML frontmatter: {exc}"
        ) from exc
    if not isinstance(front, dict):
        raise ReturnValidationError(
            f"catalog entry {path} frontmatter is not an object"
        )
    return front


def _parse_not_applicable_contract(
    front: dict, path: Path, *, observable: bool
) -> tuple[
    tuple[NotApplicableCondition, ...] | None,
    EvidenceSourceGroups | None,
]:
    """Validate the catalog-owned v5 applicability contract as one unit."""
    fields = {"not_applicable_when", "applicability_evaluable_from"}
    present = fields.intersection(front)
    if not present:
        return None, None
    if present != fields:
        raise ReturnValidationError(
            f"catalog entry {path} has a partial applicability contract: "
            f"{sorted(present)}; {sorted(fields)} are required together"
        )
    if not observable:
        raise ReturnValidationError(
            f"unobservable catalog entry {path} cannot declare an "
            "applicability contract"
        )
    raw_conditions = front["not_applicable_when"]
    if not isinstance(raw_conditions, list) or not raw_conditions:
        raise ReturnValidationError(
            f"catalog entry {path} not_applicable_when must be a non-empty array"
        )
    conditions: list[NotApplicableCondition] = []
    seen: set[str] = set()
    expected_fields = {"condition_id", "description"}
    for index, raw in enumerate(raw_conditions):
        label = f"catalog entry {path} not_applicable_when[{index}]"
        if not isinstance(raw, dict) or set(raw) != expected_fields:
            actual = sorted(raw) if isinstance(raw, dict) else type(raw).__name__
            raise ReturnValidationError(
                f"{label} must contain exactly {sorted(expected_fields)}, got {actual}"
            )
        condition_id = raw.get("condition_id")
        description = raw.get("description")
        if (
            not isinstance(condition_id, str)
            or CONDITION_ID_RE.fullmatch(condition_id) is None
        ):
            raise ReturnValidationError(
                f"{label}.condition_id must be a stable lowercase id using "
                "letters, digits, hyphens, or underscores"
            )
        if condition_id in seen:
            raise ReturnValidationError(
                f"catalog entry {path} has duplicate not-applicable condition "
                f"{condition_id!r}"
            )
        if (
            not isinstance(description, str)
            or not description.strip()
            or description != description.strip()
        ):
            raise ReturnValidationError(
                f"{label}.description must be a non-empty string without edge "
                "whitespace"
            )
        seen.add(condition_id)
        conditions.append(NotApplicableCondition(condition_id, description))
    try:
        applicability_gate = parse_evidence_source_groups(
            front["applicability_evaluable_from"],
            EVIDENCE_SOURCES,
            field_name="applicability_evaluable_from",
        )
    except ValueError as exc:
        raise ReturnValidationError(
            f"catalog entry {path} has invalid applicability gate: {exc}"
        ) from exc
    return tuple(conditions), applicability_gate


@lru_cache(maxsize=8)
def load_catalog(catalog_dir: str | Path | None = None) -> PatternCatalog:
    """Load catalog identity, polarity and observability plus a content hash."""
    root = Path(catalog_dir) if catalog_dir is not None else default_catalog_dir()
    index_path = root / "_index.md"
    try:
        index_content = index_path.read_bytes()
    except OSError as exc:
        raise ReturnValidationError(
            f"cannot read catalog index {index_path}: {exc}"
        ) from exc
    try:
        index_content.decode("utf-8")
    except UnicodeError as exc:
        raise ReturnValidationError(
            f"catalog index {index_path} cannot be decoded as UTF-8: {exc}"
        ) from exc

    paths = catalog_entry_paths(root)
    if not paths:
        raise ReturnValidationError(f"no pattern entries found under {root}")

    entries: dict[str, CatalogEntry] = {}
    fingerprint_contents: list[tuple[str, bytes]] = []
    for path in paths:
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise ReturnValidationError(
                f"cannot read catalog entry {path}: {exc}"
            ) from exc
        front = _frontmatter(path, content)
        pattern_id = front.get("id")
        entry_type = front.get("type")
        if not isinstance(pattern_id, str) or not pattern_id:
            raise ReturnValidationError(f"catalog entry {path} has no string `id`")
        if pattern_id in entries:
            raise ReturnValidationError(
                f"duplicate catalog id {pattern_id!r}: {entries[pattern_id].path} and {path}"
            )
        if entry_type not in {"pattern", "antipattern"}:
            raise ReturnValidationError(
                f"catalog entry {path} has invalid type {entry_type!r}"
            )
        observable = front.get("observable", True)
        if not isinstance(observable, bool):
            raise ReturnValidationError(
                f"catalog entry {path} has non-boolean observable={observable!r}"
            )
        raw_channels = front.get("evidence_channels")
        if observable:
            if (
                not isinstance(raw_channels, list)
                or not raw_channels
                or any(channel not in EVIDENCE_CHANNELS for channel in raw_channels)
                or len(raw_channels) != len(set(raw_channels))
            ):
                raise ReturnValidationError(
                    f"observable catalog entry {path} must declare a non-empty, "
                    "duplicate-free evidence_channels list drawn from "
                    f"{sorted(EVIDENCE_CHANNELS)}"
                )
            evidence_channels = frozenset(raw_channels)
        else:
            if raw_channels not in (None, []):
                raise ReturnValidationError(
                    f"unobservable catalog entry {path} cannot declare "
                    "evidence_channels"
                )
            evidence_channels = frozenset()

        raw_metadata_fields = front.get("evidence_metadata_fields", [])
        if (
            not isinstance(raw_metadata_fields, list)
            or any(field not in TALK_METADATA_FIELDS for field in raw_metadata_fields)
            or len(raw_metadata_fields) != len(set(raw_metadata_fields))
            or bool(raw_metadata_fields) != ("talk_metadata" in evidence_channels)
        ):
            raise ReturnValidationError(
                f"catalog entry {path} has invalid evidence_metadata_fields; "
                "declare a duplicate-free subset of source metadata iff "
                "talk_metadata is an evidence channel"
            )
        evidence_metadata_fields = frozenset(raw_metadata_fields)
        raw_dimensions = front.get("vault_dimensions")
        if (
            not isinstance(raw_dimensions, list)
            or not raw_dimensions
            or any(
                isinstance(dimension, bool)
                or not isinstance(dimension, int)
                or dimension < 1
                or dimension > 14
                for dimension in raw_dimensions
            )
            or len(raw_dimensions) != len(set(raw_dimensions))
        ):
            raise ReturnValidationError(
                f"catalog entry {path} must declare duplicate-free "
                "vault_dimensions integers from 1 through 14"
            )
        vault_dimensions = tuple(raw_dimensions)
        (
            not_applicable_when,
            applicability_evaluable_from,
        ) = _parse_not_applicable_contract(front, path, observable=observable)
        base_gate_fields = {
            "evaluable_from",
            "evidence_requirements",
            "not_evaluable_when",
        }
        outcome_gate_fields = {"strong_evaluable_from", "absence_evaluable_from"}
        present_gates = base_gate_fields.intersection(front)
        present_outcome_gates = outcome_gate_fields.intersection(front)
        evaluable_from = None
        strong_evaluable_from = None
        absence_evaluable_from = None
        if present_gates or present_outcome_gates:
            if present_gates != base_gate_fields:
                raise ReturnValidationError(
                    f"catalog entry {path} has a partial evidence gate: "
                    f"{sorted(present_gates | present_outcome_gates)}"
                )
            raw_sources = front["evaluable_from"]
            try:
                evaluable_from = parse_evidence_source_groups(
                    raw_sources, EVIDENCE_SOURCES
                )
                strong_evaluable_from = parse_evidence_source_groups(
                    front.get("strong_evaluable_from", raw_sources),
                    EVIDENCE_SOURCES,
                    field_name="strong_evaluable_from",
                )
                raw_absence_sources = front.get("absence_evaluable_from", raw_sources)
                absence_evaluable_from = (
                    None
                    if raw_absence_sources is None
                    else parse_evidence_source_groups(
                        raw_absence_sources,
                        EVIDENCE_SOURCES,
                        field_name="absence_evaluable_from",
                    )
                )
            except ValueError as exc:
                raise ReturnValidationError(
                    f"catalog entry {path} has invalid evidence gate: {exc}"
                ) from exc
            for gate_name, gate in (
                ("evaluable_from", evaluable_from),
                ("strong_evaluable_from", strong_evaluable_from),
                ("absence_evaluable_from", absence_evaluable_from),
            ):
                for group in gate or ():
                    for source in group:
                        primary_channels = EVIDENCE_SOURCE_CHANNELS.get(
                            source, frozenset()
                        ) - {"talk_metadata"}
                        if not primary_channels.intersection(evidence_channels):
                            raise ReturnValidationError(
                                f"catalog entry {path} {gate_name} source "
                                f"{source!r} has no compatible non-metadata "
                                "evidence channel; talk_metadata may only "
                                "corroborate a located source"
                            )
        for group in applicability_evaluable_from or ():
            for source in group:
                primary_channels = EVIDENCE_SOURCE_CHANNELS.get(source, frozenset()) - {
                    "talk_metadata"
                }
                if not primary_channels.intersection(evidence_channels):
                    raise ReturnValidationError(
                        f"catalog entry {path} applicability_evaluable_from "
                        f"source {source!r} has no compatible non-metadata "
                        "evidence channel; talk_metadata may only corroborate "
                        "a located source"
                    )
        relative = path.relative_to(root).as_posix()
        entries[pattern_id] = CatalogEntry(
            pattern_id=pattern_id,
            entry_type=entry_type,
            observable=observable,
            evaluable_from=evaluable_from,
            strong_evaluable_from=strong_evaluable_from,
            absence_evaluable_from=absence_evaluable_from,
            evidence_channels=evidence_channels,
            evidence_metadata_fields=evidence_metadata_fields,
            vault_dimensions=vault_dimensions,
            path=relative,
            not_applicable_when=not_applicable_when,
            applicability_evaluable_from=applicability_evaluable_from,
        )
        fingerprint_contents.append((relative, content))
    return PatternCatalog(
        entries=entries,
        fingerprint=catalog_fingerprint(index_content, fingerprint_contents),
    )


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
            "slides_local_path must be a canonical vault-relative POSIX path"
        )
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or len(path.parts) != 2
        or path.parts[0] != "slides"
        or path.name in {".", ".."}
        or path.suffix.lower() != ".pdf"
    ):
        raise ReturnValidationError(
            "slides_local_path must have the canonical form slides/<artifact>.pdf"
        )
    return value


def _manifest_error(field: str, message: str, *, reason: str | None = None) -> NoReturn:
    """Raise a manifest rejection carrying a typed, closed reason.

    The reason defaults to the schema field path — closed, schema-derived, and
    free of the rejected input value the message quotes. A caller that already
    holds a narrower classification (an artifact-locator reason, say) passes it
    as ``reason`` so the specific code survives to the public diagnostic.
    """
    raise ReturnValidationError(
        f"structured_data.video_extraction.{field} {message}",
        reason_code=reason or f"video_extraction.{field}",
    )


def _manifest_bool(manifest: dict, field: str) -> bool:
    value = manifest.get(field)
    if not isinstance(value, bool):
        _manifest_error(field, f"must be a boolean, got {value!r}")
    return value


def _manifest_nonnegative_int(manifest: dict, field: str, *, positive=False) -> int:
    value = manifest.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < int(positive):
        qualifier = "positive" if positive else "non-negative"
        _manifest_error(field, f"must be a {qualifier} integer, got {value!r}")
    return value


def _validate_absolute_manifest_path(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        _manifest_error(field, "must be a non-empty native absolute path")
    try:
        materialize_native_root(value)
    except ArtifactLocatorError as exc:
        reason_message = {
            "artifact_locator_nul_byte": "must not contain a NUL byte",
            "artifact_locator_dot_segment": ("must not contain ambiguous dot segments"),
        }.get(
            exc.reason_code,
            "must be a native absolute path without ambiguous syntax",
        )
        _manifest_error(
            field,
            f"{reason_message} ({exc.reason_code})",
            reason=exc.reason_code,
        )
    return value


def _validate_slide_region(value) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    if (
        not isinstance(value, list)
        or len(value) != 4
        or any(
            isinstance(item, bool) or not isinstance(item, (int, float))
            for item in value
        )
    ):
        _manifest_error(
            "slide_region", "must be null or four numeric normalized coordinates"
        )
    left, top, right, bottom = value
    if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
        _manifest_error(
            "slide_region",
            "must satisfy 0 <= left < right <= 1 and 0 <= top < bottom <= 1",
        )
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
            "structured_data.video_extraction schema-v3 manifest"
        )
    if manifest.get("schema_version") != VIDEO_EXTRACTION_SCHEMA_VERSION:
        _manifest_error("schema_version", f"must be {VIDEO_EXTRACTION_SCHEMA_VERSION}")
    if manifest.get("slide_source") != "video_extracted":
        _manifest_error("slide_source", "must be 'video_extracted'")
    pipeline_version = manifest.get("pipeline_version")
    if (
        not isinstance(pipeline_version, str)
        or not pipeline_version.strip()
        or pipeline_version != pipeline_version.strip()
        or any(char.isspace() for char in pipeline_version)
    ):
        _manifest_error("pipeline_version", "must be a non-empty version token")

    source_video_id = manifest.get("source_video_id")
    if not isinstance(source_video_id, str) or not VIDEO_SOURCE_ID_RE.fullmatch(
        source_video_id
    ):
        _manifest_error(
            "source_video_id", "must be a non-empty URL-safe identity token"
        )
    source_video_path = _validate_absolute_manifest_path(
        manifest.get("source_video_path"), "source_video_path"
    )
    if Path(source_video_path).name != f"{source_video_id}.mp4":
        _manifest_error(
            "source_video_path",
            f"must end in {source_video_id}.mp4",
        )
    total_frames = _manifest_nonnegative_int(
        manifest, "total_frames_extracted", positive=True
    )
    unique_count = _manifest_nonnegative_int(
        manifest, "unique_frame_count", positive=True
    )
    if unique_count > total_frames:
        _manifest_error("unique_frame_count", "cannot exceed total_frames_extracted")
    if manifest.get("authored_slide_count", object()) is not None:
        _manifest_error(
            "authored_slide_count", "must remain null for sampled video frames"
        )
    _manifest_nonnegative_int(manifest, "hash_threshold_used")
    fps = manifest.get("fps_used")
    if isinstance(fps, bool) or not isinstance(fps, (int, float)) or fps <= 0:
        _manifest_error("fps_used", f"must be a positive number, got {fps!r}")

    retained = manifest.get("retained_frames")
    if not isinstance(retained, list) or len(retained) != unique_count:
        _manifest_error(
            "retained_frames", "must be an array whose length equals unique_frame_count"
        )
    prior_frame_index = -1
    prior_timestamp = -1.0
    for index, frame in enumerate(retained, start=1):
        label = f"retained_frames[{index - 1}]"
        if not isinstance(frame, dict):
            _manifest_error(label, "must be an object")
        page_number = frame.get("page_number")
        if (
            isinstance(page_number, bool)
            or not isinstance(page_number, int)
            or page_number != index
        ):
            _manifest_error(f"{label}.page_number", f"must be {index}")
        frame_index = frame.get("frame_index")
        if (
            isinstance(frame_index, bool)
            or not isinstance(frame_index, int)
            or frame_index < 0
            or frame_index >= total_frames
            or frame_index <= prior_frame_index
        ):
            _manifest_error(
                f"{label}.frame_index",
                "must be a strictly increasing "
                "zero-based index below total_frames_extracted",
            )
        timestamp = frame.get("timestamp_seconds")
        if (
            isinstance(timestamp, bool)
            or not isinstance(timestamp, (int, float))
            or timestamp < 0
            or timestamp < prior_timestamp
        ):
            _manifest_error(
                f"{label}.timestamp_seconds",
                "must be a non-decreasing non-negative number",
            )
        expected_timestamp = frame_index / fps
        if not math.isclose(
            float(timestamp), expected_timestamp, rel_tol=1e-9, abs_tol=5e-4
        ):
            _manifest_error(
                f"{label}.timestamp_seconds",
                f"must equal frame_index / fps_used ({expected_timestamp})",
            )
        prior_frame_index = frame_index
        prior_timestamp = float(timestamp)

    method = manifest.get("slide_region_method")
    if method not in {"auto", "manual", "none"}:
        _manifest_error(
            "slide_region_method", "must be one of 'auto', 'manual', or 'none'"
        )
    region = _validate_slide_region(manifest.get("slide_region"))
    detected = _manifest_bool(manifest, "slide_region_detected")
    applied = _manifest_bool(manifest, "slide_region_applied")
    verified = _manifest_bool(manifest, "slide_region_verified")
    expected_applied = region is not None
    expected_detected = method == "auto" and expected_applied
    if applied is not expected_applied:
        _manifest_error(
            "slide_region_applied", "must agree with whether slide_region is present"
        )
    if detected is not expected_detected:
        _manifest_error(
            "slide_region_detected", "must be true only for a detected auto region"
        )
    if method == "none" and region is not None:
        _manifest_error("slide_region", "must be null when slide_region_method is none")
    if method == "manual" and region is None:
        _manifest_error("slide_region", "is required for a manual crop")
    if method != "manual" and verified:
        _manifest_error("slide_region_verified", "can be true only for a manual crop")

    trusted = method == "manual" and verified and applied
    review_required = _manifest_bool(manifest, "review_required")
    expected_review_required = not trusted
    if review_required is not expected_review_required:
        _manifest_error(
            "review_required",
            "must be false exactly when a verified manual slide region is trusted",
        )
    review_reason = manifest.get("review_reason")
    if review_required:
        if not isinstance(review_reason, str) or not review_reason.strip():
            _manifest_error(
                "review_reason", "must explain why operator review is required"
            )
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
                "must be 'slide_region' or 'full_frame_context'",
            )
        if scope in seen_scopes:
            _manifest_error(f"{label}.artifact_scope", f"duplicates {scope!r}")
        seen_scopes.add(scope)
        artifact_path = _validate_absolute_manifest_path(
            artifact.get("path"), f"{label}.path"
        )
        suffix = ".slide-region.pdf" if scope == "slide_region" else ".context.pdf"
        if Path(artifact_path).name != f"{source_video_id}{suffix}":
            _manifest_error(f"{label}.path", f"must end in {source_video_id}{suffix}")
        page_count = artifact.get("page_count")
        if (
            isinstance(page_count, bool)
            or not isinstance(page_count, int)
            or page_count != unique_count
        ):
            _manifest_error(f"{label}.page_count", "must equal unique_frame_count")
        if artifact.get("source_video_id") != source_video_id:
            _manifest_error(f"{label}.source_video_id", "must match source_video_id")
        if artifact.get("source_video_path") != source_video_path:
            _manifest_error(
                f"{label}.source_video_path", "must match source_video_path"
            )
        crop_method = artifact.get("crop_method")
        crop_verified = artifact.get("crop_verified")
        artifact_trusted = artifact.get("trusted_for_authored_slide_analysis")
        if not isinstance(crop_verified, bool):
            _manifest_error(f"{label}.crop_verified", "must be a boolean")
        if not isinstance(artifact_trusted, bool):
            _manifest_error(
                f"{label}.trusted_for_authored_slide_analysis", "must be a boolean"
            )
        if scope == "full_frame_context":
            if crop_method != "none" or crop_verified or artifact_trusted:
                _manifest_error(
                    label,
                    "full_frame_context must use crop_method none and "
                    "can never be verified or trusted as authored slides",
                )
        elif (
            crop_method != method
            or crop_verified is not verified
            or artifact_trusted is not trusted
        ):
            _manifest_error(
                label,
                "slide_region crop provenance and trust must match the "
                "top-level manifest",
            )

    if applied and "slide_region" not in seen_scopes:
        _manifest_error("artifacts", "must contain the applied slide_region artifact")
    if not applied and "slide_region" in seen_scopes:
        _manifest_error(
            "artifacts", "cannot contain slide_region when no region was applied"
        )
    if review_required and "full_frame_context" not in seen_scopes:
        _manifest_error(
            "artifacts", "must retain full_frame_context while review is required"
        )
    if trusted and "slide_region" not in seen_scopes:
        _manifest_error("artifacts", "must contain the trusted slide_region artifact")
    return VideoExtractionState(
        source_video_id=source_video_id,
        trusted_slide_region=trusted,
    )


def _validate_video_return(
    ret: dict, structured: dict, slides_local_path: str | None
) -> bool:
    """Return whether the manifest carries trusted authored-slide evidence."""
    state = validate_video_extraction_manifest(structured)
    expected_path = f"slides/{state.source_video_id}.pdf"
    if slides_local_path is not None and slides_local_path != expected_path:
        raise ReturnValidationError(
            "video-extracted slides_local_path must be the promoted path "
            f"{expected_path!r}"
        )
    if slides_local_path is not None and not state.trusted_slide_region:
        raise ReturnValidationError(
            "slides_local_path cannot promote an untrusted video extraction artifact"
        )

    trusted_and_promoted = (
        state.trusted_slide_region and slides_local_path == expected_path
    )
    if ret["status"] == "processed" and not trusted_and_promoted:
        raise ReturnValidationError(
            "status processed with slide_source video_extracted requires a trusted "
            "schema-v3 slide_region manifest and promoted slides_local_path"
        )
    if slides_local_path is None:
        clear_fields = set(ret.get("clear_fields") or [])
        if "slides_local_path" not in clear_fields:
            raise ReturnValidationError(
                "video_extracted returns without a promoted artifact must clear "
                "slides_local_path so a stale promoted deck cannot survive"
            )
    if not state.trusted_slide_region:
        contaminated = sorted(
            field
            for field in AUTHORED_SLIDE_FIELDS
            if _is_nonempty(structured.get(field))
        )
        if contaminated:
            raise ReturnValidationError(
                "context-only video extraction cannot return authored-slide evidence "
                f"in structured_data: {contaminated}"
            )
    return state.trusted_slide_region


def validate_authored_slide_fields_against_source(
    structured: Mapping[str, object],
    slide_source: str,
) -> None:
    """Reject model-authored slide evidence when no slide lane was used."""
    if slide_source != "none":
        return
    contaminated = sorted(
        field for field in AUTHORED_SLIDE_FIELDS if _is_nonempty(structured.get(field))
    )
    if contaminated:
        raise ReturnValidationError(
            "slide_source none cannot return authored-slide evidence in "
            f"structured_data: {contaminated}"
        )


def canonical_evidence_source_group(group: frozenset[str]) -> list[str]:
    """Return one comparison group in the stable public source order."""
    return [source for source in EVIDENCE_SOURCE_ORDER if source in group]


def qualifying_comparison_groups(
    entry: CatalogEntry,
    confidence: str,
    available_sources: set[str],
    *,
    current_contract: bool = True,
) -> tuple[frozenset[str], ...]:
    """Return satisfied all-of groups for one positive detection outcome."""
    gate = (
        entry.detection_gate(confidence) if current_contract else entry.evaluable_from
    )
    if gate is None:
        return ()
    return tuple(
        group
        for group in qualifying_evidence_groups(gate, available_sources)
        if len(group) > 1
    )


def _validate_comparison_evidence_sources_used(
    detection: dict,
    label: str,
    entry: CatalogEntry,
    confidence: str,
    available_sources: set[str],
    return_schema_version: int,
) -> None:
    """Bind current comparison detections to one exact qualifying source group."""
    evidence_source = detection.get("evidence_source")
    supplied = detection.get("evidence_sources_used")
    if evidence_source != "source_comparison":
        if "evidence_sources_used" in detection:
            raise ReturnValidationError(
                f"{label}.evidence_sources_used is allowed only when "
                "evidence_source is 'source_comparison'"
            )
        return
    if (
        return_schema_version not in OUTCOME_GATE_RETURN_SCHEMA_VERSIONS
        and "evidence_sources_used" not in detection
    ):
        return
    if (
        not isinstance(supplied, list)
        or len(supplied) < 2
        or any(
            source not in EVIDENCE_SOURCES or source == "source_comparison"
            for source in supplied
        )
        or len(supplied) != len(set(supplied))
    ):
        raise ReturnValidationError(
            f"{label}.evidence_sources_used must be a duplicate-free array of "
            "at least two underlying evidence sources"
        )
    supplied_group = frozenset(supplied)
    qualifying = qualifying_comparison_groups(
        entry,
        confidence,
        available_sources,
        current_contract=(return_schema_version in OUTCOME_GATE_RETURN_SCHEMA_VERSIONS),
    )
    if supplied_group not in qualifying:
        allowed = [canonical_evidence_source_group(group) for group in qualifying]
        raise ReturnValidationError(
            f"{label}.evidence_sources_used must exactly match one qualifying "
            f"comparison group; allowed groups are {allowed}"
        )


def _validate_evidence_citations(claim: dict, label: str, entry: CatalogEntry) -> None:
    """Validate a model-owned source-location claim before artifact resolution."""
    citations = claim.get("evidence_citations")
    if not isinstance(citations, list) or not citations:
        raise ReturnValidationError(
            f"{label}.evidence_citations must be a non-empty array"
        )
    evidence_source = claim.get("evidence_source")
    if evidence_source == "source_comparison":
        raw_sources = claim.get("evidence_sources_used")
        expected_sources: frozenset[str] = (
            frozenset(source for source in raw_sources if isinstance(source, str))
            if isinstance(raw_sources, list)
            else frozenset()
        )
    else:
        expected_sources = (
            frozenset({evidence_source})
            if isinstance(evidence_source, str)
            else frozenset()
        )
    covered_sources: set[str] = set()
    for index, citation in enumerate(citations):
        citation_label = f"{label}.evidence_citations[{index}]"
        if not isinstance(citation, dict):
            raise ReturnValidationError(f"{citation_label} must be an object")
        source = citation.get("source")
        if source not in expected_sources:
            raise ReturnValidationError(
                f"{citation_label}.source must belong to the detection's exact "
                f"source set {sorted(expected_sources, key=repr)}"
            )
        channel = citation.get("channel")
        if channel not in EVIDENCE_CHANNELS:
            raise ReturnValidationError(
                f"{citation_label}.channel must be one of "
                f"{sorted(EVIDENCE_CHANNELS)}, got {channel!r}"
            )
        compatible_channels = EVIDENCE_SOURCE_CHANNELS.get(str(source), frozenset())
        if channel not in compatible_channels:
            raise ReturnValidationError(
                f"{citation_label}.channel {channel!r} cannot locate "
                f"source {source!r}; compatible channels are "
                f"{sorted(compatible_channels)}"
            )
        if channel not in entry.evidence_channels:
            raise ReturnValidationError(
                f"{entry.pattern_id!r} cannot be proved through {channel!r}; "
                f"catalog permits {sorted(entry.evidence_channels)}"
            )
        unknown = sorted(set(citation) - EVIDENCE_CITATION_FIELDS[channel])
        if unknown:
            raise ReturnValidationError(
                f"{citation_label} has unknown fields {unknown}"
            )
        if channel in {"transcript", "timed_transcript"}:
            quote = citation.get("quote")
            if not isinstance(quote, str) or not quote.strip():
                raise ReturnValidationError(
                    f"{citation_label}.quote must be a non-empty string"
                )
            translation = citation.get("translation")
            if translation is not None and (
                not isinstance(translation, str) or not translation.strip()
            ):
                raise ReturnValidationError(
                    f"{citation_label}.translation must be a non-empty string"
                )
        elif channel in {"slides", "slide_sequence"}:
            numbers = citation.get("slide_numbers")
            if (
                not isinstance(numbers, list)
                or not numbers
                or any(
                    isinstance(number, bool)
                    or not isinstance(number, int)
                    or number < 1
                    for number in numbers
                )
                or len(numbers) != len(set(numbers))
            ):
                raise ReturnValidationError(
                    f"{citation_label}.slide_numbers must contain unique positive "
                    "integers"
                )
            if channel == "slide_sequence" and (
                len(numbers) < 2
                or any(right != left + 1 for left, right in zip(numbers, numbers[1:]))
            ):
                raise ReturnValidationError(
                    f"{citation_label}.slide_numbers must be a consecutive, "
                    "ascending sequence"
                )
        elif channel == "video":
            start = citation.get("start_seconds")
            end = citation.get("end_seconds")
            if (
                isinstance(start, bool)
                or not isinstance(start, (int, float))
                or isinstance(end, bool)
                or not isinstance(end, (int, float))
                or not math.isfinite(float(start))
                or not math.isfinite(float(end))
                or start < 0
                or end <= start
            ):
                raise ReturnValidationError(
                    f"{citation_label} requires finite non-negative "
                    "start_seconds/end_seconds with end after start"
                )
        else:
            field = citation.get("field")
            if field not in entry.evidence_metadata_fields:
                raise ReturnValidationError(
                    f"{citation_label}.field must be one of "
                    f"{sorted(entry.evidence_metadata_fields)}, got {field!r}"
                )
        if channel != "talk_metadata":
            covered_sources.add(str(source))
    missing = sorted(expected_sources - covered_sources)
    if missing:
        raise ReturnValidationError(
            f"{label}.evidence_citations must locate every exact source; "
            f"missing {missing}"
        )


def _validate_applicability_assessments(
    observations: dict,
    catalog: PatternCatalog,
    available_sources: set[str],
    detected_ids: set[str],
    return_schema_version: int,
) -> list[dict]:
    """Validate worker-authored v5 applicability decisions.

    Whether an assessment is required is intentionally deferred until artifact
    resolution proves complete applicability-gate coverage. This pass owns the
    exact raw shape, catalog authority, polarity, and declared-source gate.
    """
    raw = observations.get("applicability_assessments")
    if return_schema_version != RETURN_SCHEMA_VERSION:
        if raw is not None:
            raise ReturnValidationError(
                "applicability_assessments is supported only by return schema v5"
            )
        return []
    if not isinstance(raw, list):
        raise ReturnValidationError(
            "return-schema v5 pattern observations require an "
            "applicability_assessments array"
        )
    seen: set[str] = set()
    for index, assessment in enumerate(raw):
        label = f"pattern_observations.applicability_assessments[{index}]"
        if not isinstance(assessment, dict):
            raise ReturnValidationError(f"{label} must be an object")
        pattern_id = _require_string(assessment, "pattern_id")
        if pattern_id in seen:
            raise ReturnValidationError(
                f"applicability_assessments contains duplicate id {pattern_id!r}"
            )
        seen.add(pattern_id)
        if pattern_id in detected_ids:
            raise ReturnValidationError(
                f"{pattern_id!r} cannot be both detected and applicability-assessed"
            )
        entry = catalog.entries.get(pattern_id)
        if entry is None:
            raise ReturnValidationError(
                f"{label}.pattern_id {pattern_id!r} is not in the catalog"
            )
        if not entry.observable:
            raise ReturnValidationError(
                f"{pattern_id!r} is observable:false and cannot be "
                "applicability-assessed by ingress"
            )
        gate = entry.applicability_evaluable_from
        conditions = entry.not_applicable_when
        if gate is None or conditions is None:
            raise ReturnValidationError(
                f"{pattern_id!r} has no catalog-owned applicability contract"
            )
        result = assessment.get("result")
        if result not in {"applicable", "not_applicable"}:
            raise ReturnValidationError(
                f"{label}.result must be 'applicable' or 'not_applicable'"
            )
        required_fields = {
            "pattern_id",
            "result",
            "evidence_source",
            "evidence",
            "evidence_citations",
        }
        if result == "not_applicable":
            required_fields.add("condition_id")
        elif "condition_id" in assessment:
            raise ReturnValidationError(
                f"{label}.condition_id is forbidden when result is 'applicable'"
            )
        evidence_source = assessment.get("evidence_source")
        if evidence_source == "source_comparison":
            required_fields.add("evidence_sources_used")
        elif "evidence_sources_used" in assessment:
            raise ReturnValidationError(
                f"{label}.evidence_sources_used is allowed only when "
                "evidence_source is 'source_comparison'"
            )
        actual_fields = set(assessment)
        if actual_fields != required_fields:
            raise ReturnValidationError(
                f"{label} must contain exactly {sorted(required_fields)}; "
                f"missing={sorted(required_fields - actual_fields)}, "
                f"unknown={sorted(actual_fields - required_fields)}"
            )
        if result == "not_applicable":
            authorized = {condition.condition_id for condition in conditions}
            if assessment.get("condition_id") not in authorized:
                raise ReturnValidationError(
                    f"{label}.condition_id must be one of "
                    f"{sorted(authorized)}, got {assessment.get('condition_id')!r}"
                )
        if evidence_source not in EVIDENCE_SOURCES:
            raise ReturnValidationError(
                f"{label}.evidence_source must be one of "
                f"{sorted(EVIDENCE_SOURCES)}, got {evidence_source!r}"
            )
        if evidence_source not in available_sources:
            raise ReturnValidationError(
                f"{label}.evidence_source {evidence_source!r} is not listed in "
                "pattern_observations.evidence_sources"
            )
        if evidence_source == "source_comparison":
            used = assessment.get("evidence_sources_used")
            if (
                not isinstance(used, list)
                or len(used) < 2
                or any(
                    source not in EVIDENCE_SOURCES or source == "source_comparison"
                    for source in used
                )
                or len(used) != len(set(used))
            ):
                raise ReturnValidationError(
                    f"{label}.evidence_sources_used must be a duplicate-free "
                    "array of at least two underlying evidence sources"
                )
            supplied_group = frozenset(used)
            qualifying = tuple(
                group
                for group in qualifying_evidence_groups(gate, available_sources)
                if len(group) > 1
            )
            if supplied_group not in qualifying:
                allowed = [
                    canonical_evidence_source_group(group) for group in qualifying
                ]
                raise ReturnValidationError(
                    f"{label}.evidence_sources_used must exactly match one "
                    f"qualifying applicability group; allowed groups are {allowed}"
                )
        elif not evidence_source_satisfies_gate(
            gate, cast(str, evidence_source), available_sources
        ):
            allowed = [canonical_evidence_source_group(group) for group in gate]
            raise ReturnValidationError(
                f"{pattern_id!r} applicability cannot be evaluated from "
                f"{evidence_source!r}; catalog allows {allowed}"
            )
        _require_string(assessment, "evidence")
        _validate_evidence_citations(assessment, label, entry)
    return raw


def _validate_detection_list(
    observations: dict,
    field: str,
    expected_type: str,
    catalog: PatternCatalog,
    available_sources: set[str],
    return_schema_version: int,
) -> list[dict]:
    value = observations.get(field)
    if not isinstance(value, list):
        raise ReturnValidationError(
            f"pattern_observations.{field} must be an array of detection objects"
        )

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
                f"{label}.pattern_id {pattern_id!r} is not in the Presentation Patterns catalog"
            )
        if entry.entry_type != expected_type:
            raise ReturnValidationError(
                f"{pattern_id!r} is a catalog {entry.entry_type}, so it cannot appear in {field}"
            )
        if not entry.observable:
            raise ReturnValidationError(
                f"{pattern_id!r} is observable:false and cannot be scored from ingress artifacts"
            )
        confidence = detection.get("confidence")
        if confidence not in CONFIDENCE_LEVELS:
            raise ReturnValidationError(
                f"{label}.confidence must be one of {sorted(CONFIDENCE_LEVELS)}, "
                f"got {confidence!r}"
            )
        evidence_source = detection.get("evidence_source")
        if evidence_source not in EVIDENCE_SOURCES:
            raise ReturnValidationError(
                f"{label}.evidence_source must be one of {sorted(EVIDENCE_SOURCES)}, "
                f"got {evidence_source!r}"
            )
        if evidence_source not in available_sources:
            raise ReturnValidationError(
                f"{label}.evidence_source {evidence_source!r} is not listed in "
                "pattern_observations.evidence_sources"
            )
        detection_gate = (
            entry.detection_gate(confidence)
            if return_schema_version in OUTCOME_GATE_RETURN_SCHEMA_VERSIONS
            else entry.evaluable_from
        )
        if (
            return_schema_version in SOURCE_LOCATED_RETURN_SCHEMA_VERSIONS
            and detection_gate is None
        ):
            raise ReturnValidationError(
                f"{pattern_id!r} has no owner-approved source gate and cannot "
                "be detected by a current return"
            )
        gate_satisfied = detection_gate is None or evidence_source_satisfies_gate(
            detection_gate, evidence_source, available_sources
        )
        legacy_unresolved_comparison = (
            return_schema_version not in OUTCOME_GATE_RETURN_SCHEMA_VERSIONS
            and evidence_source == "source_comparison"
            and "evidence_sources_used" not in detection
        )
        if not gate_satisfied and not legacy_unresolved_comparison:
            allowed = [
                canonical_evidence_source_group(group) for group in detection_gate or ()
            ]
            raise ReturnValidationError(
                f"{pattern_id!r} cannot be evaluated from {evidence_source!r}; "
                f"catalog allows {confidence} source alternatives {allowed}"
            )
        _validate_comparison_evidence_sources_used(
            detection,
            label,
            entry,
            confidence,
            available_sources,
            return_schema_version,
        )
        _require_string(detection, "evidence")
        if return_schema_version in SOURCE_LOCATED_RETURN_SCHEMA_VERSIONS:
            _validate_evidence_citations(detection, label, entry)
        dimensions = detection.get("dimensions")
        if dimensions is not None:
            if (
                return_schema_version in SOURCE_LOCATED_RETURN_SCHEMA_VERSIONS
                and dimensions != list(entry.vault_dimensions)
            ):
                raise ReturnValidationError(
                    f"{label}.dimensions must exactly match the catalog-owned "
                    f"ordered value {list(entry.vault_dimensions)}"
                )
            if return_schema_version not in SOURCE_LOCATED_RETURN_SCHEMA_VERSIONS and (
                not isinstance(dimensions, list)
                or any(
                    isinstance(item, bool)
                    or not isinstance(item, int)
                    or item < 1
                    or item > 14
                    for item in dimensions
                )
            ):
                raise ReturnValidationError(
                    f"{label}.dimensions must be an array of integers from 1 through 14"
                )
    return value


def _complete_coverage_sets(
    observations: dict,
) -> tuple[set[str], set[frozenset[str]]]:
    complete_sources: set[str] = set()
    complete_comparison_groups: set[frozenset[str]] = set()
    inspection = observations.get("source_inspection")
    if not isinstance(inspection, list):
        return complete_sources, complete_comparison_groups
    for record in inspection:
        if (
            not isinstance(record, dict)
            or record.get("absence_capability_complete") is not True
        ):
            continue
        source = record.get("source")
        if source == "source_comparison":
            used = record.get("evidence_sources_used")
            if isinstance(used, list):
                complete_comparison_groups.add(frozenset(used))
        elif isinstance(source, str):
            complete_sources.add(source)
    return complete_sources, complete_comparison_groups


def _canonical_gate_complete(
    gate: EvidenceSourceGroups | None,
    complete_sources: set[str],
    complete_comparison_groups: set[frozenset[str]],
) -> bool:
    if gate is None:
        return False
    return any(
        (len(group) == 1 and next(iter(group)) in complete_sources)
        or (len(group) > 1 and group in complete_comparison_groups)
        for group in gate
    )


def _validate_canonical_v5_outcomes(
    observations: dict,
    catalog: PatternCatalog,
) -> list[dict]:
    """Validate the exhaustive engine-owned v5 outcome projection."""
    if observations.get("evidence_schema_version") != PATTERN_EVIDENCE_SCHEMA_VERSION:
        raise ReturnValidationError(
            "canonical return-schema v5 observations require evidence schema "
            f"{PATTERN_EVIDENCE_SCHEMA_VERSION}"
        )
    detections = []
    detected_ids_seen: set[str] = set()
    for lane, expected_type in (
        ("patterns_detected", "pattern"),
        ("antipatterns_detected", "antipattern"),
    ):
        raw_lane = observations.get(lane)
        if not isinstance(raw_lane, list):
            raise ReturnValidationError(f"canonical {lane} must be an array")
        for item in raw_lane:
            pattern_id = item.get("pattern_id") if isinstance(item, dict) else None
            if not isinstance(pattern_id, str):
                raise ReturnValidationError(
                    f"canonical {lane} contains unknown, unobservable, duplicate, "
                    "or polarity-swapped pattern ids"
                )
            entry = catalog.entries.get(pattern_id)
            if (
                entry is None
                or not entry.observable
                or entry.entry_type != expected_type
                or pattern_id in detected_ids_seen
            ):
                raise ReturnValidationError(
                    f"canonical {lane} contains unknown, unobservable, duplicate, "
                    "or polarity-swapped pattern ids"
                )
            detected_ids_seen.add(pattern_id)
        detections.extend(raw_lane)
    detected_ids = {
        item.get("pattern_id")
        for item in detections
        if isinstance(item, dict) and isinstance(item.get("pattern_id"), str)
    }
    raw_assessments = observations.get("applicability_assessments")
    if not isinstance(raw_assessments, list):
        raise ReturnValidationError(
            "canonical v5 observations require applicability_assessments"
        )
    assessments: dict[str, dict] = {}
    for index, item in enumerate(raw_assessments):
        if not isinstance(item, dict):
            raise ReturnValidationError(
                f"canonical applicability_assessments[{index}] must be an object"
            )
        pattern_id = item.get("pattern_id")
        if (
            not isinstance(pattern_id, str)
            or not pattern_id
            or pattern_id in assessments
        ):
            raise ReturnValidationError(
                "canonical applicability assessments require unique pattern ids"
            )
        if pattern_id in detected_ids:
            raise ReturnValidationError(
                f"{pattern_id!r} cannot be detected and applicability-assessed"
            )
        assessments[pattern_id] = item
    raw_not_evaluable = observations.get("not_evaluable")
    if not isinstance(raw_not_evaluable, list):
        raise ReturnValidationError("canonical not_evaluable must be an array")
    not_evaluable_ids: set[str] = set()
    for item in raw_not_evaluable:
        if isinstance(item, dict):
            pattern_id = item.get("pattern_id")
            if isinstance(pattern_id, str):
                not_evaluable_ids.add(pattern_id)
    if len(not_evaluable_ids) != len(raw_not_evaluable):
        raise ReturnValidationError(
            "canonical not_evaluable entries require unique pattern ids"
        )
    complete_sources, complete_comparison_groups = _complete_coverage_sets(observations)
    expected: dict[str, str] = {}
    for pattern_id, entry in sorted(catalog.entries.items()):
        if not entry.observable:
            continue
        if pattern_id in detected_ids:
            if pattern_id in not_evaluable_ids:
                raise ReturnValidationError(
                    f"{pattern_id!r} cannot be detected and not_evaluable"
                )
            expected[pattern_id] = "detected"
            continue
        assessment = assessments.get(pattern_id)
        if entry.applicability_evaluable_from is not None:
            applicability_complete = _canonical_gate_complete(
                entry.applicability_evaluable_from,
                complete_sources,
                complete_comparison_groups,
            )
            if applicability_complete and assessment is None:
                raise ReturnValidationError(
                    f"{pattern_id!r} is missing its mandatory applicability assessment"
                )
            if not applicability_complete and assessment is not None:
                raise ReturnValidationError(
                    f"{pattern_id!r} has an applicability assessment without "
                    "complete gate coverage"
                )
            if not applicability_complete:
                expected[pattern_id] = "not_evaluable"
                continue
            assert assessment is not None
            result = assessment.get("result")
            if result == "not_applicable":
                expected[pattern_id] = "not_applicable"
                continue
            if result != "applicable":
                raise ReturnValidationError(
                    f"{pattern_id!r} has invalid applicability result {result!r}"
                )
        elif assessment is not None:
            raise ReturnValidationError(
                f"{pattern_id!r} has no catalog applicability contract"
            )
        expected[pattern_id] = (
            "undetected"
            if _canonical_gate_complete(
                entry.absence_evaluable_from,
                complete_sources,
                complete_comparison_groups,
            )
            else "not_evaluable"
        )
    expected_not_evaluable = {
        pattern_id
        for pattern_id, outcome in expected.items()
        if outcome == "not_evaluable"
    }
    if not_evaluable_ids != expected_not_evaluable:
        raise ReturnValidationError(
            "canonical not_evaluable projection disagrees with exhaustive "
            f"outcomes; expected {sorted(expected_not_evaluable)}, got "
            f"{sorted(not_evaluable_ids)}"
        )
    raw_outcomes = observations.get("pattern_outcomes")
    if not isinstance(raw_outcomes, list):
        raise ReturnValidationError(
            "canonical v5 observations require exhaustive pattern_outcomes"
        )
    canonical_outcomes = [
        {"pattern_id": pattern_id, "outcome": expected[pattern_id]}
        for pattern_id in sorted(expected)
    ]
    if raw_outcomes != canonical_outcomes:
        raise ReturnValidationError(
            "canonical pattern_outcomes must contain exactly one sorted row per "
            "observable catalog entry and match detection/applicability/coverage "
            "precedence"
        )
    try:
        expected_identity = opportunity_coverage_identity(
            canonical_outcomes,
            pattern_catalog_fingerprint=catalog.fingerprint,
            pattern_scoring_schema_version=PATTERN_SCORING_SCHEMA_VERSION,
        )
    except PatternEvidenceError as exc:
        raise ReturnValidationError(
            f"canonical pattern outcomes cannot form an opportunity identity: {exc}"
        ) from exc
    if observations.get("opportunity_coverage_identity") != expected_identity:
        raise ReturnValidationError(
            "canonical opportunity_coverage_identity does not match the scoring "
            "schema, catalog, and exhaustive outcome ledger"
        )
    return canonical_outcomes


def assess_current_persisted_pattern_evidence_freshness(
    talk: Mapping[str, object],
    *,
    vault_root: str | Path,
    source_roots: Mapping[str, object] | None = None,
    catalog: PatternCatalog | None = None,
    video_evidence_assessment: VideoEvidenceAssessment | None = None,
) -> tuple[str, ...]:
    """Combine artifact freshness with active-catalog v5 projection replay."""
    reasons = set(
        assess_artifact_freshness(
            talk,
            vault_root=vault_root,
            source_roots=source_roots,
            video_evidence_assessment=video_evidence_assessment,
        )
    )
    observations = talk.get("pattern_observations")
    if (
        isinstance(observations, dict)
        and observations.get("evidence_schema_version")
        == PATTERN_EVIDENCE_SCHEMA_VERSION
    ):
        try:
            _validate_canonical_v5_outcomes(
                observations,
                catalog if catalog is not None else load_catalog(),
            )
        except ReturnValidationError:
            reasons.add("pattern_outcomes_catalog_projection_drift")
    return tuple(sorted(reasons))


def assess_scoring_generation(
    ret: dict, catalog: PatternCatalog
) -> ScoringGenerationAssessment:
    """Canonicalize detections and assess the current scoring-v5 contract.

    Older returns remain replayable under their exact historical semantics, but
    only a canonical v5 payload can establish exhaustive opportunity outcomes.
    """
    version = resolve_return_schema_version(ret)
    observations = ret.get("pattern_observations")
    if not isinstance(observations, dict):
        return ScoringGenerationAssessment([], [], ())
    raw_available = observations.get("evidence_sources")
    available: set[str] = (
        {source for source in raw_available if isinstance(source, str)}
        if isinstance(raw_available, list)
        else set()
    )
    absence_available: set[str] = available
    inspected_comparison_groups: set[frozenset[str]] = set()
    complete_comparison_groups: set[frozenset[str]] = set()
    if version in SOURCE_LOCATED_RETURN_SCHEMA_VERSIONS:
        inspection = observations.get("source_inspection")
        absence_available = (
            {
                str(item["source"])
                for item in inspection
                if isinstance(item, dict)
                and item.get("absence_capability_complete") is True
                and isinstance(item.get("source"), str)
            }
            if isinstance(inspection, list)
            else set()
        )
        if isinstance(inspection, list):
            for item in inspection:
                if (
                    isinstance(item, dict)
                    and item.get("source") == "source_comparison"
                    and isinstance(item.get("evidence_sources_used"), list)
                ):
                    group = frozenset(item["evidence_sources_used"])
                    inspected_comparison_groups.add(group)
                    if item.get("absence_capability_complete") is True:
                        complete_comparison_groups.add(group)
    normalized_lanes: list[list[dict]] = []
    reasons: set[str] = set()
    if version < SOURCE_LOCATED_RETURN_SCHEMA_VERSION:
        reasons.add("return_schema_precedes_source_locations")
    elif version == SOURCE_LOCATED_RETURN_SCHEMA_VERSION:
        reasons.add("return_schema_precedes_exhaustive_outcomes")
    elif observations.get("evidence_schema_version") != PATTERN_EVIDENCE_SCHEMA_VERSION:
        reasons.add("canonical_outcomes_unresolved")
    detected_ids: set[str] = set()
    for field in ("patterns_detected", "antipatterns_detected"):
        normalized = []
        raw_detections = observations.get(field)
        detections = raw_detections if isinstance(raw_detections, list) else []
        for detection in detections:
            item = copy.deepcopy(detection)
            pattern_id = item.get("pattern_id")
            if isinstance(pattern_id, str):
                detected_ids.add(pattern_id)
            entry = catalog.entries.get(pattern_id)
            confidence = item.get("confidence")
            comparison_group = None
            if item.get("evidence_source") == "source_comparison":
                groups = (
                    qualifying_comparison_groups(
                        entry,
                        confidence,
                        available,
                        current_contract=True,
                    )
                    if entry is not None and isinstance(confidence, str)
                    else ()
                )
                if "evidence_sources_used" in item:
                    supplied = frozenset(item.get("evidence_sources_used") or [])
                    matched = next(
                        (group for group in groups if group == supplied), None
                    )
                    if matched is None:
                        # validate_return owns the user-facing failure; keep this
                        # helper fail-closed for direct persistence callers.
                        reasons.add(f"comparison_group_unresolved:{pattern_id}")
                    else:
                        comparison_group = matched
                        item["evidence_sources_used"] = canonical_evidence_source_group(
                            matched
                        )
                        if (
                            version in SOURCE_LOCATED_RETURN_SCHEMA_VERSIONS
                            and matched not in inspected_comparison_groups
                        ):
                            reasons.add(f"comparison_group_uninspected:{pattern_id}")
                elif version in OUTCOME_GATE_RETURN_SCHEMA_VERSIONS:
                    # A current return without explicit comparison proof is
                    # invalid; validation provides the precise diagnostic.
                    reasons.add(f"comparison_group_unresolved:{pattern_id}")
                elif len(groups) == 1:
                    comparison_group = groups[0]
                    item["evidence_sources_used"] = canonical_evidence_source_group(
                        groups[0]
                    )
                elif not groups:
                    reasons.add(f"comparison_group_unresolved:{pattern_id}")
                else:
                    reasons.add(f"comparison_group_ambiguous:{pattern_id}")
            if (
                entry is not None
                and confidence == "strong"
                and entry.strong_evaluable_from is not None
            ):
                if item.get("evidence_source") == "source_comparison":
                    strong_groups = qualifying_comparison_groups(
                        entry, confidence, available
                    )
                    strong_satisfied = comparison_group in strong_groups
                else:
                    strong_satisfied = evidence_source_satisfies_gate(
                        entry.strong_evaluable_from,
                        item.get("evidence_source"),
                        available,
                    )
                if not strong_satisfied:
                    reasons.add(f"strong_gate_unsatisfied:{pattern_id}")
            if entry is not None and version in SOURCE_LOCATED_RETURN_SCHEMA_VERSIONS:
                item["dimensions"] = list(entry.vault_dimensions)
            normalized.append(item)
        normalized_lanes.append(normalized)

    if (
        version == RETURN_SCHEMA_VERSION
        and observations.get("evidence_schema_version")
        == PATTERN_EVIDENCE_SCHEMA_VERSION
    ):
        _validate_canonical_v5_outcomes(observations, catalog)

    raw_not_evaluable = observations.get("not_evaluable")
    not_evaluable_ids = (
        {
            item.get("pattern_id")
            for item in raw_not_evaluable
            if isinstance(item, dict) and isinstance(item.get("pattern_id"), str)
        }
        if isinstance(raw_not_evaluable, list)
        else set()
    )
    for pattern_id, entry in catalog.entries.items():
        if version == RETURN_SCHEMA_VERSION:
            # Exhaustive v5 outcome validation above owns applicability and
            # absence precedence. Reapplying the v4 absence-only projection
            # would misclassify catalog-authorized not-applicable outcomes.
            continue
        absence_gate = entry.absence_evaluable_from
        if not entry.observable or pattern_id in detected_ids:
            continue
        if absence_gate is None:
            if (
                version in SOURCE_LOCATED_RETURN_SCHEMA_VERSIONS
                and pattern_id not in not_evaluable_ids
            ):
                reasons.add(f"source_gate_pending_owner_review:{pattern_id}")
            continue
        if version in SOURCE_LOCATED_RETURN_SCHEMA_VERSIONS:
            absence_satisfied = any(
                (len(group) == 1 and next(iter(group)) in absence_available)
                or (len(group) > 1 and group in complete_comparison_groups)
                for group in absence_gate
            )
        else:
            absence_satisfied = bool(
                qualifying_evidence_groups(absence_gate, absence_available)
            )
        if pattern_id not in not_evaluable_ids and not absence_satisfied:
            reasons.add(f"absence_gate_unsatisfied:{pattern_id}")

    return ScoringGenerationAssessment(
        normalized_lanes[0],
        normalized_lanes[1],
        tuple(sorted(reasons)),
    )


def canonical_persisted_pattern_observations(
    ret: dict,
    catalog: PatternCatalog,
    assessment: ScoringGenerationAssessment | None = None,
) -> dict:
    """Return the receipt-bound normalized pattern block stored by ingress."""
    resolved = assessment or assess_scoring_generation(ret, catalog)
    observations = ret.get("pattern_observations")
    if not isinstance(observations, dict):
        raise ReturnValidationError(
            "pattern_observations is required and must be an object"
        )
    raw_score = observations.get("pattern_score")
    score = raw_score.get("score") if isinstance(raw_score, dict) else raw_score
    raw_not_evaluable = observations.get("not_evaluable")
    not_evaluable = (
        copy.deepcopy(raw_not_evaluable) if isinstance(raw_not_evaluable, list) else []
    )
    evidence_sources = copy.deepcopy(observations.get("evidence_sources"))
    return_version = resolve_return_schema_version(ret)
    patterns_detected = copy.deepcopy(resolved.patterns_detected)
    antipatterns_detected = copy.deepcopy(resolved.antipatterns_detected)
    if return_version not in SOURCE_LOCATED_RETURN_SCHEMA_VERSIONS:
        for detection in patterns_detected + antipatterns_detected:
            detection["evidence_citations"] = []
    persisted = {
        "patterns_detected": patterns_detected,
        "pattern_ids": [item["pattern_id"] for item in patterns_detected],
        "antipatterns_detected": antipatterns_detected,
        "antipattern_ids": [item["pattern_id"] for item in antipatterns_detected],
        "not_evaluable": not_evaluable,
        "not_evaluable_ids": [item["pattern_id"] for item in not_evaluable],
        "evidence_sources": evidence_sources,
        "pattern_score": score,
    }
    if return_version in SOURCE_LOCATED_RETURN_SCHEMA_VERSIONS:
        persisted["evidence_schema_version"] = (
            PATTERN_EVIDENCE_SCHEMA_VERSION
            if return_version == RETURN_SCHEMA_VERSION
            else LEGACY_PATTERN_EVIDENCE_SCHEMA_VERSION
        )
        persisted["source_inspection"] = copy.deepcopy(
            observations.get("source_inspection")
        )
    if return_version == RETURN_SCHEMA_VERSION:
        _validate_canonical_v5_outcomes(observations, catalog)
        persisted["applicability_assessments"] = copy.deepcopy(
            observations.get("applicability_assessments")
        )
        persisted["pattern_outcomes"] = copy.deepcopy(
            observations.get("pattern_outcomes")
        )
        persisted["opportunity_coverage_identity"] = observations.get(
            "opportunity_coverage_identity"
        )
    return persisted


def _validate_available_sources(
    observations: dict,
    slide_source: str,
    transcript_source: str | None,
    *,
    video_static_slides_available=False,
) -> set[str]:
    sources = observations.get("evidence_sources")
    if (
        not isinstance(sources, list)
        or not sources
        or any(source not in EVIDENCE_SOURCES for source in sources)
    ):
        raise ReturnValidationError(
            "pattern_observations.evidence_sources is required and must be a "
            f"non-empty array drawn from {sorted(EVIDENCE_SOURCES)}"
        )
    if len(sources) != len(set(sources)):
        raise ReturnValidationError(
            "pattern_observations.evidence_sources contains duplicates"
        )
    available = set(sources)
    if transcript_source == "none" and "transcript" in available:
        raise ReturnValidationError(
            "evidence_sources includes transcript but transcript_source is none"
        )
    if slide_source == "none" and available.intersection(
        {"static_slides", "native_deck"}
    ):
        raise ReturnValidationError(
            "slide_source none cannot support static/native slide evidence_sources"
        )
    if (
        slide_source == "video_extracted"
        and "static_slides" in available
        and not video_static_slides_available
    ):
        raise ReturnValidationError(
            "evidence_sources includes static_slides, but the video extraction has "
            "no trusted schema-v3 slide_region artifact"
        )
    if slide_source not in {"pptx", "both"} and "native_deck" in available:
        raise ReturnValidationError(
            f"evidence_sources includes native_deck but slide_source is {slide_source!r}"
        )
    if "source_comparison" in available:
        underlying = available - {"source_comparison"}
        visual = underlying.intersection(
            {"static_slides", "native_deck", "delivery_video"}
        )
        if len(underlying) < 2 or not visual:
            raise ReturnValidationError(
                "source_comparison requires at least two underlying sources, "
                "including at least one visual source, in "
                "pattern_observations.evidence_sources"
            )
    return available


def _validate_source_inspection(
    observations: dict,
    available_sources: set[str],
    return_schema_version: int,
) -> None:
    """Validate worker-authored coverage claims before artifact resolution."""
    inspection = observations.get("source_inspection")
    if return_schema_version not in SOURCE_LOCATED_RETURN_SCHEMA_VERSIONS:
        if inspection is not None:
            raise ReturnValidationError(
                "source_inspection is supported only by return schemas v4/v5"
            )
        return
    if not isinstance(inspection, list) or not inspection:
        raise ReturnValidationError(
            "current pattern observations require non-empty source_inspection"
        )
    seen: set[str] = set()
    seen_comparison_groups: set[frozenset[str]] = set()
    for index, item in enumerate(inspection):
        label = f"pattern_observations.source_inspection[{index}]"
        if not isinstance(item, dict):
            raise ReturnValidationError(f"{label} must be an object")
        source = item.get("source")
        fields = SOURCE_INSPECTION_RAW_FIELDS.get(str(source))
        if fields is None:
            raise ReturnValidationError(
                f"{label}.source must be one of {sorted(SOURCE_INSPECTION_RAW_FIELDS)}"
            )
        if source != "source_comparison" and source in seen:
            raise ReturnValidationError(
                f"source_inspection contains duplicate source {source!r}"
            )
        seen.add(cast(str, source))
        unknown = sorted(set(item) - fields)
        missing = sorted(fields - set(item))
        if unknown or missing:
            raise ReturnValidationError(
                f"{label} must contain exactly {sorted(fields)}; "
                f"missing={missing}, unknown={unknown}"
            )
        if source == "source_comparison":
            used = item.get("evidence_sources_used")
            if (
                not isinstance(used, list)
                or len(used) < 2
                or any(
                    candidate not in EVIDENCE_SOURCES
                    or candidate == "source_comparison"
                    for candidate in used
                )
                or len(used) != len(set(used))
                or not set(used).intersection(
                    {"static_slides", "native_deck", "delivery_video"}
                )
            ):
                raise ReturnValidationError(
                    f"{label}.evidence_sources_used must contain at least two "
                    "duplicate-free underlying sources including a visual source"
                )
            if not set(used).issubset(available_sources):
                raise ReturnValidationError(
                    f"{label}.evidence_sources_used must be listed as inspected "
                    "underlying evidence_sources"
                )
            comparison_group = frozenset(used)
            if comparison_group in seen_comparison_groups:
                raise ReturnValidationError(
                    f"source_inspection contains duplicate comparison group "
                    f"{sorted(comparison_group)}"
                )
            seen_comparison_groups.add(comparison_group)
            if item.get("comparison_scope") not in {"full", "partial"}:
                raise ReturnValidationError(
                    f"{label}.comparison_scope must be 'full' or 'partial'"
                )
            continue
        range_field = {
            "transcript": "line_ranges",
            "static_slides": "page_ranges",
            "native_deck": "page_ranges",
            "delivery_video": "time_ranges",
        }[cast(str, source)]
        ranges = item.get(range_field)
        if not isinstance(ranges, list) or not ranges:
            raise ReturnValidationError(
                f"{label}.{range_field} must be a non-empty array"
            )
        prior_end: float | int | None = None
        for range_index, raw_range in enumerate(ranges):
            range_label = f"{label}.{range_field}[{range_index}]"
            if not isinstance(raw_range, list) or len(raw_range) != 2:
                raise ReturnValidationError(
                    f"{range_label} must be a two-item [start, end] array"
                )
            start, end = raw_range
            if source == "delivery_video":
                valid_numbers = all(
                    not isinstance(value, bool)
                    and isinstance(value, (int, float))
                    and math.isfinite(float(value))
                    for value in raw_range
                )
                minimum = 0
            else:
                valid_numbers = all(
                    not isinstance(value, bool) and isinstance(value, int)
                    for value in raw_range
                )
                minimum = 1
            if (
                not valid_numbers
                or start < minimum
                or end < start
                or (source == "delivery_video" and end <= start)
                or (prior_end is not None and start <= prior_end)
            ):
                raise ReturnValidationError(
                    f"{range_label} must be ascending, non-overlapping, and "
                    f"start at or above {minimum}"
                )
            prior_end = end
    if seen != available_sources:
        raise ReturnValidationError(
            "source_inspection sources must exactly match evidence_sources; "
            f"inspection={sorted(seen)}, evidence_sources={sorted(available_sources)}"
        )


def _validate_not_evaluable(
    observations: dict,
    catalog: PatternCatalog,
    available_sources: set[str],
    return_schema_version: int,
) -> list[dict]:
    entries = observations.get("not_evaluable")
    if not isinstance(entries, list):
        raise ReturnValidationError(
            "pattern_observations.not_evaluable is required and must be an array"
        )
    seen = set()
    for index, item in enumerate(entries):
        label = f"pattern_observations.not_evaluable[{index}]"
        if not isinstance(item, dict):
            raise ReturnValidationError(f"{label} must be an object")
        pattern_id = _require_string(item, "pattern_id")
        if pattern_id in seen:
            raise ReturnValidationError(
                f"not_evaluable contains duplicate id {pattern_id!r}"
            )
        seen.add(pattern_id)
        entry = catalog.entries.get(pattern_id)
        if entry is None:
            raise ReturnValidationError(
                f"{label}.pattern_id {pattern_id!r} is not in the catalog"
            )
        if (
            entry.evaluable_from is None
            and return_schema_version not in SOURCE_LOCATED_RETURN_SCHEMA_VERSIONS
        ):
            raise ReturnValidationError(
                f"{pattern_id!r} has no source-aware evidence gate and cannot be "
                "classified as not_evaluable"
            )
        if return_schema_version in SOURCE_LOCATED_RETURN_SCHEMA_VERSIONS:
            expected_fields = {"pattern_id", "reason_code"}
            if set(item) != expected_fields:
                raise ReturnValidationError(
                    f"{label} must contain exactly {sorted(expected_fields)}; "
                    "free-prose waivers are not scoring authority"
                )
            expected_reasons = {
                (
                    POSITIVE_ONLY_ABSENCE_REASON_CODE
                    if entry.evaluable_from is not None
                    else SOURCE_GATE_PENDING_REASON_CODE
                )
                if entry.absence_evaluable_from is None
                else SOURCE_INSPECTION_REASON_CODE
            }
            if (
                return_schema_version == RETURN_SCHEMA_VERSION
                and entry.applicability_evaluable_from is not None
            ):
                expected_reasons.add(APPLICABILITY_INSPECTION_REASON_CODE)
            if item.get("reason_code") not in expected_reasons:
                raise ReturnValidationError(
                    f"{label}.reason_code must be one of {sorted(expected_reasons)!r}"
                )
        else:
            source = item.get("evidence_source")
            if source not in EVIDENCE_SOURCES:
                raise ReturnValidationError(
                    f"{label}.evidence_source must be one of {sorted(EVIDENCE_SOURCES)}"
                )
            if source not in available_sources:
                raise ReturnValidationError(
                    f"{label}.evidence_source {source!r} is not listed in "
                    "evidence_sources"
                )
            _require_string(item, "reason")
    return entries


def _validate_unavailable_catalog_gates(
    catalog: PatternCatalog,
    available_sources: set[str],
    not_evaluable: list[dict],
    detected_ids: set[str],
    return_schema_version: int,
) -> None:
    """Require an explicit outcome when absence cannot be established.

    A valid positive detection is authoritative and suppresses the otherwise
    contradictory absence requirement. Undetected entries use their effective
    absence gate, which defaults to the base evaluable_from contract.
    """
    if return_schema_version in SOURCE_LOCATED_RETURN_SCHEMA_VERSIONS:
        # Complete coverage is artifact-derived later by
        # canonicalize_return_evidence. That pass computes the exact required
        # IDs and rejects both missing and blanket model-authored waivers.
        return
    recorded = {item["pattern_id"] for item in not_evaluable}
    required = set()
    for pattern_id, entry in catalog.entries.items():
        gate = (
            entry.absence_evaluable_from
            if return_schema_version in OUTCOME_GATE_RETURN_SCHEMA_VERSIONS
            else entry.evaluable_from
        )
        if (
            entry.observable
            and gate is not None
            and pattern_id not in detected_ids
            and not qualifying_evidence_groups(gate, available_sources)
        ):
            required.add(pattern_id)
    missing = sorted(required - recorded)
    if missing:
        raise ReturnValidationError(
            "source-gated catalog entries without a qualifying inspected source "
            f"must be marked not_evaluable: {missing}"
        )


def weighted_detection_total(detections: list[dict]) -> float:
    """Sum one polarity's detections under the owner-approved weight table."""
    return sum(DETECTION_WEIGHTS[detection["confidence"]] for detection in detections)


def pattern_score_basis(
    patterns: list[dict], antipatterns: list[dict], not_evaluable: list[dict]
) -> dict:
    """The evidence composition that travels with every emitted score.

    A single weighted number cannot say whether it came from two strong
    detections or four moderate ones, and it cannot say how much of the catalog
    was unevaluable for this talk. Without that, a score drop reads as a
    regression when it may only be thinner evidence. The basis is what makes the
    number honest, so it is required rather than optional.
    """
    counts: dict[str, dict[str, int]] = {}
    for lane, detections in (("patterns", patterns), ("antipatterns", antipatterns)):
        lane_counts = {level: 0 for level in sorted(DETECTION_WEIGHTS)}
        for detection in detections:
            lane_counts[detection["confidence"]] += 1
        counts[lane] = lane_counts
    return {
        "schema_version": WEIGHTED_PATTERN_SCORING_SCHEMA_VERSION,
        "weights": dict(sorted(DETECTION_WEIGHTS.items())),
        "patterns": counts["patterns"],
        "antipatterns": counts["antipatterns"],
        "not_evaluable_count": len(not_evaluable),
    }


def expected_weighted_score(patterns: list[dict], antipatterns: list[dict]) -> float:
    """The aggregate the detection arrays require, rounded deterministically.

    Weights are eighths at worst, so two decimal places represent every
    reachable value exactly; rounding here keeps a float sum from emitting
    0.30000000000000004 and failing an equality check that is logically true.
    """
    total = weighted_detection_total(patterns) - weighted_detection_total(antipatterns)
    return round(total, 2)


def _require_score_basis(observations: dict, wanted: dict) -> None:
    """Every weighted score carries its basis, bare number or score object.

    The requirement is on the SCORE, not on the shape it was written in. Gating
    it inside the score-object branch would let a return emit a bare weighted
    number with no record of the evidence behind it — precisely the
    unaccompanied number the basis exists to prevent.
    """
    basis = observations.get("pattern_score_basis")
    if basis is None:
        raise ReturnValidationError(
            "pattern_observations.pattern_score_basis is required alongside a "
            "weighted score; a bare number cannot say what evidence produced it"
        )
    if basis != wanted:
        raise ReturnValidationError(
            f"pattern_score_basis {basis} does not match the detection arrays {wanted}"
        )


def _validate_flat_score(
    raw: object, pattern_count: int, antipattern_count: int
) -> None:
    """The pre-v6 contract: every detection counts one, whatever its confidence."""
    expected = pattern_count - antipattern_count
    if isinstance(raw, bool):
        raise ReturnValidationError(
            "pattern_observations.pattern_score cannot be a boolean"
        )
    if isinstance(raw, int):
        if raw != expected:
            raise ReturnValidationError(
                f"pattern_score is {raw}, but {pattern_count} patterns minus "
                f"{antipattern_count} antipatterns is {expected}"
            )
        return
    if not isinstance(raw, dict):
        raise ReturnValidationError(
            "pattern_observations.pattern_score must be an integer or the "
            "declared score object"
        )
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
                f"pattern_score.{field} is {value}, but the detection arrays "
                f"require {wanted}"
            )


def _validate_score(
    observations: dict,
    patterns: list[dict],
    antipatterns: list[dict],
    not_evaluable: list[dict],
    return_schema_version: int,
) -> None:
    """Validate the aggregate against the contract its schema was produced under.

    Weighted scoring is a v6 contract, not a reinterpretation of v5. A v5 return
    was PRODUCED by a worker counting +1/-1, so rescoring it under the weight
    table would not validate that return — it would silently restate what the
    worker meant, which is the reinterpretation `stateful-artifacts` forbids.
    Each schema is checked against the arithmetic in force when it was written.
    """
    if "pattern_score" not in observations:
        raise ReturnValidationError("pattern_observations.pattern_score is required")
    raw = observations["pattern_score"]
    if return_schema_version < WEIGHTED_SCORE_RETURN_SCHEMA_VERSION:
        _validate_flat_score(raw, len(patterns), len(antipatterns))
        if "pattern_score_basis" in observations:
            raise ReturnValidationError(
                "pattern_score_basis is a v"
                f"{WEIGHTED_SCORE_RETURN_SCHEMA_VERSION} field; a v"
                f"{return_schema_version} return cannot carry one"
            )
        return
    expected = expected_weighted_score(patterns, antipatterns)
    if isinstance(raw, bool):
        raise ReturnValidationError(
            "pattern_observations.pattern_score cannot be a boolean"
        )
    wanted_basis = pattern_score_basis(patterns, antipatterns, not_evaluable)
    if isinstance(raw, (int, float)):
        if round(float(raw), 2) != expected:
            raise ReturnValidationError(
                f"pattern_score is {raw}, but the weighted detection arrays "
                f"require {expected} (weights {dict(sorted(DETECTION_WEIGHTS.items()))})"
            )
        _require_score_basis(observations, wanted_basis)
        return
    if not isinstance(raw, dict):
        raise ReturnValidationError(
            "pattern_observations.pattern_score must be a number or the declared score object"
        )

    required: dict[str, float] = {
        "patterns_used": float(len(patterns)),
        "antipatterns_detected": float(len(antipatterns)),
        "score": expected,
    }
    for field, wanted in required.items():
        value = raw.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ReturnValidationError(f"pattern_score.{field} must be a number")
        if round(float(value), 2) != wanted:
            raise ReturnValidationError(
                f"pattern_score.{field} is {value}, but the detection arrays require {wanted}"
            )
    _require_score_basis(observations, wanted_basis)


def resolved_return_pattern_score(observations: dict) -> float:
    """Return the already-validated weighted score from one observation block."""
    raw = observations["pattern_score"]
    if isinstance(raw, dict):
        return float(raw["score"])
    return float(raw)


def _validate_adherence_comparison(
    ret: dict, return_schema_version: int, talk_pattern_score: float
) -> None:
    """Validate the standalone half of the claim-bound adherence contract."""
    comparison = ret.get("adherence_comparison")
    assessment = ret.get("adherence_assessment")
    if return_schema_version not in OUTCOME_GATE_RETURN_SCHEMA_VERSIONS:
        if "adherence_comparison" in ret:
            raise ReturnValidationError(
                "adherence_comparison is supported only by return schemas v3/v4/v5"
            )
        return
    if comparison is None:
        if assessment != "":
            raise ReturnValidationError(
                f"return-schema v{return_schema_version} without "
                "adherence_comparison must use the "
                "exact empty adherence_assessment sentinel"
            )
        return
    if not isinstance(comparison, dict):
        raise ReturnValidationError(
            "adherence_comparison must be an object when present"
        )
    _validate_exact_fields(
        comparison,
        ADHERENCE_COMPARISON_FIELDS,
        "adherence_comparison",
    )
    comparison_version = comparison.get("schema_version")
    if (
        isinstance(comparison_version, bool)
        or not isinstance(comparison_version, int)
        or comparison_version != ADHERENCE_COMPARISON_SCHEMA_VERSION
    ):
        raise ReturnValidationError(
            "adherence_comparison.schema_version must be "
            f"the integer {ADHERENCE_COMPARISON_SCHEMA_VERSION}"
        )
    try:
        baseline = validate_adherence_baseline(comparison.get("baseline"))
    except AdherenceBaselineError as exc:
        raise ReturnValidationError(
            f"adherence_comparison.baseline is invalid: {exc}"
        ) from exc
    baseline_count = cast(int, baseline["scored_talk_count"])
    if baseline_count < MIN_ADHERENCE_BASELINE_TALKS:
        raise ReturnValidationError(
            "adherence_comparison is forbidden below the minimum baseline "
            f"population of {MIN_ADHERENCE_BASELINE_TALKS} talks"
        )
    comparison_score = comparison.get("talk_pattern_score")
    if (
        isinstance(comparison_score, bool)
        or not isinstance(comparison_score, int)
        or comparison_score != talk_pattern_score
    ):
        raise ReturnValidationError(
            "adherence_comparison.talk_pattern_score must be an integer equal "
            "to the validated "
            f"pattern_observations.pattern_score {talk_pattern_score}"
        )
    if not isinstance(assessment, str) or not assessment.strip():
        raise ReturnValidationError(
            "return-schema v3 with an eligible adherence baseline requires a "
            "substantive adherence_assessment"
        )
    assessment_text = assessment.strip()
    endings = list(_ADHERENCE_SENTENCE_TERMINATOR.finditer(assessment_text))
    sentence_count = len(endings)
    # Deliberately mechanical: every .?! cluster followed by whitespace/end is
    # a boundary, including abbreviation periods. Authors should spell out an
    # abbreviation that would otherwise create a false boundary. The final
    # sentence must carry terminal punctuation.
    if (
        sentence_count not in range(2, 5)
        or not endings
        or endings[-1].end() != len(assessment_text)
    ):
        raise ReturnValidationError(
            "adherence_assessment must contain exactly 2-4 punctuation-"
            "terminated sentences; periods in abbreviations count as sentence "
            "boundaries"
        )


def validate_v5_adherence_opportunity(
    talk: dict,
    ret: dict,
    canonical_ret: dict,
) -> None:
    """Bind a v5 raw-score comparison to one exact opportunity denominator."""
    if resolve_return_schema_version(ret) != RETURN_SCHEMA_VERSION:
        return
    if ret.get("status") not in ANALYSIS_STATUSES:
        return
    claim = talk.get("_queue_claim")
    if not isinstance(claim, dict):
        raise ReturnValidationError(
            f"{ret.get('filename', '<unknown>')} has no queue claim carrying "
            "the immutable adherence baseline"
        )
    try:
        baseline = validate_adherence_baseline(claim.get("adherence_baseline"))
    except AdherenceBaselineError as exc:
        raise ReturnValidationError(
            f"{ret.get('filename', '<unknown>')} queue-claim adherence baseline "
            f"is invalid: {exc}"
        ) from exc
    observations = canonical_ret.get("pattern_observations")
    if not isinstance(observations, dict):
        raise ReturnValidationError("canonical v5 return has no pattern observations")
    identity = observations.get("opportunity_coverage_identity")
    baseline_identity = baseline.get("opportunity_coverage_identity")
    baseline_count = cast(int, baseline["scored_talk_count"])
    comparable = (
        baseline_count >= MIN_ADHERENCE_BASELINE_TALKS
        and isinstance(identity, str)
        and identity == baseline_identity
    )
    comparison = ret.get("adherence_comparison")
    assessment = ret.get("adherence_assessment")
    if comparison is None and assessment == "":
        # The raw worker cannot author the engine-derived opportunity identity.
        # The exact empty sentinel is therefore always a safe v5 outcome; post-
        # batch/profile consumers may compare only already-canonical identities.
        return
    if comparable:
        if not isinstance(comparison, dict):
            raise ReturnValidationError(
                "v5 adherence prose requires a structured comparison"
            )
        if comparison.get("baseline") != baseline:
            raise ReturnValidationError(
                "adherence_comparison.baseline must exactly match the immutable "
                "queue-claim baseline"
            )
        if not isinstance(assessment, str) or not assessment.strip():
            raise ReturnValidationError(
                "a comparable v5 adherence result requires substantive "
                "adherence_assessment prose"
            )
        return
    if comparison is not None or assessment != "":
        reason = (
            "insufficient frozen baseline history"
            if baseline_count < MIN_ADHERENCE_BASELINE_TALKS
            else "opportunity coverage identity mismatch"
        )
        raise ReturnValidationError(
            "return-schema v5 raw-score adherence comparison is unavailable: "
            f"{reason}; omit adherence_comparison and use the exact empty "
            "adherence_assessment sentinel"
        )


def _validate_per_slide_visual(structured: dict) -> None:
    if "per_slide_visual" not in structured:
        return

    rows = structured["per_slide_visual"]
    if not isinstance(rows, list):
        raise ReturnValidationError("structured_data.per_slide_visual must be an array")

    slide_count = structured.get("slide_count")
    if (
        isinstance(slide_count, bool)
        or not isinstance(slide_count, int)
        or slide_count < 1
    ):
        raise ReturnValidationError(
            "structured_data.slide_count must be a positive integer when "
            "per_slide_visual is present"
        )
    if len(rows) != slide_count:
        raise ReturnValidationError(
            "structured_data.per_slide_visual must contain exactly "
            f"slide_count ({slide_count}) rows, got {len(rows)}"
        )

    for index, row in enumerate(rows, start=1):
        label = f"structured_data.per_slide_visual[{index - 1}]"
        if not isinstance(row, dict):
            raise ReturnValidationError(f"{label} must be an object")
        row_fields = set(row)
        if row_fields != PER_SLIDE_VISUAL_FIELDS:
            missing = sorted(PER_SLIDE_VISUAL_FIELDS - row_fields)
            unexpected = sorted(row_fields - PER_SLIDE_VISUAL_FIELDS, key=repr)
            details = []
            if missing:
                details.append(f"missing {missing}")
            if unexpected:
                details.append(f"unexpected {unexpected}")
            raise ReturnValidationError(
                f"{label} must contain exactly the canonical fields; "
                + "; ".join(details)
            )

        slide_number = row["slide_number"]
        if (
            isinstance(slide_number, bool)
            or not isinstance(slide_number, int)
            or slide_number != index
        ):
            raise ReturnValidationError(
                f"{label}.slide_number must be {index}; rows must uniquely and "
                "contiguously cover 1 through slide_count in order"
            )
        background = row["background_color_name"]
        if not isinstance(background, str) or not background.strip():
            raise ReturnValidationError(
                f"{label}.background_color_name must be a non-empty string"
            )
        content_type = row["content_type"]
        if (
            not isinstance(content_type, str)
            or content_type not in PER_SLIDE_CONTENT_TYPES
        ):
            raise ReturnValidationError(
                f"{label}.content_type must be one of "
                f"{sorted(PER_SLIDE_CONTENT_TYPES)}, got {content_type!r}"
            )
        image_composition = row["image_composition"]
        if (
            not isinstance(image_composition, str)
            or image_composition not in PER_SLIDE_IMAGE_COMPOSITIONS
        ):
            raise ReturnValidationError(
                f"{label}.image_composition must be one of "
                f"{sorted(PER_SLIDE_IMAGE_COMPOSITIONS)}, "
                f"got {image_composition!r}"
            )
        for field in PER_SLIDE_VISUAL_BOOLEAN_FIELDS:
            if not isinstance(row[field], bool):
                raise ReturnValidationError(f"{label}.{field} must be a boolean")

    background_sequence = structured.get("background_color_sequence")
    if background_sequence is not None:
        expected_backgrounds = [row["background_color_name"] for row in rows]
        if background_sequence != expected_backgrounds:
            raise ReturnValidationError(
                "structured_data.background_color_sequence must exactly match "
                "per_slide_visual background_color_name values in slide order"
            )

    if "meme_count" in structured:
        meme_count = structured["meme_count"]
        if (
            isinstance(meme_count, bool)
            or not isinstance(meme_count, int)
            or meme_count < 0
        ):
            raise ReturnValidationError(
                "structured_data.meme_count must be a non-negative integer"
            )
        expected_memes = sum(row["content_type"] in MEME_CONTENT_TYPES for row in rows)
        if meme_count != expected_memes:
            raise ReturnValidationError(
                f"structured_data.meme_count is {meme_count}, but "
                f"per_slide_visual contains {expected_memes} meme slides"
            )


def _validate_image_source_distribution(structured: dict) -> None:
    basis_field = "image_source_distribution_basis"
    if basis_field in structured:
        basis = structured[basis_field]
        if not isinstance(basis, str) or not basis.strip():
            raise ReturnValidationError(
                f"structured_data.{basis_field} must be a non-empty string"
            )

    if "image_source_distribution" not in structured:
        return
    distribution = structured["image_source_distribution"]
    if not isinstance(distribution, dict):
        raise ReturnValidationError(
            "structured_data.image_source_distribution must be an object "
            "mapping source labels to counts"
        )
    for source, count in distribution.items():
        if not isinstance(source, str) or not source.strip():
            raise ReturnValidationError(
                "structured_data.image_source_distribution keys must be "
                "non-empty source-label strings"
            )
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ReturnValidationError(
                "structured_data.image_source_distribution"
                f"[{source!r}] must be a non-negative integer count"
            )
    if basis_field not in structured:
        raise ReturnValidationError(
            f"structured_data.{basis_field} is required whenever "
            "image_source_distribution is present"
        )


def validate_structured_data(
    structured: dict, *, require_complete_groups: bool = False
) -> None:
    """Validate structured findings, optionally enforcing snapshot groups."""
    if "co_presenter" in structured and not isinstance(
        structured["co_presenter"], bool
    ):
        raise ReturnValidationError("structured_data.co_presenter must be a boolean")
    if "co_presenters" in structured:
        names = structured["co_presenters"]
        if not isinstance(names, list) or any(
            not isinstance(name, str) or not name.strip() for name in names
        ):
            raise ReturnValidationError(
                "structured_data.co_presenters must be an array of non-empty names"
            )
    if structured.get("co_presenter") is True and not structured.get("co_presenters"):
        raise ReturnValidationError(
            "structured_data.co_presenter is true, so co_presenters must name the speakers"
        )
    if (
        require_complete_groups
        and structured.get("co_presenter") is False
        and structured.get("co_presenters")
    ):
        raise ReturnValidationError(
            "snapshot return structured_data.co_presenter is false, so "
            "co_presenters must be empty or omitted"
        )
    language = structured.get("delivery_language")
    if language is not None and (
        not isinstance(language, str) or not LANGUAGE_RE.fullmatch(language)
    ):
        raise ReturnValidationError(
            "structured_data.delivery_language must be a lowercase language code "
            f"such as 'en' or 'pt-br', got {language!r}"
        )
    _validate_per_slide_visual(structured)
    _validate_image_source_distribution(structured)
    if require_complete_groups and ("image_source_distribution" in structured) != (
        "image_source_distribution_basis" in structured
    ):
        raise ReturnValidationError(
            "snapshot return requires structured_data.image_source_distribution "
            "and image_source_distribution_basis to be supplied together"
        )


def _native_deck_cited_slide_numbers(
    detections: list[dict],
) -> set[int]:
    """Return exact native-deck slides cited by validated detections."""
    cited: set[int] = set()
    for detection in detections:
        citations = detection.get("evidence_citations")
        if not isinstance(citations, list):
            continue
        for citation in citations:
            if not isinstance(citation, Mapping):
                continue
            if citation.get("source") != "native_deck":
                continue
            slide_numbers = citation.get("slide_numbers")
            if not isinstance(slide_numbers, list):
                continue
            cited.update(
                number
                for number in slide_numbers
                if isinstance(number, int) and not isinstance(number, bool)
            )
    return cited


def _native_deck_findings_present(
    structured: Mapping[str, object],
    detections: list[dict],
) -> bool:
    """Return whether a PPTX return carries audit-bound native findings."""
    if any(field in structured for field in PPTX_RENDER_DEPENDENT_FIELDS):
        return True
    return bool(_native_deck_cited_slide_numbers(detections))


def validate_native_deck_design_receipt(
    *,
    structured: dict,
    observations: dict,
    slide_source: str,
    detections: list[dict],
) -> None:
    """Require a current native audit and any claim-dependent render evidence."""
    raw_audit = structured.get("native_deck_audit")
    if raw_audit is not None and slide_source not in {"pptx", "both"}:
        raise ReturnValidationError(
            "structured_data.native_deck_audit requires slide_source pptx or both"
        )
    evidence_sources = observations.get("evidence_sources")
    source_inspection = observations.get("source_inspection")
    native_declared = (
        slide_source in {"pptx", "both"}
        or (isinstance(evidence_sources, list) and "native_deck" in evidence_sources)
        or (
            isinstance(source_inspection, list)
            and any(
                isinstance(item, Mapping) and item.get("source") == "native_deck"
                for item in source_inspection
            )
        )
        or bool(_native_deck_cited_slide_numbers(detections))
    )
    design_findings = native_declared and _native_deck_findings_present(
        structured, detections
    )
    if raw_audit is None:
        if native_declared:
            raise ReturnValidationError(
                "declared, inspected, or cited native-deck evidence requires the current "
                "structured_data.native_deck_audit from pptx-extraction.py"
            )
        return
    slide_count = structured.get("slide_count")
    expected_count = (
        slide_count
        if isinstance(slide_count, int) and not isinstance(slide_count, bool)
        else None
    )
    try:
        audit = validate_native_deck_audit(
            raw_audit,
            slide_count=expected_count,
        )
    except PptxEvidenceError as exc:
        raise ReturnValidationError(
            f"structured_data.native_deck_audit is invalid: {exc}"
        ) from exc
    if not design_findings or not audit["render_required_slide_numbers"]:
        return
    render_required = set(cast(list[int], audit["render_required_slide_numbers"]))
    structured_visual_findings = any(
        field in structured for field in PPTX_RENDER_DEPENDENT_FIELDS
    )
    cited_required = _native_deck_cited_slide_numbers(detections).intersection(
        render_required
    )
    pages_requiring_render = (
        render_required if structured_visual_findings else cited_required
    )
    if not pages_requiring_render:
        return
    receipt = audit["rendered_page_inspection"]
    if not isinstance(receipt, Mapping):
        raise ReturnValidationError(
            "render-required native-deck findings need an "
            "identity-bound rendered_page_inspection receipt"
        )
    inspected_required = receipt.get("inspected_required_slide_numbers")
    if (
        not isinstance(inspected_required, list)
        or not pages_requiring_render.issubset(set(inspected_required))
        or (structured_visual_findings and receipt.get("complete") is not True)
    ):
        raise ReturnValidationError(
            "identity-bound rendered_page_inspection does not cover every "
            "render-required slide used by the native-deck findings"
        )
    if (
        not isinstance(evidence_sources, list)
        or "static_slides" not in evidence_sources
    ):
        raise ReturnValidationError(
            "render-required native-deck design findings must list the exact "
            "rendered PDF as inspected static_slides evidence"
        )
    static_receipt = (
        next(
            (
                item
                for item in source_inspection
                if isinstance(item, Mapping) and item.get("source") == "static_slides"
            ),
            None,
        )
        if isinstance(source_inspection, list)
        else None
    )
    if static_receipt is None:
        raise ReturnValidationError(
            "render-required native-deck design findings need a static_slides "
            "source_inspection record"
        )
    try:
        audited_slide_count = cast(int, audit["slide_count"])
        covered = ranges_cover_pages(
            static_receipt.get("page_ranges"),
            sorted(pages_requiring_render),
            page_count=audited_slide_count,
        )
    except PptxEvidenceError as exc:
        raise ReturnValidationError(
            f"static_slides render inspection is invalid: {exc}"
        ) from exc
    if not covered:
        raise ReturnValidationError(
            "static_slides source_inspection must cover every render-required "
            "native-deck page"
        )


def validate_structured_policy_value(field, value, policy) -> None:
    """Validate one declared v2 field against its persistence policy shape."""
    if policy in {ATOMIC_MAP, ADDITIVE_MAP} and not isinstance(value, dict):
        raise ReturnValidationError(
            f"structured_data.{field} must be an object under its {policy} policy"
        )
    if policy in {REPLACE_LIST, ATOMIC_LIST} and not isinstance(value, list):
        raise ReturnValidationError(
            f"structured_data.{field} must be an array under its {policy} policy"
        )
    if policy == REPLACE_SCALAR and isinstance(value, (dict, list)):
        raise ReturnValidationError(
            f"structured_data.{field} must be a scalar under its {policy} policy"
        )


def validate_v2_structured_policy_shapes(structured: dict) -> None:
    """Apply the writer's v2 shape registry at standalone-return preflight."""
    for field, value in structured.items():
        policy = STRUCTURED_FIELD_POLICIES.get(field)
        if policy is None:
            if isinstance(value, dict):
                raise ReturnValidationError(
                    f"structured_data.{field} is an unregistered object; declare "
                    "an atomic policy or place additive data under "
                    "structured_data.extensions"
                )
            # Unregistered scalar/array fields replace atomically and cannot
            # preserve stale nested dictionary children.
            continue
        validate_structured_policy_value(field, value, policy)


def validate_verbatim_examples(verbatim: dict, *, reject_unknown: bool = False) -> None:
    """Validate declared verbatim snapshot lanes without requiring every lane."""
    if reject_unknown:
        unknown = sorted(set(verbatim) - VERBATIM_EXAMPLE_FIELDS)
        if unknown:
            raise ReturnValidationError(
                f"snapshot return has unknown verbatim_examples lanes: {unknown}"
            )
    for field in VERBATIM_EXAMPLE_FIELDS.intersection(verbatim):
        values = verbatim[field]
        if not isinstance(values, list) or any(
            not isinstance(value, str) for value in values
        ):
            raise ReturnValidationError(
                f"verbatim_examples.{field} must be an array of strings"
            )


def _require_persisted_analysis_mapping(talk: dict, field: str) -> dict:
    value = talk.get(field)
    if not isinstance(value, dict):
        filename = talk.get("filename", "<unknown>")
        raise ReturnValidationError(
            f"{filename} persisted {field} must be an object, got "
            f"{type(value).__name__}"
        )
    return value


def validate_persisted_v2_analysis_state(talk: dict) -> None:
    """Validate canonical effective analysis after v2/v3 persistence."""
    structured = _require_persisted_analysis_mapping(talk, "structured_data")
    verbatim = _require_persisted_analysis_mapping(talk, "verbatim_examples")
    observations = _require_persisted_analysis_mapping(talk, "pattern_observations")

    for field, policy in STRUCTURED_FIELD_POLICIES.items():
        if field in structured:
            validate_structured_policy_value(field, structured[field], policy)
    validate_structured_data(structured, require_complete_groups=True)
    validate_verbatim_examples(verbatim, reject_unknown=True)

    actual_fields = set(observations)
    allowed_fields = {
        frozenset(V5_PERSISTED_PATTERN_OBSERVATION_FIELDS),
        PERSISTED_PATTERN_OBSERVATION_FIELDS,
        LEGACY_PERSISTED_PATTERN_OBSERVATION_FIELDS,
    }
    if actual_fields not in allowed_fields:
        raise ReturnValidationError(
            "persisted pattern snapshot has noncanonical fields; expected the "
            f"v5 {sorted(V5_PERSISTED_PATTERN_OBSERVATION_FIELDS)}, source-located "
            f"v4 {sorted(PERSISTED_PATTERN_OBSERVATION_FIELDS)}, or legacy "
            f"{sorted(LEGACY_PERSISTED_PATTERN_OBSERVATION_FIELDS)}, got "
            f"{sorted(actual_fields)}"
        )
    evidence_schema_version = observations.get("evidence_schema_version")
    located_evidence = evidence_schema_version is not None
    if located_evidence and evidence_schema_version not in {
        LEGACY_PATTERN_EVIDENCE_SCHEMA_VERSION,
        PATTERN_EVIDENCE_SCHEMA_VERSION,
    }:
        raise ReturnValidationError(
            "persisted pattern snapshot evidence_schema_version must be one of "
            f"{[LEGACY_PATTERN_EVIDENCE_SCHEMA_VERSION, PATTERN_EVIDENCE_SCHEMA_VERSION]}"
        )
    if (
        evidence_schema_version == PATTERN_EVIDENCE_SCHEMA_VERSION
        and actual_fields != set(V5_PERSISTED_PATTERN_OBSERVATION_FIELDS)
    ):
        raise ReturnValidationError(
            "evidence-schema v2 persisted snapshots require exhaustive v5 fields"
        )
    if (
        evidence_schema_version == LEGACY_PATTERN_EVIDENCE_SCHEMA_VERSION
        and actual_fields != set(PERSISTED_PATTERN_OBSERVATION_FIELDS)
    ):
        raise ReturnValidationError(
            "evidence-schema v1 persisted snapshots must use the archival v4 shape"
        )
    for lane, ids_lane in (
        ("patterns_detected", "pattern_ids"),
        ("antipatterns_detected", "antipattern_ids"),
        ("not_evaluable", "not_evaluable_ids"),
    ):
        entries = observations[lane]
        ids = observations[ids_lane]
        if (
            not isinstance(entries, list)
            or any(not isinstance(entry, dict) for entry in entries)
            or not isinstance(ids, list)
        ):
            raise ReturnValidationError(
                f"persisted pattern snapshot {lane}/{ids_lane} has an "
                "invalid container shape"
            )
        expected_ids = [
            entry.get("pattern_id") for entry in entries if entry.get("pattern_id")
        ]
        if ids != expected_ids:
            raise ReturnValidationError(
                f"persisted pattern snapshot {ids_lane} does not match {lane}"
            )
        if lane in {"patterns_detected", "antipatterns_detected"}:
            for entry in entries:
                citations = entry.get("evidence_citations")
                if located_evidence and (
                    not isinstance(citations, list) or not citations
                ):
                    raise ReturnValidationError(
                        "source-located persisted detections require non-empty "
                        "evidence_citations"
                    )
                if not located_evidence and citations != []:
                    raise ReturnValidationError(
                        "legacy persisted detections must use the explicit empty "
                        "evidence_citations sentinel"
                    )
    evidence_sources = observations["evidence_sources"]
    if not isinstance(evidence_sources, list) or any(
        not isinstance(source, str) for source in evidence_sources
    ):
        raise ReturnValidationError(
            "persisted pattern snapshot evidence_sources must be an array of strings"
        )
    if located_evidence:
        inspection = observations.get("source_inspection")
        if (
            not isinstance(inspection, list)
            or not inspection
            or any(not isinstance(item, dict) for item in inspection)
        ):
            raise ReturnValidationError(
                "source-located persisted snapshots require non-empty canonical "
                "source_inspection"
            )
        inspected_sources = [item.get("source") for item in inspection]
        underlying_sources = [
            source for source in inspected_sources if source != "source_comparison"
        ]
        comparison_groups = [
            frozenset(item.get("evidence_sources_used") or [])
            for item in inspection
            if item.get("source") == "source_comparison"
        ]
        if (
            any(source not in EVIDENCE_SOURCES for source in inspected_sources)
            or len(underlying_sources) != len(set(underlying_sources))
            or len(comparison_groups) != len(set(comparison_groups))
            or any(len(group) < 2 for group in comparison_groups)
            or set(inspected_sources) != set(evidence_sources)
        ):
            raise ReturnValidationError(
                "persisted source_inspection sources must exactly match "
                "evidence_sources; underlying sources and comparison groups "
                "must be unique"
            )
    if evidence_schema_version == PATTERN_EVIDENCE_SCHEMA_VERSION:
        assessments = observations.get("applicability_assessments")
        if not isinstance(assessments, list):
            raise ReturnValidationError(
                "evidence-schema v2 applicability_assessments must be an array"
            )
        assessment_ids: set[str] = set()
        for item in assessments:
            if not isinstance(item, dict):
                raise ReturnValidationError(
                    "persisted applicability assessments must be objects"
                )
            pattern_id = item.get("pattern_id")
            citations = item.get("evidence_citations")
            if (
                not isinstance(pattern_id, str)
                or not pattern_id
                or pattern_id in assessment_ids
                or not isinstance(citations, list)
                or not citations
            ):
                raise ReturnValidationError(
                    "persisted applicability assessments require unique ids and "
                    "non-empty source-located citations"
                )
            assessment_ids.add(pattern_id)
        outcomes = observations.get("pattern_outcomes")
        if not isinstance(outcomes, list) or any(
            not isinstance(item, dict) or not isinstance(item.get("pattern_id"), str)
            for item in outcomes
        ):
            raise ReturnValidationError(
                "persisted pattern_outcomes must be an array of pattern objects"
            )
        typed_outcomes = cast(list[dict[str, object]], outcomes)
        try:
            expected_identity = opportunity_coverage_identity(
                typed_outcomes,
                pattern_catalog_fingerprint=talk.get("pattern_catalog_fingerprint"),
                pattern_scoring_schema_version=talk.get(
                    "pattern_scoring_schema_version"
                ),
            )
        except PatternEvidenceError as exc:
            raise ReturnValidationError(
                f"persisted pattern_outcomes are invalid: {exc}"
            ) from exc
        if typed_outcomes != sorted(
            typed_outcomes,
            key=lambda item: cast(str, item["pattern_id"]),
        ):
            raise ReturnValidationError(
                "persisted pattern_outcomes must use canonical pattern-id order"
            )
        if observations.get("opportunity_coverage_identity") != expected_identity:
            raise ReturnValidationError(
                "persisted opportunity_coverage_identity does not match its "
                "outcome ledger and generation"
            )
    score = observations["pattern_score"]
    if isinstance(score, bool) or not isinstance(score, int):
        raise ReturnValidationError(
            "persisted pattern snapshot pattern_score must be an integer"
        )
    if talk.get("pattern_score") != score:
        raise ReturnValidationError(
            "persisted pattern snapshot diverges from promoted pattern_score"
        )


def _validate_catalog_feedback(feedback) -> None:
    if not isinstance(feedback, dict):
        raise ReturnValidationError(
            "catalog_feedback is required and must be an object"
        )
    for field in CATALOG_FEEDBACK_LISTS:
        if field not in feedback:
            raise ReturnValidationError(f"catalog_feedback.{field} is required")
        if not isinstance(feedback[field], list):
            raise ReturnValidationError(f"catalog_feedback.{field} must be an array")


def _validate_clear_fields(value) -> None:
    if value is None:
        return
    if not isinstance(value, list) or any(
        not isinstance(path, str) or not path for path in value
    ):
        raise ReturnValidationError(
            "clear_fields must be an array of non-empty dotted paths"
        )
    if len(value) != len(set(value)):
        raise ReturnValidationError("clear_fields contains duplicate paths")
    scalar_roots = {
        "rhetoric_notes",
        "areas_for_improvement",
        "adherence_assessment",
        "transcript_source",
        "transcript_path",
        "slide_source",
        "slides_local_path",
    }
    nested_roots = {"structured_data", "verbatim_examples", "pattern_observations"}
    for path in value:
        parts = path.split(".")
        if any(not part for part in parts):
            raise ReturnValidationError(
                f"clear_fields path {path!r} has an empty segment"
            )
        if parts[0] in scalar_roots and len(parts) == 1:
            continue
        if parts[0] in nested_roots and len(parts) >= 2:
            continue
        raise ReturnValidationError(
            f"clear_fields path {path!r} is outside the analysis-owned allowlist"
        )


def _validate_processed_date(value) -> None:
    if value is None:
        return
    try:
        normalize_processing_stamp(value)
    except (TypeError, ValueError) as exc:
        raise ReturnValidationError(
            "processed_date must be YYYY-MM-DD or a timezone-aware ISO-8601 "
            f"timestamp: {exc}"
        ) from exc


def _validate_skipped_return_fields(ret: dict) -> None:
    disallowed = sorted(set(ret) - SKIPPED_RETURN_FIELDS)
    if disallowed:
        raise ReturnValidationError(
            "skipped terminal returns may only close the queue claim; they cannot "
            "mutate or clear prior analysis fields. Remove "
            f"{disallowed}"
        )


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
        + "; ".join(details)
    )


def _validate_queue_claim(
    value, *, expected_fields=RETURN_QUEUE_CLAIM_FIELDS, label="queue_claim"
) -> None:
    if not isinstance(value, dict):
        raise ReturnValidationError(
            "queue_claim is required and must copy run_id, batch_id, and "
            "reprocess_generation from the claimed talk"
        )
    _validate_exact_fields(value, expected_fields, label)
    for field in ("run_id", "batch_id"):
        item = value.get(field)
        if (
            not isinstance(item, str)
            or not item
            or item.strip() != item
            or any(char.isspace() for char in item)
        ):
            raise ReturnValidationError(
                f"{label}.{field} must be a non-empty token without whitespace"
            )
    generation = value.get("reprocess_generation")
    if (
        isinstance(generation, bool)
        or not isinstance(generation, int)
        or generation < 1
    ):
        raise ReturnValidationError(
            f"{label}.reprocess_generation must be a positive integer"
        )


def _nonempty_talk_string(talk: dict, field: str) -> bool:
    value = talk.get(field)
    return isinstance(value, str) and bool(value.strip())


def _validate_stored_claim(expected: dict, filename: str) -> None:
    state = expected.get("state")
    version = expected.get("schema_version")
    if (
        isinstance(version, bool)
        or not isinstance(version, int)
        or version
        not in {
            LEGACY_QUEUE_CLAIM_SCHEMA_VERSION,
            PREVIOUS_QUEUE_CLAIM_SCHEMA_VERSION,
            BASELINE_QUEUE_CLAIM_SCHEMA_VERSION,
            SOURCE_LOCATED_QUEUE_CLAIM_SCHEMA_VERSION,
            QUEUE_CLAIM_SCHEMA_VERSION,
        }
    ):
        supported_claim_versions = {
            LEGACY_QUEUE_CLAIM_SCHEMA_VERSION,
            PREVIOUS_QUEUE_CLAIM_SCHEMA_VERSION,
            BASELINE_QUEUE_CLAIM_SCHEMA_VERSION,
            SOURCE_LOCATED_QUEUE_CLAIM_SCHEMA_VERSION,
            QUEUE_CLAIM_SCHEMA_VERSION,
        }
        raise ReturnValidationError(
            f"{filename} queue claim schema_version must be "
            f"one of {sorted(supported_claim_versions)}, "
            f"got {version!r}"
        )
    if state == "claimed":
        expected_fields = (
            ACTIVE_QUEUE_CLAIM_FIELDS
            if version in BASELINE_BOUND_QUEUE_CLAIM_SCHEMA_VERSIONS
            else BASE_ACTIVE_QUEUE_CLAIM_FIELDS
        )
    elif version == LEGACY_QUEUE_CLAIM_SCHEMA_VERSION:
        expected_fields = LEGACY_COMPLETED_QUEUE_CLAIM_FIELDS
    elif version == PREVIOUS_QUEUE_CLAIM_SCHEMA_VERSION:
        expected_fields = PREVIOUS_COMPLETED_QUEUE_CLAIM_FIELDS
    else:
        expected_fields = COMPLETED_QUEUE_CLAIM_FIELDS
    label = f"{filename} queue claim"
    _validate_queue_claim(expected, expected_fields=expected_fields, label=label)
    claimed_at = expected.get("claimed_at")
    try:
        normalized_claimed_at = normalize_processing_stamp(claimed_at)
    except (TypeError, ValueError) as exc:
        raise ReturnValidationError(
            f"{filename} queue claim claimed_at must be timezone-aware: {exc}"
        ) from exc
    if len(normalized_claimed_at) == 10:
        raise ReturnValidationError(
            f"{filename} queue claim claimed_at must be a timezone-aware timestamp, "
            "not a bare date"
        )
    if version in BASELINE_BOUND_QUEUE_CLAIM_SCHEMA_VERSIONS:
        if expected.get("claimed_at") != normalized_claimed_at:
            raise ReturnValidationError(
                f"{filename} schema-v{version} queue claim claimed_at must use canonical "
                f"UTC whole-second form {normalized_claimed_at!r}"
            )
        required_return = expected.get("required_return_schema_version")
        expected_return = version
        if (
            isinstance(required_return, bool)
            or not isinstance(required_return, int)
            or required_return != expected_return
        ):
            raise ReturnValidationError(
                f"{filename} schema-v{version} queue claim must require return "
                f"schema version {expected_return}, got {required_return!r}"
            )
        try:
            baseline = validate_adherence_baseline(expected.get("adherence_baseline"))
        except AdherenceBaselineError as exc:
            raise ReturnValidationError(
                f"{filename} queue claim adherence_baseline is invalid: {exc}"
            ) from exc
        expected_baseline_schema = (
            ADHERENCE_BASELINE_SCHEMA_VERSION
            if version == QUEUE_CLAIM_SCHEMA_VERSION
            else LEGACY_ADHERENCE_BASELINE_SCHEMA_VERSION
        )
        if baseline.get("schema_version") != expected_baseline_schema:
            raise ReturnValidationError(
                f"{filename} schema-v{version} queue claim requires adherence "
                f"baseline schema {expected_baseline_schema}, got "
                f"{baseline.get('schema_version')!r}"
            )
        if baseline["as_of"] != normalized_claimed_at:
            raise ReturnValidationError(
                f"{filename} queue claim adherence_baseline.as_of must equal claimed_at"
            )
        if baseline["active_batch_excluded"] is not True:
            raise ReturnValidationError(
                f"{filename} schema-v{version} queue claim adherence_baseline must "
                "exclude the active batch"
            )
    previous = expected.get("previous_status")
    if previous not in CLAIMABLE_PREVIOUS_STATUSES:
        raise ReturnValidationError(
            f"{filename} queue claim previous_status {previous!r} is not claimable"
        )
    if state == "claimed":
        return
    try:
        normalized_released_at = normalize_processing_stamp(expected.get("released_at"))
    except (TypeError, ValueError) as exc:
        raise ReturnValidationError(
            f"{filename} completed queue claim released_at must be timezone-aware: {exc}"
        ) from exc
    if len(normalized_released_at) == 10:
        raise ReturnValidationError(
            f"{filename} completed queue claim released_at must be a timezone-aware "
            "timestamp, not a bare date"
        )
    if not _nonempty_talk_string(expected, "release_reason"):
        raise ReturnValidationError(
            f"{filename} completed queue claim must carry release_reason"
        )
    if expected.get("result_status") not in RETURN_STATUSES:
        raise ReturnValidationError(
            f"{filename} completed queue claim has invalid result_status "
            f"{expected.get('result_status')!r}"
        )
    if version in RECEIPT_QUEUE_CLAIM_SCHEMA_VERSIONS:
        receipt = expected.get("result_payload_sha256")
        if (
            not isinstance(receipt, str)
            or re.fullmatch(r"[0-9a-f]{64}", receipt) is None
        ):
            raise ReturnValidationError(
                f"{filename} completed queue claim result_payload_sha256 must be "
                "a lowercase 64-character SHA-256 receipt"
            )


def _validate_return_sources_against_talk(talk: dict, ret: dict) -> None:
    """Bind returned provenance/evidence to sources reachable from the talk."""
    transcript_source = ret.get("transcript_source")
    if "transcript_path" in ret:
        try:
            transcript_path = validate_transcript_path(ret["transcript_path"])
        except PatternEvidenceError as exc:
            raise ReturnValidationError(str(exc)) from exc
        youtube_id = talk.get("youtube_id")
        if isinstance(youtube_id, str) and youtube_id:
            expected = PurePosixPath("transcripts") / f"{youtube_id}.txt"
            if transcript_path != expected:
                raise ReturnValidationError(
                    f"{talk.get('filename', '<unknown>')} return transcript_path "
                    f"must match the claimed youtube_id: expected {expected}"
                )
        else:
            registered = talk.get("transcript_path")
            if not isinstance(registered, str):
                raise ReturnValidationError(
                    f"{talk.get('filename', '<unknown>')} cannot introduce a "
                    "non-YouTube transcript_path in a return; register the "
                    "artifact on the talk before claiming the batch"
                )
            try:
                registered_path = validate_transcript_path(registered)
            except PatternEvidenceError as exc:
                raise ReturnValidationError(
                    f"claimed talk transcript_path is invalid: {exc}"
                ) from exc
            if transcript_path != registered_path:
                raise ReturnValidationError(
                    f"{talk.get('filename', '<unknown>')} return transcript_path "
                    "must exactly match the pre-registered talk transcript_path"
                )
    observations = ret.get("pattern_observations")
    evidence_sources = (
        set(observations.get("evidence_sources") or [])
        if isinstance(observations, dict)
        else set()
    )
    if (
        transcript_source in TRANSCRIPT_SOURCES - {"none"}
        or "transcript" in evidence_sources
    ) and not has_transcript_source(talk):
        raise ReturnValidationError(
            f"{talk.get('filename', '<unknown>')} return claims transcript provenance/evidence, "
            "but the claimed talk has no transcript reference or active video source"
        )

    slide_source = ret.get("slide_source")
    returned_slides_path = ret.get("slides_local_path")
    if isinstance(returned_slides_path, str) and slide_source in {"pdf", "both"}:
        declared_pdf = next(
            (
                (field, talk[field])
                for field in ("slides_local_path", "slides_pdf_path", "pdf_path")
                if _is_nonempty(talk.get(field))
            ),
            None,
        )
        if declared_pdf is not None:
            field, expected_path = declared_pdf
            if returned_slides_path != expected_path:
                raise ReturnValidationError(
                    f"{talk.get('filename', '<unknown>')} return "
                    f"slides_local_path must match the exact {field} preclaim: "
                    f"expected {expected_path!r}"
                )
        else:
            drive_id = talk.get("google_drive_id")
            if not isinstance(drive_id, str) or not drive_id.strip():
                raise ReturnValidationError(
                    f"{talk.get('filename', '<unknown>')} cannot introduce a PDF "
                    "slides_local_path without a local PDF preclaim or preclaim "
                    "google_drive_id"
                )
            expected_path = f"slides/{drive_id}.pdf"
            if returned_slides_path != expected_path:
                raise ReturnValidationError(
                    f"{talk.get('filename', '<unknown>')} return "
                    f"slides_local_path must match preclaim google_drive_id: "
                    f"expected {expected_path!r}"
                )
    elif (
        isinstance(returned_slides_path, str)
        and slide_source != "video_extracted"
        and returned_slides_path != talk.get("slides_local_path")
    ):
        raise ReturnValidationError(
            f"{talk.get('filename', '<unknown>')} return slides_local_path must "
            "exactly match pre-registered talk provenance"
        )
    has_pptx = has_pptx_source(talk)
    has_pdf = has_pdf_source(talk)
    if slide_source in {"pptx", "both"} and not has_pptx:
        raise ReturnValidationError(
            f"{talk.get('filename', '<unknown>')} return claims slide_source "
            f"{slide_source!r}, but the claimed talk has no pptx_path"
        )
    if slide_source in {"pdf", "both"} and not has_pdf:
        raise ReturnValidationError(
            f"{talk.get('filename', '<unknown>')} return claims slide_source "
            f"{slide_source!r}, but the claimed talk has no independent PDF source"
        )
    if slide_source == "video_extracted" and not has_video_source(talk):
        raise ReturnValidationError(
            f"{talk.get('filename', '<unknown>')} return claims video-extracted "
            "slides, but the claimed talk has no active video source"
        )
    if "native_deck" in evidence_sources and not has_pptx:
        raise ReturnValidationError(
            f"{talk.get('filename', '<unknown>')} return claims native_deck evidence, "
            "but the claimed talk has no pptx_path"
        )
    if "delivery_video" in evidence_sources and not has_video_source(talk):
        raise ReturnValidationError(
            f"{talk.get('filename', '<unknown>')} return claims delivery_video evidence, "
            "but the claimed talk has no active video source"
        )


def _validate_terminal_status_against_talk(
    talk: dict,
    ret: dict,
    artifact_capabilities: dict[str, object] | None = None,
) -> None:
    """Bind mechanically decidable terminal skip reasons to live talk state."""
    filename = talk.get("filename", "<unknown>")
    status = ret.get("status")
    if artifact_capabilities is None:
        verified = set(source_capabilities(talk))
        repairs: set[str] = set()
        acquisitions = (
            set(source_capabilities(talk))
            if has_remote_acquisition_source(talk)
            else set()
        )
        declared_local = has_local_source_artifact(talk)
    else:
        raw_verified = artifact_capabilities.get("verified_capabilities")
        raw_acquisitions = artifact_capabilities.get("acquisition_capabilities")
        raw_repairs = artifact_capabilities.get("repair_capabilities")
        verified = (
            {item for item in raw_verified if isinstance(item, str)}
            if isinstance(raw_verified, (list, tuple, set, frozenset))
            else set()
        )
        acquisitions = (
            {item for item in raw_acquisitions if isinstance(item, str)}
            if isinstance(raw_acquisitions, (list, tuple, set, frozenset))
            else set()
        )
        repairs = (
            {item for item in raw_repairs if isinstance(item, str)}
            if isinstance(raw_repairs, (list, tuple, set, frozenset))
            else set()
        )
        declared_local = bool(verified | repairs)
    if status == "skipped_no_sources":
        capabilities = sorted(verified | repairs | acquisitions)
        if capabilities:
            raise ReturnValidationError(
                f"{filename} cannot finish skipped_no_sources while usable source "
                f"capabilities remain: {capabilities}"
            )
        return
    if status == "skipped_download_failed":
        if not acquisitions:
            raise ReturnValidationError(
                f"{filename} cannot finish skipped_download_failed without a "
                "usable remote video, transcript/YouTube identity, or slide "
                "acquisition path"
            )
        if declared_local:
            raise ReturnValidationError(
                f"{filename} cannot finish skipped_download_failed while local "
                "source capabilities remain verified or repairable: "
                f"{sorted(verified | repairs)}"
            )
        return
    if status != "skipped_duplicate":
        return
    relation = talk.get("source_relation")
    target = relation.get("target_filename") if isinstance(relation, dict) else None
    if (
        not isinstance(relation, dict)
        or relation.get("type") != "duplicate"
        or not isinstance(target, str)
        or not target.strip()
        or target == filename
    ):
        raise ReturnValidationError(
            f"{filename} cannot finish skipped_duplicate without "
            "source_relation.type='duplicate' and a target_filename"
        )


def validate_claim_against_talk(
    talk,
    ret,
    *,
    allow_completed=False,
    require_completed=False,
    artifact_capabilities: dict[str, object] | None = None,
) -> None:
    """Match a validated return to the talk's current generation claim."""
    expected = talk.get("_queue_claim") if isinstance(talk, dict) else None
    supplied = ret.get("queue_claim") if isinstance(ret, dict) else None
    filename = (
        talk.get("filename", "<unknown>") if isinstance(talk, dict) else "<unknown>"
    )
    if require_completed:
        allowed_states = {"completed"}
    elif allow_completed:
        allowed_states = {"claimed", "completed"}
    else:
        allowed_states = {"claimed"}
    if not isinstance(expected, dict) or expected.get("state") not in allowed_states:
        required = (
            "completed queue claim" if require_completed else "active queue claim"
        )
        raise ReturnValidationError(
            f"{filename} has no {required}; refusing an unclaimed or replayed return"
        )
    _validate_stored_claim(expected, filename)
    return_schema_version = resolve_return_schema_version(ret)
    claim_schema_version = expected.get("schema_version")
    if claim_schema_version in {
        LEGACY_QUEUE_CLAIM_SCHEMA_VERSION,
        PREVIOUS_QUEUE_CLAIM_SCHEMA_VERSION,
    } and return_schema_version not in {
        LEGACY_RETURN_SCHEMA_VERSION,
        PREVIOUS_RETURN_SCHEMA_VERSION,
    }:
        raise ReturnValidationError(
            f"{filename} queue claim schema_version "
            f"{claim_schema_version} cannot authorize return schema version "
            f"{return_schema_version}; legacy claims authorize only v1/v2 "
            "returns"
        )
    if (
        claim_schema_version in BASELINE_BOUND_QUEUE_CLAIM_SCHEMA_VERSIONS
        and return_schema_version != expected.get("required_return_schema_version")
    ):
        raise ReturnValidationError(
            f"{filename} queue claim schema_version {claim_schema_version} "
            f"requires return schema version "
            f"{expected.get('required_return_schema_version')}, got "
            f"{return_schema_version}"
        )
    if claim_schema_version in BASELINE_BOUND_QUEUE_CLAIM_SCHEMA_VERSIONS:
        baseline = validate_adherence_baseline(expected["adherence_baseline"])
        if expected.get("state") == "claimed":
            current_catalog = load_catalog()
            if (
                baseline["pattern_catalog_fingerprint"] != current_catalog.fingerprint
                or baseline["pattern_scoring_schema_version"]
                != PATTERN_SCORING_SCHEMA_VERSION
            ):
                raise ReturnValidationError(
                    f"{filename} schema-v{claim_schema_version} claim baseline "
                    "generation no longer matches the current catalog/scoring "
                    "contract; recover and reclaim the batch before accepting "
                    "returns"
                )
        if ret.get("status") in ANALYSIS_STATUSES:
            comparison = ret.get("adherence_comparison")
            baseline_count = cast(int, baseline["scored_talk_count"])
            if claim_schema_version == QUEUE_CLAIM_SCHEMA_VERSION:
                # A raw v5 return cannot author its engine-derived opportunity
                # identity. Canonical evidence binds (or suppresses) the
                # comparison after exhaustive outcomes are computed.
                if (
                    isinstance(comparison, dict)
                    and comparison.get("baseline") != baseline
                ):
                    raise ReturnValidationError(
                        f"{filename} adherence_comparison.baseline does not "
                        "exactly match the immutable queue-claim baseline"
                    )
            elif baseline_count >= MIN_ADHERENCE_BASELINE_TALKS:
                if not isinstance(comparison, dict):
                    raise ReturnValidationError(
                        f"{filename} schema-v{claim_schema_version} claim has an "
                        "eligible adherence "
                        "baseline and requires adherence_comparison"
                    )
                if comparison.get("baseline") != baseline:
                    raise ReturnValidationError(
                        f"{filename} adherence_comparison.baseline does not "
                        "exactly match the immutable queue-claim baseline"
                    )
                observations = ret.get("pattern_observations")
                if not isinstance(observations, dict):
                    raise ReturnValidationError(
                        f"{filename} return has no pattern observations for "
                        "adherence comparison"
                    )
                score = resolved_return_pattern_score(observations)
                comparison_score = comparison.get("talk_pattern_score")
                if (
                    isinstance(comparison_score, bool)
                    or not isinstance(comparison_score, int)
                    or comparison_score != score
                ):
                    raise ReturnValidationError(
                        f"{filename} adherence comparison talk score does not "
                        "match the validated return score"
                    )
            elif comparison is not None or ret.get("adherence_assessment") != "":
                raise ReturnValidationError(
                    f"{filename} schema-v{claim_schema_version} claim baseline "
                    "has fewer than "
                    f"{MIN_ADHERENCE_BASELINE_TALKS} talks; return the exact "
                    "empty adherence_assessment sentinel and omit "
                    "adherence_comparison"
                )
    talk_generation = talk.get("reprocess_generation")
    if (
        isinstance(talk_generation, bool)
        or not isinstance(talk_generation, int)
        or talk_generation < 1
    ):
        raise ReturnValidationError(
            f"{filename} talk reprocess_generation must be a positive integer"
        )
    if expected.get("reprocess_generation") != talk_generation:
        raise ReturnValidationError(
            f"{filename} active claim generation "
            f"{expected.get('reprocess_generation')!r} disagrees with talk generation "
            f"{talk_generation!r}"
        )
    if not isinstance(supplied, dict):
        raise ReturnValidationError(f"{filename} return has no validated queue_claim")
    for field in ("run_id", "batch_id", "reprocess_generation"):
        if supplied.get(field) != expected.get(field):
            raise ReturnValidationError(
                f"queue_claim.{field} {supplied.get(field)!r} does not match active "
                f"claim value {expected.get(field)!r}"
            )
    if (
        expected.get("state") == "claimed"
        and talk.get("status") != "reprocessing-inflight"
    ):
        raise ReturnValidationError(
            f"{filename} has an active claim but status is {talk.get('status')!r}, "
            "expected 'reprocessing-inflight'"
        )
    if expected.get("state") == "completed":
        if expected.get("schema_version") not in {
            PREVIOUS_QUEUE_CLAIM_SCHEMA_VERSION,
            BASELINE_QUEUE_CLAIM_SCHEMA_VERSION,
            SOURCE_LOCATED_QUEUE_CLAIM_SCHEMA_VERSION,
            QUEUE_CLAIM_SCHEMA_VERSION,
        }:
            raise ReturnValidationError(
                f"{filename} completed queue claim schema_version "
                f"{expected.get('schema_version')!r} predates the return-payload "
                "receipt; reprocess the talk before writing its analysis"
            )
        if expected.get("result_status") != ret.get("status"):
            raise ReturnValidationError(
                f"{filename} completed claim result {expected.get('result_status')!r} "
                f"does not match return status {ret.get('status')!r}"
            )
        if talk.get("status") != ret.get("status"):
            raise ReturnValidationError(
                f"{filename} DB status {talk.get('status')!r} does not match completed "
                f"return status {ret.get('status')!r}"
            )
        actual_receipt = canonical_return_sha256(ret)
        if expected.get("result_payload_sha256") != actual_receipt:
            raise ReturnValidationError(
                f"{filename} return payload SHA-256 does not match the receipt "
                "stored by persist-results.py; refusing a substituted return"
            )
    if (
        ret.get("status") in ANALYSIS_STATUSES
        and ret.get("slide_source") == "video_extracted"
    ):
        structured = ret.get("structured_data")
        manifest = (
            structured.get("video_extraction") if isinstance(structured, dict) else None
        )
        if not isinstance(manifest, dict):
            raise ReturnValidationError(
                f"{filename} return has no validated video_extraction manifest"
            )
        returned_id = manifest.get("source_video_id")
        expected_id = talk.get("youtube_id")
        if not isinstance(expected_id, str) or not expected_id.strip():
            raise ReturnValidationError(
                f"{filename} has no youtube_id to bind the video extraction manifest"
            )
        if returned_id != expected_id:
            raise ReturnValidationError(
                "structured_data.video_extraction.source_video_id "
                f"{returned_id!r} does not match talk youtube_id {expected_id!r}"
            )
    if (
        ret.get("status") in ANALYSIS_STATUSES
        and return_schema_version == RETURN_SCHEMA_VERSION
        and artifact_capabilities is not None
    ):
        observations = ret.get("pattern_observations")
        evidence_sources = (
            observations.get("evidence_sources")
            if isinstance(observations, dict)
            else None
        )
        structured = ret.get("structured_data")
        native_deck_used = (
            ret.get("slide_source") in {"pptx", "both"}
            or (
                isinstance(evidence_sources, list) and "native_deck" in evidence_sources
            )
            or (isinstance(structured, dict) and "native_deck_audit" in structured)
        )
        blocking_reason = required_pptx_evidence_blocking_reason(
            talk,
            artifact_capabilities,
            native_deck_used=native_deck_used,
        )
        if blocking_reason is not None:
            raise ReturnValidationError(
                f"{filename} cannot persist current analysis: {blocking_reason}"
            )
    _validate_terminal_status_against_talk(
        talk, ret, artifact_capabilities=artifact_capabilities
    )
    _validate_return_sources_against_talk(talk, ret)


def validate_persisted_catalog_generation(
    talk: dict, ret: dict, catalog: PatternCatalog, *, canonical_ret: dict | None = None
) -> None:
    """Require renderable analysis state to match the validated catalog."""
    if ret.get("status") not in ANALYSIS_STATUSES:
        return
    filename = ret.get("filename", "<unknown>")
    if resolve_return_schema_version(ret) in OUTCOME_GATE_RETURN_SCHEMA_VERSIONS:
        if talk.get("adherence_assessment") != ret.get("adherence_assessment"):
            raise ReturnValidationError(
                f"{filename} persisted adherence_assessment diverges from the "
                "receipt-bound return"
            )
        if "adherence_comparison" in ret:
            if talk.get("adherence_comparison") != ret["adherence_comparison"]:
                raise ReturnValidationError(
                    f"{filename} persisted adherence_comparison diverges from "
                    "the receipt-bound return"
                )
        elif "adherence_comparison" in talk:
            raise ReturnValidationError(
                f"{filename} persisted analysis retained an adherence_comparison "
                "for a below-threshold return"
            )
    return_version = resolve_return_schema_version(ret)
    if (
        return_version in SOURCE_LOCATED_RETURN_SCHEMA_VERSIONS
        and canonical_ret is None
    ):
        raise ReturnValidationError(
            f"{filename} current return requires canonical source evidence "
            "before persisted-state validation"
        )
    evidence_ret = canonical_ret or ret
    if resolve_return_schema_version(evidence_ret) != return_version:
        raise ReturnValidationError(
            f"{filename} canonical evidence changed return_schema_version"
        )
    if return_version == RETURN_SCHEMA_VERSION:
        validate_v5_adherence_opportunity(talk, ret, evidence_ret)
    assessment = assess_scoring_generation(evidence_ret, catalog)
    observations = talk.get("pattern_observations")
    if not isinstance(observations, dict):
        raise ReturnValidationError(
            f"{filename} persisted pattern_observations must be an object"
        )
    expected_observations = canonical_persisted_pattern_observations(
        evidence_ret, catalog, assessment
    )
    divergent_fields = sorted(
        field
        for field, expected in expected_observations.items()
        if observations.get(field) != expected
    )
    if divergent_fields:
        raise ReturnValidationError(
            f"{filename} persisted pattern observations diverge from the "
            f"receipt-bound canonical return fields: {divergent_fields}"
        )
    status = talk.get("pattern_scoring_generation_status")
    reasons = talk.get("pattern_scoring_generation_reasons")
    if not assessment.current:
        if return_version == RETURN_SCHEMA_VERSION:
            raise ReturnValidationError(
                f"{filename} current return cannot satisfy scoring generation "
                f"{PATTERN_SCORING_SCHEMA_VERSION}: "
                f"{list(assessment.reasons)}"
            )
        claim = talk.get("_queue_claim")
        historical_v3 = (
            return_version == BASELINE_RETURN_SCHEMA_VERSION
            and isinstance(claim, dict)
            and claim.get("schema_version") == BASELINE_QUEUE_CLAIM_SCHEMA_VERSION
            and claim.get("state") == "completed"
            and status == CURRENT_PATTERN_SCORING_GENERATION_STATUS
            and reasons == []
            and talk.get("pattern_scoring_schema_version")
            == BASELINE_RETURN_SCHEMA_VERSION
            and isinstance(claim.get("adherence_baseline"), dict)
            and talk.get("pattern_catalog_fingerprint")
            == claim["adherence_baseline"].get("pattern_catalog_fingerprint")
        )
        historical_v4 = (
            return_version == SOURCE_LOCATED_RETURN_SCHEMA_VERSION
            and isinstance(claim, dict)
            and claim.get("schema_version") == SOURCE_LOCATED_QUEUE_CLAIM_SCHEMA_VERSION
            and claim.get("state") == "completed"
            and status == CURRENT_PATTERN_SCORING_GENERATION_STATUS
            and reasons == []
            and talk.get("pattern_scoring_schema_version")
            == SOURCE_LOCATED_RETURN_SCHEMA_VERSION
            and isinstance(claim.get("adherence_baseline"), dict)
            and talk.get("pattern_catalog_fingerprint")
            == claim["adherence_baseline"].get("pattern_catalog_fingerprint")
            and isinstance(observations, dict)
            and observations.get("evidence_schema_version")
            == LEGACY_PATTERN_EVIDENCE_SCHEMA_VERSION
        )
        if historical_v3 or historical_v4:
            return
        if status != LEGACY_UNBASELINEABLE_SCORING_STATUS:
            raise ReturnValidationError(
                f"{filename} persisted pattern_scoring_generation_status "
                f"{status!r} does not match recomputed legacy evidence status"
            )
        if reasons != list(assessment.reasons):
            raise ReturnValidationError(
                f"{filename} persisted pattern_scoring_generation_reasons "
                "do not match the receipt-bound return and current catalog"
            )
        stale = sorted(
            field
            for field in (
                "pattern_scoring_schema_version",
                "pattern_catalog_fingerprint",
            )
            if field in talk
        )
        if stale:
            raise ReturnValidationError(
                f"{filename} legacy-unbaselineable analysis retains stale "
                f"current scoring metadata: {stale}"
            )
        return

    if status != CURRENT_PATTERN_SCORING_GENERATION_STATUS:
        raise ReturnValidationError(
            f"{filename} persisted pattern_scoring_generation_status {status!r} "
            f"does not match {CURRENT_PATTERN_SCORING_GENERATION_STATUS!r}"
        )
    if reasons != []:
        raise ReturnValidationError(
            f"{filename} current scoring generation must persist an empty "
            "pattern_scoring_generation_reasons array"
        )
    scoring_version = talk.get("pattern_scoring_schema_version")
    if scoring_version != PATTERN_SCORING_SCHEMA_VERSION:
        raise ReturnValidationError(
            f"{filename} persisted pattern_scoring_schema_version "
            f"{scoring_version!r} does not match renderer version "
            f"{PATTERN_SCORING_SCHEMA_VERSION}; rerun persist-results.py"
        )
    fingerprint = talk.get("pattern_catalog_fingerprint")
    if fingerprint != catalog.fingerprint:
        raise ReturnValidationError(
            f"{filename} persisted pattern_catalog_fingerprint {fingerprint!r} "
            f"does not match the catalog validated for rendering "
            f"{catalog.fingerprint!r}; rerun persist-results.py"
        )


def validate_batch_claims_against_talks(
    talks,
    returns,
    *,
    required_state: str,
    artifact_capabilities_by_filename: dict[str, dict[str, object]] | None = None,
) -> dict[str, dict]:
    """Bind one complete return batch to one complete queue-claim batch.

    Per-return generation checks are necessary but insufficient: accepting two
    valid returns from a three-member claim batch closes a partial batch and
    strands its final member.  Resolve the shared run/batch identity first,
    require the return filenames to equal every DB member carrying that
    identity, require one lifecycle state across the whole set, and only then
    run the existing member-level claim validation.

    ``claimed`` is the pre-persistence boundary; ``completed`` is the
    post-persistence analysis-write boundary.  A batch split across those
    states is invalid at both boundaries and must be recovered by a fresh
    queue generation rather than completed piecemeal.
    """
    if required_state not in {"claimed", "completed"}:
        raise ValueError(
            f"required_state must be 'claimed' or 'completed', got {required_state!r}"
        )
    if not isinstance(talks, list):
        raise ReturnValidationError("tracking database must carry a `talks` array")
    if not isinstance(returns, list) or not returns:
        raise ReturnValidationError("batch-returns must contain at least one return")

    try:
        validated_talks = validate_talk_record_schemas(talks)
    except IngressContractError as exc:
        raise ReturnValidationError(str(exc)) from exc

    return_names = [ret.get("filename") for ret in returns]
    duplicate_returns = sorted(
        {
            name
            for name in return_names
            if isinstance(name, str) and return_names.count(name) > 1
        }
    )
    if duplicate_returns:
        raise ReturnValidationError(
            f"duplicate return filename(s): {duplicate_returns}"
        )

    identities = {
        (ret["queue_claim"]["run_id"], ret["queue_claim"]["batch_id"])
        for ret in returns
    }
    if len(identities) != 1:
        raise ReturnValidationError(
            "all returns must carry one queue run_id/batch_id identity; got "
            f"{sorted(identities)}"
        )
    run_id, batch_id = next(iter(identities))

    talks_by_name: dict[str, dict] = {}
    duplicate_talks = set()
    for talk in validated_talks:
        filename = talk.get("filename")
        if not isinstance(filename, str) or not filename:
            continue
        if filename in talks_by_name:
            duplicate_talks.add(filename)
        else:
            talks_by_name[filename] = talk
    if duplicate_talks:
        raise ReturnValidationError(
            f"tracking database has duplicate filenames: {sorted(duplicate_talks)}"
        )

    members = []
    for talk in talks_by_name.values():
        claim = talk.get("_queue_claim")
        if (
            isinstance(claim, dict)
            and claim.get("run_id") == run_id
            and claim.get("batch_id") == batch_id
        ):
            members.append(talk)

    expected_names = {talk["filename"] for talk in members}
    supplied_names = set(return_names)
    missing = sorted(expected_names - supplied_names)
    unexpected = sorted(supplied_names - expected_names)
    if not expected_names or missing or unexpected:
        details = []
        if not expected_names:
            details.append("no matching DB members")
        if missing:
            details.append(f"missing {missing}")
        if unexpected:
            details.append(f"unexpected {unexpected}")
        raise ReturnValidationError(
            "return filenames must exactly match every member of queue batch "
            f"run_id={run_id!r}, batch_id={batch_id!r}; " + "; ".join(details)
        )

    wrong_states = sorted(
        (talk["filename"], talk.get("_queue_claim", {}).get("state"))
        for talk in members
        if talk.get("_queue_claim", {}).get("state") != required_state
    )
    if wrong_states:
        raise ReturnValidationError(
            "queue batch must be wholly "
            f"{required_state!r} before this write; closed or stranded member(s): "
            f"{wrong_states}"
        )

    member_claims = [talk["_queue_claim"] for talk in members]
    claim_versions = {claim.get("schema_version") for claim in member_claims}
    bound_versions = claim_versions & BASELINE_BOUND_QUEUE_CLAIM_SCHEMA_VERSIONS
    if bound_versions:
        if len(claim_versions) != 1:
            raise ReturnValidationError(
                "queue batch cannot mix baseline-bound claims with another claim "
                f"versions: {sorted(claim_versions, key=repr)}"
            )
        claim_version = next(iter(bound_versions))
        claimed_at_values = {claim.get("claimed_at") for claim in member_claims}
        if len(claimed_at_values) != 1:
            raise ReturnValidationError(
                f"schema-v{claim_version} queue batch must share one claimed_at "
                "timestamp"
            )
        canonical_baseline = member_claims[0].get("adherence_baseline")
        if any(
            claim.get("adherence_baseline") != canonical_baseline
            for claim in member_claims
        ):
            raise ReturnValidationError(
                f"schema-v{claim_version} queue batch must share one immutable "
                "adherence_baseline"
            )
        if not isinstance(canonical_baseline, dict) or canonical_baseline.get(
            "excluded_filenames"
        ) != sorted(expected_names):
            raise ReturnValidationError(
                f"schema-v{claim_version} "
                "adherence_baseline.excluded_filenames must equal "
                f"the exact queue batch {sorted(expected_names)}"
            )

    returns_by_name = {ret["filename"]: ret for ret in returns}
    for filename in sorted(expected_names):
        artifact_capabilities = None
        if artifact_capabilities_by_filename is not None:
            artifact_capabilities = artifact_capabilities_by_filename.get(filename)
            if artifact_capabilities is None:
                raise ReturnValidationError(
                    f"artifact capability preflight omitted queue member {filename!r}"
                )
        validate_claim_against_talk(
            talks_by_name[filename],
            returns_by_name[filename],
            require_completed=required_state == "completed",
            artifact_capabilities=artifact_capabilities,
        )
    return talks_by_name


def validate_return(ret, catalog: PatternCatalog | None = None) -> None:
    """Validate one return completely, raising before either writer mutates state."""
    if not isinstance(ret, dict):
        raise ReturnValidationError(
            f"subagent return must be an object, got {type(ret).__name__}"
        )
    return_schema_version = resolve_return_schema_version(ret)
    _require_string(ret, "filename")
    status = ret.get("status")
    if status not in RETURN_STATUSES:
        raise ReturnValidationError(
            f"status is required and must be one of {sorted(RETURN_STATUSES)}, got {status!r}"
        )
    _validate_queue_claim(ret.get("queue_claim"))
    _validate_clear_fields(ret.get("clear_fields"))
    _validate_processed_date(ret.get("processed_date"))
    slides_local_path = _validate_slides_local_path(ret)

    transcript_source = ret.get("transcript_source")
    if "transcript_path" in ret:
        try:
            validate_transcript_path(ret["transcript_path"])
        except PatternEvidenceError as exc:
            raise ReturnValidationError(str(exc)) from exc
    if (
        return_schema_version in SNAPSHOT_RETURN_SCHEMA_VERSIONS
        and "transcript_source" in ret
        and transcript_source not in TRANSCRIPT_SOURCES
    ):
        raise ReturnValidationError(
            "snapshot return transcript_source must be omitted when provenance "
            f"is unknown or be one of {sorted(TRANSCRIPT_SOURCES)}, got "
            f"{transcript_source!r}"
        )
    if (
        return_schema_version not in SNAPSHOT_RETURN_SCHEMA_VERSIONS
        and transcript_source is not None
        and transcript_source not in TRANSCRIPT_SOURCES
    ):
        raise ReturnValidationError(
            f"transcript_source must be one of {sorted(TRANSCRIPT_SOURCES)}, "
            f"got {transcript_source!r}"
        )

    slide_source = ret.get("slide_source")
    if slide_source is not None and slide_source not in SLIDE_SOURCES:
        raise ReturnValidationError(
            f"slide_source must be one of {sorted(SLIDE_SOURCES)}, got {slide_source!r}"
        )

    if status not in ANALYSIS_STATUSES:
        _validate_skipped_return_fields(ret)
        return

    if slide_source not in SLIDE_SOURCES:
        raise ReturnValidationError(
            f"slide_source is required for {status} and must be one of "
            f"{sorted(SLIDE_SOURCES)}, got {slide_source!r}"
        )
    if status == "processed" and slide_source == "none":
        raise ReturnValidationError(
            "status processed requires slide evidence; use processed_partial for slide_source none"
        )

    for field in PROSE_FIELDS:
        if field not in ret:
            raise ReturnValidationError(f"{field} is required and must be a string")
        if not isinstance(ret[field], str):
            raise ReturnValidationError(
                f"{field} must be a string, got {type(ret[field]).__name__}"
            )
        if (
            return_schema_version in SNAPSHOT_RETURN_SCHEMA_VERSIONS
            and field in SUBSTANTIVE_PROSE_FIELDS
            and not ret[field].strip()
        ):
            raise ReturnValidationError(
                f"{field} must be a non-whitespace string for {status}"
            )
        if (
            return_schema_version in SNAPSHOT_RETURN_SCHEMA_VERSIONS
            and field == "adherence_assessment"
            and ret[field] != ""
            and not ret[field].strip()
        ):
            raise ReturnValidationError(
                "adherence_assessment must be substantive or the exact empty "
                "string sentinel"
            )

    structured = ret.get("structured_data")
    if not isinstance(structured, dict):
        raise ReturnValidationError("structured_data is required and must be an object")
    if "video_extraction" in structured and slide_source != "video_extracted":
        raise ReturnValidationError(
            "structured_data.video_extraction is allowed only when "
            "slide_source is 'video_extracted'"
        )
    validate_structured_data(structured)
    validate_authored_slide_fields_against_source(structured, slide_source)
    video_static_slides_available = False
    if slide_source == "video_extracted":
        video_static_slides_available = _validate_video_return(
            ret, structured, slides_local_path
        )
    if return_schema_version in SNAPSHOT_RETURN_SCHEMA_VERSIONS:
        # Source trust errors are more actionable than dependent-group errors,
        # so enforce snapshot-dependent groups only after video scope is checked.
        validate_v2_structured_policy_shapes(structured)
        validate_structured_data(structured, require_complete_groups=True)
    verbatim = ret.get("verbatim_examples")
    if not isinstance(verbatim, dict):
        raise ReturnValidationError(
            "verbatim_examples is required and must be an object"
        )
    if return_schema_version in SNAPSHOT_RETURN_SCHEMA_VERSIONS:
        validate_verbatim_examples(verbatim, reject_unknown=True)
    observations = ret.get("pattern_observations")
    if not isinstance(observations, dict):
        raise ReturnValidationError(
            "pattern_observations is required and must be an object"
        )
    if return_schema_version in SNAPSHOT_RETURN_SCHEMA_VERSIONS:
        allowed_observation_fields = (
            V5_PATTERN_OBSERVATION_RETURN_FIELDS
            if return_schema_version == RETURN_SCHEMA_VERSION
            else PATTERN_OBSERVATION_RETURN_FIELDS
        )
        unknown_observations = sorted(set(observations) - allowed_observation_fields)
        if unknown_observations:
            raise ReturnValidationError(
                "snapshot return has unknown pattern_observations fields: "
                f"{unknown_observations}"
            )

    resolved_catalog = catalog or load_catalog()
    available_sources = _validate_available_sources(
        observations,
        slide_source,
        transcript_source,
        video_static_slides_available=video_static_slides_available,
    )
    _validate_source_inspection(observations, available_sources, return_schema_version)
    patterns = _validate_detection_list(
        observations,
        "patterns_detected",
        "pattern",
        resolved_catalog,
        available_sources,
        return_schema_version,
    )
    antipatterns = _validate_detection_list(
        observations,
        "antipatterns_detected",
        "antipattern",
        resolved_catalog,
        available_sources,
        return_schema_version,
    )
    detected_ids = {item["pattern_id"] for item in patterns} | {
        item["pattern_id"] for item in antipatterns
    }
    applicability = _validate_applicability_assessments(
        observations,
        resolved_catalog,
        available_sources,
        detected_ids,
        return_schema_version,
    )
    if return_schema_version == RETURN_SCHEMA_VERSION:
        validate_native_deck_design_receipt(
            structured=structured,
            observations=observations,
            slide_source=slide_source,
            detections=[*patterns, *antipatterns, *applicability],
        )
    not_evaluable = _validate_not_evaluable(
        observations, resolved_catalog, available_sources, return_schema_version
    )
    _validate_unavailable_catalog_gates(
        resolved_catalog,
        available_sources,
        not_evaluable,
        detected_ids,
        return_schema_version,
    )
    overlap = {item["pattern_id"] for item in patterns} & {
        item["pattern_id"] for item in antipatterns
    }
    if overlap:
        raise ReturnValidationError(
            f"pattern ids cannot appear in both detection lanes: {sorted(overlap)}"
        )
    evaluated = {item["pattern_id"] for item in patterns} | {
        item["pattern_id"] for item in antipatterns
    }
    unavailable_overlap = evaluated & {item["pattern_id"] for item in not_evaluable}
    if unavailable_overlap:
        raise ReturnValidationError(
            "pattern ids cannot be both detected and not_evaluable: "
            f"{sorted(unavailable_overlap)}"
        )
    _validate_score(
        observations,
        patterns,
        antipatterns,
        not_evaluable,
        return_schema_version,
    )
    _validate_adherence_comparison(
        ret,
        return_schema_version,
        resolved_return_pattern_score(observations),
    )
    _validate_catalog_feedback(ret.get("catalog_feedback"))


def audit_batch(returns, catalog: PatternCatalog | None = None):
    """Return (catalog, errors) after checking every entry and duplicate name."""
    if not isinstance(returns, list):
        raise ReturnValidationError(
            f"batch-returns must be a JSON array, got {type(returns).__name__}"
        )
    resolved_catalog = catalog or load_catalog()
    seen: set[str] = set()
    errors = []
    for index, ret in enumerate(returns):
        try:
            validate_return(ret, resolved_catalog)
        except ReturnValidationError as exc:
            name = ret.get("filename") if isinstance(ret, dict) else None
            label = name or f"entry {index}"
            errors.append(
                {"index": index, "filename": name, "error": f"{label}: {exc}"}
            )
        name = ret.get("filename") if isinstance(ret, dict) else None
        if not isinstance(name, str) or not name:
            continue
        if name in seen:
            errors.append(
                {
                    "index": index,
                    "filename": name,
                    "error": f"duplicate return filename {name!r}",
                }
            )
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
    schema_versions: dict[str, int] = {}
    scoring_generations = []
    for ret in returns:
        version = resolve_return_schema_version(ret)
        version_key = str(version)
        schema_versions[version_key] = schema_versions.get(version_key, 0) + 1
        if ret.get("status") not in ANALYSIS_STATUSES:
            scoring_generations.append(
                {
                    "filename": ret["filename"],
                    "status": UNSCORED_PATTERN_SCORING_GENERATION_STATUS,
                    "reasons": [],
                }
            )
        else:
            assessment = assess_scoring_generation(ret, catalog)
            scoring_generations.append(
                {
                    "filename": ret["filename"],
                    "status": (
                        CURRENT_PATTERN_SCORING_GENERATION_STATUS
                        if assessment.current
                        else LEGACY_UNBASELINEABLE_SCORING_STATUS
                    ),
                    "reasons": list(assessment.reasons),
                }
            )
    return {
        "valid": True,
        "returns": len(returns),
        "filenames": [ret["filename"] for ret in returns],
        "return_schema_versions": dict(sorted(schema_versions.items())),
        "pattern_scoring_schema_version": PATTERN_SCORING_SCHEMA_VERSION,
        "pattern_scoring_generations": scoring_generations,
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
        raise ReturnValidationError(
            f"{label} file {path} is not valid JSON: {exc}"
        ) from exc
