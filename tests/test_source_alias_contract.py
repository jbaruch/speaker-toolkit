"""Synthetic owner, scanner, and read-only regressions for source aliases."""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
from pathlib import Path

import pytest

from conftest import CURRENT_ROOT_SCHEMA_VERSION, current_tracking_config


# Public identity pairs from #231; all metadata and comparison hashes below are
# synthetic fixtures, not a claim that this suite fetched or verified a video.
PAIRS = [
    ("76NjQxjKCAQ", "FzDYQ3SIKEc", 9750),
    ("SNMrlOxbI7k", "WKWFKEmfpmc", 9760),
    ("blLFf6iY2IA", "TYLVt9ZAI2M", 9870),
    ("P34QBbvLXjU", "sGZRDP533Nc", 9180),
]
MISSING = {"$missing": True}


def _provider(identity):
    return {
        "provider": "youtube",
        "video_id": identity,
        "url": f"https://youtu.be/{identity}",
        "title": "Synthetic delivery",
        "uploader": "Synthetic event channel",
        "upload_date": "2026-01-02",
        "duration_seconds": 2700,
        "captured_at": "2026-02-01T12:00:00Z",
    }


def _record(pair=PAIRS[0], **updates):
    canonical, alias, agreement = pair
    record = {
        "schema_version": 1,
        "talk_filename": "talk.md",
        "catalog_title": "Synthetic delivery",
        "source_type": "video",
        "alias": _provider(alias),
        "canonical": _provider(canonical),
        "relationship": "valid_duplicate",
        "event": {
            "url": "https://event.example/program/session",
            "conference": "TestConf",
            "date": "2026-01-01",
            "speakers": ["Synthetic Speaker"],
        },
        "comparison": {
            "method": "transcript",
            "summary": "Synthetic matching interior recording sequence",
            "canonical_sha256": "a" * 64,
            "alias_sha256": "b" * 64,
            "agreement_basis_points": agreement,
        },
        "reviewer": "Synthetic owner",
        "verified_at": "2026-02-01T14:00:00+01:00",
        "canonical_choice_reason": "The event upload retains the complete Q&A",
    }
    record.update(updates)
    return record


def _database(record=None):
    record = record or _record()
    return {
        "schema_version": CURRENT_ROOT_SCHEMA_VERSION,
        "config": current_tracking_config(),
        "talks": [
            {
                "schema_version": 1,
                "filename": "talk.md",
                "title": record["catalog_title"],
                "conference": record["event"]["conference"],
                "date": record["event"]["date"],
                "status": "pending",
                "video_url": record["canonical"]["url"],
                "youtube_id": record["canonical"]["video_id"],
            }
        ],
        "pptx_catalog": [],
        "qr_codes": [],
        "resources": [],
        "thumbnails": [],
        "confirmed_intents": [],
        "improvement_goals": [],
    }


def _mutation(database, record):
    talk = database["talks"][0]
    return {
        "kind": "record_source_alias",
        "record": record,
        "expect": {
            "video_url": talk.get("video_url", MISSING),
            "youtube_id": talk.get("youtube_id", MISSING),
            "source_rejections": talk.get("source_rejections", MISSING),
            "source_aliases": database.get("source_aliases", MISSING),
        },
    }


def _write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


@pytest.mark.parametrize("pair", PAIRS)
def test_owner_acceptance_preserves_canonical_and_all_talk_state(
    mutate_tracking_database, tracking_database, pair
):
    record = _record(pair)
    database = _database(record)
    before = copy.deepcopy(database)
    candidate, changes = mutate_tracking_database.build_candidate(
        database, [_mutation(database, record)]
    )
    assert candidate == {**before, "source_aliases": [record]}
    assert database == before
    assert len(changes) == 1
    assert tracking_database.assess_tracking_database(candidate).state == "current"
    again, changes = mutate_tracking_database.build_candidate(
        candidate, [_mutation(candidate, record)]
    )
    assert again == candidate
    assert changes == []


@pytest.mark.parametrize("pair", PAIRS)
@pytest.mark.parametrize("stored_id", [True, False])
def test_scanner_resolves_alias_url_and_id_without_any_write(
    mutate_tracking_database, scan_shownotes_module, tmp_path, pair, stored_id
):
    record = _record(pair)
    database = _database(record)
    if not stored_id:
        database["talks"][0].pop("youtube_id")
    site = tmp_path / "shownotes"
    notes = site / "_talks"
    notes.mkdir(parents=True)
    database["config"]["shownotes"] = {
        "enabled": True,
        "source": {
            "type": "local_jekyll",
            "path_or_url": str(site),
            "talks_subdir": "_talks",
        },
    }
    database, _ = mutate_tracking_database.build_candidate(
        database, [_mutation(database, record)]
    )
    (notes / "talk.md").write_text(
        "---\nlayout: talk\n---\n# Synthetic delivery\n**Conference:** TestConf\n"
        f"**Date:** 2026-01-01\n**Video:** [Watch](https://www.youtube.com/watch?v={record['alias']['video_id']})\n",
        encoding="utf-8",
    )
    path = tmp_path / "tracking-database.json"
    _write(path, database)
    original = path.read_bytes()
    report = scan_shownotes_module.execute(path, apply_requested=True)
    assert report["entries"][0]["disposition"] == "unchanged"
    assert report["entries"][0]["issues"] == []
    assert report["mutation_count"] == 0
    assert not report["database_written"]
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("schema_version", 2),
        ("schema_version", 1.0),
        ("relationship", "wrong_delivery"),
        ("relationship", []),
        ("source_type", "slides"),
        ("reviewer", ""),
        ("verified_at", "2026-02-01T14:00:00"),
        ("verified_at", "20260201T14:00:00Z"),
        ("verified_at", "2026-W05-7T14:00:00Z"),
        ("comparison", {}),
        ("event", {}),
        ("canonical_choice_reason", ""),
    ],
)
def test_closed_record_failures_never_modify_input(tracking_database, field, value):
    record = _record(**{field: value})
    database = _database()
    database["source_aliases"] = [record]
    before = copy.deepcopy(database)
    with pytest.raises(tracking_database.TrackingDatabaseError):
        tracking_database.assess_tracking_database(database)
    assert database == before


@pytest.mark.parametrize(
    "side,field,value",
    [
        ("alias", "video_id", "WrongVideo1"),
        ("canonical", "provider", "unknown"),
        ("alias", "url", "https://youtube.com/watch?v=FzDYQ3SIKEc&v=WrongVideo1"),
        ("alias", "duration_seconds", True),
        ("canonical", "duration_seconds", 10**400),
        ("comparison", "method", "title_similarity"),
        ("comparison", "method", []),
        ("comparison", "alias_sha256", None),
        ("comparison", "agreement_basis_points", True),
        ("event", "url", "https://youtu.be/FzDYQ3SIKEc"),
        ("event", "speakers", []),
    ],
)
def test_provider_and_independent_evidence_are_required(
    tracking_database, side, field, value
):
    database = _database()
    record = _record()
    record[side][field] = value
    database["source_aliases"] = [record]
    with pytest.raises(tracking_database.TrackingDatabaseError):
        tracking_database.assess_tracking_database(database)


@pytest.mark.parametrize(
    "change",
    [
        "canonical",
        "date",
        "title",
        "rejected",
        "cross_talk",
        "active_overlap",
        "cycle",
        "future",
    ],
)
def test_conflicts_fail_closed_before_owner_write(mutate_tracking_database, change):
    record = _record()
    database = _database(record)
    if change == "canonical":
        record["canonical"] = _provider(PAIRS[1][0])
    elif change == "date":
        record["event"]["date"] = "2025-01-01"
    elif change == "title":
        record["catalog_title"] = "A different delivery"
    elif change == "rejected":
        database["talks"][0]["source_rejections"] = [
            {
                "schema_version": 1,
                "source_type": "video",
                "url": record["alias"]["url"],
                "reason": "wrong_delivery",
                "evidence": "Independent program identifies a different talk",
                "verified_at": "2026-02-01T12:00:00Z",
            }
        ]
    elif change in {"cross_talk", "active_overlap"}:
        other = copy.deepcopy(database["talks"][0])
        other["filename"] = "unrelated.md"
        other["youtube_id"] = (
            record["alias"]["video_id"] if change == "active_overlap" else PAIRS[1][0]
        )
        other["video_url"] = f"https://youtu.be/{other['youtube_id']}"
        database["talks"].append(other)
        if change == "cross_talk":
            prior = copy.deepcopy(record)
            prior["talk_filename"] = "unrelated.md"
            prior["canonical"] = _provider(PAIRS[1][0])
            database["source_aliases"] = [prior]
    elif change == "cycle":
        first = _record()
        second = _record(PAIRS[1])
        first["canonical"] = copy.deepcopy(second["alias"])
        second["canonical"] = copy.deepcopy(first["alias"])
        database["source_aliases"] = [first, second]
    else:
        database["source_aliases"] = [_record(schema_version=999)]
    before = copy.deepcopy(database)
    with pytest.raises(mutate_tracking_database.TrackingDatabaseMutationError):
        mutate_tracking_database.build_candidate(
            database, [_mutation(database, record)]
        )
    assert database == before


def test_alias_apply_binds_input_and_reviewed_candidate(
    mutate_tracking_database, tmp_path
):
    record = _record()
    database = _database(record)
    path = tmp_path / "tracking-database.json"
    plan = tmp_path / "alias-plan.json"
    _write(path, database)
    original = path.read_bytes()
    payload = {"schema_version": 1, "mutations": [_mutation(database, record)]}
    _write(plan, payload)
    preview = mutate_tracking_database.execute(
        path, plan, apply=False, expected_sha256=None
    )
    assert path.read_bytes() == original
    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="expected-output-sha256",
    ):
        mutate_tracking_database.execute(
            path, plan, apply=True, expected_sha256=preview["input_sha256"]
        )
    payload["mutations"][0]["record"]["reviewer"] = "Different reviewer after review"
    _write(plan, payload)
    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError, match="candidate output"
    ):
        mutate_tracking_database.execute(
            path,
            plan,
            apply=True,
            expected_sha256=preview["input_sha256"],
            expected_output_sha256=preview["output_sha256"],
        )
    assert path.read_bytes() == original
    payload["mutations"][0]["record"]["reviewer"] = _record()["reviewer"]
    _write(plan, payload)
    result = mutate_tracking_database.execute(
        path,
        plan,
        apply=True,
        expected_sha256=preview["input_sha256"],
        expected_output_sha256=preview["output_sha256"],
    )
    assert result["database_written"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == preview["output_sha256"]
    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError, match="input sha256"
    ):
        mutate_tracking_database.execute(
            path,
            plan,
            apply=True,
            expected_sha256=preview["input_sha256"],
            expected_output_sha256=preview["output_sha256"],
        )


def test_v2_rollout_read_and_owner_migration_preserve_values(tracking_database):
    database = _database()
    database["schema_version"] = 2
    before = copy.deepcopy(database)
    assert tracking_database.assess_tracking_database(database).state == "legacy"
    result = tracking_database.migrate_tracking_database(database)
    assert result.database == {**before, "schema_version": CURRENT_ROOT_SCHEMA_VERSION}
    assert result.from_schema_version == 2
    assert not any(result.record_counts.values())
    assert database == before


@pytest.mark.parametrize("root", [2, 3])
def test_qr_only_repair_retains_root_and_active_claims(tracking_database, root):
    from test_tracking_database_schema import _qr_repair_with_active_claim

    database = _qr_repair_with_active_claim(tracking_database, 7)
    database["schema_version"] = root
    before = copy.deepcopy(database)
    assert not tracking_database.assess_tracking_database(database).usable
    result = tracking_database.repair_missing_qr_schema_versions(database)
    expected = copy.deepcopy(before)
    expected["qr_codes"][0]["schema_version"] = 1
    assert result.database == expected
    assert result.from_schema_version == result.to_schema_version == root
    assert database == before


def test_preflight_and_reader_refuse_future_alias_without_rewrite(
    preflight_vault, read_tracking_database, tmp_path, capsys
):
    database = _database()
    database["source_aliases"] = [_record(schema_version=999)]
    path = tmp_path / "tracking-database.json"
    _write(path, database)
    original = path.read_bytes()
    assert preflight_vault.main([str(tmp_path)]) == 1
    assert json.loads(capsys.readouterr().out)["blocking_count"] >= 1
    assert read_tracking_database.main([str(path)]) == 2
    assert "database" not in json.loads(capsys.readouterr().out)
    assert path.read_bytes() == original


def test_alias_record_is_not_a_source_capability(tracking_database):
    database = _database()
    contract = importlib.import_module("ingress_contract")
    assert not contract.has_video_source({"source_aliases": [_record()]})
    database["talks"][0].pop("video_url")
    database["talks"][0].pop("youtube_id")
    database["source_aliases"] = [_record()]
    with pytest.raises(
        tracking_database.TrackingDatabaseError, match="no agreeing canonical"
    ):
        tracking_database.assess_tracking_database(database)


@pytest.mark.parametrize(
    "relationship", ["valid_duplicate", "mirror", "superseded_by_official_upload"]
)
def test_closed_relationships_preserve_valid_alternates(
    mutate_tracking_database, relationship
):
    record = _record(relationship=relationship)
    database = _database(record)
    result, _ = mutate_tracking_database.build_candidate(
        database, [_mutation(database, record)]
    )
    assert result["source_aliases"] == [record]
    assert result["talks"] == database["talks"]


def test_alias_approval_refuses_an_active_claim(
    mutate_tracking_database, tracking_database
):
    from test_tracking_database_schema import _qr_repair_with_active_claim

    database = tracking_database.repair_missing_qr_schema_versions(
        _qr_repair_with_active_claim(tracking_database, 7)
    ).database
    record = _record(talk_filename=database["talks"][0]["filename"])
    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError, match="active claim"
    ):
        mutate_tracking_database.build_candidate(
            database, [_mutation(database, record)]
        )


def test_unrelated_writers_and_profile_preserve_alias_values(
    mutate_tracking_database,
    apply_source_repairs,
    queue_state,
    persist_results,
    tracking_database_io,
    validate_profile,
    tmp_path,
):
    record = _record()
    database = _database(record)
    database["talks"][0]["status"] = "processed_partial"
    database["talks"][0]["processed_date"] = "2026-01-03"
    database["talks"][0]["rhetoric_notes"] = "Historical delivery notes"
    path = tmp_path / "tracking-database.json"
    _write(path, database)
    profile = {
        "pattern_profile": {"pattern_baseline": {"as_of": "2026-02-02T12:00:00Z"}}
    }
    before = validate_profile._load_live_pattern_snapshot(tmp_path, profile)
    database, _ = mutate_tracking_database.build_candidate(
        database, [_mutation(database, record)]
    )
    _write(path, database)
    assert validate_profile._load_live_pattern_snapshot(tmp_path, profile) == before
    ledger_bytes = json.dumps(database["source_aliases"], ensure_ascii=False).encode()
    candidate, _ = mutate_tracking_database.build_candidate(
        database,
        [
            {
                "kind": "set_config",
                "path": ["speaker_name"],
                "expect": MISSING,
                "value": "Synthetic Speaker",
            }
        ],
    )
    candidate, _ = apply_source_repairs.build_repaired_database(
        candidate,
        [
            {
                "filename": "talk.md",
                "reason": "Explicit queue transition unrelated to alias identity",
                "expect": {"status": "processed_partial"},
                "set": {"status": "needs-reprocessing"},
            }
        ],
    )
    snapshot = tracking_database_io.snapshot_tracking_database(path)
    queue_state.write_database_atomically(path, candidate, expected_snapshot=snapshot)
    loaded, snapshot = persist_results.load_tracking_database(path)
    assert (
        json.dumps(loaded["source_aliases"], ensure_ascii=False).encode()
        == ledger_bytes
    )
    loaded["talks"][0]["rhetoric_notes"] = "Updated synthetic analysis"
    persist_results.atomic_write_json(path, loaded, expected_snapshot=snapshot)
    stored = tracking_database_io.decode_json_object(
        tracking_database_io.snapshot_tracking_database(path)
    )
    assert (
        json.dumps(stored["source_aliases"], ensure_ascii=False).encode()
        == ledger_bytes
    )


def test_scanner_cannot_import_another_talk_with_an_accepted_alias(
    mutate_tracking_database,
    scan_shownotes_module,
    tmp_path,
):
    record = _record()
    database = _database(record)
    site = tmp_path / "notes"
    talks = site / "_talks"
    talks.mkdir(parents=True)
    (talks / "unrelated.md").write_text(
        "---\nlayout: talk\n---\n# Unrelated delivery\n**Conference:** ElseConf\n"
        f"**Date:** 2026-01-02\n**Video:** [Watch]({record['alias']['url']})\n",
        encoding="utf-8",
    )
    database["config"]["shownotes"] = {
        "enabled": True,
        "source": {
            "type": "local_jekyll",
            "path_or_url": str(site),
            "talks_subdir": "_talks",
        },
    }
    database, _ = mutate_tracking_database.build_candidate(
        database, [_mutation(database, record)]
    )
    path = tmp_path / "tracking-database.json"
    _write(path, database)
    original = path.read_bytes()
    with pytest.raises(
        scan_shownotes_module.ShownotesScanError, match="overlaps an active canonical"
    ):
        scan_shownotes_module.execute(path, apply_requested=True)
    assert path.read_bytes() == original


@pytest.mark.parametrize("expected", [None, [], {"video_url": None}])
def test_incomplete_expectations_are_closed(mutate_tracking_database, expected):
    database = _database()
    mutation = _mutation(database, _record())
    mutation["expect"] = expected
    with pytest.raises(mutate_tracking_database.TrackingDatabaseMutationError):
        mutate_tracking_database.build_candidate(database, [mutation])


@pytest.mark.parametrize("value", ["20260101", "2026-W01-4", "2026-02-30"])
@pytest.mark.parametrize("side,field", [("event", "date"), ("alias", "upload_date")])
def test_calendar_dates_have_one_portable_valid_spelling(
    tracking_database, value, side, field
):
    record = _record()
    record[side][field] = value
    database = _database()
    database["source_aliases"] = [record]
    with pytest.raises(tracking_database.TrackingDatabaseError, match="calendar date"):
        tracking_database.assess_tracking_database(database)


@pytest.mark.parametrize("value", ["typo", "A" * 64, "f" * 63, "missing"])
def test_invalid_candidate_digest_names_its_own_flag(
    mutate_tracking_database, tmp_path, value
):
    database = _database()
    path = tmp_path / "tracking-database.json"
    plan = tmp_path / "alias-plan.json"
    _write(path, database)
    original = path.read_bytes()
    _write(plan, {"schema_version": 1, "mutations": [_mutation(database, _record())]})
    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="--expected-output-sha256",
    ) as error:
        mutate_tracking_database.execute(
            path,
            plan,
            apply=True,
            expected_sha256=hashlib.sha256(original).hexdigest(),
            expected_output_sha256=value,
        )
    assert "--expected-sha256" not in str(error.value)
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    "relative",
    [
        "vault-clarification/SKILL.md",
        "presentation-creator/SKILL.md",
        "presentation-creator/references/phase7-post-event.md",
        "illustrations/references/thumbnails.md",
        "vault-ingress/references/bootstrap-and-preflight.md",
        "vault-ingress/references/batch-persistence.md",
        "vault-profile/references/profile-construction-rules.md",
    ],
)
def test_catalog_rollout_consumers_reference_owner_schema(relative):
    root = Path(__file__).resolve().parents[1]
    document = (root / "skills" / relative).read_text(encoding="utf-8")
    assert "schemas-db.md#schema-versioning" in document
    for obsolete in (
        "database schema 2",
        "database schema v2",
        "current schema 2",
        "writes require schema 2",
        "schemas 0 and 1",
        "schema 0 or 1",
    ):
        assert obsolete not in document
    owner = (root / "skills/vault-ingress/references/schemas-db.md").read_text(
        encoding="utf-8"
    )
    assert "### Schema versioning" in owner
