"""Small shared contracts for vault-ingress state and source boundaries."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qs, urlparse

from tracking_database import TALK_RECORD_SCHEMA_VERSION

TALK_SCHEMA_VERSION = TALK_RECORD_SCHEMA_VERSION
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
# Shape version of the structured_data.video_extraction record. Owned by
# skills/vault-ingress/scripts/video-slide-extraction.py and shared here so the
# producer and every reader gate on one number. v5 reads `source_video_id` as a
# provider-qualified binding token; v4 read it as a YouTube ID, which every v5
# reader still accepts because a YouTube ID is exactly its own token. That is
# what makes this a backward-compatible widening rather than a repurposed
# field: a v4 record needs no migration and no re-extraction, and the two
# contracts stay distinguishable because a v4 record may not carry a
# provider-prefixed token. v3 predates the source receipt and stays readable
# only as an archival/reprocessing input, never upgraded in place.
VIDEO_EXTRACTION_SCHEMA_VERSION = 5
YOUTUBE_BOUND_VIDEO_EXTRACTION_SCHEMA_VERSION = 4
READABLE_VIDEO_EXTRACTION_SCHEMA_VERSIONS = frozenset({4, 5})
ARCHIVAL_VIDEO_EXTRACTION_SCHEMA_VERSION = 3
YOUTUBE_ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")
GOOGLE_DRIVE_ID_RE = re.compile(r"[A-Za-z0-9_-]{3,}")
VIMEO_ID_RE = re.compile(r"[0-9]{6,12}")
# An InfoQ presentation is addressed by a path slug, not a numeric id. The
# provider exposes no video id at all, so the slug is the identity.
INFOQ_SLUG_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{1,79}[a-z0-9])?")
# Providers whose recordings this pipeline can bind evidence to. A provider
# outside the set is readable as a URL and remains unusable as an identity:
# nothing derives a binding token for it, so its artifacts stay unbound rather
# than binding to a token that no reader can reproduce.
SUPPORTED_SOURCE_PROVIDERS = ("youtube", "vimeo", "infoq")
# The provider separator sits OUTSIDE the YouTube ID alphabet on purpose. With
# an in-alphabet separator, the InfoQ slug `kafka` and a real YouTube ID
# `infoq-kafka` produce the same token, and every ownership, alias, and
# duplicate check keyed on that token conflates two different recordings. A
# character no YouTube ID can contain makes the overlap unrepresentable rather
# than unlikely.
SOURCE_PROVIDER_SEPARATOR = "+"


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
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "youtu.be",
        "www.youtu.be",
        "youtube-nocookie.com",
        "www.youtube-nocookie.com",
    }


def parse_vimeo_id(url: Any) -> str | None:
    """Return the numeric ID from supported Vimeo URL forms, otherwise ``None``."""
    parsed = _parsed_provider_url(url)
    if parsed is None:
        return None
    host, parts = parsed
    if host == "player.vimeo.com":
        candidate = parts[1] if len(parts) >= 2 and parts[0] == "video" else None
    elif host == "vimeo.com":
        if len(parts) >= 3 and parts[0] in {"groups", "event"} and parts[2] == "videos":
            candidate = parts[3] if len(parts) >= 4 else None
        elif len(parts) >= 3 and parts[0] == "channels":
            candidate = parts[2]
        else:
            # A bare `/<id>` optionally followed by an unlisted-link hash.
            candidate = parts[0] if parts else None
    else:
        return None
    return (
        candidate
        if isinstance(candidate, str) and VIMEO_ID_RE.fullmatch(candidate)
        else None
    )


def parse_infoq_id(url: Any) -> str | None:
    """Return the presentation slug from an InfoQ presentation URL."""
    parsed = _parsed_provider_url(url)
    if parsed is None:
        return None
    host, parts = parsed
    if host != "infoq.com" or len(parts) < 2 or parts[0] != "presentations":
        return None
    slug = parts[1].casefold()
    return slug if INFOQ_SLUG_RE.fullmatch(slug) else None


def _parsed_provider_url(url: Any) -> tuple[str, list[str]] | None:
    """Return one URL's normalized host and non-empty path segments."""
    if not isinstance(url, str) or not url.strip():
        return None
    candidate = url.strip()
    if "://" not in candidate:
        candidate = "https://" + candidate
    parsed = urlparse(candidate)
    if parsed.scheme.casefold() not in {"http", "https"}:
        return None
    host = (parsed.hostname or "").casefold().rstrip(".")
    for prefix in ("www.", "m."):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    return host, [part for part in parsed.path.split("/") if part]


@dataclass(frozen=True)
class SourceIdentity:
    """One talk recording's provider-qualified identity.

    ``binding_token`` is what every artifact, manifest, and receipt binds to.
    A YouTube token is the bare 11-character ID, so every identity written
    before providers were qualified keeps binding to the same token and no
    stored artifact changes meaning. Other providers carry their prefix, which
    is what keeps two providers' identically-named recordings apart.
    """

    provider: str
    video_id: str

    @property
    def binding_token(self) -> str:
        if self.provider == "youtube":
            return self.video_id
        return f"{self.provider}{SOURCE_PROVIDER_SEPARATOR}{self.video_id}"


_PROVIDER_PARSERS = (
    ("youtube", parse_youtube_id),
    ("vimeo", parse_vimeo_id),
    ("infoq", parse_infoq_id),
)
_PROVIDER_ID_PATTERNS = {
    "youtube": YOUTUBE_ID_RE,
    "vimeo": VIMEO_ID_RE,
    "infoq": INFOQ_SLUG_RE,
}


def parse_source_identity(url: Any) -> SourceIdentity | None:
    """Return the provider-qualified identity a supported URL names."""
    for provider, parser in _PROVIDER_PARSERS:
        video_id = parser(url)
        if video_id is not None:
            return SourceIdentity(provider, video_id)
    return None


def source_identity_for(provider: Any, video_id: Any) -> SourceIdentity | None:
    """Return a validated identity for one declared provider/ID pair."""
    if not isinstance(provider, str) or not isinstance(video_id, str):
        return None
    pattern = _PROVIDER_ID_PATTERNS.get(provider)
    if pattern is None or not pattern.fullmatch(video_id):
        return None
    return SourceIdentity(provider, video_id)


def talk_source_identity(talk: Mapping[str, Any]) -> SourceIdentity | None:
    """Return the identity a talk record's active source names.

    The stored ``youtube_id`` keeps its precedence over ``video_url`` so a
    YouTube talk resolves exactly as it did before providers were qualified;
    every other provider resolves from the active URL, which is the only place
    a non-YouTube identity is recorded.
    """
    youtube_id = talk.get("youtube_id")
    if isinstance(youtube_id, str) and YOUTUBE_ID_RE.fullmatch(youtube_id):
        return SourceIdentity("youtube", youtube_id)
    return parse_source_identity(talk.get("video_url"))


def talk_binding_token(talk: Mapping[str, Any]) -> str | None:
    """Return the token a talk's artifacts and receipts bind to."""
    identity = talk_source_identity(talk)
    return None if identity is None else identity.binding_token


def is_source_binding_token(value: Any) -> bool:
    """Return whether exactly one supported identity produces this token."""
    return token_source_identity(value) is not None


def token_source_identity(value: Any) -> SourceIdentity | None:
    """Return the one identity a binding token names, otherwise ``None``.

    The inverse of ``binding_token`` and total: the separator cannot appear in a
    YouTube ID, so a prefixed token and a YouTube token are never the same
    string and this never has to choose between two readings.
    """
    if not isinstance(value, str):
        return None
    if YOUTUBE_ID_RE.fullmatch(value):
        return SourceIdentity("youtube", value)
    provider, separator, video_id = value.partition(SOURCE_PROVIDER_SEPARATOR)
    if not separator or provider == "youtube":
        return None
    return source_identity_for(provider, video_id)


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
    return values[0] if values and GOOGLE_DRIVE_ID_RE.fullmatch(values[0]) else None


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
        "drive.google.com",
        "docs.google.com",
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
    return any(
        has_nonempty_source_field(talk, field) for field in TRANSCRIPT_ARTIFACT_FIELDS
    ) or has_video_source(talk)


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
    return has_remote_video_acquisition(talk) or has_remote_slide_acquisition(talk)


def has_local_source_artifact(talk: dict) -> bool:
    """Return whether a local transcript/deck/PDF reference remains usable."""
    return any(
        has_nonempty_source_field(talk, field) for field in LOCAL_ARTIFACT_FIELDS
    )


def validate_talk_record_schemas(talks: object) -> list[dict]:
    """Validate every talk shape/version without mutating any record."""
    if not isinstance(talks, list):
        raise IngressContractError("tracking database must carry a `talks` array")
    validated = []
    for index, talk in enumerate(talks):
        if not isinstance(talk, dict):
            raise IngressContractError(
                f"talks[{index}] must be a JSON object, got {type(talk).__name__}"
            )
        version = talk.get("schema_version", 0)
        if isinstance(version, bool) or not isinstance(version, int) or version < 0:
            raise IngressContractError(
                f"talks[{index}].schema_version must be a non-negative integer, "
                f"got {version!r}"
            )
        if version > TALK_SCHEMA_VERSION:
            filename = talk.get("filename", f"talks[{index}]")
            raise IngressContractError(
                f"{filename} uses future talk schema_version {version}; this writer "
                f"supports through {TALK_SCHEMA_VERSION} and will not downgrade it"
            )
        validated.append(talk)
    return validated


def reject_tracking_database_symlink(path: str | os.PathLike[str]) -> None:
    """Fail before opening a tracking DB through a final-component symlink."""
    candidate = Path(path)
    if candidate.is_symlink():
        raise IngressContractError(
            f"tracking database path {candidate} is a symbolic link; pass the "
            "canonical regular-file path so atomic replacement cannot split the "
            "link from its target"
        )
