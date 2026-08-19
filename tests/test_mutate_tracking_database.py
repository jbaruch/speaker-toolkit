"""Tests for the typed owner mutation-plan surface."""

from __future__ import annotations

import copy
import json
from typing import Any
from pathlib import Path

import unicodedata

import pytest


import importlib as _importlib
import sys as _sys

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1] / "skills" / "vault-ingress" / "scripts"
)
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

# Talk-record fixtures track the current schema rather than pinning a literal:
# a pin makes every fixture in this module unmutatable the moment the talk
# record shape advances, which surfaces as "must be exact current talk schema"
# on tests that are about something else entirely.
CURRENT_TALK_SCHEMA = _importlib.import_module(
    "tracking_database"
).TALK_RECORD_SCHEMA_VERSION

MISSING = {"$missing": True}
DEFAULT_DIRECTORY_EXCLUSIONS = [
    ".venv",
    "venv",
    "node_modules",
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".tessl",
]


def _current_config(**updates: object) -> dict[str, Any]:
    config: dict[str, object] = {
        "schema_version": 2,
        "pptx_directory_exclusions": copy.deepcopy(DEFAULT_DIRECTORY_EXCLUSIONS),
    }
    config.update(updates)
    return config


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _base_database() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "config": _current_config(),
        "talks": [
            {
                "schema_version": CURRENT_TALK_SCHEMA,
                "filename": "talk.md",
                "status": "processed",
            }
        ],
        "pptx_catalog": [],
        "qr_codes": [],
        "resources": [],
        "thumbnails": [],
        "confirmed_intents": [],
        "improvement_goals": [],
    }


def _goal() -> dict[str, Any]:
    return {
        "id": "reduce-shortchanged",
        "schema_version": 2,
        "issue": "Rushed close",
        "kind": "pacing",
        "antipattern_id": None,
        "metric": "closing minutes",
        "baseline_value": "2",
        "target": "5",
        "set_date": "2026-07-31",
        "set_by": "vault-clarification",
        "status": "active",
        "current_value": "",
        "last_checked": None,
        "checked_by": None,
        "verification_state": "pending",
        "verification_reasons": [],
        "supersedes_goal_id": None,
        "baseline_provenance": {"lane": "pacing"},
    }


def _complete_plan() -> dict[str, Any]:
    goal = _goal()
    return {
        "schema_version": 1,
        "mutations": [
            {
                "kind": "set_config",
                "path": ["shownotes", "enabled"],
                "expect": MISSING,
                "value": True,
            },
            {
                "kind": "record_pptx",
                "expect": MISSING,
                "expect_talk_pptx_path": MISSING,
                "record": {
                    "schema_version": 3,
                    "pptx_path": "Conference/Talk.pptx",
                    "talk_filename": "talk.md",
                    "matched": True,
                    "slide_count": 10,
                    "visual_extracted": False,
                    "visual_evidence": None,
                    "identity_assessment": {
                        "schema_version": 2,
                        "pptx_path": "Conference/Talk.pptx",
                        "verdict": "matched",
                        "artifact_role": "delivery",
                        "selected_talk_filename": "talk.md",
                        "reason_codes": ["identity_matched"],
                        # The row carries no extraction evidence yet, so there
                        # is nothing to cross-check against — identity is
                        # verified BEFORE extraction. The assessment still has
                        # to name the generation it read.
                        "source_identity": {
                            "algorithm": "sha256",
                            "digest": "e" * 64,
                            "size_bytes": 2048,
                        },
                        "candidates": [
                            {
                                "talk_filename": "talk.md",
                                "signals": {
                                    "title": "unknown",
                                    "venue": "agree",
                                    "delivery_year": "unknown",
                                    "hashtag": "unknown",
                                    "published_pdf": "unknown",
                                    "filename_similarity": "unknown",
                                },
                                "agreeing": ["venue"],
                                "conflicting": [],
                            }
                        ],
                    },
                },
            },
            {
                "kind": "upsert_confirmed_intent",
                "expect": MISSING,
                "record": {
                    "schema_version": 1,
                    "pattern": "delayed-self-introduction",
                    "intent": "deliberate",
                    "rule": "Hook before credentials",
                    "note": "Speaker confirmed",
                    "confirmed_date": "2026-08-01",
                    "source_talk": "talk.md",
                    "retrofit_targets": ["opening guidance"],
                },
            },
            {
                "kind": "upsert_improvement_goal",
                "expect": MISSING,
                "record": goal,
            },
            {
                "kind": "patch_improvement_goal_verification",
                "id": goal["id"],
                "expect": {
                    "current_value": "",
                    "last_checked": None,
                    "checked_by": None,
                    "verification_state": "pending",
                    "verification_reasons": [],
                },
                "set": {
                    "current_value": "3",
                    "last_checked": "2026-08-01",
                    "checked_by": "vault-ingress",
                    "verification_state": "current",
                    "verification_reasons": [],
                },
            },
            {
                "kind": "upsert_resource",
                "expect": MISSING,
                "record": {
                    "schema_version": 1,
                    "talk_slug": "talk",
                    "item_count": 3,
                    "category_breakdown": {"url": 2, "book": 1},
                },
            },
            {
                "kind": "upsert_thumbnail",
                "expect": MISSING,
                "record": {
                    "schema_version": 1,
                    "talk_slug": "talk",
                    "youtube_url": "https://youtu.be/AbCdEfGhI_1",
                    "source_slide_num": 5,
                    "speaker_photo_used": "headshot.jpg",
                    "thumbnail_path": "illustrations/thumbnail.png",
                    "shownotes_thumbnail_path": "assets/images/thumbnails/talk-thumbnail.png",
                    "dimensions": "1280x720",
                    "file_size_kb": 185,
                    "created_at": "2026-08-01",
                    "approved": True,
                },
            },
            {
                "kind": "update_talk_publishing",
                "filename": "talk.md",
                "expect": {
                    "shownotes_url": MISSING,
                    "shownotes_published": MISSING,
                    "thumbnail_generated": MISSING,
                    "video_added_to_shownotes": MISSING,
                    "video_url": MISSING,
                    "youtube_id": MISSING,
                },
                "set": {
                    "shownotes_url": "https://example.com/talk",
                    "shownotes_published": True,
                    "thumbnail_generated": True,
                    "video_added_to_shownotes": True,
                    "video_url": "https://youtu.be/AbCdEfGhI_1",
                    "youtube_id": "AbCdEfGhI_1",
                },
            },
        ],
    }


def test_dry_run_then_hash_bound_apply_covers_every_typed_operation(
    mutate_tracking_database,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "tracking-database.json"
    plan_path = tmp_path / "plan.json"
    database = _base_database()
    _write_json(database_path, database)
    _write_json(plan_path, _complete_plan())
    before = database_path.read_bytes()

    dry_run = mutate_tracking_database.execute(
        database_path,
        plan_path,
        apply=False,
        expected_sha256=None,
    )
    assert dry_run["changed"] is True
    assert dry_run["database_written"] is False
    assert database_path.read_bytes() == before

    applied = mutate_tracking_database.execute(
        database_path,
        plan_path,
        apply=True,
        expected_sha256=dry_run["input_sha256"],
    )

    result = json.loads(database_path.read_text(encoding="utf-8"))
    assert applied["database_written"] is True
    assert applied["input_sha256"] == dry_run["input_sha256"]
    assert applied["output_sha256"] == dry_run["output_sha256"]
    assert result["config"]["shownotes"]["enabled"] is True
    assert result["talks"][0]["pptx_path"] == "Conference/Talk.pptx"
    assert result["talks"][0]["thumbnail_generated"] is True
    assert result["talks"][0]["video_added_to_shownotes"] is True
    assert result["pptx_catalog"][0]["talk_filename"] == "talk.md"
    assert result["confirmed_intents"][0]["intent"] == "deliberate"
    assert result["improvement_goals"][0]["current_value"] == "3"
    assert result["resources"][0]["item_count"] == 3
    assert result["thumbnails"][0]["approved"] is True


def test_noop_plan_preserves_noncanonical_bytes_and_inode(
    mutate_tracking_database,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "tracking-database.json"
    database = _base_database()
    database["config"]["speaker_name"] = "Ada"
    database["talks"] = []
    raw = (json.dumps(database, separators=(",", ":")) + "\n").encode()
    database_path.write_bytes(raw)
    plan_path = tmp_path / "plan.json"
    _write_json(
        plan_path,
        {
            "schema_version": 1,
            "mutations": [
                {
                    "kind": "set_config",
                    "path": ["speaker_name"],
                    "expect": "Ada",
                    "value": "Ada",
                }
            ],
        },
    )
    dry_run = mutate_tracking_database.execute(
        database_path,
        plan_path,
        apply=False,
        expected_sha256=None,
    )
    inode = database_path.stat().st_ino

    applied = mutate_tracking_database.execute(
        database_path,
        plan_path,
        apply=True,
        expected_sha256=dry_run["input_sha256"],
    )

    assert applied["changed"] is False
    assert applied["database_written"] is False
    assert applied["input_sha256"] == applied["output_sha256"]
    assert database_path.read_bytes() == raw
    assert database_path.stat().st_ino == inode


def test_apply_requires_reviewed_exact_hash(
    mutate_tracking_database,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "tracking-database.json"
    plan_path = tmp_path / "plan.json"
    _write_json(database_path, _base_database())
    _write_json(plan_path, _complete_plan())

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="requires --expected-sha256",
    ):
        mutate_tracking_database.execute(
            database_path,
            plan_path,
            apply=True,
            expected_sha256=None,
        )
    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="input sha256 precondition failed",
    ):
        mutate_tracking_database.execute(
            database_path,
            plan_path,
            apply=True,
            expected_sha256="0" * 64,
        )


def test_plan_expectation_mismatch_is_whole_plan_noop(
    mutate_tracking_database,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "tracking-database.json"
    plan_path = tmp_path / "plan.json"
    database = _base_database()
    _write_json(database_path, database)
    plan = _complete_plan()
    plan["mutations"][0]["expect"] = False
    _write_json(plan_path, plan)
    before = database_path.read_bytes()

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="precondition failed",
    ):
        mutate_tracking_database.execute(
            database_path,
            plan_path,
            apply=False,
            expected_sha256=None,
        )

    assert database_path.read_bytes() == before


def test_initialization_dry_run_and_missing_precondition(
    mutate_tracking_database,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "tracking-database.json"
    plan_path = tmp_path / "plan.json"
    _write_json(
        plan_path,
        {
            "schema_version": 1,
            "mutations": [{"kind": "initialize_database", "config": {}}],
        },
    )

    dry_run = mutate_tracking_database.execute(
        database_path,
        plan_path,
        apply=False,
        expected_sha256=None,
    )
    assert dry_run["input_state"] == "missing"
    assert not database_path.exists()

    applied = mutate_tracking_database.execute(
        database_path,
        plan_path,
        apply=True,
        expected_sha256="missing",
    )
    assert applied["database_written"] is True
    initialized = json.loads(database_path.read_text(encoding="utf-8"))
    assert initialized["schema_version"] == 1
    assert initialized["config"]["schema_version"] == 2
    assert (
        initialized["config"]["pptx_directory_exclusions"]
        == DEFAULT_DIRECTORY_EXCLUSIONS
    )
    assert initialized["talks"] == []


def test_initialization_surfaces_owner_io_failure_as_mutation_error(
    cooperative_lock,
    mutate_tracking_database,
    tracking_database_io,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "tracking-database.json"
    plan_path = tmp_path / "plan.json"
    _write_json(
        plan_path,
        {
            "schema_version": 1,
            "mutations": [{"kind": "initialize_database", "config": {}}],
        },
    )
    outside_lock = tmp_path / "outside.lock"
    outside_lock.write_bytes(b"")
    cooperative_lock.lock_path_for(database_path).symlink_to(outside_lock)

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="cooperative tracking-database lock",
    ):
        mutate_tracking_database.execute(
            database_path,
            plan_path,
            apply=True,
            expected_sha256="missing",
        )
    assert not database_path.exists()


def test_initialization_preserves_valid_custom_directory_exclusions(
    mutate_tracking_database,
) -> None:
    initialized = mutate_tracking_database.initial_database(
        {
            "kind": "initialize_database",
            "config": {
                "pptx_directory_exclusions": ["generated", "VendorCache"],
            },
        },
        index=0,
    )

    assert initialized["config"]["schema_version"] == 2
    assert initialized["config"]["pptx_directory_exclusions"] == [
        "generated",
        "VendorCache",
    ]


def test_mutation_rejects_malformed_directory_exclusions(
    mutate_tracking_database,
) -> None:
    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="case-insensitive duplicate",
    ):
        mutate_tracking_database.build_candidate(
            _base_database(),
            [
                {
                    "kind": "set_config",
                    "path": ["pptx_directory_exclusions"],
                    "expect": DEFAULT_DIRECTORY_EXCLUSIONS,
                    "value": ["venv", "VENV"],
                }
            ],
        )


def test_initialization_rejects_malformed_directory_exclusions(
    mutate_tracking_database,
) -> None:
    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="case-insensitive duplicate",
    ):
        mutate_tracking_database.initial_database(
            {
                "kind": "initialize_database",
                "config": {
                    "pptx_directory_exclusions": ["venv", "VENV"],
                },
            },
            index=0,
        )


def test_plan_strict_json_rejects_duplicate_keys(
    mutate_tracking_database,
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        '{"schema_version":1,"schema_version":1,"mutations":[]}\n',
        encoding="utf-8",
    )

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="duplicate object key 'schema_version'",
    ):
        mutate_tracking_database.load_plan(plan_path)


def test_plan_strict_json_rejects_non_roundtrippable_number(
    mutate_tracking_database,
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        '{"schema_version":1,"mutations":[{"kind":"set_config",'
        '"path":["ratio"],"expect":{"$missing":true},'
        '"value":0.12345678901234567890123456789}]}\n',
        encoding="utf-8",
    )

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="cannot round-trip losslessly",
    ):
        mutate_tracking_database.load_plan(plan_path)


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        pytest.param(
            b'{"schema_version":1,"mutations":'
            + b"[" * 500
            + b"{}"
            + b"]" * 500
            + b"}\n",
            "maximum supported JSON nesting depth 200",
            id="decoded-depth-limit",
        ),
        pytest.param(
            b'{"schema_version":1,"mutations":'
            + b"[" * 10_000
            + b"{}"
            + b"]" * 10_000
            + b"}\n",
            "maximum supported JSON nesting depth 200",
            id="decoder-recursion-limit",
        ),
        pytest.param(
            b'{"schema_version":1,"mutations":[{"kind":"set_config",'
            b'"path":["value"],"expect":{"$missing":true},'
            b'"value":"\\ud800"}]}\n',
            "unpaired UTF-16 surrogate",
            id="unpaired-surrogate",
        ),
    ],
)
def test_plan_strict_json_rejects_unsafe_tree(
    mutate_tracking_database,
    tmp_path: Path,
    raw: bytes,
    message: str,
) -> None:
    plan_path = tmp_path / "plan.json"
    plan_path.write_bytes(raw)

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match=message,
    ) as stopped:
        mutate_tracking_database.load_plan(plan_path)

    assert len(str(stopped.value)) < 1000
    assert plan_path.read_bytes() == raw


def test_talk_clarification_operation_accepts_only_structured_exact_fields(
    mutate_tracking_database,
) -> None:
    candidate, changes = mutate_tracking_database.build_candidate(
        _base_database(),
        [
            {
                "kind": "update_talk_clarification",
                "filename": "talk.md",
                "expect": {
                    "blind_spot_observations": MISSING,
                    "humor_postmortem": MISSING,
                },
                "set": {
                    "blind_spot_observations": {"room_energy": "high"},
                    "humor_postmortem": ["opening joke landed"],
                },
            }
        ],
    )

    assert candidate["talks"][0]["blind_spot_observations"] == {"room_energy": "high"}
    assert candidate["talks"][0]["humor_postmortem"] == ["opening joke landed"]
    assert changes[0]["kind"] == "update_talk_clarification"

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="must be a JSON object or array",
    ):
        mutate_tracking_database.build_candidate(
            _base_database(),
            [
                {
                    "kind": "update_talk_clarification",
                    "filename": "talk.md",
                    "expect": {"humor_postmortem": MISSING},
                    "set": {"humor_postmortem": "unstructured"},
                }
            ],
        )


# Every version below the current one, so the set widens with each bump
# instead of quietly leaving the newest stale version untested.
@pytest.mark.parametrize("schema_version", list(range(1, CURRENT_TALK_SCHEMA)))
@pytest.mark.parametrize(
    ("kind", "field", "value"),
    [
        ("update_talk_publishing", "shownotes_published", True),
        (
            "update_talk_clarification",
            "humor_postmortem",
            ["legacy talk must first be promoted by its domain writer"],
        ),
    ],
)
def test_talk_metadata_mutations_require_exact_current_talk_schema(
    mutate_tracking_database,
    schema_version: int,
    kind: str,
    field: str,
    value: object,
) -> None:
    database = _base_database()
    database["talks"][0]["schema_version"] = schema_version
    original = copy.deepcopy(database)

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match=f"must be exact current talk schema {CURRENT_TALK_SCHEMA}",
    ):
        mutate_tracking_database.build_candidate(
            database,
            [
                {
                    "kind": kind,
                    "filename": "talk.md",
                    "expect": {field: MISSING},
                    "set": {field: value},
                }
            ],
        )

    assert database == original


def _legacy_goal_for_mutation(kind: str) -> dict[str, Any]:
    goal = {
        key: copy.deepcopy(value)
        for key, value in _goal().items()
        if key
        not in {
            "verification_state",
            "verification_reasons",
            "supersedes_goal_id",
            "baseline_provenance",
        }
    }
    goal["schema_version"] = 1
    goal["kind"] = kind
    goal["antipattern_id"] = "shortchanged" if kind == "antipattern" else None
    return goal


@pytest.mark.parametrize("kind", ["antipattern", "underuse"])
def test_legacy_pattern_goals_are_report_only(
    mutate_tracking_database,
    kind: str,
) -> None:
    database = _base_database()
    goal = _legacy_goal_for_mutation(kind)
    database["improvement_goals"] = [goal]

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="historical schema-v1 .* skip and report",
    ):
        mutate_tracking_database.build_candidate(
            database,
            [
                {
                    "kind": "patch_improvement_goal_verification",
                    "id": goal["id"],
                    "expect": {"status": "active"},
                    "set": {"status": "stalled"},
                }
            ],
        )


@pytest.mark.parametrize("kind", ["pacing", "other"])
def test_legacy_independent_goals_allow_only_legacy_verification_fields(
    mutate_tracking_database,
    kind: str,
) -> None:
    database = _base_database()
    goal = _legacy_goal_for_mutation(kind)
    database["improvement_goals"] = [goal]
    mutation = {
        "kind": "patch_improvement_goal_verification",
        "id": goal["id"],
        "expect": {
            "status": "active",
            "current_value": "",
            "last_checked": None,
            "checked_by": None,
        },
        "set": {
            "status": "improving",
            "current_value": "3",
            "last_checked": "2026-08-01",
            "checked_by": "vault-ingress",
        },
    }

    candidate, changes = mutate_tracking_database.build_candidate(
        database,
        [mutation],
    )

    updated = candidate["improvement_goals"][0]
    assert updated["schema_version"] == 1
    assert updated["status"] == "improving"
    assert updated["current_value"] == "3"
    assert "verification_state" not in updated
    assert changes[0]["kind"] == "patch_improvement_goal_verification"

    forbidden = copy.deepcopy(mutation)
    forbidden["expect"] = {"verification_state": MISSING}
    forbidden["set"] = {"verification_state": "current"}
    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="unsupported fields.*verification_state",
    ):
        mutate_tracking_database.build_candidate(database, [forbidden])


def test_legacy_goal_retirement_preserves_every_other_field(
    mutate_tracking_database,
) -> None:
    database = _base_database()
    legacy = {
        key: copy.deepcopy(value)
        for key, value in _goal().items()
        if key
        not in {
            "verification_state",
            "verification_reasons",
            "supersedes_goal_id",
            "baseline_provenance",
        }
    }
    legacy.update({"id": "legacy-goal", "schema_version": 1})
    database["improvement_goals"] = [copy.deepcopy(legacy)]

    candidate, changes = mutate_tracking_database.build_candidate(
        database,
        [
            {
                "kind": "retire_improvement_goal",
                "id": "legacy-goal",
                "expect": legacy,
            }
        ],
    )

    retired = candidate["improvement_goals"][0]
    assert retired == {**legacy, "status": "retired"}
    assert changes == [
        {
            "kind": "retire_improvement_goal",
            "identity": "legacy-goal",
            "before": legacy,
            "after": {**legacy, "status": "retired"},
        }
    ]


@pytest.mark.parametrize("mutation_index", [1, 2, 3, 5, 6])
def test_complete_collection_records_reject_unknown_fields(
    mutate_tracking_database,
    mutation_index: int,
) -> None:
    mutation = copy.deepcopy(_complete_plan()["mutations"][mutation_index])
    mutation["record"]["unexpected"] = "drift"

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="unknown fields.*unexpected",
    ):
        mutate_tracking_database.build_candidate(_base_database(), [mutation])


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("shownotes_published", 1, "must be boolean"),
        ("shownotes_url", "", "must be a nonempty string"),
        ("youtube_id", "too-short", "11-character YouTube ID"),
    ],
)
def test_publishing_fields_are_type_validated(
    mutate_tracking_database,
    field: str,
    value: object,
    message: str,
) -> None:
    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match=message,
    ):
        mutate_tracking_database.build_candidate(
            _base_database(),
            [
                {
                    "kind": "update_talk_publishing",
                    "filename": "talk.md",
                    "expect": {field: MISSING},
                    "set": {field: value},
                }
            ],
        )


def test_json_preconditions_and_noops_are_type_sensitive(
    mutate_tracking_database,
) -> None:
    database = _base_database()
    database["config"] = _current_config(enabled=True)
    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="precondition failed",
    ):
        mutate_tracking_database.build_candidate(
            database,
            [
                {
                    "kind": "set_config",
                    "path": ["enabled"],
                    "expect": 1,
                    "value": False,
                }
            ],
        )

    candidate, changes = mutate_tracking_database.build_candidate(
        database,
        [
            {
                "kind": "set_config",
                "path": ["enabled"],
                "expect": True,
                "value": 1,
            }
        ],
    )
    assert candidate["config"]["enabled"] == 1
    assert type(candidate["config"]["enabled"]) is int
    assert changes

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="precondition failed",
    ):
        mutate_tracking_database.build_candidate(
            _base_database(),
            [
                {
                    "kind": "set_config",
                    "path": ["absent"],
                    "expect": {"$missing": 1},
                    "value": "new",
                }
            ],
        )


def test_delete_missing_nested_config_does_not_materialize_parents(
    mutate_tracking_database,
) -> None:
    candidate, changes = mutate_tracking_database.build_candidate(
        _base_database(),
        [
            {
                "kind": "set_config",
                "path": ["shownotes", "legacy", "enabled"],
                "expect": MISSING,
                "delete": True,
            },
            {
                "kind": "set_config",
                "path": ["shownotes", "enabled"],
                "expect": MISSING,
                "value": True,
            },
        ],
    )

    assert candidate["config"] == {
        "schema_version": 2,
        "pptx_directory_exclusions": DEFAULT_DIRECTORY_EXCLUSIONS,
        "shownotes": {"enabled": True},
    }
    assert len(changes) == 1
    assert changes[0]["identity"] == "shownotes.enabled"


def test_delete_missing_nested_config_preserves_exact_expectations(
    mutate_tracking_database,
) -> None:
    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="precondition failed",
    ):
        mutate_tracking_database.build_candidate(
            _base_database(),
            [
                {
                    "kind": "set_config",
                    "path": ["shownotes", "legacy", "enabled"],
                    "expect": {"$missing": 1},
                    "delete": True,
                }
            ],
        )

    database = _base_database()
    database["config"] = _current_config(shownotes={"legacy": None})
    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match=r"config\.shownotes\.legacy must be an object",
    ):
        mutate_tracking_database.build_candidate(
            database,
            [
                {
                    "kind": "set_config",
                    "path": ["shownotes", "legacy", "enabled"],
                    "expect": MISSING,
                    "delete": True,
                }
            ],
        )


def test_set_config_rejects_reserved_missing_marker_value(
    mutate_tracking_database,
) -> None:
    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="value cannot equal the reserved missing marker",
    ):
        mutate_tracking_database.build_candidate(
            _base_database(),
            [
                {
                    "kind": "set_config",
                    "path": ["legacy"],
                    "expect": MISSING,
                    "value": MISSING,
                }
            ],
        )

    candidate, _ = mutate_tracking_database.build_candidate(
        _base_database(),
        [
            {
                "kind": "set_config",
                "path": ["ordinary_object"],
                "expect": MISSING,
                "value": {"$missing": 1},
            }
        ],
    )
    assert candidate["config"]["ordinary_object"] == {"$missing": 1}


def test_delete_recovers_persisted_reserved_missing_marker(
    mutate_tracking_database,
    tmp_path: Path,
) -> None:
    database = _base_database()
    database["config"]["legacy"] = copy.deepcopy(MISSING)

    database_path = tmp_path / "tracking-database.json"
    plan_path = tmp_path / "plan.json"
    _write_json(database_path, database)
    _write_json(
        plan_path,
        {
            "schema_version": 1,
            "mutations": [
                {
                    "kind": "set_config",
                    "path": ["legacy"],
                    "expect": MISSING,
                    "delete": True,
                }
            ],
        },
    )
    before = database_path.read_bytes()

    dry_run = mutate_tracking_database.execute(
        database_path,
        plan_path,
        apply=False,
        expected_sha256=None,
    )
    assert dry_run["changed"] is True
    assert dry_run["database_written"] is False
    assert database_path.read_bytes() == before
    assert dry_run["changes"] == [
        {
            "kind": "set_config",
            "identity": "legacy",
            "before": MISSING,
            "after": MISSING,
            "before_exists": True,
            "after_exists": False,
        }
    ]

    applied = mutate_tracking_database.execute(
        database_path,
        plan_path,
        apply=True,
        expected_sha256=dry_run["input_sha256"],
    )
    result = json.loads(database_path.read_text(encoding="utf-8"))
    assert applied["database_written"] is True
    assert applied["changes"] == dry_run["changes"]
    assert "legacy" not in result["config"]


@pytest.mark.parametrize("legacy_value", [None, {"$missing": 1}, "value"])
def test_missing_expectation_recovery_rejects_other_present_values(
    mutate_tracking_database,
    legacy_value: object,
) -> None:
    database = _base_database()
    database["config"]["legacy"] = legacy_value

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="expected a missing value",
    ):
        mutate_tracking_database.build_candidate(
            database,
            [
                {
                    "kind": "set_config",
                    "path": ["legacy"],
                    "expect": MISSING,
                    "delete": True,
                }
            ],
        )


def test_boolean_plan_and_record_schema_versions_are_rejected(
    mutate_tracking_database,
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "plan.json"
    _write_json(plan_path, {"schema_version": True, "mutations": [{}]})
    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="schema_version must be 1",
    ):
        mutate_tracking_database.load_plan(plan_path)

    mutation = copy.deepcopy(_complete_plan()["mutations"][5])
    mutation["record"]["schema_version"] = True
    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="schema_version must be exact integer 1",
    ):
        mutate_tracking_database.build_candidate(_base_database(), [mutation])


@pytest.mark.parametrize("mutation_index", [1, 2, 5, 6])
def test_versioned_owner_records_require_schema_version(
    mutate_tracking_database,
    mutation_index: int,
) -> None:
    mutation = copy.deepcopy(_complete_plan()["mutations"][mutation_index])
    del mutation["record"]["schema_version"]

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="missing .*schema_version",
    ):
        mutate_tracking_database.build_candidate(_base_database(), [mutation])


@pytest.mark.parametrize("schema_version", [True, 1, 3])
def test_initialization_rejects_noncurrent_config_schema_version(
    mutate_tracking_database,
    schema_version,
) -> None:
    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="config.schema_version must be exact integer 2",
    ):
        mutate_tracking_database.initial_database(
            {
                "kind": "initialize_database",
                "config": {"schema_version": schema_version},
            },
            index=0,
        )


# Reviewed shownotes catalog-conflict repair (#236). `scan-shownotes.py --apply`
# refuses review-required entries, so an approved title or conference
# correction had no owner writer at all — the operator's only options were to
# leave a known-wrong catalog fact in place or edit the database directly.


def _catalog_database(**talk_fields: Any) -> dict[str, Any]:
    database = _base_database()
    database["talks"][0].update(
        {
            "title": "Monkey See Monkey Do",
            "conference": "DevOps Nashville 2024",
            **talk_fields,
        }
    )
    return database


def _repair(set_values: dict[str, Any], expect: dict[str, Any], **extra: Any):
    mutation = {
        "kind": "apply_reviewed_metadata",
        "filename": "talk.md",
        "expect": expect,
        "set": set_values,
    }
    mutation.update(extra)
    return mutation


def test_a_reviewed_conference_conflict_applies_with_an_exact_precondition(
    mutate_tracking_database,
) -> None:
    """Acceptance 1: the live DevOps Nashville case."""
    database = _catalog_database()

    candidate, changes = mutate_tracking_database.build_candidate(
        database,
        [
            _repair(
                {"conference": "DevOps Days Nashville 2024"},
                {"conference": "DevOps Nashville 2024"},
            )
        ],
    )

    assert candidate["talks"][0]["conference"] == "DevOps Days Nashville 2024"
    assert changes[0]["kind"] == "apply_reviewed_metadata"
    assert changes[0]["before"] == {"conference": "DevOps Nashville 2024"}
    # The input object is never mutated; only the candidate carries the repair.
    assert database["talks"][0]["conference"] == "DevOps Nashville 2024"


def test_a_reviewed_title_conflict_applies_without_opening_other_fields(
    mutate_tracking_database,
) -> None:
    """Acceptance 2: the live Voxxed Luxembourg case, and nothing wider."""
    database = _catalog_database()

    candidate, _changes = mutate_tracking_database.build_candidate(
        database,
        [
            _repair(
                {"title": "Monkey See Monkey Do at Voxxed Days Luxembourg 2026"},
                {"title": "Monkey See Monkey Do"},
            )
        ],
    )

    assert candidate["talks"][0]["title"].endswith("Voxxed Days Luxembourg 2026")
    assert candidate["talks"][0]["status"] == "processed"


@pytest.mark.parametrize(
    "field",
    ["status", "video_url", "slides_url", "transcript_source"],
)
def test_the_writer_refuses_every_field_outside_the_catalog_set(
    mutate_tracking_database, field
) -> None:
    """A reviewed metadata decision is not a licence to edit arbitrary talk fields."""
    database = _catalog_database()

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError, match="unsupported"
    ):
        mutate_tracking_database.build_candidate(
            database, [_repair({field: "anything"}, {field: None})]
        )


def test_a_stale_precondition_installs_nothing(mutate_tracking_database) -> None:
    """Acceptance 3: the reviewed value must still be the one that was reviewed."""
    database = _catalog_database()
    original = copy.deepcopy(database)

    with pytest.raises(mutate_tracking_database.TrackingDatabaseMutationError):
        mutate_tracking_database.build_candidate(
            database,
            [
                _repair(
                    {"conference": "DevOps Days Nashville 2024"},
                    {"conference": "Something Else Entirely"},
                )
            ],
        )

    assert database == original


def test_an_unknown_filename_installs_nothing(mutate_tracking_database) -> None:
    database = _catalog_database()
    mutation = _repair(
        {"conference": "DevOps Days Nashville 2024"},
        {"conference": "DevOps Nashville 2024"},
    )
    mutation["filename"] = "nobody.md"

    with pytest.raises(mutate_tracking_database.TrackingDatabaseMutationError):
        mutate_tracking_database.build_candidate(database, [mutation])


def test_a_duplicate_filename_installs_nothing(mutate_tracking_database) -> None:
    database = _catalog_database()
    database["talks"].append(copy.deepcopy(database["talks"][0]))

    with pytest.raises(mutate_tracking_database.TrackingDatabaseMutationError):
        mutate_tracking_database.build_candidate(
            database,
            [
                _repair(
                    {"conference": "DevOps Days Nashville 2024"},
                    {"conference": "DevOps Nashville 2024"},
                )
            ],
        )


def test_a_legacy_talk_schema_still_takes_a_catalog_repair(
    mutate_tracking_database,
) -> None:
    """Superseded by #333: this writer no longer requires the current generation.

    It once refused a legacy record like every other writer. That locked catalog
    corrections out of 209 of the 215 live talks, which no migration can lift —
    the generations between carry analysis a migration must not fabricate. A
    catalog repair reads no analysis field, so it does not need that gate.
    """
    database = _catalog_database()
    database["talks"][0]["schema_version"] = 4

    candidate, _ = mutate_tracking_database.build_candidate(
        database,
        [
            _repair(
                {"conference": "DevOps Days Nashville 2024"},
                {"conference": "DevOps Nashville 2024"},
            )
        ],
    )

    assert candidate["talks"][0]["conference"] == "DevOps Days Nashville 2024"
    assert candidate["talks"][0]["schema_version"] == 4


def test_a_metadata_only_change_refuses_a_reprocess_transition(
    mutate_tracking_database,
) -> None:
    """Acceptance 4, first half: the writer proves the change is metadata-only."""
    database = _catalog_database()

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError, match="metadata-only"
    ):
        mutate_tracking_database.build_candidate(
            database,
            [
                _repair(
                    {"conference": "DevOps Days Nashville 2024"},
                    {"conference": "DevOps Nashville 2024"},
                    reprocess={
                        "status": "needs-reprocessing",
                        "reprocess_reason": "not needed",
                    },
                )
            ],
        )


def test_an_analysis_invalidating_field_requires_the_transition_atomically(
    mutate_tracking_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Acceptance 4, second half.

    Both current fields are metadata-only, so the invalidating branch is
    exercised by classifying one as invalidating — which is exactly what adding
    such a field would do.
    """
    monkeypatch.setattr(
        mutate_tracking_database,
        "ANALYSIS_INVALIDATING_METADATA_FIELDS",
        frozenset({"conference"}),
    )
    database = _catalog_database()

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="invalidates derived analysis",
    ):
        mutate_tracking_database.build_candidate(
            database,
            [
                _repair(
                    {"conference": "DevOps Days Nashville 2024"},
                    {"conference": "DevOps Nashville 2024"},
                )
            ],
        )

    candidate, changes = mutate_tracking_database.build_candidate(
        database,
        [
            _repair(
                {"conference": "DevOps Days Nashville 2024"},
                {"conference": "DevOps Nashville 2024"},
                reprocess={
                    "status": "needs-reprocessing",
                    "reprocess_reason": "catalog conference corrected",
                },
            )
        ],
    )

    talk = candidate["talks"][0]
    assert talk["conference"] == "DevOps Days Nashville 2024"
    assert talk["status"] == "needs-reprocessing"
    assert talk["reprocess_reason"] == "catalog conference corrected"
    assert changes[0]["after"]["status"] == "needs-reprocessing"


def test_a_reprocess_transition_rejects_an_unsupported_status(
    mutate_tracking_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        mutate_tracking_database,
        "ANALYSIS_INVALIDATING_METADATA_FIELDS",
        frozenset({"conference"}),
    )
    database = _catalog_database()

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError, match="must be one of"
    ):
        mutate_tracking_database.build_candidate(
            database,
            [
                _repair(
                    {"conference": "DevOps Days Nashville 2024"},
                    {"conference": "DevOps Nashville 2024"},
                    reprocess={"status": "processed", "reprocess_reason": "nope"},
                )
            ],
        )


def test_unrelated_talk_fields_survive_the_repair(mutate_tracking_database) -> None:
    database = _catalog_database(
        date="2024-07-10", video_url="https://youtu.be/AbCdEfGhI_1"
    )

    candidate, _changes = mutate_tracking_database.build_candidate(
        database,
        [
            _repair(
                {"conference": "DevOps Days Nashville 2024"},
                {"conference": "DevOps Nashville 2024"},
            )
        ],
    )

    talk = candidate["talks"][0]
    assert talk["date"] == "2024-07-10"
    assert talk["video_url"] == "https://youtu.be/AbCdEfGhI_1"
    assert talk["title"] == "Monkey See Monkey Do"


def test_every_writable_metadata_field_is_classified(mutate_tracking_database) -> None:
    """The import-time guard that keeps a new field from defaulting to safe."""
    classified = (
        mutate_tracking_database.METADATA_ONLY_FIELDS
        | mutate_tracking_database.ANALYSIS_INVALIDATING_METADATA_FIELDS
    )
    assert mutate_tracking_database.METADATA_TALK_FIELDS <= classified


def _bound_catalog_database() -> dict[str, Any]:
    """A stored binding, both sides written, as the live vault carries them."""
    database = _base_database()
    database["talks"][0]["pptx_path"] = "Conference/Talk.pptx"
    database["pptx_catalog"] = [
        {
            "schema_version": 1,
            "pptx_path": "Conference/Talk.pptx",
            "talk_filename": "talk.md",
            "matched": True,
            "slide_count": 10,
            "visual_extracted": True,
        }
    ]
    return database


def _sever(**overrides: Any) -> dict[str, Any]:
    mutation: dict[str, Any] = {
        "kind": "sever_pptx_talk_binding",
        "pptx_path": "Conference/Talk.pptx",
        "expect": {
            "schema_version": 1,
            "pptx_path": "Conference/Talk.pptx",
            "talk_filename": "talk.md",
            "matched": True,
            "slide_count": 10,
            "visual_extracted": True,
        },
        "expect_talk_pptx_path": "Conference/Talk.pptx",
    }
    mutation.update(overrides)
    return {"schema_version": 1, "mutations": [mutation]}


def test_severing_clears_both_sides_of_the_binding(
    tmp_path: Path, mutate_tracking_database
) -> None:
    """Clearing only the catalog row leaves the talk still naming the deck, and
    every reader that resolves slides through `talks[].pptx_path` keeps drawing
    evidence from it."""
    database = _bound_catalog_database()
    candidate, _changes = mutate_tracking_database.build_candidate(
        database, _sever()["mutations"]
    )

    record = candidate["pptx_catalog"][0]
    assert record["talk_filename"] is None
    assert record["matched"] is False
    assert "pptx_path" not in candidate["talks"][0]
    # The deck still exists and the catalog still knows about it.
    assert record["pptx_path"] == "Conference/Talk.pptx"


def test_severing_records_a_change_for_each_side(
    tmp_path: Path, mutate_tracking_database
) -> None:
    _candidate, changes = mutate_tracking_database.build_candidate(
        _bound_catalog_database(), _sever()["mutations"]
    )

    assert [change["kind"] for change in changes] == [
        "sever_pptx_talk_binding",
        "clear_talk_pptx_path",
    ]


def test_a_stale_catalog_expectation_refuses_the_sever(
    mutate_tracking_database,
) -> None:
    """Assessed at one moment, applied at another."""
    database = _bound_catalog_database()
    plan = _sever()
    plan["mutations"][0]["expect"]["slide_count"] = 11

    with pytest.raises(mutate_tracking_database.TrackingDatabaseMutationError):
        mutate_tracking_database.build_candidate(database, plan["mutations"])


def test_a_stale_talk_expectation_refuses_the_sever(mutate_tracking_database) -> None:
    database = _bound_catalog_database()
    plan = _sever(expect_talk_pptx_path="Conference/Moved.pptx")

    with pytest.raises(mutate_tracking_database.TrackingDatabaseMutationError):
        mutate_tracking_database.build_candidate(database, plan["mutations"])


def test_severing_an_unbound_row_is_refused(mutate_tracking_database) -> None:
    """Reporting work that did not happen is worse than refusing it."""
    database = _bound_catalog_database()
    database["pptx_catalog"][0]["talk_filename"] = None
    database["pptx_catalog"][0]["matched"] = False
    plan = _sever()
    plan["mutations"][0]["expect"]["talk_filename"] = None
    plan["mutations"][0]["expect"]["matched"] = False

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="binds no talk",
    ):
        mutate_tracking_database.build_candidate(database, plan["mutations"])


def test_severing_a_row_that_does_not_exist_is_refused(
    mutate_tracking_database,
) -> None:
    database = _bound_catalog_database()
    plan = _sever(pptx_path="Conference/Absent.pptx")

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="does not exist",
    ):
        mutate_tracking_database.build_candidate(database, plan["mutations"])


def test_severing_a_v3_row_nulls_its_identity_assessment(
    mutate_tracking_database,
) -> None:
    """An unbound row's assessment is null by the shape's own rule."""
    database = _bound_catalog_database()
    record = database["pptx_catalog"][0]
    record.update(
        {
            "schema_version": 3,
            "visual_extracted": False,
            "visual_evidence": None,
            "identity_assessment": {
                "schema_version": 1,
                "pptx_path": "Conference/Talk.pptx",
                "verdict": "review_required",
                "artifact_role": "delivery",
                "selected_talk_filename": None,
                "reason_codes": ["identity_unassessed_legacy_binding"],
                "candidates": [],
            },
        }
    )
    plan = _sever(expect=copy.deepcopy(record))

    candidate, _changes = mutate_tracking_database.build_candidate(
        database, plan["mutations"]
    )

    assert candidate["pptx_catalog"][0]["identity_assessment"] is None


def test_severing_a_v1_row_does_not_invent_an_assessment_field(
    mutate_tracking_database,
) -> None:
    """Only a v3 row carries the field; adding it would be a shape v1 lacks."""
    candidate, _changes = mutate_tracking_database.build_candidate(
        _bound_catalog_database(), _sever()["mutations"]
    )

    assert "identity_assessment" not in candidate["pptx_catalog"][0]


def test_severing_a_wrong_row_spares_a_talks_binding_to_another_deck(
    mutate_tracking_database,
) -> None:
    """A talk can name a correctly-bound deck while some other catalog row
    wrongly claims it. Severing the wrong row must not destroy the right
    binding — the talk side is cleared only when it names THIS deck.
    """
    database = _bound_catalog_database()
    # The talk's own binding points at the deck it really belongs to.
    database["talks"][0]["pptx_path"] = "Conference/Correct.pptx"
    plan = _sever(expect_talk_pptx_path="Conference/Correct.pptx")

    candidate, changes = mutate_tracking_database.build_candidate(
        database, plan["mutations"]
    )

    assert candidate["pptx_catalog"][0]["talk_filename"] is None
    assert candidate["talks"][0]["pptx_path"] == "Conference/Correct.pptx"
    assert [change["kind"] for change in changes] == ["sever_pptx_talk_binding"]


# Reviewed delivery-date repair (#333). The identity-registration run found 11
# talks whose cataloged year disagreed with the recording, and the reviewed
# metadata writer covered `title` and `conference` but not `date` — so a proven
# wrong delivery date had no owner writer at all.


def test_a_reviewed_delivery_date_applies_with_an_exact_precondition(
    mutate_tracking_database,
) -> None:
    database = _catalog_database(date="2014")

    candidate, changes = mutate_tracking_database.build_candidate(
        database,
        [_repair({"date": "2013-10-19"}, {"date": "2014"})],
    )

    assert candidate["talks"][0]["date"] == "2013-10-19"
    assert changes[0]["kind"] == "apply_reviewed_metadata"
    assert changes[0]["before"] == {"date": "2014"}
    assert database["talks"][0]["date"] == "2014"


def test_a_reviewed_delivery_date_may_be_a_bare_year(
    mutate_tracking_database,
) -> None:
    """A coarse record is a real delivery date, so the writer accepts `YYYY`."""
    database = _catalog_database(date="2019")

    candidate, _ = mutate_tracking_database.build_candidate(
        database,
        [_repair({"date": "2016"}, {"date": "2019"})],
    )

    assert candidate["talks"][0]["date"] == "2016"


def test_a_reviewed_delivery_date_stays_readable_by_the_catalog_parser(
    mutate_tracking_database,
) -> None:
    """An unparseable date would trade a wrong date for an uncheckable one."""
    database = _catalog_database(date="2014")

    for rejected in ("October 2013", "2013-13-01", "13-10-2013", "2013/10/19"):
        with pytest.raises(
            mutate_tracking_database.TrackingDatabaseMutationError
        ) as excinfo:
            mutate_tracking_database.build_candidate(
                database,
                [_repair({"date": rejected}, {"date": "2014"})],
            )
        assert "must be YYYY or an ISO-8601 calendar date" in str(excinfo.value)


def test_a_reviewed_date_repair_does_not_open_unrelated_talk_fields(
    mutate_tracking_database,
) -> None:
    database = _catalog_database(date="2014")

    with pytest.raises(mutate_tracking_database.TrackingDatabaseMutationError):
        mutate_tracking_database.build_candidate(
            database,
            [_repair({"date": "2013", "status": "pending"}, {"date": "2014"})],
        )


# Owner-reviewed provider-title equivalence ledger (#333).


def _equivalence(**updates: Any) -> dict[str, Any]:
    record = {
        "schema_version": 1,
        "video_id": "QS-_4k7o7A4",
        "provider_title": "JavaDay Kiev 2014: Spring - битва конфигураций",
        "reason": "cross_language_title",
        "evidence": "owner-reviewed translation of the catalog title",
        "verified_at": "2026-08-18T12:00:00Z",
    }
    record.update(updates)
    return record


def _record_equivalence(**updates: Any) -> dict[str, Any]:
    mutation = {
        "kind": "record_source_title_equivalence",
        "filename": "talk.md",
        "equivalence": _equivalence(),
    }
    mutation.update(updates)
    return mutation


def test_a_reviewed_title_equivalence_is_appended_with_a_stamped_version(
    mutate_tracking_database,
) -> None:
    database = _catalog_database()

    unstamped = _equivalence()
    del unstamped["schema_version"]

    candidate, changes = mutate_tracking_database.build_candidate(
        database, [_record_equivalence(equivalence=unstamped)]
    )

    recorded = candidate["talks"][0]["source_title_equivalence"]
    assert len(recorded) == 1
    assert recorded[0]["schema_version"] == 1
    assert recorded[0]["reason"] == "cross_language_title"
    assert changes[0]["kind"] == "record_source_title_equivalence"
    assert "source_title_equivalence" not in database["talks"][0]


def test_a_second_equivalence_appends_rather_than_replacing(
    mutate_tracking_database,
) -> None:
    database = _catalog_database(source_title_equivalence=[_equivalence()])

    candidate, _ = mutate_tracking_database.build_candidate(
        database,
        [
            _record_equivalence(
                equivalence=_equivalence(
                    video_id="wd-mXqXdfk0",
                    provider_title="JavaDay Kiev 2014: Транcформации",
                )
            )
        ],
    )

    assert len(candidate["talks"][0]["source_title_equivalence"]) == 2


def test_a_duplicate_equivalence_is_refused(mutate_tracking_database) -> None:
    database = _catalog_database(source_title_equivalence=[_equivalence()])

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError
    ) as excinfo:
        mutate_tracking_database.build_candidate(database, [_record_equivalence()])

    assert "duplicates an equivalence" in str(excinfo.value)


@pytest.mark.parametrize(
    "invalid",
    [
        {"reason": "looked_close_enough"},
        {"evidence": ""},
        {"verified_at": "2026-08-18T12:00:00"},
        {"video_id": ""},
    ],
)
def test_an_unreviewable_equivalence_is_refused(
    mutate_tracking_database, invalid: dict[str, Any]
) -> None:
    database = _catalog_database()

    with pytest.raises(mutate_tracking_database.TrackingDatabaseMutationError):
        mutate_tracking_database.build_candidate(
            database, [_record_equivalence(equivalence=_equivalence(**invalid))]
        )


def test_a_whitespace_variant_duplicate_equivalence_is_refused(
    mutate_tracking_database,
) -> None:
    """The reader treats these as one approval, so the writer must too."""
    database = _catalog_database(source_title_equivalence=[_equivalence()])
    # Trimmed (the validator rejects untrimmed outright), but carrying an
    # internal whitespace run and NFD composition — both of which the reader
    # canonicalizes away, so both name the same approval.
    spaced = _equivalence(
        provider_title=unicodedata.normalize(
            "NFD", "JavaDay Kiev 2014: Spring -  битва конфигураций"
        )
    )

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError
    ) as excinfo:
        mutate_tracking_database.build_candidate(
            database, [_record_equivalence(equivalence=spaced)]
        )

    assert "duplicates an equivalence" in str(excinfo.value)


@pytest.mark.parametrize("version", [2, 0, True, "1"])
def test_an_equivalence_with_a_foreign_generation_is_refused(
    mutate_tracking_database, version: object
) -> None:
    database = _catalog_database()

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError
    ) as excinfo:
        mutate_tracking_database.build_candidate(
            database,
            [_record_equivalence(equivalence=_equivalence(schema_version=version))],
        )

    assert "schema_version must be 1" in str(excinfo.value)


# Legacy-generation catalog repair (#333). 209 of the 215 live talk records are
# schema v1, and no migration lifts them: the generations between carry analysis
# a migration is forbidden to fabricate. Holding a date repair to the current
# generation locked the correction out of the whole live catalog.


@pytest.mark.parametrize("version", [1, 2, 3, 4, 5, 6])
def test_a_catalog_repair_reaches_every_readable_talk_generation(
    mutate_tracking_database, version: int
) -> None:
    database = _catalog_database(date="2014", schema_version=version)

    candidate, _ = mutate_tracking_database.build_candidate(
        database, [_repair({"date": "2013-10-19"}, {"date": "2014"})]
    )

    assert candidate["talks"][0]["date"] == "2013-10-19"


def test_a_catalog_repair_leaves_the_records_generation_untouched(
    mutate_tracking_database,
) -> None:
    """Repairing a catalog fact must not claim the record was reanalyzed."""
    database = _catalog_database(date="2014", schema_version=1)

    candidate, _ = mutate_tracking_database.build_candidate(
        database, [_repair({"date": "2013"}, {"date": "2014"})]
    )

    assert candidate["talks"][0]["schema_version"] == 1


@pytest.mark.parametrize("version", [0, 7, "6", True])
def test_a_catalog_repair_still_refuses_an_unreadable_generation(
    mutate_tracking_database, version: object
) -> None:
    """Out-of-range generations are refused; the database assessment gets there
    first, so this asserts the refusal rather than which layer produced it."""
    database = _catalog_database(date="2014")
    database["talks"][0]["schema_version"] = version

    with pytest.raises(mutate_tracking_database.TrackingDatabaseMutationError):
        mutate_tracking_database.build_candidate(
            database, [_repair({"date": "2013"}, {"date": "2014"})]
        )


def test_other_writers_still_require_the_current_generation(
    mutate_tracking_database,
) -> None:
    """The relaxation is scoped to catalog repair, not opened to every writer."""
    database = _catalog_database(schema_version=1)

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError
    ) as excinfo:
        mutate_tracking_database.build_candidate(
            database,
            [
                {
                    "kind": "update_talk_publishing",
                    "filename": "talk.md",
                    "expect": {"shownotes_published": False},
                    "set": {"shownotes_published": True},
                }
            ],
        )

    assert "exact current talk schema 6" in str(excinfo.value)
