#!/usr/bin/env python3
"""Read-only, offline integrity preflight for a rhetoric vault.

Accept either a vault directory or its tracking-database JSON file.  The script
prints exactly one JSON report to stdout and exits 1 only when the report has a
blocking integrity finding.  Warnings (including legacy metadata gaps) exit 0.

This preflight deliberately does not fetch source metadata and does not inspect
PDF page counts.  In particular, a video-extracted PDF proves that a slide
artifact exists; its page count is not evidence for the authored ``slide_count``.

The optional ``source_identity`` evidence shape and finding taxonomy are
documented in ``references/source-identity-preflight.md``.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
import json
import math
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import parse_qs, urlparse


REPORT_SCHEMA_VERSION = 1
SOURCE_IDENTITY_SCHEMA_VERSION = 1

TRANSCRIPT_SOURCES = frozenset({"youtube_auto", "whisper", "manual", "none"})
SLIDE_SOURCES = frozenset({"pptx", "pdf", "both", "video_extracted", "none"})
COMPLETED_STATUSES = frozenset({"processed", "processed_partial"})
RELATION_TYPES = frozenset({"duplicate", "borrowed_recording"})

# These are intentionally a closed, documented set.  Tests exercise every
# class so callers can route fixes without parsing prose.
SLIDE_CONTRACT_CODES = frozenset({
    "slide_source_unsupported",
    "slide_pptx_reference_missing",
    "slide_pptx_artifact_missing",
    "slide_pdf_reference_missing",
    "slide_pdf_artifact_missing",
    "slide_video_reference_missing",
    "slide_video_artifact_missing",
})

YOUTUBE_ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")
WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
TITLE_STOP_WORDS = frozenset({
    "a", "an", "and", "at", "by", "conference", "for", "from", "in",
    "keynote", "of", "on", "or", "session", "talk", "the", "to", "with",
})


def parse_youtube_id(url: Any) -> str | None:
    """Return an ID from supported YouTube URL forms, otherwise ``None``.

    Supported forms are ``youtube.com/watch?v=...``, ``youtu.be/...``, and
    ``youtube.com/{shorts,embed}/...``.  A syntactically YouTube-looking URL
    with an invalid ID also returns ``None``; :func:`is_youtube_url` lets the
    validator distinguish that corruption from an unrelated video provider.
    """
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

    if video_id and YOUTUBE_ID_RE.fullmatch(video_id):
        return video_id
    return None


def is_youtube_url(url: Any) -> bool:
    """Whether ``url`` names a recognized YouTube host (valid ID or not)."""
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


def _nonempty_string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _json_value(value: Any) -> Any:
    """Keep finding details JSON-safe without stringifying normal scalars."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else repr(value)
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return repr(value)


class VaultPreflight:
    """Accumulate deterministic findings for one already-loaded database."""

    def __init__(self, database: Any, vault_root: Path, database_path: Path):
        self.database = database
        self.vault_root = vault_root.resolve(strict=False)
        self.database_path = database_path.resolve(strict=False)
        self.findings: list[dict[str, Any]] = []
        self.talks: list[dict[str, Any]] = []
        self.source_indexes: list[int] = []
        self.config: dict[str, Any] = {}
        self.filenames: dict[str, int] = {}
        self.youtube_ids: dict[int, str] = {}
        self.valid_relations: dict[int, tuple[str, str]] = {}

    def add(
        self,
        severity: str,
        code: str,
        message: str,
        *,
        talk_index: int | None = None,
        filename: str | None = None,
        field: str | None = None,
        expected: Any = None,
        actual: Any = None,
        artifact_path: Path | str | None = None,
    ) -> None:
        self.findings.append({
            "severity": severity,
            "code": code,
            "talk_index": talk_index,
            "filename": filename,
            "field": field,
            "message": message,
            "expected": _json_value(expected),
            "actual": _json_value(actual),
            "artifact_path": (
                str(Path(artifact_path).resolve(strict=False))
                if artifact_path is not None else None
            ),
        })

    def talk_add(
        self,
        index: int,
        severity: str,
        code: str,
        message: str,
        **details: Any,
    ) -> None:
        talk = self.talks[index]
        filename = _nonempty_string(talk.get("filename"))
        self.add(
            severity,
            code,
            message,
            talk_index=self.source_indexes[index],
            filename=filename,
            **details,
        )

    def run(self) -> dict[str, Any]:
        if not isinstance(self.database, dict):
            self.add(
                "blocking", "database_shape_invalid",
                "tracking database must be a JSON object",
                expected="object", actual=type(self.database).__name__,
            )
            return self.report(0)

        config = self.database.get("config", {})
        if isinstance(config, dict):
            self.config = config
        else:
            self.add(
                "warning", "config_shape_invalid",
                "config is not an object; config-backed checks were skipped",
                field="config", expected="object", actual=type(config).__name__,
            )

        talks = self.database.get("talks")
        if not isinstance(talks, list):
            self.add(
                "blocking", "talks_shape_invalid",
                "tracking database talks must be an array",
                field="talks", expected="array", actual=type(talks).__name__,
            )
            return self.report(0)

        for index, talk in enumerate(talks):
            if not isinstance(talk, dict):
                self.add(
                    "blocking", "talk_shape_invalid",
                    "each talks entry must be an object",
                    talk_index=index, expected="object",
                    actual=type(talk).__name__,
                )
                continue
            self.talks.append(talk)
            self.source_indexes.append(index)

        # Valid-entry checks use compact internal indexes.  Findings map those
        # back to the original source-array indexes, even around malformed rows.
        self._validate_filenames()
        for index in range(len(self.talks)):
            self._validate_sources(index)
            self._validate_artifacts(index)
            self._validate_source_identity(index)
        self._validate_relations()
        self._validate_duplicate_youtube_ids()
        return self.report(len(talks))

    def _validate_filenames(self) -> None:
        occurrences: defaultdict[str, list[int]] = defaultdict(list)
        for index, talk in enumerate(self.talks):
            value = talk.get("filename")
            filename = _nonempty_string(value)
            if filename is None:
                self.talk_add(
                    index, "blocking", "filename_missing",
                    "talk filename must be a nonempty string",
                    field="filename", expected="nonempty string", actual=value,
                )
                continue
            if value != filename:
                self.talk_add(
                    index, "blocking", "filename_not_normalized",
                    "talk filename must not have surrounding whitespace",
                    field="filename", expected=filename, actual=value,
                )
            occurrences[filename].append(index)
            self.filenames.setdefault(filename, index)

        for filename, indexes in sorted(occurrences.items()):
            if len(indexes) > 1:
                self.add(
                    "blocking", "duplicate_filename",
                    "talk filenames must be unique",
                    filename=filename, field="filename",
                    expected="one record",
                    actual=[self.source_indexes[index] for index in indexes],
                )

    def _validate_sources(self, index: int) -> None:
        talk = self.talks[index]
        transcript_source = talk.get("transcript_source")
        if transcript_source is not None and (
            not isinstance(transcript_source, str)
            or transcript_source not in TRANSCRIPT_SOURCES
        ):
            self.talk_add(
                index, "blocking", "transcript_source_unsupported",
                "transcript_source is outside the supported enum",
                field="transcript_source", expected=sorted(TRANSCRIPT_SOURCES),
                actual=transcript_source,
            )

        slide_source = talk.get("slide_source")
        if slide_source is not None and (
            not isinstance(slide_source, str)
            or slide_source not in SLIDE_SOURCES
        ):
            self.talk_add(
                index, "blocking", "slide_source_unsupported",
                "slide_source is outside the supported enum; transcript_only is "
                "represented by slide_source 'none'",
                field="slide_source", expected=sorted(SLIDE_SOURCES),
                actual=slide_source,
            )
        elif slide_source is None and self._needs_artifact_checks(talk):
            self.talk_add(
                index, "warning", "slide_source_missing",
                "processable or completed talk has no slide_source provenance",
                field="slide_source", expected=sorted(SLIDE_SOURCES), actual=None,
            )

        video_url = talk.get("video_url")
        stored_id = talk.get("youtube_id")
        parsed_id = parse_youtube_id(video_url)
        youtube_url = is_youtube_url(video_url)

        valid_stored_id = None
        if stored_id is not None and stored_id != "":
            if not isinstance(stored_id, str) or not YOUTUBE_ID_RE.fullmatch(stored_id):
                self.talk_add(
                    index, "blocking", "youtube_id_invalid",
                    "stored youtube_id must be exactly 11 URL-safe characters",
                    field="youtube_id", expected="11-character YouTube ID",
                    actual=stored_id,
                )
            else:
                valid_stored_id = stored_id

        if youtube_url and parsed_id is None:
            self.talk_add(
                index, "blocking", "youtube_url_invalid",
                "YouTube URL does not contain a valid ID in a supported URL form",
                field="video_url",
                expected="watch, youtu.be, shorts, or embed URL with an 11-character ID",
                actual=video_url,
            )
        elif parsed_id is not None and valid_stored_id is None:
            self.talk_add(
                index, "blocking", "youtube_id_missing",
                "YouTube URL has an ID but the stored youtube_id is missing or invalid",
                field="youtube_id", expected=parsed_id, actual=stored_id,
            )
        elif parsed_id is not None and valid_stored_id != parsed_id:
            self.talk_add(
                index, "blocking", "youtube_id_mismatch",
                "video_url and stored youtube_id identify different recordings",
                field="youtube_id", expected=parsed_id, actual=valid_stored_id,
            )

        identity_id = parsed_id or valid_stored_id
        if identity_id is not None:
            self.youtube_ids[index] = identity_id

    def _needs_artifact_checks(self, talk: dict[str, Any]) -> bool:
        return bool(_nonempty_string(talk.get("video_url"))) or (
            talk.get("status") in COMPLETED_STATUSES
        )

    def _artifact_severity(self, talk: dict[str, Any], *, declared: bool) -> str:
        # A completed record that explicitly declares an acquisition source has
        # made an integrity claim.  A pending/processable record is expected to
        # acquire the same artifact during ingress, so absence is actionable but
        # not yet corruption.
        if declared and talk.get("status") in COMPLETED_STATUSES:
            return "blocking"
        if talk.get("status") == "processed":
            return "blocking"
        return "warning"

    def _validate_artifacts(self, index: int) -> None:
        talk = self.talks[index]
        if not self._needs_artifact_checks(talk):
            return

        transcript_source = talk.get("transcript_source")
        source_is_known = transcript_source is None or (
            isinstance(transcript_source, str)
            and transcript_source in TRANSCRIPT_SOURCES
        )
        if transcript_source != "none" and source_is_known:
            transcript_path = self._transcript_path(talk)
            declared = (
                isinstance(transcript_source, str)
                and transcript_source in TRANSCRIPT_SOURCES - {"none"}
            )
            severity = self._artifact_severity(talk, declared=declared)
            if transcript_path is None:
                self.talk_add(
                    index, severity, "transcript_reference_missing",
                    "expected transcript cannot be resolved without youtube_id or transcript_path",
                    field="youtube_id", expected="youtube_id or transcript_path",
                    actual=talk.get("youtube_id"),
                )
            elif not transcript_path.is_file():
                self.talk_add(
                    index, severity, "transcript_artifact_missing",
                    "expected transcript file does not exist",
                    field="transcript_source", actual=transcript_source,
                    artifact_path=transcript_path,
                )

        slide_source = talk.get("slide_source")
        if (
            not isinstance(slide_source, str)
            or slide_source not in SLIDE_SOURCES
            or slide_source == "none"
        ):
            return
        severity = self._artifact_severity(talk, declared=True)

        if slide_source in {"pptx", "both"}:
            pptx_path = self._pptx_path(talk)
            if pptx_path is None:
                self.talk_add(
                    index, severity, "slide_pptx_reference_missing",
                    "slide_source requires a nonempty pptx_path",
                    field="pptx_path", expected="PPTX path",
                    actual=talk.get("pptx_path"),
                )
            elif not pptx_path.is_file():
                self.talk_add(
                    index, severity, "slide_pptx_artifact_missing",
                    "declared PPTX artifact does not exist",
                    field="pptx_path", actual=talk.get("pptx_path"),
                    artifact_path=pptx_path,
                )

        if slide_source in {"pdf", "both"}:
            explicit_pdf = self._slide_pdf_path(talk)
            if explicit_pdf is not None:
                if not explicit_pdf.is_file():
                    self.talk_add(
                        index, severity, "slide_pdf_artifact_missing",
                        "declared slide PDF artifact does not exist",
                        field=self._slide_pdf_path_field(talk),
                        actual=talk.get(self._slide_pdf_path_field(talk)),
                        artifact_path=explicit_pdf,
                    )
                # An explicit local artifact is a complete offline reference.
                # Legacy imports often predate Drive IDs and use descriptive
                # filenames; requiring a made-up Drive ID would corrupt their
                # provenance rather than improve it.
                return
            drive_id = _nonempty_string(talk.get("google_drive_id"))
            if drive_id is None:
                self.talk_add(
                    index, severity, "slide_pdf_reference_missing",
                    "slide_source requires a nonempty google_drive_id",
                    field="google_drive_id", expected="Google Drive file ID",
                    actual=talk.get("google_drive_id"),
                )
            else:
                pdf_path = self.vault_root / "slides" / f"{drive_id}.pdf"
                if not pdf_path.is_file():
                    self.talk_add(
                        index, severity, "slide_pdf_artifact_missing",
                        "declared Google Drive PDF artifact does not exist",
                        field="google_drive_id", actual=drive_id,
                        artifact_path=pdf_path,
                    )

        if slide_source == "video_extracted":
            explicit_pdf = self._slide_pdf_path(talk)
            if explicit_pdf is not None:
                if not explicit_pdf.is_file():
                    self.talk_add(
                        index, severity, "slide_video_artifact_missing",
                        "declared video-extracted PDF artifact does not exist",
                        field=self._slide_pdf_path_field(talk),
                        actual=talk.get(self._slide_pdf_path_field(talk)),
                        artifact_path=explicit_pdf,
                    )
                return
            youtube_id = self.youtube_ids.get(index)
            if youtube_id is None:
                self.talk_add(
                    index, severity, "slide_video_reference_missing",
                    "video_extracted source requires a valid YouTube identity",
                    field="youtube_id", expected="valid YouTube ID",
                    actual=talk.get("youtube_id"),
                )
            else:
                pdf_path = self.vault_root / "slides" / f"{youtube_id}.pdf"
                if not pdf_path.is_file():
                    self.talk_add(
                        index, severity, "slide_video_artifact_missing",
                        "declared video-extracted PDF artifact does not exist",
                        field="slide_source", actual="video_extracted",
                        artifact_path=pdf_path,
                    )

    def _transcript_path(self, talk: dict[str, Any]) -> Path | None:
        explicit = _nonempty_string(talk.get("transcript_path"))
        if explicit:
            path = Path(explicit).expanduser()
            return path if path.is_absolute() else self.vault_root / path
        youtube_id = _nonempty_string(talk.get("youtube_id"))
        if youtube_id and YOUTUBE_ID_RE.fullmatch(youtube_id):
            return self.vault_root / "transcripts" / f"{youtube_id}.txt"
        return None

    def _pptx_path(self, talk: dict[str, Any]) -> Path | None:
        value = _nonempty_string(talk.get("pptx_path"))
        if value is None:
            return None
        path = Path(value).expanduser()
        if path.is_absolute():
            return path
        source_dir = _nonempty_string(self.config.get("pptx_source_dir"))
        if source_dir:
            return Path(source_dir).expanduser() / path
        return self.vault_root / path

    @staticmethod
    def _slide_pdf_path_field(talk: dict[str, Any]) -> str:
        """Return the first populated canonical-or-legacy local PDF field."""
        for field in ("slides_local_path", "slides_pdf_path", "pdf_path"):
            if _nonempty_string(talk.get(field)):
                return field
        return "slides_local_path"

    def _slide_pdf_path(self, talk: dict[str, Any]) -> Path | None:
        """Resolve a recorded local slide PDF without inventing provenance.

        ``slides_local_path`` is the current field. ``slides_pdf_path`` and
        ``pdf_path`` are accepted read-only aliases because historical ingress
        wrote both forms and those artifacts can be perfectly valid even when
        no Google Drive identifier was ever recorded.
        """
        field = self._slide_pdf_path_field(talk)
        value = _nonempty_string(talk.get(field))
        if value is None:
            return None
        path = Path(value).expanduser()
        return path if path.is_absolute() else self.vault_root / path

    def _validate_source_identity(self, index: int) -> None:
        talk = self.talks[index]
        if "source_identity" not in talk:
            return  # The v1 evidence block is optional for legacy records.
        evidence = talk.get("source_identity")
        if not isinstance(evidence, dict):
            self.talk_add(
                index, "blocking", "source_identity_shape_invalid",
                "source_identity must be an object",
                field="source_identity", expected="object",
                actual=type(evidence).__name__,
            )
            return

        schema_version = evidence.get("schema_version")
        if schema_version is None:
            self.talk_add(
                index, "warning", "source_identity_schema_missing",
                "source_identity has no schema_version; validating known fields",
                field="source_identity.schema_version",
                expected=SOURCE_IDENTITY_SCHEMA_VERSION, actual=None,
            )
        elif (
            type(schema_version) is not int
            or schema_version != SOURCE_IDENTITY_SCHEMA_VERSION
        ):
            self.talk_add(
                index, "warning", "source_identity_schema_unsupported",
                "source_identity schema version is not the version this preflight owns; "
                "validating known fields only",
                field="source_identity.schema_version",
                expected=SOURCE_IDENTITY_SCHEMA_VERSION, actual=schema_version,
            )

        provider = evidence.get("provider")
        if provider is not None and provider != "youtube":
            self.talk_add(
                index, "warning", "source_identity_provider_unknown",
                "source_identity provider is not currently understood",
                field="source_identity.provider", expected="youtube", actual=provider,
            )

        evidence_id = evidence.get("video_id")
        expected_id = self.youtube_ids.get(index)
        if evidence_id is None:
            self._identity_gap(index, "video_id")
        elif not isinstance(evidence_id, str) or not YOUTUBE_ID_RE.fullmatch(evidence_id):
            self.talk_add(
                index, "blocking", "source_identity_video_id_invalid",
                "source_identity video_id must be an 11-character YouTube ID",
                field="source_identity.video_id",
                expected="11-character YouTube ID", actual=evidence_id,
            )
        elif expected_id is not None and evidence_id != expected_id:
            self.talk_add(
                index, "blocking", "source_identity_video_id_mismatch",
                "recorded identity evidence names a different video",
                field="source_identity.video_id", expected=expected_id,
                actual=evidence_id,
            )

        self._validate_identity_title(index, evidence)
        self._validate_identity_speakers(index, evidence)
        self._validate_identity_dates(index, evidence)
        self._validate_identity_duration(index, evidence)

    def _identity_gap(self, index: int, field: str) -> None:
        self.talk_add(
            index, "warning", f"source_identity_{field}_missing",
            f"source_identity has no {field} evidence",
            field=f"source_identity.{field}", expected=f"recorded {field} evidence",
            actual=None,
        )

    def _validate_identity_title(self, index: int, evidence: dict[str, Any]) -> None:
        observed = evidence.get("title")
        expected = self.talks[index].get("title")
        if observed is None:
            self._identity_gap(index, "title")
            return
        observed_title = _nonempty_string(observed)
        if observed_title is None:
            self.talk_add(
                index, "blocking", "source_identity_title_invalid",
                "source_identity title must be a nonempty string",
                field="source_identity.title", expected="nonempty title", actual=observed,
            )
            return
        expected_title = _nonempty_string(expected)
        if expected_title is None:
            self.talk_add(
                index, "warning", "source_identity_title_uncheckable",
                "talk has no title to compare with recorded title evidence",
                field="title", expected="talk title", actual=expected,
            )
            return
        if not titles_agree(expected_title, observed_title):
            self.talk_add(
                index, "blocking", "source_identity_title_mismatch",
                "recorded video title does not materially overlap the catalog title",
                field="source_identity.title", expected=expected_title,
                actual=observed_title,
            )

    def _validate_identity_speakers(self, index: int, evidence: dict[str, Any]) -> None:
        observed = evidence.get("speakers")
        if observed is None:
            self._identity_gap(index, "speakers")
            return
        if (
            not isinstance(observed, list)
            or not observed
            or any(not _nonempty_string(item) for item in observed)
        ):
            self.talk_add(
                index, "blocking", "source_identity_speakers_invalid",
                "source_identity speakers must be a nonempty array of nonempty names",
                field="source_identity.speakers",
                expected="nonempty string array", actual=observed,
            )
            return

        expected = expected_speakers(self.talks[index], self.config)
        if not expected:
            self.talk_add(
                index, "warning", "source_identity_speakers_uncheckable",
                "catalog and config have no expected speaker name",
                field="speaker", expected="catalog or config speaker", actual=None,
            )
            return
        if not any(names_agree(left, right) for left in expected for right in observed):
            self.talk_add(
                index, "blocking", "source_identity_speaker_mismatch",
                "recorded speaker evidence does not name an expected speaker",
                field="source_identity.speakers", expected=expected, actual=observed,
            )

    def _validate_identity_dates(self, index: int, evidence: dict[str, Any]) -> None:
        talk_date = parse_catalog_date(self.talks[index].get("date"))
        recorded_raw = evidence.get("recorded_date")
        upload_raw = evidence.get("upload_date")
        if recorded_raw is None and upload_raw is None:
            self._identity_gap(index, "date")
            return

        recorded = self._parse_evidence_date(index, "recorded_date", recorded_raw)
        upload = self._parse_evidence_date(index, "upload_date", upload_raw)
        if talk_date is None:
            self.talk_add(
                index, "warning", "source_identity_date_uncheckable",
                "catalog date is absent or not YYYY/ISO-8601; source dates cannot be compared",
                field="date", expected="YYYY or YYYY-MM-DD",
                actual=self.talks[index].get("date"),
            )
            return

        catalog_day, catalog_year = talk_date
        if recorded is not None:
            if recorded.year != catalog_year:
                self.talk_add(
                    index, "blocking", "source_identity_recorded_year_mismatch",
                    "recorded date and catalog date are in different years",
                    field="source_identity.recorded_date",
                    expected=catalog_year, actual=recorded.isoformat(),
                )
            elif catalog_day is not None and recorded != catalog_day:
                self.talk_add(
                    index, "warning", "source_identity_recorded_date_differs",
                    "recorded date differs from the catalog day within the same year",
                    field="source_identity.recorded_date",
                    expected=catalog_day.isoformat(), actual=recorded.isoformat(),
                )
        if upload is not None:
            predates = (
                upload < catalog_day if catalog_day is not None
                else upload.year < catalog_year
            )
            if predates:
                self.talk_add(
                    index, "blocking", "source_identity_upload_predates_talk",
                    "recorded upload date predates the cataloged delivery",
                    field="source_identity.upload_date",
                    expected=(catalog_day.isoformat() if catalog_day else f">={catalog_year}"),
                    actual=upload.isoformat(),
                )

    def _parse_evidence_date(
        self, index: int, field: str, value: Any,
    ) -> date | None:
        if value is None:
            return None
        if not isinstance(value, str):
            self.talk_add(
                index, "blocking", "source_identity_date_invalid",
                f"source_identity {field} must be an ISO-8601 calendar date",
                field=f"source_identity.{field}", expected="YYYY-MM-DD", actual=value,
            )
            return None
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            self.talk_add(
                index, "blocking", "source_identity_date_invalid",
                f"source_identity {field} must be an ISO-8601 calendar date",
                field=f"source_identity.{field}", expected="YYYY-MM-DD", actual=value,
            )
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            self.talk_add(
                index, "blocking", "source_identity_date_invalid",
                f"source_identity {field} must be an ISO-8601 calendar date",
                field=f"source_identity.{field}", expected="YYYY-MM-DD", actual=value,
            )
            return None

    def _validate_identity_duration(self, index: int, evidence: dict[str, Any]) -> None:
        observed = evidence.get("duration_seconds")
        if observed is None:
            self._identity_gap(index, "duration_seconds")
            return
        if (
            isinstance(observed, bool)
            or not isinstance(observed, (int, float))
            or not math.isfinite(observed)
            or observed <= 0
        ):
            self.talk_add(
                index, "blocking", "source_identity_duration_invalid",
                "source_identity duration_seconds must be a positive number",
                field="source_identity.duration_seconds",
                expected="positive seconds", actual=observed,
            )
            return

        expected = expected_duration_seconds(self.talks[index])
        if expected is None:
            return
        tolerance = max(60.0, expected * 0.05)
        if abs(float(observed) - expected) > tolerance:
            self.talk_add(
                index, "blocking", "source_identity_duration_mismatch",
                "recorded duration differs from catalog duration beyond 60 seconds or 5%",
                field="source_identity.duration_seconds", expected=expected,
                actual=observed,
            )

    def _validate_relations(self) -> None:
        for index, talk in enumerate(self.talks):
            relation = relation_from(talk)
            if relation is None:
                continue
            relation_type, target = relation
            if (
                not isinstance(relation_type, str)
                or relation_type not in RELATION_TYPES
                or not _nonempty_string(target)
            ):
                self.talk_add(
                    index, "blocking", "source_relation_invalid",
                    "source relation must have type duplicate|borrowed_recording and a target filename",
                    field="source_relation",
                    expected={"type": sorted(RELATION_TYPES), "target_filename": "..."},
                    actual=talk.get("source_relation"),
                )
                continue
            target = target.strip()
            target_index = self.filenames.get(target)
            if target_index is None or target_index == index:
                self.talk_add(
                    index, "blocking", "source_relation_invalid",
                    "source relation target must name another catalog record",
                    field="source_relation.target_filename",
                    expected="another existing filename", actual=target,
                )
                continue
            source_id = self.youtube_ids.get(index)
            target_id = self.youtube_ids.get(target_index)
            if source_id is None or source_id != target_id:
                # Legacy `_duplicate_of` records describe duplicate *content*
                # as well as duplicate recordings.  A different video simply
                # cannot waive duplicate-ID enforcement; it is not itself
                # corrupt.  The explicit v1 source_relation shape is narrower.
                if "source_relation" in talk or relation_type == "borrowed_recording":
                    self.talk_add(
                        index, "blocking", "source_relation_identity_mismatch",
                        "duplicate/borrowed relation target must carry the same YouTube identity",
                        field="source_relation.target_filename",
                        expected=source_id, actual=target_id,
                    )
                continue
            self.valid_relations[index] = (relation_type, target)

    def _validate_duplicate_youtube_ids(self) -> None:
        groups: defaultdict[str, list[int]] = defaultdict(list)
        for index, video_id in self.youtube_ids.items():
            groups[video_id].append(index)
        for video_id, indexes in sorted(groups.items()):
            if len(indexes) < 2:
                continue
            roots = [index for index in indexes if index not in self.valid_relations]
            if len(roots) <= 1:
                continue
            filenames = [
                _nonempty_string(self.talks[index].get("filename"))
                or f"talk[{index}]"
                for index in indexes
            ]
            self.add(
                "blocking", "duplicate_youtube_id",
                "YouTube ID is used by multiple talks without an explicit "
                "duplicate/borrowed-recording relation",
                field="youtube_id", expected="one canonical record plus explicit relations",
                actual={"youtube_id": video_id, "filenames": filenames},
            )

    def report(self, talk_count: int) -> dict[str, Any]:
        severity_order = {"blocking": 0, "warning": 1}
        self.findings.sort(key=lambda finding: (
            severity_order.get(finding["severity"], 9),
            finding["filename"] or "",
            finding["talk_index"] if finding["talk_index"] is not None else -1,
            finding["code"],
            finding["message"],
        ))
        by_severity = Counter(item["severity"] for item in self.findings)
        by_code = Counter(item["code"] for item in self.findings)
        blocking = by_severity["blocking"]
        warnings = by_severity["warning"]
        return {
            "schema_version": REPORT_SCHEMA_VERSION,
            "ok": blocking == 0,
            "database": str(self.database_path),
            "vault_root": str(self.vault_root),
            "talk_count": talk_count,
            "blocking_count": blocking,
            "warning_count": warnings,
            "summary": {
                "by_severity": {
                    "blocking": blocking,
                    "warning": warnings,
                },
                "by_code": dict(sorted(by_code.items())),
            },
            "findings": self.findings,
        }


def _normalized_words(value: str) -> set[str]:
    return {
        word for word in WORD_RE.findall(value.casefold())
        if word not in TITLE_STOP_WORDS and len(word) > 1
    }


def titles_agree(expected: str, observed: str) -> bool:
    """Conservative, deterministic title-overlap check.

    At least half the catalog's significant words must appear in the recorded
    source title, with a two-word floor when the catalog title has two or more
    significant words.  Exact normalized containment is accepted first.
    """
    expected_flat = " ".join(WORD_RE.findall(expected.casefold()))
    observed_flat = " ".join(WORD_RE.findall(observed.casefold()))
    if expected_flat and f" {expected_flat} " in f" {observed_flat} ":
        return True
    expected_words = _normalized_words(expected)
    observed_words = _normalized_words(observed)
    if not expected_words or not observed_words:
        return False
    overlap = len(expected_words & observed_words)
    minimum = 1 if len(expected_words) == 1 else max(2, (len(expected_words) + 1) // 2)
    return overlap >= minimum


def _name_words(value: str) -> set[str]:
    return {word for word in WORD_RE.findall(value.casefold()) if len(word) > 1}


def names_agree(expected: str, observed: str) -> bool:
    expected_ordered = [
        word for word in WORD_RE.findall(expected.casefold()) if len(word) > 1
    ]
    left = _name_words(expected)
    right = _name_words(observed)
    if not left or not right:
        return False
    if left <= right:
        return True
    return right <= left and bool(expected_ordered) and expected_ordered[-1] in right


def expected_speakers(talk: dict[str, Any], config: dict[str, Any]) -> list[str]:
    for key in ("speakers", "speaker"):
        value = talk.get(key)
        if isinstance(value, list):
            names = [item.strip() for item in value if _nonempty_string(item)]
            if names:
                return names
        else:
            name = _nonempty_string(value)
            if name:
                return [name]
    config_name = _nonempty_string(config.get("speaker_name"))
    return [config_name] if config_name else []


def parse_catalog_date(value: Any) -> tuple[date | None, int] | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if re.fullmatch(r"\d{4}", value):
        return None, int(value)
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed, parsed.year


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
        if isinstance(value, bool):
            continue
        if (
            isinstance(value, (int, float))
            and math.isfinite(value)
            and value > 0
        ):
            return float(value)
    return None


def relation_from(talk: dict[str, Any]) -> tuple[Any, Any] | None:
    """Read the v1 relation shape plus narrowly-scoped legacy aliases."""
    if "source_relation" in talk:
        relation = talk.get("source_relation")
        if relation is None:
            return None
        if not isinstance(relation, dict):
            return "", None
        return relation.get("type"), relation.get("target_filename")
    for key, relation_type in (
        ("duplicate_of", "duplicate"),
        ("_duplicate_of", "duplicate"),
        ("borrowed_recording_from", "borrowed_recording"),
        ("_borrowed_recording_from", "borrowed_recording"),
    ):
        if key in talk and talk.get(key) is not None:
            return relation_type, talk.get(key)
    return None


def resolve_input(value: str | Path) -> tuple[Path, Path]:
    """Return ``(vault_root, database_path)`` without requiring either to exist."""
    path = Path(value).expanduser()
    if path.is_dir() or (not path.exists() and path.suffix.casefold() != ".json"):
        return path, path / "tracking-database.json"
    return path.parent, path


def error_report(vault_root: Path, database_path: Path, code: str, message: str) -> dict[str, Any]:
    validator = VaultPreflight({}, vault_root, database_path)
    validator.add("blocking", code, message)
    return validator.report(0)


def run_preflight(value: str | Path) -> dict[str, Any]:
    """Load and validate a vault, returning a report without mutating it."""
    vault_root, database_path = resolve_input(value)
    try:
        raw = database_path.read_text(encoding="utf-8")
    except UnicodeError as exc:
        return error_report(
            vault_root, database_path, "database_encoding_invalid",
            f"tracking database is not valid UTF-8: {exc}",
        )
    except OSError as exc:
        return error_report(
            vault_root, database_path, "database_unreadable",
            f"cannot read tracking database: {exc}",
        )
    try:
        database = json.loads(raw)
    except json.JSONDecodeError as exc:
        return error_report(
            vault_root, database_path, "database_json_invalid",
            f"tracking database is not valid JSON at line {exc.lineno}, column {exc.colno}",
        )
    return VaultPreflight(database, vault_root, database_path).run()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument(
        "vault_or_database",
        help="vault root directory or tracking-database JSON path",
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code:
            report = error_report(
                Path.cwd(), Path.cwd() / "tracking-database.json",
                "invalid_arguments", "expected one vault directory or database path",
            )
            print(json.dumps(report, indent=2, sort_keys=True))
        raise

    report = run_preflight(args.vault_or_database)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["blocking_count"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
