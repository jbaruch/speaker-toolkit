"""Tests for flag-image-text-reprocess.py (issue #116 migration)."""

import json

import pytest


@pytest.fixture(scope="session")
def flag_script():
    import os

    from conftest import SCRIPTS_VI, _import_script

    return _import_script(
        os.path.join(SCRIPTS_VI, "flag-image-text-reprocess.py"),
        "flag_image_text_reprocess",
    )


# ── slide_is_unreadable: dual-accept over both extraction shapes ─────


def test_new_shape_low_confidence_is_unreadable(flag_script):
    assert flag_script.slide_is_unreadable(
        {"text_extraction_confidence": "low", "has_image": True},
    ) is True


def test_new_shape_high_confidence_is_readable(flag_script):
    assert flag_script.slide_is_unreadable(
        {"text_extraction_confidence": "high", "has_image": True},
    ) is False


def test_old_shape_image_without_text_frame_is_unreadable(flag_script):
    """The pre-fix signature: a picture present, no text-frame shape reached."""
    assert flag_script.slide_is_unreadable(
        {"has_image": True, "has_text_placeholder": False},
    ) is True


def test_old_shape_text_slide_is_readable(flag_script):
    assert flag_script.slide_is_unreadable(
        {"has_image": False, "has_text_placeholder": True},
    ) is False


def test_new_shape_wins_over_old_fields(flag_script):
    """A re-extracted deck is judged by its confidence, not the legacy fields."""
    assert flag_script.slide_is_unreadable({
        "text_extraction_confidence": "high",
        "has_image": True,
        "has_text_placeholder": False,
    }) is False


# ── flag: idempotency and selection ──────────────────────────────────


def _db():
    return {"talks": [
        {"filename": "a.md", "pptx_path": "deck-a.pptx", "status": "processed",
         "reprocess_reason": None},
        {"filename": "b.md", "pptx_path": "deck-b.pptx", "status": "processed",
         "reprocess_reason": None},
    ]}


def test_flag_marks_only_affected_talks(flag_script):
    db = _db()
    changed = flag_script.flag(db, {"deck-a.pptx": 3})
    assert [c["filename"] for c in changed] == ["a.md"]
    assert db["talks"][0]["status"] == "needs-reprocessing"
    assert db["talks"][0]["reprocess_reason"] == "image_text_extraction_fixed"
    # Untouched talk keeps its state
    assert db["talks"][1]["status"] == "processed"
    assert db["talks"][1]["reprocess_reason"] is None


def test_flag_is_idempotent(flag_script):
    """Re-running must not re-flag what it already flagged."""
    db = _db()
    flag_script.flag(db, {"deck-a.pptx": 3})
    changed_again = flag_script.flag(db, {"deck-a.pptx": 3})
    assert changed_again == []


def test_flag_overrides_a_different_reprocess_reason(flag_script):
    """A talk queued for another migration is re-flagged for this one.

    This migration is the more recent claim on the talk; both reasons lead to
    the same reparse, so the newer one wins rather than being skipped.
    """
    db = _db()
    db["talks"][0]["reprocess_reason"] = "pattern_scoring_added"
    changed = flag_script.flag(db, {"deck-a.pptx": 1})
    assert len(changed) == 1
    assert db["talks"][0]["reprocess_reason"] == "image_text_extraction_fixed"


# ── affected_decks ───────────────────────────────────────────────────


def test_affected_decks_counts_unreadable_slides(flag_script):
    extraction = [{
        "pptx_path": "deck-a.pptx",
        "per_slide_visual": [
            {"text_extraction_confidence": "low"},
            {"text_extraction_confidence": "low"},
            {"text_extraction_confidence": "high"},
        ],
    }]
    assert flag_script.affected_decks(extraction) == {"deck-a.pptx": 2}


def test_affected_decks_omits_clean_decks(flag_script):
    extraction = [{
        "pptx_path": "clean.pptx",
        "per_slide_visual": [{"text_extraction_confidence": "high"}],
    }]
    assert flag_script.affected_decks(extraction) == {}


# ── CLI ──────────────────────────────────────────────────────────────


def test_cli_dry_run_does_not_write(flag_script, tmp_path, capsys):
    db_path = tmp_path / "db.json"
    db_path.write_text(json.dumps(_db()), encoding="utf-8")
    ex_path = tmp_path / "ex.json"
    ex_path.write_text(json.dumps([{
        "pptx_path": "deck-a.pptx",
        "per_slide_visual": [{"text_extraction_confidence": "low"}],
    }]), encoding="utf-8")
    before = db_path.read_text(encoding="utf-8")

    rc = flag_script.main(["flag", str(db_path), str(ex_path)])
    assert rc == 0
    assert db_path.read_text(encoding="utf-8") == before  # untouched
    out = json.loads(capsys.readouterr().out)
    assert out["talks_flagged"] == 1
    assert out["applied"] is False


def test_cli_apply_writes(flag_script, tmp_path, capsys):
    db_path = tmp_path / "db.json"
    db_path.write_text(json.dumps(_db()), encoding="utf-8")
    ex_path = tmp_path / "ex.json"
    ex_path.write_text(json.dumps([{
        "pptx_path": "deck-a.pptx",
        "per_slide_visual": [{"text_extraction_confidence": "low"}],
    }]), encoding="utf-8")

    rc = flag_script.main(["flag", str(db_path), str(ex_path), "--apply"])
    assert rc == 0
    written = json.loads(db_path.read_text(encoding="utf-8"))
    assert written["talks"][0]["status"] == "needs-reprocessing"
    assert json.loads(capsys.readouterr().out)["applied"] is True


def test_cli_missing_file_exits_nonzero(flag_script, tmp_path, capsys):
    rc = flag_script.main(["flag", str(tmp_path / "nope.json"), str(tmp_path)])
    assert rc == 1
    assert "not a file" in capsys.readouterr().err


# ── extraction output shapes (single-file vs directory) ──────────────


def test_affected_decks_reads_single_file_output(flag_script):
    """`pptx-extraction.py <deck.pptx>` emits one bare deck dict, not a list.

    Falling through to [] there reported zero affected talks for exactly the
    decks this migration exists to catch.
    """
    single = {
        "pptx_path": "deck-a.pptx",
        "slide_count": 2,
        "per_slide_visual": [
            {"text_extraction_confidence": "low"},
            {"text_extraction_confidence": "high"},
        ],
    }
    assert flag_script.affected_decks(single) == {"deck-a.pptx": 1}


def test_affected_decks_reads_wrapper_shapes(flag_script):
    """Directory mode wraps decks under `decks` / `results`."""
    deck = {
        "pptx_path": "deck-a.pptx",
        "per_slide_visual": [{"text_extraction_confidence": "low"}],
    }
    assert flag_script.affected_decks({"decks": [deck]}) == {"deck-a.pptx": 1}
    assert flag_script.affected_decks({"results": [deck]}) == {"deck-a.pptx": 1}
    assert flag_script.affected_decks([deck]) == {"deck-a.pptx": 1}


def test_cli_flags_from_single_file_extraction(flag_script, tmp_path, capsys):
    """End-to-end on the real single-file shape."""
    db_path = tmp_path / "db.json"
    db_path.write_text(json.dumps(_db()), encoding="utf-8")
    ex_path = tmp_path / "ex.json"
    ex_path.write_text(json.dumps({
        "pptx_path": "deck-a.pptx",
        "slide_count": 1,
        "per_slide_visual": [{"text_extraction_confidence": "low"}],
    }), encoding="utf-8")

    rc = flag_script.main(["flag", str(db_path), str(ex_path), "--apply"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["talks_flagged"] == 1
    written = json.loads(db_path.read_text(encoding="utf-8"))
    assert written["talks"][0]["status"] == "needs-reprocessing"
