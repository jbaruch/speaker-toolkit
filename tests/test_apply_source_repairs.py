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
        "schema_version": 1,
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


def deck_database():
    """A markdown-authored talk in the state #318 describes: deck, no evidence."""
    database = base_database()
    database["talks"][0]["slide_source"] = "markdown"
    return database


def deck_repair(**overrides):
    repair = {
        "filename": "talk.md",
        "reason": "Slidev deck rendered to PDF and registered as slide evidence",
        "expect": {
            "slide_source": "markdown",
            "slides_local_path": {"$missing": True},
            "deck_source_path": {"$missing": True},
        },
        "set": {
            "slide_source": "pdf",
            "slides_local_path": "slides/talk.pdf",
            "deck_source_path": "/decks/spring-rag/slides.md",
        },
    }
    repair.update(overrides)
    return {"schema_version": 1, "repairs": [repair]}


def test_registering_a_render_keeps_the_deck_it_was_rendered_from(
    apply_source_repairs,
) -> None:
    """`slide_source` alone loses the provenance the moment the PDF is bound.

    Registering the render moves `slide_source` from "markdown" to "pdf", which
    is correct — the talk now has readable slide evidence. Before this field
    existed that rewrite also erased the only trace that the deck was authored
    in markdown, leaving nothing to re-render when the deck changed.
    """
    repaired, changes = apply_source_repairs.build_repaired_database(
        deck_database(),
        deck_repair()["repairs"],
    )

    talk = repaired["talks"][0]
    assert talk["slide_source"] == "pdf"
    assert talk["slides_local_path"] == "slides/talk.pdf"
    assert talk["deck_source_path"] == "/decks/spring-rag/slides.md"
    assert changes


@pytest.mark.parametrize(
    "path",
    [
        "/decks/spring-rag/slides.md",
        "decks/spring-rag/slides.md",
        "slides.MD",
        "deck.markdown",
    ],
)
def test_deck_source_path_accepts_absolute_and_vault_relative_decks(
    apply_source_repairs,
    path,
) -> None:
    """Decks live one git repo per talk, so no configured directory locates them.

    An absolute path is the ordinary case and a relative one resolves from the
    vault root, matching `pptx_path`. Both are accepted here; neither is
    checked for existence, because the deck's repo need not be in this
    checkout.
    """
    apply_source_repairs.validate_plan(
        deck_repair(
            set={
                "slide_source": "pdf",
                "slides_local_path": "slides/talk.pdf",
                "deck_source_path": path,
            }
        )
    )


@pytest.mark.parametrize(
    ("path", "message"),
    [
        ("deck.pptx", "must name a markdown deck source"),
        ("decks/spring-rag", "must name a deck file, not a directory"),
        ("decks//slides.md", "write it as 'decks/slides.md'"),
        ("./slides.md", "write it as 'slides.md'"),
        ("../slides.md", "must not contain a '..' segment"),
        (" slides.md", "write it as 'slides.md'"),
        ("decks\\slides.md", "must separate path segments with '/'"),
        ("", "must be a nonempty string"),
        (42, "must be a nonempty string"),
    ],
)
def test_deck_source_path_rejects_a_value_that_is_not_a_deck(
    apply_source_repairs,
    path,
    message,
) -> None:
    """Each rejection names the defect it found, not the first check to fire."""
    plan = deck_repair(
        set={
            "slide_source": "pdf",
            "slides_local_path": "slides/talk.pdf",
            "deck_source_path": path,
        }
    )

    with pytest.raises(apply_source_repairs.SourceRepairError, match=message):
        apply_source_repairs.validate_plan(plan)


def test_deck_source_path_can_be_cleared_when_a_deck_moves_away(
    apply_source_repairs,
) -> None:
    """A registered deck that is no longer the talk's source is unregisterable."""
    database = deck_database()
    database["talks"][0]["deck_source_path"] = "/decks/old/slides.md"
    repaired, changes = apply_source_repairs.build_repaired_database(
        database,
        [
            {
                "filename": "talk.md",
                "reason": "deck repo retired; the render is now the only source",
                "expect": {"deck_source_path": "/decks/old/slides.md"},
                "clear": ["deck_source_path"],
            }
        ],
    )

    assert "deck_source_path" not in repaired["talks"][0]
    assert changes
