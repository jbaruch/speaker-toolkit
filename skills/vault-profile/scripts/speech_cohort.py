"""Deterministic, read-only cohort planning for recorded speech calibration.

The caller supplies a strict ingress-owner database snapshot. This module does
not open media, infer speaker identity, infer presentation families, or rewrite
catalog data. Every talk remains in the report, including exclusions. Family,
mode, language, and solo-speaker declarations come from structured_data.
Actual source availability, duration, and generation are acquisition-owner facts,
not established by this metadata-only plan.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import date
import re
from typing import Any, NoReturn

from speech_rates import MAX_DURATION_SECONDS, MAX_SAMPLES, SpeechRateError


COHORT_METHOD = "catalog-solo-family-coverage-v1"
MAX_TALKS = 10000
SAMPLE_TARGET_SECONDS = 600.0
SAMPLE_MINIMUM_SECONDS = 180.0
EDGE_MARGIN_SECONDS = 30.0
_VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")
_LANGUAGE = re.compile(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})*\Z")


def _fail(code: str, message: str) -> NoReturn:
    raise SpeechRateError(code, message)


def _label(value: Any, *, limit: int = 500) -> str | None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > limit
        or any(ord(char) < 32 for char in value)
    ):
        return None
    return " ".join(value.split())


def _year(value: Any) -> int | None:
    if (
        not isinstance(value, str)
        or re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", value) is None
    ):
        return None
    parts = [int(part) for part in value.split("-")]
    try:
        return date(*parts, *([1] * (3 - len(parts)))).year
    except ValueError:
        return None


def _candidate(talk: dict, language: str, allow_download: bool) -> dict:
    filename = talk["filename"]
    structured = talk.get("structured_data")
    structured = structured if isinstance(structured, Mapping) else {}
    family = _label(structured.get("talk_family"))
    mode = _label(structured.get("mode"), limit=64)
    declared_language = _label(structured.get("delivery_language"), limit=32)
    declared_language = declared_language.casefold() if declared_language else None
    reasons = []
    if family is None:
        reasons.append("presentation_family_missing")
    if mode is None:
        reasons.append("delivery_mode_missing")
    if declared_language is None:
        reasons.append("delivery_language_missing")
    elif declared_language != language:
        reasons.append("different_delivery_language")
    # A missing declaration is not proof of single-speaker audio. Never infer
    # which voice belongs to the vault owner from a talk title or transcript.
    if structured.get("co_presenter") is not False:
        reasons.append(
            "multiple_speakers"
            if structured.get("co_presenter") is True
            else "solo_speaker_scope_unverified"
        )
    co_presenters = structured.get("co_presenters")
    if co_presenters not in (None, []):
        reasons.append("co_presenters_declared")
    extraction = structured.get("video_extraction")
    extraction = extraction if isinstance(extraction, Mapping) else {}
    declared_paths = [
        value
        for value in (
            talk.get("video_local_path"),
            talk.get("video_path"),
            extraction.get("source_video_path"),
        )
        if value is not None and value != ""
    ]
    source = None
    if declared_paths:
        if any(_label(value, limit=8192) is None for value in declared_paths):
            reasons.append("local_recording_locator_invalid")
        elif len(set(declared_paths)) != 1:
            reasons.append("local_recording_locator_conflict")
        else:
            # Keep the literal locator. Only the acquisition owner resolves it.
            source = {"kind": "local_media", "locator": declared_paths[0]}
    video_id = talk.get("youtube_id")
    if video_id in (None, ""):
        video_id = None
    elif not isinstance(video_id, str) or _VIDEO_ID.fullmatch(video_id) is None:
        reasons.append("recording_identity_invalid")
        video_id = None
    if source is None and not declared_paths:
        if video_id is not None and allow_download:
            source = {"kind": "youtube", "video_id": video_id}
        else:
            reasons.append(
                "recording_download_not_enabled"
                if video_id is not None
                else "recording_source_missing"
            )
    return {
        "schema_version": 1,
        "recording_id": filename,
        "family": family.casefold() if family else None,
        "family_label": family,
        "mode": mode,
        "language": declared_language,
        "year": _year(talk.get("date")),
        "youtube_id": video_id,
        "source": source,
        "status": "excluded" if reasons else "eligible",
        "reasons": sorted(set(reasons)),
    }


def _canonical_duplicate(group: list[dict], talks: dict[str, dict]) -> dict | None:
    """Honor an explicit same-recording relation; never merge conflicting facts."""
    if len({row["family"] for row in group}) != 1:
        return None
    names = {row["recording_id"] for row in group}
    canonical = []
    for row in group:
        talk = talks[row["recording_id"]]
        relation = talk.get("source_relation")
        target = None
        if isinstance(relation, Mapping) and relation.get("type") in {
            "duplicate",
            "borrowed_recording",
        }:
            target = relation.get("target_filename")
        if target is None:
            target = next(
                (
                    talk[key]
                    for key in (
                        "duplicate_of",
                        "_duplicate_of",
                        "borrowed_recording_from",
                        "_borrowed_recording_from",
                    )
                    if key in talk
                ),
                None,
            )
        if target is None:
            canonical.append(row)
        elif (
            not isinstance(target, str)
            or target not in names
            or target == row["recording_id"]
        ):
            return None
    return canonical[0] if len(canonical) == 1 else None


def plan_cohort(
    database: Any,
    speaker: str,
    *,
    language: str,
    maximum_recordings: int = 12,
    allow_download: bool = False,
    demo_modes: tuple[str, ...] = (),
) -> dict:
    """Plan a bounded diverse cohort; all metadata decisions remain inspectable."""
    if not isinstance(database, dict) or not isinstance(database.get("config"), dict):
        _fail("pace_database_invalid", "Read a strict ingress-owner database snapshot.")
    requested = _label(speaker)
    configured = _label(database["config"].get("speaker_name"))
    if (
        requested is None
        or configured is None
        or requested.casefold() != configured.casefold()
    ):
        _fail(
            "pace_speaker_unverified",
            "Select the speaker explicitly named in the vault configuration.",
        )
    if not isinstance(language, str) or _LANGUAGE.fullmatch(language) is None:
        _fail(
            "pace_language_invalid",
            "Select an explicit lowercase delivery-language code.",
        )
    if (
        type(maximum_recordings) is not int
        or not 1 <= maximum_recordings <= MAX_SAMPLES
    ):
        _fail("pace_cohort_limit_invalid", "Select one to 64 recordings.")
    if type(allow_download) is not bool:
        _fail(
            "pace_download_option_invalid",
            "Explicitly enable or disable recording downloads.",
        )
    if (
        not isinstance(demo_modes, (tuple, list))
        or any(
            _label(mode, limit=64) is None or _label(mode, limit=64) != mode
            for mode in demo_modes
        )
        or len(set(demo_modes)) != len(demo_modes)
    ):
        _fail(
            "pace_demo_modes_invalid",
            "Supply unique explicit demo/tutorial mode identifiers.",
        )
    raw = database.get("talks")
    if not isinstance(raw, list) or len(raw) > MAX_TALKS:
        _fail(
            "pace_database_invalid",
            "Read an owner snapshot containing at most 10,000 talks.",
        )
    talks = {}
    for talk in raw:
        if (
            not isinstance(talk, dict)
            or _label(talk.get("filename"), limit=500) is None
            or _label(talk.get("filename"), limit=500) != talk.get("filename")
        ):
            _fail(
                "pace_talk_identity_invalid",
                "Repair missing or malformed talk identities through ingress.",
            )
        name = talk["filename"]
        if name in talks:
            _fail(
                "pace_talk_identity_duplicate",
                "Resolve duplicate talk identities through ingress.",
            )
        talks[name] = talk
    rows = [_candidate(talks[name], language, allow_download) for name in sorted(talks)]
    groups = defaultdict(list)
    for row in rows:
        if row["youtube_id"] is not None:
            groups[row["youtube_id"]].append(row)
    for group in groups.values():
        if len(group) < 2:
            continue
        canonical = _canonical_duplicate(group, talks)
        # An excluded declaration can contradict another row's solo-speaker
        # claim. Do not hide that evidence by grouping eligible rows alone.
        if any(
            {"multiple_speakers", "co_presenters_declared"} & set(row["reasons"])
            for row in group
        ) or (canonical is not None and canonical["status"] != "eligible"):
            canonical = None
        for row in group:
            if row is not canonical and row["status"] == "eligible":
                row["status"] = "excluded"
                row["reasons"] = [
                    "duplicate_recording"
                    if canonical is not None
                    else "duplicate_recording_identity_unresolved"
                ]
    available = [row for row in rows if row["status"] == "eligible"]
    family_counts, year_counts, mode_counts = Counter(), Counter(), Counter()
    selected = []
    while available and len(selected) < maximum_recordings:
        row = min(
            available,
            key=lambda item: (
                family_counts[item["family"]],
                item["source"]["kind"] != "local_media",
                year_counts[item["year"]],
                mode_counts[item["mode"]],
                item["recording_id"],
            ),
        )
        available.remove(row)
        row["status"] = "selected"
        selected.append(row["recording_id"])
        family_counts[row["family"]] += 1
        year_counts[row["year"]] += 1
        mode_counts[row["mode"]] += 1
    for row in available:
        row["status"] = "not_selected"
        row["reasons"] = ["cohort_budget"]
    return {
        "schema_version": 1,
        "method_version": COHORT_METHOD,
        "speaker": configured,
        "language": language,
        "maximum_recordings": maximum_recordings,
        "allow_download": allow_download,
        "demo_modes": sorted(demo_modes),
        "selected_recording_ids": selected,
        "recordings": rows,
    }


def sample_window(duration_seconds: Any) -> tuple[float, float]:
    """Choose an interior window from an acquisition-owner measured duration."""
    if (
        type(duration_seconds) not in (int, float)
        or not 0 < duration_seconds <= MAX_DURATION_SECONDS
    ):
        _fail(
            "pace_duration_invalid",
            "Acquire a finite recording duration through the media owner.",
        )
    duration = float(duration_seconds)
    margin = max(EDGE_MARGIN_SECONDS, duration * 0.1)
    window = min(SAMPLE_TARGET_SECONDS, duration - 2 * margin)
    if window < SAMPLE_MINIMUM_SECONDS:
        _fail(
            "pace_recording_too_short",
            "Select a recording with at least three minutes of interior speech.",
        )
    return ((duration - window) / 2, window)
