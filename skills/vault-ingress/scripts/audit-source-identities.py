#!/usr/bin/env python3
"""Capture and audit active YouTube source identities without mutating the vault.

The helper reads a tracking database, fetches stable yt-dlp metadata once per
active YouTube ID, compares that evidence with every record using the ID, and
prints one deterministic JSON report. It never writes the database, never
applies a URL, and never treats uploader/upload date as speaker/recorded date.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse


REPORT_SCHEMA_VERSION = 1
SOURCE_IDENTITY_SCHEMA_VERSION = 1
YT_DLP_TIMEOUT_SECONDS = 60
YOUTUBE_ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")
WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
TITLE_STOP_WORDS = frozenset({
    "a", "an", "and", "at", "by", "conference", "for", "from", "in",
    "keynote", "of", "on", "or", "session", "talk", "the", "to", "with",
})
CLIP_MARKERS = frozenset({
    "clip", "demo", "excerpt", "highlight", "highlights", "preview", "promo",
    "short", "teaser", "trailer",
})
ERROR_CODES = frozenset({
    "active_youtube_url_invalid",
    "database_shape_invalid",
    "metadata_fetch_failed",
    "provider_metadata_incomplete",
    "provider_video_id_mismatch",
    "provider_webpage_identity_mismatch",
    "talk_shape_invalid",
    "talks_shape_invalid",
})


class MetadataFetchError(RuntimeError):
    """yt-dlp could not return usable JSON metadata."""


def _nonempty(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def parse_youtube_id(value: Any) -> str | None:
    """Parse the supported watch, short, embed, and youtu.be URL forms."""
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    if "://" not in candidate:
        candidate = "https://" + candidate
    parsed = urlparse(candidate)
    host = (parsed.hostname or "").casefold().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("m."):
        host = host[2:]

    video_id: str | None = None
    if host == "youtu.be":
        parts = [part for part in parsed.path.split("/") if part]
        video_id = parts[0] if parts else None
    elif host in {"youtube.com", "youtube-nocookie.com"}:
        parts = [part for part in parsed.path.split("/") if part]
        if parts == ["watch"]:
            values = parse_qs(parsed.query).get("v", [])
            video_id = values[0] if values else None
        elif len(parts) >= 2 and parts[0] in {"shorts", "embed"}:
            video_id = parts[1]
    return video_id if video_id and YOUTUBE_ID_RE.fullmatch(video_id) else None


def is_youtube_url(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    candidate = value.strip()
    if "://" not in candidate:
        candidate = "https://" + candidate
    host = (urlparse(candidate).hostname or "").casefold().rstrip(".")
    return host in {
        "youtube.com", "www.youtube.com", "m.youtube.com",
        "youtu.be", "www.youtu.be", "youtube-nocookie.com",
        "www.youtube-nocookie.com",
    }


def _normalized_words(value: str) -> set[str]:
    return {
        word for word in WORD_RE.findall(value.casefold())
        if word not in TITLE_STOP_WORDS and len(word) > 1
    }


def titles_agree(expected: str, observed: str) -> bool:
    """Mirror the offline preflight's conservative title-overlap rule."""
    expected_flat = " ".join(WORD_RE.findall(expected.casefold()))
    observed_flat = " ".join(WORD_RE.findall(observed.casefold()))
    if expected_flat and f" {expected_flat} " in f" {observed_flat} ":
        return True
    expected_words = _normalized_words(expected)
    observed_words = _normalized_words(observed)
    if not expected_words or not observed_words:
        return False
    overlap = len(expected_words & observed_words)
    minimum = 1 if len(expected_words) == 1 else max(
        2, (len(expected_words) + 1) // 2)
    return overlap >= minimum


def expected_duration_seconds(talk: dict[str, Any]) -> float | None:
    candidates = [
        talk.get("duration_seconds"),
        talk.get("video_duration_seconds"),
        talk.get("talk_duration_seconds"),
    ]
    structured = talk.get("structured_data")
    if isinstance(structured, dict):
        candidates.extend([
            structured.get("video_duration_seconds"),
            structured.get("recording_duration_seconds"),
            structured.get("duration_seconds"),
        ])
    for value in candidates:
        if (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(value)
            and value > 0
        ):
            return float(value)
    return None


def parse_catalog_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def normalize_captured_at(value: str | datetime | None = None) -> str:
    """Return a second-precision UTC timestamp; reject timezone-free evidence."""
    if value is None:
        parsed = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        raw = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise ValueError("captured_at must be an ISO-8601 timestamp") from exc
    else:
        raise ValueError("captured_at must be an ISO-8601 timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("captured_at must include a timezone")
    normalized = parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    return normalized.replace("+00:00", "Z")


def fetch_youtube_metadata(
    video_id: str,
    runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    """Fetch one video's metadata through the yt-dlp CLI without downloading it."""
    if not YOUTUBE_ID_RE.fullmatch(video_id):
        raise MetadataFetchError(f"invalid YouTube ID: {video_id!r}")
    command = [
        "yt-dlp", "--ignore-config", "--no-playlist", "--skip-download",
        "--dump-single-json", "--no-warnings",
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    try:
        completed = runner(
            command, capture_output=True, text=True, check=False,
            timeout=YT_DLP_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MetadataFetchError(f"cannot run yt-dlp: {exc}") from exc
    if completed.returncode != 0:
        detail = _nonempty(completed.stderr) or "yt-dlp exited non-zero"
        raise MetadataFetchError(detail.splitlines()[-1][:500])
    try:
        metadata = json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise MetadataFetchError("yt-dlp did not return valid JSON") from exc
    if not isinstance(metadata, dict):
        raise MetadataFetchError("yt-dlp metadata must be a JSON object")
    return metadata


def _provider_date(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if re.fullmatch(r"\d{8}", raw):
        raw = f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return None
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        return None


def _positive_number(value: Any) -> int | float | None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        return None
    numeric = float(value)
    return int(numeric) if numeric.is_integer() else numeric


def provider_evidence(
    requested_id: str,
    metadata: dict[str, Any],
    captured_at: str,
) -> tuple[dict[str, Any], list[str]]:
    """Select stable provider fields and return validation fault codes."""
    provider_id = _nonempty(metadata.get("id"))
    webpage_url = _nonempty(metadata.get("webpage_url"))
    webpage_id = parse_youtube_id(webpage_url)
    faults: list[str] = []
    if provider_id != requested_id:
        faults.append("provider_video_id_mismatch")
    if webpage_url is not None and webpage_id != requested_id:
        faults.append("provider_webpage_identity_mismatch")

    evidence = {
        "schema_version": SOURCE_IDENTITY_SCHEMA_VERSION,
        "provider": "youtube",
        "video_id": provider_id,
        "title": _nonempty(metadata.get("title")),
        "uploader": _nonempty(metadata.get("uploader")),
        "uploader_id": _nonempty(metadata.get("uploader_id")),
        "upload_date": _provider_date(metadata.get("upload_date")),
        "duration_seconds": _positive_number(metadata.get("duration")),
        "webpage_url": webpage_url,
        "webpage_video_id": webpage_id,
        "captured_at": captured_at,
    }
    missing = [
        field for field in (
            "title", "uploader", "upload_date", "duration_seconds", "webpage_url",
        )
        if evidence[field] is None
    ]
    if missing:
        faults.append("provider_metadata_incomplete")
    return evidence, faults


def proposed_source_identity(evidence: dict[str, Any]) -> dict[str, Any]:
    """Return provider facts only; uploader and upload date are not human identity."""
    return {
        key: value for key, value in evidence.items()
        if value is not None
    }


def _finding(
    code: str,
    video_id: str | None,
    talk_indexes: list[int],
    filenames: list[str],
    message: str,
    evidence: Any,
    review_priority: str = "medium",
) -> dict[str, Any]:
    return {
        "code": code,
        "review_priority": review_priority,
        "video_id": video_id,
        "talk_indexes": sorted(talk_indexes),
        "filenames": sorted(filenames),
        "message": message,
        "evidence": evidence,
    }


def _filename(talk: dict[str, Any], index: int) -> str:
    return _nonempty(talk.get("filename")) or f"talk[{index}]"


def _stored_identity_differences(
    talk: dict[str, Any], proposal: dict[str, Any],
) -> list[dict[str, Any]]:
    stored = talk.get("source_identity")
    if not isinstance(stored, dict):
        return []
    fields = (
        "video_id", "title", "uploader", "uploader_id", "upload_date",
        "duration_seconds", "webpage_url",
    )
    differences = []
    for field in fields:
        if field not in stored or field not in proposal:
            continue
        if stored[field] != proposal[field]:
            differences.append({
                "field": field,
                "stored": stored[field],
                "fetched": proposal[field],
            })
    return differences


def _non_delivery_signals(
    talk: dict[str, Any], evidence: dict[str, Any], title_agrees: bool | None,
) -> list[str]:
    provider_title = evidence.get("title")
    duration = evidence.get("duration_seconds")
    expected = expected_duration_seconds(talk)
    markers = sorted(
        _normalized_words(provider_title or "") & CLIP_MARKERS)
    signals: list[str] = []
    if markers:
        signals.append("provider_title_has_clip_marker:" + ",".join(markers))
    if isinstance(duration, (int, float)) and expected is not None:
        if expected >= 600 and duration / expected < 0.55:
            signals.append("provider_duration_under_55_percent_of_catalog")
    if isinstance(duration, (int, float)) and duration < 120:
        catalog_words = _normalized_words(_nonempty(talk.get("title")) or "")
        if "lightning" not in catalog_words:
            signals.append("provider_duration_under_two_minutes")
    if title_agrees is False and isinstance(duration, (int, float)) and duration < 600:
        signals.append("title_mismatch_plus_sub_ten_minute_duration")

    strong = any(
        signal.startswith("provider_duration_under_")
        or signal == "title_mismatch_plus_sub_ten_minute_duration"
        for signal in signals
    )
    marker_with_support = bool(markers) and (
        title_agrees is False
        or (isinstance(duration, (int, float)) and duration < 900)
    )
    return signals if strong or marker_with_support else []


def _talks_collide(talks: list[dict[str, Any]]) -> bool:
    for left_index, left in enumerate(talks):
        for right in talks[left_index + 1:]:
            left_title = _nonempty(left.get("title"))
            right_title = _nonempty(right.get("title"))
            if left_title and right_title and not titles_agree(left_title, right_title):
                return True
            left_date = _nonempty(left.get("date"))
            right_date = _nonempty(right.get("date"))
            if left_date and right_date and left_date != right_date:
                return True
    return False


def audit_database(
    database: Any,
    *,
    database_path: str | Path,
    metadata_fetcher: Callable[[str], dict[str, Any]],
    captured_at: str | datetime | None = None,
) -> dict[str, Any]:
    """Audit one loaded database. The input object is never mutated."""
    captured = normalize_captured_at(captured_at)
    database_name = str(Path(database_path).expanduser().resolve(strict=False))
    findings: list[dict[str, Any]] = []
    talk_audits: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    groups: defaultdict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)

    if not isinstance(database, dict):
        findings.append(_finding(
            "database_shape_invalid", None, [], [],
            "tracking database must be a JSON object",
            {"actual": type(database).__name__}, "high",
        ))
        talks: list[Any] = []
    else:
        raw_talks = database.get("talks")
        if not isinstance(raw_talks, list):
            findings.append(_finding(
                "talks_shape_invalid", None, [], [],
                "tracking database talks must be an array",
                {"actual": type(raw_talks).__name__}, "high",
            ))
            talks = []
        else:
            talks = raw_talks

    active_count = 0
    audits_by_index: dict[int, dict[str, Any]] = {}
    for index, talk in enumerate(talks):
        if not isinstance(talk, dict):
            findings.append(_finding(
                "talk_shape_invalid", None, [index], [f"talk[{index}]"],
                "active source audit skipped a non-object talk record",
                {"actual": type(talk).__name__}, "high",
            ))
            continue
        video_url = _nonempty(talk.get("video_url"))
        if video_url is None:
            continue
        active_count += 1
        filename = _filename(talk, index)
        video_id = parse_youtube_id(video_url)
        audit = {
            "talk_index": index,
            "filename": filename,
            "active_video_url": video_url,
            "youtube_id": video_id,
            "stored_youtube_id": talk.get("youtube_id"),
            "catalog": {
                "title": talk.get("title"),
                "date": talk.get("date"),
                "conference": talk.get("conference"),
                "duration_seconds": expected_duration_seconds(talk),
            },
            "comparison": None,
            "proposed_evidence": None,
        }
        talk_audits.append(audit)
        audits_by_index[index] = audit
        if video_id is None:
            code = (
                "active_youtube_url_invalid" if is_youtube_url(video_url)
                else "active_video_provider_unsupported"
            )
            findings.append(_finding(
                code, None, [index], [filename],
                "active video source cannot be audited as a YouTube identity",
                {"active_video_url": video_url},
                "high" if code in ERROR_CODES else "medium",
            ))
            continue
        stored_id = _nonempty(talk.get("youtube_id"))
        if stored_id is not None and stored_id != video_id:
            findings.append(_finding(
                "stored_youtube_id_mismatch", video_id, [index], [filename],
                "active video URL and stored youtube_id disagree",
                {"url_video_id": video_id, "stored_youtube_id": stored_id}, "high",
            ))
        groups[video_id].append((index, talk))

    evidence_by_id: dict[str, dict[str, Any]] = {}
    for video_id in sorted(groups):
        members = groups[video_id]
        indexes = [index for index, _ in members]
        filenames = [_filename(talk, index) for index, talk in members]
        source = {
            "video_id": video_id,
            "talk_indexes": sorted(indexes),
            "filenames": sorted(filenames),
            "fetch_status": "ok",
            "provider_evidence": None,
            "error": None,
        }
        try:
            raw_metadata = metadata_fetcher(video_id)
            if not isinstance(raw_metadata, dict):
                raise MetadataFetchError("metadata fetcher returned a non-object")
        except (MetadataFetchError, OSError, RuntimeError) as exc:
            source["fetch_status"] = "error"
            source["error"] = str(exc)
            findings.append(_finding(
                "metadata_fetch_failed", video_id, indexes, filenames,
                "yt-dlp metadata capture failed",
                {"error": str(exc)}, "high",
            ))
            sources.append(source)
            continue

        evidence, faults = provider_evidence(video_id, raw_metadata, captured)
        source["provider_evidence"] = evidence
        critical = {
            "provider_video_id_mismatch", "provider_webpage_identity_mismatch",
        }.intersection(faults)
        for code in sorted(set(faults)):
            missing = [
                field for field in (
                    "title", "uploader", "upload_date", "duration_seconds",
                    "webpage_url",
                )
                if evidence[field] is None
            ]
            findings.append(_finding(
                code, video_id, indexes, filenames,
                (
                    "provider metadata is missing stable audit fields"
                    if code == "provider_metadata_incomplete"
                    else "provider metadata does not confirm the requested identity"
                ),
                {
                    "requested_video_id": video_id,
                    "provider_video_id": evidence["video_id"],
                    "webpage_video_id": evidence["webpage_video_id"],
                    "missing_fields": missing,
                },
                "high" if code in ERROR_CODES else "medium",
            ))
        if critical:
            source["fetch_status"] = "invalid"
            sources.append(source)
            continue

        proposal = proposed_source_identity(evidence)
        evidence_by_id[video_id] = proposal
        sources.append(source)

    for video_id in sorted(groups):
        proposal = evidence_by_id.get(video_id)
        for index, talk in groups[video_id]:
            audit = audits_by_index[index]
            if proposal is None:
                continue
            provider_title = _nonempty(proposal.get("title"))
            catalog_title = _nonempty(talk.get("title"))
            title_agrees = (
                titles_agree(catalog_title, provider_title)
                if catalog_title and provider_title else None
            )
            expected_duration = expected_duration_seconds(talk)
            provider_duration = proposal.get("duration_seconds")
            duration_within_tolerance: bool | None = None
            if expected_duration is not None and isinstance(
                    provider_duration, (int, float)):
                tolerance = max(60.0, expected_duration * 0.05)
                duration_within_tolerance = (
                    abs(float(provider_duration) - expected_duration) <= tolerance)
            catalog_date = parse_catalog_date(talk.get("date"))
            upload_date = _provider_date(proposal.get("upload_date"))
            upload_predates = (
                date.fromisoformat(upload_date) < catalog_date
                if catalog_date is not None and upload_date is not None else None
            )
            differences = _stored_identity_differences(talk, proposal)
            audit["comparison"] = {
                "catalog_title_agrees": title_agrees,
                "duration_within_tolerance": duration_within_tolerance,
                "upload_predates_catalog_date": upload_predates,
                "stored_source_identity_differences": differences,
            }
            audit["proposed_evidence"] = {
                "source_identity": deepcopy(proposal),
            }
            filename = _filename(talk, index)
            if title_agrees is False:
                findings.append(_finding(
                    "provider_title_mismatch", video_id, [index], [filename],
                    "provider title does not materially overlap the catalog title",
                    {"catalog_title": catalog_title, "provider_title": provider_title},
                ))
            if duration_within_tolerance is False:
                findings.append(_finding(
                    "provider_duration_mismatch", video_id, [index], [filename],
                    "provider duration differs from the catalog duration beyond tolerance",
                    {
                        "catalog_duration_seconds": expected_duration,
                        "provider_duration_seconds": provider_duration,
                    },
                ))
            if (
                upload_predates is True
                and catalog_date is not None
                and upload_date is not None
            ):
                findings.append(_finding(
                    "provider_upload_predates_catalog", video_id, [index], [filename],
                    "provider upload date predates the cataloged delivery date",
                    {
                        "catalog_date": catalog_date.isoformat(),
                        "provider_upload_date": upload_date,
                    },
                ))
            if differences:
                findings.append(_finding(
                    "stored_source_identity_differs", video_id, [index], [filename],
                    "fresh provider facts differ from stored source identity evidence",
                    differences,
                ))
            signals = _non_delivery_signals(talk, proposal, title_agrees)
            if signals:
                findings.append(_finding(
                    "likely_non_delivery_clip", video_id, [index], [filename],
                    "provider title/duration suggest this source may not be a full delivery",
                    {
                        "signals": signals,
                        "catalog_title": catalog_title,
                        "provider_title": provider_title,
                        "catalog_duration_seconds": expected_duration,
                        "provider_duration_seconds": provider_duration,
                    },
                    "high",
                ))

    for video_id in sorted(groups):
        members = groups[video_id]
        member_talks = [talk for _, talk in members]
        if len(member_talks) < 2 or not _talks_collide(member_talks):
            continue
        indexes = [index for index, _ in members]
        filenames = [_filename(talk, index) for index, talk in members]
        collision_records: list[dict[str, Any]] = [
            {
                "filename": _filename(talk, index),
                "title": talk.get("title"),
                "date": talk.get("date"),
                "conference": talk.get("conference"),
                "source_relation": talk.get("source_relation"),
            }
            for index, talk in members
        ]
        collision_records.sort(key=lambda item: str(item["filename"]))
        findings.append(_finding(
            "same_id_cross_talk_collision", video_id, indexes, filenames,
            "one active YouTube identity is attached to distinct catalog talks/deliveries",
            {
                "catalog_records": collision_records,
                "provider_title": evidence_by_id.get(video_id, {}).get("title"),
            },
            "high",
        ))

    priority_order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda item: (
        priority_order.get(item["review_priority"], 9),
        item["code"], item["video_id"] or "", item["filenames"],
    ))
    talk_audits.sort(key=lambda item: (item["talk_index"], item["filename"]))
    sources.sort(key=lambda item: item["video_id"])
    by_code = Counter(item["code"] for item in findings)
    fetch_errors = sum(1 for item in sources if item["fetch_status"] != "ok")
    complete = not any(item["code"] in ERROR_CODES for item in findings)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "captured_at": captured,
        "database": database_name,
        "complete": complete,
        "review_required": bool(findings),
        "active_talk_count": active_count,
        "unique_youtube_id_count": len(groups),
        "metadata_fetch_count": len(groups),
        "metadata_fetch_error_count": fetch_errors,
        "summary": {
            "finding_count": len(findings),
            "by_code": {key: by_code[key] for key in sorted(by_code)},
        },
        "sources": sources,
        "talks": talk_audits,
        "findings": findings,
    }


def resolve_input(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_dir() or (not path.exists() and path.suffix.casefold() != ".json"):
        return path / "tracking-database.json"
    return path


def audit_path(
    value: str | Path,
    *,
    metadata_fetcher: Callable[[str], dict[str, Any]] = fetch_youtube_metadata,
    captured_at: str | datetime | None = None,
) -> dict[str, Any]:
    """Read and audit a vault/database path without writing any file."""
    database_path = resolve_input(value).resolve(strict=False)
    try:
        database = json.loads(database_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        report = audit_database(
            {}, database_path=database_path,
            metadata_fetcher=metadata_fetcher, captured_at=captured_at,
        )
        report["complete"] = False
        report["review_required"] = True
        report["summary"] = {
            "finding_count": 1,
            "by_code": {"database_unreadable": 1},
        }
        report["findings"] = [_finding(
            "database_unreadable", None, [], [],
            "tracking database could not be read as UTF-8 JSON",
            {"error": str(exc)}, "high",
        )]
        return report
    return audit_database(
        database, database_path=database_path,
        metadata_fetcher=metadata_fetcher, captured_at=captured_at,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "vault_or_database",
        help="vault root directory or tracking-database JSON path",
    )
    parser.add_argument(
        "--captured-at",
        help="timezone-aware ISO timestamp for reproducible capture output",
    )
    args = parser.parse_args(argv)
    try:
        report = audit_path(
            args.vault_or_database, captured_at=args.captured_at,
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["complete"]:
        return 0
    print(
        "source identity audit incomplete; review report findings, correct "
        "the active source or retry yt-dlp, then rerun",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
