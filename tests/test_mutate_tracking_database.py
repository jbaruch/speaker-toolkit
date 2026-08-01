"""Tests for the typed owner mutation-plan surface."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest


MISSING = {"$missing": True}


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _base_database() -> dict[str, object]:
    return {
        "config": {},
        "talks": [{"filename": "talk.md", "status": "processed"}],
        "pptx_catalog": [],
        "qr_codes": [],
        "resources": [],
        "thumbnails": [],
        "confirmed_intents": [],
        "improvement_goals": [],
    }


def _goal() -> dict[str, object]:
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


def _complete_plan() -> dict[str, object]:
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
                    "schema_version": 1,
                    "pptx_path": "Conference/Talk.pptx",
                    "talk_filename": "talk.md",
                    "matched": True,
                    "slide_count": 10,
                    "visual_extracted": False,
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
    raw = b'{"config":{"speaker_name":"Ada"},"talks":[]}\n'
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
    assert initialized["config"]["schema_version"] == 1
    assert initialized["talks"] == []


def test_initialization_surfaces_owner_io_failure_as_mutation_error(
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
    tracking_database_io.lock_path_for(database_path).symlink_to(outside_lock)

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

    assert candidate["talks"][0]["blind_spot_observations"] == {
        "room_energy": "high"
    }
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


def test_legacy_goal_retirement_preserves_every_other_field(
    mutate_tracking_database,
) -> None:
    database = _base_database()
    legacy = {
        "id": "legacy-goal",
        "schema_version": 1,
        "status": "active",
        "legacy_note": {"must": "survive"},
        "verification_reasons": ["historical"],
    }
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
    database["config"] = {"enabled": True}
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

    assert candidate["config"] == {"shownotes": {"enabled": True}}
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
    database["config"] = {"shownotes": {"legacy": None}}
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


def test_initialization_rejects_noninteger_config_schema_version(
    mutate_tracking_database,
) -> None:
    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="config.schema_version must be exact integer 1",
    ):
        mutate_tracking_database.initial_database(
            {
                "kind": "initialize_database",
                "config": {"schema_version": True},
            },
            index=0,
        )
