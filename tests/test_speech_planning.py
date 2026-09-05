"""Family-balanced planning remains distinct from actual-recording evidence."""

import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from conftest import SCRIPTS_VP, _import_script
from test_speech_calibration import cohort, pace, request, sample

rates = _import_script(Path(SCRIPTS_VP) / "speech_rates.py", "speech_rates")


@pytest.fixture
def profile():
    return pace.calibrate(request(cohort()))


def test_plan_retains_mean_observed_range_and_separate_conservative_budget(profile):
    before = copy.deepcopy(profile)
    assert rates.validate_profile(profile) == before
    result = rates.plan_duration(120, intended_metric="narration", profile=profile)
    metric = profile["summary"]["metrics"]["narration"]
    assert result["schema_version"] == 2
    assert result["kind"] == "prediction_not_verification"
    assert result["rate"]["value"] == metric["family_balanced_mean"]
    assert (
        result["rate"]["mean_confidence_interval_95"]
        == metric["mean_confidence_interval_95"]
    )
    assert result["rate"]["range"] == metric["observed_recording_range"]
    assert result["range_kind"] == "observed_recording_range_not_prediction_interval"
    assert result["estimated_range_seconds"] == pytest.approx(
        [
            7200 / metric["observed_recording_range"][1],
            7200 / metric["observed_recording_range"][0],
        ]
    )
    assert result["estimated_seconds"] == pytest.approx(
        7200 / metric["family_balanced_mean"]
    )
    assert result["conservative_estimated_seconds"] == pytest.approx(
        7200 / metric["conservative_planning_wpm"]
    )
    assert result["conservative_estimated_seconds"] > result["estimated_seconds"]
    provenance = result["rate"]["provenance"]
    assert provenance["sample_count"] == 8
    assert provenance["presentation_family_count"] == 8
    assert provenance["calibration_sha256"] == profile["calibration_sha256"]
    assert len(provenance["evidence_sha256"]) == 8
    assert profile == before


def test_real_calibration_cli_recomputes_v2_from_retained_owner_evidence(profile):
    original = rates.encode(profile["calibration"])
    result = subprocess.run(
        [sys.executable, str(Path(SCRIPTS_VP) / "speech_rates.py"), "calibrate"],
        input=original,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert len(result.stdout.splitlines()) == 1
    assert result.stderr == b""
    report = json.loads(result.stdout)
    assert report == {"schema_version": 1, "ok": True, "data": profile}
    assert rates.encode(profile["calibration"]) == original


def test_family_profile_wins_over_assumption_but_low_confidence_never_falls_back(
    profile,
):
    assumption = rates.assumed_narration(150, 160, reason="fixture assumption")
    result = rates.plan_duration(
        120, intended_metric="narration", profile=profile, assumption=assumption
    )
    assert result["rate"]["basis"] == "measured"
    for rows in ([], [sample()]):
        sparse = pace.calibrate(request(rows))
        with pytest.raises(rates.SpeechRateError) as exc:
            rates.plan_duration(
                120, intended_metric="narration", profile=sparse, assumption=assumption
            )
        assert exc.value.code == "pace_confidence_insufficient"


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("schema_version", 3),
        ("metric", "articulation"),
        ("basis", "assumption"),
        ("mean_confidence_interval_95", None),
        ("mean_confidence_interval_95", [0, 120]),
        ("mean_confidence_interval_95", [120, 70]),
        ("conservative_planning_wpm", True),
        ("conservative_planning_wpm", 1),
        ("unknown", "private value"),
    ],
)
def test_bad_family_rate_refuses_without_relabeling(profile, field, value):
    rate = pace.narration_rate(profile)
    rate[field] = value
    with pytest.raises(rates.SpeechRateError):
        rates.validate_rate(rate)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 1),
        ("presentation_family_count", True),
        ("presentation_family_count", 1),
        ("presentation_family_count", 9),
        ("sample_count", 1),
        ("analyzed_duration_seconds", 1),
        ("evidence_sha256", None),
        ("evidence_sha256", ["a" * 64] * 8),
        ("calibration_sha256", "unknown"),
        ("language", "English"),
        ("confidence_level", "high"),
        ("interval_kind", "prediction_interval"),
        ("range_kind", "confidence_interval"),
        ("method_version", "word-gaps-v1"),
    ],
)
def test_bad_family_provenance_is_not_accepted_by_readers(profile, field, value):
    rate = pace.narration_rate(profile)
    rate["provenance"][field] = value
    with pytest.raises(rates.SpeechRateError):
        rates.validate_rate(rate)


@pytest.mark.parametrize("families", [5, 6, 7, 8])
def test_homogeneous_rates_with_broad_coverage_are_representable(families):
    rows = cohort()
    for index, row in enumerate(rows):
        row["family"] = f"family{index % families}"
        original = sample(row["recording_id"], row["family"])
        row["words"] = original["words"]
    report = pace.calibrate(request(rows))
    rate = pace.narration_rate(report)
    assert rate["mean_confidence_interval_95"] == [rate["value"], rate["value"]]
    assert rate["conservative_planning_wpm"] == rate["value"]


def test_v2_rate_survives_outline_and_script_without_becoming_a_duration_guarantee(
    profile, outline_schema, extract_script
):
    outline = outline_schema.load_outline(
        Path(__file__).parent / "fixtures" / "outline-example.yaml"
    )
    data = outline.model_dump(mode="json")
    data["talk"]["pacing_wpm"] = None
    data["talk"]["pacing_rate"] = pace.narration_rate(profile)
    restored = outline_schema.Outline.model_validate_json(json.dumps(data))
    assert restored.talk.narration_rate == data["talk"]["pacing_rate"]
    rendered = extract_script.render(restored)
    assert "measured family-balanced mean" in rendered
    assert "conservative planning" in rendered
    assert "8 recordings, 8 families" in rendered
    assert "conditional mean 95% interval" in rendered
    assert "not a prediction interval" in rendered
    assert "actual word timestamps and actual duration" in rendered
    assert "observed sample range" not in rendered


@pytest.mark.parametrize(
    "defect,code",
    [
        (None, None),
        ("low", "pace_confidence_insufficient"),
        ("words", "pace_word_evidence_invalid"),
        ("tampered", "pace_profile_inconsistent"),
    ],
)
def test_real_cli_dispatch_preserves_typed_errors_and_never_writes_input(
    profile, tmp_path, defect, code
):
    if defect == "low":
        profile = pace.calibrate(request([]))
    elif defect == "words":
        profile["calibration"]["samples"][0]["words"]["words"][0]["end_seconds"] = 0
    elif defect == "tampered":
        profile["summary"]["metrics"]["narration"]["family_balanced_mean"] = 1
    payload = {
        "schema_version": 1,
        "word_count": 120,
        "intended_metric": "narration",
        "profile": profile,
        "assumption": None,
    }
    original = rates.encode(payload)
    source = tmp_path / "planning.json"
    source.write_bytes(original)
    result = subprocess.run(
        [sys.executable, str(Path(SCRIPTS_VP) / "speech_rates.py"), "plan"],
        input=original,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == (1 if defect else 0), result.stderr
    assert len(result.stdout.splitlines()) == 1
    report = json.loads(result.stdout)
    assert report["ok"] is (defect is None)
    if defect:
        assert report["error"]["code"] == code
        assert "token0" not in result.stdout.decode() + result.stderr.decode()
    else:
        assert report["data"]["schema_version"] == 2
    assert source.read_bytes() == original
