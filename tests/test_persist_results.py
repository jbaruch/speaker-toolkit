"""Tests for persist-results.py — deterministic Step 4 merge of subagent returns.

Regression coverage for #97: structured_data computed by subagents must land in
the tracking DB, with the declared queryable scalars promoted to the talk top level.
"""

import copy
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest


def _return(**overrides):
    ret = {
        "filename": "talk.md",
        "queue_claim": {
            "run_id": "reparse",
            "batch_id": "25",
            "reprocess_generation": 1,
        },
        "status": "processed",
        "processed_date": "2026-06-18",
        "transcript_source": "youtube_auto",
        "slide_source": "pptx",
        "rhetoric_notes": "notes",
        "areas_for_improvement": "improve",
        "adherence_assessment": "above baseline",
        "new_patterns": "",
        "summary_updates": "",
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
                {"pattern_id": "narrative-arc", "confidence": "strong",
                 "evidence_source": "transcript",
                 "evidence": "The talk follows a four-act argument."},
                {"pattern_id": "bookends", "confidence": "moderate",
                 "evidence_source": "static_slides",
                 "evidence": "Repeated dividers mark section boundaries."},
            ],
            "antipatterns_detected": [
                {"pattern_id": "shortchanged", "confidence": "weak",
                 "evidence_source": "transcript",
                 "evidence": "The close is compressed."},
            ],
            "evidence_sources": ["transcript", "native_deck", "static_slides",
                                 "source_comparison"],
            "not_evaluable": [],
            "pattern_score": {"patterns_used": 2, "antipatterns_detected": 1, "score": 1},
        },
        "catalog_feedback": {
            "unmatched_observations": [],
            "confusable_pairs": [],
            "definition_problems": [],
            "scoring_problems": [],
            "tensions": [],
        },
    }
    ret.update(overrides)
    return ret


def _talk(**overrides):
    talk = {
        "filename": "talk.md",
        "status": "reprocessing-inflight",
        "reprocess_generation": 1,
        "video_url": "https://youtu.be/AbCdEfGhI_1",
        "youtube_id": "AbCdEfGhI_1",
        "pptx_path": "Conference/Talk.pptx",
        "slides_url": "https://drive.google.com/file/d/slides-id/view",
        "_queue_claim": {
            "schema_version": 1,
            "run_id": "reparse",
            "batch_id": "25",
            "claimed_at": "2026-07-31T18:00:00+00:00",
            "previous_status": "needs-reprocessing",
            "reprocess_generation": 1,
            "state": "claimed",
        },
        "structured_data": {},
        "verbatim_examples": {},
        "pattern_observations": {"pattern_ids": [], "antipattern_ids": [], "pattern_score": 0},
    }
    talk.update(overrides)
    return talk


def _skipped_return(**overrides):
    ret = {
        "filename": "talk.md",
        "queue_claim": {
            "run_id": "reparse",
            "batch_id": "25",
            "reprocess_generation": 1,
        },
        "status": "skipped_no_sources",
    }
    ret.update(overrides)
    return ret


def _complete_unavailable_source_gates(return_validation, ret):
    available = set(ret["pattern_observations"]["evidence_sources"])
    catalog = return_validation.load_catalog()
    ret["pattern_observations"]["not_evaluable"] = [{
        "pattern_id": pattern_id,
        "evidence_source": sorted(available)[0],
        "reason": "The inspected fixture sources cannot evaluate this pattern.",
    } for pattern_id, entry in sorted(catalog.entries.items())
        if entry.observable and entry.evaluable_from is not None and
        not return_validation.qualifying_evidence_groups(
            entry.evaluable_from, available)]
    return ret


def test_promotes_queryable_scalars(persist_results):
    talk = _talk()
    persist_results.merge_talk(talk, _return())
    assert talk["slide_count"] == 62
    assert talk["delivery_language"] == "en"
    assert talk["co_presenter"] is False  # boolean false is meaningful, not "empty"
    assert talk["opening_type"] == "demo_cold_open"
    assert talk["illustration_style"] == "comic_book"
    assert talk["pattern_score"] == 1
    assert talk["audience_interaction_count"] == 3


def test_full_structured_data_persisted(persist_results):
    talk = _talk()
    persist_results.merge_talk(talk, _return())
    # The whole block lands, not just the promoted scalars.
    assert talk["structured_data"]["narrative_arc_type"] == "problem_diagnosis_solution"
    assert talk["structured_data"]["slide_design_style"] == "comic_book"


def test_skipped_merge_cannot_mutate_prior_analysis_even_without_validator(
        persist_results):
    talk = _talk(
        processed_date="2026-06-18",
        transcript_source="youtube_auto",
        slide_source="pptx",
        rhetoric_notes="trusted prior analysis",
        structured_data={"slide_count": 42},
        verbatim_examples={"jokes": ["kept"]},
        video_url=None,
        pptx_path=None,
        slides_url=None,
    )
    malicious = _return(
        status="skipped_no_sources",
        rhetoric_notes=["wrong type"],
        slide_source="not-an-enum",
        structured_data={"video_extraction": {"schema_version": "invalid"}},
        clear_fields=["structured_data.slide_count"],
    )

    persist_results.merge_talk(talk, malicious, run_date="2026-07-31")

    assert talk["status"] == "skipped_no_sources"
    assert talk["rhetoric_notes"] == "trusted prior analysis"
    assert talk["structured_data"] == {"slide_count": 42}
    assert talk["verbatim_examples"] == {"jokes": ["kept"]}
    assert talk["processed_date"] == "2026-06-18"
    assert talk["transcript_source"] == "youtube_auto"
    assert talk["slide_source"] == "pptx"


def test_deep_merge_is_additive(persist_results):
    talk = _talk(structured_data={"act_structure": {"act_count": 4}})
    ret = _return()
    ret["structured_data"]["act_structure"] = {"named_acts": True}
    persist_results.merge_talk(talk, ret)
    acts = talk["structured_data"]["act_structure"]
    assert acts["act_count"] == 4  # earlier-run data preserved
    assert acts["named_acts"] is True  # new data merged in


def test_video_extraction_manifest_replaces_legacy_manifest_atomically(
        persist_results):
    talk = _talk(structured_data={
        "video_extraction": {
            "schema_version": 2,
            "output_pdf": "/legacy/full-frame.pdf",
            "unique_slides_count": 80,
        },
    })
    ret = _return()
    ret["structured_data"]["video_extraction"] = {
        "schema_version": 3,
        "artifacts": [{"artifact_scope": "slide_region"}],
    }
    persist_results.merge_talk(talk, ret)
    assert talk["structured_data"]["video_extraction"] == {
        "schema_version": 3,
        "artifacts": [{"artifact_scope": "slide_region"}],
    }


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
    assert obs["pattern_score"] == 1  # flattened from {"score": 1}
    assert len(obs["patterns_detected"]) == 2  # detailed arrays kept for Section 15
    assert obs["evidence_sources"] == [
        "transcript", "native_deck", "static_slides", "source_comparison"]
    assert obs["not_evaluable"] == []
    assert obs["not_evaluable_ids"] == []


def test_not_evaluable_patterns_are_persisted_but_never_scored(
        persist_results, tmp_path):
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    ret = _return()
    ret["pattern_observations"]["not_evaluable"] = [{
        "pattern_id": "composite-animation",
        "evidence_source": "static_slides",
        "reason": "No animation timing survives in the rendered pages.",
    }]
    db.write_text(json.dumps({"talks": [_talk()]}))
    batch.write_text(json.dumps([ret]))
    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    obs = json.loads(db.read_text())["talks"][0]["pattern_observations"]
    assert obs["not_evaluable_ids"] == ["composite-animation"]
    assert obs["pattern_score"] == 1


def test_scalar_result_fields_copied(persist_results):
    talk = _talk()
    persist_results.merge_talk(
        talk, _return(slides_local_path="slides/source.pdf"))
    assert talk["status"] == "processed"
    assert talk["processed_date"] == "2026-06-18"
    assert talk["rhetoric_notes"] == "notes"
    assert talk["transcript_source"] == "youtube_auto"
    assert talk["slides_local_path"] == "slides/source.pdf"


def test_run_date_stamped_when_return_omits_processed_date(persist_results):
    """The reparse regression: a return that reports status but no date left the
    previous run's date in place, so the DB could not say which talks it covered."""
    ret = _return()
    del ret["processed_date"]
    talk = _talk(processed_date="2026-04-09")
    _, stamped, _, _ = persist_results.merge_talk(talk, ret, run_date="2026-07-26")
    assert talk["processed_date"] == "2026-07-26"
    assert stamped is True


def test_batch_run_date_wins_over_legacy_return_date(persist_results):
    talk = _talk()
    _, stamped, _, _ = persist_results.merge_talk(
        talk, _return(), run_date="2026-07-26")
    assert talk["processed_date"] == "2026-07-26"
    assert stamped is True


def test_empty_processed_date_is_stamped(persist_results):
    talk = _talk(processed_date="2026-04-09")
    _, stamped, _, _ = persist_results.merge_talk(
        talk, _return(processed_date=""), run_date="2026-07-26")
    assert talk["processed_date"] == "2026-07-26"
    assert stamped is True


def test_no_run_date_leaves_processed_date_untouched(persist_results):
    ret = _return()
    del ret["processed_date"]
    talk = _talk(processed_date="2026-04-09")
    _, stamped, _, _ = persist_results.merge_talk(talk, ret)
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


def test_cli_batch_timestamp_overrides_date_only_return_stamp_everywhere(
        persist_results, tmp_path):
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    authoritative = "2026-07-27T14:03:22+00:00"
    db.write_text(json.dumps({"talks": [_talk(processed_date="2026-04-09")]}))
    batch.write_text(json.dumps([_return(processed_date="2026-07-27")]))

    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch),
         "--run-date", authoritative],
        capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr
    stored = json.loads(db.read_text())["talks"][0]
    assert stored["processed_date"] == authoritative
    assert stored["_queue_claim"]["released_at"] == authoritative
    assert json.loads(result.stdout)["talks"][0]["stamped_processed_date"] is True


def test_cli_rejects_conflicting_explicit_return_timestamp_before_write(
        persist_results, tmp_path):
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    original = {"talks": [_talk(processed_date="2026-04-09")]}
    db.write_text(json.dumps(original))
    batch.write_text(json.dumps([
        _return(processed_date="2026-07-27T08:00:00+00:00")]))

    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch),
         "--run-date", "2026-07-27T14:03:22+00:00"],
        capture_output=True, text=True,
    )

    assert result.returncode == 1
    assert "explicit timestamp" in result.stderr
    assert "conflicts with authoritative batch run_date" in result.stderr
    assert json.loads(db.read_text()) == original


def test_matching_explicit_return_timestamp_is_accepted_and_batch_stamped(
        persist_results):
    talk = _talk(processed_date="2026-04-09")
    _, stamped, _, _ = persist_results.merge_talk(
        talk,
        _return(processed_date="2026-07-27T16:03:22.987+02:00"),
        run_date="2026-07-27T14:03:22+00:00",
    )
    assert talk["processed_date"] == "2026-07-27T14:03:22+00:00"
    assert stamped is True


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
    assert "must exactly match" in result.stderr
    assert "unexpected ['missing.md']" in result.stderr


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


def test_return_processed_timestamp_is_persisted_in_canonical_utc(persist_results):
    talk = _talk()

    persist_results.merge_talk(
        talk,
        _return(processed_date="2026-07-27T16:03:22.987654+02:00"),
    )

    assert talk["processed_date"] == "2026-07-27T14:03:22+00:00"


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
    assert "2 patterns minus 1 antipatterns is 1" in result.stderr
    assert "42" in result.stderr


@pytest.mark.parametrize("bad", [True, False, "19", ["19"], 1.5, 1.0])
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


@pytest.mark.parametrize("inner", [True, False, "19", ["19"], 1.5, 1.0])
def test_invalid_score_inside_the_declared_dict_is_rejected(
        persist_results, tmp_path, inner):
    """The dict is the declared shape, but its `score` is what PROMOTE writes.

    Type-checking only the bare form left `{"score": True}` reaching the DB
    unexamined — the same defect one level in.
    """
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    ret = _return()
    ret["pattern_observations"]["pattern_score"] = {
        "patterns_used": 2, "antipatterns_detected": 1, "score": inner}
    db.write_text(json.dumps({"talks": [_talk()]}))
    batch.write_text(json.dumps([ret]))
    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1, f"{inner!r} was accepted: {result.stdout}"
    assert "pattern_score.score" in result.stderr
    stored = json.loads(db.read_text())["talks"][0]
    assert "pattern_score" not in stored


def test_merge_stamps_the_talk_schema_version(persist_results, tmp_path):
    """stateful-artifacts requires a schema_version on every record."""
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    db.write_text(json.dumps({"talks": [_talk()]}))
    batch.write_text(json.dumps([_return()]))
    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    talk = json.loads(db.read_text())["talks"][0]
    assert talk["schema_version"] == persist_results.TALK_SCHEMA_VERSION


def test_schema_version_is_stamped_over_an_older_value(persist_results, tmp_path):
    """A v1 record merged by this writer becomes v2 — that is the migration."""
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    old = _talk()
    old["schema_version"] = 1
    db.write_text(json.dumps({"talks": [old]}))
    batch.write_text(json.dumps([_return()]))
    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (json.loads(db.read_text())["talks"][0]["schema_version"] ==
            persist_results.TALK_SCHEMA_VERSION)


def test_future_talk_schema_rejects_before_any_record_is_migrated(persist_results):
    database = {
        "talks": [
            {"filename": "legacy.md", "schema_version": 1},
            {
                "filename": "future.md",
                "schema_version": persist_results.TALK_SCHEMA_VERSION + 1,
            },
        ],
    }
    before = copy.deepcopy(database)

    with pytest.raises(ValueError, match="will not downgrade"):
        persist_results.migrate_records(database)

    assert database == before


def test_cli_rejects_future_talk_schema_without_rewriting(
        persist_results, tmp_path):
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    original = {"talks": [_talk(schema_version=99)]}
    db.write_text(json.dumps(original))
    batch.write_text(json.dumps([_return()]))
    before = db.read_bytes()

    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "future talk schema_version 99" in result.stderr
    assert "will not downgrade" in result.stderr
    assert db.read_bytes() == before


def test_non_object_talk_member_is_actionable_and_does_not_rewrite(
        persist_results, tmp_path):
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    db.write_text(json.dumps({"talks": [_talk(), "not-a-talk"]}))
    batch.write_text(json.dumps([_return()]))
    before = db.read_bytes()

    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "talks[1] must be a JSON object" in result.stderr
    assert "Traceback" not in result.stderr
    assert db.read_bytes() == before


def test_tracking_database_symlink_is_rejected_without_splitting_state(
        persist_results, tmp_path):
    target = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    target.write_text(json.dumps({"talks": [_talk()]}))
    batch.write_text(json.dumps([_return()]))
    before = target.read_bytes()
    link = tmp_path / "tracking-link.json"
    link.symlink_to(target.name)

    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(link), str(batch)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "symbolic link" in result.stderr
    assert link.is_symlink()
    assert target.read_bytes() == before


@pytest.mark.parametrize("block", ["structured_data", "verbatim_examples",
                                   "pattern_observations"])
def test_a_malformed_content_block_fails_loudly(persist_results, tmp_path, block):
    """A wrong-typed block used to be SKIPPED while the merge reported success.

    `structured_data` arriving as a list lost the entire analysis and still
    exited 0 — the silent-drop shape this script exists to eliminate.
    """
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    ret = _return()
    ret[block] = [{"slide_count": 60}]  # a list where an object is declared
    db.write_text(json.dumps({"talks": [_talk()]}))
    batch.write_text(json.dumps([ret]))
    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1, f"{block} was skipped silently: {result.stdout}"
    assert block in result.stderr


@pytest.mark.parametrize("bad", [
    ["narrative-arc", "bookends"],          # bare id strings
    "narrative-arc",                        # a string: len() counts characters
    {"pattern_id": "narrative-arc"},        # a single object, not an array
])
def test_malformed_detection_arrays_fail_loudly(persist_results, tmp_path, bad):
    """List-of-strings raised AttributeError mid-merge and killed the script
    before it printed its JSON; a plain string made `len()` count characters as
    detections and fed a silently wrong number into the score cross-check."""
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    ret = _return()
    ret["pattern_observations"]["patterns_detected"] = bad
    db.write_text(json.dumps({"talks": [_talk()]}))
    batch.write_text(json.dumps([ret]))
    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1, f"{bad!r} was accepted: {result.stdout}"
    assert "patterns_detected" in result.stderr
    assert "Traceback" not in result.stderr, "died instead of reporting"


def test_a_malformed_return_leaves_the_talk_untouched(persist_results, tmp_path):
    """Validation runs before any write, so a bad return is not half-merged."""
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    ret = _return()
    ret["pattern_observations"]["patterns_detected"] = ["narrative-arc"]
    original = _talk()
    db.write_text(json.dumps({"talks": [original]}))
    batch.write_text(json.dumps([ret]))
    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert json.loads(db.read_text())["talks"][0] == original


def test_malformed_per_slide_visual_leaves_database_untouched(
        persist_results, tmp_path):
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    ret = _return()
    ret["structured_data"].update({
        "slide_count": 1,
        # Synthetic legacy KCDC shape: aliases cannot cross persistence.
        "per_slide_visual": [{
            "slide_number": 1,
            "content_type": "title",
            "background": "purple_halftone",
            "has_text_footer": True,
        }],
    })
    original = {"talks": [_talk()]}
    db.write_text(json.dumps(original))
    before = db.read_bytes()
    batch.write_text(json.dumps([ret]))

    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "per_slide_visual[0] must contain exactly the canonical fields" in result.stderr
    assert db.read_bytes() == before


def test_migration_stamps_every_record_not_just_merged_ones(persist_results, tmp_path):
    """Stamping only touched talks leaves the artifact permanently mixed-version,
    so a reader cannot tell an unversioned record from an untouched one."""
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    merged, untouched = _talk(), _talk()
    untouched["filename"] = "other-talk.md"
    untouched["_queue_claim"]["batch_id"] = "unrelated-batch"
    db.write_text(json.dumps({"talks": [merged, untouched]}))
    batch.write_text(json.dumps([_return()]))
    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["migrated_records"] == 2
    for talk in json.loads(db.read_text())["talks"]:
        assert talk["schema_version"] == persist_results.TALK_SCHEMA_VERSION


def test_score_object_without_a_score_key_fails_loudly(persist_results, tmp_path):
    """Present-but-incomplete is malformed, not absent — returning "no score"
    would drop the value exactly like the bare int used to."""
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    ret = _return()
    ret["pattern_observations"]["pattern_score"] = {
        "patterns_used": 2, "antipatterns_detected": 1}
    db.write_text(json.dumps({"talks": [_talk()]}))
    batch.write_text(json.dumps([ret]))
    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "pattern_score.score must be an integer" in result.stderr
    assert "pattern_score" not in json.loads(db.read_text())["talks"][0]


def test_clear_fields_removes_contaminated_values_and_promoted_scalars(
        persist_results, tmp_path):
    """A corrective reparse can explicitly remove claims disproved by artifacts."""
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    talk = _talk(
        slide_count=999,
        slides_local_path="slides/stale.pdf",
        structured_data={"slide_count": 999, "stale_claim": "borrowed deck"},
        verbatim_examples={"jokes": ["quote from a sibling delivery"]},
    )
    ret = _return(clear_fields=[
        "slides_local_path",
        "structured_data.slide_count",
        "structured_data.stale_claim",
        "verbatim_examples.jokes",
    ])
    del ret["structured_data"]["slide_count"]
    ret["verbatim_examples"]["jokes"] = []
    db.write_text(json.dumps({"talks": [talk]}))
    batch.write_text(json.dumps([ret]))
    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    stored = json.loads(db.read_text())["talks"][0]
    assert "slide_count" not in stored
    assert "slides_local_path" not in stored
    assert "slide_count" not in stored["structured_data"]
    assert "stale_claim" not in stored["structured_data"]
    assert "jokes" not in stored["verbatim_examples"]
    report = json.loads(result.stdout)
    assert "structured_data.slide_count" in report["talks"][0]["cleared"]
    assert "slide_count" in report["talks"][0]["cleared"]


def test_pattern_score_clear_removes_both_nested_and_promoted_value(
        persist_results, tmp_path):
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    talk = _talk(
        pattern_score=99,
        pattern_observations={"pattern_score": 99, "pattern_ids": ["narrative-arc"]},
    )
    ret = _return(clear_fields=["pattern_observations.pattern_score"])
    # The valid replacement score is written after the clear; the important
    # invariant is that no old 99 survives on either surface.
    db.write_text(json.dumps({"talks": [talk]}))
    batch.write_text(json.dumps([ret]))
    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    stored = json.loads(db.read_text())["talks"][0]
    assert stored["pattern_score"] == 1
    assert stored["pattern_observations"]["pattern_score"] == 1


def test_catalog_generation_is_stamped_and_processing_claim_is_closed(
        persist_results, tmp_path):
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    talk = _talk()
    db.write_text(json.dumps({"talks": [talk]}))
    batch.write_text(json.dumps([_return()]))
    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    stored = json.loads(db.read_text())["talks"][0]
    assert stored["pattern_scoring_schema_version"] == \
        persist_results.PATTERN_SCORING_SCHEMA_VERSION
    assert stored["pattern_catalog_fingerprint"] == report["pattern_catalog_fingerprint"]
    assert stored["_queue_claim"]["state"] == "completed"
    assert stored["_queue_claim"]["schema_version"] == \
        persist_results.QUEUE_CLAIM_SCHEMA_VERSION
    assert stored["_queue_claim"]["result_status"] == "processed"
    assert stored["_queue_claim"]["release_reason"] == "return_persisted"
    assert stored["_queue_claim"]["result_payload_sha256"] == \
        persist_results.canonical_return_sha256(_return())


def test_missing_status_rejects_the_whole_batch_without_migrating_db(
        persist_results, tmp_path):
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    original = {"talks": [_talk()]}
    invalid = _return()
    del invalid["status"]
    db.write_text(json.dumps(original))
    batch.write_text(json.dumps([_return(filename="talk.md"), invalid]))
    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "status is required" in result.stderr
    assert json.loads(db.read_text()) == original


def test_duplicate_db_filenames_are_rejected_before_write(persist_results, tmp_path):
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    original = {"talks": [_talk(), _talk()]}
    db.write_text(json.dumps(original))
    batch.write_text(json.dumps([_return()]))
    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "duplicate filenames" in result.stderr
    assert json.loads(db.read_text()) == original


def test_partial_three_member_batch_is_rejected_before_any_db_write(
        persist_results, tmp_path):
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    talks = [_talk(filename=f"{name}.md") for name in ("a", "b", "c")]
    returns = [_return(filename=f"{name}.md") for name in ("a", "b")]
    original = {"talks": talks}
    db.write_text(json.dumps(original))
    batch.write_text(json.dumps(returns))

    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )

    assert result.returncode == 1
    assert "missing ['c.md']" in result.stderr
    assert json.loads(db.read_text()) == original


def test_partially_closed_batch_cannot_be_finished_piecemeal(
        persist_results, tmp_path):
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    talks = [_talk(filename=f"{name}.md") for name in ("a", "b", "c")]
    for talk in talks[:2]:
        talk["status"] = "processed"
        talk["_queue_claim"].update({
            "state": "completed",
            "released_at": "2026-07-31T18:05:00+00:00",
            "release_reason": "return_persisted",
            "result_status": "processed",
        })
    original = {"talks": talks}
    db.write_text(json.dumps(original))
    batch.write_text(json.dumps([
        _return(filename=f"{name}.md") for name in ("a", "b", "c")]))

    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )

    assert result.returncode == 1
    assert "closed or stranded member" in result.stderr
    assert json.loads(db.read_text()) == original


def test_stale_return_generation_cannot_roll_back_a_requeue(persist_results, tmp_path):
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    talk = _talk(reprocess_generation=2)
    talk["_queue_claim"]["reprocess_generation"] = 2
    original = {"talks": [talk]}
    stale = _return()  # generation 1
    db.write_text(json.dumps(original))
    batch.write_text(json.dumps([stale]))
    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "does not match active claim value 2" in result.stderr
    assert json.loads(db.read_text()) == original


def test_claim_generation_cannot_lag_top_level_generation(persist_results, tmp_path):
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    talk = _talk(reprocess_generation=2)
    original = {"talks": [talk]}
    db.write_text(json.dumps(original))
    batch.write_text(json.dumps([_return()]))

    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )

    assert result.returncode == 1
    assert "active claim generation 1 disagrees with talk generation 2" in result.stderr
    assert json.loads(db.read_text()) == original


def test_active_claim_with_undeclared_fields_is_rejected_before_write(
        persist_results, tmp_path):
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    talk = _talk()
    talk["_queue_claim"]["released_at"] = None
    original = {"talks": [talk]}
    db.write_text(json.dumps(original))
    batch.write_text(json.dumps([_return()]))

    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )

    assert result.returncode == 1
    assert "must use exactly the schema fields" in result.stderr
    assert "released_at" in result.stderr
    assert json.loads(db.read_text()) == original


def test_skipped_return_preserves_prior_analysis_and_persists_terminal_metadata(
        persist_results, tmp_path):
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    talk = _talk(
        processed_date="2026-06-18",
        transcript_source="youtube_auto",
        slide_source="pptx",
        rhetoric_notes="trusted prior analysis",
        structured_data={"slide_count": 42},
        verbatim_examples={"jokes": ["kept"]},
        video_url=None,
        pptx_path=None,
        slides_url=None,
    )
    db.write_text(json.dumps({"talks": [talk]}))
    batch.write_text(json.dumps([_skipped_return()]))

    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr
    stored = json.loads(db.read_text())["talks"][0]
    assert stored["status"] == "skipped_no_sources"
    assert stored["processed_date"] == "2026-06-18"
    assert stored["transcript_source"] == "youtube_auto"
    assert stored["slide_source"] == "pptx"
    assert stored["rhetoric_notes"] == "trusted prior analysis"
    assert stored["structured_data"] == {"slide_count": 42}
    assert stored["verbatim_examples"] == {"jokes": ["kept"]}
    assert stored["_queue_claim"]["state"] == "completed"


@pytest.mark.parametrize(
    "source_fields",
    [
        {"video_url": "https://youtu.be/AbCdEfGhI_1"},
        {"transcript_path": "transcripts/talk.txt"},
        {"pptx_path": "decks/talk.pptx"},
        {"slides_local_path": "slides/talk.pdf"},
    ],
)
def test_skipped_no_sources_rejects_each_live_capability(
        persist_results, tmp_path, source_fields):
    base = {
        "video_url": None,
        "pptx_path": None,
        "slides_url": None,
        "google_drive_id": None,
        "transcript_path": None,
        "slides_local_path": None,
    }
    talk = _talk(**{**base, **source_fields})
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    db.write_text(json.dumps({"talks": [talk]}))
    batch.write_text(json.dumps([_skipped_return()]))
    before = db.read_bytes()

    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "cannot finish skipped_no_sources" in result.stderr
    assert db.read_bytes() == before


@pytest.mark.parametrize(
    "local_source",
    [
        {"transcript_path": "transcripts/talk.txt"},
        {"pptx_path": "decks/talk.pptx"},
        {"slides_local_path": "slides/talk.pdf"},
    ],
)
def test_download_failure_rejects_when_a_local_artifact_remains(
        persist_results, tmp_path, local_source):
    talk = _talk(**{
        "pptx_path": None,
        "slides_url": None,
        "transcript_path": None,
        "slides_local_path": None,
        **local_source,
    })
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    db.write_text(json.dumps({"talks": [talk]}))
    batch.write_text(json.dumps([
        _skipped_return(status="skipped_download_failed")]))
    before = db.read_bytes()

    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "while a local transcript, PPTX, or PDF artifact remains" in result.stderr
    assert db.read_bytes() == before


def test_download_failure_requires_a_remote_acquisition_path(
        persist_results, tmp_path):
    talk = _talk(video_url=None, pptx_path=None, slides_url=None)
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    db.write_text(json.dumps({"talks": [talk]}))
    batch.write_text(json.dumps([
        _skipped_return(status="skipped_download_failed")]))

    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "without a declared video or remote slide acquisition path" in result.stderr


def test_duplicate_skip_requires_a_bound_canonical_talk(
        persist_results, tmp_path):
    talk = _talk(video_url=None, pptx_path=None, slides_url=None)
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    db.write_text(json.dumps({"talks": [talk]}))
    batch.write_text(json.dumps([_skipped_return(status="skipped_duplicate")]))

    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "source_relation.type='duplicate'" in result.stderr


@pytest.mark.parametrize(
    ("status", "talk_overrides"),
    [
        (
            "skipped_download_failed",
            {"video_url": "https://youtu.be/AbCdEfGhI_1"},
        ),
        (
            "skipped_duplicate",
            {
                "source_relation": {
                    "type": "duplicate",
                    "target_filename": "canonical.md",
                },
            },
        ),
    ],
)
def test_mechanically_bound_skip_status_can_close_claim(
        persist_results, tmp_path, status, talk_overrides):
    talk = _talk(**{
        "video_url": None,
        "pptx_path": None,
        "slides_url": None,
        "transcript_path": None,
        "slides_local_path": None,
        **talk_overrides,
    })
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    db.write_text(json.dumps({"talks": [talk]}))
    batch.write_text(json.dumps([_skipped_return(status=status)]))

    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    stored = json.loads(db.read_text())["talks"][0]
    assert stored["status"] == status
    assert stored["_queue_claim"]["result_status"] == status


def test_skipped_return_with_analysis_fields_aborts_without_write(
        persist_results, tmp_path):
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    original = {"talks": [_talk(rhetoric_notes="trusted prior analysis")]}
    invalid = _skipped_return(rhetoric_notes="stale rejected analysis")
    db.write_text(json.dumps(original))
    batch.write_text(json.dumps([invalid]))

    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )

    assert result.returncode == 1
    assert "cannot mutate or clear prior analysis fields" in result.stderr
    assert json.loads(db.read_text()) == original


def test_kcdc_wrong_transcript_source_cannot_be_resurrected(
        persist_results, return_validation, tmp_path):
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    talk = _talk(
        video_url=None,
        youtube_id=None,
        pptx_path=None,
        transcript_source="none",
        slide_source="pdf",
        google_drive_id="slides-id",
    )
    ret = _return(status="processed_partial", slide_source="pdf")
    ret["pattern_observations"]["evidence_sources"] = [
        "transcript", "static_slides"]
    _complete_unavailable_source_gates(return_validation, ret)
    original = {"talks": [talk]}
    db.write_text(json.dumps(original))
    batch.write_text(json.dumps([ret]))

    result = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )

    assert result.returncode == 1
    assert "no transcript reference or active video source" in result.stderr
    assert json.loads(db.read_text()) == original


def test_completed_generation_cannot_be_replayed(persist_results, tmp_path):
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    db.write_text(json.dumps({"talks": [_talk()]}))
    batch.write_text(json.dumps([_return()]))
    first = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )
    assert first.returncode == 0, first.stderr
    completed = db.read_bytes()
    replay = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch)],
        capture_output=True, text=True,
    )
    assert replay.returncode == 1
    assert "closed or stranded member" in replay.stderr
    assert db.read_bytes() == completed
