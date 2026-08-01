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
                {
                    "pattern_id": "narrative-arc",
                    "confidence": "strong",
                    "evidence": "The deck follows a problem-to-resolution arc.",
                    "evidence_citations": [
                        {"channel": "slides", "slide_numbers": [1, 20, 60]}
                    ],
                },
                {
                    "pattern_id": "bookends",
                    "confidence": "moderate",
                    "evidence": "Matching dividers bracket the main sections.",
                    "evidence_citations": [
                        {"channel": "slides", "slide_numbers": [2, 18]}
                    ],
                },
            ],
            "antipatterns_detected": [
                {
                    "pattern_id": "ant-fonts",
                    "confidence": "weak",
                    "evidence": "One code slide uses text below the readable threshold.",
                    "evidence_citations": [
                        {"channel": "slides", "slide_numbers": [8]}
                    ],
                }
            ],
            "pattern_score": {"patterns_used": 8, "antipatterns_detected": 1, "score": 7},
        },
    }
    ret.update(overrides)
    return ret


def _talk(**overrides):
    talk = {
        "filename": "talk.md",
        "status": "pending",
        "slide_source": "pptx",
        "slide_count": 62,
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
    assert obs["antipattern_ids"] == ["ant-fonts"]
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
    """A v1 record merged by this writer becomes v3 — that is the migration."""
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
    assert json.loads(db.read_text())["talks"][0]["schema_version"] == 3


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


def test_migration_stamps_every_record_not_just_merged_ones(persist_results, tmp_path):
    """Stamping only touched talks leaves the artifact permanently mixed-version,
    so a reader cannot tell an unversioned record from an untouched one."""
    db = tmp_path / "tracking-database.json"
    batch = tmp_path / "batch-returns.json"
    merged, untouched = _talk(), _talk()
    untouched["filename"] = "other-talk.md"
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
    assert "no `score` key" in result.stderr
    assert "pattern_score" not in json.loads(db.read_text())["talks"][0]


def test_detection_requires_source_located_evidence(persist_results):
    detection = {
        "pattern_id": "narrative-arc",
        "confidence": "strong",
        "evidence": "A clear problem-to-resolution arc.",
    }
    with pytest.raises(ValueError, match="evidence_citations"):
        persist_results.validate_detection(
            detection,
            field="patterns_detected",
            catalog=persist_results.load_pattern_catalog(),
        )


def test_transcript_quote_is_verified_and_locations_are_engine_owned(persist_results):
    detection = {
        "pattern_id": "opening-punch",
        "confidence": "strong",
        "evidence": "A concrete incident opens the talk.",
        "evidence_citations": [
            {
                "channel": "timed_transcript",
                "quote": "The production deploy failed on Friday night.",
                "line_start": 999,
                "start_seconds": 999,
            }
        ],
    }
    context = {
        "transcript_text": (
            "The production deploy failed on Friday night.\n"
            "That incident changed our release process."
        ),
        "transcript_reason": "loaded fixture transcript",
        "timed_segments": [
            {
                "text": "The production deploy failed on Friday night.",
                "start_seconds": 2.0,
                "end_seconds": 6.0,
            },
            {
                "text": "That incident changed our release process.",
                "start_seconds": 6.0,
                "end_seconds": 10.0,
            },
        ],
        "timing_reason": "2 verified timed segments",
    }

    validated = persist_results.validate_detection(
        detection,
        field="patterns_detected",
        catalog=persist_results.load_pattern_catalog(),
        evidence_context=context,
    )

    citation = validated["evidence_citations"][0]
    assert citation["line_start"] == 1
    assert citation["line_end"] == 1
    assert citation["start_seconds"] == 2.0
    assert citation["end_seconds"] == 6.0


def test_non_english_citation_matches_original_and_keeps_translation(persist_results):
    detection = {
        "pattern_id": "narrative-arc",
        "confidence": "strong",
        "evidence": "The speaker frames the incident as the turning point.",
        "evidence_citations": [
            {
                "channel": "transcript",
                "quote": "Этот сбой изменил весь наш процесс.",
                "translation": "That failure changed our entire process.",
            }
        ],
    }
    validated = persist_results.validate_detection(
        detection,
        field="patterns_detected",
        catalog=persist_results.load_pattern_catalog(),
        evidence_context={
            "transcript_text": "Этот сбой изменил весь наш процесс.",
            "timed_segments": [],
        },
    )
    citation = validated["evidence_citations"][0]
    assert citation["translation"] == "That failure changed our entire process."
    assert citation["line_start"] == 1


def test_citation_shapes_reject_unknown_model_fields(persist_results):
    detection = {
        "pattern_id": "narrative-arc",
        "confidence": "strong",
        "evidence": "A clear problem-to-resolution arc.",
        "evidence_citations": [
            {
                "channel": "slides",
                "slide_numbers": [1, 2],
                "model_reasoning": "trust me",
            }
        ],
    }
    with pytest.raises(ValueError, match="unknown fields"):
        persist_results.validate_detection(
            detection,
            field="patterns_detected",
            catalog=persist_results.load_pattern_catalog(),
        )


def test_timing_dependent_pattern_fails_closed_without_sidecar(persist_results):
    detection = {
        "pattern_id": "opening-punch",
        "confidence": "strong",
        "evidence": "A concrete incident opens the talk.",
        "evidence_citations": [
            {
                "channel": "timed_transcript",
                "quote": "The production deploy failed on Friday night.",
            }
        ],
    }
    context = {
        "transcript_text": "The production deploy failed on Friday night.",
        "transcript_reason": "loaded fixture transcript",
        "timed_segments": [],
        "timing_reason": "timed transcript sidecar is missing",
    }
    with pytest.raises(ValueError, match="no verified timestamp"):
        persist_results.validate_detection(
            detection,
            field="patterns_detected",
            catalog=persist_results.load_pattern_catalog(),
            evidence_context=context,
        )


def test_catalog_rejects_wrong_channel_and_hidden_process_inference(persist_results):
    catalog = persist_results.load_pattern_catalog()
    transcript_guess = {
        "pattern_id": "composite-animation",
        "confidence": "moderate",
        "evidence": "The speaker describes several movements.",
        "evidence_citations": [
            {
                "channel": "transcript",
                "quote": "Watch this element move across the whole screen.",
            }
        ],
    }
    with pytest.raises(ValueError, match="cannot be proved through"):
        persist_results.validate_detection(
            transcript_guess,
            field="patterns_detected",
            catalog=catalog,
        )

    hidden_process = {
        "pattern_id": "fourthought",
        "confidence": "strong",
        "evidence": "The final talk is well organized.",
        "evidence_citations": [
            {"channel": "slides", "slide_numbers": [1, 2]}
        ],
    }
    with pytest.raises(ValueError, match="observable:false"):
        persist_results.validate_detection(
            hidden_process,
            field="patterns_detected",
            catalog=catalog,
        )


def test_catalog_rejects_pattern_antipattern_bucket_swaps(persist_results):
    detection = {
        "pattern_id": "ant-fonts",
        "confidence": "strong",
        "evidence": "The slide text is too small to read.",
        "evidence_citations": [
            {"channel": "slides", "slide_numbers": [8]}
        ],
    }
    with pytest.raises(ValueError, match="cataloged as 'antipattern'"):
        persist_results.validate_detection(
            detection,
            field="patterns_detected",
            catalog=persist_results.load_pattern_catalog(),
        )


def test_duplicate_pattern_ids_are_rejected(persist_results):
    observations = _return()["pattern_observations"]
    observations["patterns_detected"] = [
        observations["patterns_detected"][0],
        observations["patterns_detected"][0],
    ]
    with pytest.raises(ValueError, match="duplicate pattern IDs"):
        persist_results.require_detections(
            observations,
            "patterns_detected",
            catalog=persist_results.load_pattern_catalog(),
        )


def test_v3_migration_marks_legacy_evidence_unlocated(persist_results):
    db = {
        "talks": [
            _talk(
                schema_version=2,
                pattern_observations={
                    "patterns_detected": [
                        {
                            "pattern_id": "narrative-arc",
                            "confidence": "strong",
                            "evidence": "Legacy prose only.",
                        }
                    ],
                    "antipatterns_detected": [],
                    "pattern_score": 1,
                },
            )
        ]
    }
    assert persist_results.migrate_records(db) == 1
    talk = db["talks"][0]
    assert talk["schema_version"] == 3
    assert talk["pattern_observations"]["evidence_schema_version"] == 1
    assert talk["pattern_observations"]["patterns_detected"][0][
        "evidence_citations"
    ] == []


def test_non_youtube_transcript_path_is_resolved_inside_vault(persist_results, tmp_path):
    transcript_dir = tmp_path / "transcripts"
    transcript_dir.mkdir()
    transcript = transcript_dir / "infoq-talk.txt"
    transcript.write_text(
        "The production deploy failed on Friday night.",
        encoding="utf-8",
    )
    talk = _talk(filename="infoq.md")
    ret = _return(
        filename="infoq.md",
        transcript_path="transcripts/infoq-talk.txt",
    )

    context = persist_results.build_evidence_context(tmp_path, talk, ret)

    assert context["transcript_text"] == transcript.read_text(encoding="utf-8")
    assert "loaded transcript" in context["transcript_reason"]


@pytest.mark.parametrize(
    "bad_path",
    ["../secret.txt", "/tmp/secret.txt", "analyses/talk.txt", "transcripts/talk.json"],
)
def test_transcript_path_cannot_escape_its_vault_directory(
    persist_results,
    tmp_path,
    bad_path,
):
    with pytest.raises(ValueError, match="under the vault's transcripts"):
        persist_results.build_evidence_context(
            tmp_path,
            _talk(filename="infoq.md"),
            _return(filename="infoq.md", transcript_path=bad_path),
        )


def test_invalid_youtube_id_cannot_become_a_transcript_path(persist_results, tmp_path):
    with pytest.raises(ValueError, match="11-character YouTube id"):
        persist_results.build_evidence_context(
            tmp_path,
            _talk(youtube_id="../../escape"),
            _return(),
        )


def test_youtube_talk_cannot_redirect_evidence_to_another_transcript(
    persist_results,
    tmp_path,
):
    with pytest.raises(ValueError, match="does not match this talk's youtube_id"):
        persist_results.build_evidence_context(
            tmp_path,
            _talk(youtube_id="eg6gqvUFh6Q"),
            _return(transcript_path="transcripts/someone-else.txt"),
        )


def test_slide_citation_requires_a_declared_usable_source(persist_results):
    detection = {
        "pattern_id": "narrative-arc",
        "confidence": "strong",
        "evidence": "The deck follows a problem-to-resolution arc.",
        "evidence_citations": [
            {"channel": "slides", "slide_numbers": [1, 2]}
        ],
    }
    with pytest.raises(ValueError, match="no usable slide source/count"):
        persist_results.validate_detection(
            detection,
            field="patterns_detected",
            catalog=persist_results.load_pattern_catalog(),
            evidence_context={"slide_source": "model_guess", "slide_count": 2},
        )


def test_video_citation_rejects_nonfinite_timestamps(persist_results):
    detection = {
        "pattern_id": "make-it-rain",
        "confidence": "strong",
        "evidence": "Objects are thrown to audience members.",
        "evidence_citations": [
            {"channel": "video", "start_seconds": 2.0, "end_seconds": float("inf")}
        ],
    }
    with pytest.raises(ValueError, match="numeric start_seconds/end_seconds"):
        persist_results.validate_detection(
            detection,
            field="patterns_detected",
            catalog=persist_results.load_pattern_catalog(),
            evidence_context={"video_url": "https://example.test/video"},
        )


def test_talk_metadata_cannot_cite_generated_analysis_prose(persist_results):
    detection = {
        "pattern_id": "lightning-talk",
        "confidence": "strong",
        "evidence": "The return calls itself a lightning talk.",
        "evidence_citations": [
            {"channel": "talk_metadata", "field": "rhetoric_notes"}
        ],
    }
    with pytest.raises(ValueError, match="is not source metadata"):
        persist_results.validate_detection(
            detection,
            field="patterns_detected",
            catalog=persist_results.load_pattern_catalog(),
        )


def test_pattern_metadata_policy_rejects_irrelevant_source_fields(persist_results):
    detection = {
        "pattern_id": "lightning-talk",
        "confidence": "strong",
        "evidence": "A transcript artifact exists.",
        "evidence_citations": [
            {"channel": "talk_metadata", "field": "transcript_path"}
        ],
    }
    with pytest.raises(ValueError, match="not permitted for this pattern"):
        persist_results.validate_detection(
            detection,
            field="patterns_detected",
            catalog=persist_results.load_pattern_catalog(),
        )


def test_talk_metadata_value_is_stamped_from_promoted_source_field(
    persist_results,
    tmp_path,
):
    ret = _return()
    context = persist_results.build_evidence_context(tmp_path, _talk(), ret)
    detection = {
        "pattern_id": "lightning-talk",
        "confidence": "moderate",
        "evidence": "The deck uses the fixed 20-slide format.",
        "evidence_citations": [
            {"channel": "talk_metadata", "field": "slide_count", "value": 999}
        ],
    }

    validated = persist_results.validate_detection(
        detection,
        field="patterns_detected",
        catalog=persist_results.load_pattern_catalog(),
        evidence_context=context,
    )

    assert validated["evidence_citations"][0]["value"] == 62


def test_catalog_rejects_duplicate_evidence_channels(persist_results, tmp_path):
    category = tmp_path / "build"
    category.mkdir()
    (category / "duplicate.md").write_text(
        """---
id: duplicate
type: pattern
observable: true
evidence_channels: [video, video]
---
# Duplicate
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid evidence_channels"):
        persist_results.load_pattern_catalog(tmp_path)


def test_migration_refuses_to_downgrade_a_future_schema(persist_results):
    db = {"talks": [_talk(schema_version=persist_results.TALK_SCHEMA_VERSION + 1)]}
    with pytest.raises(ValueError, match="will not downgrade"):
        persist_results.migrate_records(db)
    assert db["talks"][0]["schema_version"] == persist_results.TALK_SCHEMA_VERSION + 1


def test_future_schema_preflight_leaves_earlier_legacy_record_untouched(persist_results):
    legacy = _talk(schema_version=2)
    future = _talk(
        filename="future.md",
        schema_version=persist_results.TALK_SCHEMA_VERSION + 1,
    )
    db = {"talks": [legacy, future]}
    with pytest.raises(ValueError, match="will not downgrade"):
        persist_results.migrate_records(db)
    assert legacy["schema_version"] == 2
