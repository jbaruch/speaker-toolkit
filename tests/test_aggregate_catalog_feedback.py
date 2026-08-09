"""Tests for deterministic, read-only catalog-feedback intake."""

import json
import subprocess
import sys

import pytest


def _catalog_file(path, catalog_id, polarity, *, name=None, aliases=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    name_field = f"name: {name}\n" if name is not None else ""
    aliases_field = f"aliases: {json.dumps(aliases)}\n" if aliases is not None else ""
    path.write_text(
        "---\n"
        f"id: {catalog_id}\n"
        f"{name_field}"
        f"type: {polarity}\n"
        f"{aliases_field}"
        "---\n\n"
        f"# {catalog_id}\n",
        encoding="utf-8",
    )


@pytest.fixture
def catalog_fixture(tmp_path):
    root = tmp_path / "patterns"
    _catalog_file(
        root / "prepare" / "alpha.md",
        "alpha",
        "pattern",
        name="Alpha Signal",
        aliases=["First Move"],
    )
    _catalog_file(root / "build" / "_anti_beta.md", "beta", "antipattern")
    _catalog_file(root / "deliver" / "gamma.md", "gamma", "pattern")
    return root


def _feedback():
    return {
        "unmatched_observations": [
            {
                "observation": "The room predicts before the reveal.",
                "why_no_pattern_fits": "The existing mechanism differs.",
                "proposed_name": "Fresh Move",
                "proposed_polarity": "pattern",
            }
        ],
        "tensions": [
            {
                "pattern_ids": ["alpha", "beta"],
                "catalog_polarities": {
                    "alpha": "pattern",
                    "beta": "antipattern",
                },
                "nature": "Using alpha can trigger beta.",
                "evidence": "Both occur in the same minute.",
            }
        ],
        "definition_problems": [
            {
                "pattern_id": "beta",
                "catalog_polarity": "antipattern",
                "problem": "ambiguous",
                "detail": "Its threshold is not testable.",
            }
        ],
        "scoring_problems": [
            {
                "issue": "Confidence is unweighted.",
                "detail": "Weak and strong evidence both count one.",
                "polarity": "neutral",
            }
        ],
        "confusable_pairs": [
            {
                "pattern_ids": ["alpha", "gamma"],
                "detail": "The boundary is not observable.",
            }
        ],
    }


def _return(filename="talk.md", feedback=None):
    return {
        "filename": filename,
        "status": "processed",
        "catalog_feedback": _feedback() if feedback is None else feedback,
    }


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")
    return path


def _issues(report):
    issues = []
    issues.extend(report["catalog"]["errors"])
    issues.extend(report["validation"]["errors"])
    for item in report["entries"]["invalid"]:
        issues.extend(item["issues"])
    for item in report["returns"]["invalid"]:
        issues.extend(item["issues"])
    for item in report["inputs"]["invalid"]:
        issues.extend(item.get("issues", []))
    return {item["code"] for item in issues}


def test_normalize_suggestion_is_format_only(aggregate_catalog_feedback):
    normalize = aggregate_catalog_feedback.normalize_suggestion
    assert normalize("  Fresh_Move!  ") == "fresh-move"
    assert normalize("Fresh—Move") == "fresh-move"
    assert normalize("Café Move") == "café-move"


def test_valid_five_lane_return_preserves_provenance_and_groups_ids(
    aggregate_catalog_feedback,
    catalog_fixture,
    tmp_path,
):
    source = _write(tmp_path / "returns" / "one.json", _return())

    report = aggregate_catalog_feedback.aggregate_feedback(
        [source], catalog_path=catalog_fixture
    )

    assert report["ok"] is True
    assert report["input_summary"] == {"accepted": 1, "rejected": 0, "invalid": 0}
    assert report["entry_summary"] == {"accepted": 5, "invalid": 0, "warnings": 0}
    accepted = report["entries"]["accepted"]
    assert {item["provenance"]["feedback_lane"] for item in accepted} == set(
        aggregate_catalog_feedback.LANES
    )
    assert all(
        item["provenance"]["source_path"] == str(source.resolve()) for item in accepted
    )
    assert all(item["provenance"]["talk_filename"] == "talk.md" for item in accepted)
    assert all(item["provenance"]["source_return_index"] == 0 for item in accepted)

    groups = {item["catalog_id"]: item for item in report["exact_catalog_ids"]}
    assert groups["alpha"]["polarity"] == "pattern"
    assert groups["alpha"]["occurrence_count"] == 2
    assert groups["beta"]["polarity"] == "antipattern"
    assert groups["beta"]["lane_counts"] == {
        "definition_problems": 1,
        "tensions": 1,
    }
    assert report["normalized_suggestions"][0]["normalized_suggestion"] == "fresh-move"


def test_normalized_suggestion_recurrence_counts_talks_and_returns(
    aggregate_catalog_feedback,
    catalog_fixture,
    tmp_path,
):
    directory = tmp_path / "returns"
    first = _return("one.md")
    second = _return("two.md")
    second["catalog_feedback"]["unmatched_observations"][0]["proposed_name"] = (
        "fresh_move"
    )
    third = _return("two.md")
    third["catalog_feedback"]["unmatched_observations"][0]["proposed_name"] = (
        "Fresh-Move!"
    )
    _write(directory / "a.json", [first, second])
    _write(directory / "nested" / "b.json", third)

    report = aggregate_catalog_feedback.aggregate_feedback(
        [directory], catalog_path=catalog_fixture
    )

    group = next(
        item
        for item in report["normalized_suggestions"]
        if item["normalized_suggestion"] == "fresh-move"
    )
    assert group["occurrence_count"] == 3
    assert group["talk_count"] == 2
    assert group["source_return_count"] == 3
    assert group["polarity_status"] == "consistent"
    assert {item["value"] for item in group["variants"]} == {
        "Fresh Move",
        "fresh_move",
        "Fresh-Move!",
    }


def test_exact_catalog_ids_are_not_folded_into_suggestions(
    aggregate_catalog_feedback,
    catalog_fixture,
    tmp_path,
):
    feedback = _feedback()
    feedback["unmatched_observations"][0]["proposed_name"] = "Alpha"
    source = _write(tmp_path / "return.json", _return(feedback=feedback))

    report = aggregate_catalog_feedback.aggregate_feedback(
        [source], catalog_path=catalog_fixture
    )

    assert "suggestion_matches_catalog_id" in _issues(report)
    assert all(
        item["normalized_suggestion"] != "alpha"
        for item in report["normalized_suggestions"]
    )
    assert any(item["catalog_id"] == "alpha" for item in report["exact_catalog_ids"])


@pytest.mark.parametrize(
    "proposed_name",
    [
        "Alpha Signal",
        "Alpha—Signal!",
        "First_Move",
    ],
)
def test_existing_catalog_names_and_aliases_are_not_novel_suggestions(
    aggregate_catalog_feedback,
    catalog_fixture,
    tmp_path,
    proposed_name,
):
    feedback = _feedback()
    feedback["unmatched_observations"][0]["proposed_name"] = proposed_name
    source = _write(tmp_path / "return.json", _return(feedback=feedback))

    report = aggregate_catalog_feedback.aggregate_feedback(
        [source], catalog_path=catalog_fixture
    )

    assert report["ok"] is False
    assert "suggestion_matches_catalog_alias" in _issues(report)
    invalid = [
        item
        for item in report["entries"]["invalid"]
        if item["provenance"]["feedback_lane"] == "unmatched_observations"
    ]
    assert invalid[0]["issues"][0]["catalog_id"] == "alpha"


def test_missing_legacy_suggestion_polarity_is_warning_not_rejection(
    aggregate_catalog_feedback,
    catalog_fixture,
    tmp_path,
):
    feedback = _feedback()
    del feedback["unmatched_observations"][0]["proposed_polarity"]
    source = _write(tmp_path / "legacy.json", _return(feedback=feedback))

    report = aggregate_catalog_feedback.aggregate_feedback(
        [source], catalog_path=catalog_fixture
    )

    assert report["ok"] is True
    assert report["input_summary"]["accepted"] == 1
    assert report["normalized_suggestions"][0]["polarity_status"] == "unspecified"
    assert {item["code"] for item in report["validation"]["warnings"]} == {
        "suggestion_polarity_missing"
    }


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("bad_suggestion_polarity", "suggestion_polarity_invalid"),
        ("wrong_catalog_polarity", "catalog_polarity_mismatch"),
        ("wrong_pair_polarities", "catalog_polarity_mismatch"),
        ("non_neutral_scoring", "lane_polarity_invalid"),
    ],
)
def test_lane_polarity_mismatches_are_invalid(
    aggregate_catalog_feedback,
    catalog_fixture,
    tmp_path,
    mutation,
    code,
):
    feedback = _feedback()
    if mutation == "bad_suggestion_polarity":
        feedback["unmatched_observations"][0]["proposed_polarity"] = "positive"
    elif mutation == "wrong_catalog_polarity":
        feedback["definition_problems"][0]["catalog_polarity"] = "pattern"
    elif mutation == "wrong_pair_polarities":
        feedback["tensions"][0]["catalog_polarities"]["beta"] = "pattern"
    elif mutation == "non_neutral_scoring":
        feedback["scoring_problems"][0]["polarity"] = "antipattern"
    source = _write(tmp_path / f"{mutation}.json", _return(feedback=feedback))

    report = aggregate_catalog_feedback.aggregate_feedback(
        [source], catalog_path=catalog_fixture
    )

    assert report["ok"] is False
    assert report["input_summary"]["invalid"] == 1
    assert code in _issues(report)


def test_cross_return_suggestion_polarity_conflict_is_reported(
    aggregate_catalog_feedback,
    catalog_fixture,
    tmp_path,
):
    first = _return("first.md")
    second = _return("second.md")
    second["catalog_feedback"]["unmatched_observations"][0]["proposed_polarity"] = (
        "antipattern"
    )
    source = _write(tmp_path / "batch.json", [first, second])

    report = aggregate_catalog_feedback.aggregate_feedback(
        [source], catalog_path=catalog_fixture
    )

    group = report["normalized_suggestions"][0]
    assert group["polarity_status"] == "conflict"
    assert group["asserted_polarities"] == ["antipattern", "pattern"]
    assert "suggestion_polarity_conflict" in _issues(report)
    assert report["ok"] is False


def test_confusable_pair_requires_exactly_two_ids_but_tension_allows_more(
    aggregate_catalog_feedback,
    catalog_fixture,
    tmp_path,
):
    feedback = _feedback()
    feedback["confusable_pairs"][0]["pattern_ids"] = ["alpha", "beta", "gamma"]
    feedback["tensions"][0]["pattern_ids"] = ["alpha", "beta", "gamma"]
    del feedback["tensions"][0]["catalog_polarities"]
    source = _write(tmp_path / "arity.json", _return(feedback=feedback))

    report = aggregate_catalog_feedback.aggregate_feedback(
        [source], catalog_path=catalog_fixture
    )

    invalid = [
        item
        for item in report["entries"]["invalid"]
        if item["provenance"]["feedback_lane"] == "confusable_pairs"
    ]
    assert len(invalid) == 1
    assert invalid[0]["issues"][0]["code"] == "catalog_id_count_invalid"
    assert any(
        item["provenance"]["feedback_lane"] == "tensions"
        for item in report["entries"]["accepted"]
    )


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("unknown_lane", "feedback_lane_unsupported"),
        ("lane_not_array", "feedback_lane_not_array"),
        ("entry_not_object", "feedback_entry_not_object"),
        ("missing_text", "feedback_text_missing"),
        ("unknown_id", "catalog_id_unknown"),
        ("duplicate_ids", "catalog_ids_duplicate"),
    ],
)
def test_feedback_lane_shape_validation(
    aggregate_catalog_feedback,
    catalog_fixture,
    tmp_path,
    mutation,
    code,
):
    feedback = _feedback()
    if mutation == "unknown_lane":
        feedback["schema_problems"] = [{"field": "x", "detail": "y"}]
    elif mutation == "lane_not_array":
        feedback["tensions"] = {"pattern_ids": ["alpha", "beta"]}
    elif mutation == "entry_not_object":
        feedback["scoring_problems"] = ["bad shape"]
    elif mutation == "missing_text":
        feedback["definition_problems"][0]["detail"] = " "
    elif mutation == "unknown_id":
        feedback["definition_problems"][0]["pattern_id"] = "invented-id"
    elif mutation == "duplicate_ids":
        feedback["confusable_pairs"][0]["pattern_ids"] = ["alpha", "alpha"]
    source = _write(tmp_path / f"{mutation}.json", _return(feedback=feedback))

    report = aggregate_catalog_feedback.aggregate_feedback(
        [source], catalog_path=catalog_fixture
    )

    assert code in _issues(report)
    assert report["ok"] is False


def test_inputs_are_classified_accepted_rejected_and_invalid(
    aggregate_catalog_feedback,
    catalog_fixture,
    tmp_path,
):
    accepted = _write(tmp_path / "accepted.json", _return())
    rejected = _write(
        tmp_path / "rejected.json",
        {
            "filename": "thin.md",
            "status": "processed",
        },
    )
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"filename":', encoding="utf-8")

    report = aggregate_catalog_feedback.aggregate_feedback(
        [accepted, rejected, invalid], catalog_path=catalog_fixture
    )

    assert report["input_summary"] == {"accepted": 1, "rejected": 1, "invalid": 1}
    assert report["inputs"]["accepted"][0]["path"] == str(accepted.resolve())
    assert report["inputs"]["rejected"][0]["path"] == str(rejected.resolve())
    assert report["inputs"]["invalid"][0]["path"] == str(invalid.resolve())
    assert "input_json_invalid" in _issues(report)


def test_nonstandard_json_constant_is_invalid(
    aggregate_catalog_feedback,
    catalog_fixture,
    tmp_path,
):
    source = tmp_path / "nan.json"
    source.write_text(
        '{"filename":"talk.md","catalog_feedback":{},"value":NaN}',
        encoding="utf-8",
    )

    report = aggregate_catalog_feedback.aggregate_feedback(
        [source], catalog_path=catalog_fixture
    )

    assert report["input_summary"]["invalid"] == 1
    assert "input_json_invalid" in _issues(report)


def test_duplicate_json_object_keys_are_invalid_before_feedback_is_lost(
    aggregate_catalog_feedback,
    catalog_fixture,
    tmp_path,
):
    source = tmp_path / "duplicate-key.json"
    source.write_text(
        '{"filename":"talk.md","catalog_feedback":{'
        '"definition_problems":[{"pattern_id":"alpha",'
        '"problem":"ambiguous","detail":"must survive"}],'
        '"definition_problems":[]}}',
        encoding="utf-8",
    )

    report = aggregate_catalog_feedback.aggregate_feedback(
        [source], catalog_path=catalog_fixture
    )

    assert report["ok"] is False
    assert report["input_summary"] == {
        "accepted": 0,
        "rejected": 0,
        "invalid": 1,
    }
    assert "input_json_duplicate_key" in _issues(report)


def test_current_and_legacy_feedback_fields_cannot_coexist(
    aggregate_catalog_feedback,
    catalog_fixture,
    tmp_path,
):
    value = _return()
    value["feedback"] = {
        "definition_problems": [
            {
                "pattern_id": "alpha",
                "problem": "would be discarded",
                "detail": "dual representations are ambiguous",
            }
        ],
    }
    source = _write(tmp_path / "dual-feedback.json", value)

    report = aggregate_catalog_feedback.aggregate_feedback(
        [source], catalog_path=catalog_fixture
    )

    assert report["ok"] is False
    assert "catalog_feedback_fields_conflict" in _issues(report)
    assert report["entry_summary"]["accepted"] == 0


def test_programmatic_api_rejects_no_inputs(
    aggregate_catalog_feedback,
    catalog_fixture,
):
    report = aggregate_catalog_feedback.aggregate_feedback(
        [], catalog_path=catalog_fixture
    )

    assert report["ok"] is False
    assert "inputs_missing" in _issues(report)


def test_feedback_return_requires_talk_provenance(
    aggregate_catalog_feedback,
    catalog_fixture,
    tmp_path,
):
    source = _write(tmp_path / "anonymous.json", {"catalog_feedback": {}})

    report = aggregate_catalog_feedback.aggregate_feedback(
        [source], catalog_path=catalog_fixture
    )

    assert report["input_summary"]["invalid"] == 1
    assert "talk_identity_missing" in _issues(report)


def test_feedback_harvest_wrapper_is_supported(
    aggregate_catalog_feedback,
    catalog_fixture,
    tmp_path,
):
    wrapper = {
        "harvested_from": "legacy reparse",
        "returns": [{"filename": "wrapped.md", "feedback": _feedback()}],
    }
    source = _write(tmp_path / "harvest.json", wrapper)

    report = aggregate_catalog_feedback.aggregate_feedback(
        [source], catalog_path=catalog_fixture
    )

    assert report["inputs"]["accepted"][0]["shape"] == "feedback_harvest"
    assert report["return_summary"]["accepted"] == 1
    assert all(
        item["provenance"]["talk_filename"] == "wrapped.md"
        for item in report["entries"]["accepted"]
    )


def test_empty_feedback_is_an_accepted_return(
    aggregate_catalog_feedback,
    catalog_fixture,
    tmp_path,
):
    source = _write(tmp_path / "empty.json", _return(feedback={}))

    report = aggregate_catalog_feedback.aggregate_feedback(
        [source], catalog_path=catalog_fixture
    )

    assert report["input_summary"]["accepted"] == 1
    assert report["return_summary"]["accepted"] == 1
    assert report["entry_summary"]["accepted"] == 0


def test_duplicate_discovery_does_not_double_count(
    aggregate_catalog_feedback,
    catalog_fixture,
    tmp_path,
):
    directory = tmp_path / "returns"
    source = _write(directory / "one.json", _return())

    report = aggregate_catalog_feedback.aggregate_feedback(
        [directory, source], catalog_path=catalog_fixture
    )

    assert report["input_summary"]["accepted"] == 1
    assert report["entry_summary"]["accepted"] == 5
    assert "duplicate_input_suppressed" in {
        item["code"] for item in report["validation"]["warnings"]
    }


def test_report_is_stable_across_input_argument_order(
    aggregate_catalog_feedback,
    catalog_fixture,
    tmp_path,
):
    first = _write(tmp_path / "b.json", _return("b.md"))
    second = _write(tmp_path / "a.json", _return("a.md"))

    left = aggregate_catalog_feedback.aggregate_feedback(
        [first, second], catalog_path=catalog_fixture
    )
    right = aggregate_catalog_feedback.aggregate_feedback(
        [second, first], catalog_path=catalog_fixture
    )

    assert left == right


def test_catalog_polarity_fault_is_reported_without_modifying_catalog(
    aggregate_catalog_feedback,
    catalog_fixture,
    tmp_path,
):
    bad = catalog_fixture / "build" / "wrong.md"
    _catalog_file(bad, "wrong", "antipattern")
    source = _write(tmp_path / "return.json", _return())
    before = {path: path.read_bytes() for path in catalog_fixture.rglob("*.md")}

    report = aggregate_catalog_feedback.aggregate_feedback(
        [source], catalog_path=catalog_fixture
    )

    assert "catalog_filename_polarity_mismatch" in _issues(report)
    assert report["ok"] is False
    assert {path: path.read_bytes() for path in catalog_fixture.rglob("*.md")} == before


def test_bundled_catalog_registry_uses_frontmatter_polarity(
    aggregate_catalog_feedback,
):
    catalog = aggregate_catalog_feedback.load_catalog(
        aggregate_catalog_feedback.default_catalog_path()
    )
    assert catalog["errors"] == []
    assert catalog["registry"]["ant-fonts"]["polarity"] == "antipattern"
    assert catalog["registry"]["anti-sell"]["polarity"] == "pattern"
    assert len(catalog["registry"]) == 111


def test_cli_emits_stable_json_and_does_not_edit_inputs_or_catalog(
    aggregate_catalog_feedback,
    catalog_fixture,
    tmp_path,
):
    source = _write(tmp_path / "return.json", _return())
    source_before = source.read_bytes()
    catalog_before = {path: path.read_bytes() for path in catalog_fixture.rglob("*.md")}

    result = subprocess.run(
        [
            sys.executable,
            aggregate_catalog_feedback.__file__,
            str(source),
            "--catalog",
            str(catalog_fixture),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    report = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert report["ok"] is True
    assert report["read_only"] is True
    assert source.read_bytes() == source_before
    assert {
        path: path.read_bytes() for path in catalog_fixture.rglob("*.md")
    } == catalog_before


def test_cli_exits_nonzero_on_invalid_feedback(
    aggregate_catalog_feedback,
    catalog_fixture,
    tmp_path,
):
    feedback = _feedback()
    feedback["confusable_pairs"][0]["pattern_ids"] = ["alpha", "beta", "gamma"]
    source = _write(tmp_path / "invalid.json", _return(feedback=feedback))

    result = subprocess.run(
        [
            sys.executable,
            aggregate_catalog_feedback.__file__,
            str(source),
            "--catalog",
            str(catalog_fixture),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert json.loads(result.stdout)["ok"] is False


# --- #203: the CLI has a closed failure boundary ---


def test_outer_boundary_reports_an_unexpected_failure_without_a_traceback(
    aggregate_catalog_feedback, capsys, monkeypatch
):
    """Every documented outcome is JSON; a traceback would be the one exception."""

    def explode(*_args, **_kwargs):
        raise RuntimeError("injected failure at /private/vault/returns/a.json")

    monkeypatch.setattr(aggregate_catalog_feedback, "aggregate_feedback", explode)

    assert aggregate_catalog_feedback.run_cli(["some-return.json"]) == 3

    captured = capsys.readouterr()
    assert captured.out == ""  # stdout stays clean
    payload = json.loads(captured.err.splitlines()[0])
    assert payload["error"] == "catalog_feedback_unexpected_failure"
    assert payload["error_type"] == "RuntimeError"
    assert payload["origin"], "the failing code location must be reported"
    assert "injected failure" not in captured.err
    assert "/private/vault/returns/a.json" not in captured.err
    assert "Traceback" not in captured.err


def test_unexpected_failure_exit_is_distinct_from_the_argparse_exit(
    aggregate_catalog_feedback, capsys, monkeypatch
):
    """argparse already owns 2 — reusing it would conflate the two causes."""

    def explode(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(aggregate_catalog_feedback, "aggregate_feedback", explode)
    assert aggregate_catalog_feedback.run_cli(["some-return.json"]) == 3

    capsys.readouterr()
    with pytest.raises(SystemExit) as excinfo:
        aggregate_catalog_feedback.run_cli([])
    assert excinfo.value.code == 2


def test_the_argument_error_report_still_reaches_stdout(
    aggregate_catalog_feedback, capsys
):
    """The boundary must not swallow the documented invalid-arguments report."""
    with pytest.raises(SystemExit):
        aggregate_catalog_feedback.run_cli([])

    report = json.loads(capsys.readouterr().out)
    assert report["error"]["code"] == "invalid_arguments"


def test_outer_boundary_lets_the_documented_verdicts_through(
    aggregate_catalog_feedback, monkeypatch
):
    """An `ok: false` report is exit 1, not an unexpected failure."""
    monkeypatch.setattr(aggregate_catalog_feedback, "main", lambda *a, **k: 1)
    assert aggregate_catalog_feedback.run_cli([]) == 1
