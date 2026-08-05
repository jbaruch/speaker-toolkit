"""Version and migration contract for ``tracking-database.json``.

``vault-ingress`` owns this artifact's shape and all migrations.  Other skills
may read the legacy and current generations during rollout.  They must never
rewrite a legacy generation or infer a migration from fields that happen to be
present.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import datetime as dt
import re
from typing import Any, Mapping

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


LEGACY_TRACKING_DATABASE_SCHEMA_VERSION = 0
TRACKING_DATABASE_SCHEMA_VERSION = 1
LEGACY_TALK_RECORD_SCHEMA_VERSION = 1
TALK_RECORD_SCHEMA_VERSION = 5
LEGACY_CONFIG_RECORD_SCHEMA_VERSION = 1
CONFIG_RECORD_SCHEMA_VERSION = 2
PPTX_CATALOG_RECORD_SCHEMA_VERSION = 1
QR_CODE_RECORD_SCHEMA_VERSION = 1
RESOURCE_RECORD_SCHEMA_VERSION = 1
THUMBNAIL_RECORD_SCHEMA_VERSION = 1
CONFIRMED_INTENT_RECORD_SCHEMA_VERSION = 1
SOURCE_REJECTION_RECORD_SCHEMA_VERSION = 1
LEGACY_IMPROVEMENT_GOAL_RECORD_SCHEMA_VERSION = 1
IMPROVEMENT_GOAL_RECORD_SCHEMA_VERSION = 2

READABLE_TRACKING_DATABASE_SCHEMA_VERSIONS = frozenset(
    {
        LEGACY_TRACKING_DATABASE_SCHEMA_VERSION,
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
    "source_rejections",
)

PPTX_CATALOG_REQUIRED_FIELDS = frozenset(
    {"pptx_path", "talk_filename", "matched", "slide_count", "visual_extracted"}
)
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
RESOURCE_REQUIRED_FIELDS = frozenset(
    {"talk_slug", "item_count", "category_breakdown"}
)
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
CONFIRMED_INTENT_REQUIRED_FIELDS = frozenset(
    {"pattern", "intent", "rule", "note"}
)
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
        raise TrackingDatabaseError(f"{label} must be a canonical YYYY-MM-DD date") from exc
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


def _validate_schema_one_record(
    collection: str,
    record: Mapping[str, object],
    *,
    label: str,
) -> None:
    if collection == "pptx_catalog":
        _require_closed_shape(
            record,
            required=PPTX_CATALOG_REQUIRED_FIELDS,
            label=label,
        )
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
            raise TrackingDatabaseError(
                f"{label}.visual_extracted must be a boolean"
            )
        return
    if collection == "qr_codes":
        _require_closed_shape(record, required=QR_CODE_REQUIRED_FIELDS, label=label)
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
            raise TrackingDatabaseError(
                f"{label}.category_breakdown must be an object"
            )
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
    if (
        root_version not in READABLE_TRACKING_DATABASE_SCHEMA_VERSIONS
        or (
            root_version_is_explicit
            and root_version == LEGACY_TRACKING_DATABASE_SCHEMA_VERSION
        )
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
        "pptx_catalog": frozenset({PPTX_CATALOG_RECORD_SCHEMA_VERSION}),
        "qr_codes": frozenset({QR_CODE_RECORD_SCHEMA_VERSION}),
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

    accepted_rejection_versions = frozenset(
        {SOURCE_REJECTION_RECORD_SCHEMA_VERSION}
    )
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
        for index, record in enumerate(collections[key]):
            version = _record_version(
                record,
                f"{key}[{index}]",
                missing_version=1,
            )
            if key == "improvement_goals" and version in {
                LEGACY_IMPROVEMENT_GOAL_RECORD_SCHEMA_VERSION,
                IMPROVEMENT_GOAL_RECORD_SCHEMA_VERSION,
            }:
                _validate_improvement_goal(
                    record,
                    version=version,
                    label=f"{key}[{index}]",
                )
            elif version == 1:
                _validate_schema_one_record(key, record, label=f"{key}[{index}]")

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
                "tracking database schema v1 has malformed owner-managed state; "
                "update speaker-toolkit or repair the owner-managed state. Schema "
                f"migration will refuse this state ({exc})"
            ) from exc
        raise
    if assessment.usable and assessment.state == "current":
        if not isinstance(database, dict):
            raise TrackingDatabaseError(
                "tracking database root must be a JSON object"
            )
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
            if (
                isinstance(rejection, dict)
                and "schema_version" not in rejection
            ):
                rejection["schema_version"] = SOURCE_REJECTION_RECORD_SCHEMA_VERSION
    if talk_version_added:
        talk["schema_version"] = LEGACY_TALK_RECORD_SCHEMA_VERSION
    return talk_version_added


def migrate_tracking_database(database: object) -> TrackingDatabaseMigration:
    """Build the deterministic owner migration to root v1/config v2."""
    assessment = assess_tracking_database(database)
    if not assessment.usable:
        raise TrackingDatabaseError(
            "tracking database cannot be migrated by this owner version: "
            + ", ".join(assessment.reason_codes)
        )
    if assessment.state == "current":
        current = require_current_tracking_database(database)
        return TrackingDatabaseMigration(
            database=copy.deepcopy(current),
            changed=False,
            from_schema_version=TRACKING_DATABASE_SCHEMA_VERSION,
            to_schema_version=TRACKING_DATABASE_SCHEMA_VERSION,
            record_counts=_empty_record_counts(),
        )
    if not isinstance(database, dict):
        raise TrackingDatabaseError("tracking database root must be a JSON object")

    candidate: dict[str, Any] = copy.deepcopy(database)
    root_version = tracking_database_schema_version(candidate)
    talks = _object_collection(candidate, "talks", required=True)
    active = _active_claim_filenames(talks)
    if active:
        raise TrackingDatabaseError(
            "tracking database has active queue writers; recover or complete these "
            f"claims before migration: {active}"
        )

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
                raise TrackingDatabaseError(str(exc)) from exc
        else:
            exclusions = list(DEFAULT_PPTX_DIRECTORY_EXCLUSIONS)
        config["pptx_directory_exclusions"] = exclusions
        config["schema_version"] = CONFIG_RECORD_SCHEMA_VERSION
        counts["config"] = 1

    if root_version == TRACKING_DATABASE_SCHEMA_VERSION:
        require_current_tracking_database(candidate)
        return TrackingDatabaseMigration(
            database=candidate,
            changed=bool(counts["config"]),
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
        "pptx_catalog": PPTX_CATALOG_RECORD_SCHEMA_VERSION,
        "qr_codes": QR_CODE_RECORD_SCHEMA_VERSION,
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
        from_schema_version=LEGACY_TRACKING_DATABASE_SCHEMA_VERSION,
        to_schema_version=TRACKING_DATABASE_SCHEMA_VERSION,
        record_counts=counts,
    )
