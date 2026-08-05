"""Tracking-database schema ownership and migration tests."""

from __future__ import annotations

import copy
import hashlib
import json
import os

import pytest


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


def _legacy_goal(*, goal_id: str = "legacy") -> dict:
    return {
        "id": goal_id,
        "issue": "Keep the final section unhurried",
        "kind": "pacing",
        "antipattern_id": None,
        "metric": "minutes remaining at final section",
        "baseline_value": "2 minutes",
        "target": "at least 5 minutes",
        "set_date": "2026-06-11",
        "set_by": "vault-clarification",
        "status": "active",
        "current_value": "",
        "last_checked": None,
        "checked_by": None,
    }


def _current_goal(*, goal_id: str = "current") -> dict:
    return {
        **_legacy_goal(goal_id=goal_id),
        "schema_version": 2,
        "kind": "other",
        "metric": "audience questions answered",
        "baseline_value": "3",
        "target": "5",
        "verification_state": "pending",
        "verification_reasons": [],
        "supersedes_goal_id": None,
        "baseline_provenance": {"lane": "independent"},
    }


def _legacy_talk(*, filename: str = "one.md") -> dict:
    return {
        "filename": filename,
        "status": "processed",
        "pattern_observations": {
            "source_inspection": {"transcript": "legacy-unverified"},
            "patterns_detected": [
                {
                    "pattern_id": "hook",
                    "evidence_citations": [{"source": "transcript"}],
                }
            ],
        },
        "source_rejections": [
            {
                "source_type": "video",
                "url": "https://example.test/wrong",
                "reason": "wrong delivery",
                "evidence": "title and event do not match",
                "verified_at": "2026-07-31T14:00:00-05:00",
            }
        ],
    }


def _baseline_for_claim(version: int, *, filename: str = "one.md") -> dict:
    baseline = {
        "schema_version": 2 if version == 5 else 1,
        "as_of": "2026-07-31T12:00:00+00:00",
        "scope": "global",
        "active_batch_excluded": True,
        "excluded_filenames": [filename],
        "eligible_statuses": ["processed", "processed_partial"],
        "pattern_scoring_generation_status": "current",
        "pattern_scoring_generation_reasons": [],
        "pattern_catalog_fingerprint": "a" * 64,
        "pattern_scoring_schema_version": 5 if version == 5 else 4,
        "scored_talk_count": 0,
        "pattern_score_sum": 0,
        "average_pattern_score": None,
    }
    if version == 5:
        baseline.update(
            {
                "eligible_talk_count": 0,
                "opportunity_coverage_identity": None,
                "raw_score_comparison_status": "unavailable",
                "raw_score_comparison_reason": "empty_current_cohort",
            }
        )
    return baseline


def _claim_for_version(
    version: int,
    *,
    generation: int,
    state: str,
    batch_id: str,
    filename: str = "one.md",
) -> dict:
    claim = {
        "schema_version": version,
        "run_id": "schema-test",
        "batch_id": batch_id,
        "claimed_at": "2026-07-31T12:00:00+00:00",
        "previous_status": "needs-reprocessing",
        "reprocess_generation": generation,
        "state": state,
    }
    if version >= 3:
        claim.update(
            {
                "required_return_schema_version": version,
                "adherence_baseline": _baseline_for_claim(
                    version,
                    filename=filename,
                ),
            }
        )
    if state != "claimed":
        claim.update(
            {
                "released_at": "2026-07-31T13:00:00+00:00",
                "release_reason": "schema_test_closed",
            }
        )
    return claim


def _legacy_database() -> dict:
    return {
        "config": {"python_path": "/opt/python"},
        "talks": [_legacy_talk()],
        "pptx_catalog": [
            {
                "pptx_path": "decks/one.pptx",
                "talk_filename": "one.md",
                "matched": True,
                "slide_count": 42,
                "visual_extracted": False,
            }
        ],
        "qr_codes": [
            {
                "talk_slug": "one",
                "target_url": "https://example.test/one",
                "shortener": "none",
                "short_path": None,
                "short_url": "https://example.test/one",
                "shortener_link_id": None,
                "qr_png_rel_path": "illustrations/one-qr.png",
                "created_at": "2026-07-01",
                "updated_at": "2026-07-01",
            }
        ],
        "resources": [
            {
                "talk_slug": "one",
                "item_count": 3,
                "category_breakdown": {"url": 3},
            }
        ],
        "thumbnails": [
            {
                "talk_slug": "one",
                "youtube_url": "https://youtube.test/watch?v=abcdefghijk",
                "source_slide_num": 7,
                "speaker_photo_used": "photos/speaker.png",
                "thumbnail_path": "illustrations/thumbnail.png",
                "shownotes_thumbnail_path": "assets/one-thumbnail.png",
                "dimensions": "1280x720",
                "file_size_kb": 512,
                "created_at": "2026-07-02",
                "approved": True,
            }
        ],
        "confirmed_intents": [
            {
                "pattern": "hook",
                "intent": "deliberate",
                "rule": "Open with the result",
                "note": "",
                "confirmed_date": "2026-07-03",
                "source_talks": ["one.md"],
            }
        ],
        "improvement_goals": [_legacy_goal(), _current_goal()],
    }


def _expected_migration(database: dict) -> dict:
    expected = copy.deepcopy(database)
    expected["schema_version"] = 1
    expected["config"]["schema_version"] = 2
    expected["config"]["pptx_directory_exclusions"] = DEFAULT_DIRECTORY_EXCLUSIONS
    for talk in expected["talks"]:
        talk.setdefault("schema_version", 1)
        for rejection in talk.get("source_rejections", []):
            rejection.setdefault("schema_version", 1)
    for collection in (
        "pptx_catalog",
        "qr_codes",
        "resources",
        "thumbnails",
        "confirmed_intents",
    ):
        for record in expected.setdefault(collection, []):
            record.setdefault("schema_version", 1)
    for goal in expected.setdefault("improvement_goals", []):
        goal.setdefault("schema_version", 1)
    for collection in (
        "talks",
        "pptx_catalog",
        "qr_codes",
        "resources",
        "thumbnails",
        "confirmed_intents",
        "improvement_goals",
    ):
        expected.setdefault(collection, [])
    return expected


def test_legacy_reader_accepts_without_mutating(tracking_database):
    database = _legacy_database()
    original = copy.deepcopy(database)

    assessment = tracking_database.assess_tracking_database(database)

    assert assessment.as_dict() == {
        "usable": True,
        "state": "legacy",
        "schema_version": 0,
        "accepted_schema_versions": [0, 1],
        "reason_codes": [],
    }
    assert database == original


def test_future_root_is_no_usable_prior_state(tracking_database):
    assessment = tracking_database.assess_tracking_database(
        _legacy_database() | {"schema_version": 2}
    )

    assert assessment.usable is False
    assert assessment.state == "unsupported"
    assert assessment.reason_codes == (
        "tracking_database_schema_version_unsupported",
    )


def test_explicit_root_zero_is_not_implicit_legacy_state(tracking_database):
    database = _legacy_database() | {"schema_version": 0}
    original = copy.deepcopy(database)

    assessment = tracking_database.assess_tracking_database(database)

    assert assessment.usable is False
    assert assessment.reason_codes == (
        "tracking_database_schema_version_unsupported",
    )
    with pytest.raises(tracking_database.TrackingDatabaseError):
        tracking_database.migrate_tracking_database(database)
    assert database == original


@pytest.mark.parametrize(
    ("collection", "record"),
    [
        (
            "talks",
            {
                "schema_version": 6,
                "talk_id": "future-talk",
                "pattern_observations": ["future-shape"],
            },
        ),
        (
            "pptx_catalog",
            {"schema_version": 2, "path": "future/deck.pptx"},
        ),
    ],
)
def test_future_owner_shape_is_classified_before_legacy_identity_validation(
    tracking_database,
    collection,
    record,
):
    database = _legacy_database()
    database[collection] = [record]

    assessment = tracking_database.assess_tracking_database(database)

    assert assessment.usable is False
    assert assessment.reason_codes == (
        f"{collection}_schema_version_unsupported",
    )


@pytest.mark.parametrize(
    ("record_class", "reason_code"),
    [
        ("config", "config_schema_version_unsupported"),
        ("talks", "talks_schema_version_unsupported"),
        ("pptx_catalog", "pptx_catalog_schema_version_unsupported"),
        ("qr_codes", "qr_codes_schema_version_unsupported"),
        ("resources", "resources_schema_version_unsupported"),
        ("thumbnails", "thumbnails_schema_version_unsupported"),
        ("confirmed_intents", "confirmed_intents_schema_version_unsupported"),
        ("improvement_goals", "improvement_goals_schema_version_unsupported"),
        ("source_rejections", "source_rejections_schema_version_unsupported"),
    ],
)
@pytest.mark.parametrize("unsupported_version", [0, 99])
def test_explicit_sentinel_or_future_record_is_not_migrated(
    tracking_database,
    record_class,
    reason_code,
    unsupported_version,
):
    database = _legacy_database()
    if record_class == "config":
        database["config"]["schema_version"] = unsupported_version
    elif record_class == "source_rejections":
        database["talks"][0]["source_rejections"][0][
            "schema_version"
        ] = unsupported_version
    else:
        database[record_class][0]["schema_version"] = unsupported_version

    assessment = tracking_database.assess_tracking_database(database)

    assert assessment.usable is False
    assert assessment.reason_codes == (reason_code,)
    with pytest.raises(tracking_database.TrackingDatabaseError):
        tracking_database.migrate_tracking_database(database)


def test_future_pattern_evidence_is_no_usable_prior_state_without_mutation(
    tracking_database,
):
    database = _legacy_database()
    database["talks"][0]["pattern_observations"]["evidence_schema_version"] = 99
    before = copy.deepcopy(database)

    assessment = tracking_database.assess_tracking_database(database)

    assert assessment.usable is False
    assert assessment.reason_codes == (
        "pattern_evidence_schema_version_unsupported",
    )
    assert database == before


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda value: value.update(config=[]), "'config' must be an object"),
        (lambda value: value.update(talks={}), "'talks' must be an array"),
        (
            lambda value: value["talks"].append(_legacy_talk()),
            "duplicate talk filename",
        ),
        (
            lambda value: value["pptx_catalog"][0].update(matched=False),
            "matched must equal",
        ),
        (
            lambda value: value["resources"][0].update(item_count=2),
            "category_breakdown total",
        ),
        (
            lambda value: value["thumbnails"][0].update(speaker_photo_used=True),
            "speaker_photo_used must be a non-empty",
        ),
        (
            lambda value: value["confirmed_intents"][0].update(
                source_talk="one.md"
            ),
            "may use only one",
        ),
        (
            lambda value: value["improvement_goals"][0].pop("target"),
            "missing fields",
        ),
        (
            lambda value: value["talks"][0]["source_rejections"][0].update(
                verified_at="2026-07-31"
            ),
            "timezone-aware",
        ),
    ],
)
def test_malformed_legacy_shape_fails_before_migration(
    tracking_database,
    change,
    message,
):
    database = _legacy_database()
    change(database)

    with pytest.raises(tracking_database.TrackingDatabaseError, match=message):
        tracking_database.assess_tracking_database(database)


@pytest.mark.parametrize(
    ("collection", "identity"),
    [
        ("talks", "filename"),
        ("pptx_catalog", "pptx_path"),
        ("qr_codes", "talk_slug"),
        ("resources", "talk_slug"),
        ("thumbnails", "talk_slug"),
        ("confirmed_intents", "pattern"),
        ("improvement_goals", "id"),
    ],
)
def test_duplicate_owner_identity_is_rejected(
    tracking_database,
    collection,
    identity,
):
    database = _legacy_database()
    database[collection].append(copy.deepcopy(database[collection][0]))

    with pytest.raises(
        tracking_database.TrackingDatabaseError,
        match=f"duplicate .*{identity}",
    ):
        tracking_database.assess_tracking_database(database)


def test_owner_migration_only_adds_owned_version_keys(tracking_database):
    database = _legacy_database()
    original = copy.deepcopy(database)

    result = tracking_database.migrate_tracking_database(database)

    assert result.changed is True
    assert result.from_schema_version == 0
    assert result.to_schema_version == 1
    assert database == original
    assert result.database == _expected_migration(original)
    assert result.database["talks"][0]["schema_version"] == 1
    assert (
        result.database["talks"][0]["pattern_observations"]
        == original["talks"][0]["pattern_observations"]
    )
    assert result.record_counts == {
        "config": 1,
        "talks": 1,
        "pptx_catalog": 1,
        "qr_codes": 1,
        "resources": 1,
        "thumbnails": 1,
        "confirmed_intents": 1,
        "improvement_goals": 1,
        "source_rejections": 1,
    }
    assert tracking_database.assess_tracking_database(result.database).state == "current"


def test_talk_count_excludes_nested_source_rejection_stamp(tracking_database):
    database = _legacy_database()
    database["talks"][0]["schema_version"] = 1

    result = tracking_database.migrate_tracking_database(database)

    assert result.record_counts["talks"] == 0
    assert result.record_counts["source_rejections"] == 1


@pytest.mark.parametrize("evidence_version", [1, 2])
def test_owner_migration_preserves_supported_pattern_evidence_exactly(
    tracking_database,
    evidence_version,
):
    database = _legacy_database()
    observations = database["talks"][0]["pattern_observations"]
    observations["evidence_schema_version"] = evidence_version
    observations["antipatterns_detected"] = [
        {
            "pattern_id": "wall-of-text",
            "evidence_citations": [{"source": "slides", "slide_numbers": [3]}],
        }
    ]
    before = copy.deepcopy(observations)

    migrated = tracking_database.migrate_tracking_database(database).database

    assert migrated["talks"][0]["pattern_observations"] == before


@pytest.mark.parametrize(
    "legacy_observations",
    [
        None,
        [],
        [
            {"pattern": "hook", "evidence": "opening line"},
            {"pattern": "callback", "evidence": "closing line"},
        ],
    ],
)
def test_implicit_v1_migration_preserves_legacy_observation_shapes(
    tracking_database,
    legacy_observations,
):
    database = _legacy_database()
    database["talks"][0]["pattern_observations"] = copy.deepcopy(
        legacy_observations
    )

    migrated = tracking_database.migrate_tracking_database(database).database

    assert migrated["talks"][0]["pattern_observations"] == legacy_observations
    assert migrated["talks"][0]["schema_version"] == 1


def test_future_source_identity_receipt_does_not_poison_root_migration(
    tracking_database,
):
    database = _legacy_database()
    database["talks"][0]["source_identity"] = {
        "schema_version": 99,
        "provider": "future-provider",
        "future_receipt": {"preserve": True},
    }
    before = copy.deepcopy(database["talks"][0]["source_identity"])

    migrated = tracking_database.migrate_tracking_database(database).database

    assert migrated["talks"][0]["source_identity"] == before


@pytest.mark.parametrize("current_root", [False, True])
@pytest.mark.parametrize("claim_version", [1, 2, 3, 4, 5])
def test_legacy_and_current_roots_accept_supported_claim_version_boundaries(
    tracking_database,
    current_root,
    claim_version,
):
    database = _legacy_database()
    if current_root:
        database = tracking_database.migrate_tracking_database(database).database
    database["talks"][0]["status"] = "reprocessing-inflight"
    database["talks"][0]["reprocess_generation"] = 2
    database["talks"][0]["_queue_claim"] = _claim_for_version(
        claim_version,
        generation=2,
        state="claimed",
        batch_id="current",
    )
    database["talks"][0]["_queue_claim_history"] = [
        _claim_for_version(
            claim_version,
            generation=1,
            state="stale_recovered",
            batch_id="history",
        )
    ]

    assessment = tracking_database.assess_tracking_database(database)

    assert assessment.usable is True
    assert assessment.state == ("current" if current_root else "legacy")


@pytest.mark.parametrize("current_root", [False, True])
@pytest.mark.parametrize("claim_location", ["current", "history"])
@pytest.mark.parametrize(
    "malformed_claim",
    [
        {},
        {"schema_version": 0},
        {"schema_version": 3, "required_return_schema_version": 3},
        {
            "schema_version": 3,
            "required_return_schema_version": 3,
            "adherence_baseline": {},
        },
        {
            "schema_version": 4,
            "required_return_schema_version": 4,
            "adherence_baseline": {"schema_version": 2},
        },
        {
            "schema_version": 5,
            "required_return_schema_version": 5,
            "adherence_baseline": {"schema_version": 1},
        },
    ],
)
def test_legacy_and_current_roots_reject_malformed_claim_versions(
    tracking_database,
    current_root,
    claim_location,
    malformed_claim,
):
    database = _legacy_database()
    if current_root:
        database = tracking_database.migrate_tracking_database(database).database
    if claim_location == "current":
        database["talks"][0]["_queue_claim"] = copy.deepcopy(malformed_claim)
    else:
        database["talks"][0]["_queue_claim_history"] = [
            copy.deepcopy(malformed_claim)
        ]

    with pytest.raises(tracking_database.TrackingDatabaseError):
        tracking_database.assess_tracking_database(database)


@pytest.mark.parametrize("current_root", [False, True])
@pytest.mark.parametrize("claim_location", ["current", "history"])
def test_future_claim_is_no_usable_state_before_old_nested_validation(
    tracking_database,
    current_root,
    claim_location,
):
    database = _legacy_database()
    if current_root:
        database = tracking_database.migrate_tracking_database(database).database
    database["talks"][0]["schema_version"] = 5
    database["talks"][0]["pattern_observations"] = ["future-owned-shape"]
    future_claim = {
        "schema_version": 6,
        "future_identity": "not-an-old-run-id",
        "state": {"future": True},
    }
    if claim_location == "current":
        database["talks"][0]["_queue_claim"] = future_claim
        database["talks"][0]["_queue_claim_history"] = {
            "future_history_shape": True
        }
    else:
        database["talks"][0]["_queue_claim_history"] = [future_claim]

    assessment = tracking_database.assess_tracking_database(database)

    assert assessment.usable is False
    assert assessment.reason_codes == (
        "queue_claim_schema_version_unsupported",
    )


def test_future_claim_baseline_is_classified_before_known_baseline_shape(
    tracking_database,
):
    database = _legacy_database()
    database["talks"][0]["_queue_claim"] = {
        "schema_version": 5,
        "adherence_baseline": {
            "schema_version": 99,
            "future_snapshot": {"shape": "opaque"},
        },
    }

    assessment = tracking_database.assess_tracking_database(database)

    assert assessment.usable is False
    assert assessment.reason_codes == (
        "adherence_baseline_schema_version_unsupported",
    )


@pytest.mark.parametrize("current_root", [False, True])
def test_legacy_and_current_roots_reject_malformed_claim_history(
    tracking_database,
    current_root,
):
    database = _legacy_database()
    if current_root:
        database = tracking_database.migrate_tracking_database(database).database
    database["talks"][0]["_queue_claim_history"] = {}

    with pytest.raises(
        tracking_database.TrackingDatabaseError,
        match="_queue_claim_history must be an array",
    ):
        tracking_database.assess_tracking_database(database)


def test_migration_rejects_queue_invalid_open_history_record(
    tracking_database,
):
    database = _legacy_database()
    database["talks"][0]["_queue_claim_history"] = [
        _claim_for_version(
            1,
            generation=1,
            state="claimed",
            batch_id="invalid-history",
        )
    ]
    original = copy.deepcopy(database)

    with pytest.raises(
        tracking_database.TrackingDatabaseError,
        match="historical claims must be closed",
    ):
        tracking_database.migrate_tracking_database(database)

    assert database == original


def test_owner_migration_adds_absent_owned_collections(tracking_database):
    database = {"config": {}, "talks": []}

    result = tracking_database.migrate_tracking_database(database)

    for collection in (
        "pptx_catalog",
        "qr_codes",
        "resources",
        "thumbnails",
        "confirmed_intents",
        "improvement_goals",
    ):
        assert result.database[collection] == []
    assert result.database["schema_version"] == 1


def test_owner_migration_preserves_mixed_historical_talk_versions(
    tracking_database,
):
    database = _legacy_database()
    database["talks"] = []
    for version in (1, 4, 5):
        talk = _legacy_talk(filename=f"v{version}.md")
        talk["schema_version"] = version
        database["talks"].append(talk)
    database["talks"].append(_legacy_talk(filename="implicit-v1.md"))

    migrated = tracking_database.migrate_tracking_database(database).database

    assert [talk["schema_version"] for talk in migrated["talks"]] == [1, 4, 5, 1]


@pytest.mark.parametrize(
    "active_talk",
    [
        {
            **_legacy_talk(),
            "status": "reprocessing-inflight",
            "reprocess_generation": 1,
            "_queue_claim": _claim_for_version(
                1,
                generation=1,
                state="claimed",
                batch_id="active",
            ),
        },
        {
            **_legacy_talk(),
            "status": "needs-reprocessing",
            "reprocess_generation": 1,
            "_queue_claim": _claim_for_version(
                1,
                generation=1,
                state="claimed",
                batch_id="drifted",
            ),
        },
    ],
)
def test_owner_migration_rejects_active_writers(tracking_database, active_talk):
    database = _legacy_database()
    database["talks"] = [active_talk]

    with pytest.raises(
        tracking_database.TrackingDatabaseError,
        match="active queue writers",
    ):
        tracking_database.migrate_tracking_database(database)


def test_current_migration_is_idempotent_with_stable_counts(tracking_database):
    current = tracking_database.migrate_tracking_database(_legacy_database()).database

    second = tracking_database.migrate_tracking_database(current)

    assert second.changed is False
    assert second.database == current
    assert second.database is not current
    assert second.record_counts == {
        "config": 0,
        "talks": 0,
        "pptx_catalog": 0,
        "qr_codes": 0,
        "resources": 0,
        "thumbnails": 0,
        "confirmed_intents": 0,
        "improvement_goals": 0,
        "source_rejections": 0,
    }


def test_current_root_config_v1_migrates_only_config(tracking_database):
    current = tracking_database.migrate_tracking_database(_legacy_database()).database
    current["config"] = {
        "schema_version": 1,
        "python_path": "/opt/python",
    }
    untouched = {
        key: copy.deepcopy(value)
        for key, value in current.items()
        if key != "config"
    }

    assessment = tracking_database.assess_tracking_database(current)
    migration = tracking_database.migrate_tracking_database(current)

    assert assessment.usable is True
    assert assessment.state == "legacy"
    assert migration.changed is True
    assert migration.from_schema_version == 1
    assert migration.to_schema_version == 1
    assert migration.record_counts["config"] == 1
    assert migration.database["config"] == {
        "schema_version": 2,
        "python_path": "/opt/python",
        "pptx_directory_exclusions": DEFAULT_DIRECTORY_EXCLUSIONS,
    }
    assert {
        key: value
        for key, value in migration.database.items()
        if key != "config"
    } == untouched

    second = tracking_database.migrate_tracking_database(migration.database)
    assert second.changed is False
    assert second.from_schema_version == 1
    assert second.to_schema_version == 1
    assert second.database == migration.database
    assert all(count == 0 for count in second.record_counts.values())


def test_config_v1_migration_preserves_valid_custom_exclusions(tracking_database):
    current = tracking_database.migrate_tracking_database(_legacy_database()).database
    current["config"] = {
        "schema_version": 1,
        "pptx_directory_exclusions": ["generated", "VendorCache"],
    }

    migration = tracking_database.migrate_tracking_database(current)

    assert migration.database["config"] == {
        "schema_version": 2,
        "pptx_directory_exclusions": ["generated", "VendorCache"],
    }


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        (
            {"schema_version": 2},
            "config schema v2 requires pptx_directory_exclusions",
        ),
        (
            {
                "schema_version": 2,
                "pptx_directory_exclusions": ["venv", "VENV"],
            },
            "case-insensitive duplicate",
        ),
    ],
)
def test_current_config_v2_rejects_missing_or_malformed_exclusions(
    tracking_database,
    config,
    expected,
):
    current = tracking_database.migrate_tracking_database(_legacy_database()).database
    current["config"] = config

    with pytest.raises(tracking_database.TrackingDatabaseError, match=expected):
        tracking_database.assess_tracking_database(current)


def test_future_config_generation_fails_closed_without_poisoning_root_version(
    tracking_database,
):
    current = tracking_database.migrate_tracking_database(_legacy_database()).database
    current["config"]["schema_version"] = 3

    assessment = tracking_database.assess_tracking_database(current)

    assert assessment.usable is False
    assert assessment.schema_version == 1
    assert assessment.reason_codes == ("config_schema_version_unsupported",)
    with pytest.raises(
        tracking_database.TrackingDatabaseError,
        match="config_schema_version_unsupported",
    ):
        tracking_database.migrate_tracking_database(current)


@pytest.mark.parametrize(
    "collection",
    [
        "talks",
        "pptx_catalog",
        "qr_codes",
        "resources",
        "thumbnails",
        "confirmed_intents",
        "improvement_goals",
    ],
)
def test_current_root_requires_every_owned_collection(
    tracking_database,
    collection,
):
    current = tracking_database.migrate_tracking_database(_legacy_database()).database
    current.pop(collection)

    with pytest.raises(
        tracking_database.TrackingDatabaseError,
        match=f"requires a '{collection}' array",
    ):
        tracking_database.assess_tracking_database(current)


def test_current_root_requires_explicit_child_versions(tracking_database):
    current = tracking_database.migrate_tracking_database(_legacy_database()).database
    current["talks"][0].pop("schema_version")
    current["talks"][0]["source_rejections"][0].pop("schema_version")
    current["qr_codes"][0].pop("schema_version")

    assessment = tracking_database.assess_tracking_database(current)

    assert assessment.usable is False
    assert assessment.reason_codes == (
        "qr_codes_schema_version_missing",
        "talks_schema_version_missing",
    )
    with pytest.raises(
        tracking_database.TrackingDatabaseError,
        match="migration will refuse",
    ):
        tracking_database.require_current_tracking_database(current)


def test_require_current_routes_legacy_state_to_owner_migration(tracking_database):
    with pytest.raises(
        tracking_database.TrackingDatabaseError,
        match="migrate-tracking-database.py",
    ):
        tracking_database.require_current_tracking_database(_legacy_database())


def _write_database(path, database: dict) -> bytes:
    raw = (json.dumps(database, indent=2) + "\n").encode()
    path.write_bytes(raw)
    os.chmod(path, 0o600)
    return raw


def test_migration_dry_run_is_side_effect_free(
    migrate_tracking_database,
    tmp_path,
):
    path = tmp_path / "tracking-database.json"
    raw = _write_database(path, _legacy_database())

    report = migrate_tracking_database.execute(
        path,
        apply=False,
        expected_sha256=None,
    )

    assert path.read_bytes() == raw
    assert report["mode"] == "dry-run"
    assert report["changed"] is True
    assert report["database_written"] is False
    assert report["input_sha256"] == hashlib.sha256(raw).hexdigest()
    assert not (tmp_path / ".backups").exists()


@pytest.mark.parametrize("apply", [False, True])
def test_explicit_root_zero_cli_refuses_before_write_or_backup(
    migrate_tracking_database,
    tmp_path,
    apply,
):
    path = tmp_path / "tracking-database.json"
    raw = _write_database(path, _legacy_database() | {"schema_version": 0})

    with pytest.raises(
        migrate_tracking_database.TrackingDatabaseMigrationError,
        match="tracking_database_schema_version_unsupported",
    ):
        migrate_tracking_database.execute(
            path,
            apply=apply,
            expected_sha256=(hashlib.sha256(raw).hexdigest() if apply else None),
        )

    assert path.read_bytes() == raw
    assert not (tmp_path / ".backups").exists()


def test_apply_writes_exact_backup_through_shared_transaction(
    migrate_tracking_database,
    tracking_database,
    tmp_path,
):
    path = tmp_path / "tracking-database.json"
    raw = _write_database(path, _legacy_database())
    digest = hashlib.sha256(raw).hexdigest()

    report = migrate_tracking_database.execute(
        path,
        apply=True,
        expected_sha256=digest,
    )

    backup = (
        tmp_path
        / ".backups"
        / f"{path.name}.owner-migration-{digest}.bak"
    )
    assert backup.read_bytes() == raw
    assert report["backup"] == str(backup)
    assert report["database_written"] is True
    assert report["durability_state"] == "durable"
    assert report["warnings"] == []
    current = json.loads(path.read_text())
    assert tracking_database.assess_tracking_database(current).state == "current"
    assert (path.stat().st_mode & 0o777) == 0o600


def test_config_only_migration_uses_generation_neutral_backup_name(
    migrate_tracking_database,
    tracking_database,
    tmp_path,
):
    path = tmp_path / "tracking-database.json"
    current = tracking_database.migrate_tracking_database(_legacy_database()).database
    current["config"] = {"schema_version": 1, "python_path": "/opt/python"}
    raw = _write_database(path, current)
    digest = hashlib.sha256(raw).hexdigest()

    report = migrate_tracking_database.execute(
        path,
        apply=True,
        expected_sha256=digest,
    )

    backup = (
        tmp_path
        / ".backups"
        / f"{path.name}.owner-migration-{digest}.bak"
    )
    assert backup.read_bytes() == raw
    assert report["backup"] == str(backup)
    assert report["from_schema_version"] == 1
    assert report["to_schema_version"] == 1
    assert report["record_counts"]["config"] == 1


def test_config_only_migration_tolerates_cloud_stage_churn_and_is_idempotent(
    migrate_tracking_database,
    tracking_database,
    tracking_database_io,
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "tracking-database.json"
    current = tracking_database.migrate_tracking_database(_legacy_database()).database
    current["config"] = {"schema_version": 1, "python_path": "/opt/python"}
    raw = _write_database(path, current)
    digest = hashlib.sha256(raw).hexdigest()
    dry_run = migrate_tracking_database.execute(
        path,
        apply=False,
        expected_sha256=None,
    )
    original_stage = tracking_database_io._stage_candidate
    stage_calls = 0

    def stage_then_change_timestamps(target, candidate, mode):
        nonlocal stage_calls
        stage_calls += 1
        stage = original_stage(target, candidate, mode)
        metadata = os.fstat(stage.descriptor)
        os.utime(
            stage.path,
            ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1_000_000),
            follow_symlinks=False,
        )
        return stage

    monkeypatch.setattr(
        tracking_database_io,
        "_stage_candidate",
        stage_then_change_timestamps,
    )

    applied = migrate_tracking_database.execute(
        path,
        apply=True,
        expected_sha256=digest,
    )
    installed = path.read_bytes()
    installed_inode = path.stat().st_ino
    backup = tmp_path / ".backups" / f"{path.name}.owner-migration-{digest}.bak"

    assert applied["database_written"] is True
    assert applied["durability_state"] == "durable"
    assert applied["warnings"] == []
    assert applied["output_sha256"] == dry_run["output_sha256"]
    assert hashlib.sha256(installed).hexdigest() == dry_run["output_sha256"]
    assert backup.read_bytes() == raw
    assert applied["backup"] == str(backup)
    assert json.loads(installed)["config"] == {
        "schema_version": 2,
        "python_path": "/opt/python",
        "pptx_directory_exclusions": DEFAULT_DIRECTORY_EXCLUSIONS,
    }

    replay = migrate_tracking_database.execute(
        path,
        apply=True,
        expected_sha256=applied["output_sha256"],
    )

    assert replay["changed"] is False
    assert replay["database_written"] is False
    assert replay["backup"] is None
    assert replay["output_sha256"] == applied["output_sha256"]
    assert path.read_bytes() == installed
    assert path.stat().st_ino == installed_inode
    assert stage_calls == 1
    assert not list(tmp_path.glob(".*.tracking-db.tmp"))


def test_apply_current_database_is_exact_noop_without_backup(
    migrate_tracking_database,
    tracking_database,
    tmp_path,
):
    path = tmp_path / "tracking-database.json"
    current = tracking_database.migrate_tracking_database(_legacy_database()).database
    raw = _write_database(path, current)
    inode = path.stat().st_ino

    report = migrate_tracking_database.execute(
        path,
        apply=True,
        expected_sha256=hashlib.sha256(raw).hexdigest(),
    )

    assert report["changed"] is False
    assert report["database_written"] is False
    assert report["backup"] is None
    assert path.read_bytes() == raw
    assert path.stat().st_ino == inode


def test_apply_requires_matching_dry_run_hash(
    migrate_tracking_database,
    tmp_path,
):
    path = tmp_path / "tracking-database.json"
    _write_database(path, _legacy_database())

    with pytest.raises(
        migrate_tracking_database.TrackingDatabaseMigrationError,
        match="--expected-sha256",
    ):
        migrate_tracking_database.execute(path, apply=True, expected_sha256=None)
    with pytest.raises(
        migrate_tracking_database.TrackingDatabaseMigrationError,
        match="sha256 precondition failed",
    ):
        migrate_tracking_database.execute(
            path,
            apply=True,
            expected_sha256="0" * 64,
        )


def test_shared_cas_rejects_change_before_commit(
    migrate_tracking_database,
    monkeypatch,
    tmp_path,
):
    path = tmp_path / "tracking-database.json"
    raw = _write_database(path, _legacy_database())
    digest = hashlib.sha256(raw).hexdigest()
    concurrent = b'{"concurrent":true}\n'
    original_commit = migrate_tracking_database.commit_tracking_database

    def racing_commit(expected, candidate, *, backup=None):
        path.write_bytes(concurrent)
        return original_commit(expected, candidate, backup=backup)

    monkeypatch.setattr(
        migrate_tracking_database,
        "commit_tracking_database",
        racing_commit,
    )

    with pytest.raises(migrate_tracking_database.TrackingDatabaseMigrationError):
        migrate_tracking_database.execute(
            path,
            apply=True,
            expected_sha256=digest,
        )

    assert path.read_bytes() == concurrent
    assert not (tmp_path / ".backups").exists()


@pytest.mark.parametrize("apply", [False, True])
def test_malformed_or_active_state_blocks_before_backup(
    migrate_tracking_database,
    tmp_path,
    apply,
):
    path = tmp_path / "tracking-database.json"
    database = _legacy_database()
    database["talks"][0].update(
        {
            "status": "reprocessing-inflight",
            "reprocess_generation": 1,
            "_queue_claim": _claim_for_version(
                1,
                generation=1,
                state="claimed",
                batch_id="blocking",
            ),
        }
    )
    raw = _write_database(path, database)

    with pytest.raises(
        migrate_tracking_database.TrackingDatabaseMigrationError,
        match="active queue writers",
    ):
        migrate_tracking_database.execute(
            path,
            apply=apply,
            expected_sha256=(hashlib.sha256(raw).hexdigest() if apply else None),
        )

    assert path.read_bytes() == raw
    assert not (tmp_path / ".backups").exists()


def test_legacy_queue_recovery_unblocks_migration_without_schema_stamping(
    migrate_tracking_database,
    queue_state,
    tmp_path,
    capsys,
):
    path = tmp_path / "tracking-database.json"
    database = _legacy_database()
    database["talks"] = [
        {
            **_legacy_talk(),
            "status": "reprocessing-inflight",
            "reprocess_generation": 1,
            "_queue_claim": {
                "schema_version": 1,
                "run_id": "legacy-run",
                "batch_id": "1",
                "claimed_at": "2026-07-31T12:00:00+00:00",
                "previous_status": "needs-reprocessing",
                "reprocess_generation": 1,
                "state": "claimed",
            },
        }
    ]
    raw = _write_database(path, database)

    with pytest.raises(
        migrate_tracking_database.TrackingDatabaseMigrationError,
        match="active queue writers",
    ):
        migrate_tracking_database.execute(
            path,
            apply=False,
            expected_sha256=None,
        )
    assert path.read_bytes() == raw
    assert not (tmp_path / ".backups").exists()

    assert queue_state.main(
        [str(path), "inspect", "--run-id", "legacy-run"]
    ) == 0
    capsys.readouterr()
    assert path.read_bytes() == raw

    assert queue_state.main(
        [
            str(path),
            "recover",
            "--now",
            "2026-08-01T12:00:00+00:00",
            "--stale-after-seconds",
            "1",
            "--run-id",
            "legacy-run",
        ]
    ) == 0
    capsys.readouterr()
    recovered = json.loads(path.read_text())
    assert "schema_version" not in recovered
    assert "schema_version" not in recovered["talks"][0]
    assert recovered["talks"][0]["status"] == "needs-reprocessing"
    claim = recovered["talks"][0]["_queue_claim"]
    assert claim["schema_version"] == 2
    assert claim["state"] == "stale_recovered"
    assert claim["release_reason"] == "lease_expired"

    report = migrate_tracking_database.execute(
        path,
        apply=False,
        expected_sha256=None,
    )
    assert report["changed"] is True
    assert report["from_schema_version"] == 0
    assert report["to_schema_version"] == 1


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (
            b'{"config":{"python_path":"a","python_path":"b"},"talks":[]}\n',
            "duplicate object key 'python_path'",
        ),
        (b'{"config":{"value":NaN},"talks":[]}\n', "JSON number NaN"),
    ],
)
def test_strict_json_failure_has_no_write_or_backup(
    migrate_tracking_database,
    tmp_path,
    raw,
    message,
):
    path = tmp_path / "tracking-database.json"
    path.write_bytes(raw)

    with pytest.raises(
        migrate_tracking_database.TrackingDatabaseMigrationError,
        match=message,
    ):
        migrate_tracking_database.execute(
            path,
            apply=True,
            expected_sha256=hashlib.sha256(raw).hexdigest(),
        )

    assert path.read_bytes() == raw
    assert not (tmp_path / ".backups").exists()


@pytest.mark.parametrize("apply", [False, True])
def test_non_roundtrippable_number_blocks_migration_before_backup(
    migrate_tracking_database,
    tmp_path,
    apply,
):
    path = tmp_path / "tracking-database.json"
    database = _legacy_database()
    database["config"]["precision_marker"] = "NUMBER_TOKEN"
    raw = (json.dumps(database, indent=2) + "\n").encode().replace(
        b'"NUMBER_TOKEN"',
        b"0.12345678901234567890123456789",
    )
    path.write_bytes(raw)

    with pytest.raises(
        migrate_tracking_database.TrackingDatabaseMigrationError,
        match="cannot round-trip losslessly",
    ):
        migrate_tracking_database.execute(
            path,
            apply=apply,
            expected_sha256=(hashlib.sha256(raw).hexdigest() if apply else None),
        )

    assert path.read_bytes() == raw
    assert not (tmp_path / ".backups").exists()


@pytest.mark.parametrize(
    "number_token",
    [
        pytest.param("1e" + "9" * 30, id="extreme-exponent"),
        pytest.param("7" * 5000, id="huge-integer"),
    ],
)
def test_cli_reports_extreme_number_as_json_without_write_or_backup(
    migrate_tracking_database,
    tmp_path,
    capsys,
    number_token,
):
    path = tmp_path / "tracking-database.json"
    database = _legacy_database()
    database["config"]["precision_marker"] = "NUMBER_TOKEN"
    raw = (json.dumps(database, indent=2) + "\n").encode().replace(
        b'"NUMBER_TOKEN"',
        number_token.encode(),
    )
    path.write_bytes(raw)

    result = migrate_tracking_database.main(
        [
            str(path),
            "--apply",
            "--expected-sha256",
            hashlib.sha256(raw).hexdigest(),
        ]
    )
    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert result == 2
    assert report["ok"] is False
    assert "cannot round-trip losslessly" in report["error"]
    assert len(report["error"]) < 1000
    assert "Traceback" not in captured.err
    assert path.read_bytes() == raw
    assert not (tmp_path / ".backups").exists()


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        pytest.param(
            b'{"config":{"value":' + b"[" * 500 + b"0" + b"]" * 500
            + b'},"talks":[]}\n',
            "maximum supported JSON nesting depth 200",
            id="decoded-depth-limit",
        ),
        pytest.param(
            b'{"config":{"value":' + b"[" * 10_000 + b"0" + b"]" * 10_000
            + b'},"talks":[]}\n',
            "maximum supported JSON nesting depth 200",
            id="decoder-recursion-limit",
        ),
        pytest.param(
            b'{"config":{"value":"\\ud800"},"talks":[]}\n',
            "unpaired UTF-16 surrogate",
            id="unpaired-surrogate",
        ),
    ],
)
def test_cli_reports_unsafe_json_tree_without_write_or_backup(
    migrate_tracking_database,
    tmp_path,
    capsys,
    raw,
    message,
):
    path = tmp_path / "tracking-database.json"
    path.write_bytes(raw)

    result = migrate_tracking_database.main(
        [
            str(path),
            "--apply",
            "--expected-sha256",
            hashlib.sha256(raw).hexdigest(),
        ]
    )
    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert result == 2
    assert report["ok"] is False
    assert message in report["error"]
    assert len(report["error"]) < 1000
    assert "Traceback" not in captured.err
    assert path.read_bytes() == raw
    assert not (tmp_path / ".backups").exists()


def test_cli_errors_follow_json_contract(
    migrate_tracking_database,
    tmp_path,
    capsys,
):
    path = tmp_path / "tracking-database.json"
    raw = b'{"config":{},"talks":[],"talks":[{"filename":"hidden.md"}]}\n'
    path.write_bytes(raw)

    result = migrate_tracking_database.main(
        [
            str(path),
            "--apply",
            "--expected-sha256",
            hashlib.sha256(raw).hexdigest(),
        ]
    )
    captured = capsys.readouterr()

    assert result == 2
    assert json.loads(captured.out)["ok"] is False
    assert "duplicate object key 'talks'" in captured.err
    assert path.read_bytes() == raw
    assert not (tmp_path / ".backups").exists()

    result = migrate_tracking_database.main([])
    captured = capsys.readouterr()
    assert result == 2
    assert json.loads(captured.out)["ok"] is False
    assert "invalid arguments" in captured.err
