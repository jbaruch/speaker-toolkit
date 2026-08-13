"""Canonical source locations for vault-ingress pattern detections.

The model supplies a claim (quote, slide numbers, video range, or metadata
field).  This module resolves that claim against the claimed talk's artifacts
and returns a deep-copied detection carrying only canonical, auditable
locations.  It deliberately knows nothing about queue lifecycles or scoring;
both persistence surfaces call it before comparing a return with stored state.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

from artifact_locator import (
    ArtifactLocatorError,
    classify_artifact_locator,
    materialize_artifact_locator,
    materialize_native_root,
)
from ingress_contract import (
    has_remote_slide_acquisition,
    has_remote_video_acquisition,
)
from artifact_metadata import canonicalize_trusted_artifact_locator
from pdf_evidence import PdfArtifactProbe, PdfEvidenceError, probe_pdf_artifact
from transcript_quality import validate_transcript
from transcript_timing import (
    load_verified_quality_receipt,
    load_verified_segments,
    load_verified_transcript_source,
    quality_sidecar_path,
    resolve_quote,
    sidecar_path,
)
from pptx_evidence import (
    PPTX_EXTRACTION_PIPELINE_VERSION,
    PPTX_EXTRACTION_SCHEMA_VERSION,
    PptxArtifactProbe,
    PptxEvidenceError,
    probe_pptx_artifact,
    recompute_native_deck_audit,
    validate_native_deck_audit,
)
from video_evidence import (
    VideoArtifactProbe,
    VideoEvidenceAssessment,
    VideoEvidenceError,
)


LEGACY_PATTERN_EVIDENCE_SCHEMA_VERSION = 1
PATTERN_EVIDENCE_SCHEMA_VERSION = 2
SOURCE_LOCATED_RETURN_SCHEMA_VERSION = 4
EXHAUSTIVE_OUTCOME_RETURN_SCHEMA_VERSION = 5
# v6 validates as a return contract but does not persist yet: admitting it here
# would store a new record shape under talk schema v5. Persistence, the talk
# schema bump, the claim contract, and the migration advance together in the
# activation change, not piecemeal.
CANONICALIZABLE_RETURN_SCHEMA_VERSIONS = frozenset(
    {SOURCE_LOCATED_RETURN_SCHEMA_VERSION, EXHAUSTIVE_OUTCOME_RETURN_SCHEMA_VERSION}
)
CURRENT_PATTERN_SCORING_SCHEMA_VERSION = 5
PATTERN_OUTCOMES = frozenset(
    {"detected", "undetected", "not_evaluable", "not_applicable"}
)
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
# These are deliberately the worker-side fields, not the persisted canonical
# shape.  Artifact identities, resolved transcript locations, and metadata
# values are engine authority and a raw return must never be allowed to replay
# them from an older analysis.
EVIDENCE_CITATION_FIELDS = {
    "transcript": frozenset(
        {
            "source",
            "channel",
            "quote",
            "translation",
        }
    ),
    "timed_transcript": frozenset(
        {
            "source",
            "channel",
            "quote",
            "translation",
        }
    ),
    "slides": frozenset({"source", "channel", "slide_numbers"}),
    "slide_sequence": frozenset({"source", "channel", "slide_numbers"}),
    "video": frozenset({"source", "channel", "start_seconds", "end_seconds"}),
    "talk_metadata": frozenset({"source", "channel", "field"}),
}
EVIDENCE_SOURCE_CHANNELS = {
    "transcript": frozenset({"transcript", "timed_transcript", "talk_metadata"}),
    "static_slides": frozenset({"slides", "slide_sequence", "talk_metadata"}),
    "native_deck": frozenset({"slides", "slide_sequence", "talk_metadata"}),
    "delivery_video": frozenset({"video", "talk_metadata"}),
}
INSPECTABLE_EVIDENCE_SOURCES = frozenset(
    {"transcript", "static_slides", "native_deck", "delivery_video"}
)
SOURCE_INSPECTION_RAW_FIELDS = {
    "transcript": frozenset({"source", "line_ranges"}),
    "static_slides": frozenset({"source", "page_ranges"}),
    "native_deck": frozenset({"source", "page_ranges"}),
    "delivery_video": frozenset({"source", "time_ranges"}),
    "source_comparison": frozenset(
        {"source", "evidence_sources_used", "comparison_scope"}
    ),
}
SOURCE_INSPECTION_REASON_CODE = "missing_required_source_coverage"
APPLICABILITY_INSPECTION_REASON_CODE = "missing_applicability_source_coverage"
SOURCE_GATE_PENDING_REASON_CODE = "source_gate_pending_owner_review"
POSITIVE_ONLY_ABSENCE_REASON_CODE = "absence_not_authorized_by_catalog"
ABSENCE_CAPABILITY_AUTHORIZED_TRANSCRIPT = "authorized_transcript"
ABSENCE_CAPABILITY_AUTHORIZED_STATIC = "authorized_rendered_static"
ABSENCE_CAPABILITY_NONEXHAUSTIVE_VIDEO = "nonexhaustive_video_extraction"
ABSENCE_CAPABILITY_BARE_NATIVE = "bare_native_deck"
ABSENCE_CAPABILITY_BARE_VIDEO = "bare_delivery_video"
ABSENCE_CAPABILITY_COMPARISON_UNVERIFIED = "comparison_alignment_unverified"
ABSENCE_CAPABILITY_INCOMPLETE_RANGES = "incomplete_range_coverage"
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
USABLE_SLIDE_SOURCES = frozenset({"pptx", "pdf", "both", "video_extracted"})
MIN_TRANSCRIPT_QUOTE_WORDS = 4
TRANSCRIPT_BUNDLE_SNAPSHOT_ATTEMPTS = 3

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
_YOUTUBE_ID = re.compile(r"[A-Za-z0-9_-]{11}")
_VIDEO_SUFFIXES = frozenset({".mp4", ".webm", ".mkv", ".mov"})


class PatternEvidenceError(ValueError):
    """A detection cannot be bound to the claimed talk's source artifacts."""


@dataclass(frozen=True)
class _TranscriptBundleSnapshot:
    """Exact bytes observed for one transcript and its independent receipts."""

    transcript_bytes: bytes | None
    quality_bytes: bytes | None
    timing_bytes: bytes | None

    @property
    def signature(self) -> tuple[str | None, str | None, str | None]:
        """Return content identities, preserving missing-file state."""

        def digest(raw: bytes | None) -> str | None:
            return hashlib.sha256(raw).hexdigest() if raw is not None else None

        return (
            digest(self.transcript_bytes),
            digest(self.quality_bytes),
            digest(self.timing_bytes),
        )


@dataclass(frozen=True)
class _VerifiedTranscriptSnapshot:
    """One internally coherent transcript context or a stable rejection."""

    text: str | None
    transcript_reason: str
    policy_bound: bool
    timed_segments: tuple[dict[str, object], ...]
    timing_reason: str
    bundle: _TranscriptBundleSnapshot | None


def _nonempty(value: object) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def _dig(value: object, dotted: str) -> object:
    current = value
    for key in dotted.split("."):
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current


def validate_transcript_path(value: object) -> PurePosixPath:
    """Return one canonical vault-relative transcript path."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise PatternEvidenceError(
            "transcript_path must be a non-empty vault-relative string"
        )
    if "\\" in value:
        raise PatternEvidenceError("transcript_path must be a canonical POSIX path")
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or relative.as_posix() != value
        or len(relative.parts) != 2
        or relative.parts[0] != "transcripts"
        or relative.name in {".", ".."}
        or relative.suffix.lower() != ".txt"
    ):
        raise PatternEvidenceError(
            "transcript_path must name transcripts/<artifact>.txt"
        )
    return relative


def _resolve_local_artifact(
    vault_root: str | Path,
    value: object,
    *,
    suffix: str | frozenset[str],
    label: str,
    root_kind: str = "vault",
) -> Path:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise PatternEvidenceError(f"{label} must be a non-empty path")
    if "\x00" in value:
        raise PatternEvidenceError(f"{label} must not contain a NUL byte")
    _reject_ambiguous_path_segments(value, label=label)
    suffixes = frozenset({suffix}) if isinstance(suffix, str) else suffix
    root = _native_artifact_root(vault_root, label="vault_root").resolve()
    candidate = _materialize_artifact_locator(
        value,
        trusted_root=root,
        label=label,
    )
    if candidate.suffix.casefold() not in suffixes:
        raise PatternEvidenceError(f"{label} must use one of {sorted(suffixes)}")
    lexical = candidate
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PatternEvidenceError(
            f"{label} resolves outside {_trusted_root_description(root_kind)}"
        ) from exc
    if lexical != resolved:
        raise PatternEvidenceError(f"{label} must not traverse a symbolic link")
    if not resolved.is_file():
        raise PatternEvidenceError(f"{label} artifact is missing or unreadable")
    return resolved


def _lexical_absolute(value: str | Path) -> Path:
    """Return an absolute locator without touching the filesystem."""
    return _native_artifact_root(value, label="artifact root")


def _materialize_artifact_locator(
    value: object,
    *,
    trusted_root: object | None = None,
    label: str,
) -> Path:
    """Translate the shared closed locator contract to evidence errors."""
    try:
        return materialize_artifact_locator(value, trusted_root=trusted_root)
    except ArtifactLocatorError as exc:
        raise PatternEvidenceError(f"{label}: {exc.reason_code}") from exc


def _native_artifact_root(value: object, *, label: str) -> Path:
    """Require a lexical native absolute root without cwd/home expansion."""
    try:
        return materialize_native_root(value)
    except ArtifactLocatorError as exc:
        raise PatternEvidenceError(f"{label}: {exc.reason_code}") from exc


def _canonical_pdf_root(value: str | Path) -> Path:
    """Map a trusted configured PDF root without resolving a PDF leaf."""
    locator = _lexical_absolute(value)
    _mapped_locator, canonical_root = canonicalize_trusted_artifact_locator(
        locator,
        locator,
    )
    return canonical_root or locator


def _canonical_video_root(value: str | Path) -> Path:
    """Map a trusted configured video root without resolving a video leaf."""
    locator = _lexical_absolute(value)
    _mapped_locator, canonical_root = canonicalize_trusted_artifact_locator(
        locator,
        locator,
    )
    return canonical_root or locator


def _reject_ambiguous_path_segments(value: str, *, label: str) -> None:
    """Apply the shared host-independent lexical locator classifier."""
    try:
        classify_artifact_locator(value)
    except ArtifactLocatorError as exc:
        raise PatternEvidenceError(f"{label}: {exc.reason_code}") from exc


def _trusted_root_description(root_kind: str) -> str:
    """Name the trusted root a rejected locator was actually measured against.

    ``root_kind`` uses the same vocabulary ``_resolve_preclaim_artifact``
    returns, so a rejection diagnostic names the boundary that refused the
    artifact rather than defaulting to the vault root.
    """
    if root_kind == "vault":
        return "the vault root"
    if root_kind == "pptx_source":
        return "the configured pptx_source_dir root"
    if root_kind.startswith("preclaim:"):
        return f"the {root_kind.removeprefix('preclaim:')} preclaim root"
    return "the trusted root"


def _resolve_local_bounded_artifact(
    trusted_root: str | Path,
    value: object,
    *,
    suffix: str | frozenset[str],
    label: str,
    canonicalize_root: bool = False,
    root_kind: str = "vault",
) -> Path:
    """Validate a locator lexically; its bounded probe owns filesystem I/O."""
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise PatternEvidenceError(f"{label} must be a non-empty path")
    if "\x00" in value:
        raise PatternEvidenceError(f"{label} must not contain a NUL byte")
    _reject_ambiguous_path_segments(value, label=label)
    root_locator = _native_artifact_root(trusted_root, label="trusted root")
    candidate = _materialize_artifact_locator(
        value,
        trusted_root=root_locator,
        label=label,
    )
    canonical_root = root_locator
    if canonicalize_root:
        candidate, admitted_root = canonicalize_trusted_artifact_locator(
            candidate,
            root_locator,
        )
        if admitted_root is None:  # pragma: no cover - trusted_root is required
            raise PatternEvidenceError(f"{label} has no trusted root")
        canonical_root = admitted_root
    try:
        relative = candidate.relative_to(canonical_root)
    except ValueError as exc:
        raise PatternEvidenceError(
            f"{label} resolves outside {_trusted_root_description(root_kind)}"
        ) from exc
    suffixes = frozenset({suffix}) if isinstance(suffix, str) else suffix
    if not relative.parts or candidate.suffix.casefold() not in suffixes:
        raise PatternEvidenceError(f"{label} must use one of {sorted(suffixes)}")
    return candidate


def _resolve_local_pptx_artifact(
    trusted_root: str | Path,
    value: object,
    *,
    label: str,
    root_kind: str = "vault",
) -> Path:
    return _resolve_local_bounded_artifact(
        trusted_root,
        value,
        suffix=".pptx",
        label=label,
        root_kind=root_kind,
    )


def _resolve_local_pdf_artifact(
    trusted_root: str | Path,
    value: object,
    *,
    label: str,
    root_kind: str = "vault",
) -> Path:
    return _resolve_local_bounded_artifact(
        trusted_root,
        value,
        suffix=".pdf",
        label=label,
        canonicalize_root=True,
        root_kind=root_kind,
    )


def _resolve_local_video_artifact(
    trusted_root: str | Path,
    value: object,
    *,
    label: str,
    suffixes: frozenset[str] = _VIDEO_SUFFIXES,
) -> Path:
    """Resolve one video locator lexically; the bounded probe owns leaf I/O."""
    return _resolve_local_bounded_artifact(
        trusted_root,
        value,
        suffix=suffixes,
        label=label,
        canonicalize_root=True,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise PatternEvidenceError(f"cannot hash artifact {path}: {exc}") from exc
    return digest.hexdigest()


def _capture_transcript_bundle(path: Path) -> _TranscriptBundleSnapshot:
    """Read one best-effort content snapshot of transcript bundle paths."""

    def optional_bytes(artifact: Path) -> bytes | None:
        try:
            return artifact.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise PatternEvidenceError(
                f"cannot snapshot transcript bundle artifact {artifact}: {exc}"
            ) from exc

    return _TranscriptBundleSnapshot(
        transcript_bytes=optional_bytes(path),
        quality_bytes=optional_bytes(quality_sidecar_path(path)),
        timing_bytes=optional_bytes(sidecar_path(path)),
    )


def _artifact_identity(
    artifact_root: str | Path,
    path: Path,
    *,
    root_kind: str = "vault",
    artifact_sha256: str | None = None,
    lexical: bool = False,
) -> dict[str, str]:
    root = (
        _lexical_absolute(artifact_root) if lexical else Path(artifact_root).resolve()
    )
    resolved = _lexical_absolute(path) if lexical else path.resolve(strict=False)
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise PatternEvidenceError(
            f"artifact resolves outside the {root_kind!r} artifact root: {path}"
        ) from exc
    return {
        "artifact_root": root_kind,
        "artifact_path": relative.as_posix(),
        "artifact_sha256": (
            artifact_sha256 if artifact_sha256 is not None else _sha256_file(resolved)
        ),
    }


def _resolve_preclaim_artifact(
    vault_root: str | Path,
    owner: Mapping[str, object],
    field: str,
    *,
    suffix: str,
    source_roots: Mapping[str, object] | None,
) -> tuple[Path, Path, str]:
    """Resolve an owner-recorded local artifact under one trusted root."""
    value = owner.get(field)
    if not isinstance(value, str) or not value.strip():
        raise PatternEvidenceError(f"{field} must be a non-empty path")
    _reject_ambiguous_path_segments(value, label=field)
    vault = _native_artifact_root(vault_root, label="vault_root")
    configured_root: Path | None = None
    if (
        field == "pptx_path"
        and isinstance(source_roots, Mapping)
        and "pptx_source_dir" in source_roots
        and source_roots.get("pptx_source_dir") is not None
    ):
        configured_root = _native_artifact_root(
            source_roots.get("pptx_source_dir"),
            label="pptx_source_dir",
        )
    try:
        locator_kind = classify_artifact_locator(value)
    except ArtifactLocatorError as exc:
        raise PatternEvidenceError(f"{field}: {exc.reason_code}") from exc
    resolver = (
        _resolve_local_pptx_artifact
        if suffix == ".pptx"
        else _resolve_local_pdf_artifact
        if suffix == ".pdf"
        else None
    )
    if locator_kind == "relative":
        root = configured_root or vault
        root_kind = "pptx_source" if configured_root is not None else "vault"
        if resolver is None:
            path = _resolve_local_artifact(
                root, value, suffix=suffix, label=field, root_kind=root_kind
            )
        else:
            path = resolver(root, value, label=field, root_kind=root_kind)
        admitted_root = _canonical_pdf_root(root) if suffix == ".pdf" else root
        return path, admitted_root, root_kind

    absolute = _materialize_artifact_locator(value, label=field)
    for root, root_kind in (
        (vault, "vault"),
        (configured_root, "pptx_source"),
    ):
        if root is None:
            continue
        try:
            candidate = absolute.relative_to(root).as_posix()
        except ValueError:
            continue
        admitted_root = _canonical_pdf_root(root) if suffix == ".pdf" else root
        path = (
            _resolve_local_artifact(
                root, candidate, suffix=suffix, label=field, root_kind=root_kind
            )
            if resolver is None
            else resolver(root, candidate, label=field, root_kind=root_kind)
        )
        return path, admitted_root, root_kind

    root = _native_artifact_root(absolute.parent, label=f"{field} parent")
    preclaim_kind = f"preclaim:{field}"
    admitted_root = _canonical_pdf_root(root) if suffix == ".pdf" else root
    path = (
        _resolve_local_artifact(
            root, absolute.name, suffix=suffix, label=field, root_kind=preclaim_kind
        )
        if resolver is None
        else resolver(root, absolute.name, label=field, root_kind=preclaim_kind)
    )
    return path, admitted_root, preclaim_kind


def _pptx_locator_count(
    path: Path,
    *,
    trusted_root: Path | None = None,
) -> int:
    try:
        count = probe_pptx_artifact(path, trusted_root=trusted_root).slide_count
    except PptxEvidenceError as exc:
        raise PatternEvidenceError(f"cannot read PPTX artifact {path}: {exc}") from exc
    return count


def _declared_pdf_path(talk: Mapping[str, object]) -> tuple[str, object] | None:
    for field in ("slides_local_path", "slides_pdf_path", "pdf_path"):
        if _nonempty(talk.get(field)):
            return field, talk[field]
    slide_source = talk.get("slide_source")
    if isinstance(slide_source, str) and slide_source in {"pdf", "both"}:
        drive_id = talk.get("google_drive_id")
        if isinstance(drive_id, str) and drive_id.strip() == drive_id and drive_id:
            return "google_drive_id", f"slides/{drive_id}.pdf"
    return None


def _identity_duration(talk: Mapping[str, object], youtube_id: str) -> float | None:
    identity = talk.get("source_identity")
    if not (
        isinstance(identity, Mapping)
        and identity.get("schema_version") == 1
        and identity.get("provider") == "youtube"
        and identity.get("video_id") == youtube_id
    ):
        return None
    duration = identity.get("duration_seconds")
    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(float(duration))
        or float(duration) <= 0
    ):
        return None
    return float(duration)


def _catalog_duration(talk: Mapping[str, object]) -> float | None:
    """Return only provider/source-owned duration, never prior analysis prose."""
    youtube_id = talk.get("youtube_id")
    if isinstance(youtube_id, str):
        return _identity_duration(talk, youtube_id)
    return None


def _selected_video_assessment(
    assessment: VideoEvidenceAssessment | None,
) -> VideoEvidenceAssessment:
    """Resolve one operation-local assessment without hiding nested probes."""
    return assessment if assessment is not None else VideoEvidenceAssessment()


def _video_failure_reason(error: VideoEvidenceError) -> str:
    return f"{error.reason_code}: {error}"


def _video_unavailable_record(
    error: VideoEvidenceError,
    path: Path | None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "unavailable",
        "reason_code": error.reason_code,
        "reason": str(error),
        "details": copy.deepcopy(error.details),
        "artifact_path": str(path) if path is not None else None,
    }


def _local_video_binding(
    vault_root: str | Path,
    owner: Mapping[str, object],
    youtube_id: str | None,
) -> tuple[Path | None, str]:
    structured = owner.get("structured_data")
    manifest = (
        structured.get("video_extraction") if isinstance(structured, Mapping) else None
    )
    if isinstance(manifest, Mapping):
        if youtube_id is None:
            return None, "video_extraction manifest has no claimed video id"
        if (
            manifest.get("schema_version") != 3
            or manifest.get("source_video_id") != youtube_id
        ):
            return (
                None,
                "video_extraction manifest is not bound to the claimed video id",
            )
        try:
            source_path = resolve_video_extraction_source(
                vault_root,
                manifest,
                youtube_id,
            )
        except PatternEvidenceError as exc:
            return None, str(exc)
        return source_path, f"identity-bound local source video {source_path}"

    for field in ("video_local_path", "video_path"):
        if not _nonempty(owner.get(field)):
            continue
        try:
            source_path = _resolve_local_video_artifact(
                vault_root,
                owner[field],
                label=field,
            )
        except PatternEvidenceError as exc:
            return None, str(exc)
        if youtube_id is not None and source_path.stem != youtube_id:
            return None, f"{field} filename is not bound to youtube_id"
        return source_path, f"pre-registered local source video {source_path}"
    return None, "no predeclared local video artifact"


def resolve_video_extraction_source(
    vault_root: str | Path,
    manifest: Mapping[str, object],
    youtube_id: str,
) -> Path:
    """Resolve one manifest MP4 lexically; the bounded probe owns leaf I/O."""
    source_path = _resolve_local_video_artifact(
        vault_root,
        manifest.get("source_video_path"),
        label="video_extraction.source_video_path",
        suffixes=frozenset({".mp4"}),
    )
    if source_path.name != f"{youtube_id}.mp4":
        raise PatternEvidenceError(
            "local source-video filename is not bound to youtube_id"
        )
    return source_path


def _probe_video_manifest_artifacts(
    vault_root: str | Path,
    manifest: Mapping[str, object],
    youtube_id: str,
) -> dict[str, tuple[PdfArtifactProbe, Path]]:
    """Bound every current manifest PDF before any part can be persisted."""
    artifacts = manifest.get("artifacts")
    count = manifest.get("unique_frame_count")
    if (
        not isinstance(artifacts, list)
        or isinstance(count, bool)
        or not isinstance(count, int)
        or count < 1
    ):
        raise PatternEvidenceError(
            "video_extraction artifacts have no valid shared page count"
        )
    artifact_root = _canonical_pdf_root(vault_root)
    probes: dict[str, tuple[PdfArtifactProbe, Path]] = {}
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, Mapping):
            raise PatternEvidenceError(
                f"video_extraction artifact {index} must be an object"
            )
        scope = artifact.get("artifact_scope")
        if scope not in {"slide_region", "full_frame_context"} or scope in probes:
            raise PatternEvidenceError(
                f"video_extraction artifact {index} has an invalid scope"
            )
        if (
            artifact.get("source_video_id") != youtube_id
            or artifact.get("page_count") != count
        ):
            raise PatternEvidenceError(
                f"video_extraction {scope} artifact is not identity/count bound"
            )
        artifact_path = _resolve_local_pdf_artifact(
            vault_root,
            artifact.get("path"),
            label=f"video_extraction {scope} artifact",
        )
        artifact_probe = probe_pdf_artifact(
            artifact_path,
            trusted_root=artifact_root,
        )
        if artifact_probe.page_count != count:
            raise PatternEvidenceError(
                f"video_extraction {scope} artifact page count is not verified"
            )
        probes[scope] = (artifact_probe, artifact_path)
    return probes


def _trusted_video_slide_probe(
    vault_root: str | Path,
    owner: Mapping[str, object],
    youtube_id: str,
    *,
    artifact_probes: Mapping[str, tuple[PdfArtifactProbe, Path]] | None = None,
    source_video_probe: VideoArtifactProbe | None = None,
    video_evidence_assessment: VideoEvidenceAssessment | None = None,
) -> tuple[PdfArtifactProbe | None, str, Path | None]:
    structured = owner.get("structured_data")
    manifest = (
        structured.get("video_extraction") if isinstance(structured, Mapping) else None
    )
    if not isinstance(manifest, Mapping):
        return None, "no video_extraction manifest", None
    count = manifest.get("unique_frame_count")
    if (
        artifact_probes is None
        and not isinstance(count, bool)
        and isinstance(count, int)
        and count > 0
    ):
        try:
            artifact_probes = _probe_video_manifest_artifacts(
                vault_root,
                manifest,
                youtube_id,
            )
        except PatternEvidenceError as exc:
            return None, str(exc), None
    trusted = (
        manifest.get("schema_version") == 3
        and manifest.get("source_video_id") == youtube_id
        and manifest.get("slide_region_method") == "manual"
        and manifest.get("slide_region_applied") is True
        and manifest.get("slide_region_verified") is True
        and manifest.get("review_required") is False
        and manifest.get("review_reason") is None
        and not isinstance(count, bool)
        and isinstance(count, int)
        and count > 0
    )
    if not trusted:
        return None, "video slide-region provenance is not trusted", None
    local_path, local_reason = _local_video_binding(vault_root, owner, youtube_id)
    if local_path is None:
        return None, local_reason, None
    if source_video_probe is None:
        try:
            source_video_probe = _selected_video_assessment(
                video_evidence_assessment
            ).probe(
                local_path,
                trusted_root=_canonical_video_root(vault_root),
            )
        except VideoEvidenceError as exc:
            return None, _video_failure_reason(exc), None
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        return None, "video_extraction artifacts must be an array", None
    slide_artifacts = [
        artifact
        for artifact in artifacts
        if isinstance(artifact, Mapping)
        and artifact.get("artifact_scope") == "slide_region"
    ]
    if len(slide_artifacts) != 1:
        return None, "trusted video extraction requires one slide_region artifact", None
    artifact = slide_artifacts[0]
    if (
        artifact.get("trusted_for_authored_slide_analysis") is not True
        or artifact.get("crop_verified") is not True
        or artifact.get("source_video_id") != youtube_id
        or artifact.get("source_video_path") != manifest.get("source_video_path")
        or artifact.get("page_count") != count
    ):
        return None, "slide_region artifact is not identity/count bound", None
    artifact_root = _canonical_pdf_root(vault_root)
    if artifact_probes is not None:
        admitted = artifact_probes.get("slide_region")
        if admitted is None:
            return None, "trusted video extraction has no slide_region probe", None
        artifact_probe, artifact_path = admitted
    else:
        try:
            artifact_path = _resolve_local_pdf_artifact(
                vault_root,
                artifact.get("path"),
                label="video_extraction slide_region artifact",
            )
            artifact_probe = probe_pdf_artifact(
                artifact_path,
                trusted_root=artifact_root,
            )
            if artifact_probe.page_count != count:
                return None, "slide_region artifact page count is not verified", None
        except PatternEvidenceError as exc:
            return None, str(exc), None
    promoted = owner.get("slides_local_path")
    if _nonempty(promoted):
        try:
            path = _resolve_local_pdf_artifact(
                vault_root,
                promoted,
                label="slides_local_path",
            )
            promoted_probe = probe_pdf_artifact(
                path,
                trusted_root=artifact_root,
            )
        except PatternEvidenceError as exc:
            return None, str(exc), None
        if promoted_probe.page_count != count:
            return (
                None,
                (
                    "trusted video slide-region page count disagrees with the local "
                    "promoted PDF"
                ),
                None,
            )
        if promoted_probe.source_sha256 != artifact_probe.source_sha256:
            return (
                None,
                (
                    "trusted video slide-region content digest disagrees with the "
                    "local promoted PDF"
                ),
                None,
            )
        return (
            promoted_probe,
            f"trusted promoted video slide-region PDF {path}",
            path,
        )
    # A processed_partial return may intentionally leave the reviewed artifact
    # unpromoted. The manifest-owned slide_region PDF is still identity-, crop-,
    # and count-bound evidence and is safe for citations.
    return (
        artifact_probe,
        f"trusted unpromoted video slide-region PDF {artifact_path}",
        artifact_path,
    )


def _returned_slide_artifact(
    vault_root: str | Path,
    talk: Mapping[str, object],
    ret: Mapping[str, object],
    *,
    video_evidence_assessment: VideoEvidenceAssessment | None = None,
) -> tuple[
    PdfArtifactProbe | None,
    str,
    Path | None,
    Path | None,
    VideoArtifactProbe | None,
]:
    """Admit only a current-run artifact at a path fixed by preclaim identity."""
    slide_source = ret.get("slide_source")
    returned_path = ret.get("slides_local_path")
    if slide_source in {"pdf", "both"}:
        if not _nonempty(returned_path):
            return (
                None,
                "return makes no explicit current-run PDF artifact assertion",
                None,
                None,
                None,
            )
        declared_pdf = _declared_pdf_path(talk)
        if declared_pdf is not None and declared_pdf[0] != "google_drive_id":
            field, expected = declared_pdf
            if returned_path != expected:
                raise PatternEvidenceError(
                    f"return PDF path must match the exact {field} preclaim"
                )
            path, artifact_root, _root_kind = _resolve_preclaim_artifact(
                vault_root,
                talk,
                field,
                suffix=".pdf",
                source_roots=None,
            )
        else:
            drive_id = talk.get("google_drive_id")
            if not isinstance(drive_id, str) or not drive_id.strip():
                raise PatternEvidenceError(
                    "return PDF cannot be identity-bound without a local PDF "
                    "preclaim or preclaim google_drive_id"
                )
            expected = f"slides/{drive_id}.pdf"
            if returned_path != expected:
                raise PatternEvidenceError(
                    f"return PDF path must be the identity-derived {expected!r}"
                )
            artifact_root = _canonical_pdf_root(vault_root)
            path = _resolve_local_pdf_artifact(
                vault_root,
                expected,
                label="return slides_local_path",
            )
        return (
            probe_pdf_artifact(path, trusted_root=artifact_root),
            f"read identity-bound PDF {path}",
            path,
            None,
            None,
        )
    if slide_source == "video_extracted":
        youtube_id = talk.get("youtube_id")
        if not isinstance(youtube_id, str) or _YOUTUBE_ID.fullmatch(youtube_id) is None:
            raise PatternEvidenceError(
                "return video slides have no valid preclaim youtube_id"
            )
        expected = f"slides/{youtube_id}.pdf"
        if _nonempty(returned_path) and returned_path != expected:
            raise PatternEvidenceError(
                f"return video slide path must be the identity-derived {expected!r}"
            )
        structured = ret.get("structured_data")
        manifest = (
            structured.get("video_extraction")
            if isinstance(structured, Mapping)
            else None
        )
        if not isinstance(manifest, Mapping):
            raise PatternEvidenceError(
                "return video slides have no video_extraction manifest"
            )
        local_path, local_reason = _local_video_binding(vault_root, ret, youtube_id)
        if local_path is None:
            raise PatternEvidenceError(
                "return video extraction source is unavailable: " + local_reason
            )
        try:
            source_video_probe = _selected_video_assessment(
                video_evidence_assessment
            ).probe(
                local_path,
                trusted_root=_canonical_video_root(vault_root),
            )
        except VideoEvidenceError as exc:
            raise PatternEvidenceError(
                "return video extraction source is unavailable: "
                + _video_failure_reason(exc)
            ) from exc
        artifact_probes = _probe_video_manifest_artifacts(
            vault_root,
            manifest,
            youtube_id,
        )
        probe, reason, slide_path = _trusted_video_slide_probe(
            vault_root,
            ret,
            youtube_id,
            artifact_probes=artifact_probes,
            source_video_probe=source_video_probe,
            video_evidence_assessment=video_evidence_assessment,
        )
        observations = ret.get("pattern_observations")
        claimed_static = (
            "static_slides" in (observations.get("evidence_sources") or [])
            if isinstance(observations, Mapping)
            else False
        )
        if probe is None or slide_path is None:
            if _nonempty(returned_path) or claimed_static:
                raise PatternEvidenceError(reason)
            return None, reason, None, local_path, source_video_probe
        return probe, reason, slide_path, local_path, source_video_probe
    return (
        None,
        "return declares no deterministic local slide artifact",
        None,
        None,
        None,
    )


def admit_return_artifacts(
    vault_root: str | Path,
    talk: Mapping[str, object],
    ret: Mapping[str, object],
    *,
    video_evidence_assessment: VideoEvidenceAssessment | None = None,
) -> None:
    """Bound current-return slide artifacts for every supported return schema."""
    structured = ret.get("structured_data")
    if (
        isinstance(structured, Mapping)
        and "video_extraction" in structured
        and ret.get("slide_source") != "video_extracted"
    ):
        raise PatternEvidenceError(
            "return video_extraction provenance requires slide_source 'video_extracted'"
        )
    if ret.get("slide_source") not in {"pdf", "both", "video_extracted"}:
        return
    try:
        _returned_slide_artifact(
            vault_root,
            talk,
            ret,
            video_evidence_assessment=_selected_video_assessment(
                video_evidence_assessment
            ),
        )
    except PdfEvidenceError as exc:
        raise PatternEvidenceError(
            f"cannot admit returned PDF artifact ({exc.reason_code}): {exc}"
        ) from exc


def resolve_transcript_artifact(
    vault_root: str | Path,
    talk: Mapping[str, object],
    _ret: Mapping[str, object] | None = None,
) -> tuple[Path | None, str]:
    """Resolve a transcript exclusively from the pre-return talk record.

    ``_ret`` remains as a compatibility argument for callers from the brief-lived
    v3 citation implementation.  It is deliberately ignored: a return must not
    redirect evidence resolution to another talk's transcript.
    """
    root = _native_artifact_root(vault_root, label="vault_root").resolve()

    def bound(candidate: Path) -> Path:
        lexical = _materialize_artifact_locator(
            candidate,
            label="transcript artifact",
        )
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise PatternEvidenceError(
                "transcript artifact resolves outside the vault root"
            ) from exc
        if lexical != resolved:
            raise PatternEvidenceError(
                "transcript artifact must not traverse a symbolic link"
            )
        return resolved

    explicit = talk.get("transcript_path")
    youtube_id = talk.get("youtube_id")
    if _nonempty(explicit):
        relative = validate_transcript_path(explicit)
        if isinstance(youtube_id, str) and _YOUTUBE_ID.fullmatch(youtube_id):
            expected = PurePosixPath("transcripts") / f"{youtube_id}.txt"
            if relative != expected:
                raise PatternEvidenceError(
                    "transcript_path does not match the claimed talk's youtube_id"
                )
        resolved = bound(root.joinpath(*relative.parts))
        return resolved, f"resolved transcript_path {relative}"

    if isinstance(youtube_id, str) and youtube_id:
        if _YOUTUBE_ID.fullmatch(youtube_id) is None:
            raise PatternEvidenceError(
                f"youtube_id {youtube_id!r} is not an 11-character YouTube id"
            )
        return bound(root / "transcripts" / f"{youtube_id}.txt"), (
            f"resolved transcript from youtube_id {youtube_id}"
        )

    return None, "no pre-registered transcript_path or youtube_id"


def _validate_transcript_quality_for_owner(
    transcript_path: Path,
    transcript_text: str,
    talk: Mapping[str, object],
    *,
    trusted_fallback_duration: float | None = None,
    trusted_local_media_sha256: str | None = None,
) -> tuple[bool, str, str, bool]:
    """Apply a hash-current acquisition receipt in current owner context."""
    receipt, receipt_reason = load_verified_quality_receipt(
        transcript_path, transcript_text
    )
    if not isinstance(receipt, Mapping):
        return (
            False,
            "current evidence requires a hash-current transcript quality "
            f"receipt: {receipt_reason}",
            receipt_reason,
            False,
        )
    policy = receipt.get("policy")
    provenance = receipt.get("provenance")
    if not isinstance(policy, Mapping) or not isinstance(provenance, Mapping):
        return (
            False,
            "verified transcript quality receipt is incomplete",
            receipt_reason,
            False,
        )
    quality_min_words = policy.get("min_words")
    quality_duration = policy.get("duration_seconds")
    if not isinstance(quality_min_words, int) or isinstance(
        quality_min_words, bool
    ):  # pragma: no cover - loader owns shape
        return False, "quality receipt min_words is invalid", receipt_reason, False

    provenance_kind = provenance.get("kind")
    owner_youtube_id = talk.get("youtube_id")
    owner_duration = _catalog_duration(talk)
    if provenance_kind == "youtube_duration":
        if provenance.get("video_id") != owner_youtube_id:
            return (
                False,
                "receipt_owner_mismatch: transcript quality receipt youtube "
                "video_id does not match "
                "the claimed talk",
                receipt_reason,
                True,
            )
        if (
            owner_duration is not None
            and isinstance(quality_duration, (int, float))
            and not isinstance(quality_duration, bool)
            and abs(float(quality_duration) - owner_duration) > 1.0
        ):
            return (
                False,
                "receipt_owner_mismatch: transcript quality receipt duration "
                "disagrees with provider "
                "source identity",
                receipt_reason,
                True,
            )
    elif provenance_kind == "local_media_duration":
        if trusted_local_media_sha256 is None:
            return (
                False,
                "receipt_owner_mismatch: transcript quality receipt cites "
                "local media that is not "
                "bound to the claimed talk",
                receipt_reason,
                True,
            )
        if provenance.get("media_sha256") != trusted_local_media_sha256:
            return (
                False,
                "receipt_owner_mismatch: transcript quality receipt local-media "
                "digest does not match "
                "the claimed talk artifact",
                receipt_reason,
                True,
            )
        if (
            trusted_fallback_duration is None
            or not isinstance(quality_duration, (int, float))
            or isinstance(quality_duration, bool)
            or abs(float(quality_duration) - trusted_fallback_duration) > 1.0
        ):
            return (
                False,
                "receipt_owner_mismatch: transcript quality receipt duration "
                "disagrees with the bound "
                "local-media artifact",
                receipt_reason,
                True,
            )
    elif provenance_kind == "fixed_default":
        # The fixed-default policy is a non-relaxable acquisition result used
        # by the offline existing-artifact fast path. Only duration-bearing
        # provenance claims an owner duration and therefore needs identity or
        # media-byte binding here.
        pass
    else:  # pragma: no cover - loader owns provenance shape
        return False, "quality receipt provenance is invalid", receipt_reason, False

    valid, quality_reason = validate_transcript(
        transcript_text,
        min_words=quality_min_words,
        duration_seconds=quality_duration,
    )
    return valid, quality_reason, receipt_reason, True


def validate_transcript_quality_for_owner(
    transcript_path: Path,
    _transcript_text: str,
    talk: Mapping[str, object],
    *,
    vault_root: str | Path,
    video_evidence_assessment: VideoEvidenceAssessment | None = None,
) -> tuple[bool, str, str, bool]:
    """Validate one transcript against its full receipt and current owner.

    The public wrapper is shared by offline preflight and evidence resolution.
    The path is authoritative; the compatibility text argument is never mixed
    with newer on-disk receipts and is therefore intentionally ignored.
    Its final boolean says whether a hash-current receipt was decoded; a false
    validity with a true receipt flag is therefore an owner/provenance or
    transcript-quality failure, not a missing-receipt failure.
    """
    raw_youtube_id = talk.get("youtube_id")
    youtube_id = (
        raw_youtube_id
        if isinstance(raw_youtube_id, str) and _YOUTUBE_ID.fullmatch(raw_youtube_id)
        else None
    )
    local_media_path, _ = _local_video_binding(vault_root, talk, youtube_id)
    local_media_duration: float | None = None
    local_media_sha256: str | None = None
    if local_media_path is not None:
        try:
            local_media_probe = _selected_video_assessment(
                video_evidence_assessment
            ).probe(
                local_media_path,
                trusted_root=_canonical_video_root(vault_root),
            )
        except VideoEvidenceError:
            pass
        else:
            local_media_duration = local_media_probe.duration_seconds
            local_media_sha256 = local_media_probe.source_sha256
    unstable_reason = (
        "transcript bundle changed during quality validation; retry after "
        "acquisition or cloud sync completes"
    )
    for _attempt in range(TRANSCRIPT_BUNDLE_SNAPSHOT_ATTEMPTS):
        try:
            before = _capture_transcript_bundle(transcript_path)
        except PatternEvidenceError as exc:
            unstable_reason = str(exc)
            continue
        if before.transcript_bytes is None:
            result = (
                False,
                f"transcript artifact is missing: {transcript_path}",
                f"transcript artifact is missing: {transcript_path}",
                False,
            )
        else:
            try:
                current_text = before.transcript_bytes.decode("utf-8")
            except UnicodeDecodeError:
                # These strings reach public preflight capability facts, so the
                # decoder's message — which carries the offending byte offset —
                # stays out of them.
                result = (
                    False,
                    "transcript artifact is not valid UTF-8",
                    "transcript artifact is not valid UTF-8",
                    False,
                )
            else:
                result = _validate_transcript_quality_for_owner(
                    transcript_path,
                    current_text,
                    talk,
                    trusted_fallback_duration=local_media_duration,
                    trusted_local_media_sha256=local_media_sha256,
                )
        try:
            after = _capture_transcript_bundle(transcript_path)
        except PatternEvidenceError as exc:
            unstable_reason = str(exc)
            continue
        if after.signature == before.signature:
            return result
    return False, unstable_reason, unstable_reason, False


def _load_verified_transcript_snapshot(
    transcript_path: Path,
    talk: Mapping[str, object],
    *,
    owner_source: str,
    owner_video_id: str | None,
    owner_media_sha256: str | None,
    owner_duration_seconds: float | None,
    local_media_probe: VideoArtifactProbe | None,
) -> _VerifiedTranscriptSnapshot:
    """Load text and both receipts from one stable bundle generation.

    Multi-file replacement is transactional on caught errors but cannot be one
    portable atomic rename. A reader can therefore encounter the brief rename
    window or a cloud-sync replacement. Content snapshots around every loader
    call either prove that all derived values came from one stable generation,
    retry against the new generation, or reject the transcript lane.
    """

    unstable_reason = (
        "transcript bundle changed during evidence snapshot; retry after "
        "acquisition or cloud sync completes"
    )
    for _attempt in range(TRANSCRIPT_BUNDLE_SNAPSHOT_ATTEMPTS):
        try:
            before = _capture_transcript_bundle(transcript_path)
        except PatternEvidenceError as exc:
            unstable_reason = str(exc)
            continue

        transcript_bytes = before.transcript_bytes
        if transcript_bytes is None:
            try:
                after = _capture_transcript_bundle(transcript_path)
            except PatternEvidenceError as exc:
                unstable_reason = str(exc)
                continue
            if after.signature != before.signature:
                continue
            return _VerifiedTranscriptSnapshot(
                text=None,
                transcript_reason=f"transcript file is missing: {transcript_path}",
                policy_bound=False,
                timed_segments=(),
                timing_reason="timed transcript is unavailable",
                bundle=None,
            )

        try:
            transcript_text = transcript_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                after = _capture_transcript_bundle(transcript_path)
            except PatternEvidenceError as snapshot_exc:
                unstable_reason = str(snapshot_exc)
                continue
            if after.signature != before.signature:
                continue
            return _VerifiedTranscriptSnapshot(
                text=None,
                # Reaches public preflight capability facts: no host path and
                # no decoder byte offset.
                transcript_reason="transcript file is not valid UTF-8",
                policy_bound=False,
                timed_segments=(),
                timing_reason="timed transcript is unavailable",
                bundle=None,
            )

        (
            transcript_ok,
            quality_reason,
            policy_reason,
            policy_bound,
        ) = _validate_transcript_quality_for_owner(
            transcript_path,
            transcript_text,
            talk,
            trusted_fallback_duration=(
                local_media_probe.duration_seconds
                if local_media_probe is not None
                else None
            ),
            trusted_local_media_sha256=(
                local_media_probe.source_sha256
                if local_media_probe is not None
                else None
            ),
        )
        provenance_reason = "timing provenance was not inspected"
        timed_segments: list[dict[str, object]] = []
        timing_reason = "timed transcript is unavailable"
        if transcript_ok:
            _provenance_source, provenance_reason = load_verified_transcript_source(
                transcript_path,
                transcript_text,
                owner_source=owner_source,
                owner_video_id=owner_video_id,
                owner_media_sha256=owner_media_sha256,
                owner_duration_seconds=owner_duration_seconds,
            )
            timed_segments, timing_reason = load_verified_segments(
                transcript_path,
                transcript_text,
                owner_source=owner_source,
                owner_video_id=owner_video_id,
                owner_media_sha256=owner_media_sha256,
                owner_duration_seconds=owner_duration_seconds,
            )

        try:
            after = _capture_transcript_bundle(transcript_path)
        except PatternEvidenceError as exc:
            unstable_reason = str(exc)
            continue
        if after.signature != before.signature:
            continue
        if not transcript_ok:
            return _VerifiedTranscriptSnapshot(
                text=None,
                transcript_reason=(
                    f"transcript artifact failed quality validation: {quality_reason}"
                ),
                policy_bound=False,
                timed_segments=(),
                timing_reason=timing_reason,
                bundle=None,
            )
        return _VerifiedTranscriptSnapshot(
            text=transcript_text,
            transcript_reason=(
                f"loaded validated transcript {transcript_path}: "
                f"{quality_reason}; {policy_reason}; {provenance_reason}"
            ),
            policy_bound=policy_bound,
            timed_segments=tuple(timed_segments),
            timing_reason=timing_reason,
            bundle=before,
        )

    return _VerifiedTranscriptSnapshot(
        text=None,
        transcript_reason=unstable_reason,
        policy_bound=False,
        timed_segments=(),
        timing_reason="timed transcript is unavailable from an unstable bundle",
        bundle=None,
    )


def build_evidence_context(
    vault_root: str | Path,
    talk: Mapping[str, object],
    ret: Mapping[str, object] | None = None,
    source_roots: Mapping[str, object] | None = None,
    *,
    video_evidence_assessment: VideoEvidenceAssessment | None = None,
) -> dict[str, object]:
    """Resolve preclaim sources plus identity-derived current-run artifacts."""
    selected_video_assessment = _selected_video_assessment(video_evidence_assessment)
    raw_youtube_id = talk.get("youtube_id")
    bound_youtube_id = (
        raw_youtube_id
        if isinstance(raw_youtube_id, str) and _YOUTUBE_ID.fullmatch(raw_youtube_id)
        else None
    )
    predeclared_video_path, predeclared_video_reason = _local_video_binding(
        vault_root, talk, bound_youtube_id
    )
    predeclared_video_duration: float | None = None
    predeclared_video_probe: VideoArtifactProbe | None = None
    predeclared_video_error: VideoEvidenceError | None = None
    if predeclared_video_path is not None:
        try:
            predeclared_video_probe = selected_video_assessment.probe(
                predeclared_video_path,
                trusted_root=_canonical_video_root(vault_root),
            )
        except VideoEvidenceError as exc:
            predeclared_video_error = exc
            predeclared_video_reason = _video_failure_reason(exc)
        else:
            predeclared_video_duration = predeclared_video_probe.duration_seconds

    transcript_text: str | None = None
    transcript_policy_bound = False
    canonical_transcript_source: str | None = None
    recorded_transcript_source = talk.get("transcript_source")
    if recorded_transcript_source in {"youtube_auto", "whisper", "manual"}:
        canonical_transcript_source = cast(str, recorded_transcript_source)
    timing_owner_source = canonical_transcript_source or "unknown"
    timing_owner_duration = _catalog_duration(talk)
    if timing_owner_duration is None:
        timing_owner_duration = predeclared_video_duration
    timing_owner_media_sha256 = (
        predeclared_video_probe.source_sha256
        if predeclared_video_probe is not None
        else None
    )
    timed_segments: list[dict[str, object]] = []
    timing_reason = "timed transcript is unavailable"
    transcript_bundle: _TranscriptBundleSnapshot | None = None
    transcript_path, transcript_reason = resolve_transcript_artifact(vault_root, talk)
    if transcript_path is not None:
        verified_transcript = _load_verified_transcript_snapshot(
            transcript_path,
            talk,
            owner_source=timing_owner_source,
            owner_video_id=bound_youtube_id,
            owner_media_sha256=timing_owner_media_sha256,
            owner_duration_seconds=timing_owner_duration,
            local_media_probe=predeclared_video_probe,
        )
        transcript_text = verified_transcript.text
        transcript_reason = verified_transcript.transcript_reason
        transcript_policy_bound = verified_transcript.policy_bound
        timed_segments = [
            dict(segment) for segment in verified_transcript.timed_segments
        ]
        timing_reason = verified_transcript.timing_reason
        transcript_bundle = verified_transcript.bundle

    transcript_artifact_identity: dict[str, str] = {}
    timing_artifact_identity: dict[str, str] = {}
    quality_artifact_identity: dict[str, str] = {}
    if (
        transcript_text is not None
        and transcript_path is not None
        and transcript_bundle is not None
        and transcript_bundle.transcript_bytes is not None
    ):
        transcript_artifact_identity = _artifact_identity(
            vault_root,
            transcript_path,
            root_kind="vault",
            artifact_sha256=hashlib.sha256(
                transcript_bundle.transcript_bytes
            ).hexdigest(),
        )
        if timed_segments and transcript_bundle.timing_bytes is not None:
            timing_identity = _artifact_identity(
                vault_root,
                sidecar_path(transcript_path),
                root_kind="vault",
                artifact_sha256=hashlib.sha256(
                    transcript_bundle.timing_bytes
                ).hexdigest(),
            )
            timing_artifact_identity = {
                "timing_artifact_root": timing_identity["artifact_root"],
                "timing_artifact_path": timing_identity["artifact_path"],
                "timing_artifact_sha256": timing_identity["artifact_sha256"],
            }
        if transcript_policy_bound and transcript_bundle.quality_bytes is not None:
            quality_identity = _artifact_identity(
                vault_root,
                quality_sidecar_path(transcript_path),
                root_kind="vault",
                artifact_sha256=hashlib.sha256(
                    transcript_bundle.quality_bytes
                ).hexdigest(),
            )
            quality_artifact_identity = {
                "quality_artifact_root": quality_identity["artifact_root"],
                "quality_artifact_path": quality_identity["artifact_path"],
                "quality_artifact_sha256": quality_identity["artifact_sha256"],
            }

    # Citation bounds belong to the exact local artifacts, not authored
    # slide_count metadata (and never to a count supplied by this return).
    slide_counts: dict[str, int] = {}
    slide_artifact_paths: dict[str, Path] = {}
    slide_artifact_roots: dict[str, tuple[Path, str]] = {}
    slide_artifact_sha256s: dict[str, str] = {}
    slide_artifact_probes: dict[str, PdfArtifactProbe | PptxArtifactProbe] = {}
    source_reasons: dict[str, str] = {}
    source_degradations: dict[str, dict[str, object]] = {}
    source_unavailable: dict[str, dict[str, object]] = {}
    if predeclared_video_error is not None:
        source_unavailable["delivery_video"] = _video_unavailable_record(
            predeclared_video_error,
            predeclared_video_path,
        )
    pptx_count: int | None = None
    pdf_count: int | None = None
    pptx_path: Path | None = None
    pdf_path: Path | None = None
    pptx_root = _lexical_absolute(vault_root)
    pdf_root = _canonical_pdf_root(vault_root)
    pptx_root_kind = "vault"
    pdf_root_kind = "vault"
    static_slides_absence_complete = False
    if _nonempty(talk.get("pptx_path")):
        try:
            pptx_path, pptx_root, pptx_root_kind = _resolve_preclaim_artifact(
                vault_root,
                talk,
                "pptx_path",
                suffix=".pptx",
                source_roots=source_roots,
            )
            pptx_probe = probe_pptx_artifact(
                pptx_path,
                trusted_root=pptx_root,
            )
            pptx_count = pptx_probe.slide_count
            if pptx_probe.archive_recovery:
                recovered_parts = sorted(
                    str(item.get("part_name", "<unknown>"))
                    for item in pptx_probe.archive_recovery
                )
                source_reasons["native_deck"] = (
                    f"read degraded local PPTX {pptx_path}; recovery "
                    f"placeholders used for {', '.join(recovered_parts)}"
                )
                source_degradations["native_deck"] = {
                    "schema_version": 1,
                    "status": "degraded_recoverable",
                    "reason_code": "pptx_archive_recovery_required",
                    "source_artifact_sha256": pptx_probe.source_sha256,
                    "source_artifact_size_bytes": pptx_probe.source_size_bytes,
                    "extraction_schema_version": PPTX_EXTRACTION_SCHEMA_VERSION,
                    "extraction_pipeline_version": PPTX_EXTRACTION_PIPELINE_VERSION,
                    "archive_recovery": [
                        copy.deepcopy(item) for item in pptx_probe.archive_recovery
                    ],
                }
            else:
                slide_counts["native_deck"] = pptx_count
                slide_artifact_paths["native_deck"] = pptx_path
                slide_artifact_roots["native_deck"] = (
                    pptx_root,
                    pptx_root_kind,
                )
                slide_artifact_sha256s["native_deck"] = pptx_probe.source_sha256
                slide_artifact_probes["native_deck"] = pptx_probe
                source_reasons["native_deck"] = f"read local PPTX {pptx_path}"
        except PptxEvidenceError as exc:
            source_reasons["native_deck"] = str(exc)
            source_unavailable["native_deck"] = {
                "schema_version": 1,
                "status": "unavailable",
                "reason_code": exc.reason_code,
                "reason": str(exc),
                "details": copy.deepcopy(exc.details),
                "artifact_path": str(pptx_path) if pptx_path is not None else None,
            }
        except PatternEvidenceError as exc:
            source_reasons["native_deck"] = str(exc)
    else:
        source_reasons["native_deck"] = "no predeclared local pptx_path"

    declared_pdf = _declared_pdf_path(talk)
    if declared_pdf is not None:
        pdf_field, pdf_value = declared_pdf
        try:
            if pdf_field == "google_drive_id":
                pdf_root = _canonical_pdf_root(vault_root)
                pdf_root_kind = "vault"
                pdf_path = _resolve_local_pdf_artifact(
                    pdf_root,
                    pdf_value,
                    label="google_drive_id-derived slide PDF",
                )
            else:
                pdf_path, pdf_root, pdf_root_kind = _resolve_preclaim_artifact(
                    vault_root,
                    talk,
                    pdf_field,
                    suffix=".pdf",
                    source_roots=source_roots,
                )
            pdf_probe = probe_pdf_artifact(pdf_path, trusted_root=pdf_root)
            pdf_count = pdf_probe.page_count
            slide_artifact_sha256s["static_slides"] = pdf_probe.source_sha256
            slide_artifact_probes["static_slides"] = pdf_probe
            source_reasons["static_slides"] = f"read local PDF {pdf_path}"
        except PdfEvidenceError as exc:
            source_reasons["static_slides"] = str(exc)
            source_unavailable["static_slides"] = {
                "schema_version": 1,
                "status": "unavailable",
                "reason_code": exc.reason_code,
                "reason": str(exc),
                "details": copy.deepcopy(exc.details),
                "artifact_path": str(pdf_path) if pdf_path is not None else None,
            }
        except PatternEvidenceError as exc:
            source_reasons["static_slides"] = str(exc)

    slide_source = talk.get("slide_source")
    if slide_source == "video_extracted":
        # A predeclared PDF is not interchangeable with the manifest-selected
        # video extraction. Bind path/count/digest together below, or leave the
        # static-slide lane unavailable without disturbing independent sources.
        slide_artifact_sha256s.pop("static_slides", None)
        slide_artifact_probes.pop("static_slides", None)
        youtube_id = talk.get("youtube_id")
        if isinstance(youtube_id, str) and _YOUTUBE_ID.fullmatch(youtube_id):
            video_slide_path: Path | None = None
            try:
                video_probe, video_slide_reason, video_slide_path = (
                    _trusted_video_slide_probe(
                        vault_root,
                        talk,
                        youtube_id,
                        source_video_probe=predeclared_video_probe,
                        video_evidence_assessment=selected_video_assessment,
                    )
                )
            except PdfEvidenceError as exc:
                source_reasons["static_slides"] = str(exc)
                source_unavailable["static_slides"] = {
                    "schema_version": 1,
                    "status": "unavailable",
                    "reason_code": exc.reason_code,
                    "reason": str(exc),
                    "details": copy.deepcopy(exc.details),
                    "artifact_path": (
                        str(video_slide_path) if video_slide_path is not None else None
                    ),
                }
            else:
                source_reasons["static_slides"] = video_slide_reason
                if video_probe is not None and video_slide_path is not None:
                    source_unavailable.pop("static_slides", None)
                    slide_counts["static_slides"] = video_probe.page_count
                    slide_artifact_paths["static_slides"] = video_slide_path
                    slide_artifact_roots["static_slides"] = (
                        _canonical_pdf_root(vault_root),
                        "vault",
                    )
                    slide_artifact_sha256s["static_slides"] = video_probe.source_sha256
                    slide_artifact_probes["static_slides"] = video_probe
                elif declared_pdf is None and talk.get("status") != "processed_partial":
                    expected_path = _resolve_local_pdf_artifact(
                        _canonical_pdf_root(vault_root),
                        f"slides/{youtube_id}.pdf",
                        label="youtube_id-derived video slide PDF",
                    )
                    try:
                        probe_pdf_artifact(
                            expected_path,
                            trusted_root=_canonical_pdf_root(vault_root),
                        )
                    except PdfEvidenceError as exc:
                        source_unavailable["static_slides"] = {
                            "schema_version": 1,
                            "status": "unavailable",
                            "reason_code": exc.reason_code,
                            "reason": str(exc),
                            "details": copy.deepcopy(exc.details),
                            "artifact_path": str(expected_path),
                        }
            static_slides_absence_complete = False
        else:
            source_reasons["static_slides"] = (
                "video-extracted slides have no valid pre-return youtube_id"
            )
    elif slide_source == "pdf":
        if pdf_count is not None:
            static_slides_absence_complete = True
            slide_counts["static_slides"] = pdf_count
            if pdf_path is not None:
                slide_artifact_paths["static_slides"] = pdf_path
                slide_artifact_roots["static_slides"] = (pdf_root, pdf_root_kind)
    elif slide_source == "pptx":
        if pdf_count is not None:
            # A PPTX never aliases to static slides. Preserve a separately
            # declared, readable PDF when one really exists, however: it is a
            # distinct artifact with its own identity and inspection receipt.
            slide_counts["static_slides"] = pdf_count
            static_slides_absence_complete = True
            if pdf_path is not None:
                slide_artifact_paths["static_slides"] = pdf_path
                slide_artifact_roots["static_slides"] = (pdf_root, pdf_root_kind)
        else:
            source_reasons["static_slides"] = (
                "a readable native PPTX is not a rendered static-slide artifact"
            )
    elif slide_source == "both":
        if pdf_count is not None:
            static_slides_absence_complete = True
            slide_counts["static_slides"] = pdf_count
            if pdf_path is not None:
                slide_artifact_paths["static_slides"] = pdf_path
                slide_artifact_roots["static_slides"] = (pdf_root, pdf_root_kind)
    elif pdf_count is not None and pptx_count is None:
        static_slides_absence_complete = True
        slide_counts["static_slides"] = pdf_count
        if pdf_path is not None:
            slide_artifact_paths["static_slides"] = pdf_path
            slide_artifact_roots["static_slides"] = (pdf_root, pdf_root_kind)
    elif pptx_count is not None and pdf_count is None:
        source_reasons["static_slides"] = (
            "a readable native PPTX is not a rendered static-slide artifact"
        )
    elif pptx_count is not None and pdf_count is not None:
        static_slides_absence_complete = True
        slide_counts["static_slides"] = pdf_count
        if pdf_path is not None:
            slide_artifact_paths["static_slides"] = pdf_path
            slide_artifact_roots["static_slides"] = (pdf_root, pdf_root_kind)
    else:
        source_reasons.setdefault(
            "static_slides", "no predeclared readable local slide artifact"
        )

    current_video_path: Path | None = None
    current_video_probe: VideoArtifactProbe | None = None
    if isinstance(ret, Mapping):
        try:
            (
                returned_probe,
                returned_reason,
                returned_slide_path,
                current_video_path,
                current_video_probe,
            ) = _returned_slide_artifact(
                vault_root,
                talk,
                ret,
                video_evidence_assessment=selected_video_assessment,
            )
        except PdfEvidenceError as exc:
            raise PatternEvidenceError(
                f"cannot inspect returned static slides: {exc}"
            ) from exc
        returned_source = ret.get("slide_source")
        if returned_probe is not None:
            if returned_slide_path is None:
                raise PatternEvidenceError(
                    "returned static-slide probe has no identity-bound PDF path"
                )
            static_slides_absence_complete = returned_source in {"pdf", "both"}
            slide_counts["static_slides"] = returned_probe.page_count
            source_reasons["static_slides"] = returned_reason
            slide_artifact_paths["static_slides"] = returned_slide_path
            slide_artifact_roots["static_slides"] = (
                _canonical_pdf_root(vault_root),
                "vault",
            )
            slide_artifact_sha256s["static_slides"] = returned_probe.source_sha256
            slide_artifact_probes["static_slides"] = returned_probe
            source_unavailable.pop("static_slides", None)
        elif returned_source in {"pdf", "both", "video_extracted"}:
            # No explicit current-run artifact assertion: retain any verified
            # preclaim artifact instead of silently deleting its capability.
            source_reasons.setdefault("static_slides", returned_reason)

    metadata = {
        field: copy.deepcopy(talk[field])
        for field in TALK_METADATA_FIELDS
        if field in talk and _nonempty(talk[field])
    }
    delivery_language = talk.get("delivery_language")
    if not isinstance(delivery_language, str) or not delivery_language.strip():
        returned_structured = (
            ret.get("structured_data") if isinstance(ret, Mapping) else None
        )
        returned_language = (
            returned_structured.get("delivery_language")
            if isinstance(returned_structured, Mapping)
            else None
        )
        delivery_language = (
            returned_language
            if isinstance(returned_language, str) and returned_language.strip()
            else None
        )
    video_duration: float | None = None
    video_artifact_bound = False
    video_timing_bound = False
    video_binding_reason = "no identity-bound timed video artifact"
    local_video_path = current_video_path or predeclared_video_path
    local_video_reason = (
        f"identity-bound current-return source video {current_video_path}"
        if current_video_path is not None
        else predeclared_video_reason
    )
    video_probe = current_video_probe or predeclared_video_probe
    if local_video_path is not None or bound_youtube_id is not None:
        if local_video_path is not None:
            if video_probe is not None:
                probed_duration = video_probe.duration_seconds
                identity_duration = (
                    _identity_duration(talk, bound_youtube_id)
                    if bound_youtube_id is not None
                    else None
                )
                tolerance = (
                    max(60.0, identity_duration * 0.05)
                    if identity_duration is not None
                    else None
                )
                if (
                    identity_duration is not None
                    and tolerance is not None
                    and abs(probed_duration - identity_duration) > tolerance
                ):
                    video_binding_reason = (
                        "local video duration disagrees with identity-bound "
                        "provider duration"
                    )
                else:
                    video_duration = probed_duration
                    video_artifact_bound = True
                    video_binding_reason = local_video_reason
                    source_unavailable.pop("delivery_video", None)
            elif video_binding_reason == "no identity-bound timed video artifact":
                video_binding_reason = local_video_reason
        elif local_video_reason:
            video_binding_reason = local_video_reason
    verified_sources = set(slide_counts)
    if transcript_text is not None:
        verified_sources.add("transcript")
        source_reasons["transcript"] = transcript_reason
    else:
        source_reasons["transcript"] = transcript_reason
    if video_artifact_bound and video_duration is not None:
        verified_sources.add("delivery_video")
        source_reasons["delivery_video"] = video_binding_reason
    else:
        source_reasons["delivery_video"] = video_binding_reason
    # Readability is enough for positive evidence, not negative modality
    # claims. Bare native-package identity and a full-duration video receipt do
    # not prove screen/audience/audio or session-boundary capture.
    absence_complete_sources = set(verified_sources) - {"native_deck", "delivery_video"}
    if not static_slides_absence_complete:
        # Schema-v3 extraction proves crop/artifact identity and supports
        # positive citations. Its frame sampling, transition filtering, and
        # deduplication do not prove an exhaustive delivered visual inventory,
        # so a fully inspected extracted PDF is not absence-complete.
        absence_complete_sources.discard("static_slides")
    absence_capability_reasons: dict[str, str] = {}
    if "transcript" in verified_sources:
        absence_capability_reasons["transcript"] = (
            ABSENCE_CAPABILITY_AUTHORIZED_TRANSCRIPT
        )
    if "static_slides" in verified_sources:
        absence_capability_reasons["static_slides"] = (
            ABSENCE_CAPABILITY_AUTHORIZED_STATIC
            if static_slides_absence_complete
            else ABSENCE_CAPABILITY_NONEXHAUSTIVE_VIDEO
        )
    if "native_deck" in verified_sources:
        absence_capability_reasons["native_deck"] = ABSENCE_CAPABILITY_BARE_NATIVE
    if "delivery_video" in verified_sources:
        absence_capability_reasons["delivery_video"] = ABSENCE_CAPABILITY_BARE_VIDEO
    # Artifact coexistence is not comparison work. `source_comparison` is added
    # only after a receipt-bound inspection record is canonicalized.

    slide_artifact_identities = {}
    for source, path in slide_artifact_paths.items():
        root, root_kind = slide_artifact_roots.get(
            source,
            (_native_artifact_root(vault_root, label="vault_root"), "vault"),
        )
        slide_artifact_identities[source] = _artifact_identity(
            root,
            path,
            root_kind=root_kind,
            artifact_sha256=slide_artifact_sha256s.get(source),
            lexical=source in {"native_deck", "static_slides"},
        )
    video_artifact_identity: dict[str, str] = {}
    if (
        video_artifact_bound
        and local_video_path is not None
        and video_probe is not None
    ):
        try:
            video_artifact_identity.update(
                _artifact_identity(
                    _canonical_video_root(vault_root),
                    local_video_path,
                    root_kind="vault",
                    artifact_sha256=video_probe.source_sha256,
                    lexical=True,
                )
            )
        except PatternEvidenceError as exc:
            # A video that cannot be identity-bound is unavailable video
            # evidence, not a reason to erase an independent transcript/deck.
            video_artifact_bound = False
            video_timing_bound = False
            video_duration = None
            video_binding_reason = f"cannot bind local video artifact identity: {exc}"
            verified_sources.discard("delivery_video")
            source_reasons["delivery_video"] = video_binding_reason

    return {
        "transcript_text": transcript_text,
        "transcript_reason": transcript_reason,
        "canonical_transcript_source": canonical_transcript_source,
        "timed_segments": timed_segments,
        "timing_reason": timing_reason,
        "slide_counts": slide_counts,
        "slide_artifact_paths": slide_artifact_paths,
        "slide_artifact_roots": slide_artifact_roots,
        "slide_artifact_probes": slide_artifact_probes,
        "transcript_path": transcript_path,
        "transcript_line_count": (
            len(transcript_text.splitlines()) if transcript_text is not None else None
        ),
        "local_video_path": local_video_path,
        "video_artifact_probe": video_probe,
        "transcript_artifact_identity": transcript_artifact_identity,
        "timing_artifact_identity": timing_artifact_identity,
        "quality_artifact_identity": quality_artifact_identity,
        "slide_artifact_identities": slide_artifact_identities,
        "video_artifact_identity": video_artifact_identity,
        "video_duration_seconds": video_duration,
        "video_artifact_bound": video_artifact_bound,
        "video_timing_bound": video_timing_bound,
        "video_binding_reason": video_binding_reason,
        "verified_evidence_sources": verified_sources,
        "absence_complete_evidence_sources": absence_complete_sources,
        "absence_capability_reasons": absence_capability_reasons,
        "source_reasons": source_reasons,
        "degraded_evidence_sources": source_degradations,
        "unavailable_evidence_sources": source_unavailable,
        "metadata": metadata,
        "delivery_language": delivery_language,
    }


def assess_talk_artifact_capabilities(
    talk: Mapping[str, object],
    *,
    vault_root: str | Path,
    source_roots: Mapping[str, object] | None = None,
    video_evidence_assessment: VideoEvidenceAssessment | None = None,
) -> dict[str, object]:
    """Return root-aware verified-local vs acquisition capabilities.

    This is the shared queue/terminal-state boundary. A nonempty path string is
    never a verified capability; the same parsers and quality checks used by
    canonical evidence must successfully open the artifact.
    """
    context: dict[str, object] | None = None
    contract_error: str | None = None
    selected_video_assessment = _selected_video_assessment(video_evidence_assessment)
    try:
        context = build_evidence_context(
            vault_root,
            talk,
            source_roots=source_roots,
            video_evidence_assessment=selected_video_assessment,
        )
    except PatternEvidenceError as exc:
        # Transcript identity/path errors are intentionally fail-closed for the
        # transcript, but they must not erase an independent deck/video. Retry
        # without the malformed transcript declaration and discard any fallback
        # transcript capability while retaining every other verified source.
        contract_error = str(exc)
        isolated_talk = dict(talk)
        isolated_talk.pop("transcript_path", None)
        raw_youtube_id = isolated_talk.get("youtube_id")
        if (
            not isinstance(raw_youtube_id, str)
            or _YOUTUBE_ID.fullmatch(raw_youtube_id) is None
        ):
            isolated_talk.pop("youtube_id", None)
        try:
            context = build_evidence_context(
                vault_root,
                isolated_talk,
                source_roots=source_roots,
                video_evidence_assessment=selected_video_assessment,
            )
        except PatternEvidenceError as isolated_exc:
            verified_sources = set()
            source_reasons = {
                "artifact_contract": contract_error,
                "isolated_artifact_contract": str(isolated_exc),
            }
            context = None
        else:
            raw_verified = context.get("verified_evidence_sources")
            verified_sources = (
                set(raw_verified)
                if isinstance(raw_verified, (set, frozenset))
                else set()
            )
            verified_sources.discard("transcript")
            raw_reasons = context.get("source_reasons")
            source_reasons = (
                {str(key): str(value) for key, value in raw_reasons.items()}
                if isinstance(raw_reasons, Mapping)
                else {}
            )
            source_reasons["transcript"] = contract_error
    else:
        raw_verified = context.get("verified_evidence_sources")
        verified_sources = (
            set(raw_verified) if isinstance(raw_verified, (set, frozenset)) else set()
        )
        raw_reasons = context.get("source_reasons")
        source_reasons = (
            {str(key): str(value) for key, value in raw_reasons.items()}
            if isinstance(raw_reasons, Mapping)
            else {}
        )
    verified_capabilities: set[str] = set()
    if "transcript" in verified_sources:
        verified_capabilities.add("transcript")
    if verified_sources.intersection({"static_slides", "native_deck"}):
        verified_capabilities.add("slides")
    if "delivery_video" in verified_sources:
        verified_capabilities.add("video")

    acquisitions: set[str] = set()
    repairs: set[str] = set()
    if has_remote_video_acquisition(dict(talk)):
        acquisitions.update({"video", "transcript"})
    if has_remote_slide_acquisition(dict(talk)):
        acquisitions.add("slides")
    # A registered local transcript that merely lacks or fails its current
    # receipt is repairable work, not proof that the talk has no sources. Keep
    # it out of verified capabilities while ensuring terminal-state validation
    # sends it back through acquisition/receipt repair.
    transcript_candidate = (
        context.get("transcript_path") if isinstance(context, Mapping) else None
    )
    if (
        contract_error is None
        and isinstance(transcript_candidate, Path)
        and transcript_candidate.is_file()
    ):
        if "transcript" not in verified_capabilities:
            try:
                candidate_text = transcript_candidate.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                pass
            else:
                repairable, _ = validate_transcript(candidate_text)
                if repairable:
                    repairs.add("transcript")
    youtube_id = talk.get("youtube_id")
    if isinstance(youtube_id, str) and _YOUTUBE_ID.fullmatch(youtube_id):
        acquisitions.add("transcript")
    raw_degradations = (
        context.get("degraded_evidence_sources")
        if isinstance(context, Mapping)
        else None
    )
    degraded_sources = (
        {
            str(source): copy.deepcopy(dict(details))
            for source, details in raw_degradations.items()
            if isinstance(details, Mapping)
        }
        if isinstance(raw_degradations, Mapping)
        else {}
    )
    raw_unavailable = (
        context.get("unavailable_evidence_sources")
        if isinstance(context, Mapping)
        else None
    )
    unavailable_sources = (
        {
            str(source): copy.deepcopy(dict(details))
            for source, details in raw_unavailable.items()
            if isinstance(details, Mapping)
        }
        if isinstance(raw_unavailable, Mapping)
        else {}
    )
    return {
        "verified_capabilities": tuple(sorted(verified_capabilities)),
        "verified_evidence_sources": tuple(sorted(verified_sources)),
        "acquisition_capabilities": tuple(sorted(acquisitions)),
        "repair_capabilities": tuple(sorted(repairs)),
        "source_reasons": source_reasons,
        "degraded_evidence_sources": degraded_sources,
        "unavailable_evidence_sources": unavailable_sources,
    }


def required_pptx_evidence_blocking_reason(
    talk: Mapping[str, object],
    assessment: Mapping[str, object],
    *,
    native_deck_used: bool = False,
) -> str | None:
    """Explain why degraded mandatory native evidence blocks current work."""
    if talk.get("slide_source") not in {"pptx", "both"} and not native_deck_used:
        return None
    raw_degradations = assessment.get("degraded_evidence_sources")
    native = (
        raw_degradations.get("native_deck")
        if isinstance(raw_degradations, Mapping)
        else None
    )
    if not isinstance(native, Mapping):
        return None
    raw_recovery = native.get("archive_recovery")
    parts = (
        sorted(
            str(item.get("part_name", "<unknown>"))
            for item in raw_recovery
            if isinstance(item, Mapping)
        )
        if isinstance(raw_recovery, list)
        else []
    )
    suffix = f"; damaged members: {', '.join(parts)}" if parts else ""
    return (
        "native_deck is degraded by placeholder archive recovery and cannot "
        f"authorize a current claim or analysis{suffix}; restore or re-export "
        "the PPTX first"
    )


def assess_batch_artifact_capabilities(
    talks: Iterable[object],
    filenames: Collection[str],
    *,
    vault_root: str | Path,
    source_roots: Mapping[str, object] | None = None,
    video_evidence_assessment: VideoEvidenceAssessment | None = None,
) -> dict[str, dict[str, object]]:
    """Assess only talks named by one supplied return batch."""
    selected_video_assessment = _selected_video_assessment(video_evidence_assessment)
    requested = set(filenames)
    assessed: dict[str, dict[str, object]] = {}
    for talk in talks:
        if not isinstance(talk, Mapping):
            continue
        filename = talk.get("filename")
        if not isinstance(filename, str) or filename not in requested:
            continue
        assessed[filename] = assess_talk_artifact_capabilities(
            talk,
            vault_root=vault_root,
            source_roots=source_roots,
            video_evidence_assessment=selected_video_assessment,
        )
    return assessed


def _validate_discrete_ranges(
    value: object,
    *,
    upper: int,
    label: str,
) -> tuple[list[list[int]], bool]:
    if not isinstance(value, list) or not value:
        raise PatternEvidenceError(f"{label} must be a non-empty array")
    normalized: list[list[int]] = []
    prior_end = 0
    for index, raw_range in enumerate(value):
        if (
            not isinstance(raw_range, list)
            or len(raw_range) != 2
            or any(
                isinstance(item, bool) or not isinstance(item, int)
                for item in raw_range
            )
        ):
            raise PatternEvidenceError(
                f"{label}[{index}] must be [start, end] integers"
            )
        start, end = raw_range
        if start < 1 or end < start or end > upper or start <= prior_end:
            raise PatternEvidenceError(
                f"{label}[{index}] must be an ascending, non-overlapping range "
                f"inside 1..{upper}"
            )
        normalized.append([start, end])
        prior_end = end
    complete = normalized[0][0] == 1 and normalized[-1][1] == upper
    complete = complete and all(
        right[0] == left[1] + 1 for left, right in zip(normalized, normalized[1:])
    )
    return normalized, complete


def _validate_time_ranges(
    value: object,
    *,
    duration: float,
) -> tuple[list[list[float]], bool]:
    if not isinstance(value, list) or not value:
        raise PatternEvidenceError("time_ranges must be a non-empty array")
    normalized: list[list[float]] = []
    epsilon = 0.001
    prior_end = -1.0
    for index, raw_range in enumerate(value):
        if (
            not isinstance(raw_range, list)
            or len(raw_range) != 2
            or any(not _nonnegative_number(item) for item in raw_range)
        ):
            raise PatternEvidenceError(
                f"time_ranges[{index}] must be finite [start, end] seconds"
            )
        start = float(cast(int | float, raw_range[0]))
        end = float(cast(int | float, raw_range[1]))
        if end <= start or start < prior_end or end > duration + epsilon:
            raise PatternEvidenceError(
                f"time_ranges[{index}] must be ascending, non-overlapping, "
                f"and inside the verified {duration:.3f}-second duration"
            )
        normalized.append([start, end])
        prior_end = end
    complete = normalized[0][0] <= epsilon and normalized[-1][1] >= duration - epsilon
    complete = complete and all(
        right[0] <= left[1] + epsilon for left, right in zip(normalized, normalized[1:])
    )
    return normalized, complete


def canonicalize_source_inspection(
    raw_inspection: object,
    context: Mapping[str, object],
) -> tuple[
    list[dict[str, object]],
    set[str],
    set[frozenset[str]],
]:
    """Bind worker inspection coverage to exact local artifact identities."""
    if not isinstance(raw_inspection, list) or not raw_inspection:
        raise PatternEvidenceError(
            "current pattern observations require non-empty source_inspection"
        )
    records: list[dict[str, object]] = []
    by_source: dict[str, dict[str, object]] = {}
    range_complete_sources: set[str] = set()
    complete_sources: set[str] = set()
    comparison_groups: set[frozenset[str]] = set()
    seen_comparison_groups: set[frozenset[str]] = set()
    verified = context.get("verified_evidence_sources")
    verified_sources = (
        set(verified) if isinstance(verified, (set, frozenset)) else set()
    )
    absence_complete = context.get("absence_complete_evidence_sources")
    absence_complete_sources = (
        set(absence_complete)
        if isinstance(absence_complete, (set, frozenset))
        else set(verified_sources) - {"native_deck", "delivery_video"}
    )
    slide_counts = context.get("slide_counts")
    slide_identities = context.get("slide_artifact_identities")
    raw_absence_reasons = context.get("absence_capability_reasons")
    absence_reasons = (
        raw_absence_reasons if isinstance(raw_absence_reasons, Mapping) else {}
    )

    # Underlying records are resolved first so a comparison can bind itself to
    # the exact digests and coverage records it claims to compare.
    for index, raw in enumerate(raw_inspection):
        if not isinstance(raw, Mapping):
            raise PatternEvidenceError(f"source_inspection[{index}] must be an object")
        source = raw.get("source")
        if not isinstance(source, str) or source not in SOURCE_INSPECTION_RAW_FIELDS:
            raise PatternEvidenceError(
                f"source_inspection[{index}].source is unsupported: {source!r}"
            )
        if source != "source_comparison" and source in by_source:
            raise PatternEvidenceError(
                f"source_inspection contains duplicate source {source!r}"
            )
        unknown = sorted(set(raw) - SOURCE_INSPECTION_RAW_FIELDS[source])
        if unknown:
            raise PatternEvidenceError(
                f"source_inspection[{index}] has unknown worker fields {unknown}"
            )
        if source == "source_comparison":
            continue
        if source not in verified_sources:
            reasons = context.get("source_reasons")
            reason = reasons.get(source) if isinstance(reasons, Mapping) else None
            raise PatternEvidenceError(
                f"source_inspection claims unavailable source {source!r}: {reason}"
            )

        canonical = copy.deepcopy(dict(raw))
        if source == "transcript":
            line_count = context.get("transcript_line_count")
            raw_identity = context.get("transcript_artifact_identity")
            identity = (
                copy.deepcopy(dict(raw_identity))
                if isinstance(raw_identity, Mapping)
                else {}
            )
            policy_identity = context.get("quality_artifact_identity")
            if isinstance(policy_identity, Mapping):
                identity.update(copy.deepcopy(dict(policy_identity)))
            if (
                isinstance(line_count, bool)
                or not isinstance(line_count, int)
                or line_count < 1
            ):
                raise PatternEvidenceError(
                    "transcript inspection has no verified transcript line count"
                )
            ranges, complete = _validate_discrete_ranges(
                raw.get("line_ranges"), upper=line_count, label="line_ranges"
            )
            canonical["line_ranges"] = ranges
            canonical["line_count"] = line_count
        elif source in {"static_slides", "native_deck"}:
            count = (
                slide_counts.get(source) if isinstance(slide_counts, Mapping) else None
            )
            identity = (
                slide_identities.get(source)
                if isinstance(slide_identities, Mapping)
                else None
            )
            if isinstance(count, bool) or not isinstance(count, int) or count < 1:
                raise PatternEvidenceError(
                    f"{source} inspection has no verified page/slide count"
                )
            ranges, complete = _validate_discrete_ranges(
                raw.get("page_ranges"), upper=count, label="page_ranges"
            )
            canonical["page_ranges"] = ranges
            canonical["page_count"] = count
        else:
            duration = context.get("video_duration_seconds")
            identity = context.get("video_artifact_identity")
            if (
                isinstance(duration, bool)
                or not isinstance(duration, (int, float))
                or not math.isfinite(float(duration))
                or float(duration) <= 0
            ):
                raise PatternEvidenceError(
                    "delivery_video inspection has no verified duration"
                )
            ranges, complete = _validate_time_ranges(
                raw.get("time_ranges"), duration=float(duration)
            )
            canonical["time_ranges"] = ranges
            canonical["duration_seconds"] = float(duration)
        if not isinstance(identity, Mapping) or not identity:
            raise PatternEvidenceError(
                f"source_inspection source {source!r} has no artifact identity"
            )
        canonical.update(copy.deepcopy(dict(identity)))
        canonical["coverage_complete"] = complete
        default_absence_reason = {
            "transcript": ABSENCE_CAPABILITY_AUTHORIZED_TRANSCRIPT,
            "static_slides": ABSENCE_CAPABILITY_AUTHORIZED_STATIC,
            "native_deck": ABSENCE_CAPABILITY_BARE_NATIVE,
            "delivery_video": ABSENCE_CAPABILITY_BARE_VIDEO,
        }[source]
        source_absence_reason = absence_reasons.get(source, default_absence_reason)
        absence_capability_complete = complete and source in absence_complete_sources
        canonical["absence_capability_complete"] = absence_capability_complete
        canonical["absence_capability_reason"] = (
            source_absence_reason if complete else ABSENCE_CAPABILITY_INCOMPLETE_RANGES
        )
        records.append(canonical)
        by_source[source] = canonical
        if complete:
            range_complete_sources.add(source)
            if source in absence_complete_sources:
                complete_sources.add(source)

    for index, raw in enumerate(raw_inspection):
        if not isinstance(raw, Mapping) or raw.get("source") != "source_comparison":
            continue
        used = raw.get("evidence_sources_used")
        if (
            not isinstance(used, list)
            or len(used) < 2
            or any(source not in INSPECTABLE_EVIDENCE_SOURCES for source in used)
            or len(used) != len(set(used))
            or not set(used).intersection(
                {"static_slides", "native_deck", "delivery_video"}
            )
        ):
            raise PatternEvidenceError(
                "source_comparison inspection requires at least two duplicate-free "
                "underlying sources including a visual source"
            )
        missing = [source for source in used if source not in by_source]
        if missing:
            raise PatternEvidenceError(
                "source_comparison inspection has no underlying inspection for "
                f"{missing}"
            )
        scope = raw.get("comparison_scope")
        if scope not in {"full", "partial"}:
            raise PatternEvidenceError(
                "source_comparison comparison_scope must be 'full' or 'partial'"
            )
        used_group = frozenset(used)
        if used_group in seen_comparison_groups:
            raise PatternEvidenceError(
                "source_inspection contains duplicate source_comparison group "
                f"{sorted(used_group)}"
            )
        seen_comparison_groups.add(used_group)
        canonical = copy.deepcopy(dict(raw))
        canonical["artifact_identities"] = [
            {
                "source": source,
                **{
                    key: copy.deepcopy(value)
                    for key, value in by_source[source].items()
                    if key
                    in {
                        "artifact_root",
                        "artifact_path",
                        "artifact_sha256",
                        "timing_artifact_root",
                        "timing_artifact_path",
                        "timing_artifact_sha256",
                        "quality_artifact_root",
                        "quality_artifact_path",
                        "quality_artifact_sha256",
                    }
                },
            }
            for source in used
        ]
        complete = scope == "full" and all(
            source in range_complete_sources for source in used
        )
        canonical["coverage_complete"] = complete
        canonical["absence_capability_complete"] = False
        canonical["absence_capability_reason"] = (
            ABSENCE_CAPABILITY_COMPARISON_UNVERIFIED
        )
        records.append(canonical)
        # Range-complete comparison supports positive claims, but does not
        # prove aligned modality capture. Until a canonical alignment/modality
        # receipt exists, it cannot authorize absence or force applicability.
    return records, complete_sources, comparison_groups


def _range_contains(
    ranges: object, start: int | float, end: int | float, *, discrete: bool
) -> bool:
    if not isinstance(ranges, list):
        return False
    if discrete:
        next_required = int(start)
        target = int(end)
        for item in ranges:
            if (
                not isinstance(item, list)
                or len(item) != 2
                or not all(
                    isinstance(value, int) and not isinstance(value, bool)
                    for value in item
                )
            ):
                return False
            item_start, item_end = item
            if item_end < next_required:
                continue
            if item_start > next_required:
                return False
            next_required = max(next_required, item_end + 1)
            if next_required > target:
                return True
        return False
    cursor = float(start)
    target = float(end)
    tolerance = 0.001
    for item in ranges:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or not all(isinstance(value, (int, float)) for value in item)
        ):
            return False
        item_start, item_end = float(item[0]), float(item[1])
        if item_end < cursor:
            continue
        if item_start > cursor + tolerance:
            return False
        cursor = max(cursor, item_end)
        if cursor >= target:
            return True
    return False


def _require_citations_within_inspection(
    detection: Mapping[str, object],
    inspection: list[dict[str, object]],
) -> None:
    by_source = {
        item.get("source"): item
        for item in inspection
        if item.get("source") != "source_comparison"
    }
    if detection.get("evidence_source") == "source_comparison":
        raw_group = detection.get("evidence_sources_used")
        if not isinstance(raw_group, list) or not all(
            isinstance(source, str) for source in raw_group
        ):
            raise PatternEvidenceError(
                "comparison detection has no valid evidence_sources_used"
            )
        group = frozenset(raw_group)
        comparison_matches = [
            item
            for item in inspection
            if item.get("source") == "source_comparison"
            and isinstance(item.get("evidence_sources_used"), list)
            and frozenset(cast(list[str], item["evidence_sources_used"])) == group
        ]
        if not comparison_matches:
            raise PatternEvidenceError(
                "comparison detection has no receipt-bound inspection for exact "
                f"group {sorted(group)}"
            )
    citations = detection.get("evidence_citations")
    if not isinstance(citations, list):
        return
    for citation in citations:
        if (
            not isinstance(citation, Mapping)
            or citation.get("channel") == "talk_metadata"
        ):
            continue
        source = citation.get("source")
        record = by_source.get(source)
        if not isinstance(record, Mapping):
            raise PatternEvidenceError(
                f"citation source {source!r} has no underlying inspection record"
            )
        channel = citation.get("channel")
        if channel in {"transcript", "timed_transcript"}:
            covered = _range_contains(
                record.get("line_ranges"),
                cast(int, citation.get("line_start")),
                cast(int, citation.get("line_end")),
                discrete=True,
            )
        elif channel in {"slides", "slide_sequence"}:
            numbers = citation.get("slide_numbers")
            covered = isinstance(numbers, list) and all(
                _range_contains(
                    record.get("page_ranges"), number, number, discrete=True
                )
                for number in numbers
            )
        elif channel == "video":
            covered = _range_contains(
                record.get("time_ranges"),
                cast(float, citation.get("start_seconds")),
                cast(float, citation.get("end_seconds")),
                discrete=False,
            )
        else:
            covered = False
        if not covered:
            raise PatternEvidenceError(
                f"canonical {channel!r} citation falls outside the declared "
                f"inspection ranges for {source!r}"
            )


def _absence_gate_satisfied(
    gate: object,
    complete_sources: set[str],
    comparison_groups: set[frozenset[str]],
) -> bool:
    if not isinstance(gate, tuple):
        return False
    return any(
        (len(group) == 1 and next(iter(group)) in complete_sources)
        or (len(group) > 1 and group in comparison_groups)
        for group in gate
    )


def _claim_uses_complete_gate(
    claim: Mapping[str, object],
    gate: object,
    complete_sources: set[str],
    comparison_groups: set[frozenset[str]],
) -> bool:
    """Return whether a located claim names one exact, completely inspected gate."""
    if not isinstance(gate, tuple):
        return False
    source = claim.get("evidence_source")
    if source == "source_comparison":
        used = claim.get("evidence_sources_used")
        group = frozenset(used) if isinstance(used, list) else frozenset()
        return len(group) > 1 and group in gate and group in comparison_groups
    return (
        isinstance(source, str)
        and source in complete_sources
        and frozenset({source}) in gate
    )


def opportunity_coverage_identity(
    pattern_outcomes: object,
    *,
    pattern_catalog_fingerprint: object,
    pattern_scoring_schema_version: object,
) -> str:
    """Hash the exact opportunity denominator used by raw-score comparisons.

    Detected and undetected both represent one evaluable opportunity. The two
    non-comparable states remain distinct so no consumer can normalize across a
    missing evidence opportunity or a catalog-authorized inapplicable one.
    """
    if (
        not isinstance(pattern_catalog_fingerprint, str)
        or re.fullmatch(r"[0-9a-f]{64}", pattern_catalog_fingerprint) is None
    ):
        raise PatternEvidenceError(
            "opportunity identity requires a lowercase catalog fingerprint"
        )
    if (
        isinstance(pattern_scoring_schema_version, bool)
        or not isinstance(pattern_scoring_schema_version, int)
        or pattern_scoring_schema_version < 1
    ):
        raise PatternEvidenceError(
            "opportunity identity requires a positive scoring schema version"
        )
    if not isinstance(pattern_outcomes, list):
        raise PatternEvidenceError("pattern_outcomes must be an array")
    states: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(pattern_outcomes):
        if not isinstance(item, Mapping) or set(item) != {"pattern_id", "outcome"}:
            raise PatternEvidenceError(
                f"pattern_outcomes[{index}] must contain exactly pattern_id/outcome"
            )
        pattern_id = item.get("pattern_id")
        outcome = item.get("outcome")
        if not isinstance(pattern_id, str) or not pattern_id or pattern_id in seen:
            raise PatternEvidenceError(
                f"pattern_outcomes[{index}].pattern_id is empty or duplicated"
            )
        if not isinstance(outcome, str) or outcome not in PATTERN_OUTCOMES:
            raise PatternEvidenceError(
                f"pattern_outcomes[{index}].outcome is invalid: {outcome!r}"
            )
        seen.add(pattern_id)
        states.append(
            {
                "pattern_id": pattern_id,
                "opportunity_state": (
                    "evaluable"
                    if outcome in {"detected", "undetected"}
                    else cast(str, outcome)
                ),
            }
        )
    states.sort(key=lambda item: item["pattern_id"])
    payload = {
        "pattern_scoring_schema_version": pattern_scoring_schema_version,
        "pattern_catalog_fingerprint": pattern_catalog_fingerprint,
        "opportunity_states": states,
    }
    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _nonnegative_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and float(value) >= 0
    )


def _canonicalize_transcript(
    citation: dict[str, object],
    context: Mapping[str, object],
    *,
    timed: bool,
) -> None:
    quote = citation.get("quote")
    if not isinstance(quote, str) or not quote.strip():
        raise PatternEvidenceError(
            "transcript evidence requires a non-empty verbatim quote"
        )
    if len(_WORD.findall(quote)) < MIN_TRANSCRIPT_QUOTE_WORDS:
        raise PatternEvidenceError(
            f"transcript evidence quote {quote!r} has fewer than "
            f"{MIN_TRANSCRIPT_QUOTE_WORDS} words"
        )
    delivery_language = context.get("delivery_language")
    if (
        isinstance(delivery_language, str)
        and delivery_language.split("-", 1)[0].casefold() != "en"
    ):
        translation = citation.get("translation")
        if not isinstance(translation, str) or not translation.strip():
            raise PatternEvidenceError(
                "non-English transcript evidence requires a non-empty English "
                f"translation for delivery_language {delivery_language!r}"
            )
    for field in (
        "line_start",
        "line_end",
        "start_seconds",
        "end_seconds",
        "artifact_root",
        "artifact_path",
        "artifact_sha256",
        "timing_artifact_root",
        "timing_artifact_path",
        "timing_artifact_sha256",
        "quality_artifact_root",
        "quality_artifact_path",
        "quality_artifact_sha256",
    ):
        citation.pop(field, None)
    transcript_text = context.get("transcript_text")
    if not isinstance(transcript_text, str):
        raise PatternEvidenceError(
            "transcript evidence cannot be verified: "
            f"{context.get('transcript_reason')}"
        )
    try:
        raw_segments = context.get("timed_segments")
        resolved = resolve_quote(
            transcript_text,
            quote,
            segments=raw_segments if isinstance(raw_segments, list) else [],
        )
    except ValueError as exc:
        raise PatternEvidenceError(
            f"transcript evidence quote {quote!r}: {exc}"
        ) from exc
    citation.update(resolved)
    identity = context.get("transcript_artifact_identity")
    if not isinstance(identity, Mapping) or not identity:
        raise PatternEvidenceError(
            "transcript evidence has no canonical artifact identity"
        )
    citation.update(copy.deepcopy(dict(identity)))
    quality_identity = context.get("quality_artifact_identity")
    if not isinstance(quality_identity, Mapping) or not quality_identity:
        raise PatternEvidenceError(
            "transcript evidence has no canonical quality-receipt identity"
        )
    citation.update(copy.deepcopy(dict(quality_identity)))
    if timed and "start_seconds" not in citation:
        raise PatternEvidenceError(
            f"timed transcript quote {quote!r} has no verified timestamp: "
            f"{context.get('timing_reason')}"
        )
    if timed:
        timing_identity = context.get("timing_artifact_identity")
        if not isinstance(timing_identity, Mapping) or not timing_identity:
            raise PatternEvidenceError(
                "timed transcript evidence has no canonical timing-artifact identity"
            )
        citation.update(copy.deepcopy(dict(timing_identity)))


def _canonicalize_slides(
    citation: dict[str, object],
    context: Mapping[str, object],
    *,
    sequence: bool,
) -> None:
    numbers = citation.get("slide_numbers")
    if not isinstance(numbers, list) or not numbers:
        raise PatternEvidenceError(
            "slide evidence requires a non-empty slide_numbers array"
        )
    if any(
        isinstance(number, bool) or not isinstance(number, int) or number < 1
        for number in numbers
    ):
        raise PatternEvidenceError("slide_numbers must contain positive integers")
    if len(numbers) != len(set(numbers)):
        raise PatternEvidenceError("slide_numbers must not contain duplicates")
    if sequence and (
        len(numbers) < 2
        or any(right != left + 1 for left, right in zip(numbers, numbers[1:]))
    ):
        raise PatternEvidenceError(
            "slide_sequence requires at least two consecutive ascending slides"
        )
    source = citation.get("source")
    counts = context.get("slide_counts")
    count = counts.get(source) if isinstance(counts, Mapping) else None
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        reasons = context.get("source_reasons")
        reason = reasons.get(source) if isinstance(reasons, Mapping) else None
        raise PatternEvidenceError(
            "slide evidence cannot be verified from a predeclared local "
            f"artifact: {reason}"
        )
    if any(number > count for number in numbers):
        raise PatternEvidenceError(
            f"slide evidence cites {numbers!r}, but the claimed talk has {count} slides"
        )
    citation.pop("artifact_path", None)
    citation.pop("artifact_sha256", None)
    citation.pop("artifact_root", None)
    identities = context.get("slide_artifact_identities")
    identity = identities.get(source) if isinstance(identities, Mapping) else None
    if not isinstance(identity, Mapping) or not identity:
        raise PatternEvidenceError(
            f"slide evidence source {source!r} has no canonical artifact identity"
        )
    citation.update(copy.deepcopy(dict(identity)))


def _canonicalize_video(
    citation: dict[str, object],
    context: Mapping[str, object],
) -> None:
    start = citation.get("start_seconds")
    end = citation.get("end_seconds")
    if not _nonnegative_number(start) or not _nonnegative_number(end):
        raise PatternEvidenceError(
            "video evidence requires finite non-negative start/end seconds "
            "with end after start"
        )
    start_number = float(cast(int | float, start))
    end_number = float(cast(int | float, end))
    if end_number <= start_number:
        raise PatternEvidenceError(
            "video evidence requires finite non-negative start/end seconds "
            "with end after start"
        )
    duration = context.get("video_duration_seconds")
    segments = context.get("timed_segments")
    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(float(duration))
        or float(duration) <= 0
        or context.get("video_artifact_bound") is not True
    ):
        raise PatternEvidenceError(
            f"video evidence cannot be verified: {context.get('video_binding_reason')}"
        )
    if end_number > float(duration):
        raise PatternEvidenceError(
            f"video evidence ends at {end}, beyond verified duration {duration}"
        )
    if (
        context.get("video_timing_bound") is True
        and isinstance(segments, list)
        and segments
        and not any(
            isinstance(segment, Mapping)
            and _nonnegative_number(segment.get("start_seconds"))
            and _nonnegative_number(segment.get("end_seconds"))
            and float(cast(int | float, segment["end_seconds"])) > start_number
            and float(cast(int | float, segment["start_seconds"])) < end_number
            for segment in segments
        )
    ):
        raise PatternEvidenceError(
            "video evidence range does not overlap the identity-bound timed artifact"
        )
    for field in (
        "artifact_root",
        "artifact_path",
        "artifact_sha256",
        "timing_artifact_root",
        "timing_artifact_path",
        "timing_artifact_sha256",
    ):
        citation.pop(field, None)
    identity = context.get("video_artifact_identity")
    if not isinstance(identity, Mapping) or not identity:
        raise PatternEvidenceError("video evidence has no canonical artifact identity")
    citation.update(copy.deepcopy(dict(identity)))


def _canonicalize_metadata(
    citation: dict[str, object],
    context: Mapping[str, object],
    allowed_fields: frozenset[str],
) -> None:
    field = citation.get("field")
    if not isinstance(field, str) or field not in TALK_METADATA_FIELDS:
        raise PatternEvidenceError(
            f"talk_metadata field {field!r} is not immutable source metadata"
        )
    if field not in allowed_fields:
        raise PatternEvidenceError(
            f"talk_metadata field {field!r} is not permitted for this pattern"
        )
    metadata = context.get("metadata")
    if not isinstance(metadata, Mapping) or not _nonempty(metadata.get(field)):
        raise PatternEvidenceError(
            f"talk_metadata cites absent pre-return field {field!r}"
        )
    citation.pop("value", None)
    citation["value"] = copy.deepcopy(metadata[field])
    post_metadata = context.get("post_return_metadata")
    post_value = (
        post_metadata.get(field)
        if isinstance(post_metadata, Mapping)
        else metadata[field]
    )
    citation.pop("owner_value_after_return", None)
    citation["owner_value_after_return"] = copy.deepcopy(post_value)


def canonicalize_detection_citations(
    detection: Mapping[str, object],
    *,
    evidence_channels: frozenset[str],
    evidence_metadata_fields: frozenset[str],
    context: Mapping[str, object],
) -> dict[str, object]:
    """Return one detection with verified, source-owned citation locations."""
    canonical = copy.deepcopy(dict(detection))
    detection_source = canonical.get("evidence_source")
    used = canonical.get("evidence_sources_used")
    if detection_source == "source_comparison":
        if not isinstance(used, list) or len(used) < 2:
            raise PatternEvidenceError(
                "source_comparison requires exact evidence_sources_used"
            )
        expected_sources = frozenset(used)
    elif isinstance(detection_source, str):
        expected_sources = frozenset({detection_source})
    else:
        raise PatternEvidenceError("detection has no valid evidence_source")

    citations = canonical.get("evidence_citations")
    if not isinstance(citations, list) or not citations:
        raise PatternEvidenceError(
            "current pattern detections require a non-empty evidence_citations array"
        )
    covered_sources: set[str] = set()
    normalized: list[dict[str, object]] = []
    for index, raw in enumerate(citations):
        if not isinstance(raw, Mapping):
            raise PatternEvidenceError(f"evidence_citations[{index}] must be an object")
        citation = copy.deepcopy(dict(raw))
        source = citation.get("source")
        channel = citation.get("channel")
        if source not in expected_sources:
            raise PatternEvidenceError(
                f"citation source {source!r} does not belong to the detection's "
                f"exact source set {sorted(expected_sources)}"
            )
        compatible = EVIDENCE_SOURCE_CHANNELS.get(str(source), frozenset())
        if channel not in compatible:
            raise PatternEvidenceError(
                f"citation channel {channel!r} cannot locate source {source!r}"
            )
        if channel not in evidence_channels:
            raise PatternEvidenceError(
                f"pattern cannot be proved through citation channel {channel!r}; "
                f"catalog permits {sorted(evidence_channels)}"
            )
        unknown = sorted(
            set(citation) - EVIDENCE_CITATION_FIELDS.get(str(channel), frozenset())
        )
        if unknown:
            raise PatternEvidenceError(
                f"{channel!r} citation has unknown fields {unknown}"
            )
        if channel in {"transcript", "timed_transcript"}:
            _canonicalize_transcript(
                citation, context, timed=channel == "timed_transcript"
            )
        elif channel in {"slides", "slide_sequence"}:
            _canonicalize_slides(
                citation, context, sequence=channel == "slide_sequence"
            )
        elif channel == "video":
            _canonicalize_video(citation, context)
        elif channel == "talk_metadata":
            _canonicalize_metadata(citation, context, evidence_metadata_fields)
        else:  # pragma: no cover - shape validation owns the diagnostic
            raise PatternEvidenceError(f"unsupported citation channel {channel!r}")
        # Metadata can corroborate a located source, but it is not the source
        # artifact itself.  Requiring primary coverage here prevents a title,
        # conference, slide count, or URL from self-proving transcript, deck,
        # or delivery-video evidence.
        if channel != "talk_metadata":
            covered_sources.add(str(source))
        normalized.append(citation)
    missing = sorted(expected_sources - covered_sources)
    if missing:
        raise PatternEvidenceError(
            f"evidence_citations do not locate every exact source; missing {missing}"
        )
    canonical["evidence_citations"] = normalized
    return canonical


def _live_native_deck_audit(
    pptx_path: Path,
    *,
    trusted_root: Path | None = None,
) -> dict[str, object]:
    """Recompute the audit in a bounded worker from the exact owner deck."""
    try:
        return recompute_native_deck_audit(
            pptx_path,
            trusted_root=trusted_root,
        )
    except PptxEvidenceError as exc:
        raise PatternEvidenceError(
            f"cannot recompute native-deck audit for {pptx_path}: {exc}"
        ) from exc


def _canonicalize_native_deck_audit(
    structured: dict[str, object],
    context: Mapping[str, object],
    canonical_inspection: list[dict[str, object]],
) -> None:
    """Bind a render receipt to fresh extraction and canonical source identities."""
    raw_audit = structured.get("native_deck_audit")
    if raw_audit is None:
        return
    slide_count = structured.get("slide_count")
    expected_count = (
        slide_count
        if isinstance(slide_count, int) and not isinstance(slide_count, bool)
        else None
    )
    try:
        audit = validate_native_deck_audit(raw_audit, slide_count=expected_count)
    except PptxEvidenceError as exc:
        raise PatternEvidenceError(f"native_deck_audit is invalid: {exc}") from exc

    slide_paths = context.get("slide_artifact_paths")
    native_path = (
        slide_paths.get("native_deck") if isinstance(slide_paths, Mapping) else None
    )
    if not isinstance(native_path, Path):
        raise PatternEvidenceError(
            "native_deck_audit has no canonical native_deck source artifact"
        )
    slide_roots = context.get("slide_artifact_roots")
    raw_root = (
        slide_roots.get("native_deck") if isinstance(slide_roots, Mapping) else None
    )
    trusted_root = raw_root[0] if isinstance(raw_root, tuple) and raw_root else None
    live = _live_native_deck_audit(native_path, trusted_root=trusted_root)
    immutable_fields = {
        "schema_version",
        "extraction_schema_version",
        "extraction_pipeline_version",
        "source_pptx_sha256",
        "source_pptx_size_bytes",
        "slide_count",
        "render_required_slide_numbers",
        "render_required_reasons",
        "extraction_receipt_sha256",
    }
    drift = sorted(
        field for field in immutable_fields if audit.get(field) != live.get(field)
    )
    if drift:
        raise PatternEvidenceError(
            "native_deck_audit disagrees with a fresh extraction of the exact "
            f"source PPTX: {drift}"
        )

    receipt = audit.get("rendered_page_inspection")
    if receipt is None:
        structured["native_deck_audit"] = audit
        return
    if not isinstance(receipt, Mapping):
        raise PatternEvidenceError("rendered_page_inspection must be an object")
    by_source = {
        record.get("source"): record
        for record in canonical_inspection
        if isinstance(record, Mapping)
    }
    native_inspection = by_source.get("native_deck")
    static_inspection = by_source.get("static_slides")
    if not isinstance(native_inspection, Mapping):
        raise PatternEvidenceError(
            "native_deck_audit requires receipt-bound native_deck source_inspection"
        )
    if not isinstance(static_inspection, Mapping):
        raise PatternEvidenceError(
            "rendered_page_inspection requires receipt-bound static_slides inspection"
        )
    if native_inspection.get("artifact_sha256") != audit["source_pptx_sha256"]:
        raise PatternEvidenceError(
            "native_deck_audit source digest does not match canonical native_deck"
        )
    expected_static = {
        "rendered_pdf_sha256": static_inspection.get("artifact_sha256"),
        "rendered_page_count": static_inspection.get("page_count"),
        "inspected_page_ranges": static_inspection.get("page_ranges"),
    }
    mismatches = sorted(
        field
        for field, expected in expected_static.items()
        if receipt.get(field) != expected
    )
    if mismatches:
        raise PatternEvidenceError(
            "rendered_page_inspection is not bound to the canonical static_slides "
            f"artifact and inspected ranges: {mismatches}"
        )
    slide_probes = context.get("slide_artifact_probes")
    static_probe = (
        slide_probes.get("static_slides") if isinstance(slide_probes, Mapping) else None
    )
    if not isinstance(static_probe, PdfArtifactProbe):
        raise PatternEvidenceError(
            "rendered_page_inspection has no canonical bounded static_slides receipt"
        )
    current_identity = {
        "rendered_pdf_sha256": static_probe.source_sha256,
        "rendered_pdf_size_bytes": static_probe.source_size_bytes,
        "rendered_page_count": static_probe.page_count,
    }
    current_mismatches = sorted(
        field
        for field, expected in current_identity.items()
        if receipt.get(field) != expected
    )
    if current_mismatches:
        raise PatternEvidenceError(
            "rendered_page_inspection PDF generation does not match current "
            f"canonical static_slides: {current_mismatches}"
        )
    structured["native_deck_audit"] = audit


def canonicalize_return_evidence(
    ret: Mapping[str, object],
    talk: Mapping[str, object],
    vault_root: str | Path,
    catalog: Any,
    source_roots: Mapping[str, object] | None = None,
    *,
    pattern_scoring_schema_version: int = CURRENT_PATTERN_SCORING_SCHEMA_VERSION,
    video_evidence_assessment: VideoEvidenceAssessment | None = None,
) -> dict[str, object]:
    """Return a v4/v5 payload with source claims canonically located."""
    canonical = copy.deepcopy(dict(ret))
    return_schema_version = canonical.get("return_schema_version")
    if return_schema_version not in CANONICALIZABLE_RETURN_SCHEMA_VERSIONS:
        raise PatternEvidenceError(
            "source evidence canonicalization supports return schemas "
            f"{sorted(CANONICALIZABLE_RETURN_SCHEMA_VERSIONS)}"
        )
    observations = canonical.get("pattern_observations")
    if not isinstance(observations, dict):
        raise PatternEvidenceError(
            "pattern_observations is required for evidence canonicalization"
        )
    context = build_evidence_context(
        vault_root,
        talk,
        canonical,
        source_roots=source_roots,
        video_evidence_assessment=_selected_video_assessment(video_evidence_assessment),
    )
    if context.get("transcript_text") is not None:
        canonical_transcript_source = context.get("canonical_transcript_source")
        if canonical_transcript_source not in {"youtube_auto", "whisper", "manual"}:
            raise PatternEvidenceError(
                "validated transcript has no machine receipt or pre-registered "
                "transcript_source provenance"
            )
        if canonical.get("transcript_source") != canonical_transcript_source:
            raise PatternEvidenceError(
                "return transcript_source is not bound to acquisition provenance; "
                f"expected {canonical_transcript_source!r}"
            )
    counts = context.get("slide_counts")
    slide_identities = context.get("slide_artifact_identities")
    return_slide_source = canonical.get("slide_source")
    has_static = isinstance(slide_identities, Mapping) and isinstance(
        slide_identities.get("static_slides"), Mapping
    )
    has_native = isinstance(slide_identities, Mapping) and isinstance(
        slide_identities.get("native_deck"), Mapping
    )
    if return_slide_source == "pptx" and not has_native:
        raise PatternEvidenceError(
            "return slide_source 'pptx' has no readable preclaim PPTX artifact"
        )
    if return_slide_source == "pdf" and not has_static:
        raise PatternEvidenceError(
            "return slide_source 'pdf' has no readable identity-bound PDF artifact"
        )
    if return_slide_source == "both" and not (has_static and has_native):
        raise PatternEvidenceError(
            "return slide_source 'both' requires readable PDF and PPTX artifacts"
        )
    selected_slide_source = (
        "native_deck"
        if canonical.get("slide_source") == "pptx"
        else (
            "static_slides"
            if canonical.get("slide_source") in {"pdf", "both", "video_extracted"}
            else None
        )
    )
    selected_slide_count = (
        counts.get(selected_slide_source)
        if selected_slide_source is not None and isinstance(counts, Mapping)
        else None
    )
    structured = canonical.get("structured_data")
    if isinstance(selected_slide_count, int) and not isinstance(
        selected_slide_count, bool
    ):
        if isinstance(structured, dict):
            supplied_count = structured.get("slide_count")
            if supplied_count is not None and supplied_count != selected_slide_count:
                raise PatternEvidenceError(
                    "structured_data.slide_count disagrees with the selected "
                    f"canonical artifact count {selected_slide_count}"
                )
            rows = structured.get("per_slide_visual")
            if isinstance(rows, list):
                row_numbers = [
                    row.get("slide_number") for row in rows if isinstance(row, Mapping)
                ]
                if any(
                    isinstance(number, bool)
                    or not isinstance(number, int)
                    or number < 1
                    or number > selected_slide_count
                    for number in row_numbers
                ):
                    raise PatternEvidenceError(
                        "structured_data.per_slide_visual contains a row outside "
                        f"the canonical 1..{selected_slide_count} artifact bound"
                    )
            structured["slide_count"] = selected_slide_count
    else:
        if isinstance(structured, Mapping) and "slide_count" in structured:
            raise PatternEvidenceError(
                "structured_data.slide_count has no verified selected slide artifact"
            )
        if canonical.get("status") == "processed":
            raise PatternEvidenceError(
                "status processed requires a readable canonical authored-slide artifact"
            )
    raw_metadata = context.get("metadata")
    post_return_metadata: dict[str, object] = (
        copy.deepcopy(dict(raw_metadata)) if isinstance(raw_metadata, Mapping) else {}
    )
    for field in TALK_METADATA_FIELDS:
        if field in canonical and _nonempty(canonical[field]):
            post_return_metadata[field] = copy.deepcopy(canonical[field])
    if isinstance(structured, Mapping) and "slide_count" in structured:
        post_return_metadata["slide_count"] = copy.deepcopy(structured["slide_count"])
    context["post_return_metadata"] = post_return_metadata
    claimed_sources = observations.get("evidence_sources")
    if not isinstance(claimed_sources, list):
        raise PatternEvidenceError(
            "pattern_observations.evidence_sources must be an array"
        )
    (
        canonical_inspection,
        complete_sources,
        comparison_groups,
    ) = canonicalize_source_inspection(observations.get("source_inspection"), context)
    inspected_sources = {str(record["source"]) for record in canonical_inspection}
    if set(claimed_sources) != inspected_sources:
        raise PatternEvidenceError(
            "evidence_sources must exactly match receipt-bound source_inspection; "
            f"declared={sorted(set(claimed_sources))}, "
            f"inspected={sorted(inspected_sources)}"
        )
    if canonical.get("status") == "processed" and not inspected_sources.intersection(
        {"static_slides", "native_deck"}
    ):
        raise PatternEvidenceError(
            "status processed requires a receipt-bound slide inspection; use "
            "processed_partial when no authored slide artifact was inspected"
        )
    observations["source_inspection"] = canonical_inspection
    if isinstance(structured, dict):
        _canonicalize_native_deck_audit(
            structured,
            context,
            canonical_inspection,
        )
    detected_ids: set[str] = set()
    for field in ("patterns_detected", "antipatterns_detected"):
        detections = observations.get(field)
        if not isinstance(detections, list):
            raise PatternEvidenceError(f"pattern_observations.{field} must be an array")
        normalized = []
        for detection in detections:
            if not isinstance(detection, Mapping):
                raise PatternEvidenceError(
                    f"pattern_observations.{field} entries must be objects"
                )
            pattern_id = detection.get("pattern_id")
            entry = catalog.entries.get(pattern_id)
            if entry is None:
                raise PatternEvidenceError(f"unknown catalog id {pattern_id!r}")
            located = canonicalize_detection_citations(
                detection,
                evidence_channels=entry.evidence_channels,
                evidence_metadata_fields=entry.evidence_metadata_fields,
                context=context,
            )
            located["dimensions"] = list(entry.vault_dimensions)
            _require_citations_within_inspection(located, canonical_inspection)
            normalized.append(located)
            if isinstance(pattern_id, str):
                detected_ids.add(pattern_id)
        observations[field] = normalized

    raw_not_evaluable = observations.get("not_evaluable")
    raw_entries = raw_not_evaluable if isinstance(raw_not_evaluable, list) else []
    raw_ids = {
        item.get("pattern_id") for item in raw_entries if isinstance(item, Mapping)
    }
    expected_reasons: dict[str, str] = {}
    outcomes: dict[str, str] = {pattern_id: "detected" for pattern_id in detected_ids}
    canonical_assessments: list[dict[str, object]] = []
    raw_assessments = observations.get("applicability_assessments")
    assessment_entries = raw_assessments if isinstance(raw_assessments, list) else []
    assessments_by_id: dict[str, Mapping[str, object]] = {}
    if return_schema_version == EXHAUSTIVE_OUTCOME_RETURN_SCHEMA_VERSION:
        for index, raw_assessment in enumerate(assessment_entries):
            if not isinstance(raw_assessment, Mapping):
                raise PatternEvidenceError(
                    f"applicability_assessments[{index}] must be an object"
                )
            pattern_id = raw_assessment.get("pattern_id")
            if not isinstance(pattern_id, str) or pattern_id in assessments_by_id:
                raise PatternEvidenceError(
                    "applicability_assessments pattern ids must be non-empty and "
                    "duplicate-free"
                )
            if pattern_id in detected_ids:
                raise PatternEvidenceError(
                    f"{pattern_id!r} cannot be detected and applicability-assessed"
                )
            assessments_by_id[pattern_id] = raw_assessment
    elif "applicability_assessments" in observations:
        raise PatternEvidenceError(
            "return schema v4 cannot carry applicability_assessments"
        )

    for pattern_id, entry in sorted(catalog.entries.items()):
        if not entry.observable:
            continue
        if pattern_id in detected_ids:
            continue
        assessment = assessments_by_id.get(pattern_id)
        applicability_gate = getattr(entry, "applicability_evaluable_from", None)
        conditions = getattr(entry, "not_applicable_when", None)
        if return_schema_version == EXHAUSTIVE_OUTCOME_RETURN_SCHEMA_VERSION and (
            applicability_gate is not None or conditions is not None
        ):
            if applicability_gate is None or conditions is None:
                raise PatternEvidenceError(
                    f"catalog entry {pattern_id!r} has a partial applicability contract"
                )
            applicability_complete = _absence_gate_satisfied(
                applicability_gate, complete_sources, comparison_groups
            )
            if not applicability_complete:
                if assessment is not None:
                    raise PatternEvidenceError(
                        f"{pattern_id!r} has an applicability assessment without "
                        "complete applicability-gate coverage"
                    )
                expected_reasons[pattern_id] = APPLICABILITY_INSPECTION_REASON_CODE
                outcomes[pattern_id] = "not_evaluable"
                continue
            if assessment is None:
                raise PatternEvidenceError(
                    f"{pattern_id!r} requires exactly one applicability "
                    "assessment after complete applicability-gate coverage"
                )
            if not _claim_uses_complete_gate(
                assessment,
                applicability_gate,
                complete_sources,
                comparison_groups,
            ):
                raise PatternEvidenceError(
                    f"{pattern_id!r} applicability assessment is not bound to "
                    "one complete catalog-authorized source group"
                )
            result = assessment.get("result")
            if result not in {"applicable", "not_applicable"}:
                raise PatternEvidenceError(
                    f"{pattern_id!r} applicability result is invalid: {result!r}"
                )
            authorized_conditions = {condition.condition_id for condition in conditions}
            condition_id = assessment.get("condition_id")
            if result == "not_applicable":
                if condition_id not in authorized_conditions:
                    raise PatternEvidenceError(
                        f"{pattern_id!r} not-applicable condition is not catalog "
                        f"authorized: {condition_id!r}"
                    )
            elif "condition_id" in assessment:
                raise PatternEvidenceError(
                    f"{pattern_id!r} applicable assessment cannot carry condition_id"
                )
            located_assessment = canonicalize_detection_citations(
                assessment,
                evidence_channels=entry.evidence_channels,
                evidence_metadata_fields=entry.evidence_metadata_fields,
                context=context,
            )
            _require_citations_within_inspection(
                located_assessment, canonical_inspection
            )
            canonical_assessments.append(located_assessment)
            if result == "not_applicable":
                outcomes[pattern_id] = "not_applicable"
                continue
        elif assessment is not None:
            raise PatternEvidenceError(
                f"{pattern_id!r} has no catalog-owned applicability contract"
            )

        gate = entry.absence_evaluable_from
        if gate is None:
            expected_reasons[pattern_id] = (
                POSITIVE_ONLY_ABSENCE_REASON_CODE
                if entry.evaluable_from is not None
                else SOURCE_GATE_PENDING_REASON_CODE
            )
            outcomes[pattern_id] = "not_evaluable"
        elif not _absence_gate_satisfied(gate, complete_sources, comparison_groups):
            expected_reasons[pattern_id] = SOURCE_INSPECTION_REASON_CODE
            outcomes[pattern_id] = "not_evaluable"
        else:
            outcomes[pattern_id] = "undetected"

    unknown_assessments = sorted(set(assessments_by_id) - set(outcomes))
    if unknown_assessments:
        raise PatternEvidenceError(
            "applicability_assessments contain unknown, unobservable, or "
            f"otherwise ineligible pattern ids: {unknown_assessments}"
        )
    expected_ids = set(expected_reasons)
    raw_reasons = {
        item.get("pattern_id"): item.get("reason_code")
        for item in raw_entries
        if isinstance(item, Mapping)
    }
    if (
        raw_ids != expected_ids
        or len(raw_entries) != len(expected_ids)
        or raw_reasons != expected_reasons
    ):
        raise PatternEvidenceError(
            "not_evaluable must be engine-derivable from complete inspection "
            f"coverage/catalog gates; expected {expected_reasons}, got "
            f"{raw_reasons}"
        )

    available_groups: list[list[str]] = [
        [source] for source in sorted(complete_sources - {"source_comparison"})
    ]
    for record in canonical_inspection:
        if (
            record.get("source") == "source_comparison"
            and record.get("coverage_complete") is True
            and isinstance(record.get("evidence_sources_used"), list)
        ):
            available_groups.append(
                copy.deepcopy(cast(list[str], record["evidence_sources_used"]))
            )
    observations["not_evaluable"] = [
        {
            "pattern_id": pattern_id,
            "reason_code": expected_reasons[pattern_id],
            "required_source_groups": [
                sorted(group)
                for group in (
                    catalog.entries[pattern_id].applicability_evaluable_from
                    if expected_reasons[pattern_id]
                    == APPLICABILITY_INSPECTION_REASON_CODE
                    else catalog.entries[pattern_id].absence_evaluable_from
                )
                or ()
            ],
            "available_source_groups": copy.deepcopy(available_groups),
            "capability_fact": {
                "kind": (
                    (
                        "catalog_source_gate_pending_owner_review"
                        if expected_reasons[pattern_id]
                        == SOURCE_GATE_PENDING_REASON_CODE
                        else "catalog_positive_only_absence"
                    )
                    if expected_reasons[pattern_id]
                    in {
                        SOURCE_GATE_PENDING_REASON_CODE,
                        POSITIVE_ONLY_ABSENCE_REASON_CODE,
                    }
                    else (
                        "insufficient_applicability_source_coverage"
                        if expected_reasons[pattern_id]
                        == APPLICABILITY_INSPECTION_REASON_CODE
                        else "insufficient_complete_source_coverage"
                    )
                ),
                "complete_sources": sorted(complete_sources),
            },
        }
        for pattern_id in sorted(expected_ids)
    ]
    if return_schema_version == EXHAUSTIVE_OUTCOME_RETURN_SCHEMA_VERSION:
        observations["applicability_assessments"] = sorted(
            canonical_assessments,
            key=lambda item: cast(str, item["pattern_id"]),
        )
        pattern_outcomes = [
            {"pattern_id": pattern_id, "outcome": outcomes[pattern_id]}
            for pattern_id in sorted(outcomes)
        ]
        observations["pattern_outcomes"] = pattern_outcomes
        observations["opportunity_coverage_identity"] = opportunity_coverage_identity(
            pattern_outcomes,
            pattern_catalog_fingerprint=catalog.fingerprint,
            pattern_scoring_schema_version=pattern_scoring_schema_version,
        )
        observations["evidence_schema_version"] = PATTERN_EVIDENCE_SCHEMA_VERSION
    else:
        observations["evidence_schema_version"] = LEGACY_PATTERN_EVIDENCE_SCHEMA_VERSION
    return canonical


def detection_claim(detection: object) -> object:
    """Strip engine-owned locations while retaining the model-authored claim."""
    if not isinstance(detection, Mapping):
        return detection
    claim = copy.deepcopy(dict(detection))
    # Dimensions are catalog authority, not model authority. Raw returns may
    # omit them; return validation rejects any supplied value that differs.
    claim.pop("dimensions", None)
    citations = claim.get("evidence_citations")
    if isinstance(citations, list):
        stripped = []
        for citation in citations:
            if not isinstance(citation, Mapping):
                stripped.append(citation)
                continue
            item = dict(citation)
            channel = item.get("channel")
            for field in (
                "artifact_root",
                "artifact_path",
                "artifact_sha256",
                "timing_artifact_root",
                "timing_artifact_path",
                "timing_artifact_sha256",
                "quality_artifact_root",
                "quality_artifact_path",
                "quality_artifact_sha256",
            ):
                item.pop(field, None)
            if channel in {"transcript", "timed_transcript"}:
                for field in ("line_start", "line_end", "start_seconds", "end_seconds"):
                    item.pop(field, None)
            elif channel == "talk_metadata":
                item.pop("value", None)
                item.pop("owner_value_after_return", None)
            stripped.append(item)
        claim["evidence_citations"] = stripped
    return claim


def _v5_projection_freshness_reasons(
    talk: Mapping[str, object],
    observations: Mapping[str, object],
) -> set[str]:
    """Cross-check persisted v5 lanes without trusting their outcome hash."""
    reasons: set[str] = set()

    outcomes = observations.get("pattern_outcomes")
    outcome_by_id: dict[str, str] = {}
    outcomes_valid = isinstance(outcomes, list)
    if isinstance(outcomes, list):
        for item in outcomes:
            if (
                not isinstance(item, Mapping)
                or set(item) != {"pattern_id", "outcome"}
                or not isinstance(item.get("pattern_id"), str)
                or not item.get("pattern_id")
                or item.get("pattern_id") in outcome_by_id
                or not isinstance(item.get("outcome"), str)
                or item.get("outcome") not in PATTERN_OUTCOMES
            ):
                outcomes_valid = False
                continue
            outcome_by_id[cast(str, item["pattern_id"])] = cast(str, item["outcome"])
    if not outcomes_valid:
        reasons.add("pattern_outcomes_projection_invalid")

    def lane_ids(lane: str) -> tuple[set[str], bool]:
        raw = observations.get(lane)
        if not isinstance(raw, list):
            reasons.add(f"{lane}_ids_invalid")
            return set(), False
        ids: set[str] = set()
        valid = True
        for item in raw:
            pattern_id = item.get("pattern_id") if isinstance(item, Mapping) else None
            if not isinstance(pattern_id, str) or not pattern_id or pattern_id in ids:
                valid = False
                continue
            ids.add(pattern_id)
        if not valid:
            reasons.add(f"{lane}_ids_invalid")
        return ids, valid

    pattern_ids, patterns_valid = lane_ids("patterns_detected")
    antipattern_ids, antipatterns_valid = lane_ids("antipatterns_detected")
    not_evaluable_ids, not_evaluable_valid = lane_ids("not_evaluable")
    assessment_ids, assessments_valid = lane_ids("applicability_assessments")
    assessments = observations.get("applicability_assessments")
    not_applicable_ids: set[str] = set()
    if isinstance(assessments, list):
        for item in assessments:
            if not isinstance(item, Mapping):
                continue
            pattern_id = item.get("pattern_id")
            result = item.get("result")
            if result not in {"applicable", "not_applicable"}:
                assessments_valid = False
                reasons.add("applicability_assessment_results_invalid")
            elif result == "not_applicable" and isinstance(pattern_id, str):
                not_applicable_ids.add(pattern_id)

    detected_ids = pattern_ids | antipattern_ids
    if pattern_ids & antipattern_ids:
        reasons.add("pattern_detection_polarity_overlap")
    if detected_ids & (not_evaluable_ids | assessment_ids):
        reasons.add("pattern_observation_lane_overlap")
    if not_evaluable_ids & not_applicable_ids:
        reasons.add("pattern_observation_lane_overlap")

    if outcomes_valid:
        outcome_ids = set(outcome_by_id)
        if not (detected_ids | not_evaluable_ids | assessment_ids).issubset(
            outcome_ids
        ):
            reasons.add("pattern_outcomes_unknown_lane_ids")
        if (
            patterns_valid
            and antipatterns_valid
            and {
                pattern_id
                for pattern_id, outcome in outcome_by_id.items()
                if outcome == "detected"
            }
            != detected_ids
        ):
            reasons.add("pattern_outcomes_detected_projection_drift")
        if (
            not_evaluable_valid
            and {
                pattern_id
                for pattern_id, outcome in outcome_by_id.items()
                if outcome == "not_evaluable"
            }
            != not_evaluable_ids
        ):
            reasons.add("pattern_outcomes_not_evaluable_projection_drift")
        if (
            assessments_valid
            and {
                pattern_id
                for pattern_id, outcome in outcome_by_id.items()
                if outcome == "not_applicable"
            }
            != not_applicable_ids
        ):
            reasons.add("pattern_outcomes_not_applicable_projection_drift")

    if patterns_valid and antipatterns_valid:
        expected_score = len(pattern_ids) - len(antipattern_ids)
        nested_score = observations.get("pattern_score")
        if (
            isinstance(nested_score, bool)
            or not isinstance(nested_score, int)
            or nested_score != expected_score
        ):
            reasons.add("pattern_score_projection_drift")
        promoted_score = talk.get("pattern_score")
        if (
            isinstance(promoted_score, bool)
            or not isinstance(promoted_score, int)
            or promoted_score != expected_score
            or promoted_score != nested_score
        ):
            reasons.add("promoted_pattern_score_drift")
    return reasons


def _declares_persisted_native_deck(
    talk: Mapping[str, object],
    observations: Mapping[str, object],
) -> bool:
    """Return whether persisted claims depend on the native-deck lane."""
    slide_source = talk.get("slide_source")
    if isinstance(slide_source, str) and slide_source in {"pptx", "both"}:
        return True
    evidence_sources = observations.get("evidence_sources")
    if isinstance(evidence_sources, list) and any(
        source == "native_deck" for source in evidence_sources
    ):
        return True
    inspection = observations.get("source_inspection")
    if isinstance(inspection, list) and any(
        isinstance(record, Mapping) and record.get("source") == "native_deck"
        for record in inspection
    ):
        return True
    for lane in (
        "patterns_detected",
        "antipatterns_detected",
        "applicability_assessments",
    ):
        detections = observations.get(lane)
        if not isinstance(detections, list):
            continue
        for detection in detections:
            if not isinstance(detection, Mapping):
                continue
            if detection.get("evidence_source") == "native_deck":
                return True
            citations = detection.get("evidence_citations")
            if isinstance(citations, list) and any(
                isinstance(citation, Mapping)
                and citation.get("source") == "native_deck"
                for citation in citations
            ):
                return True
    return False


def assess_persisted_pattern_evidence_freshness(
    talk: Mapping[str, object],
    *,
    vault_root: str | Path,
    source_roots: Mapping[str, object] | None = None,
    video_evidence_assessment: VideoEvidenceAssessment | None = None,
) -> tuple[str, ...]:
    """Return stable reason codes for any persisted evidence drift.

    Empty means fresh. The function is pure/read-only and root-aware so cohort,
    profile, queue, and renderer consumers share one definition of current.
    """
    observations = talk.get("pattern_observations")
    if not isinstance(observations, Mapping):
        return ("pattern_observations_missing",)
    evidence_schema_version = observations.get("evidence_schema_version")
    if evidence_schema_version not in {
        LEGACY_PATTERN_EVIDENCE_SCHEMA_VERSION,
        PATTERN_EVIDENCE_SCHEMA_VERSION,
    }:
        return ("evidence_schema_unverified",)

    reasons: set[str] = set()
    if evidence_schema_version == PATTERN_EVIDENCE_SCHEMA_VERSION:
        reasons.update(_v5_projection_freshness_reasons(talk, observations))
    vault = _lexical_absolute(vault_root)
    bounded_vault = _canonical_pdf_root(vault_root)
    bounded_video_vault = _canonical_video_root(vault_root)
    selected_video_assessment = _selected_video_assessment(video_evidence_assessment)
    current_context: Mapping[str, object] = {}
    try:
        current_context = build_evidence_context(
            vault_root,
            talk,
            source_roots=source_roots,
            video_evidence_assessment=selected_video_assessment,
        )
    except PatternEvidenceError:
        if evidence_schema_version == PATTERN_EVIDENCE_SCHEMA_VERSION:
            reasons.add("source_role_context_unavailable")

    def identity_root(
        kind: object,
        label: str,
        *,
        bounded_suffix: str | frozenset[str] | None = None,
    ) -> Path | None:
        if kind == "vault":
            if bounded_suffix == ".pdf":
                return bounded_vault
            if bounded_suffix == ".pptx":
                return vault
            if bounded_suffix == _VIDEO_SUFFIXES:
                return bounded_video_vault
            return vault
        if kind == "pptx_source":
            configured = (
                source_roots.get("pptx_source_dir")
                if isinstance(source_roots, Mapping)
                else None
            )
            if configured is None:
                reasons.add(f"{label}:artifact_root_unconfigured")
                return None
            try:
                configured_root = materialize_native_root(configured)
            except ArtifactLocatorError as exc:
                reasons.add(f"{label}:artifact_root_invalid:{exc.reason_code}")
                return None
            return (
                _canonical_pdf_root(configured_root)
                if bounded_suffix == ".pdf"
                else configured_root
            )
        if isinstance(kind, str) and kind.startswith("preclaim:"):
            field = kind.removeprefix("preclaim:")
            if field == "video_local_path" and bounded_suffix == _VIDEO_SUFFIXES:
                raw_youtube_id = talk.get("youtube_id")
                bound_youtube_id = (
                    raw_youtube_id
                    if isinstance(raw_youtube_id, str)
                    and _YOUTUBE_ID.fullmatch(raw_youtube_id)
                    else None
                )
                legacy_video_path, _reason = _local_video_binding(
                    vault_root,
                    talk,
                    bound_youtube_id,
                )
                if legacy_video_path is not None:
                    return legacy_video_path.parent
            declared = talk.get(field)
            try:
                locator_kind = classify_artifact_locator(declared)
            except ArtifactLocatorError as exc:
                reasons.add(f"{label}:artifact_root_preclaim_invalid:{exc.reason_code}")
                return None
            if locator_kind == "relative":
                reasons.add(f"{label}:artifact_root_preclaim_missing")
                return None
            try:
                absolute = materialize_artifact_locator(declared)
            except ArtifactLocatorError as exc:
                reasons.add(f"{label}:artifact_root_preclaim_invalid:{exc.reason_code}")
                return None
            parent = absolute.parent
            if bounded_suffix == ".pdf":
                return _canonical_pdf_root(parent)
            return parent
        reasons.add(f"{label}:artifact_root_invalid")
        return None

    def check_identity(
        owner: Mapping[str, object],
        label: str,
        *,
        timing: bool = False,
        quality: bool = False,
        bounded_current_digest: str | None = None,
        bounded_suffix: str | frozenset[str] | None = None,
    ) -> Path | None:
        if timing and quality:  # pragma: no cover - internal API guard
            raise ValueError("an identity cannot be both timing and quality")
        prefix = (
            "quality_artifact"
            if quality
            else "timing_artifact"
            if timing
            else "artifact"
        )
        raw_path = owner.get(f"{prefix}_path")
        digest = owner.get(f"{prefix}_sha256")
        root = identity_root(
            owner.get(f"{prefix}_root"),
            label,
            bounded_suffix=bounded_suffix,
        )
        if (
            root is None
            or not isinstance(raw_path, str)
            or not raw_path
            or PurePosixPath(raw_path).is_absolute()
            or PurePosixPath(raw_path).as_posix() != raw_path
            or any(part in {".", ".."} for part in PurePosixPath(raw_path).parts)
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            reasons.add(f"{label}:{prefix}_identity_incomplete")
            return None
        if timing and not raw_path.endswith(".segments.json"):
            reasons.add(f"{label}:{prefix}_path_invalid")
            return None
        if quality and not raw_path.endswith(".quality.json"):
            reasons.add(f"{label}:{prefix}_path_invalid")
            return None
        try:
            lexical = materialize_artifact_locator(raw_path, trusted_root=root)
        except ArtifactLocatorError:
            reasons.add(f"{label}:{prefix}_path_invalid")
            return None
        if bounded_suffix is not None:
            try:
                resolved = _resolve_local_bounded_artifact(
                    root,
                    raw_path,
                    suffix=bounded_suffix,
                    label=f"{label}:{prefix}",
                )
            except PatternEvidenceError:
                reasons.add(f"{label}:{prefix}_path_invalid")
                return None
        else:
            resolved = lexical.resolve(strict=False)
            try:
                resolved.relative_to(root)
            except ValueError:
                reasons.add(f"{label}:{prefix}_path_invalid")
                return None
            if lexical != resolved:
                reasons.add(f"{label}:{prefix}_symlink_rejected")
                return None
            if not resolved.is_file():
                reasons.add(f"{label}:{prefix}_missing")
                return None
        if bounded_current_digest is not None:
            current_digest = bounded_current_digest
        elif bounded_suffix is not None:
            reasons.add(f"{label}:{prefix}_bounded_digest_unavailable")
            return resolved
        else:
            try:
                current_digest = _sha256_file(resolved)
            except PatternEvidenceError:
                reasons.add(f"{label}:{prefix}_unreadable")
                return None
        if current_digest != digest:
            reasons.add(f"{label}:{prefix}_digest_mismatch")
        return resolved

    slide_identities = current_context.get("slide_artifact_identities")
    current_native_identity = (
        slide_identities.get("native_deck")
        if isinstance(slide_identities, Mapping)
        else None
    )
    candidate_native_digest = (
        current_native_identity.get("artifact_sha256")
        if isinstance(current_native_identity, Mapping)
        else None
    )
    bounded_native_digest = (
        candidate_native_digest
        if isinstance(candidate_native_digest, str)
        and re.fullmatch(r"[0-9a-f]{64}", candidate_native_digest) is not None
        else None
    )
    current_artifact_probes = current_context.get("slide_artifact_probes")
    current_native_probe = (
        current_artifact_probes.get("native_deck")
        if isinstance(current_artifact_probes, Mapping)
        else None
    )
    current_static_probe = (
        current_artifact_probes.get("static_slides")
        if isinstance(current_artifact_probes, Mapping)
        else None
    )
    bounded_static_digest = (
        current_static_probe.source_sha256
        if isinstance(current_static_probe, PdfArtifactProbe)
        else None
    )
    bounded_static_page_count = (
        current_static_probe.page_count
        if isinstance(current_static_probe, PdfArtifactProbe)
        else None
    )
    current_video_probe = current_context.get("video_artifact_probe")
    bounded_video_digest = (
        current_video_probe.source_sha256
        if isinstance(current_video_probe, VideoArtifactProbe)
        else None
    )
    native_declared = _declares_persisted_native_deck(talk, observations)
    structured = talk.get("structured_data")
    raw_native_audit = (
        structured.get("native_deck_audit") if isinstance(structured, Mapping) else None
    )
    validated_native_audit: dict[str, object] | None = None
    slide_source = talk.get("slide_source")
    if raw_native_audit is not None and (
        not isinstance(slide_source, str) or slide_source not in {"pptx", "both"}
    ):
        reasons.add("native_deck_audit_unexpected")
    if native_declared:
        if raw_native_audit is None:
            reasons.add("native_deck_audit_missing")
        else:
            if isinstance(raw_native_audit, Mapping) and (
                raw_native_audit.get("extraction_schema_version")
                != PPTX_EXTRACTION_SCHEMA_VERSION
                or raw_native_audit.get("extraction_pipeline_version")
                != PPTX_EXTRACTION_PIPELINE_VERSION
            ):
                reasons.add("native_deck_audit_generation_drift")
            expected_count = (
                current_native_probe.slide_count
                if isinstance(current_native_probe, PptxArtifactProbe)
                else None
            )
            try:
                validated_native_audit = validate_native_deck_audit(
                    raw_native_audit,
                    slide_count=expected_count,
                )
            except PptxEvidenceError:
                reasons.add("native_deck_audit_invalid")
            else:
                if not isinstance(current_native_probe, PptxArtifactProbe):
                    reasons.add("native_deck_audit_source_unavailable")
                elif (
                    validated_native_audit["source_pptx_sha256"]
                    != current_native_probe.source_sha256
                    or validated_native_audit["source_pptx_size_bytes"]
                    != current_native_probe.source_size_bytes
                    or validated_native_audit["slide_count"]
                    != current_native_probe.slide_count
                ):
                    reasons.add("native_deck_audit_source_generation_drift")
                structured_slide_count = (
                    structured.get("slide_count")
                    if isinstance(structured, Mapping)
                    else None
                )
                if structured_slide_count != validated_native_audit["slide_count"]:
                    reasons.add("native_deck_audit_structured_slide_count_drift")

    def check_source_identity(
        owner: Mapping[str, object],
        label: str,
        source: str,
    ) -> Path | None:
        """Check one source identity without parent-process PPTX reads."""
        allowed_suffixes = {
            "transcript": frozenset({".txt"}),
            "static_slides": frozenset({".pdf"}),
            "native_deck": frozenset({".pptx"}),
            "delivery_video": frozenset({".mp4", ".webm", ".mkv", ".mov"}),
        }.get(source, frozenset())
        raw_path = owner.get("artifact_path")
        if (
            not isinstance(raw_path, str)
            or PurePosixPath(raw_path).suffix.casefold() not in allowed_suffixes
        ):
            reasons.add(f"{label}:source_role_suffix_mismatch")
            return None
        return check_identity(
            owner,
            label,
            bounded_current_digest=(
                bounded_native_digest
                if source == "native_deck"
                else bounded_static_digest
                if source == "static_slides"
                else bounded_video_digest
                if source == "delivery_video"
                else None
            ),
            bounded_suffix=(
                ".pptx"
                if source == "native_deck"
                else ".pdf"
                if source == "static_slides"
                else _VIDEO_SUFFIXES
                if source == "delivery_video"
                else None
            ),
        )

    def owner_candidates(source: str) -> list[Path]:
        if source in {"native_deck", "static_slides"}:
            role_paths = current_context.get("slide_artifact_paths")
            current_path = (
                role_paths.get(source) if isinstance(role_paths, Mapping) else None
            )
            return (
                [_lexical_absolute(current_path)]
                if isinstance(current_path, Path)
                else []
            )
        values: list[object] = []
        if source == "transcript":
            explicit = talk.get("transcript_path")
            if _nonempty(explicit):
                values.append(explicit)
            else:
                youtube_id = talk.get("youtube_id")
                if isinstance(youtube_id, str) and _YOUTUBE_ID.fullmatch(youtube_id):
                    values.append(f"transcripts/{youtube_id}.txt")
        elif source == "delivery_video":
            owner_youtube_id = talk.get("youtube_id")
            bound_youtube_id = (
                owner_youtube_id
                if isinstance(owner_youtube_id, str)
                and _YOUTUBE_ID.fullmatch(owner_youtube_id)
                else None
            )
            bound_path, _reason = _local_video_binding(
                vault_root,
                talk,
                bound_youtube_id,
            )
            if bound_path is not None:
                return [_lexical_absolute(bound_path)]
        candidates: list[Path] = []
        allowed_suffixes = (
            frozenset({".txt"})
            if source == "transcript"
            else frozenset({".mp4", ".webm", ".mkv", ".mov"})
        )
        for value in values:
            try:
                supplied = materialize_artifact_locator(value, trusted_root=vault)
            except ArtifactLocatorError:
                continue
            if supplied.suffix.casefold() in allowed_suffixes:
                candidates.append(_lexical_absolute(supplied))
        return candidates

    inspection = observations.get("source_inspection")
    if not isinstance(inspection, list) or not inspection:
        reasons.add("source_inspection_missing")
        return tuple(sorted(reasons))
    underlying: dict[str, Mapping[str, object]] = {}
    comparison_records: list[Mapping[str, object]] = []
    for index, record in enumerate(inspection):
        label = f"source_inspection[{index}]"
        if not isinstance(record, Mapping):
            reasons.add(f"{label}:invalid")
            continue
        source = record.get("source")
        if source == "source_comparison":
            comparison_records.append(record)
            continue
        if not isinstance(source, str) or source in underlying:
            reasons.add(f"{label}:source_invalid_or_duplicate")
            continue
        underlying[source] = record
        path = check_source_identity(record, label, source)
        if "timing_artifact_path" in record or "timing_artifact_sha256" in record:
            check_identity(record, label, timing=True)
        if source == "transcript":
            check_identity(record, label, quality=True)
        if path is None:
            continue
        if evidence_schema_version == PATTERN_EVIDENCE_SCHEMA_VERSION:
            allowed_suffixes = {
                "transcript": frozenset({".txt"}),
                "static_slides": frozenset({".pdf"}),
                "native_deck": frozenset({".pptx"}),
                "delivery_video": frozenset({".mp4", ".webm", ".mkv", ".mov"}),
            }.get(source, frozenset())
            if path.suffix.casefold() not in allowed_suffixes:
                reasons.add(f"{label}:source_role_suffix_mismatch")
                continue
            if source in {"static_slides", "native_deck"}:
                role_paths = current_context.get("slide_artifact_paths")
                expected_role_path = (
                    role_paths.get(source) if isinstance(role_paths, Mapping) else None
                )
            elif source == "transcript":
                expected_role_path = current_context.get("transcript_path")
            else:
                expected_role_path = current_context.get("local_video_path")
            expected_role_identity = (
                _lexical_absolute(expected_role_path)
                if source in {"native_deck", "static_slides", "delivery_video"}
                and isinstance(expected_role_path, Path)
                else (
                    expected_role_path.resolve(strict=False)
                    if isinstance(expected_role_path, Path)
                    else None
                )
            )
            if expected_role_identity != path:
                reasons.add(f"{label}:source_role_provenance_drift")
        coherent_transcript_text: str | None = None
        if source == "transcript":
            context_transcript = current_context.get("transcript_text")
            coherent_transcript_text = (
                context_transcript if isinstance(context_transcript, str) else None
            )
            if coherent_transcript_text is None:
                reasons.add(f"{label}:transcript_quality_context_drift")
        current_candidates = owner_candidates(source)
        if path not in current_candidates:
            reasons.add(f"{label}:artifact_owner_path_drift")
        try:
            if source == "transcript":
                if coherent_transcript_text is None:
                    raise PatternEvidenceError(
                        "coherent transcript snapshot is unavailable"
                    )
                line_count = len(coherent_transcript_text.splitlines())
                _, complete = _validate_discrete_ranges(
                    record.get("line_ranges"), upper=line_count, label="line_ranges"
                )
                if record.get("line_count") != line_count:
                    reasons.add(f"{label}:line_count_drift")
            elif source in {"static_slides", "native_deck"}:
                if source == "native_deck":
                    current_roots = current_context.get("slide_artifact_roots")
                    raw_current_root = (
                        current_roots.get("native_deck")
                        if isinstance(current_roots, Mapping)
                        else None
                    )
                    trusted_root = (
                        raw_current_root[0]
                        if isinstance(raw_current_root, tuple) and raw_current_root
                        else identity_root(
                            record.get("artifact_root"),
                            label,
                            bounded_suffix=".pptx",
                        )
                    )
                    count = _pptx_locator_count(
                        path,
                        trusted_root=trusted_root,
                    )
                else:
                    if bounded_static_page_count is None:
                        reasons.add(f"{label}:bounded_page_count_unavailable")
                        continue
                    count = bounded_static_page_count
                _, complete = _validate_discrete_ranges(
                    record.get("page_ranges"), upper=count, label="page_ranges"
                )
                if record.get("page_count") != count:
                    reasons.add(f"{label}:page_count_drift")
            elif source == "delivery_video":
                if not isinstance(current_video_probe, VideoArtifactProbe):
                    raise PatternEvidenceError(
                        "bounded current video receipt is unavailable"
                    )
                duration = current_video_probe.duration_seconds
                if current_video_probe.source_sha256 != record.get("artifact_sha256"):
                    reasons.add(f"{label}:artifact_digest_mismatch")
                _, complete = _validate_time_ranges(
                    record.get("time_ranges"), duration=duration
                )
                stored_duration = record.get("duration_seconds")
                if not isinstance(stored_duration, (int, float)) or not math.isclose(
                    float(stored_duration), duration, abs_tol=0.001
                ):
                    reasons.add(f"{label}:duration_drift")
            else:
                reasons.add(f"{label}:source_invalid")
                continue
            if record.get("coverage_complete") is not complete:
                reasons.add(f"{label}:coverage_complete_drift")
            if evidence_schema_version == PATTERN_EVIDENCE_SCHEMA_VERSION:
                if not complete:
                    expected_absence_reason = ABSENCE_CAPABILITY_INCOMPLETE_RANGES
                    expected_absence_complete = False
                elif source == "transcript":
                    expected_absence_reason = ABSENCE_CAPABILITY_AUTHORIZED_TRANSCRIPT
                    expected_absence_complete = True
                elif source == "static_slides":
                    video_derived = talk.get("slide_source") == "video_extracted"
                    expected_absence_reason = (
                        ABSENCE_CAPABILITY_NONEXHAUSTIVE_VIDEO
                        if video_derived
                        else ABSENCE_CAPABILITY_AUTHORIZED_STATIC
                    )
                    expected_absence_complete = not video_derived
                elif source == "native_deck":
                    expected_absence_reason = ABSENCE_CAPABILITY_BARE_NATIVE
                    expected_absence_complete = False
                else:
                    expected_absence_reason = ABSENCE_CAPABILITY_BARE_VIDEO
                    expected_absence_complete = False
                if record.get("absence_capability_complete") is not (
                    expected_absence_complete
                ):
                    reasons.add(f"{label}:absence_capability_complete_drift")
                if record.get("absence_capability_reason") != (expected_absence_reason):
                    reasons.add(f"{label}:absence_capability_reason_drift")
        except (OSError, UnicodeError, PatternEvidenceError) as exc:
            reasons.add(f"{label}:coverage_unverifiable:{type(exc).__name__}")

    if validated_native_audit is not None:
        native_inspection = underlying.get("native_deck")
        if (
            not isinstance(native_inspection, Mapping)
            or native_inspection.get("artifact_sha256")
            != validated_native_audit["source_pptx_sha256"]
            or native_inspection.get("page_count")
            != validated_native_audit["slide_count"]
        ):
            reasons.add("native_deck_audit_source_inspection_drift")
        rendered_receipt = validated_native_audit.get("rendered_page_inspection")
        if isinstance(rendered_receipt, Mapping):
            static_inspection = underlying.get("static_slides")
            if (
                not isinstance(static_inspection, Mapping)
                or static_inspection.get("artifact_sha256")
                != rendered_receipt.get("rendered_pdf_sha256")
                or static_inspection.get("page_count")
                != rendered_receipt.get("rendered_page_count")
                or static_inspection.get("page_ranges")
                != rendered_receipt.get("inspected_page_ranges")
            ):
                reasons.add("native_deck_audit_rendered_pdf_inspection_drift")
            if not isinstance(current_static_probe, PdfArtifactProbe):
                reasons.add("native_deck_audit_rendered_pdf_unavailable")
            elif (
                rendered_receipt.get("rendered_pdf_sha256")
                != current_static_probe.source_sha256
                or rendered_receipt.get("rendered_pdf_size_bytes")
                != current_static_probe.source_size_bytes
                or rendered_receipt.get("rendered_page_count")
                != current_static_probe.page_count
            ):
                reasons.add("native_deck_audit_rendered_pdf_generation_drift")

    seen_groups: set[frozenset[str]] = set()
    for index, record in enumerate(comparison_records):
        label = f"source_comparison[{index}]"
        used = record.get("evidence_sources_used")
        group = frozenset(used) if isinstance(used, list) else frozenset()
        if len(group) < 2 or group in seen_groups or not group.issubset(underlying):
            reasons.add(f"{label}:group_invalid")
            continue
        seen_groups.add(group)
        identities = record.get("artifact_identities")
        if not isinstance(identities, list) or len(identities) != len(group):
            reasons.add(f"{label}:artifact_identities_invalid")
            continue
        identity_by_source = {
            item.get("source"): item for item in identities if isinstance(item, Mapping)
        }
        if set(identity_by_source) != set(group):
            reasons.add(f"{label}:artifact_identity_sources_mismatch")
            continue
        for source in group:
            identity = identity_by_source[source]
            expected = {
                key: underlying[source].get(key)
                for key in (
                    "artifact_root",
                    "artifact_path",
                    "artifact_sha256",
                    "timing_artifact_root",
                    "timing_artifact_path",
                    "timing_artifact_sha256",
                    "quality_artifact_root",
                    "quality_artifact_path",
                    "quality_artifact_sha256",
                )
                if key in underlying[source]
            }
            actual = {key: identity.get(key) for key in expected}
            if actual != expected:
                reasons.add(f"{label}:{source}:artifact_identity_mismatch")
            check_source_identity(identity, f"{label}:{source}", source)
            if "timing_artifact_path" in identity:
                check_identity(identity, f"{label}:{source}", timing=True)
            if "quality_artifact_path" in identity:
                check_identity(identity, f"{label}:{source}", quality=True)
        expected_complete = record.get("comparison_scope") == "full" and all(
            underlying[source].get("coverage_complete") is True for source in group
        )
        if record.get("coverage_complete") is not expected_complete:
            reasons.add(f"{label}:coverage_complete_drift")
        if evidence_schema_version == PATTERN_EVIDENCE_SCHEMA_VERSION:
            if record.get("absence_capability_complete") is not False:
                reasons.add(f"{label}:absence_capability_complete_drift")
            if record.get("absence_capability_reason") != (
                ABSENCE_CAPABILITY_COMPARISON_UNVERIFIED
            ):
                reasons.add(f"{label}:absence_capability_reason_drift")

    if set(observations.get("evidence_sources") or []) != (
        set(underlying) | ({"source_comparison"} if comparison_records else set())
    ):
        reasons.add("evidence_sources_inspection_mismatch")

    citation_lanes = ["patterns_detected", "antipatterns_detected"]
    if evidence_schema_version == PATTERN_EVIDENCE_SCHEMA_VERSION:
        citation_lanes.append("applicability_assessments")
    for lane in citation_lanes:
        detections = observations.get(lane)
        if not isinstance(detections, list):
            reasons.add(f"{lane}_invalid")
            continue
        for detection_index, detection in enumerate(detections):
            label = f"{lane}[{detection_index}]"
            if not isinstance(detection, Mapping):
                reasons.add(f"{label}:invalid")
                continue
            citations = detection.get("evidence_citations")
            if not isinstance(citations, list) or not citations:
                reasons.add(f"{label}:citations_missing")
                continue
            try:
                _require_citations_within_inspection(
                    detection,
                    [dict(item) for item in inspection if isinstance(item, Mapping)],
                )
            except PatternEvidenceError:
                reasons.add(f"{label}:citation_outside_inspection")
            for citation_index, citation in enumerate(citations):
                citation_label = f"{label}.citation[{citation_index}]"
                if not isinstance(citation, Mapping):
                    reasons.add(f"{citation_label}:invalid")
                    continue
                if citation.get("channel") == "talk_metadata":
                    field = citation.get("field")
                    if (
                        not isinstance(field, str)
                        or "owner_value_after_return" not in citation
                        or citation.get("owner_value_after_return") != talk.get(field)
                    ):
                        reasons.add(f"{citation_label}:metadata_value_drift")
                    continue
                source = citation.get("source")
                if not isinstance(source, str):
                    reasons.add(f"{citation_label}:source_uninspected")
                    continue
                expected_record = underlying.get(source)
                if expected_record is None:
                    reasons.add(f"{citation_label}:source_uninspected")
                    continue
                for field in (
                    "artifact_root",
                    "artifact_path",
                    "artifact_sha256",
                    "timing_artifact_root",
                    "timing_artifact_path",
                    "timing_artifact_sha256",
                    "quality_artifact_root",
                    "quality_artifact_path",
                    "quality_artifact_sha256",
                ):
                    if field in expected_record and citation.get(
                        field
                    ) != expected_record.get(field):
                        reasons.add(f"{citation_label}:{field}_mismatch")
                check_source_identity(citation, citation_label, source)
                if "timing_artifact_path" in citation:
                    check_identity(citation, citation_label, timing=True)
                if "quality_artifact_path" in citation:
                    check_identity(citation, citation_label, quality=True)
    if evidence_schema_version == PATTERN_EVIDENCE_SCHEMA_VERSION:
        outcomes = observations.get("pattern_outcomes")
        if not isinstance(outcomes, list):
            reasons.add("pattern_outcomes_missing")
        else:
            try:
                expected_identity = opportunity_coverage_identity(
                    outcomes,
                    pattern_catalog_fingerprint=talk.get("pattern_catalog_fingerprint"),
                    pattern_scoring_schema_version=talk.get(
                        "pattern_scoring_schema_version"
                    ),
                )
            except PatternEvidenceError:
                reasons.add("pattern_outcomes_invalid")
            else:
                canonical_order = sorted(
                    outcomes,
                    key=lambda item: (
                        str(item.get("pattern_id"))
                        if isinstance(item, Mapping)
                        else repr(item)
                    ),
                )
                if outcomes != canonical_order:
                    reasons.add("pattern_outcomes_noncanonical_order")
                if (
                    observations.get("opportunity_coverage_identity")
                    != expected_identity
                ):
                    reasons.add("opportunity_coverage_identity_drift")
    return tuple(sorted(reasons))


def assess_persisted_evidence_freshness(
    talk: Mapping[str, object],
    vault_root: str | Path,
    *,
    video_evidence_assessment: VideoEvidenceAssessment | None = None,
) -> tuple[str, ...]:
    """Compatibility wrapper for callers that have only a vault root."""
    return assess_persisted_pattern_evidence_freshness(
        talk,
        vault_root=vault_root,
        video_evidence_assessment=video_evidence_assessment,
    )


def return_evidence_claim(ret: Mapping[str, object]) -> dict[str, object]:
    """Return the model-authored payload with engine enrichment erased.

    This establishes the raw-receipt/canonical-state boundary: persistence keeps
    the receipt of the exact raw return, while this projection proves that the
    canonical copy differs only in source-owned line/time/value locations and
    the evidence schema marker.
    """
    claim = copy.deepcopy(dict(ret))
    structured = claim.get("structured_data")
    if isinstance(structured, dict):
        # Canonical slide_count is mechanically derived from the selected local
        # artifact. Raw mismatches are rejected before this projection.
        structured.pop("slide_count", None)
    observations = claim.get("pattern_observations")
    if not isinstance(observations, dict):
        return claim
    observations.pop("evidence_schema_version", None)
    observations.pop("pattern_outcomes", None)
    observations.pop("opportunity_coverage_identity", None)
    inspection = observations.get("source_inspection")
    if isinstance(inspection, list):
        projected = []
        for record in inspection:
            if not isinstance(record, Mapping):
                projected.append(record)
                continue
            source = record.get("source")
            fields = SOURCE_INSPECTION_RAW_FIELDS.get(str(source), frozenset())
            projected.append(
                {
                    field: copy.deepcopy(record[field])
                    for field in fields
                    if field in record
                }
            )
        observations["source_inspection"] = sorted(
            projected,
            key=lambda item: (
                str(item.get("source")) if isinstance(item, Mapping) else repr(item)
            ),
        )
    not_evaluable = observations.get("not_evaluable")
    if isinstance(not_evaluable, list):
        observations["not_evaluable"] = sorted(
            [
                {
                    "pattern_id": item.get("pattern_id"),
                    "reason_code": item.get("reason_code"),
                }
                if isinstance(item, Mapping)
                else item
                for item in not_evaluable
            ],
            key=lambda item: (
                str(item.get("pattern_id")) if isinstance(item, Mapping) else repr(item)
            ),
        )
    for lane in ("patterns_detected", "antipatterns_detected"):
        entries = observations.get(lane)
        if isinstance(entries, list):
            observations[lane] = [detection_claim(entry) for entry in entries]
    assessments = observations.get("applicability_assessments")
    if isinstance(assessments, list):
        observations["applicability_assessments"] = sorted(
            [detection_claim(entry) for entry in assessments],
            key=lambda item: (
                str(item.get("pattern_id")) if isinstance(item, Mapping) else repr(item)
            ),
        )
    return claim
