"""Tests for guarded, auditable vault source repairs."""

import json

import pytest


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def base_database():
    return {
        "config": {},
        "talks": [{
            "filename": "talk.md",
            "status": "processed",
            "video_url": "https://youtu.be/AbCdEfGhI_1",
            "youtube_id": "AbCdEfGhI_1",
            "transcript_source": "youtube_auto",
        }],
    }


def repair_plan(**overrides):
    repair = {
        "filename": "talk.md",
        "reason": "provider metadata identifies a demo rather than a delivery",
        "expect": {
            "video_url": "https://youtu.be/AbCdEfGhI_1",
            "youtube_id": "AbCdEfGhI_1",
            "transcript_source": "youtube_auto",
            "status": "processed",
            "reprocess_reason": {"$missing": True},
        },
        "clear": ["video_url", "youtube_id"],
        "set": {
            "transcript_source": "none",
            "status": "needs-reprocessing",
            "reprocess_reason": "source_identity_correction",
        },
    }
    repair.update(overrides)
    return {"schema_version": 1, "repairs": [repair]}


def test_dry_run_reports_changes_without_writing(
    apply_source_repairs, tmp_path,
):
    database_path = tmp_path / "tracking-database.json"
    plan_path = tmp_path / "plan.json"
    database = base_database()
    write_json(database_path, database)
    write_json(plan_path, repair_plan())
    before = database_path.read_bytes()

    report = apply_source_repairs.execute(
        database_path, plan_path, apply=False,
    )

    assert report["mode"] == "dry-run"
    assert report["repair_count"] == 1
    assert report["backup"] is None
    assert database_path.read_bytes() == before


def test_apply_writes_atomically_and_creates_exact_backup(
    apply_source_repairs, tmp_path,
):
    database_path = tmp_path / "tracking-database.json"
    plan_path = tmp_path / "plan.json"
    backup_dir = tmp_path / "backups"
    write_json(database_path, base_database())
    write_json(plan_path, repair_plan())
    before = database_path.read_bytes()

    report = apply_source_repairs.execute(
        database_path, plan_path, apply=True, backup_dir=backup_dir,
    )

    repaired = json.loads(database_path.read_text(encoding="utf-8"))
    talk = repaired["talks"][0]
    assert "video_url" not in talk
    assert "youtube_id" not in talk
    assert talk["transcript_source"] == "none"
    assert talk["status"] == "needs-reprocessing"
    assert report["mode"] == "apply"
    assert report["repair_count"] == 1
    assert report["backup"] is not None
    assert next(backup_dir.iterdir()).read_bytes() == before


def test_atomic_write_cleans_stage_and_propagates_interrupt(
    apply_source_repairs, tmp_path, monkeypatch,
):
    target = tmp_path / "tracking-database.json"
    target.write_text("old\n", encoding="utf-8")

    def interrupt(_source, _target):
        raise KeyboardInterrupt

    monkeypatch.setattr(apply_source_repairs.os, "replace", interrupt)

    with pytest.raises(KeyboardInterrupt):
        apply_source_repairs.atomic_write(target, "new\n")

    assert target.read_text(encoding="utf-8") == "old\n"
    assert [path.name for path in tmp_path.iterdir()] == [target.name]


def test_expectation_mismatch_aborts_whole_plan_without_backup(
    apply_source_repairs, tmp_path,
):
    database_path = tmp_path / "tracking-database.json"
    plan_path = tmp_path / "plan.json"
    backup_dir = tmp_path / "backups"
    database = base_database()
    write_json(database_path, database)
    plan = repair_plan()
    plan["repairs"][0]["expect"]["youtube_id"] = "WrongId0000"
    write_json(plan_path, plan)
    before = database_path.read_bytes()

    with pytest.raises(
        apply_source_repairs.SourceRepairError, match="preconditions failed"
    ):
        apply_source_repairs.execute(
            database_path, plan_path, apply=True, backup_dir=backup_dir,
        )

    assert database_path.read_bytes() == before
    assert not backup_dir.exists()


def test_missing_marker_distinguishes_absent_from_null(
    apply_source_repairs, tmp_path,
):
    database_path = tmp_path / "tracking-database.json"
    plan_path = tmp_path / "plan.json"
    database = base_database()
    database["talks"][0].pop("youtube_id")
    write_json(database_path, database)
    plan = repair_plan(
        expect={"youtube_id": {"$missing": True}},
        clear=[],
        set={"youtube_id": "AbCdEfGhI_1"},
    )
    write_json(plan_path, plan)

    report = apply_source_repairs.execute(
        database_path, plan_path, apply=False,
    )

    assert report["changes"][0]["before"]["youtube_id"] == {"$missing": True}


def test_active_queue_claim_cannot_be_repaired(
    apply_source_repairs, tmp_path,
):
    database_path = tmp_path / "tracking-database.json"
    plan_path = tmp_path / "plan.json"
    database = base_database()
    database["talks"][0]["status"] = "reprocessing-inflight"
    database["talks"][0]["_queue_claim"] = {"state": "claimed"}
    write_json(database_path, database)
    write_json(plan_path, repair_plan())

    with pytest.raises(
        apply_source_repairs.SourceRepairError, match="active queue claim"
    ):
        apply_source_repairs.execute(database_path, plan_path, apply=False)


@pytest.mark.parametrize("mutation", [
    {"set": {"rhetoric_notes": "not a source repair"}},
    {"clear": ["rhetoric_notes"]},
    {"set": {"status": "processed"}},
])
def test_plan_rejects_out_of_scope_mutations(apply_source_repairs, mutation):
    plan = repair_plan(**mutation)

    with pytest.raises(apply_source_repairs.SourceRepairError):
        apply_source_repairs.validate_plan(plan)
