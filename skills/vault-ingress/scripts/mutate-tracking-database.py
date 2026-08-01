#!/usr/bin/env python3
"""Apply typed, expectation-bound owner mutations to tracking-database.json.

The default mode is a dry run.  ``--apply`` requires ``--expected-sha256`` from
that dry run (or the literal ``missing`` for initialization).  Every operation
declares the exact record or field value it expects, so a reviewed plan cannot
silently target a different logical state even when its file hash is current.
"""

from __future__ import annotations

import argparse
import copy
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, NoReturn

from tracking_database import (
    CONFIG_RECORD_SCHEMA_VERSION,
    CONFIRMED_INTENT_OPTIONAL_FIELDS,
    CONFIRMED_INTENT_RECORD_SCHEMA_VERSION,
    CONFIRMED_INTENT_REQUIRED_FIELDS as OWNER_CONFIRMED_INTENT_REQUIRED_FIELDS,
    IMPROVEMENT_GOAL_RECORD_SCHEMA_VERSION,
    IMPROVEMENT_GOAL_REQUIRED_FIELDS as OWNER_IMPROVEMENT_GOAL_REQUIRED_FIELDS,
    PPTX_CATALOG_RECORD_SCHEMA_VERSION,
    PPTX_CATALOG_REQUIRED_FIELDS,
    RESOURCE_RECORD_SCHEMA_VERSION,
    RESOURCE_REQUIRED_FIELDS as OWNER_RESOURCE_REQUIRED_FIELDS,
    THUMBNAIL_RECORD_SCHEMA_VERSION,
    THUMBNAIL_REQUIRED_FIELDS as OWNER_THUMBNAIL_REQUIRED_FIELDS,
    TALK_RECORD_SCHEMA_VERSION,
    TRACKING_DATABASE_SCHEMA_VERSION,
    TrackingDatabaseError,
    require_current_tracking_database,
)
from tracking_database_io import (
    TrackingDatabaseIOError,
    commit_tracking_database,
    decode_json_object,
    decode_json_object_bytes,
    initialize_tracking_database,
    json_values_equal,
    render_json_object,
    snapshot_tracking_database,
)


PLAN_SCHEMA_VERSION = 1
OWNER_RECORD_SCHEMA_VERSION = CONFIRMED_INTENT_RECORD_SCHEMA_VERSION
if len(
    {
        OWNER_RECORD_SCHEMA_VERSION,
        PPTX_CATALOG_RECORD_SCHEMA_VERSION,
        RESOURCE_RECORD_SCHEMA_VERSION,
        THUMBNAIL_RECORD_SCHEMA_VERSION,
    }
) != 1:
    raise RuntimeError("typed owner collection versions require per-kind validation")
MISSING_MARKER = {"$missing": True}
COLLECTION_IDENTITIES = {
    "upsert_confirmed_intent": ("confirmed_intents", "pattern"),
    "upsert_improvement_goal": ("improvement_goals", "id"),
    "upsert_resource": ("resources", "talk_slug"),
    "upsert_thumbnail": ("thumbnails", "talk_slug"),
}
PUBLISHING_TALK_FIELDS = frozenset(
    {
        "shownotes_url",
        "shownotes_published",
        "thumbnail_generated",
        "video_added_to_shownotes",
        "video_url",
        "youtube_id",
    }
)
CLARIFICATION_TALK_FIELDS = frozenset(
    {"blind_spot_observations", "humor_postmortem"}
)
GOAL_VERIFICATION_FIELDS = frozenset(
    {
        "status",
        "current_value",
        "last_checked",
        "checked_by",
        "verification_state",
        "verification_reasons",
    }
)
LEGACY_GOAL_VERIFICATION_FIELDS = frozenset(
    {"status", "current_value", "last_checked", "checked_by"}
)
GOAL_REQUIRED_FIELDS = OWNER_IMPROVEMENT_GOAL_REQUIRED_FIELDS | {"schema_version"}
CONFIRMED_INTENT_REQUIRED_FIELDS = OWNER_CONFIRMED_INTENT_REQUIRED_FIELDS | {
    "schema_version"
}
RESOURCE_REQUIRED_FIELDS = OWNER_RESOURCE_REQUIRED_FIELDS | {"schema_version"}
PPTX_REQUIRED_FIELDS = PPTX_CATALOG_REQUIRED_FIELDS | {"schema_version"}
THUMBNAIL_REQUIRED_FIELDS = OWNER_THUMBNAIL_REQUIRED_FIELDS | {"schema_version"}
class TrackingDatabaseMutationError(ValueError):
    """A mutation plan, precondition, or database shape is invalid."""


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise TrackingDatabaseMutationError(f"invalid arguments: {message}")


def _strict_json_object(raw: bytes, path: Path, label: str) -> dict[str, Any]:
    try:
        return decode_json_object_bytes(
            raw,
            path,
            label=label,
        )
    except TrackingDatabaseIOError as exc:
        raise TrackingDatabaseMutationError(str(exc)) from exc


def load_plan(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise TrackingDatabaseMutationError(f"cannot read mutation plan {path}: {exc}") from exc
    plan = _strict_json_object(raw, path, "mutation plan")
    if not json_values_equal(plan.get("schema_version"), PLAN_SCHEMA_VERSION):
        raise TrackingDatabaseMutationError(
            f"mutation plan schema_version must be {PLAN_SCHEMA_VERSION}"
        )
    if set(plan) != {"schema_version", "mutations"}:
        raise TrackingDatabaseMutationError(
            "mutation plan must contain only schema_version and mutations"
        )
    mutations = plan.get("mutations")
    if not isinstance(mutations, list) or not mutations:
        raise TrackingDatabaseMutationError("mutation plan mutations must be a nonempty array")
    if any(not isinstance(mutation, dict) for mutation in mutations):
        raise TrackingDatabaseMutationError("every mutation must be a JSON object")
    return plan


def _require_keys(
    value: dict[str, Any],
    *,
    required: set[str] | frozenset[str],
    optional: set[str] | frozenset[str] = frozenset(),
    label: str,
) -> None:
    missing = set(required) - set(value)
    unknown = set(value) - set(required) - set(optional)
    if missing:
        raise TrackingDatabaseMutationError(f"{label} is missing {sorted(missing)}")
    if unknown:
        raise TrackingDatabaseMutationError(f"{label} has unknown fields {sorted(unknown)}")


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrackingDatabaseMutationError(f"{label} must be a nonempty string")
    if value != value.strip():
        raise TrackingDatabaseMutationError(
            f"{label} must not contain leading or trailing whitespace"
        )
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TrackingDatabaseMutationError(f"{label} must be a string")
    return value


def _exact_integer(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise TrackingDatabaseMutationError(
            f"{label} must be an integer greater than or equal to {minimum}"
        )
    return value


def _iso_date(value: object, label: str) -> str:
    text = _nonempty(value, label)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise TrackingDatabaseMutationError(
            f"{label} must be an ISO-8601 calendar date"
        ) from exc
    if parsed.isoformat() != text:
        raise TrackingDatabaseMutationError(
            f"{label} must use canonical YYYY-MM-DD form"
        )
    return text


def _string_array(value: object, label: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        suffix = "a nonempty" if nonempty else "an"
        raise TrackingDatabaseMutationError(
            f"{label} must be {suffix} array of unique nonempty strings"
        )
    normalized = [_nonempty(item, f"{label}[{index}]") for index, item in enumerate(value)]
    if len(normalized) != len(set(normalized)):
        raise TrackingDatabaseMutationError(
            f"{label} must contain unique nonempty strings"
        )
    return normalized


def _validate_record_schema(record: dict[str, Any], label: str) -> None:
    if not json_values_equal(record["schema_version"], OWNER_RECORD_SCHEMA_VERSION):
        raise TrackingDatabaseMutationError(
            f"{label}.schema_version must be exact integer "
            f"{OWNER_RECORD_SCHEMA_VERSION}"
        )


def _validate_publishing_values(values: object, label: str) -> None:
    if not isinstance(values, dict):
        raise TrackingDatabaseMutationError(f"{label} must be an object")
    for field, value in values.items():
        field_label = f"{label}.{field}"
        if field in {
            "shownotes_published",
            "thumbnail_generated",
            "video_added_to_shownotes",
        }:
            if type(value) is not bool:
                raise TrackingDatabaseMutationError(f"{field_label} must be boolean")
        elif field in {"shownotes_url", "video_url"}:
            _nonempty(value, field_label)
        elif field == "youtube_id":
            video_id = _nonempty(value, field_label)
            if re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id) is None:
                raise TrackingDatabaseMutationError(
                    f"{field_label} must be an 11-character YouTube ID"
                )


def _validate_clarification_values(values: object, label: str) -> None:
    if not isinstance(values, dict):
        raise TrackingDatabaseMutationError(f"{label} must be an object")
    for field, value in values.items():
        if field not in CLARIFICATION_TALK_FIELDS:
            continue
        if not isinstance(value, (dict, list)):
            raise TrackingDatabaseMutationError(
                f"{label}.{field} must be a JSON object or array"
            )


def _validate_goal_verification_values(values: object, label: str) -> None:
    if not isinstance(values, dict):
        raise TrackingDatabaseMutationError(f"{label} must be an object")
    for field, value in values.items():
        field_label = f"{label}.{field}"
        if field == "status":
            status = _nonempty(value, field_label)
            if status not in (
                "active",
                "improving",
                "achieved",
                "stalled",
                "regressed",
                "retired",
            ):
                raise TrackingDatabaseMutationError(f"{field_label} is unsupported")
        if field == "current_value":
            _string(value, field_label)
        elif field == "last_checked" and value is not None:
            _iso_date(value, field_label)
        elif field == "checked_by" and value is not None:
            _nonempty(value, field_label)
        elif field == "verification_state":
            state = _nonempty(value, field_label)
            if state not in (
                "pending",
                "current",
                "needs_rebaseline",
                "unverifiable",
            ):
                raise TrackingDatabaseMutationError(f"{field_label} is unsupported")
        elif field == "verification_reasons":
            _string_array(value, field_label)


def _expect_value(
    *,
    exists: bool,
    actual: object,
    expected: object,
    label: str,
) -> None:
    if json_values_equal(expected, MISSING_MARKER):
        if exists:
            raise TrackingDatabaseMutationError(
                f"{label} expected a missing value, found {actual!r}"
            )
        return
    if not exists or not json_values_equal(actual, expected):
        found = actual if exists else MISSING_MARKER
        raise TrackingDatabaseMutationError(
            f"{label} precondition failed: expected {expected!r}, found {found!r}"
        )


def _collection(
    database: dict[str, Any],
    key: str,
) -> list[dict[str, Any]]:
    value = database.setdefault(key, [])
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise TrackingDatabaseMutationError(f"database {key} must be an array of objects")
    return value


def _find_unique_record(
    records: list[dict[str, Any]],
    identity_field: str,
    identity: str,
    *,
    label: str,
) -> tuple[int | None, dict[str, Any] | None]:
    matches = [
        (index, record)
        for index, record in enumerate(records)
        if record.get(identity_field) == identity
    ]
    if len(matches) > 1:
        raise TrackingDatabaseMutationError(
            f"{label} repeats {identity_field} {identity!r}; repair duplicates first"
        )
    return matches[0] if matches else (None, None)


def _record_change(
    changes: list[dict[str, Any]],
    *,
    kind: str,
    identity: str,
    before: object,
    after: object,
) -> None:
    if json_values_equal(before, after):
        return
    changes.append(
        {
            "kind": kind,
            "identity": identity,
            "before": copy.deepcopy(before),
            "after": copy.deepcopy(after),
        }
    )


def _validate_collection_record(kind: str, record: dict[str, Any]) -> None:
    if kind == "upsert_confirmed_intent":
        label = "confirmed-intent record"
        _require_keys(
            record,
            required=CONFIRMED_INTENT_REQUIRED_FIELDS,
            optional=CONFIRMED_INTENT_OPTIONAL_FIELDS,
            label=label,
        )
        _validate_record_schema(record, label)
        _nonempty(record["pattern"], f"{label}.pattern")
        _nonempty(record["intent"], f"{label}.intent")
        _nonempty(record["rule"], f"{label}.rule")
        _string(record["note"], f"{label}.note")
        if "confirmed_date" in record:
            _iso_date(record["confirmed_date"], f"{label}.confirmed_date")
        provenance_fields = [
            field
            for field in ("talk", "source_talk", "source_talks")
            if field in record
        ]
        if len(provenance_fields) > 1:
            raise TrackingDatabaseMutationError(
                f"{label} may use only one of talk, source_talk, or source_talks"
            )
        for field in ("talk", "source_talk"):
            if field in record:
                _nonempty(record[field], f"{label}.{field}")
        for field in ("source_talks", "retrofit_targets"):
            if field in record:
                _string_array(record[field], f"{label}.{field}", nonempty=True)
    elif kind == "upsert_improvement_goal":
        label = "improvement-goal record"
        _require_keys(record, required=GOAL_REQUIRED_FIELDS, label=label)
        if not json_values_equal(
            record["schema_version"],
            IMPROVEMENT_GOAL_RECORD_SCHEMA_VERSION,
        ):
            raise TrackingDatabaseMutationError(
                f"{label}.schema_version must be exact integer "
                f"{IMPROVEMENT_GOAL_RECORD_SCHEMA_VERSION}"
            )
        for field in (
            "id",
            "issue",
            "metric",
            "baseline_value",
            "target",
            "set_by",
        ):
            _nonempty(record[field], f"{label}.{field}")
        _iso_date(record["set_date"], f"{label}.set_date")
        kind_value = _nonempty(record["kind"], f"{label}.kind")
        if kind_value not in ("antipattern", "underuse", "pacing", "other"):
            raise TrackingDatabaseMutationError(
                f"{label}.kind must be antipattern, underuse, pacing, or other"
            )
        antipattern_id = record["antipattern_id"]
        if kind_value == "antipattern":
            _nonempty(antipattern_id, f"{label}.antipattern_id")
        elif antipattern_id is not None:
            raise TrackingDatabaseMutationError(
                f"{label}.antipattern_id must be null unless kind is antipattern"
            )
        status = _nonempty(record["status"], f"{label}.status")
        if status not in (
            "active",
            "improving",
            "achieved",
            "stalled",
            "regressed",
            "retired",
        ):
            raise TrackingDatabaseMutationError(f"{label}.status is unsupported")
        _string(record["current_value"], f"{label}.current_value")
        for field in ("last_checked", "checked_by", "supersedes_goal_id"):
            value = record[field]
            if value is not None:
                if field == "last_checked":
                    _iso_date(value, f"{label}.{field}")
                else:
                    _nonempty(value, f"{label}.{field}")
        if (record["last_checked"] is None) != (record["checked_by"] is None):
            raise TrackingDatabaseMutationError(
                f"{label}.last_checked and checked_by must both be null or both set"
            )
        verification_state = _nonempty(
            record["verification_state"],
            f"{label}.verification_state",
        )
        if verification_state not in (
            "pending",
            "current",
            "needs_rebaseline",
            "unverifiable",
        ):
            raise TrackingDatabaseMutationError(
                f"{label}.verification_state is unsupported"
            )
        _string_array(
            record["verification_reasons"],
            f"{label}.verification_reasons",
        )
        provenance = record["baseline_provenance"]
        if not isinstance(provenance, dict):
            raise TrackingDatabaseMutationError(
                f"{label}.baseline_provenance must be an object"
            )
        _require_keys(
            provenance,
            required={"lane"},
            optional={"pattern_baseline"},
            label=f"{label}.baseline_provenance",
        )
        expected_lane = {
            "antipattern": "pattern_scoring",
            "underuse": "pattern_scoring",
            "pacing": "pacing",
            "other": "independent",
        }[kind_value]
        lane = _nonempty(
            provenance["lane"],
            f"{label}.baseline_provenance.lane",
        )
        if lane != expected_lane:
            raise TrackingDatabaseMutationError(
                f"{label}.baseline_provenance.lane must be {expected_lane!r}"
            )
        if kind_value in {"antipattern", "underuse"}:
            if not isinstance(provenance.get("pattern_baseline"), dict):
                raise TrackingDatabaseMutationError(
                    f"{label}.baseline_provenance.pattern_baseline must be an object"
                )
        elif "pattern_baseline" in provenance:
            raise TrackingDatabaseMutationError(
                f"{label}.baseline_provenance.pattern_baseline is valid only for "
                "pattern goals"
            )
    elif kind == "upsert_resource":
        label = "resource record"
        _require_keys(
            record,
            required=RESOURCE_REQUIRED_FIELDS,
            label=label,
        )
        _validate_record_schema(record, label)
        _nonempty(record["talk_slug"], f"{label}.talk_slug")
        item_count = _exact_integer(record["item_count"], f"{label}.item_count")
        breakdown = record["category_breakdown"]
        if not isinstance(breakdown, dict):
            raise TrackingDatabaseMutationError(
                f"{label}.category_breakdown must be an object"
            )
        category_total = 0
        for category, count in breakdown.items():
            _nonempty(category, f"{label}.category_breakdown key")
            category_total += _exact_integer(
                count,
                f"{label}.category_breakdown[{category!r}]",
            )
        if item_count != category_total:
            raise TrackingDatabaseMutationError(
                f"{label}.item_count must equal the category_breakdown total"
            )
    elif kind == "upsert_thumbnail":
        label = "thumbnail record"
        _require_keys(
            record,
            required=THUMBNAIL_REQUIRED_FIELDS,
            label=label,
        )
        _validate_record_schema(record, label)
        for field in (
            "talk_slug",
            "youtube_url",
            "speaker_photo_used",
            "thumbnail_path",
            "shownotes_thumbnail_path",
        ):
            _nonempty(record[field], f"{label}.{field}")
        _exact_integer(record["source_slide_num"], f"{label}.source_slide_num", minimum=1)
        dimensions = _nonempty(record["dimensions"], f"{label}.dimensions")
        match = re.fullmatch(r"([1-9][0-9]*)x([1-9][0-9]*)", dimensions)
        if match is None:
            raise TrackingDatabaseMutationError(
                f"{label}.dimensions must use positive WIDTHxHEIGHT form"
            )
        _exact_integer(record["file_size_kb"], f"{label}.file_size_kb")
        _iso_date(record["created_at"], f"{label}.created_at")
        if type(record["approved"]) is not bool:
            raise TrackingDatabaseMutationError(f"{label}.approved must be boolean")


def _apply_collection_upsert(
    database: dict[str, Any],
    mutation: dict[str, Any],
    changes: list[dict[str, Any]],
    *,
    index: int,
) -> None:
    kind = str(mutation.get("kind"))
    _require_keys(
        mutation,
        required={"kind", "expect", "record"},
        label=f"mutations[{index}]",
    )
    record = mutation["record"]
    if not isinstance(record, dict):
        raise TrackingDatabaseMutationError(f"mutations[{index}].record must be an object")
    _validate_collection_record(kind, record)
    collection_name, identity_field = COLLECTION_IDENTITIES[kind]
    identity = _nonempty(record.get(identity_field), f"mutations[{index}].record.{identity_field}")
    records = _collection(database, collection_name)
    record_index, current = _find_unique_record(
        records,
        identity_field,
        identity,
        label=collection_name,
    )
    _expect_value(
        exists=current is not None,
        actual=current,
        expected=mutation["expect"],
        label=f"{collection_name}[{identity!r}]",
    )
    replacement = copy.deepcopy(record)
    before: object = current if current is not None else MISSING_MARKER
    if record_index is None:
        records.append(replacement)
    else:
        records[record_index] = replacement
    _record_change(
        changes,
        kind=kind,
        identity=identity,
        before=before,
        after=replacement,
    )


def _apply_set_config(
    database: dict[str, Any],
    mutation: dict[str, Any],
    changes: list[dict[str, Any]],
    *,
    index: int,
) -> None:
    _require_keys(
        mutation,
        required={"kind", "path", "expect"},
        optional={"value", "delete"},
        label=f"mutations[{index}]",
    )
    has_value = "value" in mutation
    delete = mutation.get("delete", False)
    if not isinstance(delete, bool) or has_value == delete:
        raise TrackingDatabaseMutationError(
            f"mutations[{index}] must set exactly one of value or delete:true"
        )
    path = mutation["path"]
    if (
        not isinstance(path, list)
        or not path
        or any(not isinstance(part, str) or not part for part in path)
        or path[0] == "schema_version"
    ):
        raise TrackingDatabaseMutationError(
            f"mutations[{index}].path must be nonempty config keys outside schema_version"
        )
    config = database.setdefault("config", {})
    if not isinstance(config, dict):
        raise TrackingDatabaseMutationError("database config must be an object")
    parent = config
    label = "config." + ".".join(path)
    for offset, part in enumerate(path[:-1]):
        if part not in parent:
            if delete:
                _expect_value(
                    exists=False,
                    actual=None,
                    expected=mutation["expect"],
                    label=label,
                )
                return
            child = {}
            parent[part] = child
        else:
            child = parent[part]
        if not isinstance(child, dict):
            prefix = ".".join(path[: offset + 1])
            raise TrackingDatabaseMutationError(f"config.{prefix} must be an object")
        parent = child
    leaf = path[-1]
    exists = leaf in parent
    actual = parent.get(leaf)
    _expect_value(exists=exists, actual=actual, expected=mutation["expect"], label=label)
    before: object = actual if exists else MISSING_MARKER
    if delete:
        parent.pop(leaf, None)
        after: object = MISSING_MARKER
    else:
        after = copy.deepcopy(mutation["value"])
        parent[leaf] = after
    _record_change(
        changes,
        kind="set_config",
        identity=".".join(path),
        before=before,
        after=after,
    )


def _talk_by_filename(
    database: dict[str, Any],
    filename: object,
) -> dict[str, Any]:
    identity = _nonempty(filename, "talk filename")
    talks = _collection(database, "talks")
    _, talk = _find_unique_record(talks, "filename", identity, label="talks")
    if talk is None:
        raise TrackingDatabaseMutationError(f"talk {identity!r} does not exist")
    return talk


def _apply_record_patch(
    record: dict[str, Any],
    *,
    expect: object,
    set_values: object,
    allowed_fields: frozenset[str],
    label: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(expect, dict) or not isinstance(set_values, dict) or not set_values:
        raise TrackingDatabaseMutationError(f"{label} expect/set must be nonempty objects")
    if set(set_values) - allowed_fields:
        raise TrackingDatabaseMutationError(
            f"{label} set has unsupported fields {sorted(set(set_values) - allowed_fields)}"
        )
    if set(expect) != set(set_values):
        raise TrackingDatabaseMutationError(
            f"{label} expect must cover exactly the fields being changed"
        )
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for field, value in set_values.items():
        exists = field in record
        actual = record.get(field)
        _expect_value(
            exists=exists,
            actual=actual,
            expected=expect[field],
            label=f"{label}.{field}",
        )
        before[field] = copy.deepcopy(actual) if exists else MISSING_MARKER
        record[field] = copy.deepcopy(value)
        after[field] = copy.deepcopy(value)
    return before, after


def _require_current_talk_record(
    talk: dict[str, Any],
    *,
    filename: str,
) -> None:
    version = talk.get("schema_version")
    if type(version) is not int or version != TALK_RECORD_SCHEMA_VERSION:
        raise TrackingDatabaseMutationError(
            f"talks[{filename!r}].schema_version must be exact current talk "
            f"schema {TALK_RECORD_SCHEMA_VERSION} before this mutation"
        )


def _apply_update_talk(
    database: dict[str, Any],
    mutation: dict[str, Any],
    changes: list[dict[str, Any]],
    *,
    index: int,
) -> None:
    _require_keys(
        mutation,
        required={"kind", "filename", "expect", "set"},
        label=f"mutations[{index}]",
    )
    filename = _nonempty(mutation["filename"], f"mutations[{index}].filename")
    talk = _talk_by_filename(database, filename)
    _require_current_talk_record(talk, filename=filename)
    _validate_publishing_values(mutation["set"], f"mutations[{index}].set")
    before, after = _apply_record_patch(
        talk,
        expect=mutation["expect"],
        set_values=mutation["set"],
        allowed_fields=PUBLISHING_TALK_FIELDS,
        label=f"talks[{filename!r}]",
    )
    _record_change(
        changes,
        kind="update_talk_publishing",
        identity=filename,
        before=before,
        after=after,
    )


def _apply_update_talk_clarification(
    database: dict[str, Any],
    mutation: dict[str, Any],
    changes: list[dict[str, Any]],
    *,
    index: int,
) -> None:
    _require_keys(
        mutation,
        required={"kind", "filename", "expect", "set"},
        label=f"mutations[{index}]",
    )
    filename = _nonempty(mutation["filename"], f"mutations[{index}].filename")
    talk = _talk_by_filename(database, filename)
    _require_current_talk_record(talk, filename=filename)
    _validate_clarification_values(mutation["set"], f"mutations[{index}].set")
    before, after = _apply_record_patch(
        talk,
        expect=mutation["expect"],
        set_values=mutation["set"],
        allowed_fields=CLARIFICATION_TALK_FIELDS,
        label=f"talks[{filename!r}]",
    )
    _record_change(
        changes,
        kind="update_talk_clarification",
        identity=filename,
        before=before,
        after=after,
    )


def _apply_goal_verification(
    database: dict[str, Any],
    mutation: dict[str, Any],
    changes: list[dict[str, Any]],
    *,
    index: int,
) -> None:
    _require_keys(
        mutation,
        required={"kind", "id", "expect", "set"},
        label=f"mutations[{index}]",
    )
    identity = _nonempty(mutation["id"], f"mutations[{index}].id")
    goals = _collection(database, "improvement_goals")
    _, goal = _find_unique_record(goals, "id", identity, label="improvement_goals")
    if goal is None:
        raise TrackingDatabaseMutationError(f"improvement goal {identity!r} does not exist")
    goal_version = goal.get("schema_version")
    goal_kind = goal.get("kind")
    if goal_version == 1:
        if goal_kind in {"antipattern", "underuse"}:
            raise TrackingDatabaseMutationError(
                f"improvement goal {identity!r} is a historical schema-v1 "
                f"{goal_kind} goal; skip and report it instead of partially "
                "upgrading it"
            )
        allowed_fields = LEGACY_GOAL_VERIFICATION_FIELDS
    elif goal_version == IMPROVEMENT_GOAL_RECORD_SCHEMA_VERSION:
        allowed_fields = GOAL_VERIFICATION_FIELDS
    else:
        raise TrackingDatabaseMutationError(
            f"improvement goal {identity!r} has unsupported schema_version "
            f"{goal_version!r}"
        )
    _validate_goal_verification_values(
        mutation["set"],
        f"mutations[{index}].set",
    )
    before, after = _apply_record_patch(
        goal,
        expect=mutation["expect"],
        set_values=mutation["set"],
        allowed_fields=allowed_fields,
        label=f"improvement_goals[{identity!r}]",
    )
    _record_change(
        changes,
        kind="patch_improvement_goal_verification",
        identity=identity,
        before=before,
        after=after,
    )


def _apply_retire_improvement_goal(
    database: dict[str, Any],
    mutation: dict[str, Any],
    changes: list[dict[str, Any]],
    *,
    index: int,
) -> None:
    _require_keys(
        mutation,
        required={"kind", "id", "expect"},
        label=f"mutations[{index}]",
    )
    identity = _nonempty(mutation["id"], f"mutations[{index}].id")
    expected = mutation["expect"]
    if not isinstance(expected, dict):
        raise TrackingDatabaseMutationError(
            f"mutations[{index}].expect must be the complete expected goal record"
        )
    goals = _collection(database, "improvement_goals")
    _, goal = _find_unique_record(goals, "id", identity, label="improvement_goals")
    if goal is None:
        raise TrackingDatabaseMutationError(
            f"improvement goal {identity!r} does not exist"
        )
    _expect_value(
        exists=True,
        actual=goal,
        expected=expected,
        label=f"improvement_goals[{identity!r}]",
    )
    if "status" not in goal:
        raise TrackingDatabaseMutationError(
            f"improvement_goals[{identity!r}] has no status field to retire"
        )
    before = copy.deepcopy(goal)
    goal["status"] = "retired"
    _record_change(
        changes,
        kind="retire_improvement_goal",
        identity=identity,
        before=before,
        after=goal,
    )


def _apply_record_pptx(
    database: dict[str, Any],
    mutation: dict[str, Any],
    changes: list[dict[str, Any]],
    *,
    index: int,
) -> None:
    _require_keys(
        mutation,
        required={"kind", "expect", "record"},
        optional={"expect_talk_pptx_path"},
        label=f"mutations[{index}]",
    )
    record = mutation["record"]
    if not isinstance(record, dict):
        raise TrackingDatabaseMutationError(f"mutations[{index}].record must be an object")
    record_label = f"mutations[{index}].record"
    _require_keys(
        record,
        required=PPTX_REQUIRED_FIELDS,
        label=record_label,
    )
    _validate_record_schema(record, record_label)
    pptx_path = _nonempty(record["pptx_path"], f"{record_label}.pptx_path")
    if type(record["matched"]) is not bool:
        raise TrackingDatabaseMutationError(f"mutations[{index}].record.matched must be boolean")
    _exact_integer(record["slide_count"], f"{record_label}.slide_count")
    if type(record["visual_extracted"]) is not bool:
        raise TrackingDatabaseMutationError(
            f"{record_label}.visual_extracted must be boolean"
        )
    talk_filename = record.get("talk_filename")
    if talk_filename is not None:
        talk_filename = _nonempty(talk_filename, f"mutations[{index}].record.talk_filename")
    if record["matched"] != (talk_filename is not None):
        raise TrackingDatabaseMutationError(
            f"mutations[{index}] matched must be true exactly when talk_filename is set"
        )
    records = _collection(database, "pptx_catalog")
    record_index, current = _find_unique_record(
        records,
        "pptx_path",
        pptx_path,
        label="pptx_catalog",
    )
    _expect_value(
        exists=current is not None,
        actual=current,
        expected=mutation["expect"],
        label=f"pptx_catalog[{pptx_path!r}]",
    )
    replacement = copy.deepcopy(record)
    before: object = current if current is not None else MISSING_MARKER
    if record_index is None:
        records.append(replacement)
    else:
        records[record_index] = replacement
    _record_change(
        changes,
        kind="record_pptx",
        identity=pptx_path,
        before=before,
        after=replacement,
    )
    if talk_filename is None:
        if "expect_talk_pptx_path" in mutation:
            raise TrackingDatabaseMutationError(
                f"mutations[{index}] unmatched record must omit expect_talk_pptx_path"
            )
        return
    if "expect_talk_pptx_path" not in mutation:
        raise TrackingDatabaseMutationError(
            f"mutations[{index}] matched record requires expect_talk_pptx_path"
        )
    talk = _talk_by_filename(database, talk_filename)
    exists = "pptx_path" in talk
    actual = talk.get("pptx_path")
    _expect_value(
        exists=exists,
        actual=actual,
        expected=mutation["expect_talk_pptx_path"],
        label=f"talks[{talk_filename!r}].pptx_path",
    )
    talk["pptx_path"] = pptx_path
    _record_change(
        changes,
        kind="match_pptx_talk",
        identity=talk_filename,
        before=actual if exists else MISSING_MARKER,
        after=pptx_path,
    )


def _validate_database_shape(database: dict[str, Any]) -> None:
    config = database.get("config")
    talks = database.get("talks")
    if not isinstance(config, dict):
        raise TrackingDatabaseMutationError("database config must be an object")
    if not isinstance(talks, list) or any(not isinstance(talk, dict) for talk in talks):
        raise TrackingDatabaseMutationError("database talks must be an array of objects")
    seen: set[str] = set()
    for index, talk in enumerate(talks):
        filename = _nonempty(talk.get("filename"), f"talks[{index}].filename")
        if filename in seen:
            raise TrackingDatabaseMutationError(f"database repeats talk filename {filename!r}")
        seen.add(filename)


def initial_database(mutation: dict[str, Any], *, index: int) -> dict[str, Any]:
    _require_keys(
        mutation,
        required={"kind", "config"},
        label=f"mutations[{index}]",
    )
    config = mutation["config"]
    if not isinstance(config, dict):
        raise TrackingDatabaseMutationError(f"mutations[{index}].config must be an object")
    initial_config = copy.deepcopy(config)
    if "schema_version" in initial_config and not json_values_equal(
        initial_config["schema_version"],
        CONFIG_RECORD_SCHEMA_VERSION,
    ):
        raise TrackingDatabaseMutationError(
            f"mutations[{index}].config.schema_version must be exact integer "
            f"{CONFIG_RECORD_SCHEMA_VERSION}"
        )
    initial_config["schema_version"] = CONFIG_RECORD_SCHEMA_VERSION
    return {
        "schema_version": TRACKING_DATABASE_SCHEMA_VERSION,
        "config": initial_config,
        "talks": [],
        "pptx_catalog": [],
        "qr_codes": [],
        "resources": [],
        "thumbnails": [],
        "confirmed_intents": [],
        "improvement_goals": [],
    }


def build_candidate(
    database: dict[str, Any],
    mutations: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        require_current_tracking_database(database)
    except TrackingDatabaseError as exc:
        raise TrackingDatabaseMutationError(str(exc)) from exc
    candidate = copy.deepcopy(database)
    _validate_database_shape(candidate)
    changes: list[dict[str, Any]] = []
    for index, mutation in enumerate(mutations):
        kind = mutation.get("kind")
        if kind == "initialize_database":
            raise TrackingDatabaseMutationError(
                "initialize_database is valid only when the database is missing and "
                "must be the plan's sole mutation"
            )
        if kind == "set_config":
            _apply_set_config(candidate, mutation, changes, index=index)
        elif kind in COLLECTION_IDENTITIES:
            _apply_collection_upsert(candidate, mutation, changes, index=index)
        elif kind == "record_pptx":
            _apply_record_pptx(candidate, mutation, changes, index=index)
        elif kind == "update_talk_publishing":
            _apply_update_talk(candidate, mutation, changes, index=index)
        elif kind == "update_talk_clarification":
            _apply_update_talk_clarification(
                candidate,
                mutation,
                changes,
                index=index,
            )
        elif kind == "patch_improvement_goal_verification":
            _apply_goal_verification(candidate, mutation, changes, index=index)
        elif kind == "retire_improvement_goal":
            _apply_retire_improvement_goal(candidate, mutation, changes, index=index)
        else:
            raise TrackingDatabaseMutationError(
                f"mutations[{index}].kind {kind!r} is unsupported"
            )
    _validate_database_shape(candidate)
    try:
        require_current_tracking_database(candidate)
    except TrackingDatabaseError as exc:
        raise TrackingDatabaseMutationError(
            f"mutation candidate violates the tracking-database schema: {exc}"
        ) from exc
    return candidate, changes


def _validate_digest(value: str) -> None:
    if value == "missing":
        return
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise TrackingDatabaseMutationError(
            "--expected-sha256 must be `missing` or 64 lowercase hexadecimal characters"
        )


def execute(
    database_path: Path,
    plan_path: Path,
    *,
    apply: bool,
    expected_sha256: str | None,
) -> dict[str, Any]:
    plan = load_plan(plan_path)
    mutations = plan["mutations"]
    if expected_sha256 is not None:
        _validate_digest(expected_sha256)
    if apply and expected_sha256 is None:
        raise TrackingDatabaseMutationError(
            "--apply requires --expected-sha256 from the reviewed dry-run report"
        )

    initialize = len(mutations) == 1 and mutations[0].get("kind") == "initialize_database"
    if any(mutation.get("kind") == "initialize_database" for mutation in mutations) and not initialize:
        raise TrackingDatabaseMutationError(
            "initialize_database must be the mutation plan's sole mutation"
        )
    database_path = Path(os.path.abspath(database_path.expanduser()))
    if initialize:
        if database_path.exists() or database_path.is_symlink():
            raise TrackingDatabaseMutationError(
                f"tracking database already exists at {database_path}; use typed mutations"
            )
        if expected_sha256 not in {None, "missing"}:
            raise TrackingDatabaseMutationError(
                "initialization precondition is `missing`, not a file SHA-256"
            )
        candidate = initial_database(mutations[0], index=0)
        _validate_database_shape(candidate)
        try:
            require_current_tracking_database(candidate)
        except TrackingDatabaseError as exc:
            raise TrackingDatabaseMutationError(
                f"initial database violates the tracking-database schema: {exc}"
            ) from exc
        rendered = render_json_object(candidate)
        output_sha256 = hashlib.sha256(rendered).hexdigest()
        if apply:
            try:
                result = initialize_tracking_database(database_path, candidate)
            except TrackingDatabaseIOError as exc:
                raise TrackingDatabaseMutationError(str(exc)) from exc
            durability_state = result.durability_state
            warnings = list(result.warnings)
            database_written = result.installed
        else:
            durability_state = "dry_run"
            warnings = []
            database_written = False
        return {
            "schema_version": PLAN_SCHEMA_VERSION,
            "ok": True,
            "mode": "apply" if apply else "dry-run",
            "database": str(database_path),
            "input_sha256": None,
            "input_state": "missing",
            "output_sha256": output_sha256,
            "changed": True,
            "database_written": database_written,
            "durability_state": durability_state,
            "warnings": warnings,
            "changes": [
                {
                    "kind": "initialize_database",
                    "identity": str(database_path),
                    "before": MISSING_MARKER,
                    "after": candidate,
                }
            ],
        }

    try:
        snapshot = snapshot_tracking_database(database_path)
        database = decode_json_object(snapshot)
    except TrackingDatabaseIOError as exc:
        raise TrackingDatabaseMutationError(str(exc)) from exc
    if expected_sha256 == "missing":
        raise TrackingDatabaseMutationError(
            "tracking database exists; use its dry-run input_sha256 precondition"
        )
    if expected_sha256 is not None and expected_sha256 != snapshot.sha256:
        raise TrackingDatabaseMutationError(
            f"input sha256 precondition failed: expected {expected_sha256}, "
            f"found {snapshot.sha256}"
        )
    candidate, changes = build_candidate(database, mutations)
    rendered = render_json_object(candidate) if changes else snapshot.raw
    output_sha256 = hashlib.sha256(rendered).hexdigest()
    if apply:
        try:
            result = commit_tracking_database(snapshot, rendered)
        except TrackingDatabaseIOError as exc:
            raise TrackingDatabaseMutationError(str(exc)) from exc
        database_written = result.installed
        durability_state = result.durability_state
        warnings = list(result.warnings)
        output_sha256 = result.output_sha256
    else:
        database_written = False
        durability_state = "dry_run"
        warnings = []
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "ok": True,
        "mode": "apply" if apply else "dry-run",
        "database": str(database_path),
        "input_sha256": snapshot.sha256,
        "input_state": "present",
        "output_sha256": output_sha256,
        "changed": bool(changes),
        "database_written": database_written,
        "durability_state": durability_state,
        "warnings": warnings,
        "changes": changes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = _ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("database", type=Path)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-sha256")
    try:
        args = parser.parse_args(argv)
        report = execute(
            args.database,
            args.plan,
            apply=args.apply,
            expected_sha256=args.expected_sha256,
        )
    except TrackingDatabaseMutationError as exc:
        print(json.dumps({"schema_version": 1, "ok": False, "error": str(exc)}))
        print(f"tracking-database mutation failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
