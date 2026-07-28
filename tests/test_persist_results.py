"""Tests for persist-results.py — deterministic Step 4 merge of subagent returns.

Regression coverage for #97: structured_data computed by subagents must land in
the tracking DB, with the declared queryable scalars promoted to the talk top level.
"""

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest


def _return(**overrides):
    ret = {
        "filename": "talk.md",
        "status": "processed",
        "processed_date": "2026-06-18",
        "transcript_source": "youtube_auto",
        "rhetoric_notes": "notes",
        "areas_for_improvement": "improve",
        "structured_data": {
            "delivery_language": "en",
            "co_presenter": False,
            "slide_count": 62,
            "audience_interaction_count": 3,
            "opening_type": "demo_cold_open",
            "closing_type": "summary_cta",
            "narrative_arc_type": "problem_diagnosis_solution",
            "slide_design_style": "comic_book",
            "illustration_style": "comic_book",
        },
        "verbatim_examples": {"jokes": ["j1"]},
        "pattern_observations": {
            "patterns_detected": [
                {"pattern_id": "narrative-arc", "confidence": "strong"},
                {"pattern_id": "bookends", "confidence": "moderate"},
            ],
            "antipatterns_detected": [{"pattern_id": "shortchanged", "confidence": "weak"}],
            "pattern_score": {"patterns_used": 8, "antipatterns_detected": 1, "score": 7},
        },
    }
    ret.update(overrides)
    return ret


def _talk(**overrides):
    talk = {
        "filename": "talk.md",
        "status": "pending",
        "structured_data": {},
        "verbatim_examples": {},
        "pattern_observations": {"pattern_ids": [], "antipattern_ids": [], "pattern_score": 0},
    }
    talk.update(overrides)
    return talk


def test_promotes_queryable_scalars(persist_results):
    talk = _talk()
    persist_results.merge_talk(talk, _return())
    assert talk["slide_count"] == 62
    assert talk["delivery_language"] == "en"
    assert talk["co_presenter"] is False  # boolean false is meaningful, not "empty"
    assert talk["opening_type"] == "demo_cold_open"
    assert talk["illustration_style"] == "comic_book"
    assert talk["pattern_score"] == 7
    assert talk["audience_interaction_count"] == 3


def test_full_structured_data_persisted(persist_results):
    talk = _talk()
    persist_results.merge_talk(talk, _return())
    # The whole block lands, not just the promoted scalars.
    assert talk["structured_data"]["narrative_arc_type"] == "problem_diagnosis_solution"
    assert talk["structured_data"]["slide_design_style"] == "comic_book"


def test_deep_merge_is_additive(persist_results):
    talk = _talk(structured_data={"video_extraction": {"unique_slides_count": 80}})
    ret = _return()
    ret["structured_data"]["video_extraction"] = {"hash_threshold_used": 14}
    persist_results.merge_talk(talk, ret)
    ve = talk["structured_data"]["video_extraction"]
    assert ve["unique_slides_count"] == 80  # earlier-run data preserved
    assert ve["hash_threshold_used"] == 14  # new data merged in


def test_empty_values_never_clobber(persist_results):
    talk = _talk(structured_data={"slide_count": 62})
    ret = _return()
    ret["structured_data"]["slide_count"] = None  # empty must not overwrite
    persist_results.merge_talk(talk, ret)
    assert talk["structured_data"]["slide_count"] == 62


def test_pattern_observations_normalized(persist_results):
    talk = _talk()
    persist_results.merge_talk(talk, _return())
    obs = talk["pattern_observations"]
    assert obs["pattern_ids"] == ["narrative-arc", "bookends"]
    assert obs["antipattern_ids"] == ["shortchanged"]
    assert obs["pattern_score"] == 7  # flattened from {"score": 7}
    assert len(obs["patterns_detected"]) == 2  # detailed arrays kept for Section 15


def test_scalar_result_fields_copied(persist_results):
    talk = _talk()
    persist_results.merge_talk(talk, _return())
    assert talk["status"] == "processed"
    assert talk["processed_date"] == "2026-06-18"
    assert talk["rhetoric_notes"] == "notes"
    assert talk["transcript_source"] == "youtube_auto"


def test_run_date_stamped_when_return_omits_processed_date(persist_results):
    """The reparse regression: a return that reports status but no date left the
    previous run's date in place, so the DB could not say which talks it covered."""
    ret = _return()
    del ret["processed_date"]
    talk = _talk(processed_date="2026-04-09")
    _, stamped, _ = persist_results.merge_talk(talk, ret, run_date="2026-07-26")
    assert talk["processed_date"] == "2026-07-26"
    assert stamped is True


def test_return_processed_date_wins_over_run_date(persist_results):
    talk = _talk()
    _, stamped, _ = persist_results.merge_talk(talk, _return(), run_date="2026-07-26")
    assert talk["processed_date"] == "2026-06-18"
    assert stamped is False


def test_empty_processed_date_is_stamped(persist_results):
    talk = _talk(processed_date="2026-04-09")
    _, stamped, _ = persist_results.merge_talk(talk, _return(processed_date=""),
                                            run_date="2026-07-26")
    assert talk["processed_date"] == "2026-07-26"
    assert stamped is True


def test_no_run_date_leaves_processed_date_untouched(persist_results):
    ret = _return()
    del ret["processed_date"]
    talk = _talk(processed_date="2026-04-09")
    _, stamped, _ = persist_results.merge_talk(talk, ret)
    assert talk["processed_date"] == "2026-04-09"
    assert stamped is False


def test_cli_run_date_pins_the_stamp(persist_results, tmp_path):
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    ret = _return()
    del ret["processed_date"]
    db.write_text(json.dumps({"talks": [_talk(processed_date="2026-04-09")]}))
    batch.write_text(json.dumps([ret]))
    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch),
         "--run-date", "2026-07-26"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(db.read_text())["talks"][0]["processed_date"] == "2026-07-26"
    report = json.loads(result.stdout)
    assert report["run_date"] == "2026-07-26"
    assert report["talks"][0]["stamped_processed_date"] is True


def test_cli_rejects_malformed_run_date(persist_results, tmp_path):
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    db.write_text(json.dumps({"talks": [_talk()]}))
    batch.write_text(json.dumps([_return()]))
    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch),
         "--run-date", "26-07-2026"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "YYYY-MM-DD" in result.stderr


def test_cli_writes_db_and_reports(persist_results, tmp_path):
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    db.write_text(json.dumps({"talks": [_talk()]}))
    batch.write_text(json.dumps([_return()]))
    script = persist_results.__file__
    result = subprocess.run(
        [sys.executable, script, str(db), str(batch)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    out = json.loads(db.read_text())["talks"][0]
    assert out["slide_count"] == 62
    # Structured JSON summary on stdout (not prose), per script-delegation.
    report = json.loads(result.stdout)
    assert report["persisted"] == 1
    assert report["talks"][0]["filename"] == "talk.md"
    assert "slide_count" in report["talks"][0]["promoted"]


def test_cli_fails_visibly_on_filename_mismatch(persist_results, tmp_path):
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    db.write_text(json.dumps({"talks": [_talk(filename="a.md")]}))
    batch.write_text(json.dumps([_return(filename="missing.md")]))
    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "no talk in DB matches" in result.stderr


def test_cli_missing_input_file_is_actionable(persist_results, tmp_path):
    batch = tmp_path / "batch-returns.json"
    batch.write_text(json.dumps([_return()]))
    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(tmp_path / "nope.json"), str(batch)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "tracking database file not found" in result.stderr
    assert "Traceback" not in result.stderr  # no raw traceback


def test_cli_malformed_json_is_actionable(persist_results, tmp_path):
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    db.write_text("{ not valid json ")
    batch.write_text(json.dumps([_return()]))
    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "not valid JSON" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_non_array_batch_is_actionable(persist_results, tmp_path):
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    db.write_text(json.dumps({"talks": [_talk()]}))
    batch.write_text(json.dumps({"filename": "talk.md"}))  # object, not array
    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "must be a JSON array" in result.stderr


def test_default_stamp_is_second_resolution(persist_results):
    """A day-granular stamp cannot order a talk against a fix that shipped the
    same day — during the 2026-07-26 reparse, 90 talks shared one date and the
    re-check backlog had to flag every one because ordering was unknowable.

    The clock is injected, not read: a test asserting a stamp produced from the
    live wall clock is non-deterministic by construction."""
    frozen = datetime(2026, 7, 27, 14, 3, 22, 456789, tzinfo=timezone.utc)
    assert persist_results.default_stamp(frozen) == "2026-07-27T14:03:22+00:00"


def test_default_stamp_normalizes_to_utc(persist_results):
    """Stamps written on machines in different zones must order against each other."""
    frozen = datetime(2026, 7, 27, 16, 3, 22, tzinfo=timezone(timedelta(hours=2)))
    assert persist_results.default_stamp(frozen) == "2026-07-27T14:03:22+00:00"


def test_explicit_offset_timestamp_is_normalized_to_utc(persist_results):
    assert persist_results.normalize_stamp(
        "2026-07-27T16:03:22.987654+02:00") == "2026-07-27T14:03:22+00:00"


def test_naive_timestamp_is_rejected_with_an_actionable_message(persist_results):
    """A naive timestamp cannot be ordered against one from another machine."""
    with pytest.raises(ValueError) as excinfo:
        persist_results.normalize_stamp("2026-07-27T14:03:22")
    assert "+00:00" in str(excinfo.value)


def test_cli_rejects_a_naive_timestamp(persist_results, tmp_path):
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    db.write_text(json.dumps({"talks": [_talk()]}))
    batch.write_text(json.dumps([_return()]))
    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch),
         "--run-date", "2026-07-27T14:03:22"],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "timezone-aware" in result.stderr


def test_explicit_date_only_stamp_is_still_accepted(persist_results, tmp_path):
    """Callers pinning a stamp for reproducibility keep working, and records
    written before this change stay readable."""
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    ret = _return()
    del ret["processed_date"]
    db.write_text(json.dumps({"talks": [_talk()]}))
    batch.write_text(json.dumps([ret]))
    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch),
         "--run-date", "2026-07-26"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(db.read_text())["talks"][0]["processed_date"] == "2026-07-26"


def test_explicit_timestamp_is_accepted(persist_results, tmp_path):
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    ret = _return()
    del ret["processed_date"]
    db.write_text(json.dumps({"talks": [_talk()]}))
    batch.write_text(json.dumps([ret]))
    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch),
         "--run-date", "2026-07-27T14:03:22+00:00"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(db.read_text())["talks"][0]["processed_date"].startswith("2026-07-27T14:03:22")


def test_bare_int_pattern_score_is_coerced_and_promoted(persist_results, tmp_path):
    """The bare int is not harmless: PROMOTE digs
    `pattern_observations.pattern_score.score`, `dig` returns None on an int, and
    the queryable top-level scalar is silently dropped — the exact missing-scalar
    defect this script exists to fix, reintroduced through the input shape.

    Roughly a third of returns arrive this way; the schema invites it.
    """
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    ret = _return()
    ret["pattern_observations"]["pattern_score"] = 1  # 2 patterns - 1 antipattern
    db.write_text(json.dumps({"talks": [_talk()]}))
    batch.write_text(json.dumps([ret]))
    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["talks"][0]["coerced_pattern_score"] is True
    assert "pattern_score" in payload["talks"][0]["promoted"]
    talk = json.loads(db.read_text())["talks"][0]
    assert talk["pattern_score"] == 1


def test_dict_pattern_score_is_not_reported_as_coerced(persist_results, tmp_path):
    """Guard the guard: the flag must distinguish the two shapes."""
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    db.write_text(json.dumps({"talks": [_talk()]}))
    batch.write_text(json.dumps([_return()]))
    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["talks"][0]["coerced_pattern_score"] is False
    assert "pattern_score" in payload["talks"][0]["promoted"]


def test_bare_int_contradicting_the_arrays_fails_loudly(persist_results, tmp_path):
    """A coerced value that disagrees with the arrays is a real inconsistency.

    Recomputing silently would launder it; the script refuses to guess which
    number is right.
    """
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    ret = _return()
    ret["pattern_observations"]["pattern_score"] = 42  # arrays say 2 - 1 = 1
    db.write_text(json.dumps({"talks": [_talk()]}))
    batch.write_text(json.dumps([ret]))
    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "Refusing to guess" in result.stderr
    assert "42" in result.stderr


@pytest.mark.parametrize("bad", [True, False, "19", ["19"]])
def test_non_numeric_pattern_score_never_reaches_the_db(persist_results, tmp_path, bad):
    """Assert the persisted OUTCOME, not the helper.

    An earlier version of this test called `canonicalize_pattern_score` directly
    and passed while `merge_talk` still persisted `pattern_score: True` — because
    `isinstance(True, int)` holds in Python, so a bool sailed through
    `normalize_pattern_observations`'s numeric branch. Testing the helper in
    isolation is exactly what hid the bug.
    """
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    ret = _return()
    ret["pattern_observations"]["pattern_score"] = bad
    db.write_text(json.dumps({"talks": [_talk()]}))
    batch.write_text(json.dumps([ret]))
    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1, f"{bad!r} was accepted: {result.stdout}"
    assert "pattern_score" in result.stderr
    stored = json.loads(db.read_text())["talks"][0]
    assert "pattern_score" not in stored, f"{bad!r} reached the DB as {stored.get('pattern_score')!r}"
