"""The basis is a pure function of a return's own lanes, so a script owns it.

Reproducing it by hand costs a validate-fix cycle per worker: the field's
absence and a plausible-but-wrong shape borrowed from the sibling
`pattern_score` object are both rejections a reader cannot avoid from the
documentation alone.
"""

import json


def _detection(confidence):
    return {"pattern_id": "narrative-arc", "confidence": confidence}


def _return(patterns=(), antipatterns=(), not_evaluable=()):
    return {
        "filename": "talk.md",
        "pattern_observations": {
            "patterns_detected": list(patterns),
            "antipatterns_detected": list(antipatterns),
            "not_evaluable": list(not_evaluable),
        },
    }


def test_basis_counts_each_lane_by_confidence(build_score_basis, return_validation):
    basis = build_score_basis.basis_for(
        _return(
            patterns=[
                _detection("strong"),
                _detection("moderate"),
                _detection("strong"),
            ],
            antipatterns=[_detection("weak")],
            not_evaluable=[{"pattern_id": "coda", "reason_code": "x"}],
        ),
        "talk.md",
    )
    assert basis["patterns"] == {"strong": 2, "moderate": 1, "weak": 0}
    assert basis["antipatterns"] == {"strong": 0, "moderate": 0, "weak": 1}
    assert basis["not_evaluable_count"] == 1
    assert basis["weights"] == return_validation.DETECTION_WEIGHTS
    assert (
        basis["schema_version"]
        == return_validation.WEIGHTED_PATTERN_SCORING_SCHEMA_VERSION
    )


def test_an_empty_return_still_produces_every_field(build_score_basis):
    """A talk with no detections still needs a complete basis, not an omission."""
    basis = build_score_basis.basis_for(_return(), "talk.md")
    assert set(basis) == {
        "schema_version",
        "weights",
        "patterns",
        "antipatterns",
        "not_evaluable_count",
    }
    assert basis["not_evaluable_count"] == 0


def test_the_basis_the_script_emits_is_the_one_the_validator_requires(
    build_score_basis, return_validation
):
    """Outcome check: the emitted object must survive the validator's own gate."""
    ret = _return(
        patterns=[_detection("strong")],
        not_evaluable=[{"pattern_id": "coda", "reason_code": "x"}],
    )
    observations = dict(ret["pattern_observations"])
    observations["pattern_score_basis"] = build_score_basis.basis_for(ret, "talk.md")
    # raises ReturnValidationError if the shape or values disagree
    return_validation._require_score_basis(
        observations,
        return_validation.pattern_score_basis(
            observations["patterns_detected"],
            observations["antipatterns_detected"],
            observations["not_evaluable"],
        ),
    )


def test_a_return_without_observations_is_an_error_not_a_guess(build_score_basis):
    import pytest

    with pytest.raises(ValueError, match="pattern_observations"):
        build_score_basis.basis_for({"filename": "talk.md"}, "talk.md")


def test_a_non_array_lane_is_rejected(build_score_basis):
    import pytest

    broken = _return()
    broken["pattern_observations"]["patterns_detected"] = "not-an-array"
    with pytest.raises(ValueError, match="must be an array"):
        build_score_basis.basis_for(broken, "talk.md")


def test_a_missing_required_lane_is_rejected(build_score_basis, tmp_path, capsys):
    for missing in ("patterns_detected", "antipatterns_detected", "not_evaluable"):
        broken = _return()
        del broken["pattern_observations"][missing]
        path = tmp_path / f"missing-{missing}.json"
        path.write_text(json.dumps(broken), encoding="utf-8")

        assert build_score_basis.main([str(path)]) == 2
        captured = capsys.readouterr()
        assert f"pattern_observations.{missing} is required" in captured.err
        assert captured.out == ""


def test_cli_emits_the_completed_return(build_score_basis, tmp_path, capsys):
    """Output is the return itself, so no caller computes or places either field."""
    path = tmp_path / "r.json"
    path.write_text(
        json.dumps(_return(patterns=[_detection("moderate")])), encoding="utf-8"
    )
    assert build_score_basis.main([str(path)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["filename"] == "talk.md"
    assert printed["pattern_observations"]["pattern_score"] == 0.5
    assert (
        printed["pattern_observations"]["pattern_score_basis"]["patterns"]["moderate"]
        == 1
    )


def test_cli_emits_an_array_for_several_returns(build_score_basis, tmp_path, capsys):
    a, b = _return(patterns=[_detection("strong")]), _return()
    b["filename"] = "other.md"
    path = tmp_path / "batch.json"
    path.write_text(json.dumps([a, b]), encoding="utf-8")
    assert build_score_basis.main([str(path)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert [r["filename"] for r in printed] == ["talk.md", "other.md"]


def test_the_input_return_is_not_mutated(build_score_basis):
    """A caller reusing its own object must not find fields it did not add."""
    original = _return(patterns=[_detection("strong")])
    build_score_basis.completed(original, "talk.md")
    assert "pattern_score" not in original["pattern_observations"]
    assert "pattern_score_basis" not in original["pattern_observations"]


def test_completed_overwrites_a_worker_supplied_score_from_owner_math(
    build_score_basis,
):
    ret = _return(
        patterns=[_detection("strong"), _detection("moderate")],
        antipatterns=[_detection("weak")],
    )
    ret["pattern_observations"]["pattern_score"] = 999

    completed = build_score_basis.completed(ret, "talk.md")

    assert completed["pattern_observations"]["pattern_score"] == 1.25


def test_a_malformed_detection_exits_two_without_a_traceback(
    build_score_basis, tmp_path, capsys
):
    """A bad detection reaches the owner function as a TypeError or KeyError."""
    for broken in ("not-an-object", {"pattern_id": "x", "confidence": "enormous"}):
        path = tmp_path / "broken.json"
        path.write_text(json.dumps(_return(patterns=[broken])), encoding="utf-8")
        assert build_score_basis.main([str(path)]) == 2
        captured = capsys.readouterr()
        assert "malformed detection entry" in captured.err
        assert captured.out == ""


def test_cli_reports_unreadable_input_without_a_traceback(
    build_score_basis, tmp_path, capsys
):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    assert build_score_basis.main([str(path)]) == 2
    assert "cannot build pattern_score_basis" in capsys.readouterr().err


def test_duplicate_filenames_fail_instead_of_overwriting(
    build_score_basis, tmp_path, capsys
):
    """Keying by filename would drop every return but the last.

    A caller merging that output would give one talk another talk's basis,
    which is worse than no output at all.
    """
    first = _return(patterns=[_detection("strong")])
    second = _return(patterns=[_detection("weak")])
    path = tmp_path / "batch.json"
    path.write_text(json.dumps([first, second]), encoding="utf-8")

    assert build_score_basis.main([str(path)]) == 2
    err = capsys.readouterr().err
    assert "duplicate talk filenames" in err
    assert "talk.md" in err


def test_duplicates_across_separate_files_are_caught_too(
    build_score_basis, tmp_path, capsys
):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps(_return()), encoding="utf-8")
    b.write_text(json.dumps(_return()), encoding="utf-8")

    assert build_score_basis.main([str(a), str(b)]) == 2
    assert "duplicate talk filenames" in capsys.readouterr().err
