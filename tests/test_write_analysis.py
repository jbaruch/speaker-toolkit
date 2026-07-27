"""Tests for write-analysis.py — the executable half of Step 4 that renders
per-talk analysis markdown from subagent returns.

Regression coverage: across the 2026-07-26 full reparse the analysis-file write
was skipped for all 82 reparsed talks, because Step 4 assigned it to the
orchestrator in prose with no script to run. The DB carried the corrected
analysis while every analyses/*.md still asserted what the reparse had refuted.
"""

import json
import re
import subprocess
import sys


def _return(**overrides):
    ret = {
        "filename": "talk.md",
        "status": "processed",
        "processed_date": "2026-07-26",
        "transcript_source": "youtube_auto",
        "slide_source": "pptx",
        "rhetoric_notes": "DIMENSION 1 -- OPENING: cold open.",
        "areas_for_improvement": "1) Tighten the close.",
        "adherence_assessment": "Above the mode baseline.",
        "structured_data": {
            "slide_count": 31,
            "co_presenter": False,
            "image_only_slide_count": 0,
            "per_slide_visual": [
                {"slide": 1, "background": "salmon", "content_type": "title"},
                {"slide": 2, "background": "black", "content_type": "bullets"},
            ],
            "act_structure": {"acts": 4},
        },
        "verbatim_examples": {"jokes": ["the monkeys wrecked the server room"]},
        "pattern_observations": {
            "patterns_detected": [
                {"pattern_id": "narrative-arc", "confidence": "strong",
                 "evidence": "Four-act catalog."},
            ],
            "antipatterns_detected": [
                {"pattern_id": "ant-fonts", "confidence": "moderate",
                 "evidence": "7.5pt body text."},
            ],
            "pattern_score": {"patterns_used": 25, "antipatterns_detected": 3, "score": 22},
        },
        "catalog_feedback": {
            "unmatched_observations": [{"observation": "controlling metaphor"}],
            "tensions": [],
        },
    }
    ret.update(overrides)
    return ret


def test_renders_core_sections(write_analysis):
    md = write_analysis.render_analysis(_return())
    assert md.startswith("# Rhetoric Analysis: talk")
    assert "**Filename:** talk.md" in md
    assert "**Processed:** 2026-07-26" in md
    assert "## Rhetoric Notes (Dimensions 1-13)" in md
    assert "## Areas for Improvement (Dimension 14)" in md
    assert "## Adherence Assessment" in md
    assert "## Structured Data" in md
    assert "## Presentation Patterns Scoring" in md


def test_title_from_db_wins_over_filename(write_analysis):
    md = write_analysis.render_analysis(_return(), title="Never Trust a Monkey")
    assert md.startswith("# Rhetoric Analysis: Never Trust a Monkey")


def test_scoring_tables_carry_evidence(write_analysis):
    md = write_analysis.render_analysis(_return())
    assert "**Pattern score:** 22 (25 patterns − 3 antipatterns)" in md
    assert "| `narrative-arc` | strong | Four-act catalog. |" in md
    assert "| `ant-fonts` | moderate | 7.5pt body text. |" in md


def test_per_slide_visual_becomes_a_table(write_analysis):
    md = write_analysis.render_analysis(_return())
    assert "### per_slide_visual" in md
    assert "| slide | background | content_type |" in md
    assert "| 1 | salmon | title |" in md


def test_pipes_and_newlines_do_not_break_table_rows(write_analysis):
    ret = _return()
    ret["pattern_observations"]["patterns_detected"] = [
        {"pattern_id": "triad", "confidence": "strong",
         "evidence": "He said a | b | c\nthen paused."}
    ]
    md = write_analysis.render_analysis(ret)
    rows = [ln for ln in md.splitlines() if ln.startswith("| `triad`")]
    assert len(rows) == 1, "the newline must not split the evidence across two rows"
    row = rows[0]
    # Splitting on UNESCAPED pipes is what a markdown renderer does; escaped
    # ones stay inside the cell.
    cells = [c for c in re.split(r"(?<!\\)\|", row)[1:-1]]
    assert len(cells) == 3
    assert "\\|" in cells[2]


def test_absent_sections_are_skipped_not_stubbed(write_analysis):
    ret = _return()
    for key in ("adherence_assessment", "verbatim_examples", "catalog_feedback",
                "areas_for_improvement"):
        del ret[key]
    md = write_analysis.render_analysis(ret)
    assert "## Adherence Assessment" not in md
    assert "## Verbatim Examples" not in md
    assert "## Catalog Feedback" not in md
    assert "## Areas for Improvement" not in md
    assert "## Rhetoric Notes (Dimensions 1-13)" in md


def test_list_shaped_prose_field_renders_as_bullets(write_analysis):
    """One 2026-07-26 return sent `areas_for_improvement` as a list of finding
    objects instead of the schema's string, which crashed the whole batch."""
    md = write_analysis.render_analysis(_return(areas_for_improvement=[
        {"issue": "Zero audience production", "fix": "Ask the room."},
        {"issue": "Rhetorical questions self-answered"},
    ]))
    assert "## Areas for Improvement (Dimension 14)" in md
    assert "**issue:** Zero audience production" in md
    assert "**fix:** Ask the room." in md
    assert "Rhetorical questions self-answered" in md


def test_prose_coercion_handles_plain_lists_and_dicts(write_analysis):
    assert write_analysis.as_prose(["a", "b"]) == "- a\n- b"
    assert write_analysis.as_prose({"k": "v"}) == "- **k:** v"
    assert write_analysis.as_prose(None) == ""
    assert write_analysis.as_prose("already prose") == "already prose"


def test_empty_catalog_feedback_omits_the_section(write_analysis):
    md = write_analysis.render_analysis(
        _return(catalog_feedback={"tensions": [], "definition_problems": []}))
    assert "## Catalog Feedback" not in md


def test_run_date_fills_missing_processed_date(write_analysis):
    ret = _return()
    del ret["processed_date"]
    md = write_analysis.render_analysis(ret, run_date="2026-07-26")
    assert "**Processed:** 2026-07-26" in md


def test_return_processed_date_wins_over_run_date(write_analysis):
    md = write_analysis.render_analysis(_return(), run_date="2026-01-01")
    assert "**Processed:** 2026-07-26" in md


def test_nested_structured_fields_are_preserved(write_analysis):
    md = write_analysis.render_analysis(_return())
    assert "### Additional structured fields" in md
    assert '"act_structure"' in md


def test_cli_writes_files_and_reports(write_analysis, tmp_path):
    batch = tmp_path / "batch-returns.json"
    out = tmp_path / "analyses"
    batch.write_text(json.dumps([_return(), _return(filename="other.md")]))
    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(out),
         "--run-date", "2026-07-26"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (out / "talk.md").exists()
    assert (out / "other.md").exists()
    report = json.loads(result.stdout)
    assert report["written"] == 2
    assert report["files"][0]["bytes"] > 0


def test_cli_uses_titles_from_tracking_db(write_analysis, tmp_path):
    batch = tmp_path / "batch-returns.json"
    db = tmp_path / "tracking-database.json"
    out = tmp_path / "analyses"
    batch.write_text(json.dumps([_return()]))
    db.write_text(json.dumps({"talks": [{"filename": "talk.md", "title": "Real Title"}]}))
    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(out),
         "--talks", str(db)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (out / "talk.md").read_text().startswith("# Rhetoric Analysis: Real Title")


def test_cli_fails_visibly_on_return_without_filename(write_analysis, tmp_path):
    batch = tmp_path / "batch-returns.json"
    ret = _return()
    del ret["filename"]
    batch.write_text(json.dumps([ret]))
    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(tmp_path / "a")],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "filename" in result.stderr


def test_cli_non_array_batch_is_actionable(write_analysis, tmp_path):
    batch = tmp_path / "batch-returns.json"
    batch.write_text(json.dumps({"filename": "talk.md"}))
    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(tmp_path / "a")],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "must be a JSON array" in result.stderr


def test_output_name_is_confined_to_the_output_dir(write_analysis):
    """`filename` comes from a model-generated return, so it is untrusted for
    path purposes — tracking-database.json sits one level above analyses/."""
    assert write_analysis.safe_output_name("../tracking-database.json") == \
        "tracking-database.json.md"
    assert write_analysis.safe_output_name("/etc/passwd") == "passwd.md"
    assert write_analysis.safe_output_name("a/b/talk.md") == "talk.md"
    assert write_analysis.safe_output_name("talk.md") == "talk.md"


def test_cli_does_not_write_outside_the_output_dir(write_analysis, tmp_path):
    batch = tmp_path / "batch-returns.json"
    out = tmp_path / "analyses"
    victim = tmp_path / "tracking-database.json"
    victim.write_text('{"talks": []}')
    batch.write_text(json.dumps([_return(filename="../tracking-database.json")]))
    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(out)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert victim.read_text() == '{"talks": []}', "the sibling file was overwritten"
    assert (out / "tracking-database.json.md").exists()


def test_cli_rejects_filename_that_names_no_file(write_analysis, tmp_path):
    batch = tmp_path / "batch-returns.json"
    batch.write_text(json.dumps([_return(filename="../")]))
    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(tmp_path / "a")],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "does not name a file" in result.stderr


def test_cli_rejects_malformed_tracking_db(write_analysis, tmp_path):
    batch = tmp_path / "batch-returns.json"
    db = tmp_path / "not-a-db.json"
    batch.write_text(json.dumps([_return()]))
    db.write_text(json.dumps(["not", "a", "db"]))
    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(tmp_path / "a"),
         "--talks", str(db)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "talks" in result.stderr


def test_cli_unwritable_output_dir_is_actionable(write_analysis, tmp_path):
    batch = tmp_path / "batch-returns.json"
    batch.write_text(json.dumps([_return()]))
    # A regular file where the output directory should be: makedirs raises OSError.
    blocker = tmp_path / "blocked"
    blocker.write_text("i am a file, not a directory")
    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(blocker)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "cannot create output directory" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_missing_input_file_is_actionable(write_analysis, tmp_path):
    result = subprocess.run(
        [sys.executable, write_analysis.__file__,
         str(tmp_path / "nope.json"), str(tmp_path / "a")],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "not found" in result.stderr
