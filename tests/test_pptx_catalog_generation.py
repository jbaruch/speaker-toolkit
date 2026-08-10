"""PPTX catalog visual-evidence generation binding (#229).

Schema v1 persisted a bare ``visual_extracted`` boolean and nothing about which
extractor produced it, so a stored ``true`` could refer to v0, v1, v2, v3, or
current v4 evidence. Selection was therefore undecidable from owner state:
trusting it silently skips stale evidence, distrusting it re-extracts forever
because the catalog still cannot remember that regeneration produced current
output.

Schema v2 binds each receipt to the extractor schema, the pipeline version, the
exact source bytes, and the artifact it produced.
``classify_pptx_visual_evidence`` is the one authority every consumer shares, so
owner writes, migration, preflight, queue selection, and profile reads cannot
disagree about which decks need regeneration.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest


CURRENT_EXTRACTOR_SCHEMA = 4
CURRENT_PIPELINE = "1.5.0"

SOURCE_FINGERPRINT = {
    "algorithm": "sha256",
    "digest": "a" * 64,
    "size_bytes": 4096,
}
ARTIFACT_DIGEST = "c" * 64
OTHER_ARTIFACT_DIGEST = "d" * 64
OTHER_FINGERPRINT = {
    "algorithm": "sha256",
    "digest": "b" * 64,
    "size_bytes": 8192,
}


def _legacy_record(*, visual_extracted: bool = True) -> dict:
    """A schema-v1 catalog record: a visual claim with no generation binding."""
    return {
        "schema_version": 1,
        "pptx_path": "Conference/2024/Talk.pptx",
        "talk_filename": "2024-04-10-talk.md",
        "matched": True,
        "slide_count": 42,
        "visual_extracted": visual_extracted,
    }


def _evidence(**overrides) -> dict:
    evidence = {
        "outcome": "succeeded",
        "extractor_schema_version": CURRENT_EXTRACTOR_SCHEMA,
        "pipeline_version": CURRENT_PIPELINE,
        "source_fingerprint": copy.deepcopy(SOURCE_FINGERPRINT),
        "artifact": {"path": "evidence/talk.json", "sha256": ARTIFACT_DIGEST},
    }
    evidence.update(overrides)
    return evidence


def _current_record(**overrides) -> dict:
    record = {
        "schema_version": 2,
        "pptx_path": "Conference/2024/Talk.pptx",
        "talk_filename": "2024-04-10-talk.md",
        "matched": True,
        "slide_count": 42,
        "visual_extracted": True,
        "visual_evidence": _evidence(),
    }
    record.update(overrides)
    return record


_MATCHING_LIVE_BYTES = object()


def _classify(
    tracking_database,
    record,
    *,
    observed: Any = _MATCHING_LIVE_BYTES,
    artifact_digest: Any = _MATCHING_LIVE_BYTES,
) -> str:
    """Classify one record; both observations default to matching live state.

    The production signature has no defaults — a caller must say what it saw on
    disk — so tests that care about an observation pass it explicitly and the
    rest get the deck and artifact they described.
    """
    if observed is _MATCHING_LIVE_BYTES:
        observed = copy.deepcopy(SOURCE_FINGERPRINT)
    if artifact_digest is _MATCHING_LIVE_BYTES:
        artifact_digest = ARTIFACT_DIGEST
    return tracking_database.classify_pptx_visual_evidence(
        record,
        extractor_schema_version=CURRENT_EXTRACTOR_SCHEMA,
        pipeline_version=CURRENT_PIPELINE,
        observed_source_fingerprint=observed,
        observed_artifact_digest=artifact_digest,
    )


def test_extractor_constants_match_the_installed_extractor(pptx_evidence) -> None:
    """These tests are only meaningful while they describe the real extractor."""
    assert pptx_evidence.PPTX_EXTRACTION_SCHEMA_VERSION == CURRENT_EXTRACTOR_SCHEMA
    assert pptx_evidence.PPTX_EXTRACTION_PIPELINE_VERSION == CURRENT_PIPELINE


# Acceptance 1: a legacy bare claim is selected for regeneration.


def test_legacy_visual_extracted_is_unknown_generation_not_current(
    tracking_database,
) -> None:
    classification = _classify(tracking_database, _legacy_record())

    assert classification == tracking_database.PPTX_EVIDENCE_UNKNOWN_LEGACY
    assert tracking_database.pptx_visual_evidence_needs_extraction(classification)


def test_legacy_record_without_a_claim_is_pending(tracking_database) -> None:
    classification = _classify(
        tracking_database, _legacy_record(visual_extracted=False)
    )

    assert classification == tracking_database.PPTX_EVIDENCE_PENDING
    assert tracking_database.pptx_visual_evidence_needs_extraction(classification)


def test_unversioned_record_is_read_as_legacy(tracking_database) -> None:
    record = _legacy_record()
    del record["schema_version"]

    assert (
        _classify(tracking_database, record)
        == tracking_database.PPTX_EVIDENCE_UNKNOWN_LEGACY
    )


# Acceptance 2: a receipt for the exact same generation is skipped.


def test_current_receipt_for_the_same_generation_is_skipped(tracking_database) -> None:
    classification = _classify(
        tracking_database,
        _current_record(),
        observed=copy.deepcopy(SOURCE_FINGERPRINT),
    )

    assert classification == tracking_database.PPTX_EVIDENCE_CURRENT
    assert not tracking_database.pptx_visual_evidence_needs_extraction(classification)


def test_an_unfingerprintable_deck_is_never_current(tracking_database) -> None:
    """A stored receipt is a hint; without the live bytes it proves nothing."""
    classification = _classify(tracking_database, _current_record(), observed=None)

    assert classification == tracking_database.PPTX_EVIDENCE_UNVERIFIED
    assert tracking_database.pptx_visual_evidence_needs_extraction(classification)


def test_a_missing_extraction_artifact_is_never_current(tracking_database) -> None:
    """A deleted artifact must not stay authoritative."""
    classification = _classify(
        tracking_database, _current_record(), artifact_digest=None
    )

    assert classification == tracking_database.PPTX_EVIDENCE_UNVERIFIED
    assert tracking_database.pptx_visual_evidence_needs_extraction(classification)


def test_a_replaced_extraction_artifact_is_stale(tracking_database) -> None:
    classification = _classify(
        tracking_database, _current_record(), artifact_digest=OTHER_ARTIFACT_DIGEST
    )

    assert classification == tracking_database.PPTX_EVIDENCE_STALE


@pytest.mark.parametrize(
    "omitted",
    ["observed_source_fingerprint", "observed_artifact_digest"],
)
def test_the_live_observations_have_no_defaults(tracking_database, omitted) -> None:
    """A caller cannot skip saying what it observed on disk."""
    arguments = {
        "extractor_schema_version": CURRENT_EXTRACTOR_SCHEMA,
        "pipeline_version": CURRENT_PIPELINE,
        "observed_source_fingerprint": copy.deepcopy(SOURCE_FINGERPRINT),
        "observed_artifact_digest": ARTIFACT_DIGEST,
    }
    del arguments[omitted]

    with pytest.raises(TypeError, match=omitted):
        tracking_database.classify_pptx_visual_evidence(_current_record(), **arguments)


# Acceptance 3: a changed source generation makes the record stale again.


def test_changed_source_bytes_make_the_receipt_stale(tracking_database) -> None:
    classification = _classify(
        tracking_database,
        _current_record(),
        observed=copy.deepcopy(OTHER_FINGERPRINT),
    )

    assert classification == tracking_database.PPTX_EVIDENCE_STALE
    assert tracking_database.pptx_visual_evidence_needs_extraction(classification)


@pytest.mark.parametrize(
    "overrides",
    [
        {"extractor_schema_version": 3},
        {"pipeline_version": "1.4.0"},
    ],
)
def test_older_extractor_generations_are_stale(tracking_database, overrides) -> None:
    record = _current_record(visual_evidence=_evidence(**overrides))

    assert _classify(tracking_database, record) == tracking_database.PPTX_EVIDENCE_STALE


def test_size_only_fingerprint_drift_is_stale(tracking_database) -> None:
    """Every fingerprint field is compared, not the digest alone."""
    observed = copy.deepcopy(SOURCE_FINGERPRINT) | {"size_bytes": 4097}

    assert (
        _classify(tracking_database, _current_record(), observed=observed)
        == tracking_database.PPTX_EVIDENCE_STALE
    )


def test_never_attempted_extraction_is_pending(tracking_database) -> None:
    record = _current_record(visual_extracted=False, visual_evidence=None)

    assert (
        _classify(tracking_database, record) == tracking_database.PPTX_EVIDENCE_PENDING
    )


def test_recorded_failure_is_distinct_from_pending(tracking_database) -> None:
    record = _current_record(
        visual_extracted=False,
        visual_evidence=_evidence(outcome="failed", artifact=None),
    )

    classification = _classify(tracking_database, record)
    assert classification == tracking_database.PPTX_EVIDENCE_FAILED
    assert tracking_database.pptx_visual_evidence_needs_extraction(classification)


def test_unknown_classification_is_rejected_rather_than_treated_as_current(
    tracking_database,
) -> None:
    with pytest.raises(tracking_database.TrackingDatabaseError):
        tracking_database.pptx_visual_evidence_needs_extraction("probably_fine")


def test_a_future_record_says_the_reader_is_lagging(tracking_database) -> None:
    """stateful-artifacts: newer than accepted is no usable prior state."""
    record = _current_record(schema_version=3)

    with pytest.raises(
        tracking_database.TrackingDatabaseError, match="newer than this reader accepts"
    ):
        _classify(tracking_database, record)


@pytest.mark.parametrize(
    ("evidence", "match"),
    [
        ({"artifact": None}, "artifact is required"),
        (
            {"source_fingerprint": {"algorithm": "sha256", "digest": "nope"}},
            "missing|64 lowercase hex",
        ),
        ({"extractor_schema_version": "4"}, "must be an integer"),
    ],
)
def test_a_malformed_receipt_never_classifies_as_current(
    tracking_database, evidence, match
) -> None:
    """A receipt is the licence to skip extraction — validate before trusting it."""
    record = _current_record(visual_evidence=_evidence(**evidence))

    with pytest.raises(tracking_database.TrackingDatabaseError, match=match):
        _classify(tracking_database, record)


def test_a_mirror_flag_disagreeing_with_the_receipt_is_rejected(
    tracking_database,
) -> None:
    record = _current_record(visual_extracted=False)

    with pytest.raises(tracking_database.TrackingDatabaseError, match="must mirror"):
        _classify(tracking_database, record)


def test_a_non_integer_record_version_is_rejected(tracking_database) -> None:
    record = _current_record(schema_version="2")

    with pytest.raises(
        tracking_database.TrackingDatabaseError, match="non-negative integer"
    ):
        _classify(tracking_database, record)


# Acceptance 4: reader, writer, and migration agree on the same classification.


def _database(records: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "config": {"schema_version": 2, "pptx_directory_exclusions": []},
        "talks": [],
        "pptx_catalog": records,
        "qr_codes": [],
        "resources": [],
        "thumbnails": [],
        "confirmed_intents": [],
        "improvement_goals": [],
    }


def test_both_catalog_versions_read_as_current_database_shape(
    tracking_database,
) -> None:
    database = _database(
        [
            _legacy_record(),
            _current_record(pptx_path="Conference/2025/Second.pptx"),
        ]
    )

    assessment = tracking_database.assess_tracking_database(database)

    assert assessment.usable is True
    assert assessment.state == "current"


def test_migration_preserves_a_legacy_record_without_inventing_a_binding(
    tracking_database,
) -> None:
    unversioned = _legacy_record()
    del unversioned["schema_version"]
    database = _database([unversioned])
    # Implicit legacy: the root version key is absent, not an explicit zero.
    del database["schema_version"]
    del database["config"]["schema_version"]

    migration = tracking_database.migrate_tracking_database(database)

    migrated = migration.database["pptx_catalog"][0]
    assert migrated["schema_version"] == 1
    assert "visual_evidence" not in migrated
    assert (
        _classify(tracking_database, migrated)
        == tracking_database.PPTX_EVIDENCE_UNKNOWN_LEGACY
    )


def test_owner_writer_refuses_a_record_without_the_generation_binding(
    mutate_tracking_database,
) -> None:
    """A new write must never reintroduce an unattributable visual claim."""
    mutation = {
        "kind": "record_pptx",
        "expect": {"$missing": True},
        "record": _legacy_record() | {"talk_filename": None, "matched": False},
    }

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match=r"missing \['visual_evidence'\]",
    ):
        mutate_tracking_database.build_candidate(_database([]), [mutation])


def test_owner_writer_refuses_a_v2_shape_declared_as_v1(
    mutate_tracking_database,
) -> None:
    """The version is validated per kind: pptx_catalog left v1 behind."""
    mutation = {
        "kind": "record_pptx",
        "expect": {"$missing": True},
        "record": _current_record()
        | {"talk_filename": None, "matched": False, "schema_version": 1},
    }

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="schema_version must be exact integer 2",
    ):
        mutate_tracking_database.build_candidate(_database([]), [mutation])


def test_owner_writer_accepts_a_bound_receipt_the_reader_calls_current(
    mutate_tracking_database, tracking_database
) -> None:
    record = _current_record() | {"talk_filename": None, "matched": False}
    mutation = {
        "kind": "record_pptx",
        "expect": {"$missing": True},
        "record": copy.deepcopy(record),
    }

    candidate, _changes = mutate_tracking_database.build_candidate(
        _database([]), [mutation]
    )

    stored = candidate["pptx_catalog"][0]
    assert stored == record
    assert (
        _classify(tracking_database, stored, observed=copy.deepcopy(SOURCE_FINGERPRINT))
        == tracking_database.PPTX_EVIDENCE_CURRENT
    )


# v2 shape invariants.


def test_visual_extracted_must_mirror_the_receipt_outcome(tracking_database) -> None:
    record = _current_record(visual_extracted=False)

    with pytest.raises(tracking_database.TrackingDatabaseError, match="must mirror"):
        tracking_database.require_current_tracking_database(_database([record]))


def test_a_succeeded_receipt_must_name_its_artifact(tracking_database) -> None:
    record = _current_record(visual_evidence=_evidence(artifact=None))

    with pytest.raises(
        tracking_database.TrackingDatabaseError, match="artifact is required"
    ):
        tracking_database.require_current_tracking_database(_database([record]))


def test_a_failed_receipt_must_not_name_an_artifact(tracking_database) -> None:
    record = _current_record(
        visual_extracted=False, visual_evidence=_evidence(outcome="failed")
    )

    with pytest.raises(
        tracking_database.TrackingDatabaseError, match="artifact must be null"
    ):
        tracking_database.require_current_tracking_database(_database([record]))


@pytest.mark.parametrize(
    ("fingerprint", "match"),
    [
        ({"algorithm": "md5", "digest": "a" * 64, "size_bytes": 1}, "algorithm"),
        ({"algorithm": "sha256", "digest": "nope", "size_bytes": 1}, "digest"),
        ({"algorithm": "sha256", "digest": "a" * 64, "size_bytes": 0}, "size_bytes"),
    ],
)
def test_source_fingerprint_shape_is_enforced(
    tracking_database, fingerprint, match
) -> None:
    record = _current_record(visual_evidence=_evidence(source_fingerprint=fingerprint))

    with pytest.raises(tracking_database.TrackingDatabaseError, match=match):
        tracking_database.require_current_tracking_database(_database([record]))


def test_v1_records_may_not_carry_a_binding_field(tracking_database) -> None:
    """A v1 record with visual_evidence is drift, not a half-migrated record."""
    record = _legacy_record() | {"visual_evidence": _evidence()}

    with pytest.raises(tracking_database.TrackingDatabaseError, match="unknown fields"):
        tracking_database.require_current_tracking_database(_database([record]))
