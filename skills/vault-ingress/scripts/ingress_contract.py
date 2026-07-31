"""Small shared contracts for vault-ingress state and source boundaries."""

from __future__ import annotations

import os
from pathlib import Path


TALK_SCHEMA_VERSION = 3
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
)


class IngressContractError(ValueError):
    """A tracking-state or source capability violates the ingress contract."""


def has_nonempty_source_field(talk: dict, field: str) -> bool:
    value = talk.get(field)
    return isinstance(value, str) and bool(value.strip())


def has_video_source(talk: dict) -> bool:
    return has_nonempty_source_field(talk, "video_url")


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
    return any(has_nonempty_source_field(talk, field) for field in PDF_SOURCE_FIELDS)


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
    return any(
        has_nonempty_source_field(talk, field)
        for field in REMOTE_ACQUISITION_FIELDS
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
