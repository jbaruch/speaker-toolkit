"""Tests for persist-results.py — deterministic Step 4 merge of subagent returns.

Regression coverage for #97: structured_data computed by subagents must land in
the tracking DB, with the declared queryable scalars promoted to the talk top level.
"""

import json
import subprocess
import sys


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
    assert "persisted 1 talk(s)" in result.stdout


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
