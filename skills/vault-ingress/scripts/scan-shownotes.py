#!/usr/bin/env python3
"""Scan a configured local shownotes collection into tracking-DB proposals.

The default mode is read-only. ``--apply`` atomically adds complete new talks and
fills empty fields on exact-filename matches. Conflicts, incomplete metadata,
case-folded filename collisions, and rejected source identities remain explicit
review proposals. Remote or disabled shownotes sources produce a structured no-op.
"""

from __future__ import annotations

import argparse
import copy
import importlib
import json
import os
import re
import stat
import sys
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import urlparse

import yaml

from catalog_io import load_catalog_yaml
from ingress_contract import (
    GOOGLE_DRIVE_ID_RE,
    TALK_SCHEMA_VERSION,
    YOUTUBE_ID_RE,
    is_youtube_url,
    parse_google_drive_id,
    parse_youtube_id,
    validate_talk_record_schemas,
)
from source_identity_matching import shownotes_titles_agree
from tracking_database import (
    TrackingDatabaseError,
    assess_tracking_database,
    require_current_tracking_database,
)
from tracking_database_io import (
    TrackingDatabaseConflictError,
    TrackingDatabaseIOError,
    TrackingDatabaseSnapshot,
    decode_json_object,
    snapshot_tracking_database,
    unchanged_write_result,
    write_json_object,
)

try:  # Python 3.11+.
    tomllib = importlib.import_module("tomllib")
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10 only
    try:
        tomllib = importlib.import_module("tomli")
    except ModuleNotFoundError:
        tomllib = None


REPORT_SCHEMA_VERSION = 2
LOCAL_SOURCE_TYPES = frozenset(
    {"local_jekyll", "local_hugo", "local_eleventy", "local_astro"}
)
NONLOCAL_SOURCE_TYPES = frozenset({"remote_url", "none"})
REQUIRED_METADATA = ("title", "conference", "date")
TRACKED_FIELDS = (
    "title",
    "conference",
    "date",
    "video_url",
    "slides_url",
    "youtube_id",
    "google_drive_id",
)
METADATA_ALIASES = {
    "title": ("title",),
    "conference": ("conference", "event", "venue"),
    "date": ("date",),
    "video_url": ("video_url", "video", "recording_url", "recording", "youtube"),
    "slides_url": ("slides_url", "slides", "deck_url", "deck"),
    "youtube_id": ("youtube_id",),
    "google_drive_id": ("google_drive_id", "drive_id"),
}
BODY_LABEL_FIELDS = {
    "conference": "conference",
    "event": "conference",
    "venue": "conference",
    "date": "date",
    "video": "video_url",
    "recording": "video_url",
    "slides": "slides_url",
    "deck": "slides_url",
}
LABEL_RE = re.compile(
    r"^\s*(?:\*\*)?(?P<label>conference|event|venue|date|video|recording|slides|deck)"
    r"\s*:(?:\*\*)?\s*(?P<value>.*?)\s*$",
    re.IGNORECASE,
)
H1_RE = re.compile(r"^#\s+(?P<title>\S.*)$")
MARKDOWN_URL_RE = re.compile(r"\[[^\]]*\]\((?P<url>https?://[^)\s]+)\)")
RAW_URL_RE = re.compile(r"https?://[^\s<>]+")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
FileGeneration = tuple[int, int, int, int, int]


class ShownotesScanError(ValueError):
    """Input or state prevents a deterministic shownotes scan."""


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ShownotesScanError(
            f"invalid arguments: {message}; run scan-shownotes.py --help and retry"
        )


@dataclass(frozen=True)
class ShownotesLocation:
    enabled: bool
    source_type: str
    config_origin: str
    root: Path | None
    talks_subdir: str | None
    talks_directory: Path | None


def _nonempty(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _normalized_filename(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def _normalized_conference_for_comparison(value: str) -> str:
    """Normalize conference Unicode and case only; whitespace stays significant."""
    return unicodedata.normalize("NFC", value).casefold()


def _catalog_values_agree(
    field: str,
    left: object,
    right: object,
    *,
    conference: object,
    talk_date: object,
) -> bool:
    """Return whether stored and shownotes metadata agree without rewriting."""
    if not isinstance(left, str) or not isinstance(right, str):
        return False
    if field == "title":
        return shownotes_titles_agree(
            left,
            right,
            conference=conference,
            talk_date=talk_date,
        )
    if field == "conference":
        return _normalized_conference_for_comparison(
            left
        ) == _normalized_conference_for_comparison(right)
    return False


def _reject_symlink_components(path: Path, *, subject: str) -> None:
    if not path.is_absolute():
        raise ShownotesScanError(f"{subject} path {path} must be absolute")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError as exc:
            raise ShownotesScanError(
                f"{subject} path component {current} is missing; repair config and retry"
            ) from exc
        except OSError as exc:
            raise ShownotesScanError(
                f"cannot inspect {subject} path component {current}: {exc}; "
                "repair access and retry"
            ) from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise ShownotesScanError(
                f"{subject} path component {current} is a symbolic link; configure "
                "the canonical non-symlink path and retry"
            )


def _file_generation(metadata: os.stat_result) -> FileGeneration:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _load_database(
    path: Path,
) -> tuple[dict[str, Any], TrackingDatabaseSnapshot]:
    try:
        snapshot = snapshot_tracking_database(path)
        payload = decode_json_object(snapshot)
    except TrackingDatabaseIOError as exc:
        raise ShownotesScanError(str(exc)) from exc
    try:
        assessment = assess_tracking_database(payload)
    except TrackingDatabaseError as exc:
        raise ShownotesScanError(str(exc)) from exc
    if not assessment.usable:
        raise ShownotesScanError(
            "tracking database is not usable by this reader: "
            + ", ".join(assessment.reason_codes)
        )
    try:
        validate_talk_record_schemas(payload.get("talks"))
    except ValueError as exc:
        raise ShownotesScanError(
            f"tracking database talk records are invalid: {exc}; repair them and retry"
        ) from exc
    if not isinstance(payload.get("config"), dict):
        raise ShownotesScanError(
            "tracking database config must be a JSON object; run vault-ingress Step 1"
        )
    return payload, snapshot


def _safe_local_location(
    source_type: str,
    root_value: object,
    subdir_value: object,
    *,
    config_origin: str,
) -> ShownotesLocation:
    root_text = _nonempty(root_value)
    subdir_text = _nonempty(subdir_value)
    if root_text is None or subdir_text is None:
        raise ShownotesScanError(
            "local shownotes config requires non-empty path_or_url and talks_subdir; "
            "run vault-ingress Step 1 to complete it"
        )
    root_candidate = Path(root_text).expanduser()
    if not root_candidate.is_absolute():
        raise ShownotesScanError(
            f"shownotes root {root_text!r} is relative; configure an absolute path"
        )
    subdir = Path(subdir_text)
    if subdir.is_absolute() or any(part in {"", ".", ".."} for part in subdir.parts):
        raise ShownotesScanError(
            f"shownotes talks_subdir {subdir_text!r} must be a safe relative path"
        )
    talks_candidate = root_candidate / subdir
    _reject_symlink_components(root_candidate, subject="shownotes root")
    _reject_symlink_components(talks_candidate, subject="shownotes talks directory")
    try:
        root = root_candidate.resolve(strict=True)
        talks_directory = talks_candidate.resolve(strict=True)
        talks_directory.relative_to(root)
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise ShownotesScanError(
            "cannot resolve the configured shownotes talks directory inside its root: "
            f"{exc}; repair path_or_url/talks_subdir and retry"
        ) from exc
    if not root.is_dir() or not talks_directory.is_dir():
        raise ShownotesScanError(
            f"shownotes talks path {talks_directory} is not a directory; repair config"
        )
    return ShownotesLocation(
        enabled=True,
        source_type=source_type,
        config_origin=config_origin,
        root=root,
        talks_subdir=subdir.as_posix(),
        talks_directory=talks_directory,
    )


def resolve_shownotes_location(config: dict[str, Any]) -> ShownotesLocation:
    """Resolve nested shownotes config or its documented legacy path."""
    if config.get("shownotes") is not None:
        shownotes = config.get("shownotes")
        if not isinstance(shownotes, dict):
            raise ShownotesScanError(
                "config.shownotes must be an object; run vault-ingress Step 1 to repair it"
            )
        enabled = shownotes.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ShownotesScanError(
                "config.shownotes.enabled must be a boolean; correct it and retry"
            )
        source = shownotes.get("source")
        if not isinstance(source, dict):
            raise ShownotesScanError(
                "config.shownotes.source must be an object; run vault-ingress Step 1"
            )
        source_type = _nonempty(source.get("type"))
        if source_type is None:
            raise ShownotesScanError(
                "config.shownotes.source.type is missing; run vault-ingress Step 1"
            )
        if not enabled:
            return ShownotesLocation(False, source_type, "shownotes", None, None, None)
        if source_type in NONLOCAL_SOURCE_TYPES:
            return ShownotesLocation(True, source_type, "shownotes", None, None, None)
        if source_type not in LOCAL_SOURCE_TYPES:
            raise ShownotesScanError(
                f"unsupported shownotes source type {source_type!r}; choose one of "
                f"{sorted(LOCAL_SOURCE_TYPES | NONLOCAL_SOURCE_TYPES)}"
            )
        return _safe_local_location(
            source_type,
            source.get("path_or_url"),
            source.get("talks_subdir"),
            config_origin="shownotes",
        )

    legacy = _nonempty(config.get("talks_source_dir"))
    if legacy is None:
        raise ShownotesScanError(
            "shownotes config is missing; run vault-ingress Step 1 before scanning"
        )
    directory = Path(legacy).expanduser()
    if not directory.is_absolute():
        raise ShownotesScanError(
            f"legacy talks_source_dir {legacy!r} is relative; configure an absolute path"
        )
    return _safe_local_location(
        "legacy_local",
        str(directory.parent),
        directory.name,
        config_origin="talks_source_dir",
    )


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str, list[dict[str, str]]]:
    lines = text.splitlines()
    if not lines:
        return {}, "", []
    marker = lines[0].strip()
    if marker in {"---", "+++"}:
        try:
            end = next(
                index
                for index in range(1, len(lines))
                if lines[index].strip() == marker
            )
        except StopIteration:
            return (
                {},
                text,
                [
                    {
                        "code": "frontmatter_unterminated",
                        "message": f"{marker} frontmatter has no closing delimiter; repair the file",
                    }
                ],
            )
        frontmatter_text = "\n".join(lines[1:end])
        body = "\n".join(lines[end + 1 :])
        try:
            if marker == "---":
                parsed = (
                    load_catalog_yaml(frontmatter_text)
                    if frontmatter_text.strip()
                    else {}
                )
            elif tomllib is not None:
                parsed = tomllib.loads(frontmatter_text)
            else:
                return (
                    {},
                    body,
                    [
                        {
                            "code": "toml_parser_unavailable",
                            "message": (
                                "TOML frontmatter needs Python 3.11+ or tomli; configure that "
                                "runtime and rescan"
                            ),
                        }
                    ],
                )
        except (ValueError, yaml.YAMLError) as exc:
            return (
                {},
                body,
                [
                    {
                        "code": "frontmatter_invalid",
                        "message": f"frontmatter is invalid: {exc}; repair the file and rescan",
                    }
                ],
            )
        if not isinstance(parsed, dict):
            return (
                {},
                body,
                [
                    {
                        "code": "frontmatter_not_object",
                        "message": "frontmatter must be an object; repair the file and rescan",
                    }
                ],
            )
        return parsed, body, []

    if text.lstrip().startswith("{"):
        leading = len(text) - len(text.lstrip())
        try:
            parsed, end = json.JSONDecoder().raw_decode(text, leading)
        except json.JSONDecodeError as exc:
            return (
                {},
                text,
                [
                    {
                        "code": "frontmatter_invalid_json",
                        "message": f"JSON frontmatter is invalid: {exc}; repair the file and rescan",
                    }
                ],
            )
        if not isinstance(parsed, dict):
            return (
                {},
                text[end:],
                [
                    {
                        "code": "frontmatter_not_object",
                        "message": "JSON frontmatter must be an object; repair the file and rescan",
                    }
                ],
            )
        return parsed, text[end:].lstrip("\r\n"), []
    return {}, text, []


def _metadata_values(metadata: dict[str, Any], field: str) -> list[object]:
    containers = [metadata]
    params = metadata.get("params")
    if isinstance(params, dict):
        containers.append(params)
    values: list[object] = []
    for container in containers:
        for alias in METADATA_ALIASES[field]:
            if alias in container and container[alias] is not None:
                values.append(container[alias])
    return values


def _extract_url(value: object) -> str | None:
    text = _nonempty(value)
    if text is None:
        return None
    markdown = MARKDOWN_URL_RE.search(text)
    if markdown:
        return markdown.group("url")
    raw = RAW_URL_RE.search(text)
    if raw:
        return raw.group(0).rstrip(".,;]")
    return None


def _normalize_date(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = _nonempty(value)
    if text is None or not DATE_RE.fullmatch(text):
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def _url_identity(field: str, value: str) -> tuple[str, str]:
    parsed_id = (
        parse_youtube_id(value)
        if field == "video_url"
        else parse_google_drive_id(value)
    )
    return (field, parsed_id) if parsed_id is not None else (field, value)


def _choose_value(
    filename: str,
    field: str,
    values: list[object],
    issues: list[dict[str, str]],
) -> object | None:
    normalized: list[object] = []
    for value in values:
        if field in {"video_url", "slides_url"}:
            candidate = _extract_url(value)
        elif field == "date":
            candidate = _normalize_date(value)
        else:
            candidate = _nonempty(value)
        if candidate is None:
            issues.append(
                {
                    "code": f"{field}_invalid",
                    "field": field,
                    "message": f"{filename} has an invalid {field}; correct it and rescan",
                }
            )
            continue
        if candidate not in normalized:
            normalized.append(candidate)
    if not normalized:
        return None
    if len(normalized) > 1:
        if field in {"video_url", "slides_url"}:
            identities = {_url_identity(field, str(value)) for value in normalized}
            if len(identities) == 1:
                return normalized[0]
        issues.append(
            {
                "code": f"{field}_conflict",
                "field": field,
                "message": f"{filename} declares conflicting {field} values; choose one",
            }
        )
    return normalized[0]


def _read_markdown_text(path: Path) -> str:
    _reject_symlink_components(path.parent, subject="shownotes talks directory")
    try:
        path_metadata = path.lstat()
    except OSError as exc:
        raise ShownotesScanError(
            f"cannot inspect shownotes file {path.name}: {exc}; repair it and rescan"
        ) from exc
    if stat.S_ISLNK(path_metadata.st_mode):
        raise ShownotesScanError(
            f"{path.name} must be a regular non-symlink Markdown file"
        )
    if not stat.S_ISREG(path_metadata.st_mode):
        raise ShownotesScanError(f"{path.name} must be a regular Markdown file")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            opened_metadata = os.fstat(handle.fileno())
            if not stat.S_ISREG(opened_metadata.st_mode) or _file_generation(
                opened_metadata
            ) != _file_generation(path_metadata):
                raise ShownotesScanError(
                    f"{path.name} changed while it was opened; repair it and rescan"
                )
            raw = handle.read()
            read_metadata = os.fstat(handle.fileno())
    except OSError as exc:
        raise ShownotesScanError(
            f"cannot read {path.name} without following symlinks: {exc}; "
            "repair it and rescan"
        ) from exc
    if _file_generation(read_metadata) != _file_generation(opened_metadata):
        raise ShownotesScanError(
            f"{path.name} changed while it was read; repair it and rescan"
        )
    try:
        final_metadata = path.lstat()
    except OSError as exc:
        raise ShownotesScanError(
            f"cannot recheck {path.name}: {exc}; repair it and rescan"
        ) from exc
    if stat.S_ISLNK(final_metadata.st_mode) or _file_generation(
        final_metadata
    ) != _file_generation(read_metadata):
        raise ShownotesScanError(
            f"{path.name} path changed while it was read; repair it and rescan"
        )
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ShownotesScanError(
            f"cannot read {path.name} as UTF-8: {exc}; repair it and rescan"
        ) from exc


def parse_shownotes_file(path: Path) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Return a normalized talk proposal and review issues for one Markdown file."""
    issues: list[dict[str, str]] = []
    try:
        text = _read_markdown_text(path)
    except ShownotesScanError as exc:
        return {"filename": path.name}, [
            {
                "code": "shownotes_file_unreadable",
                "message": str(exc),
            }
        ]
    metadata, body, frontmatter_issues = _parse_frontmatter(text)
    issues.extend(frontmatter_issues)

    body_values: dict[str, list[object]] = {field: [] for field in METADATA_ALIASES}
    h1_titles: list[str] = []
    for line in body.splitlines():
        h1 = H1_RE.match(line)
        if h1:
            h1_titles.append(h1.group("title").strip())
        label = LABEL_RE.match(line)
        if label:
            field = BODY_LABEL_FIELDS[label.group("label").casefold()]
            body_values[field].append(label.group("value"))

    proposal: dict[str, Any] = {"filename": path.name}
    for field in ("title", "conference", "date", "video_url", "slides_url"):
        values = _metadata_values(metadata, field)
        if field == "title":
            values.extend(h1_titles)
        else:
            values.extend(body_values[field])
        selected = _choose_value(path.name, field, values, issues)
        if selected is not None:
            proposal[field] = selected

    video_url = proposal.get("video_url")
    if isinstance(video_url, str):
        parsed = urlparse(video_url)
        if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
            issues.append(
                {
                    "code": "video_url_invalid",
                    "field": "video_url",
                    "message": f"{path.name} video_url must be HTTP(S); correct it",
                }
            )
        elif is_youtube_url(video_url):
            youtube_id = parse_youtube_id(video_url)
            if youtube_id is None:
                issues.append(
                    {
                        "code": "youtube_url_invalid",
                        "field": "video_url",
                        "message": f"{path.name} has an unsupported YouTube URL; correct it",
                    }
                )
            else:
                proposal["youtube_id"] = youtube_id

    slides_url = proposal.get("slides_url")
    if isinstance(slides_url, str):
        parsed = urlparse(slides_url)
        if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
            issues.append(
                {
                    "code": "slides_url_invalid",
                    "field": "slides_url",
                    "message": f"{path.name} slides_url must be HTTP(S); correct it",
                }
            )
        elif (parsed.hostname or "").casefold().rstrip(".") in {
            "drive.google.com",
            "docs.google.com",
        }:
            drive_id = parse_google_drive_id(slides_url)
            if drive_id is None:
                issues.append(
                    {
                        "code": "drive_url_invalid",
                        "field": "slides_url",
                        "message": f"{path.name} has an unsupported Google Drive URL; correct it",
                    }
                )
            else:
                proposal["google_drive_id"] = drive_id

    for id_field, regex in (
        ("youtube_id", YOUTUBE_ID_RE),
        ("google_drive_id", GOOGLE_DRIVE_ID_RE),
    ):
        declared_values = _metadata_values(metadata, id_field)
        if not declared_values:
            continue
        declared = _choose_value(path.name, id_field, declared_values, issues)
        if not isinstance(declared, str) or regex.fullmatch(declared) is None:
            issues.append(
                {
                    "code": f"{id_field}_invalid",
                    "field": id_field,
                    "message": f"{path.name} has an invalid {id_field}; correct it",
                }
            )
            continue
        derived = proposal.get(id_field)
        if derived is not None and derived != declared:
            issues.append(
                {
                    "code": f"{id_field}_mismatch",
                    "field": id_field,
                    "message": (
                        f"{path.name} declares {id_field} {declared!r}, but its URL "
                        f"resolves to {derived!r}; choose the correct identity"
                    ),
                }
            )
        elif derived is None:
            proposal[id_field] = declared

    for field in REQUIRED_METADATA:
        if field not in proposal:
            issues.append(
                {
                    "code": f"{field}_missing",
                    "field": field,
                    "message": f"{path.name} is missing {field}; add it before import",
                }
            )
    return proposal, issues


def _same_source(field: str, left: str, right: str) -> bool:
    if left == right:
        return True
    parser = parse_youtube_id if field == "video_url" else parse_google_drive_id
    left_id = parser(left)
    return left_id is not None and parser(right) == left_id


def _rejected_source_issue(
    talk: dict[str, Any], field: str, candidate: str
) -> dict[str, str] | None:
    if "source_rejections" not in talk:
        return None
    rejections = talk.get("source_rejections")
    if not isinstance(rejections, list):
        return {
            "code": "source_rejections_invalid",
            "field": "source_rejections",
            "message": "source_rejections must be an array; repair it before import",
        }
    expected_type = "video" if field == "video_url" else "slides"
    for index, rejection in enumerate(rejections):
        if not isinstance(rejection, dict):
            return {
                "code": "source_rejections_invalid",
                "field": "source_rejections",
                "message": (
                    f"source_rejections[{index}] must be an object; repair it before import"
                ),
            }
        rejected_url = _nonempty(rejection.get("url"))
        if rejection.get("source_type") != expected_type or rejected_url is None:
            continue
        if _same_source(field, candidate, rejected_url):
            return {
                "code": "rejected_source_reappeared",
                "field": field,
                "message": (
                    f"shownotes proposes a known-bad {field}; keep it inactive until "
                    "human review supplies replacement evidence"
                ),
            }
    return None


def _existing_entry(
    talk: dict[str, Any],
    proposal: dict[str, Any],
    parse_issues: list[dict[str, str]],
) -> tuple[str, dict[str, Any], list[dict[str, str]]]:
    issues = list(parse_issues)
    patch: dict[str, Any] = {}
    stored_conference = talk.get("conference")
    stored_date = talk.get("date")
    for field in TRACKED_FIELDS:
        if field not in proposal:
            continue
        candidate = proposal[field]
        if field in {"video_url", "slides_url"}:
            rejection = _rejected_source_issue(talk, field, str(candidate))
            if rejection is not None:
                issues.append(rejection)
                continue
        current = talk.get(field)
        if current is None or current == "":
            patch[field] = candidate
            continue
        if current == candidate:
            continue
        if _catalog_values_agree(
            field,
            current,
            candidate,
            conference=stored_conference,
            talk_date=stored_date,
        ):
            continue
        if (
            field in {"video_url", "slides_url"}
            and isinstance(current, str)
            and _same_source(field, current, str(candidate))
        ):
            continue
        issues.append(
            {
                "code": f"existing_{field}_conflict",
                "field": field,
                "message": (
                    f"tracking DB {field} {current!r} conflicts with shownotes "
                    f"{candidate!r}; choose the authoritative value"
                ),
            }
        )
    if issues:
        return "review_required", {}, issues
    return ("update", patch, []) if patch else ("unchanged", {}, [])


def build_scan_report(
    database_path: Path,
    database: dict[str, Any],
    location: ShownotesLocation,
    *,
    apply_requested: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build a stable report and the candidate post-scan database."""
    talks = database["talks"]
    exact: dict[str, tuple[int, dict[str, Any]]] = {}
    folded: dict[str, list[str]] = {}
    for index, talk in enumerate(talks):
        filename = _nonempty(talk.get("filename"))
        if filename is None:
            raise ShownotesScanError(
                f"talks[{index}].filename is missing; repair it before shownotes scan"
            )
        if filename in exact:
            raise ShownotesScanError(
                f"tracking database repeats filename {filename!r}; deduplicate it first"
            )
        exact[filename] = (index, talk)
        folded.setdefault(_normalized_filename(filename), []).append(filename)
    collisions = {key: names for key, names in folded.items() if len(names) > 1}
    if collisions:
        raise ShownotesScanError(
            f"tracking database has normalized filename collisions {collisions}; "
            "resolve them before scanning"
        )

    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "ok": True,
        "mode": "apply" if apply_requested else "dry-run",
        "database": str(database_path.resolve(strict=False)),
        "shownotes": {
            "enabled": location.enabled,
            "source_type": location.source_type,
            "config_origin": location.config_origin,
            "root": str(location.root) if location.root else None,
            "talks_subdir": location.talks_subdir,
            "talks_directory": (
                str(location.talks_directory) if location.talks_directory else None
            ),
        },
        "operation": "scan",
        "apply_requested": apply_requested,
        "database_written": False,
        "mutation_count": 0,
        "scanned_file_count": 0,
        "existing_talk_count": len(talks),
        "counts": {
            "add": 0,
            "update": 0,
            "unchanged": 0,
            "review_required": 0,
        },
        "entries": [],
    }
    candidate_database = copy.deepcopy(database)
    if not location.enabled:
        report["operation"] = "skipped_disabled"
        return report, candidate_database
    if location.source_type in NONLOCAL_SOURCE_TYPES:
        report["operation"] = "skipped_nonlocal"
        return report, candidate_database
    if location.talks_directory is None:
        raise ShownotesScanError("local shownotes location has no talks directory")

    _reject_symlink_components(
        location.talks_directory,
        subject="shownotes talks directory",
    )
    paths = sorted(location.talks_directory.glob("*.md"), key=lambda item: item.name)
    scanned_folded: dict[str, list[str]] = {}
    for path in paths:
        scanned_folded.setdefault(_normalized_filename(path.name), []).append(path.name)
    report["scanned_file_count"] = len(paths)
    additions: list[dict[str, Any]] = []
    updates: list[tuple[int, dict[str, Any]]] = []
    entries: list[dict[str, Any]] = []
    for path in paths:
        proposal, parse_issues = parse_shownotes_file(path)
        filename = path.name
        patch: dict[str, Any] = {}
        if filename in exact:
            index, talk = exact[filename]
            disposition, patch, issues = _existing_entry(talk, proposal, parse_issues)
            if disposition == "update":
                updates.append((index, patch))
        else:
            normalized = _normalized_filename(filename)
            casefold_matches = sorted(
                {
                    *folded.get(normalized, []),
                    *(
                        scanned_name
                        for scanned_name in scanned_folded.get(normalized, [])
                        if scanned_name != filename
                    ),
                }
            )
            issues = list(parse_issues)
            if casefold_matches:
                issues.append(
                    {
                        "code": "filename_identity_ambiguous",
                        "field": "filename",
                        "message": (
                            f"{filename!r} collides with {casefold_matches}; resolve exact "
                            "filename identity before import"
                        ),
                    }
                )
            if issues:
                disposition = "review_required"
            else:
                disposition = "add"
                record = {
                    key: value
                    for key, value in proposal.items()
                    if key == "filename" or key in TRACKED_FIELDS
                }
                record.update(
                    {
                        "schema_version": TALK_SCHEMA_VERSION,
                        "status": "pending",
                    }
                )
                additions.append(record)
                patch = record
        report["counts"][disposition] += 1
        entries.append(
            {
                "filename": filename,
                "disposition": disposition,
                "proposal": proposal,
                "changes": patch,
                "issues": issues,
                "applied": False,
            }
        )

    if apply_requested:
        for index, patch in updates:
            candidate_database["talks"][index].update(copy.deepcopy(patch))
        candidate_database["talks"].extend(copy.deepcopy(additions))
        for entry in entries:
            if entry["disposition"] in {"add", "update"}:
                entry["applied"] = True
    report["entries"] = entries
    report["mutation_count"] = len(additions) + len(updates)
    return report, candidate_database


def _atomic_write_database(
    path: Path,
    database: dict[str, Any],
    *,
    expected_snapshot: TrackingDatabaseSnapshot,
):
    """Commit against the exact generation captured before shownotes scanning."""
    try:
        return write_json_object(expected_snapshot, database)
    except TrackingDatabaseConflictError as exc:
        raise ShownotesScanError(
            "tracking database content or generation changed after the scan; "
            "rerun before applying"
        ) from exc
    except TrackingDatabaseIOError as exc:
        raise ShownotesScanError(
            f"cannot atomically update tracking database {path}: {exc}"
        ) from exc


def execute(database_path: Path, *, apply_requested: bool) -> dict[str, Any]:
    database, database_snapshot = _load_database(database_path)
    if apply_requested:
        try:
            require_current_tracking_database(database)
        except TrackingDatabaseError as exc:
            raise ShownotesScanError(str(exc)) from exc
    location = resolve_shownotes_location(database["config"])
    report, candidate = build_scan_report(
        database_path,
        database,
        location,
        apply_requested=apply_requested,
    )
    if apply_requested:
        if report["mutation_count"]:
            write_result = _atomic_write_database(
                database_path,
                candidate,
                expected_snapshot=database_snapshot,
            )
        else:
            write_result = unchanged_write_result(database_snapshot)
        write_fields = {
            "input_sha256": write_result.input_sha256,
            "output_sha256": write_result.output_sha256,
            "database_written": write_result.installed,
            "durability_state": write_result.durability_state,
            "warnings": list(write_result.warnings),
        }
    else:
        write_fields = {
            "input_sha256": database_snapshot.sha256,
            "output_sha256": database_snapshot.sha256,
            "database_written": False,
            "durability_state": "dry_run",
            "warnings": [],
        }
    report.update(write_fields)
    return report


def _error_payload(message: str) -> dict[str, Any]:
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "ok": False,
        "error": message,
    }


def main(argv: list[str] | None = None) -> int:
    parser = _ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("database", type=Path, help="canonical tracking-database.json")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="atomically apply only deterministic add/update entries",
    )
    try:
        args = parser.parse_args(argv)
        report = execute(args.database, apply_requested=args.apply)
    except (ShownotesScanError, OSError) as exc:
        message = str(exc)
        print(json.dumps(_error_payload(message), sort_keys=True))
        print(f"shownotes scan failed: {message}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    # outer-boundary-process-contract: skill callers treat missing JSON as a
    # silent scan failure; emit one error object and recovery action before exit.
    except Exception as exc:  # noqa: BLE001
        message = (
            f"unexpected shownotes scan failure: {type(exc).__name__}: {exc}; "
            "inspect the input/configuration, repair the named fault, and rerun"
        )
        print(json.dumps(_error_payload(message), sort_keys=True))
        print(message, file=sys.stderr)
        raise SystemExit(2) from exc
