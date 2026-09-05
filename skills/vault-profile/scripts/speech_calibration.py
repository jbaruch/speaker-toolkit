"""Family-balanced sampled-speech profiles; deterministic arithmetic, no I/O.

Owner: vault-profile. Profile schema v2 is distinct from the v1 equal-sample
profile; v1 data must never be relabeled as family-balanced evidence. Every
derived field can be recomputed from the retained calibration request. Bootstrap
intervals describe the mean conditional on the selected presentation families,
not a prediction interval for an individual future recording.
"""

from __future__ import annotations

from collections import defaultdict
import copy
from datetime import datetime
import hashlib
import math
from pathlib import Path
import random
import re
import statistics
import sys
from typing import Any, NoReturn

INGRESS_SCRIPTS = Path(__file__).resolve().parents[2] / "vault-ingress" / "scripts"
if str(INGRESS_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(INGRESS_SCRIPTS))

from local_media_words import LocalMediaError, validate_word_sample  # noqa: E402
from speech_rates import (  # noqa: E402
    MAX_SAMPLES,
    THRESHOLDS,
    SpeechRateError,
    encode,
    measure,
    validate_rate,
)


CALIBRATION_METHOD = "family-balanced-word-gaps-v2"
MEAN_INTERVAL_KIND = (
    "mean_uncertainty_conditional_on_selected_families_not_a_prediction_interval"
)
QUALITY_METHOD = "sampled-whisper-quality-v1"
BOOTSTRAP_SEED = 368
BOOTSTRAP_REPLICATES = 4000
QUALITY_POLICY = {
    "schema_version": 1,
    "method_version": QUALITY_METHOD,
    "minimum_language_probability": 0.8,
    "minimum_mean_word_probability": 0.65,
    "maximum_compression_ratio": 2.4,
    "minimum_average_log_probability": -1.0,
    "maximum_no_speech_probability": 0.6,
    "maximum_twelve_word_wpm": 600.0,
    "minimum_lexical_words": 50,
    "minimum_sample_seconds": 180.0,
    "repetition_minimum_cycles": 4,
    "repetition_minimum_words": 24,
}
CONFIDENCE_POLICY = {
    "schema_version": 1,
    "minimum_recordings": 8,
    "minimum_families": 5,
    "minimum_analyzed_seconds": 3600.0,
    "minimum_years": 3,
    "minimum_modes": 2,
    "minimum_narration_seconds": 1800.0,
}
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")


def _fail(code: str, action: str) -> NoReturn:
    raise SpeechRateError(code, action)


def _closed(value: Any, version: int, fields: set[str]) -> dict:
    if (
        not isinstance(value, dict)
        or set(value) != fields | {"schema_version"}
        or type(value["schema_version"]) is not int
        or value["schema_version"] != version
    ):
        _fail("pace_shape_invalid", "Use the documented owner calibration schema.")
    return value


def _label(value: Any, *, maximum: int = 500) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or any(ord(char) < 32 for char in value)
    ):
        _fail(
            "pace_metadata_invalid",
            "Preserve bounded recording and cohort identifiers.",
        )
    return value


def _sample(value: Any) -> dict:
    sample = _closed(value, 1, {"recording_id", "family", "mode", "year", "words"})
    for key in ("recording_id", "family", "mode"):
        _label(sample[key])
    if sample["family"] != " ".join(sample["family"].split()).casefold():
        _fail("pace_family_invalid", "Use the cohort owner's normalized family ID.")
    year = sample["year"]
    if year is not None and (type(year) is not int or not 1 <= year <= 9999):
        _fail(
            "pace_metadata_invalid",
            "Preserve the catalog year or an explicit unknown year.",
        )
    validate_word_sample(sample["words"])
    return sample


def _word_evidence(sample: dict) -> dict:
    words = sample["words"]
    model = words["model"]
    aligner = (
        f"mlx-whisper/{words['provider_version']};{model['id']}@{model['revision']}"
    )
    return {
        "schema_version": 1,
        "timing_kind": "recorded_words",
        "source_sha256": words["source_sha256"],
        "source_duration_seconds": words["source_duration_seconds"],
        "sample_start_seconds": words["sample_start_seconds"],
        "sample_duration_seconds": words["sample_duration_seconds"],
        "aligner": aligner,
        "words": [
            [item["text"], item["start_seconds"], item["end_seconds"]]
            for item in words["words"]
        ],
    }


def _repetitive(tokens: list[str]) -> bool:
    for width in range(2, 9):
        for offset in range(width):
            previous = None
            run = 0
            for index in range(offset, len(tokens) - width + 1, width):
                block = tokens[index : index + width]
                run = run + 1 if block == previous else 1
                previous = block
                if (
                    run >= QUALITY_POLICY["repetition_minimum_cycles"]
                    and run * width >= QUALITY_POLICY["repetition_minimum_words"]
                ):
                    return True
    return False


def quality_findings(sample: dict, expected_language: str) -> list[str]:
    """Reject source/timing pathologies, not legitimate slow or fast outliers."""
    receipt = sample["words"]
    words = receipt["words"]
    reasons = set()
    if receipt["language"] != expected_language:
        reasons.add("transcribed_language_mismatch")
    if receipt["language_probability"] < QUALITY_POLICY["minimum_language_probability"]:
        reasons.add("language_confidence_low")
    if len(words) < QUALITY_POLICY["minimum_lexical_words"]:
        reasons.add("insufficient_lexical_evidence")
    if receipt["sample_duration_seconds"] < QUALITY_POLICY["minimum_sample_seconds"]:
        reasons.add("sample_too_short")
    if (
        statistics.mean(word["probability"] for word in words)
        < QUALITY_POLICY["minimum_mean_word_probability"]
    ):
        reasons.add("word_confidence_low")
    for segment in receipt["segments"]:
        if segment["compression_ratio"] > QUALITY_POLICY["maximum_compression_ratio"]:
            reasons.add("transcription_compression_excessive")
        if (
            segment["average_log_probability"]
            < QUALITY_POLICY["minimum_average_log_probability"]
        ):
            reasons.add("transcription_log_probability_low")
            if (
                segment["no_speech_probability"]
                > QUALITY_POLICY["maximum_no_speech_probability"]
            ):
                reasons.add("nonspeech_hallucination")
    for index in range(len(words) - 11):
        elapsed = words[index + 11]["end_seconds"] - words[index]["start_seconds"]
        if 12 * 60 / elapsed > QUALITY_POLICY["maximum_twelve_word_wpm"]:
            reasons.add("impossible_local_word_rate")
            break
    tokens = [re.sub(r"\W+", "", word["text"].casefold()) for word in words]
    if _repetitive(tokens):
        reasons.add("repeated_phrase_hallucination")
    return sorted(reasons)


def _quantile(ordered: list[float], probability: float) -> float:
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _bootstrap(values: list[float]) -> list[float] | None:
    if len(values) < 2:
        return None
    # The production algorithm owns its fixed resampling seed and count. Test
    # fixtures never use RNG to generate or select the data under test.
    rng = random.Random(BOOTSTRAP_SEED)
    means = sorted(
        # Use the same correctly rounded mean as the reported family estimate.
        # Summing then dividing can round a constant five-family resample just
        # beyond its observed endpoint and make a valid copied rate fail closed.
        statistics.mean(values[rng.randrange(len(values))] for _ in values)
        for _ in range(BOOTSTRAP_REPLICATES)
    )
    return [_quantile(means, 0.025), _quantile(means, 0.975)]


def _confidence(recordings: list[dict], *, mode_subset: bool = False) -> dict:
    families = {row["family"] for row in recordings}
    years = {row["year"] for row in recordings if row["year"] is not None}
    modes = {row["mode"] for row in recordings}
    seconds = math.fsum(row["sample_duration_seconds"] for row in recordings)
    reasons = []
    for failed, reason in (
        (
            len(recordings) < CONFIDENCE_POLICY["minimum_recordings"],
            "too_few_recordings",
        ),
        (
            len(families) < CONFIDENCE_POLICY["minimum_families"],
            "too_few_presentation_families",
        ),
        (
            seconds < CONFIDENCE_POLICY["minimum_analyzed_seconds"],
            "too_little_recorded_speech",
        ),
        (len(years) < CONFIDENCE_POLICY["minimum_years"], "year_coverage_narrow"),
        (
            not mode_subset and len(modes) < CONFIDENCE_POLICY["minimum_modes"],
            "delivery_modes_homogeneous",
        ),
        (any(row["year"] is None for row in recordings), "catalog_year_unknown"),
        (
            math.fsum(row["denominators"]["narration"] for row in recordings)
            < CONFIDENCE_POLICY["minimum_narration_seconds"],
            "too_little_narration_evidence",
        ),
    ):
        if failed:
            reasons.append(reason)
    return {
        "schema_version": 1,
        "level": "low" if reasons else "conditional",
        "reasons": reasons,
    }


def _summarize(recordings: list[dict], *, mode_subset: bool = False) -> dict:
    by_family = defaultdict(list)
    for recording in recordings:
        by_family[recording["family"]].append(recording)
    families = []
    for family in sorted(by_family):
        members = by_family[family]
        families.append(
            {
                "schema_version": 1,
                "family": family,
                "recording_ids": sorted(member["recording_id"] for member in members),
                "means": {
                    metric: statistics.mean(
                        member["values"][metric] for member in members
                    )
                    for metric in THRESHOLDS
                },
            }
        )
    confidence = _confidence(recordings, mode_subset=mode_subset)
    metrics = {}
    for metric, threshold in THRESHOLDS.items():
        observed = [row["values"][metric] for row in recordings]
        means = [family["means"][metric] for family in families]
        interval = _bootstrap(means) if means else None
        metrics[metric] = {
            "schema_version": 1,
            "unit": "words_per_minute",
            "pause_threshold_seconds": threshold,
            "family_balanced_mean": statistics.mean(means) if means else None,
            "family_median": statistics.median(means) if means else None,
            "family_standard_deviation": statistics.pstdev(means) if means else None,
            "family_mean_range": [min(means), max(means)] if means else None,
            "observed_recording_range": [min(observed), max(observed)]
            if observed
            else None,
            "mean_confidence_interval_95": interval,
            "conservative_planning_wpm": interval[0]
            if interval is not None and confidence["level"] == "conditional"
            else None,
        }
    return {
        "schema_version": 1,
        "recording_count": len(recordings),
        "presentation_family_count": len(families),
        "analyzed_duration_seconds": math.fsum(
            row["sample_duration_seconds"] for row in recordings
        ),
        "narration_duration_seconds": math.fsum(
            row["denominators"]["narration"] for row in recordings
        ),
        "years": sorted({row["year"] for row in recordings if row["year"] is not None}),
        "modes": sorted({row["mode"] for row in recordings}),
        "confidence": confidence,
        "families": families,
        "metrics": metrics,
    }


def calibrate(request: Any) -> dict:
    """Build v2 from owner word samples and explicit acquisition exclusions."""
    encode(request)
    request = _closed(
        request,
        2,
        {
            "speaker",
            "language",
            "catalog_sha256",
            "generated_at",
            "demo_modes",
            "samples",
            "exclusions",
        },
    )
    _label(request["speaker"])
    _label(request["language"], maximum=32)
    if re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})*", request["language"]) is None:
        _fail("pace_language_invalid", "Supply an explicit language code.")
    digest = request["catalog_sha256"]
    if not isinstance(digest, str) or _SHA.fullmatch(digest) is None:
        _fail(
            "pace_catalog_binding_invalid",
            "Use the exact strict-owner catalog snapshot digest.",
        )
    generated_at = _label(request["generated_at"], maximum=100)
    try:
        stamp = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SpeechRateError(
            "pace_timestamp_invalid",
            "Supply an explicit timezone-aware observation time.",
        ) from exc
    if stamp.utcoffset() is None:
        _fail(
            "pace_timestamp_invalid",
            "Supply an explicit timezone-aware observation time.",
        )
    demo_modes = request["demo_modes"]
    if not isinstance(demo_modes, list) or len(demo_modes) > 64:
        _fail(
            "pace_demo_modes_invalid",
            "Supply a bounded list of explicit demo/tutorial mode IDs.",
        )
    for mode in demo_modes:
        _label(mode, maximum=64)
    if len(set(demo_modes)) != len(demo_modes):
        _fail("pace_demo_modes_invalid", "Supply unique demo/tutorial mode IDs.")
    samples = request["samples"]
    exclusions = request["exclusions"]
    if (
        not isinstance(samples, list)
        or len(samples) > MAX_SAMPLES
        or not isinstance(exclusions, list)
        or len(exclusions) > 10000
    ):
        _fail(
            "pace_cohort_limit_invalid",
            "Use at most 64 samples and 10,000 explicit exclusions.",
        )
    identifiers = set()
    rejected = []
    for exclusion in exclusions:
        exclusion = _closed(exclusion, 1, {"recording_id", "reasons"})
        identifier = _label(exclusion["recording_id"])
        reasons = exclusion["reasons"]
        if (
            not isinstance(reasons, list)
            or not 1 <= len(reasons) <= 64
            or any(
                not isinstance(reason, str) or _CODE.fullmatch(reason) is None
                for reason in reasons
            )
        ):
            _fail(
                "pace_exclusion_invalid",
                "Record bounded, explicit exclusion reason codes.",
            )
        if identifier in identifiers:
            _fail("pace_recording_duplicate", "Report each recording identity once.")
        identifiers.add(identifier)
        rejected.append(copy.deepcopy(exclusion))
    admitted = []
    source_groups = defaultdict(list)
    for value in samples:
        sample = _sample(value)
        identifier = sample["recording_id"]
        if identifier in identifiers:
            _fail("pace_recording_duplicate", "Report each recording identity once.")
        identifiers.add(identifier)
        source_groups[sample["words"]["source_sha256"]].append(sample)
    for source in sorted(source_groups):
        group = sorted(source_groups[source], key=lambda sample: sample["recording_id"])
        if len({sample["words"]["source_duration_seconds"] for sample in group}) != 1:
            _fail(
                "pace_source_inconsistent",
                "Use one measured duration per unchanged source digest.",
            )
        conflicting_family = len({sample["family"] for sample in group}) != 1
        source_admitted = False
        for sample in group:
            reasons = quality_findings(sample, request["language"])
            if conflicting_family:
                reasons.append("source_family_conflict")
            elif source_admitted:
                reasons.append("duplicate_source_bytes")
            if reasons:
                rejected.append(
                    {
                        "schema_version": 1,
                        "recording_id": sample["recording_id"],
                        "reasons": sorted(set(reasons)),
                    }
                )
                continue
            result = measure(_word_evidence(sample))
            source_admitted = True
            admitted.append(
                {
                    "schema_version": 1,
                    "recording_id": sample["recording_id"],
                    "family": sample["family"],
                    "year": sample["year"],
                    "mode": sample["mode"],
                    "language": sample["words"]["language"],
                    "source_sha256": sample["words"]["source_sha256"],
                    "sample_sha256": sample["words"]["sample_sha256"],
                    "sample_start_seconds": sample["words"]["sample_start_seconds"],
                    "sample_duration_seconds": sample["words"][
                        "sample_duration_seconds"
                    ],
                    "evidence_sha256": result["evidence_sha256"],
                    "word_count": result["word_count"],
                    "values": {
                        rate["metric"]: rate["value"] for rate in result["rates"]
                    },
                    "denominators": {
                        rate["metric"]: rate["denominator_seconds"]
                        for rate in result["rates"]
                    },
                }
            )
    admitted.sort(key=lambda recording: recording["recording_id"])
    rejected.sort(key=lambda exclusion: exclusion["recording_id"])
    canonical = copy.deepcopy(request)
    canonical["samples"] = sorted(
        canonical["samples"], key=lambda sample: sample["recording_id"]
    )
    canonical["exclusions"] = sorted(
        canonical["exclusions"], key=lambda exclusion: exclusion["recording_id"]
    )
    canonical["demo_modes"] = sorted(demo_modes)
    summary = _summarize(admitted)
    demo = [row for row in admitted if row["mode"] in demo_modes]
    result = {
        "schema_version": 2,
        "method_version": CALIBRATION_METHOD,
        "calibration": canonical,
        "calibration_sha256": hashlib.sha256(encode(canonical)).hexdigest(),
        "quality_policy": copy.deepcopy(QUALITY_POLICY),
        "confidence_policy": copy.deepcopy(CONFIDENCE_POLICY),
        "bootstrap": {
            "schema_version": 1,
            "unit": "presentation_family_mean",
            "method": "percentile",
            "replicates": BOOTSTRAP_REPLICATES,
            "seed": BOOTSTRAP_SEED,
            "interpretation": MEAN_INTERVAL_KIND,
        },
        "recordings": admitted,
        "exclusions": rejected,
        "summary": summary,
        "by_mode": {
            mode: _summarize(
                [row for row in admitted if row["mode"] == mode], mode_subset=True
            )
            for mode in summary["modes"]
        },
        "demo_subset": {
            "classification": "explicit_mode_ids" if demo_modes else "not_classified",
            "mode_ids": sorted(demo_modes),
            "summary": _summarize(demo, mode_subset=True),
        },
        "scope": {
            "speaker_basis": "catalog_declared_solo_presenter",
            "language_confidence_basis": "first_30_seconds_of_each_sample",
            "speaker_diarization": "not_performed",
            "population_generalization": "not_established",
        },
    }
    encode(result)
    return result


def validate_profile(value: Any) -> dict:
    if (
        not isinstance(value, dict)
        or type(value.get("schema_version")) is not int
        or value.get("schema_version") != 2
    ):
        _fail("pace_shape_invalid", "Use a current family-balanced owner profile.")
    if "calibration" not in value:
        _fail("pace_shape_invalid", "Retain the complete owner calibration request.")
    try:
        expected = calibrate(value["calibration"])
    except LocalMediaError:
        _fail(
            "pace_word_evidence_invalid",
            "Reacquire invalid word evidence through the ingress owner before planning.",
        )
    if encode(value) != encode(expected):
        _fail(
            "pace_profile_inconsistent",
            "Regenerate derived calibration fields through the owner; never restamp them.",
        )
    return value


def narration_rate(profile: Any) -> dict:
    """Select an overall v2 narration rate only from validated, covered evidence."""
    profile = validate_profile(profile)
    summary = profile["summary"]
    if summary["confidence"]["level"] != "conditional":
        _fail(
            "pace_confidence_insufficient",
            "Acquire broader independent recording evidence through the owner; a low-confidence profile is not a planning default.",
        )
    metric = summary["metrics"]["narration"]
    return validate_rate(
        {
            "schema_version": 2,
            "metric": "narration",
            "unit": metric["unit"],
            "pause_threshold_seconds": metric["pause_threshold_seconds"],
            "value": metric["family_balanced_mean"],
            "range": copy.deepcopy(metric["observed_recording_range"]),
            "basis": "measured",
            "mean_confidence_interval_95": copy.deepcopy(
                metric["mean_confidence_interval_95"]
            ),
            "conservative_planning_wpm": metric["conservative_planning_wpm"],
            "provenance": {
                "schema_version": 2,
                "sample_count": summary["recording_count"],
                "presentation_family_count": summary["presentation_family_count"],
                "analyzed_duration_seconds": summary["analyzed_duration_seconds"],
                "cohort": profile["calibration"]["speaker"],
                "language": profile["calibration"]["language"],
                "method_version": CALIBRATION_METHOD,
                "evidence_sha256": [
                    row["evidence_sha256"] for row in profile["recordings"]
                ],
                "calibration_sha256": profile["calibration_sha256"],
                "range_kind": "observed_recording_range_not_prediction_interval",
                "confidence_level": "conditional",
                "interval_kind": MEAN_INTERVAL_KIND,
            },
        }
    )
