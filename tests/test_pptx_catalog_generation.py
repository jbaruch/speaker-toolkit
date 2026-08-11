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
import hashlib
import json
import pathlib
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


def _identity_assessment(**overrides) -> dict:
    """A v3 record's proof that this deck belongs to the talk it names (#176)."""
    assessment = {
        "schema_version": 1,
        "pptx_path": "Conference/2024/Talk.pptx",
        "verdict": "matched",
        "artifact_role": "delivery",
        "selected_talk_filename": "2024-04-10-talk.md",
        "reason_codes": ["identity_matched"],
    }
    assessment.update(overrides)
    return assessment


def _evidence_bound_record(**overrides) -> dict:
    """A schema-v2 record: evidence bound to a generation, talk binding assumed."""
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


def _current_record(**overrides) -> dict:
    record = _evidence_bound_record()
    record["schema_version"] = 3
    record["identity_assessment"] = _identity_assessment()
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
    record = _current_record(schema_version=4)

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
        match=r"missing \['identity_assessment', 'visual_evidence'\]",
    ):
        mutate_tracking_database.build_candidate(_database([]), [mutation])


def test_owner_writer_refuses_a_current_shape_declared_as_v1(
    mutate_tracking_database,
) -> None:
    """The version is validated per kind: pptx_catalog left v1 behind."""
    mutation = {
        "kind": "record_pptx",
        "expect": {"$missing": True},
        "record": _current_record()
        | {
            "talk_filename": None,
            "matched": False,
            "identity_assessment": None,
            "schema_version": 1,
        },
    }

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="schema_version must be exact integer 3",
    ):
        mutate_tracking_database.build_candidate(_database([]), [mutation])


def test_owner_writer_accepts_a_bound_receipt_the_reader_calls_current(
    mutate_tracking_database, tracking_database
) -> None:
    record = _current_record() | {
        "talk_filename": None,
        "matched": False,
        "identity_assessment": None,
    }
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


def _write(mutate_tracking_database, record: dict):
    """Persist one catalog record through the owner writer."""
    mutation = {
        "kind": "record_pptx",
        "expect": {"$missing": True},
        "record": record | {"talk_filename": None, "matched": False},
    }
    return mutate_tracking_database.build_candidate(_database([]), [mutation])


# The receipt's shape is fatal at the writer, never at the database
# assessment: a malformed receipt is per-record evidence trouble, so making it
# unusable owner state would have preflight refuse the whole vault over one bad
# extraction record.


def test_a_malformed_receipt_does_not_make_the_database_unusable(
    tracking_database,
) -> None:
    record = _current_record(visual_evidence=_evidence(artifact=None))

    assessment = tracking_database.assess_tracking_database(_database([record]))

    assert assessment.usable is True


def test_visual_extracted_must_mirror_the_receipt_outcome(
    mutate_tracking_database,
) -> None:
    record = _current_record(visual_extracted=False)

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError, match="must mirror"
    ):
        _write(mutate_tracking_database, record)


def test_a_succeeded_receipt_must_name_its_artifact(mutate_tracking_database) -> None:
    record = _current_record(visual_evidence=_evidence(artifact=None))

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="artifact is required",
    ):
        _write(mutate_tracking_database, record)


def test_a_failed_receipt_must_not_name_an_artifact(mutate_tracking_database) -> None:
    record = _current_record(
        visual_extracted=False, visual_evidence=_evidence(outcome="failed")
    )

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="artifact must be null",
    ):
        _write(mutate_tracking_database, record)


@pytest.mark.parametrize(
    ("fingerprint", "match"),
    [
        ({"algorithm": "md5", "digest": "a" * 64, "size_bytes": 1}, "algorithm"),
        ({"algorithm": "sha256", "digest": "nope", "size_bytes": 1}, "digest"),
        ({"algorithm": "sha256", "digest": "a" * 64, "size_bytes": 0}, "size_bytes"),
    ],
)
def test_source_fingerprint_shape_is_enforced(
    mutate_tracking_database, fingerprint, match
) -> None:
    record = _current_record(visual_evidence=_evidence(source_fingerprint=fingerprint))

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError, match=match
    ):
        _write(mutate_tracking_database, record)


def test_v1_records_may_not_carry_a_binding_field(tracking_database) -> None:
    """A v1 record with visual_evidence is drift, not a half-migrated record."""
    record = _legacy_record() | {"visual_evidence": _evidence()}

    with pytest.raises(tracking_database.TrackingDatabaseError, match="unknown fields"):
        tracking_database.require_current_tracking_database(_database([record]))


# The executable the ingress workflow runs (#229). Deterministic selection is a
# script, not something the agent reproduces.


def _vault(tmp_path, records: list[dict], *, deck: bytes | None = None):
    """A vault whose catalog rows point at real files under the source dir."""
    root = tmp_path / "vault"
    source = tmp_path / "presentations"
    (root / "evidence").mkdir(parents=True)
    source.mkdir()
    if deck is not None:
        (source / "Talk.pptx").write_bytes(deck)
    database = _database(records)
    database["config"]["pptx_source_dir"] = str(source)
    (root / "tracking-database.json").write_text(json.dumps(database))
    return root, source


def _live_record(deck_bytes: bytes, artifact_bytes: bytes) -> dict:
    return _current_record(
        pptx_path="Talk.pptx",
        visual_evidence=_evidence(
            source_fingerprint={
                "algorithm": "sha256",
                "digest": hashlib.sha256(deck_bytes).hexdigest(),
                "size_bytes": len(deck_bytes),
            },
            artifact={
                "path": "evidence/talk.json",
                "sha256": hashlib.sha256(artifact_bytes).hexdigest(),
            },
        ),
    )


def test_the_cli_reports_a_current_deck_as_not_needing_extraction(
    classify_pptx_evidence, tmp_path
) -> None:
    deck_bytes, artifact_bytes = b"deck", b'{"slides": []}'
    root, _source = _vault(tmp_path, [], deck=deck_bytes)
    (root / "evidence" / "talk.json").write_bytes(artifact_bytes)
    database = json.loads((root / "tracking-database.json").read_text())
    database["pptx_catalog"] = [_live_record(deck_bytes, artifact_bytes)]
    (root / "tracking-database.json").write_text(json.dumps(database))

    report = classify_pptx_evidence.execute(root)

    assert report["ok"] is True
    assert report["needs_extraction_count"] == 0
    assert report["records"][0]["classification"] == "current"


def test_the_cli_reports_an_edited_deck_as_stale(
    classify_pptx_evidence, tmp_path
) -> None:
    deck_bytes, artifact_bytes = b"deck", b'{"slides": []}'
    root, source = _vault(tmp_path, [], deck=deck_bytes)
    (root / "evidence" / "talk.json").write_bytes(artifact_bytes)
    database = json.loads((root / "tracking-database.json").read_text())
    database["pptx_catalog"] = [_live_record(deck_bytes, artifact_bytes)]
    (root / "tracking-database.json").write_text(json.dumps(database))
    (source / "Talk.pptx").write_bytes(b"deck-edited")

    report = classify_pptx_evidence.execute(root)

    assert report["needs_extraction_count"] == 1
    assert report["records"][0]["classification"] == "stale"


def test_the_cli_refuses_an_unusable_database(classify_pptx_evidence, tmp_path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "tracking-database.json").write_text('{"schema_version": 99}')

    assert classify_pptx_evidence.main([str(root)]) == 2


# Persisted state is a hint, never a licence to read an arbitrary host file.


def _outside_secret(tmp_path) -> pathlib.Path:
    secret = tmp_path / "outside" / "secret.pptx"
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_bytes(b"not yours")
    return secret


def test_an_absolute_locator_is_never_opened(pptx_catalog_selection, tmp_path) -> None:
    secret = _outside_secret(tmp_path)
    source = tmp_path / "presentations"
    source.mkdir()

    assert pptx_catalog_selection.digest_and_size(str(secret), source) is None


def test_a_locator_escaping_the_root_by_symlink_is_never_opened(
    pptx_catalog_selection, tmp_path
) -> None:
    secret = _outside_secret(tmp_path)
    source = tmp_path / "presentations"
    source.mkdir()
    # The suite that runs this file is the ubuntu `test` job; the platform
    # matrix runs a fixed list that excludes it. Symlink creation is available
    # there, so a failure here is a real signal, never a reason to skip.
    (source / "Talk.pptx").symlink_to(secret)

    assert pptx_catalog_selection.digest_and_size("Talk.pptx", source) is None


def test_a_contained_relative_locator_is_read(pptx_catalog_selection, tmp_path) -> None:
    source = tmp_path / "presentations"
    (source / "nested").mkdir(parents=True)
    (source / "nested" / "Talk.pptx").write_bytes(b"deck")

    observed = pptx_catalog_selection.digest_and_size("nested/Talk.pptx", source)

    assert observed == (hashlib.sha256(b"deck").hexdigest(), 4)


def test_an_absolute_artifact_path_leaves_the_receipt_unverified(
    pptx_catalog_selection, tmp_path
) -> None:
    """The escape is closed on the artifact side too, not just the deck."""
    secret = _outside_secret(tmp_path)

    assert (
        pptx_catalog_selection.observed_artifact_digest(
            {"artifact": {"path": str(secret), "sha256": "c" * 64}}, tmp_path / "vault"
        )
        is None
    )


def test_a_symlinked_intermediate_directory_is_never_traversed(
    pptx_catalog_selection, tmp_path
) -> None:
    """Every component below the root is opened O_NOFOLLOW, not just the leaf."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "Talk.pptx").write_bytes(b"not yours")
    source = tmp_path / "presentations"
    source.mkdir()
    (source / "nested").symlink_to(outside, target_is_directory=True)

    assert pptx_catalog_selection.digest_and_size("nested/Talk.pptx", source) is None


def test_a_non_regular_file_is_never_hashed(pptx_catalog_selection, tmp_path) -> None:
    source = tmp_path / "presentations"
    (source / "Talk.pptx").mkdir(parents=True)

    assert pptx_catalog_selection.digest_and_size("Talk.pptx", source) is None


def test_a_symlinked_root_is_still_trusted_configuration(
    pptx_catalog_selection, tmp_path
) -> None:
    """The root may be a symlink by design; only descendants are refused."""
    real = tmp_path / "real-presentations"
    real.mkdir()
    (real / "Talk.pptx").write_bytes(b"deck")
    link = tmp_path / "presentations"
    link.symlink_to(real, target_is_directory=True)

    assert pptx_catalog_selection.digest_and_size("Talk.pptx", link) == (
        hashlib.sha256(b"deck").hexdigest(),
        4,
    )


@pytest.mark.parametrize("primitive", ["O_NOFOLLOW", "O_DIRECTORY"])
def test_a_platform_without_the_safety_primitives_reads_nothing(
    pptx_catalog_selection, tmp_path, monkeypatch: pytest.MonkeyPatch, primitive
) -> None:
    """Missing no-follow support is a refusal, never a degraded read."""
    source = tmp_path / "presentations"
    source.mkdir()
    (source / "Talk.pptx").write_bytes(b"deck")
    assert pptx_catalog_selection.digest_and_size("Talk.pptx", source) is not None

    monkeypatch.delattr(pptx_catalog_selection.os, primitive, raising=False)

    assert pptx_catalog_selection.digest_and_size("Talk.pptx", source) is None


# no-secrets: a read failure must not echo the host path or the rejected input.


@pytest.mark.parametrize(
    ("body", "secret"),
    [
        ('{"a": 1, "a": 2}', '"a"'),
        ("{not json", "not json"),
        ('{"x": 1e400}', "1e400"),
    ],
)
def test_a_read_failure_never_echoes_the_input_or_the_host_path(
    classify_pptx_evidence, tmp_path, capsys, body, secret
) -> None:
    root = tmp_path / "vault-with-a-telling-name"
    root.mkdir()
    (root / "tracking-database.json").write_text(body)

    exit_code = classify_pptx_evidence.main([str(root)])

    captured = capsys.readouterr()
    assert exit_code == 2
    report = json.loads(captured.out)
    assert report["ok"] is False
    assert report["code"]
    combined = captured.out + captured.err
    assert "vault-with-a-telling-name" not in combined
    assert secret not in combined


def test_an_unusable_owner_state_is_reported_without_its_reason_prose(
    classify_pptx_evidence, tmp_path, capsys
) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "tracking-database.json").write_text(json.dumps({"schema_version": 99}))

    exit_code = classify_pptx_evidence.main([str(root)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert json.loads(captured.out)["code"] == "database_unreadable"
    assert str(root) not in captured.out + captured.err


def test_a_rejected_receipt_reports_a_code_not_the_persisted_value(
    pptx_catalog_selection, tmp_path
) -> None:
    """The rejected value came out of the database; it must not be echoed."""
    source = tmp_path / "presentations"
    source.mkdir()
    (source / "Talk.pptx").write_bytes(b"deck")
    poisoned = _current_record(
        pptx_path="Talk.pptx",
        visual_evidence=_evidence(
            source_fingerprint={
                "algorithm": "sekrit-algorithm-name",
                "digest": "a" * 64,
                "size_bytes": 4096,
            }
        ),
    )

    rows = pptx_catalog_selection.classify_catalog(
        _database([poisoned]), vault_root=tmp_path, pptx_source_dir=source
    )

    assert rows[0]["needs_extraction"] is True
    assert rows[0]["reason_code"] == "source_fingerprint_invalid"
    assert "sekrit-algorithm-name" not in json.dumps(rows)


# The identity gate: a talk binding must be proven before the deck's contents
# become that talk's evidence (#176).


def _identity_mutation(record: dict) -> dict:
    return {"kind": "record_pptx", "expect": {"$missing": True}, "record": record}


def test_a_matched_record_without_an_assessment_is_refused(
    mutate_tracking_database,
) -> None:
    record = _current_record()
    del record["identity_assessment"]

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match=r"missing \['identity_assessment'\]",
    ):
        mutate_tracking_database.build_candidate(
            _database([]), [_identity_mutation(record)]
        )


def test_a_matched_record_with_a_null_assessment_is_refused(
    mutate_tracking_database,
) -> None:
    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="required on a matched record",
    ):
        mutate_tracking_database.build_candidate(
            _database([]),
            [_identity_mutation(_current_record(identity_assessment=None))],
        )


@pytest.mark.parametrize("verdict", ["review_required", "unmatched"])
def test_an_unproven_verdict_cannot_bind_a_talk(
    mutate_tracking_database, verdict
) -> None:
    """A `review_required` deck is an owner decision nobody has made yet."""
    record = _current_record(identity_assessment=_identity_assessment(verdict=verdict))

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="must be 'matched' to bind a talk",
    ):
        mutate_tracking_database.build_candidate(
            _database([]), [_identity_mutation(record)]
        )


def test_an_assessment_naming_another_talk_is_refused(
    mutate_tracking_database,
) -> None:
    """The exact defect: a proven assessment pasted onto the wrong record."""
    record = _current_record(
        identity_assessment=_identity_assessment(
            selected_talk_filename="2023-01-01-someone-elses-talk.md"
        )
    )

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="does not match the record's talk_filename",
    ):
        mutate_tracking_database.build_candidate(
            _database([]), [_identity_mutation(record)]
        )


@pytest.mark.parametrize("role", ["master", "static_export", "backup"])
def test_a_non_delivery_artifact_cannot_bind_a_talk(
    mutate_tracking_database, role
) -> None:
    record = _current_record(
        identity_assessment=_identity_assessment(artifact_role=role)
    )

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="is not a delivery artifact",
    ):
        mutate_tracking_database.build_candidate(
            _database([]), [_identity_mutation(record)]
        )


def test_an_assessment_from_a_future_schema_is_refused(
    mutate_tracking_database,
) -> None:
    record = _current_record(identity_assessment=_identity_assessment(schema_version=2))

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="schema_version must be exact integer 1",
    ):
        mutate_tracking_database.build_candidate(
            _database([]), [_identity_mutation(record)]
        )


def test_a_reason_code_outside_the_taxonomy_is_refused(
    mutate_tracking_database,
) -> None:
    record = _current_record(
        identity_assessment=_identity_assessment(reason_codes=["looked_about_right"])
    )

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="outside the closed taxonomy",
    ):
        mutate_tracking_database.build_candidate(
            _database([]), [_identity_mutation(record)]
        )


def test_an_unmatched_record_must_not_carry_an_assessment(
    mutate_tracking_database,
) -> None:
    record = _current_record(talk_filename=None, matched=False)

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="must be null on an unmatched record",
    ):
        mutate_tracking_database.build_candidate(
            _database([]), [_identity_mutation(record)]
        )


def _database_with_talk(filename: str) -> dict:
    database = _database([])
    database["talks"] = [
        {"schema_version": 5, "filename": filename, "status": "pending"}
    ]
    return database


def test_a_proven_binding_is_persisted(mutate_tracking_database) -> None:
    record = _current_record()
    mutation = _identity_mutation(copy.deepcopy(record))
    mutation["expect_talk_pptx_path"] = {"$missing": True}

    candidate, changes = mutate_tracking_database.build_candidate(
        _database_with_talk(record["talk_filename"]), [mutation]
    )

    assert candidate["pptx_catalog"][0] == record
    assert any(change["kind"] == "match_pptx_talk" for change in changes)


def test_the_assessment_binds_to_the_module_that_produces_it(
    mutate_tracking_database, pptx_talk_identity
) -> None:
    """The writer's constants are the assessor's, not a second copy of them."""
    assert (
        mutate_tracking_database.PPTX_TALK_IDENTITY_SCHEMA_VERSION
        == pptx_talk_identity.PPTX_TALK_IDENTITY_SCHEMA_VERSION
    )
    assert mutate_tracking_database.VERDICT_MATCHED == (
        pptx_talk_identity.VERDICT_MATCHED
    )
    assert mutate_tracking_database.ROLE_DELIVERY == pptx_talk_identity.ROLE_DELIVERY


def test_an_assessment_the_assessor_produced_satisfies_the_writer(
    mutate_tracking_database, pptx_talk_identity
) -> None:
    """End to end: the assessor's own output is what the gate accepts."""
    talk = {
        "filename": "2024-04-10-talk.md",
        "title": "A Talk About Things",
        "conference": "Voxxed Days Ticino",
        "date": "2024-04-10",
    }
    assessment = pptx_talk_identity.assess_pptx_talk_identity(
        {"pptx_path": "Voxxed Days Ticino/2024/A Talk About Things.pptx"},
        [talk],
    )
    assert assessment.verdict == pptx_talk_identity.VERDICT_MATCHED

    record = _current_record(
        pptx_path=assessment.pptx_path,
        talk_filename=talk["filename"],
        identity_assessment=assessment.as_json(),
    )

    mutation = _identity_mutation(copy.deepcopy(record))
    mutation["expect_talk_pptx_path"] = {"$missing": True}

    candidate, _ = mutate_tracking_database.build_candidate(
        _database_with_talk(talk["filename"]), [mutation]
    )

    assert candidate["pptx_catalog"][0]["identity_assessment"] == assessment.as_json()
