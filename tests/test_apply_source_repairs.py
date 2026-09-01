"""Tests for guarded, auditable vault source repairs."""

import hashlib
import json
from pathlib import Path

import pytest

from conftest import current_tracking_config


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def base_database():
    return {
        "schema_version": 2,
        "config": current_tracking_config(),
        "talks": [
            {
                "schema_version": 5,
                "filename": "talk.md",
                "status": "processed",
                "video_url": "https://youtu.be/AbCdEfGhI_1",
                "youtube_id": "AbCdEfGhI_1",
                "transcript_source": "youtube_auto",
            }
        ],
        "pptx_catalog": [],
        "qr_codes": [],
        "resources": [],
        "thumbnails": [],
        "confirmed_intents": [],
        "improvement_goals": [],
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
    apply_source_repairs,
    tmp_path,
):
    database_path = tmp_path / "tracking-database.json"
    plan_path = tmp_path / "plan.json"
    database = base_database()
    write_json(database_path, database)
    write_json(plan_path, repair_plan())
    before = database_path.read_bytes()

    report = apply_source_repairs.execute(
        database_path,
        plan_path,
        apply=False,
    )

    assert report["schema_version"] == 2
    assert report["mode"] == "dry-run"
    assert report["repair_count"] == 1
    assert report["backup"] is None
    assert report["input_sha256"] == hashlib.sha256(before).hexdigest()
    assert report["output_sha256"] != report["input_sha256"]
    assert report["database_written"] is False
    assert report["durability_state"] == "dry_run"
    assert report["warnings"] == []
    assert database_path.read_bytes() == before


def test_legacy_database_rejects_repair_dry_run_without_writing(
    apply_source_repairs,
    tmp_path,
):
    database_path = tmp_path / "tracking-database.json"
    plan_path = tmp_path / "plan.json"
    database = base_database()
    database.pop("schema_version")
    database["config"].pop("schema_version")
    database["talks"][0].pop("schema_version")
    write_json(database_path, database)
    write_json(plan_path, repair_plan())
    before = database_path.read_bytes()

    with pytest.raises(
        apply_source_repairs.SourceRepairError,
        match="migrate-tracking-database.py",
    ):
        apply_source_repairs.execute(database_path, plan_path, apply=False)

    assert database_path.read_bytes() == before


def test_repair_cannot_create_unversioned_source_rejection(
    apply_source_repairs,
    tmp_path,
):
    database_path = tmp_path / "tracking-database.json"
    plan_path = tmp_path / "plan.json"
    write_json(database_path, base_database())
    plan = repair_plan()
    plan["repairs"][0]["expect"]["source_rejections"] = {"$missing": True}
    plan["repairs"][0]["set"]["source_rejections"] = [
        {
            "source_type": "video",
            "url": "https://youtu.be/AbCdEfGhI_1",
            "reason": "wrong_delivery",
            "evidence": "provider metadata identifies another delivery",
            "verified_at": "2026-08-01T12:00:00+00:00",
        }
    ]
    write_json(plan_path, plan)
    before = database_path.read_bytes()

    with pytest.raises(
        apply_source_repairs.SourceRepairError,
        match="source_rejections_schema_version_missing",
    ):
        apply_source_repairs.execute(database_path, plan_path, apply=False)

    assert database_path.read_bytes() == before


def test_apply_writes_atomically_and_creates_exact_backup(
    apply_source_repairs,
    tmp_path,
):
    database_path = tmp_path / "tracking-database.json"
    plan_path = tmp_path / "plan.json"
    backup_dir = tmp_path / "backups"
    write_json(database_path, base_database())
    write_json(plan_path, repair_plan())
    before = database_path.read_bytes()

    report = apply_source_repairs.execute(
        database_path,
        plan_path,
        apply=True,
        backup_dir=backup_dir,
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
    assert report["schema_version"] == 2
    assert report["input_sha256"] == hashlib.sha256(before).hexdigest()
    assert (
        report["output_sha256"]
        == hashlib.sha256(database_path.read_bytes()).hexdigest()
    )
    assert report["database_written"] is True
    assert report["durability_state"] == "durable"
    assert report["input_sha256"] in Path(report["backup"]).name
    assert next(backup_dir.iterdir()).read_bytes() == before


def test_idempotent_apply_preserves_exact_bytes_inode_and_skips_backup(
    apply_source_repairs,
    tmp_path,
):
    database_path = tmp_path / "tracking-database.json"
    plan_path = tmp_path / "plan.json"
    backup_dir = tmp_path / "backups"
    raw = json.dumps(base_database(), separators=(",", ":")).encode("utf-8") + b"\n"
    database_path.write_bytes(raw)
    inode = database_path.stat().st_ino
    write_json(
        plan_path,
        {
            "schema_version": 1,
            "repairs": [
                {
                    "filename": "talk.md",
                    "reason": "idempotent replay",
                    "expect": {"transcript_source": "youtube_auto"},
                    "set": {"transcript_source": "youtube_auto"},
                }
            ],
        },
    )

    report = apply_source_repairs.execute(
        database_path,
        plan_path,
        apply=True,
        backup_dir=backup_dir,
    )

    assert report["repair_count"] == 0
    assert report["database_written"] is False
    assert report["durability_state"] == "unchanged"
    assert report["input_sha256"] == report["output_sha256"]
    assert report["backup"] is None
    assert database_path.read_bytes() == raw
    assert database_path.stat().st_ino == inode
    assert not backup_dir.exists()


def test_atomic_write_cleans_stage_and_propagates_interrupt(
    apply_source_repairs,
    tracking_database_io,
    tmp_path,
    monkeypatch,
):
    target = tmp_path / "tracking-database.json"
    target.write_text('{"value": "old"}\n', encoding="utf-8")

    def interrupt(_source, _target):
        raise KeyboardInterrupt

    monkeypatch.setattr(tracking_database_io.os, "replace", interrupt)

    with pytest.raises(KeyboardInterrupt):
        apply_source_repairs.atomic_write(target, '{"value": "new"}\n')

    assert target.read_text(encoding="utf-8") == '{"value": "old"}\n'
    assert {path.name for path in tmp_path.iterdir()} == {
        target.name,
        ".tracking-database.json.lock",
    }


def test_expectation_mismatch_aborts_whole_plan_without_backup(
    apply_source_repairs,
    tmp_path,
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
            database_path,
            plan_path,
            apply=True,
            backup_dir=backup_dir,
        )

    assert database_path.read_bytes() == before
    assert not backup_dir.exists()


def test_missing_marker_distinguishes_absent_from_null(
    apply_source_repairs,
    tmp_path,
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
        database_path,
        plan_path,
        apply=False,
    )

    assert report["changes"][0]["before"]["youtube_id"] == {"$missing": True}


def test_active_queue_claim_cannot_be_repaired(
    apply_source_repairs,
    tmp_path,
):
    database_path = tmp_path / "tracking-database.json"
    plan_path = tmp_path / "plan.json"
    database = base_database()
    database["talks"][0]["status"] = "reprocessing-inflight"
    database["talks"][0]["reprocess_generation"] = 1
    database["talks"][0]["_queue_claim"] = {
        "schema_version": 1,
        "run_id": "repair-blocked",
        "batch_id": "1",
        "claimed_at": "2026-08-01T12:00:00+00:00",
        "previous_status": "needs-reprocessing",
        "reprocess_generation": 1,
        "state": "claimed",
    }
    write_json(database_path, database)
    write_json(plan_path, repair_plan())

    with pytest.raises(
        apply_source_repairs.SourceRepairError, match="active queue claim"
    ):
        apply_source_repairs.execute(database_path, plan_path, apply=False)


@pytest.mark.parametrize(
    "mutation",
    [
        {"set": {"rhetoric_notes": "not a source repair"}},
        {"clear": ["rhetoric_notes"]},
        {"set": {"status": "processed"}},
    ],
)
def test_plan_rejects_out_of_scope_mutations(apply_source_repairs, mutation):
    plan = repair_plan(**mutation)

    with pytest.raises(apply_source_repairs.SourceRepairError):
        apply_source_repairs.validate_plan(plan)


def test_source_repair_schema_and_expectations_are_type_sensitive(
    apply_source_repairs,
) -> None:
    with pytest.raises(
        apply_source_repairs.SourceRepairError,
        match="schema_version must be 1",
    ):
        apply_source_repairs.validate_plan(
            {"schema_version": True, "repairs": [repair_plan()["repairs"][0]]}
        )

    database = base_database()
    database["talks"][0]["source_identity"] = {"verified": True}
    repair = {
        "filename": "talk.md",
        "reason": "type-sensitive expectation",
        "expect": {"source_identity": {"verified": 1}},
        "set": {"source_identity": {"verified": False}},
    }
    with pytest.raises(
        apply_source_repairs.SourceRepairError,
        match="preconditions failed",
    ):
        apply_source_repairs.build_repaired_database(database, [repair])


def test_source_repair_type_change_is_not_a_noop(apply_source_repairs) -> None:
    database = base_database()
    database["talks"][0]["source_identity"] = {"verified": True}
    repaired, changes = apply_source_repairs.build_repaired_database(
        database,
        [
            {
                "filename": "talk.md",
                "reason": "replace boolean with numeric evidence",
                "expect": {"source_identity": {"verified": True}},
                "set": {"source_identity": {"verified": 1}},
            }
        ],
    )

    assert changes
    assert type(repaired["talks"][0]["source_identity"]["verified"]) is int


def test_malformed_missing_marker_is_an_exact_object_not_absence(
    apply_source_repairs,
) -> None:
    database = base_database()
    repair = {
        "filename": "talk.md",
        "reason": "malformed marker must not bypass absence check",
        "expect": {"source_identity": {"$missing": 1}},
        "set": {"source_identity": {}},
    }

    with pytest.raises(
        apply_source_repairs.SourceRepairError,
        match="preconditions failed",
    ):
        apply_source_repairs.build_repaired_database(database, [repair])


def test_the_documented_render_registration_plan_applies(
    apply_source_repairs,
) -> None:
    """The register-the-render plan in references/markdown-decks.md, verbatim.

    `validate_plan` refuses a repair that changes a field it did not declare in
    `expect`, so the page's earlier recipe — which set `status` and
    `reprocess_reason` while expecting neither — could never be applied by the
    reader following it.
    """
    database = base_database()
    database["talks"][0]["slide_source"] = "markdown"
    database["talks"][0]["status"] = "processed_partial"
    plan = {
        "schema_version": 1,
        "repairs": [
            {
                "filename": "talk.md",
                "reason": "Slidev deck rendered to PDF and registered as evidence",
                "expect": {
                    "slides_local_path": {"$missing": True},
                    "slide_source": "markdown",
                    "status": "processed_partial",
                    "reprocess_reason": {"$missing": True},
                },
                "set": {
                    "slides_local_path": "slides/talk.pdf",
                    "slide_source": "pdf",
                    "status": "needs-reprocessing",
                    "reprocess_reason": "source_added",
                },
            }
        ],
    }

    repairs = apply_source_repairs.validate_plan(plan)
    repaired, changes = apply_source_repairs.build_repaired_database(database, repairs)

    talk = repaired["talks"][0]
    assert talk["slide_source"] == "pdf"
    assert talk["slides_local_path"] == "slides/talk.pdf"
    assert talk["status"] == "needs-reprocessing"
    assert changes


def preserved_media_repair(**overrides):
    """The documented registration plan for a preserved local recording."""
    repair = {
        "filename": "talk.md",
        "reason": "YouTube source deleted upstream; preserved recording is the media",
        "expect": {
            "video_local_path": {"$missing": True},
            "status": "processed",
            "reprocess_reason": {"$missing": True},
        },
        "set": {
            "video_local_path": "slides-rebuild/AbCdEfGhI_1/AbCdEfGhI_1.mp4",
            "status": "needs-reprocessing",
            "reprocess_reason": "source_added",
        },
    }
    repair.update(overrides)
    return {"schema_version": 1, "repairs": [repair]}


def test_preserved_local_media_can_be_registered(apply_source_repairs) -> None:
    """Register a preserved recording whose remote source is gone.

    `pattern_evidence._local_video_binding` trusts local media only through a
    stored `structured_data.video_extraction` manifest or a `video_local_path` /
    `video_path` on the talk. The manifest reaches the talk through the merge,
    and a transcript Whispered from that media fails its receipt owner check
    until something marks the file as the talk's. Registering the path is the
    owner's way in.
    """
    database = base_database()
    database["talks"][0]["transcript_source"] = "whisper"

    repairs = apply_source_repairs.validate_plan(preserved_media_repair())
    repaired, changes = apply_source_repairs.build_repaired_database(database, repairs)

    talk = repaired["talks"][0]
    assert talk["video_local_path"] == "slides-rebuild/AbCdEfGhI_1/AbCdEfGhI_1.mp4"
    assert talk["status"] == "needs-reprocessing"
    assert talk["reprocess_reason"] == "source_added"
    assert changes


def test_registering_a_source_without_the_requeue_is_refused(
    apply_source_repairs,
) -> None:
    """A source that appears after the analysis ran must requeue the talk.

    The stored analysis was scored without it, so leaving the talk `processed`
    publishes a score that silently ignores evidence the vault now holds.
    """
    database = base_database()
    plan = preserved_media_repair(
        expect={
            "video_local_path": {"$missing": True},
            "transcript_source": "youtube_auto",
        },
        set={
            "video_local_path": "slides-rebuild/AbCdEfGhI_1/AbCdEfGhI_1.mp4",
            "transcript_source": "whisper",
        },
    )
    repairs = apply_source_repairs.validate_plan(plan)

    with pytest.raises(
        apply_source_repairs.SourceRepairError, match="must also set status"
    ):
        apply_source_repairs.build_repaired_database(database, repairs)


def test_registering_a_source_on_a_queued_talk_needs_no_requeue(
    apply_source_repairs,
) -> None:
    """A talk already awaiting reprocessing has nothing to invalidate."""
    database = base_database()
    database["talks"][0]["status"] = "pending"
    plan = preserved_media_repair(
        expect={
            "video_local_path": {"$missing": True},
            "transcript_source": "youtube_auto",
        },
        set={
            "video_local_path": "slides-rebuild/AbCdEfGhI_1/AbCdEfGhI_1.mp4",
            "transcript_source": "whisper",
        },
    )
    repairs = apply_source_repairs.validate_plan(plan)
    repaired, _ = apply_source_repairs.build_repaired_database(database, repairs)

    assert repaired["talks"][0]["status"] == "pending"


def test_correcting_an_existing_source_is_not_a_registration(
    apply_source_repairs,
) -> None:
    """Replacing a recorded locator is an identity correction, not an addition.

    The requeue rule fires on a source the analysis could not have seen. A
    locator that was already there keeps its own repair flow.
    """
    database = base_database()
    plan = {
        "schema_version": 1,
        "repairs": [
            {
                "filename": "talk.md",
                "reason": "provider metadata identifies the correct recording",
                "expect": {"video_url": "https://youtu.be/AbCdEfGhI_1"},
                "set": {"video_url": "https://youtu.be/AbCdEfGhI_2"},
            }
        ],
    }
    repairs = apply_source_repairs.validate_plan(plan)
    repaired, _ = apply_source_repairs.build_repaired_database(database, repairs)

    assert repaired["talks"][0]["video_url"] == "https://youtu.be/AbCdEfGhI_2"
    assert repaired["talks"][0]["status"] == "processed"


def test_legacy_video_path_alias_can_be_cleared(apply_source_repairs) -> None:
    """`video_path` is the legacy alias of the same locator and clears the same way."""
    database = base_database()
    database["talks"][0]["video_path"] = "slides-rebuild/AbCdEfGhI_1/AbCdEfGhI_1.mp4"
    plan = {
        "schema_version": 1,
        "repairs": [
            {
                "filename": "talk.md",
                "reason": "preserved recording was removed from the vault",
                "expect": {
                    "video_path": "slides-rebuild/AbCdEfGhI_1/AbCdEfGhI_1.mp4",
                },
                "clear": ["video_path"],
            }
        ],
    }

    repairs = apply_source_repairs.validate_plan(plan)
    repaired, _ = apply_source_repairs.build_repaired_database(database, repairs)

    assert "video_path" not in repaired["talks"][0]


def test_backfilling_youtube_id_is_not_a_source_registration(
    apply_source_repairs,
) -> None:
    """`youtube_id` identifies a `video_url` the talk already carries.

    Recording the derived id adds no evidence the stored analysis lacked, so it
    does not drag a requeue behind it.
    """
    database = base_database()
    database["talks"][0].pop("youtube_id")
    plan = {
        "schema_version": 1,
        "repairs": [
            {
                "filename": "talk.md",
                "reason": "backfill the identifier of the recorded video_url",
                "expect": {"youtube_id": {"$missing": True}},
                "set": {"youtube_id": "AbCdEfGhI_1"},
            }
        ],
    }
    repairs = apply_source_repairs.validate_plan(plan)
    repaired, _ = apply_source_repairs.build_repaired_database(database, repairs)

    assert repaired["talks"][0]["youtube_id"] == "AbCdEfGhI_1"
    assert repaired["talks"][0]["status"] == "processed"
