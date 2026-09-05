"""Recorded word timing stays distinct from assumed narration planning."""

import copy
import io
import json
from pathlib import Path
import subprocess
import sys

import pytest

from conftest import SCRIPTS_VP, _import_script


@pytest.fixture
def rates():
    return _import_script(Path(SCRIPTS_VP) / "speech_rates.py", "speech_rates")


@pytest.fixture
def outline(outline_schema):
    return outline_schema.load_outline(
        Path(__file__).parent / "fixtures" / "outline-example.yaml"
    )


@pytest.fixture
def evidence():
    # 40 s word spans, 4 s natural phrase gaps, 50 s complete timeline.
    # One 1.2 s gap and seven 0.4 s gaps distinguish all four metrics.
    words = []
    cursor = 1.0
    for index in range(100):
        if index == 8:
            cursor += 1.2
        elif index in (20, 30, 40, 50, 60, 70, 80):
            cursor += 0.4
        words.append(["word", round(cursor, 6), round(cursor + 0.4, 6)])
        cursor += 0.4
    return {
        "schema_version": 1,
        "timing_kind": "recorded_words",
        "source_sha256": "a" * 64,
        "source_duration_seconds": 50,
        "sample_start_seconds": 0,
        "sample_duration_seconds": 50,
        "aligner": "synthetic-fixed-fixture-v1",
        "words": words,
    }


def _profile(rates, evidence):
    return rates.calibrate(
        {
            "schema_version": 1,
            "cohort": "synthetic-demo-fixtures",
            "samples": [evidence],
        }
    )


def test_four_metrics_remain_distinct(rates, evidence):
    measured = rates.measure(evidence)
    rows = {rate["metric"]: rate for rate in measured["rates"]}
    assert rows["timeline"]["value"] == 120
    assert rows["narration"]["value"] == pytest.approx(136.363636)
    assert rows["short_phrase"]["value"] == pytest.approx(140.186916)
    assert rows["articulation"]["value"] == pytest.approx(150)
    assert [row["denominator_seconds"] for row in rows.values()] == pytest.approx(
        [50, 44, 42.8, 40]
    )
    assert [row["pause_threshold_seconds"] for row in rows.values()] == [
        None,
        2.0,
        1.0,
        0.25,
    ]
    assert all(row["unit"] == "words_per_minute" for row in rows.values())
    assert measured["source_sha256"] == "a" * 64
    assert measured["word_count"] == 100


def test_profile_persistence_keeps_provenance_and_metric_identity(
    rates, evidence, tmp_path
):
    profile = _profile(rates, evidence)
    target = tmp_path / "speech-rate-profile.json"
    target.write_bytes(rates.encode(profile))
    restored = rates.validate_profile(rates.decode(target.read_bytes()))
    assert restored == profile
    for row in restored["rates"]:
        rates.validate_rate(row)
        assert row["basis"] == "measured"
        assert row["range"] == [row["value"], row["value"]]
        provenance = row["provenance"]
        assert provenance["sample_count"] == 1
        assert provenance["analyzed_duration_seconds"] == 50
        assert provenance["cohort"] == "synthetic-demo-fixtures"
        assert provenance["method_version"] == "word-gaps-v1"
        assert (
            provenance["range_kind"] == "observed_sample_range_not_confidence_interval"
        )
        assert provenance["evidence_sha256"] == [
            rates.measure(evidence)["evidence_sha256"]
        ]


def test_long_form_prefers_measured_narration_over_assumption(rates, evidence):
    profile = _profile(rates, evidence)
    assumption = rates.assumed_narration(150, 150, reason="uncalibrated fixture")
    result = rates.plan_duration(
        100, intended_metric="narration", profile=profile, assumption=assumption
    )
    assert result["estimated_seconds"] == pytest.approx(44)
    assert result["rate"]["metric"] == "narration"
    assert result["rate"]["basis"] == "measured"
    assert result["kind"] == "prediction_not_verification"


def test_assumptions_cannot_change_recording_verdict(rates, evidence):
    slow = rates.plan_duration(
        100,
        intended_metric="narration",
        assumption=rates.assumed_narration(100, 100, reason="slow assumption"),
    )
    before = rates.verify_recording(evidence, maximum_duration_seconds=45)
    fast = rates.plan_duration(
        100,
        intended_metric="narration",
        assumption=rates.assumed_narration(200, 200, reason="fast assumption"),
    )
    after = rates.verify_recording(evidence, maximum_duration_seconds=45)
    assert slow["estimated_seconds"] == 60
    assert fast["estimated_seconds"] == 30
    assert before == after
    assert before["fits_duration"] is False
    assert before["measurement"]["actual_duration_seconds"] == 50
    assert (
        rates.verify_recording(evidence, maximum_duration_seconds=50)["fits_duration"]
        is True
    )


@pytest.mark.parametrize(
    "metric", ["timeline", "short_phrase", "articulation", "wpm", None, True]
)
def test_long_form_rejects_non_narration_or_unqualified_rates(rates, metric):
    with pytest.raises(rates.SpeechRateError):
        rates.plan_duration(100, intended_metric=metric, assumption=150)


def test_planning_requires_explicit_intent_and_basis(rates):
    with pytest.raises(TypeError):
        rates.plan_duration(100)
    with pytest.raises(rates.SpeechRateError, match="measured narration profile"):
        rates.plan_duration(100, intended_metric="narration")
    with pytest.raises(rates.SpeechRateError):
        rates.plan_duration(100, intended_metric="narration", assumption=150)


@pytest.mark.parametrize(
    "key,value",
    [
        ("schema_version", True),
        ("schema_version", 2),
        ("schema_version", 1.0),
        ("timing_kind", "predicted"),
        ("timing_kind", "segments"),
        ("source_sha256", "A" * 64),
        ("source_sha256", "bad"),
        ("source_duration_seconds", 49),
        ("source_duration_seconds", 14401),
        ("sample_duration_seconds", 0),
        ("sample_start_seconds", 1),
        ("aligner", ""),
        ("words", []),
        ("words", [["two words", 0, 1]]),
        ("words", [["...", 0, 1]]),
        ("words", [["word", 0, 0]]),
        ("words", [["word", 0, 51]]),
        ("words", [["word", True, 1]]),
        ("words", [["word", 0, float("inf")]]),
        ("words", [["word", 0, 2], ["second", 1, 3]]),
    ],
)
def test_bad_recording_evidence_fails_closed(rates, evidence, key, value):
    evidence[key] = value
    with pytest.raises(rates.SpeechRateError):
        rates.measure(evidence)


def test_unknown_fields_and_absent_versions_are_not_silently_accepted(rates, evidence):
    evidence["wpm"] = 150
    with pytest.raises(rates.SpeechRateError):
        rates.measure(evidence)
    del evidence["wpm"]
    del evidence["schema_version"]
    with pytest.raises(rates.SpeechRateError):
        rates.measure(evidence)


def test_pause_threshold_boundary_keeps_whole_eligible_gaps(rates, evidence):
    evidence["words"] = [
        ["one", 1, 2],
        ["two", 2.25, 3.25],
        ["three", 4.25, 5.25],
        ["four", 7.25, 8.25],
        ["five", 11.25, 12.25],
    ]
    rows = rates.measure(evidence)["rates"]
    assert [row["denominator_seconds"] for row in rows] == [50, 8.25, 6.25, 5.25]


def test_overlapping_samples_rejected_but_disjoint_windows_allowed(rates, evidence):
    second = copy.deepcopy(evidence)
    request = {
        "schema_version": 1,
        "cohort": "synthetic",
        "samples": [evidence, second],
    }
    with pytest.raises(rates.SpeechRateError, match="non-overlapping"):
        rates.calibrate(request)
    evidence["source_duration_seconds"] = 100
    second["source_duration_seconds"] = 100
    second["sample_start_seconds"] = 50
    profile = rates.calibrate(request)
    assert profile["rates"][0]["provenance"]["sample_count"] == 2
    assert profile["rates"][0]["provenance"]["analyzed_duration_seconds"] == 100


@pytest.mark.parametrize("mutation", ["value", "threshold", "cohort", "word", "schema"])
def test_persisted_profile_tampering_is_rejected(rates, evidence, mutation):
    profile = _profile(rates, evidence)
    if mutation == "value":
        profile["rates"][1]["value"] = 150
    elif mutation == "threshold":
        profile["rates"][1]["pause_threshold_seconds"] = 0.25
    elif mutation == "cohort":
        profile["calibration"]["cohort"] = "different"
    elif mutation == "word":
        profile["calibration"]["samples"][0]["words"][0][0] = "changed"
    else:
        profile["schema_version"] = 2
    with pytest.raises(rates.SpeechRateError):
        rates.validate_profile(profile)


def test_invalid_present_profile_does_not_fall_back_to_assumption(rates, evidence):
    profile = _profile(rates, evidence)
    profile["schema_version"] = 99
    with pytest.raises(rates.SpeechRateError):
        rates.plan_duration(
            100,
            intended_metric="narration",
            profile=profile,
            assumption=rates.assumed_narration(150, 150, reason="default"),
        )


def test_sample_mean_does_not_overflow_when_each_rate_is_finite(rates, evidence):
    samples = []
    for digest in ("a", "b", "c", "d"):
        sample = copy.deepcopy(evidence)
        sample["source_sha256"] = digest * 64
        sample["words"] = [["word", 0, 1e-306]]
        samples.append(sample)
    profile = rates.calibrate(
        {"schema_version": 1, "cohort": "synthetic-extreme", "samples": samples}
    )
    assert profile["rates"][1]["value"] == pytest.approx(6e307)
    rates.validate_profile(profile)


def test_predicted_result_is_not_recording_evidence(rates):
    prediction = rates.plan_duration(
        100,
        intended_metric="narration",
        assumption=rates.assumed_narration(150, 150, reason="default"),
    )
    with pytest.raises(rates.SpeechRateError):
        rates.verify_recording(prediction, maximum_duration_seconds=60)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema_version":1,"schema_version":1}',
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b"\xff",
        b"{",
    ],
)
def test_strict_json_decode(rates, raw):
    with pytest.raises(rates.SpeechRateError):
        rates.decode(raw)


def test_json_size_limit(rates):
    with pytest.raises(rates.SpeechRateError):
        rates.decode(b" " * (rates.MAX_JSON_BYTES + 1))
    with pytest.raises(rates.SpeechRateError):
        rates.encode("x" * rates.MAX_JSON_BYTES)


@pytest.mark.parametrize("action", ["measure", "calibrate", "plan", "verify"])
def test_real_cli_emits_one_json_and_does_not_mutate_inputs(
    rates, evidence, tmp_path, action
):
    requests = {
        "measure": evidence,
        "calibrate": {
            "schema_version": 1,
            "cohort": "synthetic",
            "samples": [evidence],
        },
        "plan": {
            "schema_version": 1,
            "word_count": 100,
            "intended_metric": "narration",
            "profile": _profile(rates, evidence),
            "assumption": None,
        },
        "verify": {
            "schema_version": 1,
            "evidence": evidence,
            "maximum_duration_seconds": 45,
        },
    }
    original = rates.encode(requests[action])
    source = tmp_path / "request.json"
    source.write_bytes(original)
    result = subprocess.run(
        [sys.executable, str(Path(SCRIPTS_VP) / "speech_rates.py"), action],
        input=original,
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == b""
    assert len(result.stdout.splitlines()) == 1
    assert json.loads(result.stdout)["ok"] is True
    assert source.read_bytes() == original


def test_cli_invalid_input_never_echoes_words_or_credentials(
    rates, monkeypatch, capsys
):
    monkeypatch.setattr(
        sys, "stdin", io.TextIOWrapper(io.BytesIO(b'{"private":"synthetic-secret"}'))
    )
    assert rates.main(["measure"]) == 1
    result = capsys.readouterr()
    assert json.loads(result.out)["ok"] is False
    assert "synthetic-secret" not in result.out + result.err


@pytest.mark.parametrize("argv", [[], ["bogus"], ["--unknown", "synthetic-secret"]])
def test_cli_usage_is_structured_and_redacted(rates, capsys, argv):
    assert rates.main(argv) == 2
    result = capsys.readouterr()
    assert json.loads(result.out)["error"]["code"] == "speech_usage_invalid"
    assert "synthetic-secret" not in result.out + result.err


def test_help_does_not_read_stdin(rates, capsys):
    assert rates.main(["--help"]) == 0
    assert "word-gaps-v1" in json.loads(capsys.readouterr().out)["data"]["help"]


def test_interior_window_cannot_verify_full_recording(rates, evidence):
    evidence["source_duration_seconds"] = 100
    evidence["sample_start_seconds"] = 20
    assert rates.measure(evidence)["actual_duration_seconds"] == 50
    with pytest.raises(rates.SpeechRateError, match="complete recording"):
        rates.verify_recording(evidence, maximum_duration_seconds=60)


def test_inconsistent_duration_for_same_source_rejected(rates, evidence):
    other = copy.deepcopy(evidence)
    other["sample_start_seconds"] = 50
    other["source_duration_seconds"] = 100
    with pytest.raises(rates.SpeechRateError, match="one actual duration"):
        rates.calibrate(
            {"schema_version": 1, "cohort": "synthetic", "samples": [evidence, other]}
        )


@pytest.mark.parametrize(
    "value", [True, "150", -1, 0, float("nan"), float("inf"), 10**400]
)
def test_invalid_assumption_numbers_are_typed_failures(rates, value):
    with pytest.raises(rates.SpeechRateError):
        rates.assumed_narration(value, value, reason="synthetic")


def test_unrepresentable_arithmetic_is_rejected(rates, evidence):
    evidence["words"] = [["word", 0, 1e-320]]
    with pytest.raises(rates.SpeechRateError):
        rates.measure(evidence)
    assumption = rates.assumed_narration(1e-320, 1e-320, reason="synthetic")
    with pytest.raises(rates.SpeechRateError):
        rates.plan_duration(100, intended_metric="narration", assumption=assumption)


@pytest.mark.parametrize("failure", [ValueError, RecursionError])
def test_decoder_value_or_recursion_failure_is_typed(rates, monkeypatch, failure):
    def reject_deep_input(*args, **kwargs):
        raise failure

    monkeypatch.setattr(rates.json, "loads", reject_deep_input)
    with pytest.raises(rates.SpeechRateError):
        rates.decode(b"[]")


def test_utf16_is_not_accepted_as_utf8_json(rates):
    with pytest.raises(rates.SpeechRateError):
        rates.decode('{"schema_version":1}'.encode("utf-16le"))


@pytest.mark.parametrize("value", [object(), float("nan"), float("inf"), -float("inf")])
def test_encoder_rejects_non_json_values_with_typed_errors(rates, value):
    with pytest.raises(rates.SpeechRateError) as caught:
        rates.encode({"private-label": value})
    assert caught.value.code == "speech_json_invalid"
    assert "private-label" not in str(caught.value)
    assert caught.value.__suppress_context__ is True


def test_encoder_rejects_circular_structures(rates):
    value = []
    value.append(value)
    with pytest.raises(rates.SpeechRateError) as caught:
        rates.encode(value)
    assert caught.value.code == "speech_json_invalid"


@pytest.mark.parametrize("failure", [TypeError, ValueError, RecursionError])
def test_encoder_failure_is_redacted_and_unchained(rates, monkeypatch, failure):
    import traceback

    def reject_input(*args, **kwargs):
        raise failure("private input value")

    monkeypatch.setattr(rates.json, "dumps", reject_input)
    with pytest.raises(rates.SpeechRateError) as caught:
        rates.encode({})
    assert caught.value.code == "speech_json_invalid"
    assert "private input value" not in "".join(
        traceback.format_exception(caught.value)
    )


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
def test_encoder_does_not_swallow_interrupts(rates, monkeypatch, interrupt):
    def stop(*args, **kwargs):
        raise interrupt

    monkeypatch.setattr(rates.json, "dumps", stop)
    with pytest.raises(interrupt):
        rates.encode({})


def test_encoder_preserves_canonical_bytes_and_size_failure(rates, monkeypatch):
    value = {"schema_version": 1, "a": [1, True, None, "text"]}
    encoded = rates.encode(value)
    assert encoded == b'{"a":[1,true,null,"text"],"schema_version":1}'
    assert rates.decode(encoded) == value
    monkeypatch.setattr(rates, "MAX_JSON_BYTES", len(encoded) - 1)
    with pytest.raises(rates.SpeechRateError) as caught:
        rates.encode(value)
    assert caught.value.code == "speech_json_too_large"


def test_outline_legacy_range_is_explicitly_unverified(outline, extract_script):
    rate = outline.talk.narration_rate
    assert rate["basis"] == "assumption"
    assert rate["metric"] == "narration"
    assert rate["pause_threshold_seconds"] == 2
    rendered = extract_script.render(outline)
    assert "140–160 WPM narration" in rendered
    assert "assumption, not verified" in rendered
    assert "actual word timestamps and actual duration" in rendered


def test_typed_measured_narration_survives_outline_and_script(
    rates, evidence, outline, outline_schema, extract_script
):
    data = outline.model_dump(mode="json")
    data["talk"]["pacing_wpm"] = None
    data["talk"]["pacing_rate"] = _profile(rates, evidence)["rates"][1]
    parsed = outline_schema.Outline.model_validate(data)
    restored = outline_schema.Outline.model_validate_json(parsed.model_dump_json())
    assert restored.talk.narration_rate["value"] == pytest.approx(136.363636)
    rendered = extract_script.render(restored)
    assert "136.364–136.364 WPM narration" in rendered
    assert "measured; 1 samples, 50 s analyzed" in rendered
    assert "synthetic-demo-fixtures" in rendered
    assert "word-gaps-v1" in rendered
    assert "not a confidence interval" in rendered


@pytest.mark.parametrize(
    "mutation",
    ["ambiguous", "articulation", "version", "no_pace", "bool_range", "reversed"],
)
def test_outline_rejects_ambiguous_or_wrong_pacing(
    rates, evidence, outline, outline_schema, mutation
):
    from pydantic import ValidationError

    data = outline.model_dump(mode="json")
    if mutation == "ambiguous":
        data["talk"]["pacing_rate"] = _profile(rates, evidence)["rates"][1]
    elif mutation == "articulation":
        data["talk"]["pacing_wpm"] = None
        data["talk"]["pacing_rate"] = _profile(rates, evidence)["rates"][3]
    elif mutation == "version":
        data["schema_version"] = 2
    elif mutation == "no_pace":
        data["talk"]["pacing_wpm"] = None
    elif mutation == "bool_range":
        data["talk"]["pacing_wpm"] = [True, 160]
    else:
        data["talk"]["pacing_wpm"] = [160, 140]
    with pytest.raises(ValidationError):
        outline_schema.Outline.model_validate(data)


def test_partial_outline_accepts_typed_pacing(rates, evidence, outline, outline_schema):
    talk = outline.model_dump(mode="json")["talk"]
    talk["pacing_wpm"] = None
    talk["pacing_rate"] = _profile(rates, evidence)["rates"][1]
    partial = outline_schema.PartialOutline.model_validate(
        {"schema_version": 1, "talk": talk}
    )
    assert partial.talk.narration_rate["basis"] == "measured"


def test_outer_boundary_emits_closed_failure_and_preserves_interrupts(
    rates, monkeypatch, capsys
):
    class BrokenInput:
        @property
        def buffer(self):
            raise RuntimeError("synthetic-secret")

    monkeypatch.setattr(sys, "stdin", BrokenInput())
    assert rates.main(["measure"]) == 2
    result = capsys.readouterr()
    assert json.loads(result.out)["error"]["code"] == "speech_unexpected_failure"
    assert "synthetic-secret" not in result.out + result.err

    class InterruptedInput:
        @property
        def buffer(self):
            raise KeyboardInterrupt

    monkeypatch.setattr(sys, "stdin", InterruptedInput())
    with pytest.raises(KeyboardInterrupt):
        rates.main(["measure"])
