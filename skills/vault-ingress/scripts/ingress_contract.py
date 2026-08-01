"""Small shared contracts for vault-ingress state and source boundaries."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


TALK_SCHEMA_VERSION = 5
TRANSCRIPT_ARTIFACT_FIELDS = ("transcript_path",)
PDF_SOURCE_FIELDS = (
    "slides_url",
    "google_drive_id",
    "slides_local_path",
    "slides_pdf_path",
    "pdf_path",
)
REMOTE_ACQUISITION_FIELDS = ("video_url", "slides_url", "google_drive_id")
LOCAL_ARTIFACT_FIELDS = (
    "transcript_path",
    "pptx_path",
    "slides_local_path",
    "slides_pdf_path",
    "pdf_path",
    "video_local_path",
    "video_path",
)
YOUTUBE_ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")
GOOGLE_DRIVE_ID_RE = re.compile(r"[A-Za-z0-9_-]{3,}")


class IngressContractError(ValueError):
    """A tracking-state or source capability violates the ingress contract."""


def has_nonempty_source_field(talk: dict, field: str) -> bool:
    value = talk.get(field)
    return isinstance(value, str) and bool(value.strip())


def parse_youtube_id(url: Any) -> str | None:
    """Return an ID from supported YouTube URL forms, otherwise ``None``."""
    if not isinstance(url, str) or not url.strip():
        return None
    candidate = url.strip()
    if "://" not in candidate and (
        candidate.startswith("youtube.com/")
        or candidate.startswith("www.youtube.com/")
        or candidate.startswith("m.youtube.com/")
        or candidate.startswith("youtu.be/")
    ):
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
    return (
        video_id
        if isinstance(video_id, str) and YOUTUBE_ID_RE.fullmatch(video_id)
        else None
    )


def is_youtube_url(url: Any) -> bool:
    """Return whether ``url`` names a recognized YouTube host."""
    if not isinstance(url, str) or not url.strip():
        return False
    candidate = url.strip()
    if "://" not in candidate:
        candidate = "https://" + candidate
    host = (urlparse(candidate).hostname or "").casefold().rstrip(".")
    return host in {
        "youtube.com", "www.youtube.com", "m.youtube.com",
        "youtu.be", "www.youtu.be", "youtube-nocookie.com",
        "www.youtube-nocookie.com",
    }


def parse_google_drive_id(url: Any) -> str | None:
    """Return a stable file/deck ID from common Google Drive URL forms."""
    if not isinstance(url, str) or not url.strip():
        return None
    candidate = url.strip()
    if "://" not in candidate:
        candidate = "https://" + candidate
    parsed = urlparse(candidate)
    host = (parsed.hostname or "").casefold().rstrip(".")
    if host not in {"drive.google.com", "docs.google.com"}:
        return None
    path_match = re.match(
        r"^/(?:file|presentation)/d/(?:e/)?([A-Za-z0-9_-]{3,})(?:/|$)",
        parsed.path,
    )
    if path_match is not None:
        return path_match.group(1)
    values = parse_qs(parsed.query).get("id", [])
    return (
        values[0]
        if values and GOOGLE_DRIVE_ID_RE.fullmatch(values[0])
        else None
    )


def _valid_http_url(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlparse(value.strip())
    return parsed.scheme.casefold() in {"http", "https"} and bool(parsed.hostname)


def has_remote_video_acquisition(talk: dict) -> bool:
    """Return whether a syntactically usable remote video identity exists."""
    youtube_id = talk.get("youtube_id")
    if isinstance(youtube_id, str) and YOUTUBE_ID_RE.fullmatch(youtube_id):
        return True
    video_url = talk.get("video_url")
    if not _valid_http_url(video_url):
        return False
    return not is_youtube_url(video_url) or parse_youtube_id(video_url) is not None


def has_remote_slide_acquisition(talk: dict) -> bool:
    """Return whether a syntactically usable remote slide identity exists."""
    drive_id = talk.get("google_drive_id")
    if isinstance(drive_id, str) and GOOGLE_DRIVE_ID_RE.fullmatch(drive_id.strip()):
        return True
    slides_url = talk.get("slides_url")
    if not _valid_http_url(slides_url):
        return False
    parsed = urlparse(str(slides_url).strip())
    if (parsed.hostname or "").casefold().rstrip(".") in {
        "drive.google.com", "docs.google.com"
    }:
        return parse_google_drive_id(slides_url) is not None
    return True


def has_video_source(talk: dict) -> bool:
    return has_remote_video_acquisition(talk) or any(
        has_nonempty_source_field(talk, field)
        for field in ("video_local_path", "video_path")
    )


def has_transcript_source(talk: dict) -> bool:
    """Return whether a transcript artifact exists or can be acquired."""
    return (
        any(has_nonempty_source_field(talk, field)
            for field in TRANSCRIPT_ARTIFACT_FIELDS)
        or has_video_source(talk)
    )


def has_pptx_source(talk: dict) -> bool:
    return has_nonempty_source_field(talk, "pptx_path")


def has_pdf_source(talk: dict) -> bool:
    return has_remote_slide_acquisition(talk) or any(
        has_nonempty_source_field(talk, field)
        for field in ("slides_local_path", "slides_pdf_path", "pdf_path")
    )


def source_capabilities(talk: dict) -> list[str]:
    """Resolve usable capabilities from reachable artifacts/acquisition paths.

    Provenance labels such as ``transcript_source: manual`` describe how an
    artifact was produced; they are never themselves evidence that the artifact
    is reachable. An active video is both video evidence and a transcript
    acquisition path.
    """
    capabilities = []
    if has_video_source(talk):
        capabilities.append("video")
    if has_pptx_source(talk) or has_pdf_source(talk):
        capabilities.append("slides")
    if has_transcript_source(talk):
        capabilities.append("transcript")
    return capabilities


def has_remote_acquisition_source(talk: dict) -> bool:
    """Return whether a declared upstream path could mechanically fail to download."""
    return (
        has_remote_video_acquisition(talk)
        or has_remote_slide_acquisition(talk)
    )


def has_local_source_artifact(talk: dict) -> bool:
    """Return whether a local transcript/deck/PDF reference remains usable."""
    return any(
        has_nonempty_source_field(talk, field)
        for field in LOCAL_ARTIFACT_FIELDS
    )


def validate_talk_record_schemas(talks: object) -> list[dict]:
    """Validate every talk shape/version without mutating any record."""
    if not isinstance(talks, list):
        raise IngressContractError("tracking database must carry a `talks` array")
    validated = []
    for index, talk in enumerate(talks):
        if not isinstance(talk, dict):
            raise IngressContractError(
                f"talks[{index}] must be a JSON object, got {type(talk).__name__}")
        version = talk.get("schema_version", 0)
        if (isinstance(version, bool) or not isinstance(version, int)
                or version < 0):
            raise IngressContractError(
                f"talks[{index}].schema_version must be a non-negative integer, "
                f"got {version!r}")
        if version > TALK_SCHEMA_VERSION:
            filename = talk.get("filename", f"talks[{index}]")
            raise IngressContractError(
                f"{filename} uses future talk schema_version {version}; this writer "
                f"supports through {TALK_SCHEMA_VERSION} and will not downgrade it")
        validated.append(talk)
    return validated


def reject_tracking_database_symlink(path: str | os.PathLike[str]) -> None:
    """Fail before opening a tracking DB through a final-component symlink."""
    candidate = Path(path)
    if candidate.is_symlink():
        raise IngressContractError(
            f"tracking database path {candidate} is a symbolic link; pass the "
            "canonical regular-file path so atomic replacement cannot split the "
            "link from its target")
