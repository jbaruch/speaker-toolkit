"""Fixed recording fixtures exercise the public family-calibration contract."""

import copy
import hashlib
from pathlib import Path

import pytest

from conftest import SCRIPTS_VI, SCRIPTS_VP, _import_script

pace = _import_script(Path(SCRIPTS_VP) / "speech_calibration.py", "speech_calibration")
word_owner = _import_script(
    Path(SCRIPTS_VI) / "local_media_words.py", "local_media_words"
)
SpeechRateError = pace.SpeechRateError
LocalMediaError = word_owner.LocalMediaError


def sample(identifier="one", family="family one", *, gap=0.25, count=600):
    duration = count * (0.25 + gap)
    raw = {
        "language": "en",
        "segments": [
            {
                "start": 0,
                "end": duration,
                "compression_ratio": 1.2,
                "avg_logprob": -0.1,
                "no_speech_prob": 0.01,
                "words": [
                    {
                        "word": f"token{index}",
                        "start": index * (0.25 + gap),
                        "end": index * (0.25 + gap) + 0.25,
                        "probability": 0.95,
                    }
                    for index in range(count)
                ],
            }
        ],
    }
    receipt = word_owner.normalize_word_result(
        raw,
        source_sha256=hashlib.sha256(identifier.encode()).hexdigest(),
        sample_sha256=hashlib.sha256((identifier + "sample").encode()).hexdigest(),
        source_duration_seconds=3600,
        sample_start_seconds=600,
        sample_duration_seconds=max(600, duration),
        provider_version="0.4.3",
        model=word_owner.DEFAULT_WORD_MODEL,
        language_probability=0.99,
    )
    return {
        "schema_version": 1,
        "recording_id": identifier,
        "family": family,
        "mode": "demo",
        "year": 2020,
        "words": receipt,
    }


def request(samples=None):
    return {
        "schema_version": 2,
        "speaker": "Fixture speaker",
        "language": "en",
        "catalog_sha256": "c" * 64,
        "generated_at": "2024-06-01T12:00:00Z",
        "demo_modes": ["demo"],
        "samples": [sample()] if samples is None else samples,
        "exclusions": [],
    }


def cohort():
    result = []
    for index in range(8):
        row = sample(
            f"recording{index}", f"family{index}", gap=0.25 + (index % 3) * 0.125
        )
        row.update(year=2018 + index % 3, mode="demo" if index % 2 else "lecture")
        result.append(row)
    return result


def test_family_means_not_delivery_count_weight_the_estimate():
    rows = [
        sample("a1", "a"),
        sample("a2", "a"),
        sample("a3", "a"),
        sample("b1", "b", gap=0.75),
    ]
    report = pace.calibrate(request(rows))
    summary = report["summary"]
    assert summary["recording_count"] == 4
    assert summary["presentation_family_count"] == 2
    values = [row["values"]["narration"] for row in report["recordings"]]
    metric = summary["metrics"]["narration"]
    expected = (values[0] + values[3]) / 2
    assert metric["family_balanced_mean"] == pytest.approx(expected)
    assert metric["family_balanced_mean"] != pytest.approx(sum(values) / 4)
    assert metric["family_median"] == pytest.approx(expected)
    assert metric["mean_confidence_interval_95"] == [values[3], values[0]]
    assert metric["family_mean_range"] == [values[3], values[0]]
    assert metric["conservative_planning_wpm"] is None
    assert summary["confidence"]["level"] == "low"


def test_all_metrics_intervals_and_mode_coverage_are_retained():
    report = pace.calibrate(request(cohort()))
    summary = report["summary"]
    assert summary["analyzed_duration_seconds"] == 4800
    assert summary["narration_duration_seconds"] > 1800
    assert summary["years"] == [2018, 2019, 2020]
    assert summary["modes"] == ["demo", "lecture"]
    assert summary["confidence"] == {
        "schema_version": 1,
        "level": "conditional",
        "reasons": [],
    }
    assert set(summary["metrics"]) == {
        "timeline",
        "narration",
        "short_phrase",
        "articulation",
    }
    for metric in summary["metrics"].values():
        low, high = metric["mean_confidence_interval_95"]
        assert low <= metric["family_balanced_mean"] <= high
        assert metric["conservative_planning_wpm"] == low
    assert report["demo_subset"]["summary"]["recording_count"] == 4
    assert report["demo_subset"]["summary"]["confidence"]["level"] == "low"
    assert report["by_mode"]["lecture"]["recording_count"] == 4
    assert report["bootstrap"]["unit"] == "presentation_family_mean"
    assert report["scope"]["population_generalization"] == "not_established"


def test_order_independent_bootstrap_and_no_input_mutation():
    data = request(cohort())
    before = copy.deepcopy(data)
    forward = pace.calibrate(data)
    assert data == before
    data["samples"].reverse()
    assert pace.calibrate(data) == forward
    assert pace.validate_profile(forward) == forward


@pytest.mark.parametrize(
    "defect,reason",
    [
        ("language", "transcribed_language_mismatch"),
        ("language_probability", "language_confidence_low"),
        ("probability", "word_confidence_low"),
        ("compression_ratio", "transcription_compression_excessive"),
        ("average_log_probability", "transcription_log_probability_low"),
        ("nonspeech", "nonspeech_hallucination"),
        ("repetition", "repeated_phrase_hallucination"),
        ("speed", "impossible_local_word_rate"),
        ("few_words", "insufficient_lexical_evidence"),
        ("short", "sample_too_short"),
    ],
)
def test_versioned_quality_gates_retain_exclusions(defect, reason):
    row = sample(count=60)
    receipt = row["words"]
    if defect == "language":
        receipt["language"] = "ru"
    elif defect == "language_probability":
        receipt["language_probability"] = 0.5
    elif defect == "probability":
        for word in receipt["words"]:
            word["probability"] = 0.5
    elif defect in ("compression_ratio", "average_log_probability"):
        receipt["segments"][0][defect] = 3.0 if defect == "compression_ratio" else -2.0
    elif defect == "nonspeech":
        receipt["segments"][0].update(
            average_log_probability=-2.0, no_speech_probability=0.9
        )
    elif defect == "repetition":
        for index, word in enumerate(receipt["words"]):
            word["text"] = ("Thank", "you.")[index % 2]
    elif defect == "speed":
        for word in receipt["words"]:
            word["start_seconds"] /= 10
            word["end_seconds"] /= 10
    elif defect == "few_words":
        receipt["words"] = receipt["words"][:49]
    elif defect == "short":
        receipt["sample_duration_seconds"] = 60
    report = pace.calibrate(request([row]))
    assert report["summary"]["recording_count"] == 0
    assert reason in report["exclusions"][0]["reasons"]
    assert report["calibration"]["samples"][0] == row


def test_legitimate_slow_demo_is_retained_but_not_confident():
    row = sample(count=60, gap=10)
    report = pace.calibrate(request([row]))
    assert report["summary"]["recording_count"] == 1
    assert report["exclusions"] == []
    assert report["summary"]["metrics"]["timeline"]["family_balanced_mean"] < 6
    assert "too_little_narration_evidence" in report["summary"]["confidence"]["reasons"]


def test_empty_evidence_never_produces_default_rate():
    data = request([])
    data["exclusions"] = [
        {
            "schema_version": 1,
            "recording_id": "absent",
            "reasons": ["local_media_unavailable"],
        }
    ]
    data["demo_modes"] = []
    report = pace.calibrate(data)
    assert report["exclusions"] == data["exclusions"]
    assert report["summary"]["recording_count"] == 0
    assert report["summary"]["metrics"]["narration"]["family_balanced_mean"] is None
    assert (
        report["summary"]["metrics"]["narration"]["mean_confidence_interval_95"] is None
    )
    assert report["demo_subset"]["classification"] == "not_classified"


def test_source_duplicates_count_once_and_failed_first_sample_does_not_hide_good_evidence():
    first, second, third = sample("a"), sample("b"), sample("c")
    second["words"]["source_sha256"] = first["words"]["source_sha256"]
    third["words"]["source_sha256"] = first["words"]["source_sha256"]
    first["words"]["language_probability"] = 0.1
    report = pace.calibrate(request([third, second, first]))
    assert [row["recording_id"] for row in report["recordings"]] == ["b"]
    assert report["exclusions"] == [
        {
            "schema_version": 1,
            "recording_id": "a",
            "reasons": ["language_confidence_low"],
        },
        {
            "schema_version": 1,
            "recording_id": "c",
            "reasons": ["duplicate_source_bytes"],
        },
    ]


def test_conflicting_source_family_excludes_both_but_conflicting_duration_refuses():
    first, second = sample("a", "one"), sample("b", "two")
    second["words"]["source_sha256"] = first["words"]["source_sha256"]
    report = pace.calibrate(request([first, second]))
    assert report["summary"]["recording_count"] == 0
    assert all(
        row["reasons"] == ["source_family_conflict"] for row in report["exclusions"]
    )
    second["words"]["source_duration_seconds"] = 3601
    with pytest.raises(SpeechRateError) as exc:
        pace.calibrate(request([first, second]))
    assert exc.value.code == "pace_source_inconsistent"


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("schema_version", 3),
        ("generated_at", "2024-06-01"),
        ("generated_at", "not-a-date"),
        ("speaker", ""),
        ("language", "English"),
        ("catalog_sha256", "unknown"),
        ("demo_modes", ["demo", "demo"]),
        ("demo_modes", [None]),
        ("samples", None),
        ("samples", [sample()] * 65),
        ("exclusions", None),
    ],
)
def test_malformed_request_is_rejected(field, value):
    data = request()
    data[field] = value
    with pytest.raises(SpeechRateError):
        pace.calibrate(data)


def test_malformed_words_are_not_repaired_by_statistics_owner():
    row = sample()
    row["words"]["words"][0]["end_seconds"] = 0
    with pytest.raises(LocalMediaError):
        pace.calibrate(request([row]))


def test_duplicate_recording_identity_and_noncanonical_family_refuse():
    with pytest.raises(SpeechRateError) as exc:
        pace.calibrate(request([sample(), sample()]))
    assert exc.value.code == "pace_recording_duplicate"
    with pytest.raises(SpeechRateError) as exc:
        pace.calibrate(request([sample(family="Family  One")]))
    assert exc.value.code == "pace_family_invalid"


@pytest.mark.parametrize(
    "field", ["summary", "bootstrap", "calibration_sha256", "extra"]
)
def test_present_profile_tampering_fails_closed(field):
    report = pace.calibrate(request([]))
    report[field] = "tampered"
    with pytest.raises(SpeechRateError) as exc:
        pace.validate_profile(report)
    assert exc.value.code == "pace_profile_inconsistent"
