"""Synthetic official-upload transitions; no live equivalence judgments."""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import os
import subprocess
import sys

import pytest

from test_source_alias_contract import (
    MISSING,
    PAIRS,
    _database,
    _provider,
    _record,
    _write,
)


def _promotion(database, identity=PAIRS[0][1]):
    talk = database["talks"][0]
    record = _record(
        alias=_provider(talk["youtube_id"]),
        canonical=_provider(identity),
        relationship="superseded_by_official_upload",
        canonical_choice_reason="Owner verified the event's official full upload",
    )
    return {
        "kind": "promote_source_alias",
        "record": record,
        "expect": {
            "talk": copy.deepcopy(talk),
            "source_aliases": copy.deepcopy(database.get("source_aliases", MISSING)),
        },
    }


@pytest.mark.parametrize("existing_alias", [False, True])
@pytest.mark.parametrize(
    "status", ["pending", "processed", "processed_partial", "needs-reprocessing"]
)
def test_promotion_preserves_evidence_and_moves_only_reviewed_source_state(
    mutate_tracking_database, tracking_database, existing_alias, status
):
    database = _database()
    talk = database["talks"][0]
    talk.update(
        status=status,
        source_identity={"schema_version": 1, "video_id": talk["youtube_id"]},
        transcript_path="transcripts/original.txt",
        video_local_path="videos/original.mp4",
        rhetoric_notes="Observations of the original recording",
        structured_data={
            "video_extraction": {
                "schema_version": 3,
                "source_video_path": "videos/original.mp4",
            }
        },
    )
    if existing_alias:
        database["source_aliases"] = [_record()]
    original = copy.deepcopy(database)
    mutation = _promotion(database)
    candidate, changes = mutate_tracking_database.build_candidate(database, [mutation])
    expected_talk = copy.deepcopy(talk)
    expected_talk.update(
        video_url=mutation["record"]["canonical"]["url"],
        youtube_id=mutation["record"]["canonical"]["video_id"],
        status="needs-reprocessing",
        reprocess_reason="source_added",
    )
    expected_talk.pop("source_identity")
    assert candidate["talks"] == [expected_talk]
    assert database == original
    assert len(changes) == 1
    assert tracking_database.assess_tracking_database(candidate).state == "current"
    history = candidate["source_aliases"][0]
    assert history["schema_version"] == 2
    assert history["prior_state"] == {
        "schema_version": 1,
        **{
            field: talk.get(field, MISSING)
            for field in (
                "video_url",
                "youtube_id",
                "source_identity",
                "status",
                "reprocess_reason",
            )
        },
    }
    assert history["retired_alias"] == (_record() if existing_alias else None)
    assert history["alias"]["video_id"] == talk["youtube_id"]
    assert "source_rejections" not in candidate["talks"][0]


def test_repeated_promotions_preserve_prior_decisions_and_resolve_all_edges(
    mutate_tracking_database, tracking_database
):
    contract = importlib.import_module("source_alias_contract")
    database = _database()
    database["source_aliases"] = [_record(), _record(alias=_provider(PAIRS[1][1]))]
    original = copy.deepcopy(database)
    for identity in (PAIRS[0][1], PAIRS[1][1], PAIRS[0][0], PAIRS[0][1]):
        previous = copy.deepcopy(database)
        database, _ = mutate_tracking_database.build_candidate(
            database, [_promotion(database, identity)]
        )
        assert tracking_database.assess_tracking_database(database).state == "current"
        for source in (PAIRS[0][0], PAIRS[0][1], PAIRS[1][1]):
            match = contract.matched_alias(
                database, database["talks"][0], _provider(source)["url"]
            )
            assert (match is None) == (source == identity)
        latest = database["source_aliases"][-1]
        prior = next(
            (
                item
                for item in previous["source_aliases"]
                if item["alias"]["video_id"] == identity
            ),
            None,
        )
        assert latest["retired_alias"] == prior
        for item in previous["source_aliases"]:
            if item != prior:
                assert item in database["source_aliases"]
    assert original["source_aliases"][0] == _record()


@pytest.mark.parametrize(
    "fault",
    [
        "wrong_delivery",
        "stale_talk",
        "stale_ledger",
        "wrong_old_source",
        "no_reason",
        "not_official",
        "rejected",
        "other_active",
        "other_alias",
        "active_claim",
        "inflight",
        "composed_plan",
        "forged_history",
    ],
)
def test_promotion_refuses_conflicts_without_mutation(mutate_tracking_database, fault):
    database = _database()
    if fault == "rejected":
        database["talks"][0]["source_rejections"] = [
            {
                "schema_version": 1,
                "source_type": "video",
                "url": _provider(PAIRS[0][1])["url"],
                "reason": "wrong_delivery",
                "evidence": "Synthetic rejected delivery",
                "verified_at": "2026-02-01T12:00:00Z",
            }
        ]
    elif fault in {"other_active", "other_alias"}:
        other = copy.deepcopy(database["talks"][0])
        other.update(
            filename="other.md",
            video_url=_provider(PAIRS[1][0])["url"],
            youtube_id=PAIRS[1][0],
        )
        if fault == "other_active":
            other.update(
                video_url=_provider(PAIRS[0][1])["url"], youtube_id=PAIRS[0][1]
            )
        else:
            database["source_aliases"] = [
                _record(talk_filename="other.md", canonical=_provider(PAIRS[1][0]))
            ]
        database["talks"].append(other)
    elif fault == "inflight":
        database["talks"][0]["status"] = "reprocessing-inflight"
    elif fault == "active_claim":
        # The owner rejects this malformed lease before a promotion may edit it.
        database["talks"][0]["_queue_claim"] = {
            "schema_version": 999,
            "state": "claimed",
        }
    mutation = _promotion(database)
    if fault == "wrong_delivery":
        mutation["record"]["event"]["date"] = "2025-01-01"
    elif fault == "stale_talk":
        mutation["expect"]["talk"]["rhetoric_notes"] = "Stale reviewed observations"
    elif fault == "stale_ledger":
        mutation["expect"]["source_aliases"] = []
    elif fault == "wrong_old_source":
        mutation["record"]["alias"] = _provider(PAIRS[1][1])
    elif fault == "no_reason":
        mutation["record"]["canonical_choice_reason"] = None
    elif fault == "not_official":
        mutation["record"]["relationship"] = "mirror"
    elif fault == "forged_history":
        mutation["record"]["schema_version"] = 2
    plan = (
        [mutation, copy.deepcopy(mutation)] if fault == "composed_plan" else [mutation]
    )
    before = copy.deepcopy(database)
    with pytest.raises(mutate_tracking_database.TrackingDatabaseMutationError):
        mutate_tracking_database.build_candidate(database, plan)
    assert database == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 999),
        ("schema_version", True),
        ("video_url", "https://youtu.be/WrongVideo1"),
        ("youtube_id", "WrongVideo1"),
        ("status", []),
        ("source_identity", "invalid"),
        ("youtube_id", {"$missing": 1}),
        ("status", {"$missing": 1.0}),
    ],
)
def test_malformed_history_is_not_usable(
    mutate_tracking_database, tracking_database, field, value
):
    database = _database()
    database, _ = mutate_tracking_database.build_candidate(
        database, [_promotion(database)]
    )
    database["source_aliases"][0]["prior_state"][field] = value
    before = copy.deepcopy(database)
    with pytest.raises(tracking_database.TrackingDatabaseError):
        tracking_database.assess_tracking_database(database)
    assert database == before


@pytest.mark.parametrize("fault", ["future", "wrong_identity", "wrong_talk", "depth"])
def test_retired_alias_history_fails_closed(
    mutate_tracking_database, tracking_database, fault
):
    database = _database()
    database["source_aliases"] = [_record()]
    database, _ = mutate_tracking_database.build_candidate(
        database, [_promotion(database)]
    )
    retired = database["source_aliases"][0]["retired_alias"]
    if fault == "future":
        retired["schema_version"] = 999
    elif fault == "wrong_identity":
        retired["alias"] = _provider(PAIRS[1][1])
    elif fault == "wrong_talk":
        retired["talk_filename"] = "other.md"
    else:
        # A cyclic in-memory input must reach the explicit depth refusal, not recursion.
        parent = database["source_aliases"][0]
        child = copy.deepcopy(parent)
        child["alias"], child["canonical"] = parent["canonical"], parent["alias"]
        child["prior_state"]["video_url"] = child["alias"]["url"]
        child["prior_state"]["youtube_id"] = child["alias"]["video_id"]
        parent["retired_alias"] = child
        child["retired_alias"] = parent
    with pytest.raises(tracking_database.TrackingDatabaseError):
        tracking_database.assess_tracking_database(database)


def test_promotion_hash_review_survives_separate_processes(
    mutate_tracking_database, tmp_path
):
    database = _database()
    path = tmp_path / "tracking-database.json"
    plan = tmp_path / "promotion.json"
    _write(path, database)
    _write(plan, {"schema_version": 1, "mutations": [_promotion(database)]})
    original = path.read_bytes()
    script = mutate_tracking_database.__file__
    result = subprocess.run(
        [sys.executable, script, str(path), str(plan)],
        env={**os.environ, "PYTHONHASHSEED": "1"},
        capture_output=True,
        text=True,
        check=True,
    )
    preview = json.loads(result.stdout)
    assert path.read_bytes() == original
    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="expected-output-sha256",
    ):
        mutate_tracking_database.execute(
            path, plan, apply=True, expected_sha256=preview["input_sha256"]
        )
    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError, match="candidate output"
    ):
        mutate_tracking_database.execute(
            path,
            plan,
            apply=True,
            expected_sha256=preview["input_sha256"],
            expected_output_sha256="0" * 64,
        )
    assert path.read_bytes() == original
    result = subprocess.run(
        [
            sys.executable,
            script,
            str(path),
            str(plan),
            "--apply",
            "--expected-sha256",
            preview["input_sha256"],
            "--expected-output-sha256",
            preview["output_sha256"],
        ],
        env={**os.environ, "PYTHONHASHSEED": "2"},
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout)["database_written"]
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


def test_promotion_cas_keeps_competing_write(
    mutate_tracking_database, tmp_path, monkeypatch
):
    database = _database()
    path = tmp_path / "tracking-database.json"
    plan = tmp_path / "promotion.json"
    _write(path, database)
    _write(plan, {"schema_version": 1, "mutations": [_promotion(database)]})
    preview = mutate_tracking_database.execute(
        path, plan, apply=False, expected_sha256=None
    )
    commit = mutate_tracking_database.commit_tracking_database
    competitor = copy.deepcopy(database)
    competitor["talks"][0]["rhetoric_notes"] = "Concurrent owner write"

    def competing_commit(snapshot, rendered):
        _write(path, competitor)
        return commit(snapshot, rendered)

    monkeypatch.setattr(
        mutate_tracking_database, "commit_tracking_database", competing_commit
    )
    with pytest.raises(mutate_tracking_database.TrackingDatabaseMutationError):
        mutate_tracking_database.execute(
            path,
            plan,
            apply=True,
            expected_sha256=preview["input_sha256"],
            expected_output_sha256=preview["output_sha256"],
        )
    assert json.loads(path.read_bytes()) == competitor


@pytest.mark.parametrize("version", [2, 3])
def test_missing_config_diagnostic_names_observed_readable_root(
    tracking_database, version
):
    database = _database()
    database["schema_version"] = version
    database.pop("config")
    with pytest.raises(
        tracking_database.TrackingDatabaseError,
        match=f"schema v{version} requires a 'config' object",
    ):
        tracking_database.assess_tracking_database(database)


@pytest.mark.parametrize("claim_version", range(1, 8))
def test_promotion_refuses_valid_active_claim_generations(
    mutate_tracking_database, tracking_database, claim_version
):
    from test_tracking_database_schema import _qr_repair_with_active_claim

    database = tracking_database.repair_missing_qr_schema_versions(
        _qr_repair_with_active_claim(tracking_database, claim_version)
    ).database
    talk = database["talks"][0]
    mutation = {
        "kind": "promote_source_alias",
        "record": _record(talk_filename=talk["filename"]),
        "expect": {"talk": copy.deepcopy(talk), "source_aliases": MISSING},
    }
    before = copy.deepcopy(database)
    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError, match="active claim"
    ):
        mutate_tracking_database.build_candidate(database, [mutation])
    assert database == before


@pytest.mark.parametrize("source", [PAIRS[0][0], PAIRS[0][1], PAIRS[1][1]])
def test_shownotes_resolves_superseded_and_other_aliases_after_promotion(
    mutate_tracking_database, scan_shownotes_module, tmp_path, source
):
    database = _database()
    database["source_aliases"] = [_record(), _record(alias=_provider(PAIRS[1][1]))]
    site = tmp_path / "notes"
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
    (notes / "talk.md").write_text(
        "---\nlayout: talk\n---\n# Synthetic delivery\n**Conference:** TestConf\n"
        f"**Date:** 2026-01-01\n**Video:** [Watch](https://youtu.be/{source})\n",
        encoding="utf-8",
    )
    database, _ = mutate_tracking_database.build_candidate(
        database, [_promotion(database)]
    )
    path = tmp_path / "tracking-database.json"
    _write(path, database)
    before = path.read_bytes()
    report = scan_shownotes_module.execute(path, apply_requested=True)
    assert report["entries"][0]["disposition"] == "unchanged"
    assert report["mutation_count"] == 0
    assert not report["database_written"]
    assert path.read_bytes() == before


def test_unrelated_writers_and_owner_reads_preserve_promotion_history(
    mutate_tracking_database,
    apply_source_repairs,
    queue_state,
    persist_results,
    tracking_database_io,
    read_tracking_database,
    tmp_path,
    capsys,
):
    database = _database()
    database["source_aliases"] = [_record()]
    database, _ = mutate_tracking_database.build_candidate(
        database, [_promotion(database)]
    )
    history = json.dumps(database["source_aliases"]).encode()
    path = tmp_path / "tracking-database.json"
    _write(path, database)
    original = path.read_bytes()
    assert read_tracking_database.main([str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    assert path.read_bytes() == original
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
                "reason": "Unrelated PDF registration",
                "expect": {"slides_url": MISSING},
                "set": {"slides_url": "https://slides.example/slides.pdf"},
            }
        ],
    )
    snapshot = tracking_database_io.snapshot_tracking_database(path)
    queue_state.write_database_atomically(path, candidate, expected_snapshot=snapshot)
    loaded, snapshot = persist_results.load_tracking_database(path)
    loaded["talks"][0]["rhetoric_notes"] = "New synthetic notes"
    persist_results.atomic_write_json(path, loaded, expected_snapshot=snapshot)
    stored = tracking_database_io.decode_json_object(
        tracking_database_io.snapshot_tracking_database(path)
    )
    assert json.dumps(stored["source_aliases"]).encode() == history


def test_promotion_contract_documents_history_and_evidence_boundary():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    reference = (root / "skills/vault-ingress/references/source-aliases.md").read_text(
        encoding="utf-8"
    )
    assert "`promote_source_alias` as the plan's sole" in reference
    for field in ("prior_state", "retired_alias", "source_added"):
        assert f"`{field}`" in reference
    assert "Never clear or relabel those receipts to bypass a gate" in reference
