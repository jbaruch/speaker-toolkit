"""Tests for write-analysis.py — the executable half of Step 4 that renders
per-talk analysis markdown from subagent returns.

Regression coverage: across the 2026-07-26 full reparse the analysis-file write
was skipped for all 82 reparsed talks, because Step 4 assigned it to the
orchestrator in prose with no script to run. The DB carried the corrected
analysis while every analyses/*.md still asserted what the reparse had refuted.
"""

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest


def _catalog_fingerprint():
    root = (
        Path(__file__).parents[1]
        / "skills"
        / "presentation-creator"
        / "references"
        / "patterns"
    )
    digest = hashlib.sha256()

    def update(relative_path, content):
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")

    update("_index.md", (root / "_index.md").read_bytes())
    for path in sorted(
            (item for item in root.rglob("*.md") if item != root / "_index.md"),
            key=lambda item: item.relative_to(root).as_posix()):
        update(path.relative_to(root).as_posix(), path.read_bytes())
    return digest.hexdigest()


CATALOG_FINGERPRINT = _catalog_fingerprint()


def _return_receipt(ret):
    canonical = json.dumps(
        ret,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _return(**overrides):
    ret = {
        "filename": "talk.md",
        "queue_claim": {
            "run_id": "reparse",
            "batch_id": "25",
            "reprocess_generation": 1,
        },
        "status": "processed",
        "processed_date": "2026-07-26",
        "transcript_source": "youtube_auto",
        "slide_source": "pptx",
        "rhetoric_notes": "DIMENSION 1 -- OPENING: cold open.",
        "areas_for_improvement": "1) Tighten the close.",
        "adherence_assessment": "Above the mode baseline.",
        "new_patterns": "",
        "summary_updates": "",
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
                 "evidence_source": "transcript", "evidence": "Four-act catalog."},
            ],
            "antipatterns_detected": [
                {"pattern_id": "ant-fonts", "confidence": "moderate",
                 "evidence_source": "static_slides", "evidence": "7.5pt body text."},
            ],
            "evidence_sources": ["transcript", "native_deck", "static_slides",
                                 "source_comparison"],
            "not_evaluable": [],
            "pattern_score": {"patterns_used": 1, "antipatterns_detected": 1, "score": 0},
        },
        "catalog_feedback": {
            "unmatched_observations": [{"observation": "controlling metaphor"}],
            "confusable_pairs": [],
            "definition_problems": [],
            "scoring_problems": [],
            "tensions": [],
        },
    }
    ret.update(overrides)
    return ret


def _write_tracking_db(
        tmp_path, returns, *, title=None, name="tracking-db.json",
        persisted_date=None):
    talks = []
    for ret in returns:
        talk = {
            "filename": ret["filename"],
            "title": title,
            "schema_version": 3,
            "status": ret["status"],
            "processed_date": (
                persisted_date or ret.get("processed_date") or "2026-07-26"),
            "reprocess_generation": ret["queue_claim"]["reprocess_generation"],
            "video_url": "https://youtu.be/AbCdEfGhI_1",
            "youtube_id": "AbCdEfGhI_1",
            "pptx_path": "Conference/Talk.pptx",
            "slides_url": "https://drive.google.com/file/d/slides-id/view",
            "pattern_scoring_schema_version": 2,
            "pattern_catalog_fingerprint": CATALOG_FINGERPRINT,
            "_queue_claim": {
                "schema_version": 2,
                **ret["queue_claim"],
                "claimed_at": "2026-07-31T18:00:00+00:00",
                "previous_status": "needs-reprocessing",
                "state": "completed",
                "released_at": "2026-07-31T18:05:00+00:00",
                "release_reason": "return_persisted",
                "result_status": ret["status"],
                "result_payload_sha256": _return_receipt(ret),
            },
        }
        if ret["status"] == "skipped_no_sources":
            talk.update({"video_url": None, "pptx_path": None, "slides_url": None})
        talks.append(talk)
    path = tmp_path / name
    path.write_text(json.dumps({"talks": talks}))
    return path


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


def test_renders_core_sections(write_analysis):
    md = write_analysis.render_analysis(
        _return(slides_local_path="slides/source.pdf"))
    assert md.startswith("# Rhetoric Analysis: talk")
    assert "**Filename:** talk.md" in md
    assert "**Processed:** 2026-07-26" in md
    assert "**Slides local path:** slides/source.pdf" in md
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
    assert "**Pattern score:** 0 (1 patterns − 1 antipatterns)" in md
    assert "| `narrative-arc` | strong | transcript | Four-act catalog. |" in md
    assert "| `ant-fonts` | moderate | static_slides | 7.5pt body text. |" in md


def test_per_slide_visual_becomes_a_table(write_analysis):
    md = write_analysis.render_analysis(_return())
    assert "### per_slide_visual" in md
    assert "| slide | background | content_type |" in md
    assert "| 1 | salmon | title |" in md


def test_pipes_and_newlines_do_not_break_table_rows(write_analysis):
    ret = _return()
    ret["pattern_observations"]["patterns_detected"] = [
        {"pattern_id": "triad", "confidence": "strong",
         "evidence_source": "transcript",
         "evidence": "He said a | b | c\nthen paused."}
    ]
    md = write_analysis.render_analysis(ret)
    rows = [ln for ln in md.splitlines() if ln.startswith("| `triad`")]
    assert len(rows) == 1, "the newline must not split the evidence across two rows"
    row = rows[0]
    # Splitting on UNESCAPED pipes is what a markdown renderer does; escaped
    # ones stay inside the cell.
    cells = [c for c in re.split(r"(?<!\\)\|", row)[1:-1]]
    assert len(cells) == 4
    assert "\\|" in cells[3]


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


def test_not_evaluable_patterns_render_with_source_and_reason(write_analysis):
    ret = _return()
    ret["pattern_observations"]["not_evaluable"] = [{
        "pattern_id": "composite-animation",
        "evidence_source": "static_slides",
        "reason": "Animation timing is absent from the PDF.",
    }]
    md = write_analysis.render_analysis(ret)
    assert "### Not Evaluable From Available Evidence" in md
    assert "| composite-animation | static_slides | Animation timing is absent" in md


def test_run_date_fills_missing_processed_date(write_analysis):
    ret = _return()
    del ret["processed_date"]
    md = write_analysis.render_analysis(ret, run_date="2026-07-26")
    assert "**Processed:** 2026-07-26" in md


def test_writer_run_date_wins_over_legacy_return_date(write_analysis):
    md = write_analysis.render_analysis(_return(), run_date="2026-01-01")
    assert "**Processed:** 2026-01-01" in md


def test_cli_renders_the_exact_canonical_stamp_persisted_in_db(
        write_analysis, tmp_path):
    batch = tmp_path / "batch-returns.json"
    out = tmp_path / "analyses"
    ret = _return(processed_date="2026-07-27T16:03:22.987654+02:00")
    batch.write_text(json.dumps([ret]))
    db = _write_tracking_db(
        tmp_path, [ret], persisted_date="2026-07-27T14:03:22+00:00")

    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(out),
         "--talks", str(db)],
        capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr
    body = (out / "talk.md").read_text()
    assert "**Processed:** 2026-07-27T14:03:22+00:00" in body
    assert "16:03:22" not in body


def test_cli_uses_persisted_stamp_when_return_omits_processed_date(
        write_analysis, tmp_path):
    batch = tmp_path / "batch-returns.json"
    out = tmp_path / "analyses"
    ret = _return()
    del ret["processed_date"]
    batch.write_text(json.dumps([ret]))
    db = _write_tracking_db(
        tmp_path, [ret], persisted_date="2026-07-27T14:03:22+00:00")

    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(out),
         "--talks", str(db)],
        capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "**Processed:** 2026-07-27T14:03:22+00:00" in \
        (out / "talk.md").read_text()


def test_cli_rejects_noncanonical_persisted_stamp_before_write(
        write_analysis, tmp_path):
    batch = tmp_path / "batch-returns.json"
    out = tmp_path / "analyses"
    ret = _return(processed_date="2026-07-27T16:03:22+02:00")
    batch.write_text(json.dumps([ret]))
    db = _write_tracking_db(
        tmp_path, [ret], persisted_date="2026-07-27T16:03:22+02:00")

    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(out),
         "--talks", str(db)],
        capture_output=True, text=True,
    )

    assert result.returncode == 1
    assert "is not the canonical stored stamp" in result.stderr
    assert not out.exists()


def test_cli_ignores_legacy_return_stamp_and_uses_persisted_value(
        write_analysis, tmp_path):
    batch = tmp_path / "batch-returns.json"
    out = tmp_path / "analyses"
    ret = _return(processed_date="2026-07-26")
    batch.write_text(json.dumps([ret]))
    db = _write_tracking_db(
        tmp_path, [ret], persisted_date="2026-07-27T14:03:22+00:00")

    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(out),
         "--talks", str(db)],
        capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "**Processed:** 2026-07-27T14:03:22+00:00" in \
        (out / "talk.md").read_text()


def test_cli_rejects_explicit_return_timestamp_conflicting_with_persisted_batch(
        write_analysis, tmp_path):
    batch = tmp_path / "batch-returns.json"
    out = tmp_path / "analyses"
    ret = _return(processed_date="2026-07-27T08:00:00+00:00")
    batch.write_text(json.dumps([ret]))
    db = _write_tracking_db(
        tmp_path, [ret], persisted_date="2026-07-27T14:03:22+00:00")

    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(out),
         "--talks", str(db)],
        capture_output=True, text=True,
    )

    assert result.returncode == 1
    assert "explicit return processed_date" in result.stderr
    assert "conflicts with persisted batch stamp" in result.stderr
    assert not out.exists()


def test_cli_checks_requested_batch_stamp_even_when_return_has_a_date(
        write_analysis, tmp_path):
    batch = tmp_path / "batch-returns.json"
    out = tmp_path / "analyses"
    ret = _return(processed_date="2026-07-26")
    batch.write_text(json.dumps([ret]))
    db = _write_tracking_db(
        tmp_path, [ret], persisted_date="2026-07-27T14:03:22+00:00")

    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(out),
         "--talks", str(db), "--run-date", "2026-07-27T14:03:23+00:00"],
        capture_output=True, text=True,
    )

    assert result.returncode == 1
    assert "--run-date" in result.stderr
    assert "does not match persisted value" in result.stderr
    assert not out.exists()


def test_persist_then_write_uses_one_exact_batch_timestamp(
        persist_results, write_analysis, tmp_path):
    batch = tmp_path / "batch-returns.json"
    out = tmp_path / "analyses"
    authoritative = "2026-07-27T14:03:22+00:00"
    ret = _return(processed_date="2026-07-26")
    batch.write_text(json.dumps([ret]))
    db = _write_tracking_db(tmp_path, [ret], persisted_date="2026-04-09")
    payload = json.loads(db.read_text())
    talk = payload["talks"][0]
    talk["status"] = "reprocessing-inflight"
    claim = talk["_queue_claim"]
    claim["state"] = "claimed"
    for field in (
            "released_at", "release_reason", "result_status",
            "result_payload_sha256"):
        del claim[field]
    db.write_text(json.dumps(payload))

    persisted = subprocess.run(
        [sys.executable, persist_results.__file__, str(db), str(batch),
         "--run-date", authoritative],
        capture_output=True, text=True,
    )
    assert persisted.returncode == 0, persisted.stderr

    written = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(out),
         "--talks", str(db), "--run-date", authoritative],
        capture_output=True, text=True,
    )

    assert written.returncode == 0, written.stderr
    stored = json.loads(db.read_text())["talks"][0]
    assert stored["processed_date"] == authoritative
    assert stored["_queue_claim"]["released_at"] == authoritative
    body = (out / "talk.md").read_text()
    assert f"**Processed:** {authoritative}" in body
    assert "**Processed:** 2026-07-26" not in body


def test_nested_structured_fields_are_preserved(write_analysis):
    md = write_analysis.render_analysis(_return())
    assert "### Additional structured fields" in md
    assert '"act_structure"' in md


def test_cli_writes_files_and_reports(write_analysis, tmp_path):
    batch = tmp_path / "batch-returns.json"
    out = tmp_path / "analyses"
    returns = [_return(), _return(filename="other.md")]
    batch.write_text(json.dumps(returns))
    db = _write_tracking_db(tmp_path, returns)
    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(out),
         "--run-date", "2026-07-26", "--talks", str(db)],
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
    out = tmp_path / "analyses"
    returns = [_return()]
    batch.write_text(json.dumps(returns))
    db = _write_tracking_db(tmp_path, returns, title="Real Title")
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
    returns = [_return(filename="../tracking-database.json")]
    batch.write_text(json.dumps(returns))
    db = _write_tracking_db(tmp_path, returns, name="queue-db.json")
    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(out),
         "--talks", str(db)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert victim.read_text() == '{"talks": []}', "the sibling file was overwritten"
    assert (out / "tracking-database.json.md").exists()


def test_cli_rejects_filename_that_names_no_file(write_analysis, tmp_path):
    batch = tmp_path / "batch-returns.json"
    returns = [_return(filename="../")]
    batch.write_text(json.dumps(returns))
    db = _write_tracking_db(tmp_path, returns)
    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(tmp_path / "a"),
         "--talks", str(db)],
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
    returns = [_return()]
    batch.write_text(json.dumps(returns))
    db = _write_tracking_db(tmp_path, returns)
    # A regular file where the output directory should be: makedirs raises OSError.
    blocker = tmp_path / "blocked"
    blocker.write_text("i am a file, not a directory")
    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(blocker),
         "--talks", str(db)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "cannot create output directory" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_non_object_return_entry_is_actionable(write_analysis, tmp_path):
    """An array of filenames is the plausible operator mistake — it passes the
    is-a-list check and then dies on .get()."""
    batch = tmp_path / "batch-returns.json"
    batch.write_text(json.dumps(["talk.md", "other.md"]))
    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(tmp_path / "a")],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "subagent return must be an object" in result.stderr
    assert "Traceback" not in result.stderr


def test_skipped_status_never_overwrites_an_existing_analysis(write_analysis, tmp_path):
    """A later skipped return must not replace an earlier good file with a stub —
    the file is keyed on the talk, so the overwrite is silent data loss."""
    batch = tmp_path / "batch-returns.json"
    out = tmp_path / "analyses"
    out.mkdir()
    good = out / "talk.md"
    good.write_text("# real analysis from a successful run\n")
    returns = [_skipped_return()]
    batch.write_text(json.dumps(returns))
    db = _write_tracking_db(tmp_path, returns)
    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(out),
         "--talks", str(db)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert good.read_text() == "# real analysis from a successful run\n"
    report = json.loads(result.stdout)
    assert report["written"] == 0
    assert report["skipped"] == [{"filename": "talk.md", "status": "skipped_no_sources"}]


def test_processed_partial_still_writes(write_analysis, tmp_path):
    batch = tmp_path / "batch-returns.json"
    out = tmp_path / "analyses"
    returns = [_return(status="processed_partial")]
    batch.write_text(json.dumps(returns))
    db = _write_tracking_db(tmp_path, returns)
    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(out),
         "--talks", str(db)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (out / "talk.md").exists()
    assert json.loads(result.stdout)["written"] == 1


def test_return_without_status_is_rejected_before_writing(write_analysis, tmp_path):
    """Missing status cannot strand a talk in its in-flight queue state."""
    ret = _return()
    del ret["status"]
    batch = tmp_path / "batch-returns.json"
    out = tmp_path / "analyses"
    batch.write_text(json.dumps([ret]))
    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(out)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "status is required" in result.stderr
    assert not out.exists()


def test_cli_requires_tracking_db_for_generation_check(write_analysis, tmp_path):
    batch = tmp_path / "batch-returns.json"
    batch.write_text(json.dumps([_return()]))
    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(tmp_path / "a")],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "--talks" in result.stderr
    assert not (tmp_path / "a").exists()


def test_stale_generation_cannot_overwrite_analysis(write_analysis, tmp_path):
    batch = tmp_path / "batch-returns.json"
    out = tmp_path / "analyses"
    out.mkdir()
    target = out / "talk.md"
    target.write_text("# current generation\n")
    ret = _return()
    batch.write_text(json.dumps([ret]))
    db = _write_tracking_db(tmp_path, [ret])
    payload = json.loads(db.read_text())
    payload["talks"][0]["reprocess_generation"] = 2
    payload["talks"][0]["_queue_claim"]["reprocess_generation"] = 2
    db.write_text(json.dumps(payload))
    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(out),
         "--talks", str(db)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "does not match" in result.stderr
    assert target.read_text() == "# current generation\n"


def test_top_level_generation_mismatch_cannot_overwrite_analysis(
        write_analysis, tmp_path):
    batch = tmp_path / "batch-returns.json"
    out = tmp_path / "analyses"
    out.mkdir()
    target = out / "talk.md"
    target.write_text("# current generation\n")
    ret = _return()
    batch.write_text(json.dumps([ret]))
    db = _write_tracking_db(tmp_path, [ret])
    payload = json.loads(db.read_text())
    payload["talks"][0]["reprocess_generation"] = 2
    db.write_text(json.dumps(payload))

    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(out),
         "--talks", str(db)],
        capture_output=True, text=True,
    )

    assert result.returncode == 1
    assert "active claim generation 1 disagrees with talk generation 2" in result.stderr
    assert target.read_text() == "# current generation\n"


def test_completed_claim_requires_exact_schema_before_analysis_write(
        write_analysis, tmp_path):
    batch = tmp_path / "batch-returns.json"
    out = tmp_path / "analyses"
    out.mkdir()
    target = out / "talk.md"
    target.write_text("# current generation\n")
    ret = _return()
    batch.write_text(json.dumps([ret]))
    db = _write_tracking_db(tmp_path, [ret])
    payload = json.loads(db.read_text())
    payload["talks"][0]["_queue_claim"]["unexpected"] = "field"
    db.write_text(json.dumps(payload))

    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(out),
         "--talks", str(db)],
        capture_output=True, text=True,
    )

    assert result.returncode == 1
    assert "must use exactly the schema fields" in result.stderr
    assert "unexpected" in result.stderr
    assert target.read_text() == "# current generation\n"


def test_substituted_return_payload_cannot_overwrite_persisted_analysis(
        write_analysis, tmp_path):
    original = _return()
    db = _write_tracking_db(tmp_path, [original])
    substituted = _return(rhetoric_notes="substituted after persistence")
    batch = tmp_path / "batch-returns.json"
    batch.write_text(json.dumps([substituted]))
    out = tmp_path / "analyses"
    out.mkdir()
    target = out / "talk.md"
    target.write_text("# persisted generation\n")

    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(out),
         "--talks", str(db)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "payload SHA-256 does not match" in result.stderr
    assert target.read_text() == "# persisted generation\n"


@pytest.mark.parametrize(
    ("field", "bad_value", "diagnostic"),
    [
        ("pattern_scoring_schema_version", 1, "pattern_scoring_schema_version"),
        ("pattern_catalog_fingerprint", "0" * 64, "pattern_catalog_fingerprint"),
    ],
)
def test_renderer_requires_the_catalog_generation_persisted_for_each_talk(
        write_analysis, tmp_path, field, bad_value, diagnostic):
    ret = _return()
    db = _write_tracking_db(tmp_path, [ret])
    payload = json.loads(db.read_text())
    payload["talks"][0][field] = bad_value
    db.write_text(json.dumps(payload))
    batch = tmp_path / "batch-returns.json"
    batch.write_text(json.dumps([ret]))
    out = tmp_path / "analyses"

    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(out),
         "--talks", str(db)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert diagnostic in result.stderr
    assert not out.exists()


def test_analysis_writer_requires_persisted_completed_claim(
        write_analysis, tmp_path):
    batch = tmp_path / "batch-returns.json"
    out = tmp_path / "analyses"
    ret = _return()
    batch.write_text(json.dumps([ret]))
    db = _write_tracking_db(tmp_path, [ret])
    payload = json.loads(db.read_text())
    talk = payload["talks"][0]
    talk["status"] = "reprocessing-inflight"
    claim = talk["_queue_claim"]
    claim["state"] = "claimed"
    for field in (
            "released_at", "release_reason", "result_status",
            "result_payload_sha256"):
        del claim[field]
    db.write_text(json.dumps(payload))

    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(out),
         "--talks", str(db)],
        capture_output=True, text=True,
    )

    assert result.returncode == 1
    assert "closed or stranded member" in result.stderr
    assert not out.exists()


def test_analysis_writer_rejects_partial_completed_batch_before_any_write(
        write_analysis, tmp_path):
    batch = tmp_path / "batch-returns.json"
    out = tmp_path / "analyses"
    out.mkdir()
    existing = out / "a.md"
    existing.write_text("# current analysis\n")
    all_returns = [_return(filename=f"{name}.md") for name in ("a", "b", "c")]
    batch.write_text(json.dumps(all_returns[:2]))
    db = _write_tracking_db(tmp_path, all_returns)

    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(out),
         "--talks", str(db)],
        capture_output=True, text=True,
    )

    assert result.returncode == 1
    assert "missing ['c.md']" in result.stderr
    assert existing.read_text() == "# current analysis\n"
    assert sorted(path.name for path in out.iterdir()) == ["a.md"]


def test_non_object_db_member_is_actionable_before_analysis_write(
        write_analysis, tmp_path):
    ret = _return()
    batch = tmp_path / "batch-returns.json"
    batch.write_text(json.dumps([ret]))
    db = _write_tracking_db(tmp_path, [ret])
    payload = json.loads(db.read_text())
    payload["talks"].append("not-a-talk")
    db.write_text(json.dumps(payload))
    out = tmp_path / "analyses"

    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(out),
         "--talks", str(db)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "talks[1] must be a JSON object" in result.stderr
    assert "Traceback" not in result.stderr
    assert not out.exists()


def test_future_talk_schema_cannot_authorize_analysis_write(
        write_analysis, tmp_path):
    ret = _return()
    batch = tmp_path / "batch-returns.json"
    batch.write_text(json.dumps([ret]))
    db = _write_tracking_db(tmp_path, [ret])
    payload = json.loads(db.read_text())
    payload["talks"][0]["schema_version"] = 99
    db.write_text(json.dumps(payload))
    out = tmp_path / "analyses"

    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(out),
         "--talks", str(db)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "future talk schema_version 99" in result.stderr
    assert not out.exists()


def test_tracking_database_symlink_is_rejected_before_analysis_write(
        write_analysis, tmp_path):
    ret = _return()
    batch = tmp_path / "batch-returns.json"
    batch.write_text(json.dumps([ret]))
    target = _write_tracking_db(tmp_path, [ret])
    before = target.read_bytes()
    link = tmp_path / "tracking-link.json"
    link.symlink_to(target.name)
    out = tmp_path / "analyses"

    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(out),
         "--talks", str(link)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "symbolic link" in result.stderr
    assert link.is_symlink()
    assert target.read_bytes() == before
    assert not out.exists()


def test_kcdc_wrong_transcript_return_cannot_overwrite_analysis(
        write_analysis, return_validation, tmp_path):
    batch = tmp_path / "batch-returns.json"
    out = tmp_path / "analyses"
    out.mkdir()
    target = out / "talk.md"
    target.write_text("# slide-only corrected analysis\n")
    ret = _return(status="processed_partial", slide_source="pdf")
    ret["pattern_observations"]["evidence_sources"] = [
        "transcript", "static_slides"]
    _complete_unavailable_source_gates(return_validation, ret)
    batch.write_text(json.dumps([ret]))
    db = _write_tracking_db(tmp_path, [ret])
    payload = json.loads(db.read_text())
    talk = payload["talks"][0]
    talk.update({
        "video_url": None,
        "youtube_id": None,
        "pptx_path": None,
        "google_drive_id": "slides-id",
        "transcript_source": "none",
        "slide_source": "pdf",
    })
    db.write_text(json.dumps(payload))

    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(out),
         "--talks", str(db)],
        capture_output=True, text=True,
    )

    assert result.returncode == 1
    assert "no transcript reference or active video source" in result.stderr
    assert target.read_text() == "# slide-only corrected analysis\n"


def test_carriage_returns_do_not_break_table_rows(write_analysis):
    ret = _return()
    ret["pattern_observations"]["patterns_detected"] = [
        {"pattern_id": "triad", "confidence": "strong",
         "evidence_source": "transcript",
         "evidence": "line one\r\nline two\rline three"}
    ]
    md = write_analysis.render_analysis(ret)
    rows = [ln for ln in md.splitlines() if ln.startswith("| `triad`")]
    assert len(rows) == 1
    assert "\r" not in rows[0]


@pytest.mark.parametrize("bad", ["", ".", "..", "...", "....", "/", "../",
                                 "   ", "\n", " . "])
def test_names_that_resolve_to_no_file_are_rejected(write_analysis, bad):
    """The docstring promised dots-only names are rejected; an equality check
    against ("", ".", "..") let "..." through and produced a "....md" file."""
    with pytest.raises(SystemExit):
        write_analysis.safe_output_name(bad)


def test_output_name_strips_whitespace_and_respects_case(write_analysis):
    """`filename` is model-generated, so a stray newline or trailing space must
    not reach the filesystem, and TALK.MD must not become TALK.MD.md."""
    assert write_analysis.safe_output_name("  talk.md\n") == "talk.md"
    assert write_analysis.safe_output_name("TALK.MD") == "TALK.MD"
    assert write_analysis.safe_output_name("Talk.Md") == "Talk.Md"
    assert write_analysis.safe_output_name(" talk ") == "talk.md"


def test_target_key_normalizes_basename_case_and_unicode(write_analysis):
    assert write_analysis.output_target_key("first/TALK.MD") == \
        write_analysis.output_target_key("second/talk.md")
    assert write_analysis.output_target_key("first/Cafe\N{COMBINING ACUTE ACCENT}.md") == \
        write_analysis.output_target_key("second/Caf\N{LATIN SMALL LETTER E WITH ACUTE}.MD")


def test_cli_rejects_normalized_target_collision_before_any_write(
        write_analysis, tmp_path):
    batch = tmp_path / "batch-returns.json"
    out = tmp_path / "analyses"
    out.mkdir()
    existing = out / "TALK.MD"
    existing.write_text("# existing analysis\n")
    returns = [
        _return(filename="first/TALK.MD"),
        _return(filename="second/talk.md"),
    ]
    batch.write_text(json.dumps(returns))
    db = _write_tracking_db(tmp_path, returns)

    result = subprocess.run(
        [sys.executable, write_analysis.__file__, str(batch), str(out),
         "--talks", str(db)],
        capture_output=True, text=True,
    )

    assert result.returncode == 1
    assert "resolve to the same analysis target" in result.stderr
    assert existing.read_text() == "# existing analysis\n"
    assert [path.name for path in out.iterdir()] == ["TALK.MD"]


def test_none_valued_structured_fields_are_omitted(write_analysis):
    """A None means 'could not determine'; rendering the literal 'None' reads as
    a finding rather than an absence."""
    md = write_analysis.render_analysis(_return(structured_data={
        "slide_count": 31,
        "delivery_language": None,
        "meme_count": 0,
    }))
    assert "- **slide_count:** 31" in md
    assert "- **meme_count:** 0" in md, "0 is a determined value, not an absence"
    assert "delivery_language" not in md


def test_cli_missing_input_file_is_actionable(write_analysis, tmp_path):
    result = subprocess.run(
        [sys.executable, write_analysis.__file__,
         str(tmp_path / "nope.json"), str(tmp_path / "a")],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "not found" in result.stderr
