"""Contract tests for the shared vault-ingress return validator."""

import copy
import json
import os
import subprocess
import sys

import pytest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VALIDATE_SCRIPT = os.path.join(
    REPO_ROOT, "skills", "vault-ingress", "scripts", "validate-returns.py")


def _return(**overrides):
    value = {
        "filename": "talk.md",
        "status": "processed",
        "slide_source": "pptx",
        "transcript_source": "youtube_auto",
        "rhetoric_notes": "Dimensions 1 through 13.",
        "areas_for_improvement": "Tighten the close.",
        "adherence_assessment": "Near the running baseline.",
        "new_patterns": "",
        "summary_updates": "",
        "structured_data": {
            "delivery_language": "en",
            "co_presenter": False,
        },
        "verbatim_examples": {"jokes": []},
        "pattern_observations": {
            "patterns_detected": [{
                "pattern_id": "narrative-arc",
                "confidence": "strong",
                "evidence": "The argument moves through four named acts.",
                "dimensions": [2, 5],
            }],
            "antipatterns_detected": [{
                "pattern_id": "shortchanged",
                "confidence": "weak",
                "evidence": "The final summary is compressed.",
                "dimensions": [12, 14],
            }],
            "pattern_score": {
                "patterns_used": 1,
                "antipatterns_detected": 1,
                "score": 0,
            },
        },
        "catalog_feedback": {
            "unmatched_observations": [],
            "confusable_pairs": [],
            "definition_problems": [],
            "scoring_problems": [],
            "tensions": [],
        },
    }
    value.update(overrides)
    return value


def _error(return_validation, value):
    with pytest.raises(return_validation.ReturnValidationError) as excinfo:
        return_validation.validate_batch([value])
    return str(excinfo.value)


def test_valid_return_resolves_the_catalog_fingerprint(return_validation):
    catalog = return_validation.validate_batch([_return()])
    assert len(catalog.entries) == 111
    assert len(catalog.fingerprint) == 64


@pytest.mark.parametrize("status", [None, "reprocessing-inflight", "skipped_no_video"])
def test_status_must_be_a_terminal_return_state(return_validation, status):
    value = _return()
    if status is None:
        del value["status"]
    else:
        value["status"] = status
    assert "status is required" in _error(return_validation, value)


def test_unknown_pattern_id_is_rejected(return_validation):
    value = _return()
    value["pattern_observations"]["patterns_detected"][0]["pattern_id"] = \
        "terminal-as-deck-until-it-exists"
    assert "is not in the Presentation Patterns catalog" in _error(return_validation, value)


def test_pattern_in_antipattern_lane_is_rejected(return_validation):
    value = _return()
    value["pattern_observations"]["antipatterns_detected"][0]["pattern_id"] = \
        "narrative-arc"
    assert "catalog pattern" in _error(return_validation, value)


def test_unobservable_pattern_is_rejected(return_validation):
    value = _return()
    value["pattern_observations"]["patterns_detected"][0]["pattern_id"] = \
        "red-yellow-green"
    assert "observable:false" in _error(return_validation, value)


def test_duplicate_detection_is_rejected(return_validation):
    value = _return()
    value["pattern_observations"]["patterns_detected"].append(
        copy.deepcopy(value["pattern_observations"]["patterns_detected"][0]))
    assert "duplicate id" in _error(return_validation, value)


@pytest.mark.parametrize("field,bad", [
    ("confidence", "certain"),
    ("evidence", ""),
    ("dimensions", [0, 15]),
])
def test_detection_evidence_contract_is_enforced(return_validation, field, bad):
    value = _return()
    value["pattern_observations"]["patterns_detected"][0][field] = bad
    assert field in _error(return_validation, value)


@pytest.mark.parametrize("field,bad", [
    ("patterns_used", 2),
    ("antipatterns_detected", 0),
    ("score", 1),
])
def test_all_declared_score_counts_are_cross_checked(
        return_validation, field, bad):
    value = _return()
    value["pattern_observations"]["pattern_score"][field] = bad
    assert f"pattern_score.{field}" in _error(return_validation, value)


def test_co_presenter_requires_a_name_array(return_validation):
    value = _return()
    value["structured_data"]["co_presenter"] = True
    assert "co_presenters must name" in _error(return_validation, value)


def test_co_presenters_rejects_a_scalar(return_validation):
    value = _return()
    value["structured_data"].update({"co_presenter": True, "co_presenters": "Alex"})
    assert "array of non-empty names" in _error(return_validation, value)


def test_delivery_language_requires_a_code(return_validation):
    value = _return()
    value["structured_data"]["delivery_language"] = "English"
    assert "lowercase language code" in _error(return_validation, value)


def test_catalog_feedback_requires_every_audit_lane(return_validation):
    value = _return()
    del value["catalog_feedback"]["definition_problems"]
    assert "catalog_feedback.definition_problems is required" in _error(
        return_validation, value)


def test_prose_fields_reject_shape_drift(return_validation):
    value = _return()
    value["summary_updates"] = [{"section": 4, "content": "new"}]
    assert "summary_updates must be a string" in _error(return_validation, value)


def test_duplicate_batch_filename_is_rejected(return_validation):
    assert "duplicate return filename" in _error_batch(
        return_validation, [_return(), _return()])


def _error_batch(return_validation, values):
    with pytest.raises(return_validation.ReturnValidationError) as excinfo:
        return_validation.validate_batch(values)
    return str(excinfo.value)


@pytest.mark.parametrize("path", [
    "status",
    "structured_data",
    "unknown.path",
    "structured_data..slide_count",
])
def test_clear_fields_is_confined_to_analysis_owned_leaves(return_validation, path):
    value = _return(clear_fields=[path])
    assert "clear_fields" in _error(return_validation, value)


def test_validator_cli_emits_structured_report(tmp_path):
    batch = tmp_path / "returns.json"
    batch.write_text(json.dumps([_return()]))
    result = subprocess.run(
        [sys.executable, VALIDATE_SCRIPT, str(batch)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["valid"] is True
    assert report["returns"] == 1
    assert report["catalog_entries"] == 111


def test_validator_cli_reports_the_filename_on_failure(tmp_path):
    batch = tmp_path / "returns.json"
    value = _return()
    del value["status"]
    batch.write_text(json.dumps([value]))
    result = subprocess.run(
        [sys.executable, VALIDATE_SCRIPT, str(batch)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "talk.md" in result.stderr
    assert "status is required" in result.stderr
