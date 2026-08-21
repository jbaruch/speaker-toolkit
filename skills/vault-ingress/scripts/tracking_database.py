"""Version and migration contract for ``tracking-database.json``.

``vault-ingress`` owns this artifact's shape and all migrations.  Other skills
may read the legacy and current generations during rollout.  They must never
rewrite a legacy generation or infer a migration from fields that happen to be
present.
"""

from __future__ import annotations

from contextlib import contextmanager
import copy
from dataclasses import dataclass
import datetime as dt
from pathlib import PurePosixPath
import re
from typing import Any, Mapping

from artifact_locator import ArtifactLocatorError, classify_artifact_locator
from queue_claim_contract import (
    QueueClaimContractError,
    classify_queue_claim_versions,
    validate_queue_claim_database,
)
from pptx_discovery_contract import (
    DEFAULT_PPTX_DIRECTORY_EXCLUSIONS,
    PptxDiscoveryContractError,
    validate_pptx_directory_exclusions,
)
from pptx_talk_identity import unassessed_legacy_binding


LEGACY_TRACKING_DATABASE_SCHEMA_VERSION = 0
# The root shape before the `markdown_decks` collection (#318). A top-level key
# is part of the ROOT record's shape, and a version on each nested deck record
# does not version its parent database, so admitting the collection moves the
# root generation (`stateful-artifacts` Migration Policy).
PRE_MARKDOWN_DECKS_TRACKING_DATABASE_SCHEMA_VERSION = 1
TRACKING_DATABASE_SCHEMA_VERSION = 2
LEGACY_TALK_RECORD_SCHEMA_VERSION = 1
FLAT_SCORE_TALK_RECORD_SCHEMA_VERSION = 5
# The generation before the owner-reviewed title-equivalence ledger (#333).
PRE_TITLE_EQUIVALENCE_TALK_RECORD_SCHEMA_VERSION = 6
# The weighted generation's record shape (#299): `pattern_observations` may
# carry a `pattern_score_basis` and `pattern_score` may be fractional.
TALK_RECORD_SCHEMA_VERSION = 7
LEGACY_CONFIG_RECORD_SCHEMA_VERSION = 1
CONFIG_RECORD_SCHEMA_VERSION = 2
LEGACY_PPTX_CATALOG_RECORD_SCHEMA_VERSION = 1
PPTX_CATALOG_EVIDENCE_BOUND_RECORD_SCHEMA_VERSION = 2
PPTX_CATALOG_RECORD_SCHEMA_VERSION = 3
LEGACY_QR_CODE_RECORD_SCHEMA_VERSION = 1
QR_CODE_RECORD_SCHEMA_VERSION = 2
RESOURCE_RECORD_SCHEMA_VERSION = 1
THUMBNAIL_RECORD_SCHEMA_VERSION = 1
CONFIRMED_INTENT_RECORD_SCHEMA_VERSION = 1
SOURCE_REJECTION_RECORD_SCHEMA_VERSION = 1
# v1 lived on the talk record and had no owning filename; v2 is the top-level
# collection shape. Migration moves a v1 entry rather than dropping it, or a
# previously approved talk would silently re-gate.
LEGACY_SOURCE_TITLE_EQUIVALENCE_RECORD_SCHEMA_VERSION = 1
SOURCE_TITLE_EQUIVALENCE_RECORD_SCHEMA_VERSION = 2
LEGACY_IMPROVEMENT_GOAL_RECORD_SCHEMA_VERSION = 1
IMPROVEMENT_GOAL_RECORD_SCHEMA_VERSION = 2
# The authored markdown deck a talk's slides were rendered from (#318). Its own
# top-level collection rather than a talk field: `TALK_RECORD_SCHEMA_VERSION`
# means the analysis generation, so a shape change there is unreachable for the
# legacy records this is for, and a nested record's version does not version its
# parent (#333). The collection is optional — absent means no registered deck —
# so every database written before it existed stays valid, and no migration
# owns it (it is absent from `_RECORD_COUNT_KEYS` for that reason): a deck is
# registered by an owner who knows where the file is, never inferred.
MARKDOWN_DECK_RECORD_SCHEMA_VERSION = 1

READABLE_TRACKING_DATABASE_SCHEMA_VERSIONS = frozenset(
    {
        LEGACY_TRACKING_DATABASE_SCHEMA_VERSION,
        PRE_MARKDOWN_DECKS_TRACKING_DATABASE_SCHEMA_VERSION,
        TRACKING_DATABASE_SCHEMA_VERSION,
    }
)
_READABLE_PATTERN_EVIDENCE_SCHEMA_VERSIONS = frozenset({1, 2})

_TOP_LEVEL_COLLECTIONS = (
    "talks",
    "pptx_catalog",
    "qr_codes",
    "resources",
    "thumbnails",
    "confirmed_intents",
    "improvement_goals",
)
_RECORD_COUNT_KEYS = (
    "config",
    "talks",
    "pptx_catalog",
    "qr_codes",
    "resources",
    "thumbnails",
    "confirmed_intents",
    "improvement_goals",
    "source_title_equivalences",
    "source_rejections",
)

PPTX_CATALOG_REQUIRED_FIELDS = frozenset(
    {"pptx_path", "talk_filename", "matched", "slide_count", "visual_extracted"}
)
# v2 binds every visual-evidence claim to the exact extractor generation and
# source bytes that produced it. A v1 record carries no such binding, so its
# bare `visual_extracted: true` cannot say which extractor schema it refers to.
PPTX_CATALOG_V2_REQUIRED_FIELDS = PPTX_CATALOG_REQUIRED_FIELDS | {"visual_evidence"}
# v3 adds the identity assessment that proves the deck belongs to the talk it
# names. v2 bound a visual claim to the bytes it came from but said nothing
# about WHOSE deck those bytes were, so a deck could carry a perfectly-attested
# extraction receipt for the wrong talk.
PPTX_CATALOG_V3_REQUIRED_FIELDS = PPTX_CATALOG_V2_REQUIRED_FIELDS | {
    "identity_assessment"
}
PPTX_IDENTITY_ASSESSMENT_REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "pptx_path",
        "verdict",
        "artifact_role",
        "selected_talk_filename",
        "reason_codes",
        # The assessor always emits its candidate table, and it is the only
        # record of what the other talks scored. Accepting an assessment without
        # it would persist a verdict nobody can re-examine.
        "candidates",
    }
)
# Both versions bind a visual claim to the extractor generation that produced
# it, so both classify. They differ only in whether the talk binding is proven,
# which is an identity question, not a currency one.
_EVIDENCE_BOUND_PPTX_CATALOG_SCHEMA_VERSIONS = frozenset(
    {
        PPTX_CATALOG_EVIDENCE_BOUND_RECORD_SCHEMA_VERSION,
        PPTX_CATALOG_RECORD_SCHEMA_VERSION,
    }
)
PPTX_VISUAL_EVIDENCE_REQUIRED_FIELDS = frozenset(
    {
        "outcome",
        "extractor_schema_version",
        "pipeline_version",
        "source_fingerprint",
        "artifact",
    }
)
PPTX_SOURCE_FINGERPRINT_REQUIRED_FIELDS = frozenset(
    {"algorithm", "digest", "size_bytes"}
)
PPTX_VISUAL_ARTIFACT_REQUIRED_FIELDS = frozenset({"path", "sha256"})
PPTX_VISUAL_EVIDENCE_OUTCOMES = frozenset({"succeeded", "failed"})
PPTX_SOURCE_FINGERPRINT_ALGORITHMS = frozenset({"sha256"})

# Derived selection classes. Only CURRENT skips regeneration; every other
# class means the persisted evidence cannot be proven to describe the current
# extractor generation of the current source bytes.
PPTX_EVIDENCE_CURRENT = "current"
PPTX_EVIDENCE_STALE = "stale"
PPTX_EVIDENCE_PENDING = "pending"
PPTX_EVIDENCE_FAILED = "failed"
PPTX_EVIDENCE_UNKNOWN_LEGACY = "unknown_legacy"
# A live observation the caller could not make — the deck's bytes or the
# extraction artifact's digest — so the receipt cannot be proven to describe
# what is on disk now.
PPTX_EVIDENCE_UNVERIFIED = "unverified"
QR_CODE_REQUIRED_FIELDS = frozenset(
    {
        "talk_slug",
        "target_url",
        "shortener",
        "short_path",
        "short_url",
        "shortener_link_id",
        "qr_png_rel_path",
        "created_at",
        "updated_at",
    }
)
# Schema v2 records every generated PNG, not just the first, and binds each to
# the exact path written plus a SHA-256 so catalog validation can tell the
# intended artifact from a stale replacement.
QR_CODE_V2_REQUIRED_FIELDS = QR_CODE_REQUIRED_FIELDS | frozenset({"artifacts"})
QR_ARTIFACT_REQUIRED_FIELDS = frozenset({"path", "path_root", "sha256", "bg_hex"})
QR_ARTIFACT_PATH_ROOTS = frozenset({"deck_dir", "cwd", "absolute"})
RESOURCE_REQUIRED_FIELDS = frozenset({"talk_slug", "item_count", "category_breakdown"})
THUMBNAIL_REQUIRED_FIELDS = frozenset(
    {
        "talk_slug",
        "youtube_url",
        "source_slide_num",
        "speaker_photo_used",
        "thumbnail_path",
        "shownotes_thumbnail_path",
        "dimensions",
        "file_size_kb",
        "created_at",
        "approved",
    }
)
CONFIRMED_INTENT_REQUIRED_FIELDS = frozenset({"pattern", "intent", "rule", "note"})
CONFIRMED_INTENT_OPTIONAL_FIELDS = frozenset(
    {
        "confirmed_date",
        "source_talk",
        "source_talks",
        "talk",
        "retrofit_targets",
    }
)
SOURCE_REJECTION_REQUIRED_FIELDS = frozenset(
    {"source_type", "url", "reason", "evidence", "verified_at"}
)
# v1 lived on the talk record, so it carried no owning filename.
LEGACY_SOURCE_TITLE_EQUIVALENCE_REQUIRED_FIELDS = frozenset(
    {
        "video_id",
        "catalog_title",
        "provider_title",
        "reason",
        "evidence",
        "verified_at",
    }
)
MARKDOWN_DECK_REQUIRED_FIELDS = frozenset({"talk_filename", "deck_source_path"})
# Every flavor this toolkit renders — Slidev, presenterm, Marp, reveal-md —
# authors markdown, so a deck source named with any other suffix is a mistyped
# path rather than a deck.
MARKDOWN_DECK_SOURCE_SUFFIXES = frozenset({".md", ".markdown"})
SOURCE_TITLE_EQUIVALENCE_REQUIRED_FIELDS = frozenset(
    {
        "talk_filename",
        "video_id",
        "catalog_title",
        "provider_title",
        "reason",
        "evidence",
        "verified_at",
    }
)
# Why an owner accepted a provider title the comparator cannot reach. Closed on
# purpose: a free-text reason would turn the ledger into a place to wave through
# any mismatch, which is the wrong-delivery detection this ledger sits next to.
SOURCE_TITLE_EQUIVALENCE_REASONS = frozenset(
    {"cross_language_title", "provider_retitled"}
)
LEGACY_IMPROVEMENT_GOAL_REQUIRED_FIELDS = frozenset(
    {
        "id",
        "issue",
        "kind",
        "antipattern_id",
        "metric",
        "baseline_value",
        "target",
        "set_date",
        "set_by",
        "status",
        "current_value",
        "last_checked",
        "checked_by",
    }
)
IMPROVEMENT_GOAL_REQUIRED_FIELDS = frozenset(
    {
        *LEGACY_IMPROVEMENT_GOAL_REQUIRED_FIELDS,
        "verification_state",
        "verification_reasons",
        "supersedes_goal_id",
        "baseline_provenance",
    }
)


class TrackingDatabaseError(ValueError):
    """The tracking database cannot be read or migrated safely."""


class TrackingDatabaseConfigExclusionsError(TrackingDatabaseError):
    """The config-owned PPTX directory-exclusion field is invalid."""


class PptxVisualEvidenceError(TrackingDatabaseError):
    """A persisted extraction receipt is malformed.

    ``reason_code`` is the stable classification. The message names the exact
    field and the rejected value, which is what an operator fixing a rejected
    WRITE needs — but a reader surfacing a rejected persisted record must
    report the code and its neutral prose instead, because the rejected value
    came out of the database (`no-secrets` -> Logging).
    """

    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


# Closed, value-neutral prose per receipt reason code.
PPTX_VISUAL_EVIDENCE_DIAGNOSTICS = {
    "receipt_not_object": "visual evidence must be an object or null",
    "receipt_shape_invalid": "visual evidence has an invalid field set",
    "outcome_invalid": "visual evidence outcome is not a supported value",
    "extractor_schema_version_invalid": (
        "visual evidence extractor schema version is not a positive integer"
    ),
    "pipeline_version_invalid": "visual evidence pipeline version is not a string",
    "source_fingerprint_invalid": "visual evidence source fingerprint is malformed",
    "artifact_required": "visual evidence records a success but names no artifact",
    "artifact_forbidden": "visual evidence records a failure but names an artifact",
    "artifact_invalid": "visual evidence artifact identity is malformed",
    "mirror_mismatch": (
        "visual_extracted disagrees with the outcome its receipt records"
    ),
}
PPTX_VISUAL_EVIDENCE_FALLBACK = "visual evidence receipt is malformed"


@dataclass(frozen=True)
class TrackingDatabaseAssessment:
    """Compatibility decision for one in-memory database generation."""

    usable: bool
    state: str
    schema_version: int
    reason_codes: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "usable": self.usable,
            "state": self.state,
            "schema_version": self.schema_version,
            "accepted_schema_versions": sorted(
                READABLE_TRACKING_DATABASE_SCHEMA_VERSIONS
            ),
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class TrackingDatabaseMigration:
    """Pure migration result; callers own backup and replacement I/O."""

    database: dict[str, Any]
    changed: bool
    from_schema_version: int
    to_schema_version: int
    record_counts: Mapping[str, int]


def _empty_record_counts() -> dict[str, int]:
    """Return stable child-version insertion counters (root uses from/to)."""
    return {key: 0 for key in _RECORD_COUNT_KEYS}


def _record_version(
    record: Mapping[str, object], label: str, *, missing_version: int = 0
) -> int:
    version = record.get("schema_version", missing_version)
    if isinstance(version, bool) or not isinstance(version, int) or version < 0:
        raise TrackingDatabaseError(
            f"{label}.schema_version must be a non-negative integer, got {version!r}"
        )
    return version


def tracking_database_schema_version(database: object) -> int:
    if not isinstance(database, Mapping):
        raise TrackingDatabaseError("tracking database root must be a JSON object")
    return _record_version(database, "tracking database")


def _object_collection(
    database: Mapping[str, object], key: str, *, required: bool
) -> list[dict[str, Any]]:
    if key not in database:
        if required:
            raise TrackingDatabaseError(
                f"tracking database schema v{TRACKING_DATABASE_SCHEMA_VERSION} "
                f"requires a {key!r} array"
            )
        return []
    value = database[key]
    if not isinstance(value, list):
        raise TrackingDatabaseError(f"tracking database {key!r} must be an array")
    records: list[dict[str, Any]] = []
    for index, record in enumerate(value):
        if not isinstance(record, dict):
            raise TrackingDatabaseError(
                f"{key}[{index}] must be a JSON object, got {type(record).__name__}"
            )
        records.append(record)
    return records


def _version_reason(
    records: list[dict[str, Any]],
    *,
    label: str,
    accepted_versions: frozenset[int],
    require_explicit: bool,
    missing_version: int,
) -> str | None:
    for index, record in enumerate(records):
        if require_explicit and "schema_version" not in record:
            return f"{label}_schema_version_missing"
        version = _record_version(
            record,
            f"{label}[{index}]",
            missing_version=missing_version,
        )
        if version not in accepted_versions:
            return f"{label}_schema_version_unsupported"
    return None


def _require_closed_shape(
    record: Mapping[str, object],
    *,
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
    label: str,
) -> None:
    fields = set(record) - {"schema_version"}
    missing = set(required) - fields
    unknown = fields - set(required) - set(optional)
    if missing:
        raise TrackingDatabaseError(f"{label} is missing fields {sorted(missing)}")
    if unknown:
        raise TrackingDatabaseError(f"{label} has unknown fields {sorted(unknown)}")


def _validate_qr_artifacts(value: object, label: str) -> list[str]:
    """Every generated PNG is recorded, each bound to its exact written path.

    Returns the validated artifact paths in order, so a caller that needs one
    reads a proven value rather than re-indexing back into the raw record —
    `language-diagnostics` prefers a helper that proves the invariant once over
    an ignore at each use.
    """
    if not isinstance(value, list) or not value:
        raise TrackingDatabaseError(f"{label} must be a non-empty array")
    seen_paths = set()
    paths: list[str] = []
    for index, artifact in enumerate(value):
        item_label = f"{label}[{index}]"
        if not isinstance(artifact, Mapping):
            raise TrackingDatabaseError(f"{item_label} must be a JSON object")
        _require_closed_shape(
            artifact, required=QR_ARTIFACT_REQUIRED_FIELDS, label=item_label
        )
        path = _require_nonempty_string(artifact["path"], f"{item_label}.path")
        if path in seen_paths:
            raise TrackingDatabaseError(
                f"{item_label}.path {path!r} is recorded more than once"
            )
        seen_paths.add(path)
        paths.append(path)
        root = _require_nonempty_string(
            artifact["path_root"], f"{item_label}.path_root"
        )
        if root not in QR_ARTIFACT_PATH_ROOTS:
            raise TrackingDatabaseError(
                f"{item_label}.path_root must be one of "
                f"{sorted(QR_ARTIFACT_PATH_ROOTS)}, got {root!r}"
            )
        digest = _require_nonempty_string(artifact["sha256"], f"{item_label}.sha256")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise TrackingDatabaseError(
                f"{item_label}.sha256 must be 64 lowercase hex characters"
            )
        if artifact["bg_hex"] is not None:
            bg = _require_nonempty_string(artifact["bg_hex"], f"{item_label}.bg_hex")
            if len(bg) != 6 or any(c not in "0123456789abcdef" for c in bg):
                raise TrackingDatabaseError(
                    f"{item_label}.bg_hex must be 6 lowercase hex characters or null"
                )
    return paths


def _require_sha256_digest(value: object, label: str) -> str:
    digest = _require_nonempty_string(value, label)
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise TrackingDatabaseError(f"{label} must be 64 lowercase hex characters")
    return digest


def _validate_pptx_source_fingerprint(value: object, label: str) -> None:
    """Validate the exact-source-bytes binding written by the PPTX extractor."""
    if not isinstance(value, Mapping):
        raise TrackingDatabaseError(f"{label} must be an object")
    _require_closed_shape(
        value, required=PPTX_SOURCE_FINGERPRINT_REQUIRED_FIELDS, label=label
    )
    algorithm = _require_nonempty_string(value["algorithm"], f"{label}.algorithm")
    if algorithm not in PPTX_SOURCE_FINGERPRINT_ALGORITHMS:
        raise TrackingDatabaseError(
            f"{label}.algorithm must be one of "
            f"{sorted(PPTX_SOURCE_FINGERPRINT_ALGORITHMS)}, got {algorithm!r}"
        )
    _require_sha256_digest(value["digest"], f"{label}.digest")
    _require_exact_integer(value["size_bytes"], f"{label}.size_bytes", minimum=1)


@contextmanager
def _receipt_reason(reason_code: str):
    """Retype the shared field validators' errors with a receipt reason code."""
    try:
        yield
    except PptxVisualEvidenceError:
        raise
    except TrackingDatabaseError as exc:
        raise PptxVisualEvidenceError(str(exc), reason_code=reason_code) from exc


def validate_pptx_visual_evidence(value: object, label: str) -> bool:
    """Validate a v2 extraction receipt; return whether it recorded a success.

    ``None`` means no extraction has been attempted for this deck — distinct
    from a recorded failure, which carries the generation it failed under.
    """
    if value is None:
        return False
    if not isinstance(value, Mapping):
        raise PptxVisualEvidenceError(
            f"{label} must be an object or null", reason_code="receipt_not_object"
        )
    with _receipt_reason("receipt_shape_invalid"):
        _require_closed_shape(
            value, required=PPTX_VISUAL_EVIDENCE_REQUIRED_FIELDS, label=label
        )
    with _receipt_reason("outcome_invalid"):
        outcome = _require_nonempty_string(value["outcome"], f"{label}.outcome")
    if outcome not in PPTX_VISUAL_EVIDENCE_OUTCOMES:
        raise PptxVisualEvidenceError(
            f"{label}.outcome must be one of "
            f"{sorted(PPTX_VISUAL_EVIDENCE_OUTCOMES)}, got {outcome!r}",
            reason_code="outcome_invalid",
        )
    with _receipt_reason("extractor_schema_version_invalid"):
        _require_exact_integer(
            value["extractor_schema_version"],
            f"{label}.extractor_schema_version",
            minimum=1,
        )
    with _receipt_reason("pipeline_version_invalid"):
        _require_nonempty_string(value["pipeline_version"], f"{label}.pipeline_version")
    with _receipt_reason("source_fingerprint_invalid"):
        _validate_pptx_source_fingerprint(
            value["source_fingerprint"], f"{label}.source_fingerprint"
        )
    artifact = value["artifact"]
    succeeded = outcome == "succeeded"
    if artifact is None:
        # A succeeded extraction that names no artifact cannot be proven to
        # still exist, which is the ambiguity this schema removes.
        if succeeded:
            raise PptxVisualEvidenceError(
                f"{label}.artifact is required when outcome is 'succeeded'",
                reason_code="artifact_required",
            )
        return succeeded
    if not isinstance(artifact, Mapping):
        raise PptxVisualEvidenceError(
            f"{label}.artifact must be an object or null",
            reason_code="artifact_invalid",
        )
    if not succeeded:
        raise PptxVisualEvidenceError(
            f"{label}.artifact must be null when outcome is 'failed'",
            reason_code="artifact_forbidden",
        )
    with _receipt_reason("artifact_invalid"):
        _require_closed_shape(
            artifact,
            required=PPTX_VISUAL_ARTIFACT_REQUIRED_FIELDS,
            label=f"{label}.artifact",
        )
        _require_nonempty_string(artifact["path"], f"{label}.artifact.path")
        _require_sha256_digest(artifact["sha256"], f"{label}.artifact.sha256")
    return succeeded


def classify_pptx_visual_evidence(
    record: Mapping[str, object],
    *,
    extractor_schema_version: int,
    pipeline_version: str,
    observed_source_fingerprint: Mapping[str, object] | None,
    observed_artifact_digest: str | None,
) -> str:
    """Return the selection class for one catalog record's visual evidence.

    The one authority every consumer shares — owner writes, migration,
    preflight, queue selection, and profile reads all classify through this
    function so they cannot disagree about which decks need regeneration.

    Both live observations are required rather than defaulted: a stored receipt
    is a hint, not authority (`stateful-artifacts` -> Hints, Not Authority), so
    a caller must say what it saw on disk. ``observed_source_fingerprint`` is
    the PPTX as it exists now; ``observed_artifact_digest`` is the SHA-256 of
    the extraction artifact the receipt names. Passing ``None`` for either
    states that the observation could not be made, which yields
    ``PPTX_EVIDENCE_UNVERIFIED`` rather than letting stored metadata alone
    claim currency — a deleted or replaced artifact must not stay
    authoritative. Only ``PPTX_EVIDENCE_CURRENT`` may skip regeneration.
    """
    version = _record_version(
        record,
        "pptx_catalog record",
        missing_version=LEGACY_PPTX_CATALOG_RECORD_SCHEMA_VERSION,
    )
    if version == LEGACY_PPTX_CATALOG_RECORD_SCHEMA_VERSION:
        # A v1 record persisted no generation at all. Its bare
        # visual_extracted may refer to any extractor schema, so a true value
        # is unknown-generation evidence, never current evidence.
        if record.get("visual_extracted") is True:
            return PPTX_EVIDENCE_UNKNOWN_LEGACY
        return PPTX_EVIDENCE_PENDING
    if version not in _EVIDENCE_BOUND_PPTX_CATALOG_SCHEMA_VERSIONS:
        # A record newer than this reader accepts means the reader is lagging,
        # not that the record is legacy. Classifying it as pending would send
        # a deck back through extraction on the strength of a shape this
        # function cannot read; the caller must update instead.
        raise TrackingDatabaseError(
            f"pptx_catalog record schema_version {version} is newer than this "
            f"reader accepts (v{LEGACY_PPTX_CATALOG_RECORD_SCHEMA_VERSION}, "
            f"v{PPTX_CATALOG_EVIDENCE_BOUND_RECORD_SCHEMA_VERSION}, and "
            f"v{PPTX_CATALOG_RECORD_SCHEMA_VERSION}); update speaker-toolkit"
        )
    # Validate before trusting. A receipt is the licence to SKIP extraction, so
    # a malformed one must never classify as current: `succeeded` with a null
    # artifact, a bogus fingerprint, or a mirror flag that disagrees with the
    # outcome would otherwise skip a deck on evidence that cannot be proven.
    succeeded = validate_pptx_visual_evidence(
        record.get("visual_evidence"), "pptx_catalog record.visual_evidence"
    )
    if record.get("visual_extracted") != succeeded:
        raise PptxVisualEvidenceError(
            "pptx_catalog record.visual_extracted must mirror whether "
            "visual_evidence records a succeeded extraction",
            reason_code="mirror_mismatch",
        )
    evidence = record.get("visual_evidence")
    if evidence is None:
        return PPTX_EVIDENCE_PENDING
    if not isinstance(evidence, Mapping):
        raise TrackingDatabaseError("pptx_catalog.visual_evidence must be an object")
    if not succeeded:
        return PPTX_EVIDENCE_FAILED
    if (
        evidence.get("extractor_schema_version") != extractor_schema_version
        or evidence.get("pipeline_version") != pipeline_version
    ):
        return PPTX_EVIDENCE_STALE
    if observed_source_fingerprint is None:
        return PPTX_EVIDENCE_UNVERIFIED
    persisted = evidence.get("source_fingerprint")
    if not isinstance(persisted, Mapping):
        raise TrackingDatabaseError(
            "pptx_catalog.visual_evidence.source_fingerprint must be an object"
        )
    if any(
        persisted.get(field) != observed_source_fingerprint.get(field)
        for field in PPTX_SOURCE_FINGERPRINT_REQUIRED_FIELDS
    ):
        return PPTX_EVIDENCE_STALE
    if observed_artifact_digest is None:
        return PPTX_EVIDENCE_UNVERIFIED
    artifact = evidence.get("artifact")
    if not isinstance(artifact, Mapping):
        raise TrackingDatabaseError(
            "pptx_catalog.visual_evidence.artifact must be an object"
        )
    if artifact.get("sha256") != observed_artifact_digest:
        return PPTX_EVIDENCE_STALE
    return PPTX_EVIDENCE_CURRENT


def pptx_visual_evidence_needs_extraction(classification: str) -> bool:
    """Whether a classification requires (re)running the visual extractor."""
    if classification not in {
        PPTX_EVIDENCE_CURRENT,
        PPTX_EVIDENCE_STALE,
        PPTX_EVIDENCE_PENDING,
        PPTX_EVIDENCE_FAILED,
        PPTX_EVIDENCE_UNKNOWN_LEGACY,
        PPTX_EVIDENCE_UNVERIFIED,
    }:
        raise TrackingDatabaseError(
            f"unknown pptx visual-evidence classification {classification!r}"
        )
    return classification != PPTX_EVIDENCE_CURRENT


def _require_nonempty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise TrackingDatabaseError(f"{label} must be a non-empty trimmed string")
    return value


def _require_string(value: object, label: str) -> None:
    if not isinstance(value, str):
        raise TrackingDatabaseError(f"{label} must be a string")


def _require_optional_nonempty_string(value: object, label: str) -> None:
    if value is not None:
        _require_nonempty_string(value, label)


def _require_exact_integer(
    value: object,
    label: str,
    *,
    minimum: int = 0,
) -> int:
    if type(value) is not int or value < minimum:
        raise TrackingDatabaseError(
            f"{label} must be an integer greater than or equal to {minimum}"
        )
    return value


def _require_iso_date(value: object, label: str) -> None:
    date_text = _require_nonempty_string(value, label)
    try:
        parsed = dt.date.fromisoformat(date_text)
    except ValueError as exc:
        raise TrackingDatabaseError(
            f"{label} must be a canonical YYYY-MM-DD date"
        ) from exc
    if parsed.isoformat() != date_text:
        raise TrackingDatabaseError(f"{label} must be a canonical YYYY-MM-DD date")


def _require_string_array(
    value: object,
    label: str,
    *,
    nonempty: bool = False,
) -> None:
    if not isinstance(value, list) or (nonempty and not value):
        qualifier = "non-empty " if nonempty else ""
        raise TrackingDatabaseError(f"{label} must be a {qualifier}array of strings")
    seen: set[str] = set()
    for index, item in enumerate(value):
        _require_nonempty_string(item, f"{label}[{index}]")
        if item in seen:
            raise TrackingDatabaseError(f"{label} contains duplicate value {item!r}")
        seen.add(item)


def _validate_config_record(
    config: Mapping[str, object],
    *,
    version: int,
) -> None:
    """Validate the owner-versioned PPTX discovery configuration."""
    if version == CONFIG_RECORD_SCHEMA_VERSION and (
        "pptx_directory_exclusions" not in config
    ):
        raise TrackingDatabaseConfigExclusionsError(
            "config schema v2 requires pptx_directory_exclusions"
        )
    exclusions = config.get("pptx_directory_exclusions")
    if exclusions is None and "pptx_directory_exclusions" not in config:
        return
    try:
        validate_pptx_directory_exclusions(
            exclusions,
            label="config.pptx_directory_exclusions",
        )
    except PptxDiscoveryContractError as exc:
        raise TrackingDatabaseConfigExclusionsError(str(exc)) from exc


def _validate_improvement_goal(
    record: Mapping[str, object],
    *,
    version: int,
    label: str,
) -> None:
    required = (
        LEGACY_IMPROVEMENT_GOAL_REQUIRED_FIELDS
        if version == LEGACY_IMPROVEMENT_GOAL_RECORD_SCHEMA_VERSION
        else IMPROVEMENT_GOAL_REQUIRED_FIELDS
    )
    _require_closed_shape(record, required=required, label=label)
    for field in (
        "id",
        "issue",
        "metric",
        "baseline_value",
        "target",
        "set_by",
    ):
        _require_nonempty_string(record[field], f"{label}.{field}")
    _require_iso_date(record["set_date"], f"{label}.set_date")
    kind = _require_nonempty_string(record["kind"], f"{label}.kind")
    if kind not in {"antipattern", "underuse", "pacing", "other"}:
        raise TrackingDatabaseError(f"{label}.kind is unsupported")
    antipattern_id = record["antipattern_id"]
    if kind == "antipattern":
        _require_nonempty_string(antipattern_id, f"{label}.antipattern_id")
    elif antipattern_id is not None:
        raise TrackingDatabaseError(
            f"{label}.antipattern_id must be null unless kind is antipattern"
        )
    status = _require_nonempty_string(record["status"], f"{label}.status")
    if status not in {
        "active",
        "improving",
        "achieved",
        "stalled",
        "regressed",
        "retired",
    }:
        raise TrackingDatabaseError(f"{label}.status is unsupported")
    _require_string(record["current_value"], f"{label}.current_value")
    _require_optional_nonempty_string(record["last_checked"], f"{label}.last_checked")
    if record["last_checked"] is not None:
        _require_iso_date(record["last_checked"], f"{label}.last_checked")
    _require_optional_nonempty_string(record["checked_by"], f"{label}.checked_by")
    if (record["last_checked"] is None) != (record["checked_by"] is None):
        raise TrackingDatabaseError(
            f"{label}.last_checked and checked_by must both be null or both set"
        )
    if version == LEGACY_IMPROVEMENT_GOAL_RECORD_SCHEMA_VERSION:
        return

    verification_state = _require_nonempty_string(
        record["verification_state"],
        f"{label}.verification_state",
    )
    if verification_state not in {
        "pending",
        "current",
        "needs_rebaseline",
        "unverifiable",
    }:
        raise TrackingDatabaseError(f"{label}.verification_state is unsupported")
    _require_string_array(
        record["verification_reasons"],
        f"{label}.verification_reasons",
    )
    _require_optional_nonempty_string(
        record["supersedes_goal_id"],
        f"{label}.supersedes_goal_id",
    )
    provenance = record["baseline_provenance"]
    if not isinstance(provenance, Mapping):
        raise TrackingDatabaseError(f"{label}.baseline_provenance must be an object")
    _require_closed_shape(
        provenance,
        required=frozenset({"lane"}),
        optional=frozenset({"pattern_baseline"}),
        label=f"{label}.baseline_provenance",
    )
    lane = _require_nonempty_string(
        provenance["lane"],
        f"{label}.baseline_provenance.lane",
    )
    expected_lane = {
        "antipattern": "pattern_scoring",
        "underuse": "pattern_scoring",
        "pacing": "pacing",
        "other": "independent",
    }[kind]
    if lane != expected_lane:
        raise TrackingDatabaseError(
            f"{label}.baseline_provenance.lane must be {expected_lane!r}"
        )
    pattern_baseline = provenance.get("pattern_baseline")
    if kind in {"antipattern", "underuse"}:
        if not isinstance(pattern_baseline, Mapping):
            raise TrackingDatabaseError(
                f"{label}.baseline_provenance.pattern_baseline must be an object"
            )
    elif "pattern_baseline" in provenance:
        raise TrackingDatabaseError(
            f"{label}.baseline_provenance.pattern_baseline is valid only for "
            "pattern goals"
        )


def _validate_collection_record(
    collection: str,
    record: Mapping[str, object],
    *,
    label: str,
) -> None:
    if collection == "pptx_catalog":
        version = record.get(
            "schema_version", LEGACY_PPTX_CATALOG_RECORD_SCHEMA_VERSION
        )
        is_v3 = version == PPTX_CATALOG_RECORD_SCHEMA_VERSION
        is_v2 = version == PPTX_CATALOG_EVIDENCE_BOUND_RECORD_SCHEMA_VERSION
        if is_v3:
            required = PPTX_CATALOG_V3_REQUIRED_FIELDS
        elif is_v2:
            required = PPTX_CATALOG_V2_REQUIRED_FIELDS
        else:
            required = PPTX_CATALOG_REQUIRED_FIELDS
        _require_closed_shape(record, required=required, label=label)
        _require_nonempty_string(record["pptx_path"], f"{label}.pptx_path")
        talk_filename = record["talk_filename"]
        if talk_filename is not None:
            _require_nonempty_string(talk_filename, f"{label}.talk_filename")
        if type(record["matched"]) is not bool:
            raise TrackingDatabaseError(f"{label}.matched must be a boolean")
        if record["matched"] != (talk_filename is not None):
            raise TrackingDatabaseError(
                f"{label}.matched must equal whether talk_filename is non-null"
            )
        _require_exact_integer(record["slide_count"], f"{label}.slide_count")
        if type(record["visual_extracted"]) is not bool:
            raise TrackingDatabaseError(f"{label}.visual_extracted must be a boolean")
        if (is_v2 or is_v3) and not isinstance(
            record["visual_evidence"], (Mapping, type(None))
        ):
            raise TrackingDatabaseError(
                f"{label}.visual_evidence must be an object or null"
            )
        if is_v3:
            # Shape only, and only enough to keep a reader from mistaking an
            # unproven binding for a proven one. The binding's own semantics are
            # the writer's gate — see `_apply_record_pptx`.
            assessment = record["identity_assessment"]
            if talk_filename is None:
                if assessment is not None:
                    raise TrackingDatabaseError(
                        f"{label}.identity_assessment must be null when "
                        "talk_filename is null"
                    )
            elif not isinstance(assessment, Mapping):
                raise TrackingDatabaseError(
                    f"{label}.identity_assessment must be an object on a matched record"
                )
        # The receipt's own shape is NOT validated here. A malformed receipt is
        # per-record evidence trouble, not unusable owner state: failing the
        # whole assessment would make preflight refuse the vault over one bad
        # extraction record, contradicting the non-blocking contract. The
        # writer (`record_pptx`) and the classifier each validate it where it
        # matters — see validate_pptx_visual_evidence.
        return
    if collection == "qr_codes":
        version = record.get("schema_version", LEGACY_QR_CODE_RECORD_SCHEMA_VERSION)
        is_v2 = version == QR_CODE_RECORD_SCHEMA_VERSION
        _require_closed_shape(
            record,
            required=QR_CODE_V2_REQUIRED_FIELDS if is_v2 else QR_CODE_REQUIRED_FIELDS,
            label=label,
        )
        if is_v2:
            artifact_paths = _validate_qr_artifacts(
                record["artifacts"], f"{label}.artifacts"
            )
            # The documented v2 contract: qr_png_rel_path is the schema-v1
            # reader's view of the first artifact, so the two must agree.
            first = artifact_paths[0]
            if record["qr_png_rel_path"] != first:
                raise TrackingDatabaseError(
                    f"{label}.qr_png_rel_path must mirror artifacts[0].path "
                    f"({first!r}), got {record['qr_png_rel_path']!r}"
                )
        for field in (
            "talk_slug",
            "target_url",
            "shortener",
            "short_url",
            "qr_png_rel_path",
            "created_at",
            "updated_at",
        ):
            _require_nonempty_string(record[field], f"{label}.{field}")
        for field in ("short_path", "shortener_link_id"):
            if record[field] is not None:
                _require_nonempty_string(record[field], f"{label}.{field}")
        _require_iso_date(record["created_at"], f"{label}.created_at")
        _require_iso_date(record["updated_at"], f"{label}.updated_at")
        return
    if collection == "resources":
        _require_closed_shape(record, required=RESOURCE_REQUIRED_FIELDS, label=label)
        _require_nonempty_string(record["talk_slug"], f"{label}.talk_slug")
        item_count = _require_exact_integer(
            record["item_count"],
            f"{label}.item_count",
        )
        breakdown = record["category_breakdown"]
        if not isinstance(breakdown, Mapping):
            raise TrackingDatabaseError(f"{label}.category_breakdown must be an object")
        category_total = 0
        for category, count in breakdown.items():
            _require_nonempty_string(category, f"{label}.category_breakdown key")
            category_total += _require_exact_integer(
                count,
                f"{label}.category_breakdown[{category!r}]",
            )
        if item_count != category_total:
            raise TrackingDatabaseError(
                f"{label}.item_count must equal the category_breakdown total"
            )
        return
    if collection == "thumbnails":
        _require_closed_shape(record, required=THUMBNAIL_REQUIRED_FIELDS, label=label)
        for field in (
            "talk_slug",
            "youtube_url",
            "speaker_photo_used",
            "thumbnail_path",
            "shownotes_thumbnail_path",
        ):
            _require_nonempty_string(record[field], f"{label}.{field}")
        _require_exact_integer(
            record["source_slide_num"],
            f"{label}.source_slide_num",
            minimum=1,
        )
        dimensions = _require_nonempty_string(
            record["dimensions"],
            f"{label}.dimensions",
        )
        if re.fullmatch(r"[1-9][0-9]*x[1-9][0-9]*", dimensions) is None:
            raise TrackingDatabaseError(
                f"{label}.dimensions must use positive WIDTHxHEIGHT form"
            )
        _require_exact_integer(record["file_size_kb"], f"{label}.file_size_kb")
        _require_iso_date(record["created_at"], f"{label}.created_at")
        if type(record["approved"]) is not bool:
            raise TrackingDatabaseError(f"{label}.approved must be a boolean")
        return
    if collection == "confirmed_intents":
        _require_closed_shape(
            record,
            required=CONFIRMED_INTENT_REQUIRED_FIELDS,
            optional=CONFIRMED_INTENT_OPTIONAL_FIELDS,
            label=label,
        )
        for field in ("pattern", "intent", "rule"):
            _require_nonempty_string(record[field], f"{label}.{field}")
        _require_string(record["note"], f"{label}.note")
        if "confirmed_date" in record:
            _require_iso_date(record["confirmed_date"], f"{label}.confirmed_date")
        provenance_fields = {
            field
            for field in ("talk", "source_talk", "source_talks")
            if field in record
        }
        if len(provenance_fields) > 1:
            raise TrackingDatabaseError(
                f"{label} may use only one of talk, source_talk, or source_talks"
            )
        for field in ("talk", "source_talk"):
            if field in record:
                _require_nonempty_string(record[field], f"{label}.{field}")
        for field in ("source_talks", "retrofit_targets"):
            if field in record:
                _require_string_array(
                    record[field],
                    f"{label}.{field}",
                    nonempty=True,
                )
        return
    if collection == "improvement_goals":
        _validate_improvement_goal(
            record,
            version=LEGACY_IMPROVEMENT_GOAL_RECORD_SCHEMA_VERSION,
            label=label,
        )
        return
    raise AssertionError(f"no schema-v1 validator for {collection}")


def _validate_source_rejection(
    rejection: Mapping[str, object],
    *,
    label: str,
) -> None:
    _require_closed_shape(
        rejection,
        required=SOURCE_REJECTION_REQUIRED_FIELDS,
        label=label,
    )
    for field in ("url", "reason", "evidence"):
        _require_nonempty_string(rejection[field], f"{label}.{field}")
    source_type = _require_nonempty_string(
        rejection["source_type"],
        f"{label}.source_type",
    )
    if source_type not in {"video", "slides"}:
        raise TrackingDatabaseError(f"{label}.source_type must be video or slides")
    verified_at = _require_nonempty_string(
        rejection["verified_at"],
        f"{label}.verified_at",
    )
    try:
        parsed = dt.datetime.fromisoformat(verified_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TrackingDatabaseError(
            f"{label}.verified_at must be a timezone-aware ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TrackingDatabaseError(
            f"{label}.verified_at must be a timezone-aware ISO-8601 timestamp"
        )


def _validate_title_equivalence_shape(
    equivalence: Mapping[str, object],
    *,
    label: str,
    required: frozenset[str],
    version: int,
) -> None:
    """Validate one title equivalence against a named generation's shape."""
    _require_closed_shape(equivalence, required=required, label=label)
    # `_require_closed_shape` ignores `schema_version` for every record, so this
    # ledger checks it explicitly. A record whose generation this reader cannot
    # name must never be honored: what it suppresses is the wrong-delivery gate,
    # and a newer generation is unusable state rather than something to coerce.
    recorded = equivalence.get("schema_version")
    if (
        isinstance(recorded, bool)
        or not isinstance(recorded, int)
        or recorded != version
    ):
        raise TrackingDatabaseError(f"{label}.schema_version must be {version}")
    for field in sorted(required - {"reason", "verified_at"}):
        _require_nonempty_string(equivalence[field], f"{label}.{field}")
    reason = _require_nonempty_string(equivalence["reason"], f"{label}.reason")
    if reason not in SOURCE_TITLE_EQUIVALENCE_REASONS:
        raise TrackingDatabaseError(
            f"{label}.reason must be one of {sorted(SOURCE_TITLE_EQUIVALENCE_REASONS)}"
        )
    verified_at = _require_nonempty_string(
        equivalence["verified_at"],
        f"{label}.verified_at",
    )
    try:
        parsed = dt.datetime.fromisoformat(verified_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TrackingDatabaseError(
            f"{label}.verified_at must be a timezone-aware ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TrackingDatabaseError(
            f"{label}.verified_at must be a timezone-aware ISO-8601 timestamp"
        )


def validate_markdown_deck(
    record: Mapping[str, object],
    *,
    label: str,
) -> None:
    """Validate one registered markdown deck source.

    The record names the markdown file a talk's deck was authored in. It is
    kept because registering a render destroys the only other trace of it: the
    repair that binds `slides/<talk>.pdf` moves `slide_source` from "markdown"
    to "pdf", correctly — the talk now has readable slides — and after that no
    field says the deck was ever markdown. The next render, after the deck
    gained slides, would begin by hunting for the file.

    The locator goes through `classify_artifact_locator`, the same lexical
    contract every other persisted artifact path uses, so a NUL byte, a `~`,
    a `..` segment, an ambiguous `//`, and a Windows reserved name are refused
    here by one shared reader rather than by a private opinion about paths.
    A native absolute value is the ordinary case, since these decks live one
    git repo per talk; a relative one is vault-root-relative, like `pptx_path`.

    Existence is not checked. The deck's repo need not be on this machine, so
    an absent file is the renderer's loud failure at render time, never a
    silent reason to refuse the whole database.
    """
    _require_closed_shape(
        record,
        required=MARKDOWN_DECK_REQUIRED_FIELDS,
        label=label,
    )
    # `_require_closed_shape` ignores `schema_version` for every record, so the
    # generation is checked explicitly. A record this reader cannot name must
    # refuse rather than be coerced into the current shape.
    recorded = record.get("schema_version")
    if (
        isinstance(recorded, bool)
        or not isinstance(recorded, int)
        or recorded != MARKDOWN_DECK_RECORD_SCHEMA_VERSION
    ):
        raise TrackingDatabaseError(
            f"{label}.schema_version must be {MARKDOWN_DECK_RECORD_SCHEMA_VERSION}"
        )
    _require_nonempty_string(record["talk_filename"], f"{label}.talk_filename")
    value = _require_nonempty_string(
        record["deck_source_path"],
        f"{label}.deck_source_path",
    )
    try:
        classify_artifact_locator(value)
    except ArtifactLocatorError as exc:
        raise TrackingDatabaseError(
            f"{label}.deck_source_path is not a usable artifact locator "
            f"({exc.reason_code}): {value!r}"
        ) from exc
    if value.endswith("/"):
        raise TrackingDatabaseError(
            f"{label}.deck_source_path ends in '/', which names a directory: {value!r}"
        )
    name = PurePosixPath(value).name
    suffix = PurePosixPath(name).suffix
    if not suffix or name == suffix:
        raise TrackingDatabaseError(
            f"{label}.deck_source_path must name a deck file, not a directory: "
            f"{value!r}"
        )
    if suffix.lower() not in MARKDOWN_DECK_SOURCE_SUFFIXES:
        raise TrackingDatabaseError(
            f"{label}.deck_source_path must name a markdown deck source "
            f"({', '.join(sorted(MARKDOWN_DECK_SOURCE_SUFFIXES))}), not {name!r}"
        )


def validate_source_title_equivalence(
    equivalence: Mapping[str, object],
    *,
    label: str,
) -> None:
    """Validate one current-generation owner-reviewed title equivalence.

    The record pins BOTH titles the owner read — the catalog title and the
    provider title. An equivalence is a judgment about one specific pair, so
    either side changing retires it: a provider that retitles the video, and a
    catalog title edited after the review, both re-gate instead of riding a
    stale approval.
    """
    _validate_title_equivalence_shape(
        equivalence,
        label=label,
        required=SOURCE_TITLE_EQUIVALENCE_REQUIRED_FIELDS,
        version=SOURCE_TITLE_EQUIVALENCE_RECORD_SCHEMA_VERSION,
    )


def validate_legacy_source_title_equivalence(
    equivalence: Mapping[str, object],
    *,
    label: str,
) -> None:
    """Validate one v1 equivalence, which lived on the talk and named no talk.

    Migration validates against this before lifting anything: stamping the
    current generation onto an unchecked record would coerce a malformed one
    into apparent validity, and silently rewrite a newer generation this reader
    cannot interpret.
    """
    _validate_title_equivalence_shape(
        equivalence,
        label=label,
        required=LEGACY_SOURCE_TITLE_EQUIVALENCE_REQUIRED_FIELDS,
        version=LEGACY_SOURCE_TITLE_EQUIVALENCE_RECORD_SCHEMA_VERSION,
    )


def _validate_talk_observation_shape(
    talk: Mapping[str, object],
    index: int,
    *,
    talk_version: int,
) -> None:
    observations = talk.get("pattern_observations")
    if (
        talk_version > LEGACY_TALK_RECORD_SCHEMA_VERSION
        and observations is not None
        and not isinstance(observations, Mapping)
    ):
        raise TrackingDatabaseError(
            f"talks[{index}].pattern_observations must be a JSON object"
        )


def _validate_record_identities(database: Mapping[str, object]) -> None:
    identity_specs = (
        ("talks", "filename"),
        ("pptx_catalog", "pptx_path"),
        ("qr_codes", "talk_slug"),
        ("resources", "talk_slug"),
        ("thumbnails", "talk_slug"),
        ("confirmed_intents", "pattern"),
        ("improvement_goals", "id"),
    )
    for collection, field in identity_specs:
        if collection not in database:
            continue
        records = _object_collection(database, collection, required=False)
        seen: set[str] = set()
        for index, record in enumerate(records):
            identity = record.get(field)
            if not isinstance(identity, str) or not identity.strip():
                raise TrackingDatabaseError(
                    f"{collection}[{index}].{field} must be a non-empty string"
                )
            if identity in seen:
                qualifier = "talk " if collection == "talks" else ""
                raise TrackingDatabaseError(
                    f"{collection} contains duplicate {qualifier}{field} {identity!r}"
                )
            seen.add(identity)


def assess_tracking_database(database: object) -> TrackingDatabaseAssessment:
    """Assess legacy/current compatibility without mutating ``database``.

    Malformed JSON shapes raise.  Unsupported future generations return an
    explicit no-usable-prior-state decision so non-owner readers can fail
    closed without treating a lagging reader as a migration opportunity.
    """
    if not isinstance(database, Mapping):
        raise TrackingDatabaseError("tracking database root must be a JSON object")
    root_version_is_explicit = "schema_version" in database
    root_version = tracking_database_schema_version(database)
    if root_version not in READABLE_TRACKING_DATABASE_SCHEMA_VERSIONS or (
        root_version_is_explicit
        and root_version == LEGACY_TRACKING_DATABASE_SCHEMA_VERSION
    ):
        return TrackingDatabaseAssessment(
            usable=False,
            state="unsupported",
            schema_version=root_version,
            reason_codes=("tracking_database_schema_version_unsupported",),
        )

    current = root_version == TRACKING_DATABASE_SCHEMA_VERSION
    if current and "config" not in database:
        raise TrackingDatabaseError(
            f"tracking database schema v{TRACKING_DATABASE_SCHEMA_VERSION} "
            "requires a 'config' object"
        )
    config = database.get("config", {})
    if not isinstance(config, Mapping):
        raise TrackingDatabaseError("tracking database 'config' must be an object")
    collections = {
        key: _object_collection(database, key, required=current or key == "talks")
        for key in _TOP_LEVEL_COLLECTIONS
    }

    reasons: list[str] = []
    if current and "schema_version" not in config:
        reasons.append("config_schema_version_missing")
    config_version = _record_version(
        config,
        "config",
        missing_version=LEGACY_CONFIG_RECORD_SCHEMA_VERSION,
    )
    if config_version not in {
        LEGACY_CONFIG_RECORD_SCHEMA_VERSION,
        CONFIG_RECORD_SCHEMA_VERSION,
    }:
        reasons.append("config_schema_version_unsupported")

    accepted_versions_by_collection = {
        "talks": frozenset(
            range(
                LEGACY_TALK_RECORD_SCHEMA_VERSION,
                TALK_RECORD_SCHEMA_VERSION + 1,
            )
        ),
        "pptx_catalog": frozenset(
            {
                LEGACY_PPTX_CATALOG_RECORD_SCHEMA_VERSION,
                *_EVIDENCE_BOUND_PPTX_CATALOG_SCHEMA_VERSIONS,
            }
        ),
        "qr_codes": frozenset(
            {
                LEGACY_QR_CODE_RECORD_SCHEMA_VERSION,
                QR_CODE_RECORD_SCHEMA_VERSION,
            }
        ),
        "resources": frozenset({RESOURCE_RECORD_SCHEMA_VERSION}),
        "thumbnails": frozenset({THUMBNAIL_RECORD_SCHEMA_VERSION}),
        "confirmed_intents": frozenset({CONFIRMED_INTENT_RECORD_SCHEMA_VERSION}),
        "improvement_goals": frozenset(
            {
                LEGACY_IMPROVEMENT_GOAL_RECORD_SCHEMA_VERSION,
                IMPROVEMENT_GOAL_RECORD_SCHEMA_VERSION,
            }
        ),
    }
    for key, records in collections.items():
        reason = _version_reason(
            records,
            label=key,
            accepted_versions=accepted_versions_by_collection[key],
            require_explicit=current,
            missing_version=(
                LEGACY_TALK_RECORD_SCHEMA_VERSION
                if key == "talks"
                else LEGACY_IMPROVEMENT_GOAL_RECORD_SCHEMA_VERSION
                if key == "improvement_goals"
                else 1
            ),
        )
        if reason is not None:
            reasons.append(reason)

    # A future or explicitly ambiguous top-level owner record may have an
    # entirely different identity and nested shape.  Never interpret it with
    # the old schema merely to produce a more detailed error.
    if reasons:
        return TrackingDatabaseAssessment(
            usable=False,
            state="unsupported",
            schema_version=root_version,
            reason_codes=tuple(sorted(set(reasons))),
        )

    _validate_config_record(config, version=config_version)

    accepted_rejection_versions = frozenset({SOURCE_REJECTION_RECORD_SCHEMA_VERSION})
    supported_talks: list[Mapping[str, object]] = []
    for talk_index, talk in enumerate(collections["talks"]):
        talk_version = _record_version(
            talk,
            f"talks[{talk_index}]",
            missing_version=LEGACY_TALK_RECORD_SCHEMA_VERSION,
        )
        if talk_version not in accepted_versions_by_collection["talks"]:
            continue
        supported_talks.append(talk)
        observations = talk.get("pattern_observations")
        if isinstance(observations, Mapping) and (
            "evidence_schema_version" in observations
        ):
            evidence_version = observations["evidence_schema_version"]
            if (
                isinstance(evidence_version, bool)
                or not isinstance(evidence_version, int)
                or evidence_version < 0
            ):
                raise TrackingDatabaseError(
                    f"talks[{talk_index}].pattern_observations."
                    "evidence_schema_version must be a non-negative integer, "
                    f"got {evidence_version!r}"
                )
            if evidence_version not in _READABLE_PATTERN_EVIDENCE_SCHEMA_VERSIONS:
                reasons.append("pattern_evidence_schema_version_unsupported")

        rejections = talk.get("source_rejections", [])
        if not isinstance(rejections, list):
            continue
        for rejection_index, rejection in enumerate(rejections):
            if not isinstance(rejection, Mapping):
                continue
            if current and "schema_version" not in rejection:
                reasons.append("source_rejections_schema_version_missing")
                break
            rejection_version = _record_version(
                rejection,
                f"talks[{talk_index}].source_rejections[{rejection_index}]",
                missing_version=SOURCE_REJECTION_RECORD_SCHEMA_VERSION,
            )
            if rejection_version not in accepted_rejection_versions:
                reasons.append("source_rejections_schema_version_unsupported")
                break

    try:
        reasons.extend(classify_queue_claim_versions(supported_talks))
    except QueueClaimContractError as exc:
        raise TrackingDatabaseError(str(exc)) from exc

    # The independent nested version gates have now classified every shape
    # that this reader can safely understand.  Future state stops here.
    if reasons:
        return TrackingDatabaseAssessment(
            usable=False,
            state="unsupported",
            schema_version=root_version,
            reason_codes=tuple(sorted(set(reasons))),
        )

    _validate_record_identities(database)

    for key in (
        "pptx_catalog",
        "qr_codes",
        "resources",
        "thumbnails",
        "confirmed_intents",
        "improvement_goals",
    ):
        # Validate every version this reader accepts. Naming versions
        # individually here meant a collection lost its shape validation the
        # moment it bumped past the named version, silently — the accepted-set
        # lookup cannot drift from the gate above that produced it.
        accepted = accepted_versions_by_collection[key]
        for index, record in enumerate(collections[key]):
            version = _record_version(
                record,
                f"{key}[{index}]",
                missing_version=1,
            )
            if version not in accepted:
                continue
            if key == "improvement_goals":
                _validate_improvement_goal(
                    record,
                    version=version,
                    label=f"{key}[{index}]",
                )
            else:
                _validate_collection_record(key, record, label=f"{key}[{index}]")

    for talk_index, talk in enumerate(collections["talks"]):
        talk_version = _record_version(
            talk,
            f"talks[{talk_index}]",
            missing_version=LEGACY_TALK_RECORD_SCHEMA_VERSION,
        )
        _validate_talk_observation_shape(
            talk,
            talk_index,
            talk_version=talk_version,
        )
        rejections = talk.get("source_rejections", [])
        if not isinstance(rejections, list):
            raise TrackingDatabaseError(
                f"talks[{talk_index}].source_rejections must be an array"
            )
        for rejection_index, rejection in enumerate(rejections):
            if not isinstance(rejection, Mapping):
                raise TrackingDatabaseError(
                    f"talks[{talk_index}].source_rejections[{rejection_index}] "
                    "must be a JSON object"
                )
            _validate_source_rejection(
                rejection,
                label=f"talks[{talk_index}].source_rejections[{rejection_index}]",
            )

    # Validated in the assessment rather than only at the writer: an equivalence
    # suppresses the wrong-delivery title gate, so a hand-edited or malformed
    # record must refuse the database instead of quietly passing a talk.
    equivalences = database.get("source_title_equivalences", [])
    if not isinstance(equivalences, list):
        raise TrackingDatabaseError("source_title_equivalences must be an array")
    known_filenames = {
        talk.get("filename")
        for talk in collections["talks"]
        if isinstance(talk, Mapping)
    }
    for index, equivalence in enumerate(equivalences):
        if not isinstance(equivalence, Mapping):
            raise TrackingDatabaseError(
                f"source_title_equivalences[{index}] must be a JSON object"
            )
        validate_source_title_equivalence(
            equivalence,
            label=f"source_title_equivalences[{index}]",
        )
        if equivalence["talk_filename"] not in known_filenames:
            raise TrackingDatabaseError(
                f"source_title_equivalences[{index}].talk_filename names no talk: "
                f"{equivalence['talk_filename']!r}"
            )

    # Validated in the assessment, like the equivalences above: a deck record
    # names the file a re-render reads, so a malformed or orphaned one must
    # refuse the database rather than send a renderer at a path no owner wrote.
    decks = database.get("markdown_decks", [])
    if not isinstance(decks, list):
        raise TrackingDatabaseError("markdown_decks must be an array")
    claimed_by_talk: set[object] = set()
    for index, record in enumerate(decks):
        if not isinstance(record, Mapping):
            raise TrackingDatabaseError(
                f"markdown_decks[{index}] must be a JSON object"
            )
        validate_markdown_deck(record, label=f"markdown_decks[{index}]")
        talk_filename = record["talk_filename"]
        if talk_filename not in known_filenames:
            raise TrackingDatabaseError(
                f"markdown_decks[{index}].talk_filename names no talk: "
                f"{talk_filename!r}"
            )
        # One deck per talk. A second record would leave every reader picking
        # between two paths with nothing in the data saying which is current.
        if talk_filename in claimed_by_talk:
            raise TrackingDatabaseError(
                f"markdown_decks[{index}] is a second deck for "
                f"{talk_filename!r}; a talk has one authored deck source"
            )
        claimed_by_talk.add(talk_filename)

    try:
        # Assessment intentionally admits claim/status drift so schema-0 queue
        # recovery can reach its dedicated repair transition.  Every other
        # claim/history/generation/batch invariant remains mandatory.
        validate_queue_claim_database(
            database,
            allow_claim_status_drift=True,
        )
    except QueueClaimContractError as exc:
        raise TrackingDatabaseError(str(exc)) from exc

    return TrackingDatabaseAssessment(
        usable=True,
        state=(
            "current"
            if current and config_version == CONFIG_RECORD_SCHEMA_VERSION
            else "legacy"
        ),
        schema_version=root_version,
        reason_codes=(),
    )


def require_current_tracking_database(database: object) -> dict[str, Any]:
    """Return a current database or raise with owner-migration guidance."""
    version = tracking_database_schema_version(database)
    try:
        assessment = assess_tracking_database(database)
    except TrackingDatabaseError as exc:
        if version == TRACKING_DATABASE_SCHEMA_VERSION:
            raise TrackingDatabaseError(
                f"tracking database schema v{TRACKING_DATABASE_SCHEMA_VERSION} "
                "has malformed owner-managed state; "
                "update speaker-toolkit or repair the owner-managed state. Schema "
                f"migration will refuse this state ({exc})"
            ) from exc
        raise
    if assessment.usable and assessment.state == "current":
        if not isinstance(database, dict):
            raise TrackingDatabaseError("tracking database root must be a JSON object")
        return database
    if assessment.usable and assessment.state == "legacy":
        raise TrackingDatabaseError(
            "tracking database has owner-managed legacy state; run "
            "skills/vault-ingress/scripts/migrate-tracking-database.py first"
        )
    reasons = ", ".join(assessment.reason_codes) or "unsupported_owner_state"
    raise TrackingDatabaseError(
        f"tracking database schema v{assessment.schema_version} contains "
        "unsupported owner-managed state; update speaker-toolkit or repair the "
        "owner-managed state. Schema migration will refuse this state "
        f"({reasons})"
    )


def _active_claim_filenames(talks: list[dict[str, Any]]) -> list[str]:
    active: list[str] = []
    for index, talk in enumerate(talks):
        claim = talk.get("_queue_claim")
        if talk.get("status") == "reprocessing-inflight" or (
            isinstance(claim, Mapping) and claim.get("state") == "claimed"
        ):
            filename = talk.get("filename")
            active.append(filename if isinstance(filename, str) else f"talks[{index}]")
    return sorted(active)


def _migrate_talk_record(talk: dict[str, Any]) -> bool:
    """Make implicit v1 record versions explicit without changing evidence."""
    talk_version_added = "schema_version" not in talk
    rejections = talk.get("source_rejections", [])
    if isinstance(rejections, list):
        for rejection in rejections:
            if isinstance(rejection, dict) and "schema_version" not in rejection:
                rejection["schema_version"] = SOURCE_REJECTION_RECORD_SCHEMA_VERSION
    if talk_version_added:
        talk["schema_version"] = LEGACY_TALK_RECORD_SCHEMA_VERSION
    return talk_version_added


_RESTAMPABLE_TALK_RECORD_SCHEMA_VERSIONS = frozenset(
    {
        FLAT_SCORE_TALK_RECORD_SCHEMA_VERSION,
        PRE_TITLE_EQUIVALENCE_TALK_RECORD_SCHEMA_VERSION,
    }
)


def _migrate_title_equivalences(candidate: dict[str, Any]) -> int:
    """Lift v1 nested equivalences into the v2 top-level collection (#333).

    v1 recorded the ledger on the talk record, which bound an owner judgment to
    the talk's analysis generation. Readers now consult the collection only, so
    a v1 entry left in place would be ignored and its talk would re-gate on a
    title mismatch its owner had already approved.

    Every legacy ledger is validated before anything is removed: assessment no
    longer inspects the nested shape, so a malformed one discarded here would be
    destroyed with nothing left to report it. Returns the number of talks whose
    field was removed, empty ledgers included — removing one changes the
    database, and a migration that alters bytes while reporting no change breaks
    the no-op contract callers rely on.
    """
    talks = candidate.get("talks")
    if not isinstance(talks, list):
        return 0

    pending: list[tuple[dict[str, Any], list[Any]]] = []
    for index, talk in enumerate(talks):
        if not isinstance(talk, dict) or "source_title_equivalence" not in talk:
            continue
        nested = talk["source_title_equivalence"]
        label = f"talks[{index}].source_title_equivalence"
        if not isinstance(nested, list):
            raise TrackingDatabaseError(f"{label} must be an array")
        for entry_index, record in enumerate(nested):
            if not isinstance(record, Mapping):
                raise TrackingDatabaseError(
                    f"{label}[{entry_index}] must be a JSON object"
                )
            # Checked as a v1 record before anything is removed. Stamping the
            # current generation onto an unvalidated record would coerce a
            # malformed one into apparent validity and silently rewrite a newer
            # generation this reader cannot interpret.
            validate_legacy_source_title_equivalence(
                record,
                label=f"{label}[{entry_index}]",
            )
        pending.append((talk, nested))
    if not pending:
        return 0

    collection = candidate.get("source_title_equivalences")
    if not isinstance(collection, list):
        collection = []
    for talk, nested in pending:
        del talk["source_title_equivalence"]
        for record in nested:
            lifted = dict(record)
            lifted.setdefault("talk_filename", talk.get("filename"))
            lifted["schema_version"] = SOURCE_TITLE_EQUIVALENCE_RECORD_SCHEMA_VERSION
            collection.append(lifted)
    # The lifted records are what every reader will consult, so they are checked
    # in their new shape rather than trusted because their inputs passed.
    for index, record in enumerate(collection):
        validate_source_title_equivalence(
            record,
            label=f"source_title_equivalences[{index}]",
        )
    candidate["source_title_equivalences"] = collection
    return len(pending)


def _restamp_talk_records(candidate: dict[str, Any]) -> int:
    """Restamp analysed talk records to the current record shape (#299, #333).

    A RESTAMP, never a rescore. The v6 shape admits a `pattern_score_basis` and
    a fractional `pattern_score`; a stored v5 record has neither, and computing
    them here would recompute a score under arithmetic its worker never used —
    the silent reinterpretation `stateful-artifacts` forbids and the exact thing
    `_validate_score` refuses on the way in.

    So the record's SHAPE advances and its SCORE does not. The talk keeps
    `pattern_scoring_schema_version: 5`, which is the truth about the arithmetic
    behind its number, and `partition_pattern_scoring_cohort` therefore excludes
    it as a generation mismatch and requeues it. That is the reparse, and this
    migration is what makes it mechanical rather than remembered.

    Without the restamp every stored talk would be unmutatable: the owner writer
    requires the exact current talk schema before any mutation, so the bump
    alone would lock the database until this ran.

    v6 to v7 (#333) was introduced for an owner ledger that has since moved to
    its own top-level collection, so v7 adds no field a v6 record lacks and the
    restamp carries it forward untouched. Only records already holding the
    analysis v7 implies are restampable; an earlier generation reaches the
    current shape by being reanalysed, never by being stamped, which is why this
    set is not simply "every version below current".
    """
    talks = candidate.get("talks")
    if not isinstance(talks, list):
        return 0
    restamped = 0
    for talk in talks:
        if not isinstance(talk, dict):
            continue
        if talk.get("schema_version") not in _RESTAMPABLE_TALK_RECORD_SCHEMA_VERSIONS:
            continue
        talk["schema_version"] = TALK_RECORD_SCHEMA_VERSION
        restamped += 1
    return restamped


def _require_no_active_writers(talks: list[Any]) -> None:
    """Refuse to change persisted shape while a writer owns the database."""
    active = _active_claim_filenames(talks)
    if active:
        raise TrackingDatabaseError(
            "tracking database has active queue writers; recover or complete these "
            f"claims before migration: {active}"
        )


def _migrate_pptx_catalog_records(candidate: dict[str, Any]) -> int:
    """Upgrade evidence-bound catalog records to the identity-bound shape.

    A v2 record's talk binding was made before any assessment existed, so
    migration cannot prove it. It must not invent a `matched` verdict — that
    would forge the evidence the v3 shape exists to require — and it must not
    call the binding wrong, because most legacy bindings are right. Stamping
    `review_required` upgrades the record, preserves the binding, and stops
    anything downstream from treating it as proven until someone looks.

    v1 records stay at v1: they carry no `visual_evidence` either, and the
    established position is that migration preserves such a record rather than
    inventing a binding for it.
    """
    records = candidate.get("pptx_catalog")
    if not isinstance(records, list):
        return 0
    migrated = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        if (
            record.get("schema_version")
            != PPTX_CATALOG_EVIDENCE_BOUND_RECORD_SCHEMA_VERSION
        ):
            continue
        pptx_path = record.get("pptx_path")
        if not isinstance(pptx_path, str) or not pptx_path.strip():
            continue
        record["schema_version"] = PPTX_CATALOG_RECORD_SCHEMA_VERSION
        record["identity_assessment"] = (
            unassessed_legacy_binding(pptx_path)
            if record.get("talk_filename") is not None
            else None
        )
        migrated += 1
    return migrated


def migrate_tracking_database(database: object) -> TrackingDatabaseMigration:
    """Build the deterministic owner migration to root v1/config v2."""
    assessment = assess_tracking_database(database)
    if not assessment.usable:
        raise TrackingDatabaseError(
            "tracking database cannot be migrated by this owner version: "
            + ", ".join(assessment.reason_codes)
        )
    if not isinstance(database, dict):
        raise TrackingDatabaseError("tracking database root must be a JSON object")

    candidate: dict[str, Any] = copy.deepcopy(database)
    talks = _object_collection(candidate, "talks", required=True)

    if assessment.state == "current":
        # A current ROOT does not mean current RECORDS. Returning on the root
        # version alone is how a record-level shape bump gets skipped for every
        # live database, since they all reached root v1 long ago — so the record
        # migrations run first and only a genuinely unchanged database takes the
        # no-op path.
        require_current_tracking_database(candidate)
        counts = _empty_record_counts()
        counts["pptx_catalog"] = _migrate_pptx_catalog_records(candidate)
        counts["source_title_equivalences"] = _migrate_title_equivalences(candidate)
        counts["talks"] = _restamp_talk_records(candidate)
        if any(counts.values()):
            # Guarded only once state would actually change. A no-op migration
            # must stay callable while a claim is live: Step 1 migrates before
            # Step 2 can recover a stranded claim, so refusing here would leave
            # an interrupted run unable to resume.
            _require_no_active_writers(talks)
        return TrackingDatabaseMigration(
            database=candidate,
            changed=any(counts.values()),
            from_schema_version=TRACKING_DATABASE_SCHEMA_VERSION,
            to_schema_version=TRACKING_DATABASE_SCHEMA_VERSION,
            record_counts=counts,
        )

    # Reaching here means the root or config shape moves, which is always a
    # state change.
    _require_no_active_writers(talks)
    root_version = tracking_database_schema_version(candidate)

    config = candidate.setdefault("config", {})
    if not isinstance(config, dict):
        raise TrackingDatabaseError("tracking database 'config' must be an object")
    counts = _empty_record_counts()
    config_version = _record_version(
        config,
        "config",
        missing_version=LEGACY_CONFIG_RECORD_SCHEMA_VERSION,
    )
    if config_version == LEGACY_CONFIG_RECORD_SCHEMA_VERSION:
        if "pptx_directory_exclusions" in config:
            try:
                exclusions = validate_pptx_directory_exclusions(
                    config["pptx_directory_exclusions"],
                    label="config.pptx_directory_exclusions",
                )
            except PptxDiscoveryContractError as exc:
                raise TrackingDatabaseConfigExclusionsError(str(exc)) from exc
        else:
            exclusions = list(DEFAULT_PPTX_DIRECTORY_EXCLUSIONS)
        config["pptx_directory_exclusions"] = exclusions
        config["schema_version"] = CONFIG_RECORD_SCHEMA_VERSION
        counts["config"] = 1

    # Ahead of the root-current return. A database at root v1 with a legacy
    # config takes that return, so a record migration placed after it would be
    # skipped for exactly the databases whose config still needed upgrading.
    counts["pptx_catalog"] += _migrate_pptx_catalog_records(candidate)
    counts["source_title_equivalences"] += _migrate_title_equivalences(candidate)
    counts["talks"] += _restamp_talk_records(candidate)

    if root_version == TRACKING_DATABASE_SCHEMA_VERSION:
        require_current_tracking_database(candidate)
        return TrackingDatabaseMigration(
            database=candidate,
            # Every record count, never a hand-listed subset: a flag that names
            # the collections it knows about goes stale the moment a migration
            # touches one it does not, and reports no-change over mutated
            # records.
            changed=any(counts.values()),
            from_schema_version=TRACKING_DATABASE_SCHEMA_VERSION,
            to_schema_version=TRACKING_DATABASE_SCHEMA_VERSION,
            record_counts=counts,
        )

    for talk in talks:
        prior_rejections = talk.get("source_rejections", [])
        if isinstance(prior_rejections, list):
            counts["source_rejections"] += sum(
                isinstance(record, dict) and "schema_version" not in record
                for record in prior_rejections
            )
        if _migrate_talk_record(talk):
            counts["talks"] += 1

    simple_collections = {
        # An unversioned pptx_catalog record persisted no extractor generation,
        # so it cannot satisfy the v2 shape and is stamped at the legacy
        # version. classify_pptx_visual_evidence reads any such record's
        # visual_extracted as unknown-generation evidence, never as current —
        # migration preserves the record rather than inventing a binding for it.
        "pptx_catalog": LEGACY_PPTX_CATALOG_RECORD_SCHEMA_VERSION,
        # An unversioned qr_codes record predates the v2 artifact receipts and
        # cannot satisfy the v2 shape, so it is stamped at the legacy version.
        # Only the QR writer produces v2 records, and it writes them complete.
        "qr_codes": LEGACY_QR_CODE_RECORD_SCHEMA_VERSION,
        "resources": RESOURCE_RECORD_SCHEMA_VERSION,
        "thumbnails": THUMBNAIL_RECORD_SCHEMA_VERSION,
        "confirmed_intents": CONFIRMED_INTENT_RECORD_SCHEMA_VERSION,
    }
    for key, schema_version in simple_collections.items():
        records = candidate.setdefault(key, [])
        if not isinstance(records, list):
            raise TrackingDatabaseError(f"tracking database {key!r} must be an array")
        for record in records:
            if not isinstance(record, dict):
                raise TrackingDatabaseError(
                    f"tracking database {key!r} has a non-object"
                )
            if "schema_version" not in record:
                record["schema_version"] = schema_version
                counts[key] += 1

    goals = candidate.setdefault("improvement_goals", [])
    if not isinstance(goals, list):
        raise TrackingDatabaseError(
            "tracking database 'improvement_goals' must be an array"
        )
    for index, goal in enumerate(goals):
        if not isinstance(goal, dict):
            raise TrackingDatabaseError("improvement_goals contains a non-object")
        _record_version(
            goal,
            f"improvement_goals[{index}]",
            missing_version=LEGACY_IMPROVEMENT_GOAL_RECORD_SCHEMA_VERSION,
        )
        if "schema_version" not in goal:
            goal["schema_version"] = LEGACY_IMPROVEMENT_GOAL_RECORD_SCHEMA_VERSION
            counts["improvement_goals"] += 1

    candidate["schema_version"] = TRACKING_DATABASE_SCHEMA_VERSION
    require_current_tracking_database(candidate)
    return TrackingDatabaseMigration(
        database=candidate,
        changed=True,
        # The generation actually read, not a hardcoded legacy 0. Every step
        # above is idempotent for a root v1 database — its records already carry
        # the versions the v0 path stamps — so v1 reaches v2 through the same
        # tail, and reporting it as having come from v0 would misname what was
        # migrated.
        from_schema_version=root_version,
        to_schema_version=TRACKING_DATABASE_SCHEMA_VERSION,
        record_counts=counts,
    )
