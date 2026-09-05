#!/usr/bin/env python3
"""Typed speaking-rate analysis and planning; no media acquisition or vault writes.

Owner: vault-profile. Schema/method v1 uses recorded, non-overlapping word
intervals, never evenly distributed segment timestamps. ``measure``,
``calibrate``, ``plan``, and ``verify`` read one JSON document on stdin and emit
one {schema_version, ok, data|error} envelope. Exit 0 succeeds, 1 rejects input,
2 reports usage/tool failure. Diagnostics never echo input values.

Input/output shapes, persistence, and reader compatibility are documented in
skills/vault-profile/references/speech-rates.md. Library entry points return
JSON-compatible objects and raise SpeechRateError on invalid contracts.

Bounds: 16 MiB JSON per request/result; 64 samples, 50,000 words per sample,
four hours per sample/source; one whitespace-free lexical token per word tuple
[text, start_seconds, end_seconds]. Times are relative to the sample. Recording
duration and word alignment must come from the same source generation. The
source SHA-256 is a provenance binding supplied by the acquisition owner, not
a claim that this arithmetic tool opened or authenticated the media.

Method word-gaps-v1: include each word span and each complete internal gap at
or below the metric's threshold (not a clipped portion of a longer gap).
Timeline includes the complete sample, including leading/trailing silence.
Narration retains gaps <=2 s, short_phrase <=1 s, articulation <=0.25 s.
Articulation is the explicitly thresholded operational metric, not a phonetic
voice-activity measurement. Profiles use equally weighted sample means and
observed sample ranges, not confidence intervals or population guarantees.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import statistics
import sys
from typing import Any, NoReturn


MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_SAMPLES = 64
MAX_WORDS = 50_000
MAX_DURATION_SECONDS = 4 * 60 * 60
METHOD_VERSION = "word-gaps-v1"
THRESHOLDS = {
    "timeline": None,
    "narration": 2.0,
    "short_phrase": 1.0,
    "articulation": 0.25,
}
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class SpeechRateError(ValueError):
    """Closed diagnostic; user-controlled words, paths, and values are omitted."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _fail(code: str, message: str) -> NoReturn:
    raise SpeechRateError(code, message)


def _record(value: Any, keys: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) != keys | {"schema_version"}:
        _fail("speech_shape_invalid", "Use the documented closed speech-rate shape.")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        _fail(
            "speech_schema_unsupported",
            "Use schema version 1; update the owner for other versions.",
        )
    return value


def _number(value: Any, *, positive: bool = False) -> float:
    if type(value) not in (int, float):
        _fail(
            "speech_number_invalid", "Use finite JSON numbers, not strings or booleans."
        )
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        _fail(
            "speech_number_invalid",
            "Use finite numbers within the supported arithmetic range.",
        )
    if value < 0 or (positive and value == 0):
        _fail(
            "speech_number_invalid",
            "Use positive durations and rates and nonnegative timestamps.",
        )
    return float(value)


def _text(value: Any, *, limit: int = 200) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        _fail(
            "speech_text_invalid",
            "Supply a nonempty bounded cohort or provenance label.",
        )
    return value


def _sha(value: Any) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        _fail(
            "speech_digest_invalid",
            "Supply the exact lowercase source SHA-256 from acquisition.",
        )
    return value


def _metric(value: Any) -> str:
    if not isinstance(value, str) or value not in THRESHOLDS:
        _fail(
            "speech_metric_invalid",
            "Name timeline, narration, short_phrase, or articulation.",
        )
    return value


def encode(value: Any) -> bytes:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode()
    if len(raw) > MAX_JSON_BYTES:
        _fail(
            "speech_json_too_large", "Reduce the calibration batch to at most 16 MiB."
        )
    return raw


def _digest(value: Any) -> str:
    return hashlib.sha256(encode(value)).hexdigest()


def validate_evidence(value: Any) -> dict:
    evidence = _record(
        value,
        {
            "timing_kind",
            "source_sha256",
            "source_duration_seconds",
            "sample_start_seconds",
            "sample_duration_seconds",
            "aligner",
            "words",
        },
    )
    if evidence["timing_kind"] != "recorded_words":
        _fail(
            "speech_recording_required",
            "Acquire actual recording word timestamps; predictions and segment timing are not evidence.",
        )
    _sha(evidence["source_sha256"])
    source_duration = _number(evidence["source_duration_seconds"], positive=True)
    duration = _number(evidence["sample_duration_seconds"], positive=True)
    start = _number(evidence["sample_start_seconds"])
    if source_duration > MAX_DURATION_SECONDS or start + duration > source_duration:
        _fail(
            "speech_window_invalid",
            "Choose a sample within the actual source duration and four-hour ceiling.",
        )
    _text(evidence["aligner"])
    words = evidence["words"]
    if not isinstance(words, list) or not 1 <= len(words) <= MAX_WORDS:
        _fail("speech_words_invalid", "Supply one to 50,000 actual aligned words.")
    previous_end = 0.0
    for word in words:
        if not isinstance(word, (list, tuple)) or len(word) != 3:
            _fail(
                "speech_word_invalid",
                "Use [word, start_seconds, end_seconds] for every aligned word.",
            )
        text, word_start, word_end = word
        _text(text)
        if any(c.isspace() for c in text) or not any(c.isalnum() for c in text):
            _fail(
                "speech_word_invalid",
                "Use one lexical token per aligned word; do not pass segments or punctuation-only tokens.",
            )
        word_start = _number(word_start)
        word_end = _number(word_end, positive=True)
        if word_start < previous_end or word_end <= word_start or word_end > duration:
            _fail(
                "speech_word_timing_invalid",
                "Supply ordered, non-overlapping positive word spans within the actual sample duration.",
            )
        previous_end = word_end
    return evidence


def _denominators(evidence: dict) -> dict[str, float]:
    words = evidence["words"]
    active = math.fsum(end - start for _, start, end in words)
    gaps = [right[1] - left[2] for left, right in zip(words, words[1:])]
    return {
        metric: evidence["sample_duration_seconds"]
        if threshold is None
        else active + math.fsum(gap for gap in gaps if gap <= threshold)
        for metric, threshold in THRESHOLDS.items()
    }


def measure(evidence: Any) -> dict:
    evidence = validate_evidence(evidence)
    denominators = _denominators(evidence)
    count = len(evidence["words"])
    return {
        "schema_version": 1,
        "method_version": METHOD_VERSION,
        "evidence_sha256": _digest(evidence),
        "source_sha256": evidence["source_sha256"],
        "word_count": count,
        "actual_duration_seconds": evidence["sample_duration_seconds"],
        "rates": [
            {
                "schema_version": 1,
                "metric": metric,
                "unit": "words_per_minute",
                "pause_threshold_seconds": THRESHOLDS[metric],
                "denominator_seconds": seconds,
                "value": _number(count * 60 / seconds, positive=True),
            }
            for metric, seconds in denominators.items()
        ],
    }


def calibrate(request: Any) -> dict:
    request = _record(request, {"cohort", "samples"})
    _text(request["cohort"])
    samples = request["samples"]
    if not isinstance(samples, list) or not 1 <= len(samples) <= MAX_SAMPLES:
        _fail(
            "speech_samples_invalid",
            "Supply one to 64 explicitly selected calibration samples.",
        )
    windows: dict[str, list[tuple[float, float]]] = {}
    source_durations = {}
    measurements = []
    for sample in samples:
        validate_evidence(sample)
        source = sample["source_sha256"]
        source_duration = sample["source_duration_seconds"]
        if source in source_durations and source_durations[source] != source_duration:
            _fail(
                "speech_source_inconsistent",
                "Use one actual duration for each unchanged recording generation.",
            )
        source_durations[source] = source_duration
        start = sample["sample_start_seconds"]
        end = start + sample["sample_duration_seconds"]
        prior = windows.setdefault(sample["source_sha256"], [])
        if any(start < old_end and end > old_start for old_start, old_end in prior):
            _fail(
                "speech_samples_overlap",
                "Select non-overlapping samples; do not count a recording window twice.",
            )
        prior.append((start, end))
        measurements.append(measure(sample))
    provenance = {
        "schema_version": 1,
        "sample_count": len(samples),
        "analyzed_duration_seconds": math.fsum(
            sample["sample_duration_seconds"] for sample in samples
        ),
        "cohort": request["cohort"],
        "method_version": METHOD_VERSION,
        "evidence_sha256": [
            measurement["evidence_sha256"] for measurement in measurements
        ],
        "range_kind": "observed_sample_range_not_confidence_interval",
    }
    rates = []
    for index, metric in enumerate(THRESHOLDS):
        values = [measurement["rates"][index]["value"] for measurement in measurements]
        rates.append(
            {
                "schema_version": 1,
                "metric": metric,
                "unit": "words_per_minute",
                "pause_threshold_seconds": THRESHOLDS[metric],
                "value": statistics.mean(values),
                "range": [min(values), max(values)],
                "basis": "measured",
                "provenance": copy.deepcopy(provenance),
            }
        )
    result = {
        "schema_version": 1,
        "calibration": copy.deepcopy(request),
        "rates": rates,
    }
    encode(result)
    return result


def validate_profile(value: Any) -> dict:
    profile = _record(value, {"calibration", "rates"})
    expected = calibrate(profile["calibration"])
    # Canonical JSON equality also rejects bool/int and int/float substitutions.
    if encode(profile) != encode(expected):
        _fail(
            "speech_profile_inconsistent",
            "Regenerate the speech profile from its recorded word evidence; do not edit derived rates.",
        )
    return profile


def validate_rate(value: Any) -> dict:
    rate = _record(
        value,
        {
            "metric",
            "unit",
            "pause_threshold_seconds",
            "value",
            "range",
            "basis",
            "provenance",
        },
    )
    metric = _metric(rate["metric"])
    threshold = rate["pause_threshold_seconds"]
    if threshold is not None:
        _number(threshold)
    if rate["unit"] != "words_per_minute" or threshold != THRESHOLDS[metric]:
        _fail(
            "speech_definition_invalid",
            "Use the named metric's v1 pause threshold and words_per_minute units.",
        )
    point = _number(rate["value"], positive=True)
    limits = rate["range"]
    if not isinstance(limits, (list, tuple)) or len(limits) != 2:
        _fail(
            "speech_range_invalid",
            "Supply an ordered [low, high] rate range containing the point estimate.",
        )
    low, high = (_number(n, positive=True) for n in limits)
    if not low <= point <= high:
        _fail(
            "speech_range_invalid",
            "Supply an ordered [low, high] rate range containing the point estimate.",
        )
    if rate["basis"] == "assumption":
        provenance = _record(rate["provenance"], {"reason"})
        _text(provenance["reason"])
    elif rate["basis"] == "measured":
        provenance = _record(
            rate["provenance"],
            {
                "sample_count",
                "analyzed_duration_seconds",
                "cohort",
                "method_version",
                "evidence_sha256",
                "range_kind",
            },
        )
        count = provenance["sample_count"]
        if type(count) is not int or not 1 <= count <= MAX_SAMPLES:
            _fail(
                "speech_provenance_invalid",
                "Preserve the measured profile's sample count and evidence provenance.",
            )
        _number(provenance["analyzed_duration_seconds"], positive=True)
        _text(provenance["cohort"])
        digests = provenance["evidence_sha256"]
        if (
            not isinstance(digests, list)
            or len(digests) != count
            or len(set(map(str, digests))) != count
        ):
            _fail(
                "speech_provenance_invalid",
                "Preserve one distinct evidence digest per measured sample.",
            )
        for digest in digests:
            _sha(digest)
        if (
            provenance["method_version"] != METHOD_VERSION
            or provenance["range_kind"]
            != "observed_sample_range_not_confidence_interval"
        ):
            _fail(
                "speech_provenance_invalid",
                "Use the current method and explicitly label observed ranges, not confidence intervals.",
            )
    else:
        _fail(
            "speech_basis_invalid",
            "Identify a rate as measured or an explicit assumption.",
        )
    return rate


def assumed_narration(low: float, high: float, *, reason: str) -> dict:
    low, high = _number(low, positive=True), _number(high, positive=True)
    return validate_rate(
        {
            "schema_version": 1,
            "metric": "narration",
            "unit": "words_per_minute",
            "pause_threshold_seconds": 2.0,
            "value": (low + high) / 2,
            "range": [low, high],
            "basis": "assumption",
            "provenance": {"schema_version": 1, "reason": reason},
        }
    )


def plan_duration(
    word_count: int,
    *,
    intended_metric: str,
    profile: Any = None,
    assumption: Any = None,
) -> dict:
    if _metric(intended_metric) != "narration":
        _fail(
            "speech_planning_metric_invalid",
            "Use narration for long-form duration planning; articulation is not elapsed narration.",
        )
    if type(word_count) is not int or not 1 <= word_count <= MAX_WORDS:
        _fail(
            "speech_word_count_invalid",
            "Supply a positive script word count within 50,000 words.",
        )
    if profile is not None:
        profile = validate_profile(profile)
        rate = next(
            rate for rate in profile["rates"] if rate["metric"] == intended_metric
        )
    elif assumption is not None:
        rate = validate_rate(assumption)
        if rate["metric"] != intended_metric or rate["basis"] != "assumption":
            _fail(
                "speech_assumption_invalid",
                "Supply an explicitly assumed narration rate, or the complete measured profile.",
            )
    else:
        _fail(
            "speech_rate_required",
            "Provide a measured narration profile or an explicitly labeled assumption.",
        )
    low, high = rate["range"]
    return {
        "schema_version": 1,
        "kind": "prediction_not_verification",
        "word_count": word_count,
        "intended_metric": intended_metric,
        "rate": copy.deepcopy(rate),
        "estimated_seconds": _number(word_count * 60 / rate["value"], positive=True),
        "estimated_range_seconds": [
            _number(word_count * 60 / high, positive=True),
            _number(word_count * 60 / low, positive=True),
        ],
    }


def verify_recording(evidence: Any, *, maximum_duration_seconds: float) -> dict:
    maximum = _number(maximum_duration_seconds, positive=True)
    measurement = measure(evidence)
    if (
        evidence["sample_start_seconds"] != 0
        or evidence["sample_duration_seconds"] != evidence["source_duration_seconds"]
    ):
        _fail(
            "speech_full_recording_required",
            "Verify the complete recording, not an interior calibration sample.",
        )
    return {
        "schema_version": 1,
        "kind": "recorded_duration_check",
        "maximum_duration_seconds": maximum,
        "fits_duration": measurement["actual_duration_seconds"] <= maximum,
        "measurement": measurement,
    }


def _pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("speech_json_invalid", "Remove duplicate JSON keys.")
        result[key] = value
    return result


def _constant(_: str) -> NoReturn:
    _fail("speech_json_invalid", "Use finite standard JSON values.")


def decode(raw: bytes) -> Any:
    if len(raw) > MAX_JSON_BYTES:
        _fail(
            "speech_json_too_large", "Reduce the calibration batch to at most 16 MiB."
        )
    try:
        return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        _fail(
            "speech_json_invalid",
            "Supply one UTF-8 JSON document matching the owner schema.",
        )


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        _fail(
            "speech_usage_invalid", "Use --help for the speech-rate command contract."
        )


def main(argv: list[str] | None = None) -> int:
    try:
        parser = _Parser(description=__doc__, allow_abbrev=False, add_help=False)
        parser.add_argument(
            "action", nargs="?", choices=("measure", "calibrate", "plan", "verify")
        )
        parser.add_argument("--help", action="store_true")
        args = parser.parse_args(argv)
        if args.help:
            result = {"help": __doc__}
        elif args.action:
            request = decode(sys.stdin.buffer.read(MAX_JSON_BYTES + 1))
            if args.action == "measure":
                result = measure(request)
            elif args.action == "calibrate":
                result = calibrate(request)
            elif args.action == "plan":
                request = _record(
                    request, {"word_count", "intended_metric", "profile", "assumption"}
                )
                result = plan_duration(
                    request["word_count"],
                    intended_metric=request["intended_metric"],
                    profile=request["profile"],
                    assumption=request["assumption"],
                )
            else:
                request = _record(request, {"evidence", "maximum_duration_seconds"})
                result = verify_recording(
                    request["evidence"],
                    maximum_duration_seconds=request["maximum_duration_seconds"],
                )
        else:
            _fail(
                "speech_usage_invalid",
                "Choose measure, calibrate, plan, or verify; use --help.",
            )
        print(encode({"schema_version": 1, "ok": True, "data": result}).decode())
        return 0
    except SpeechRateError as exc:
        code, message = exc.code, str(exc)
        status = 2 if code == "speech_usage_invalid" else 1
    except OSError:
        code, message, status = (
            "speech_io_failed",
            "Check access to the input/output streams and retry.",
            2,
        )
    # Consumers treat absent/invalid JSON as a silent contract failure. Emit a
    # closed error envelope; a traceback would replace their required JSON.
    except Exception:  # noqa: BLE001 — outer-boundary-process-contract
        code, message, status = (
            "speech_unexpected_failure",
            "Preserve the input and report this owner failure code.",
            2,
        )
    print(
        json.dumps(
            {
                "schema_version": 1,
                "ok": False,
                "error": {"code": code, "message": message},
            }
        )
    )
    print(message, file=sys.stderr)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
