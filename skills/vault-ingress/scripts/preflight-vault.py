#!/usr/bin/env python3
"""Read-only, offline integrity preflight for a rhetoric vault.

Accept either a vault directory or its tracking-database JSON file.  The script
prints exactly one JSON report to stdout and exits 1 only when the report has a
blocking integrity finding.  Warnings (including legacy metadata gaps) exit 0.

This preflight deliberately does not fetch source metadata. It verifies PDF
container/page-tree integrity inside bounded workers, but a delivered PDF page
count is never evidence for the authored ``slide_count``.

The optional ``source_identity`` evidence shape and finding taxonomy are
documented in ``references/source-identity-preflight.md``.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime
import json
import math
import os
from pathlib import Path
import re
import sys
from typing import Any

from artifact_locator import (
    ArtifactLocatorError,
    materialize_artifact_locator,
    materialize_native_root,
)
from artifact_metadata import canonicalize_trusted_artifact_locator
from ingress_contract import (
    YOUTUBE_ID_RE,
    is_youtube_url,
    parse_google_drive_id,
    parse_youtube_id,
    source_capabilities,
)

from return_validation import (
    PATTERN_SCORING_SCHEMA_VERSION,
    ReturnValidationError,
    VIDEO_EXTRACTION_SCHEMA_VERSION,
    validate_video_extraction_manifest,
)
from pattern_evidence import (
    PATTERN_EVIDENCE_SCHEMA_VERSION,
    PatternEvidenceError,
    assess_talk_artifact_capabilities,
    resolve_video_extraction_source,
    validate_transcript_path,
    validate_transcript_quality_for_owner,
)
from pdf_evidence import PdfArtifactProbe, PdfEvidenceError, probe_pdf_artifact
from video_evidence import VideoEvidenceAssessment, VideoEvidenceError
from source_identity_matching import (
    EventAlias,
    event_agreement,
    known_event_aliases,
    titles_agree,
)
from tracking_database import (
    CONFIG_RECORD_SCHEMA_VERSION,
    LEGACY_CONFIG_RECORD_SCHEMA_VERSION,
    TrackingDatabaseConfigExclusionsError,
    TrackingDatabaseError,
    assess_tracking_database,
)
from pptx_discovery_contract import (
    PptxDiscoveryContractError,
    validate_pptx_directory_exclusions,
)
from tracking_database_io import (
    TrackingDatabaseIOError,
    decode_json_object,
    snapshot_tracking_database,
)
from vault_root_authority import (
    VaultRootAuthorityError,
    materialize_native_authority,
    resolve_vault_root_authority,
)


REPORT_SCHEMA_VERSION = 1
SOURCE_IDENTITY_SCHEMA_VERSION = 1
TRANSCRIPT_SOURCES = frozenset({"youtube_auto", "whisper", "manual", "none"})
SLIDE_SOURCES = frozenset({"pptx", "pdf", "both", "video_extracted", "none"})
COMPLETED_STATUSES = frozenset({"processed", "processed_partial"})
RELATION_TYPES = frozenset({"duplicate", "borrowed_recording"})
REJECTABLE_SOURCE_TYPES = frozenset({"video", "slides"})
SOURCELESS_STATUSES = frozenset({"skipped_no_sources", "skipped_no_video"})

# These are intentionally a closed, documented set.  Tests exercise every
# class so callers can route fixes without parsing prose.
SLIDE_CONTRACT_CODES = frozenset(
    {
        "slide_source_unsupported",
        "slide_pptx_reference_missing",
        "slide_pptx_artifact_missing",
        "slide_pptx_artifact_unreadable",
        "slide_pptx_artifact_degraded",
        "slide_pdf_reference_missing",
        "slide_pdf_artifact_missing",
        "slide_pdf_artifact_unavailable",
        "slide_pdf_artifact_unreadable",
        "slide_video_reference_missing",
        "slide_video_artifact_missing",
        "slide_video_artifact_unavailable",
        "slide_video_artifact_unreadable",
    }
)
SOURCE_VIDEO_CONTRACT_CODES = frozenset(
    {
        "source_video_artifact_missing",
        "source_video_artifact_unavailable",
        "source_video_artifact_unreadable",
    }
)

_SOURCE_VIDEO_PROVENANCE_FAILURE_KINDS = frozenset(
    {"not_regular", "root_escape", "symlink_or_reparse"}
)

WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


def _vault_root_authority_finding(
    error: VaultRootAuthorityError,
) -> dict[str, Any]:
    """Build one closed, path-neutral authority finding."""
    actual: dict[str, object] = {"reason_code": error.reason_code}
    if error.locator_reason_code is not None:
        actual["locator_reason_code"] = error.locator_reason_code
    authorities = getattr(error, "authorities", ())
    if authorities:
        actual["authorities"] = list(authorities)
    if error.reason_code == "vault_root_authority_mismatch":
        field = (
            "cli.vault_root"
            if authorities == ("database_path", "cli_root")
            else "config.vault_storage_path"
        )
    else:
        field = {
            "vault_root_cli_invalid": "cli.vault_root",
            "vault_root_database_path_invalid": "database.path",
            "vault_root_config_invalid": "config.vault_storage_path",
        }[error.reason_code]
    return {
        "severity": "blocking",
        "code": error.reason_code,
        "talk_index": None,
        "filename": None,
        "field": field,
        "message": str(error),
        "expected": "one lexically identical native absolute vault root",
        "actual": actual,
        "artifact_path": None,
        "capability_fact": None,
    }


def _reportable_artifact_path(value: Path | str | None) -> str | None:
    """Return only a proved native absolute path; never cwd-rebase a locator."""
    if value is None:
        return None
    try:
        return os.fspath(materialize_artifact_locator(value))
    except ArtifactLocatorError:
        return None


def _nonempty_string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _raw_locator_string(value: Any) -> str | None:
    """Return a present locator unchanged so validation sees its raw grammar."""
    return value if isinstance(value, str) and value else None


def _is_timezone_aware_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _json_value(value: Any) -> Any:
    """Keep finding details JSON-safe without stringifying normal scalars."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else repr(value)
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [_json_value(item) for item in sorted(value, key=repr)]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return repr(value)


def _source_video_failure_code(error: VideoEvidenceError) -> str:
    """Map bounded-video failures without conflating bytes with provenance."""
    reason_code = error.reason_code
    failure_kind = error.details.get("failure_kind")
    if reason_code == "video_evidence_invalid" and isinstance(
        error.details.get("locator_failure"), str
    ):
        return "video_extraction_provenance_invalid"
    if reason_code == "video_artifact_unavailable":
        if failure_kind == "missing":
            return "source_video_artifact_missing"
        if failure_kind in _SOURCE_VIDEO_PROVENANCE_FAILURE_KINDS:
            return "video_extraction_provenance_invalid"
    if reason_code == "video_cloud_placeholder_unavailable":
        return "source_video_artifact_unavailable"
    return "source_video_artifact_unreadable"


class VaultPreflight:
    """Accumulate deterministic findings for one already-loaded database."""

    def __init__(self, database: Any, vault_root: Path, database_path: Path):
        self.database = database
        self.vault_root = Path(vault_root)
        self._artifact_root: Path | None = None
        self.database_path = Path(database_path)
        self.findings: list[dict[str, Any]] = []
        self.talks: list[dict[str, Any]] = []
        self.source_indexes: list[int] = []
        self.config: dict[str, Any] = {}
        self.filenames: dict[str, int] = {}
        self.youtube_ids: dict[int, str] = {}
        self.valid_relations: dict[int, tuple[str, str]] = {}
        self.event_aliases: set[EventAlias] = set()
        self.artifact_capabilities: dict[int, dict[str, object]] = {}
        self.video_evidence_assessment = VideoEvidenceAssessment()
        self.reported_source_video_failures: set[int] = set()
        self.reported_config_exclusions_invalid = False

    def artifact_root(self) -> Path:
        """Map the trusted configured root lazily, without probing CLI input."""
        if self._artifact_root is None:
            _artifact, admitted_root = canonicalize_trusted_artifact_locator(
                self.vault_root,
                self.vault_root,
            )
            self._artifact_root = admitted_root or self.vault_root
        return self._artifact_root

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
        capability_fact: Any = None,
    ) -> None:
        self.findings.append(
            {
                "severity": severity,
                "code": code,
                "talk_index": talk_index,
                "filename": filename,
                "field": field,
                "message": message,
                "expected": _json_value(expected),
                "actual": _json_value(actual),
                "artifact_path": _reportable_artifact_path(artifact_path),
                "capability_fact": _json_value(capability_fact),
            }
        )

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
        if (
            severity == "warning"
            and (
                "artifact" in code
                or "receipt" in code
                or "reference" in code
                or code.startswith("video_extraction_provenance_")
            )
            and "capability_fact" not in details
        ):
            details["capability_fact"] = self._capabilities(index)
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
                "blocking",
                "database_shape_invalid",
                "tracking database must be a JSON object",
                expected="object",
                actual=type(self.database).__name__,
            )
            return self.report(0)

        try:
            assessment = assess_tracking_database(self.database)
        except TrackingDatabaseError as exc:
            config = self.database.get("config")
            if not (
                isinstance(exc, TrackingDatabaseConfigExclusionsError)
                and isinstance(config, dict)
                and self._report_invalid_pptx_directory_exclusions(config)
            ):
                self.add(
                    "blocking",
                    "tracking_database_schema_invalid",
                    str(exc),
                    field="schema_version",
                )
        else:
            if not assessment.usable:
                reason_codes = list(assessment.reason_codes)
                field = "schema_version"
                expected: Any = assessment.as_dict()["accepted_schema_versions"]
                actual: Any = {
                    "root_schema_version": assessment.schema_version,
                    "reason_codes": reason_codes,
                }
                if {
                    "config_schema_version_missing",
                    "config_schema_version_unsupported",
                }.intersection(assessment.reason_codes):
                    config = self.database.get("config")
                    config_version = (
                        config.get("schema_version")
                        if isinstance(config, dict)
                        else None
                    )
                    field = "config.schema_version"
                    expected = [
                        LEGACY_CONFIG_RECORD_SCHEMA_VERSION,
                        CONFIG_RECORD_SCHEMA_VERSION,
                    ]
                    actual = {
                        "schema_version": config_version,
                        "reason_codes": reason_codes,
                    }
                self.add(
                    "blocking",
                    "tracking_database_schema_unsupported",
                    "tracking database is not usable by this reader",
                    field=field,
                    expected=expected,
                    actual=actual,
                )
                return self.report(0)

        config = self.database.get("config", {})
        try:
            self.vault_root = resolve_vault_root_authority(
                database_path=self.database_path,
                config=config,
                cli_vault_root=self.vault_root,
            )
        except VaultRootAuthorityError as exc:
            self._add_vault_root_authority_error(exc)
            return self.report(0)

        if isinstance(config, dict):
            self.config = config
            self._validate_config_artifact_roots()
        else:
            self.add(
                "warning",
                "config_shape_invalid",
                "config is not an object; config-backed checks were skipped",
                field="config",
                expected="object",
                actual=type(config).__name__,
            )

        talks = self.database.get("talks")
        if not isinstance(talks, list):
            self.add(
                "blocking",
                "talks_shape_invalid",
                "tracking database talks must be an array",
                field="talks",
                expected="array",
                actual=type(talks).__name__,
            )
            return self.report(0)

        for index, talk in enumerate(talks):
            if not isinstance(talk, dict):
                self.add(
                    "blocking",
                    "talk_shape_invalid",
                    "each talks entry must be an object",
                    talk_index=index,
                    expected="object",
                    actual=type(talk).__name__,
                )
                continue
            self.talks.append(talk)
            self.source_indexes.append(index)

        self.event_aliases = known_event_aliases(self.talks)

        # Valid-entry checks use compact internal indexes.  Findings map those
        # back to the original source-array indexes, even around malformed rows.
        self._validate_filenames()
        for index in range(len(self.talks)):
            self._validate_sources(index)
            self._validate_source_status_reachability(index)
            self._validate_source_rejections(index)
            self._validate_artifacts(index)
            self._validate_source_identity(index)
        self._validate_relations()
        self._validate_duplicate_youtube_ids()
        return self.report(len(talks))

    def _add_vault_root_authority_error(
        self,
        error: VaultRootAuthorityError,
    ) -> None:
        """Record one path-neutral authority failure before artifact checks."""
        self.findings.append(_vault_root_authority_finding(error))

    def _validate_config_artifact_roots(self) -> None:
        """Report each invalid configured source root once, even without talks."""
        self._report_invalid_pptx_directory_exclusions(self.config)
        if (
            "pptx_source_dir" not in self.config
            or self.config.get("pptx_source_dir") is None
        ):
            return
        try:
            materialize_native_root(self.config.get("pptx_source_dir"))
        except ArtifactLocatorError as exc:
            self.add(
                "blocking",
                "pptx_source_dir_invalid",
                "configured PPTX source root must be a native absolute path",
                field="config.pptx_source_dir",
                expected="absent, null, or a native absolute path",
                actual={"reason_code": exc.reason_code},
            )

    def _report_invalid_pptx_directory_exclusions(
        self,
        config: dict[str, Any],
    ) -> bool:
        """Report one typed exclusion fault and suppress generic schema noise."""
        message: str | None = None
        actual: Any = config.get("pptx_directory_exclusions")
        if (
            config.get("schema_version") == CONFIG_RECORD_SCHEMA_VERSION
            and "pptx_directory_exclusions" not in config
        ):
            message = (
                "current config must declare exact-component PPTX directory exclusions"
            )
            actual = {"state": "missing"}
        elif "pptx_directory_exclusions" in config:
            try:
                validate_pptx_directory_exclusions(
                    actual,
                    label="config.pptx_directory_exclusions",
                )
            except PptxDiscoveryContractError as exc:
                message = str(exc)
        if message is None:
            return False
        if not self.reported_config_exclusions_invalid:
            self.add(
                "blocking",
                "pptx_directory_exclusions_invalid",
                message,
                field="config.pptx_directory_exclusions",
                expected="bounded unique exact-component string array",
                actual=actual,
            )
            self.reported_config_exclusions_invalid = True
        return True

    def _validate_filenames(self) -> None:
        occurrences: defaultdict[str, list[int]] = defaultdict(list)
        for index, talk in enumerate(self.talks):
            value = talk.get("filename")
            filename = _nonempty_string(value)
            if filename is None:
                self.talk_add(
                    index,
                    "blocking",
                    "filename_missing",
                    "talk filename must be a nonempty string",
                    field="filename",
                    expected="nonempty string",
                    actual=value,
                )
                continue
            if value != filename:
                self.talk_add(
                    index,
                    "blocking",
                    "filename_not_normalized",
                    "talk filename must not have surrounding whitespace",
                    field="filename",
                    expected=filename,
                    actual=value,
                )
            occurrences[filename].append(index)
            self.filenames.setdefault(filename, index)

        for filename, indexes in sorted(occurrences.items()):
            if len(indexes) > 1:
                self.add(
                    "blocking",
                    "duplicate_filename",
                    "talk filenames must be unique",
                    filename=filename,
                    field="filename",
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
                index,
                "blocking",
                "transcript_source_unsupported",
                "transcript_source is outside the supported enum",
                field="transcript_source",
                expected=sorted(TRANSCRIPT_SOURCES),
                actual=transcript_source,
            )

        slide_source = talk.get("slide_source")
        if slide_source is not None and (
            not isinstance(slide_source, str) or slide_source not in SLIDE_SOURCES
        ):
            self.talk_add(
                index,
                "blocking",
                "slide_source_unsupported",
                "slide_source is outside the supported enum; transcript_only is "
                "represented by slide_source 'none'",
                field="slide_source",
                expected=sorted(SLIDE_SOURCES),
                actual=slide_source,
            )
        elif slide_source is None and self._needs_artifact_checks(talk):
            self.talk_add(
                index,
                "warning",
                "slide_source_missing",
                "processable or completed talk has no slide_source provenance",
                field="slide_source",
                expected=sorted(SLIDE_SOURCES),
                actual=None,
            )

        structured = talk.get("structured_data")
        if (
            isinstance(structured, dict)
            and "video_extraction" in structured
            and slide_source != "video_extracted"
        ):
            self.talk_add(
                index,
                "blocking",
                "video_extraction_slide_source_mismatch",
                "persisted video extraction provenance is outside its slide lane",
                field="structured_data.video_extraction",
                expected="present only when slide_source is 'video_extracted'",
                actual=slide_source,
            )

        video_url = talk.get("video_url")
        stored_id = talk.get("youtube_id")
        parsed_id = parse_youtube_id(video_url)
        youtube_url = is_youtube_url(video_url)

        valid_stored_id = None
        if stored_id is not None and stored_id != "":
            if not isinstance(stored_id, str) or not YOUTUBE_ID_RE.fullmatch(stored_id):
                self.talk_add(
                    index,
                    "blocking",
                    "youtube_id_invalid",
                    "stored youtube_id must be exactly 11 URL-safe characters",
                    field="youtube_id",
                    expected="11-character YouTube ID",
                    actual=stored_id,
                )
            else:
                valid_stored_id = stored_id

        if youtube_url and parsed_id is None:
            self.talk_add(
                index,
                "blocking",
                "youtube_url_invalid",
                "YouTube URL does not contain a valid ID in a supported URL form",
                field="video_url",
                expected="watch, youtu.be, shorts, or embed URL with an 11-character ID",
                actual=video_url,
            )
        elif parsed_id is not None and valid_stored_id is None:
            self.talk_add(
                index,
                "blocking",
                "youtube_id_missing",
                "YouTube URL has an ID but the stored youtube_id is missing or invalid",
                field="youtube_id",
                expected=parsed_id,
                actual=stored_id,
            )
        elif parsed_id is not None and valid_stored_id != parsed_id:
            self.talk_add(
                index,
                "blocking",
                "youtube_id_mismatch",
                "video_url and stored youtube_id identify different recordings",
                field="youtube_id",
                expected=parsed_id,
                actual=valid_stored_id,
            )

        identity_id = parsed_id or valid_stored_id
        if identity_id is not None:
            self.youtube_ids[index] = identity_id

    def _needs_artifact_checks(self, talk: dict[str, Any]) -> bool:
        transcript_source = talk.get("transcript_source")
        slide_source = talk.get("slide_source")
        return (
            talk.get("status") in COMPLETED_STATUSES
            or bool(source_capabilities(talk))
            or (
                isinstance(transcript_source, str)
                and transcript_source in TRANSCRIPT_SOURCES - {"none"}
            )
            or (
                isinstance(slide_source, str)
                and slide_source in SLIDE_SOURCES - {"none"}
            )
        )

    def _validate_source_status_reachability(self, index: int) -> None:
        """Reject skipped-source states that hide independent slide inputs."""
        talk = self.talks[index]
        status = talk.get("status")
        if status not in SOURCELESS_STATUSES:
            return

        sources = []
        if _nonempty_string(talk.get("pptx_path")):
            sources.append("pptx")
        if any(
            _nonempty_string(talk.get(field))
            for field in (
                "slides_url",
                "google_drive_id",
                "slides_local_path",
                "slides_pdf_path",
                "pdf_path",
            )
        ):
            sources.append("pdf")
        if not sources:
            return

        self.talk_add(
            index,
            "blocking",
            "status_source_reachability_conflict",
            "source-less skip status conflicts with an independent slide source",
            field="status",
            expected="a status that permits slide-only processing",
            actual={"status": status, "independent_sources": sorted(sources)},
        )

    def _validate_source_rejections(self, index: int) -> None:
        """Keep known-bad upstream links from returning during later scans."""
        talk = self.talks[index]
        if "source_rejections" not in talk:
            return
        rejections = talk.get("source_rejections")
        if not isinstance(rejections, list):
            self.talk_add(
                index,
                "blocking",
                "source_rejections_shape_invalid",
                "source_rejections must be an array",
                field="source_rejections",
                expected="array",
                actual=type(rejections).__name__,
            )
            return

        for position, rejection in enumerate(rejections):
            field = f"source_rejections[{position}]"
            if not isinstance(rejection, dict):
                self.talk_add(
                    index,
                    "blocking",
                    "source_rejection_invalid",
                    "each source rejection must be an object",
                    field=field,
                    expected="object",
                    actual=type(rejection).__name__,
                )
                continue
            source_type = rejection.get("source_type")
            url = _nonempty_string(rejection.get("url"))
            reason = _nonempty_string(rejection.get("reason"))
            evidence = _nonempty_string(rejection.get("evidence"))
            verified_at = _nonempty_string(rejection.get("verified_at"))
            valid_timestamp = False
            if verified_at:
                try:
                    parsed = datetime.fromisoformat(verified_at.replace("Z", "+00:00"))
                    valid_timestamp = parsed.tzinfo is not None
                except ValueError:
                    pass
            if (
                source_type not in REJECTABLE_SOURCE_TYPES
                or url is None
                or reason is None
                or evidence is None
                or not valid_timestamp
            ):
                self.talk_add(
                    index,
                    "blocking",
                    "source_rejection_invalid",
                    "source rejection requires video type, URL, reason, evidence, "
                    "and a timezone-aware verified_at timestamp",
                    field=field,
                    expected={
                        "source_type": sorted(REJECTABLE_SOURCE_TYPES),
                        "url": "...",
                        "reason": "...",
                        "evidence": "...",
                        "verified_at": "ISO-8601 with timezone",
                    },
                    actual=rejection,
                )
                continue

            active_field = "video_url" if source_type == "video" else "slides_url"
            active_url = _nonempty_string(talk.get(active_field))
            parser = (
                parse_youtube_id if source_type == "video" else parse_google_drive_id
            )
            active_id = parser(active_url) if active_url else None
            rejected_id = parser(url)
            same_source = active_url == url or (
                active_id is not None and rejected_id == active_id
            )
            if same_source:
                self.talk_add(
                    index,
                    "blocking",
                    "rejected_source_reactivated",
                    f"an active {active_field} is recorded as a known-bad source",
                    field=active_field,
                    expected="a source not in source_rejections",
                    actual=active_url,
                )

    def _is_current_artifact_generation(self, talk: dict[str, Any]) -> bool:
        observations = talk.get("pattern_observations")
        return (
            talk.get("status") in COMPLETED_STATUSES
            and talk.get("pattern_scoring_generation_status") == "current"
            and talk.get("pattern_scoring_generation_reasons") == []
            and talk.get("pattern_scoring_schema_version")
            == PATTERN_SCORING_SCHEMA_VERSION
            and isinstance(observations, dict)
            and observations.get("evidence_schema_version")
            == PATTERN_EVIDENCE_SCHEMA_VERSION
        )

    def _capabilities(self, index: int) -> dict[str, object]:
        cached = self.artifact_capabilities.get(index)
        if cached is not None:
            return cached
        configured_source = self.config.get("pptx_source_dir")
        source_roots = (
            {"pptx_source_dir": configured_source}
            if "pptx_source_dir" in self.config and configured_source is not None
            else None
        )
        assessed = assess_talk_artifact_capabilities(
            self.talks[index],
            vault_root=self.artifact_root(),
            source_roots=source_roots,
            video_evidence_assessment=self.video_evidence_assessment,
        )
        self.artifact_capabilities[index] = assessed
        return assessed

    def _artifact_severity(
        self, index: int, talk: dict[str, Any], *, declared: bool
    ) -> str:
        # Current v5 evidence is an integrity claim and remains fail-closed.
        if declared and self._is_current_artifact_generation(talk):
            return "blocking"
        # A legacy completed record is migration input, not current proof. If
        # another verified/repairable/remote lane can drive normalization and
        # reprocessing, report actionable work without deadlocking that repair.
        if talk.get("status") in COMPLETED_STATUSES:
            capabilities = self._capabilities(index)
            usable: set[object] = set()
            for field in (
                "verified_capabilities",
                "repair_capabilities",
                "acquisition_capabilities",
            ):
                values = capabilities.get(field)
                if isinstance(values, (tuple, list, set, frozenset)):
                    usable.update(values)
            if not usable:
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
            declared = isinstance(
                transcript_source, str
            ) and transcript_source in TRANSCRIPT_SOURCES - {"none"}
            severity = self._artifact_severity(index, talk, declared=declared)
            if transcript_path is None:
                self.talk_add(
                    index,
                    severity,
                    "transcript_reference_missing",
                    "expected transcript cannot be resolved without youtube_id or transcript_path",
                    field="youtube_id",
                    expected="youtube_id or transcript_path",
                    actual=talk.get("youtube_id"),
                )
            elif not transcript_path.is_file():
                self.talk_add(
                    index,
                    severity,
                    "transcript_artifact_missing",
                    "expected transcript file does not exist",
                    field="transcript_source",
                    actual=transcript_source,
                    artifact_path=transcript_path,
                )
            else:
                self._validate_transcript_quality(
                    index, talk, transcript_path, severity
                )

        slide_source = talk.get("slide_source")
        if (
            not isinstance(slide_source, str)
            or slide_source not in SLIDE_SOURCES
            or slide_source == "none"
        ):
            return
        severity = self._artifact_severity(index, talk, declared=True)

        def require_static_pdf_capability(
            *,
            code_prefix: str,
            field: str,
            artifact_path: Path | None,
        ) -> bool:
            capabilities = self._capabilities(index)
            raw_verified = capabilities.get("verified_evidence_sources")
            if (
                isinstance(raw_verified, (tuple, list, set, frozenset))
                and "static_slides" in raw_verified
            ):
                return True
            raw_unavailable = capabilities.get("unavailable_evidence_sources")
            unavailable = (
                raw_unavailable.get("static_slides")
                if isinstance(raw_unavailable, dict)
                else None
            )
            if code_prefix == "slide_video" and not isinstance(unavailable, dict):
                # A readable video-derived PDF is still withheld from verified
                # evidence until the separate crop/provenance validator runs.
                return True
            raw_reasons = capabilities.get("source_reasons")
            reason = (
                unavailable
                if isinstance(unavailable, dict)
                else (
                    raw_reasons.get("static_slides")
                    if isinstance(raw_reasons, dict)
                    else "PDF probe returned no static-slide capability"
                )
            )
            details = (
                unavailable.get("details") if isinstance(unavailable, dict) else None
            )
            failure_kind = (
                details.get("failure_kind") if isinstance(details, dict) else None
            )
            reason_code = (
                unavailable.get("reason_code")
                if isinstance(unavailable, dict)
                else None
            )
            if failure_kind == "missing":
                suffix = "missing"
                message = "declared slide PDF artifact does not exist"
            elif reason_code == "pdf_cloud_placeholder_unavailable":
                suffix = "unavailable"
                message = "declared slide PDF is not hydrated for local inspection"
            else:
                suffix = "unreadable"
                message = (
                    "declared slide PDF could not complete bounded evidence inspection"
                )
            self.talk_add(
                index,
                severity,
                f"{code_prefix}_artifact_{suffix}",
                message,
                field=field,
                actual=reason,
                artifact_path=artifact_path,
                capability_fact=capabilities,
            )
            return False

        if slide_source in {"pptx", "both"}:
            pptx_path = self._pptx_path(talk)
            if _raw_locator_string(talk.get("pptx_path")) is None:
                self.talk_add(
                    index,
                    severity,
                    "slide_pptx_reference_missing",
                    "slide_source requires a nonempty pptx_path",
                    field="pptx_path",
                    expected="PPTX path",
                    actual=talk.get("pptx_path"),
                )
            else:
                capabilities = self._capabilities(index)
                raw_degradations = capabilities.get("degraded_evidence_sources")
                degradation = (
                    raw_degradations.get("native_deck")
                    if isinstance(raw_degradations, dict)
                    else None
                )
                raw_verified = capabilities.get("verified_evidence_sources")
                native_verified = (
                    isinstance(raw_verified, (tuple, list, set, frozenset))
                    and "native_deck" in raw_verified
                )
                if isinstance(degradation, dict):
                    self.talk_add(
                        index,
                        severity,
                        "slide_pptx_artifact_degraded",
                        "declared PPTX required loss-reporting media recovery; "
                        "restore or re-export the deck before current analysis",
                        field="pptx_path",
                        actual=degradation,
                        artifact_path=pptx_path,
                        capability_fact=capabilities,
                    )
                elif not native_verified:
                    raw_unavailable = capabilities.get("unavailable_evidence_sources")
                    unavailable = (
                        raw_unavailable.get("native_deck")
                        if isinstance(raw_unavailable, dict)
                        else None
                    )
                    raw_reasons = capabilities.get("source_reasons")
                    reason = (
                        unavailable
                        if isinstance(unavailable, dict)
                        else (
                            raw_reasons.get("native_deck")
                            if isinstance(raw_reasons, dict)
                            else "PPTX parser returned no native-deck capability"
                        )
                    )
                    failure_kind = (
                        unavailable.get("details", {}).get("failure_kind")
                        if isinstance(unavailable, dict)
                        and isinstance(unavailable.get("details"), dict)
                        else None
                    )
                    code = (
                        "slide_pptx_artifact_missing"
                        if failure_kind == "missing"
                        else "slide_pptx_artifact_unreadable"
                    )
                    message = (
                        "declared PPTX artifact does not exist"
                        if failure_kind == "missing"
                        else "declared PPTX cannot be parsed or safely recovered"
                    )
                    self.talk_add(
                        index,
                        severity,
                        code,
                        message,
                        field="pptx_path",
                        actual=reason,
                        artifact_path=pptx_path,
                        capability_fact=capabilities,
                    )

        if slide_source in {"pdf", "both"}:
            explicit_field = self._slide_pdf_path_field(talk)
            explicit_locator = _raw_locator_string(talk.get(explicit_field))
            explicit_pdf = self._slide_pdf_path(talk)
            if explicit_locator is not None:
                require_static_pdf_capability(
                    code_prefix="slide_pdf",
                    field=explicit_field,
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
                    index,
                    severity,
                    "slide_pdf_reference_missing",
                    "slide_source requires a nonempty google_drive_id",
                    field="google_drive_id",
                    expected="Google Drive file ID",
                    actual=talk.get("google_drive_id"),
                )
            else:
                pdf_path = self.vault_root / "slides" / f"{drive_id}.pdf"
                require_static_pdf_capability(
                    code_prefix="slide_pdf",
                    field="google_drive_id",
                    artifact_path=pdf_path,
                )

        if slide_source == "video_extracted":
            explicit_field = self._slide_pdf_path_field(talk)
            explicit_locator = _raw_locator_string(talk.get(explicit_field))
            explicit_pdf = self._slide_pdf_path(talk)
            if explicit_locator is not None:
                if (
                    require_static_pdf_capability(
                        code_prefix="slide_video",
                        field=explicit_field,
                        artifact_path=explicit_pdf,
                    )
                    and explicit_pdf is not None
                ):
                    self._validate_video_extraction_provenance(
                        index,
                        explicit_pdf,
                        severity,
                        require_trusted=True,
                    )
                return
            youtube_id = self.youtube_ids.get(index)
            if youtube_id is None:
                self.talk_add(
                    index,
                    severity,
                    "slide_video_reference_missing",
                    "video_extracted source requires a valid YouTube identity",
                    field="youtube_id",
                    expected="valid YouTube ID",
                    actual=talk.get("youtube_id"),
                )
            else:
                pdf_path = self.vault_root / "slides" / f"{youtube_id}.pdf"
                if talk.get("status") == "processed_partial":
                    self._validate_video_extraction_provenance(
                        index,
                        None,
                        severity,
                        require_trusted=False,
                    )
                    return
                static_pdf_available = require_static_pdf_capability(
                    code_prefix="slide_video",
                    field="slide_source",
                    artifact_path=pdf_path,
                )
                promoted_pdf_available = False
                if static_pdf_available:
                    try:
                        probe_pdf_artifact(
                            pdf_path,
                            trusted_root=self.vault_root,
                        )
                    except PdfEvidenceError as exc:
                        failure_kind = exc.details.get("failure_kind")
                        promoted_pdf_missing = failure_kind == "missing"
                        if promoted_pdf_missing:
                            if talk.get("status") != "processed_partial":
                                self.talk_add(
                                    index,
                                    severity,
                                    "slide_video_artifact_missing",
                                    "processed video extraction has no promoted "
                                    "canonical slide PDF",
                                    field="slide_source",
                                    actual={
                                        "reason_code": exc.reason_code,
                                        "details": dict(exc.details),
                                    },
                                    artifact_path=pdf_path,
                                )
                        else:
                            suffix = (
                                "unavailable"
                                if exc.reason_code
                                == "pdf_cloud_placeholder_unavailable"
                                else "unreadable"
                            )
                            self.talk_add(
                                index,
                                severity,
                                f"slide_video_artifact_{suffix}",
                                "implicit promoted video-slide PDF failed its "
                                "bounded integrity probe",
                                field="slide_source",
                                actual={
                                    "reason_code": exc.reason_code,
                                    "details": dict(exc.details),
                                },
                                artifact_path=pdf_path,
                            )
                    else:
                        promoted_pdf_available = True
                if static_pdf_available and promoted_pdf_available:
                    self._validate_video_extraction_provenance(
                        index,
                        pdf_path,
                        severity,
                        require_trusted=True,
                    )
                elif static_pdf_available:
                    # A partial result may intentionally retain only a trusted
                    # unpromoted crop candidate or full-frame context. Validate
                    # its complete manifest and preserved artifacts, but do not
                    # invent a promoted authored deck.
                    self._validate_video_extraction_provenance(
                        index,
                        None,
                        severity,
                        require_trusted=False,
                    )

    def _transcript_path(self, talk: dict[str, Any]) -> Path | None:
        explicit = _raw_locator_string(talk.get("transcript_path"))
        if explicit:
            try:
                relative = validate_transcript_path(explicit)
                youtube_id = _nonempty_string(talk.get("youtube_id"))
                if (
                    youtube_id
                    and YOUTUBE_ID_RE.fullmatch(youtube_id)
                    and relative.as_posix() != f"transcripts/{youtube_id}.txt"
                ):
                    return None
                return materialize_artifact_locator(
                    relative.as_posix(),
                    trusted_root=self.vault_root,
                )
            except (ArtifactLocatorError, PatternEvidenceError):
                return None
        youtube_id = _nonempty_string(talk.get("youtube_id"))
        if youtube_id and YOUTUBE_ID_RE.fullmatch(youtube_id):
            return self.vault_root / "transcripts" / f"{youtube_id}.txt"
        return None

    def _validate_transcript_quality(
        self,
        index: int,
        talk: dict[str, Any],
        transcript_path: Path,
        severity: str,
    ) -> None:
        try:
            text = transcript_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            self.talk_add(
                index,
                severity,
                "transcript_artifact_unreadable",
                "transcript artifact cannot be decoded as UTF-8 speech text",
                artifact_path=transcript_path,
                actual=str(exc),
            )
            return
        valid, reason, receipt_reason, receipt_bound = (
            validate_transcript_quality_for_owner(
                transcript_path,
                text,
                talk,
                vault_root=self.artifact_root(),
                video_evidence_assessment=self.video_evidence_assessment,
            )
        )
        if valid:
            return
        if not receipt_bound:
            capabilities = self._capabilities(index)
            self.talk_add(
                index,
                severity,
                "transcript_quality_receipt_unverified",
                "current transcript evidence requires a hash-current full "
                "quality-policy and provenance receipt",
                artifact_path=transcript_path,
                actual={
                    "receipt_reason": receipt_reason,
                    "capabilities": capabilities,
                },
            )
            return
        if reason.startswith("receipt_owner_mismatch:"):
            self.talk_add(
                index,
                "blocking",
                "transcript_quality_provenance_mismatch",
                "transcript quality provenance is not bound to the current "
                "talk owner and exact source artifact",
                artifact_path=transcript_path,
                actual=reason.removeprefix("receipt_owner_mismatch: "),
            )
            return
        self.talk_add(
            index,
            severity,
            "transcript_artifact_quality_invalid",
            "transcript artifact fails its exact receipt-bound quality contract",
            artifact_path=transcript_path,
            actual=reason,
        )

    def _pptx_path(self, talk: dict[str, Any]) -> Path | None:
        value = _raw_locator_string(talk.get("pptx_path"))
        if value is None:
            return None
        configured_source = self.config.get("pptx_source_dir")
        try:
            trusted_root = (
                materialize_native_root(configured_source)
                if "pptx_source_dir" in self.config and configured_source is not None
                else self.vault_root
            )
            return materialize_artifact_locator(value, trusted_root=trusted_root)
        except ArtifactLocatorError:
            return None

    @staticmethod
    def _slide_pdf_path_field(talk: dict[str, Any]) -> str:
        """Return the first populated canonical-or-legacy local PDF field."""
        for field in ("slides_local_path", "slides_pdf_path", "pdf_path"):
            if _raw_locator_string(talk.get(field)):
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
        value = _raw_locator_string(talk.get(field))
        if value is None:
            return None
        try:
            return materialize_artifact_locator(
                value,
                trusted_root=self.vault_root,
            )
        except ArtifactLocatorError:
            return None

    def _validate_video_extraction_provenance(
        self,
        index: int,
        promoted_pdf: Path | None,
        severity: str,
        *,
        require_trusted: bool,
    ) -> None:
        """Validate schema-v3 provenance and any claimed authored-deck trust."""
        talk = self.talks[index]
        structured = talk.get("structured_data")
        extraction = (
            structured.get("video_extraction") if isinstance(structured, dict) else None
        )
        if not isinstance(extraction, dict):
            self.talk_add(
                index,
                severity,
                "video_extraction_provenance_missing",
                "video-extracted slides have no structured extraction manifest",
                field="structured_data.video_extraction",
                expected=f"schema {VIDEO_EXTRACTION_SCHEMA_VERSION} manifest",
                actual=extraction,
                artifact_path=promoted_pdf,
            )
            return

        try:
            state = validate_video_extraction_manifest({"video_extraction": extraction})
        except ReturnValidationError as exc:
            self.talk_add(
                index,
                "blocking",
                "video_extraction_provenance_invalid",
                "video extraction manifest violates the schema-v3 artifact contract",
                field="structured_data.video_extraction",
                expected="complete, internally consistent schema-v3 manifest",
                actual=str(exc),
                artifact_path=promoted_pdf,
            )
            return

        errors: list[str] = []
        trusted_slide_region_probe: PdfArtifactProbe | None = None
        expected_id = self.youtube_ids.get(index)
        if state.source_video_id != expected_id:
            errors.append("source_video_id must match the talk's YouTube identity")
        else:
            try:
                source_video_path = resolve_video_extraction_source(
                    self.artifact_root(),
                    extraction,
                    state.source_video_id,
                )
            except PatternEvidenceError:
                errors.append(
                    "source_video_path must name a root-confined, non-symlinked "
                    "preserved source video"
                )
            else:
                try:
                    self.video_evidence_assessment.probe(
                        source_video_path,
                        trusted_root=self.artifact_root(),
                    )
                except VideoEvidenceError as exc:
                    finding_code = _source_video_failure_code(exc)
                    failure = {
                        "reason_code": exc.reason_code,
                        "details": dict(exc.details),
                    }
                    if finding_code == "video_extraction_provenance_invalid":
                        closed_reason = exc.details.get("locator_failure")
                        if not isinstance(closed_reason, str):
                            closed_reason = exc.details.get("failure_kind")
                        if not isinstance(closed_reason, str):
                            closed_reason = exc.reason_code
                        errors.append(f"source_video_path: {closed_reason}")
                    elif index not in self.reported_source_video_failures:
                        self.reported_source_video_failures.add(index)
                        message = {
                            "source_video_artifact_missing": (
                                "preserved source video artifact does not exist"
                            ),
                            "source_video_artifact_unavailable": (
                                "preserved source video is not hydrated for local "
                                "inspection"
                            ),
                            "source_video_artifact_unreadable": (
                                "preserved source video could not complete bounded "
                                "evidence inspection"
                            ),
                        }[finding_code]
                        self.talk_add(
                            index,
                            severity,
                            finding_code,
                            message,
                            field=(
                                "structured_data.video_extraction.source_video_path"
                            ),
                            actual=failure,
                            artifact_path=source_video_path,
                            capability_fact=self._capabilities(index),
                        )

        artifacts = extraction.get("artifacts")
        # Shared schema validation proved this is a list of artifact objects.
        assert isinstance(artifacts, list)
        for artifact in artifacts:
            assert isinstance(artifact, dict)
            artifact_path = _raw_locator_string(artifact.get("path"))
            if artifact_path is None:
                errors.append("every artifact path must exist")
                continue
            try:
                materialized_artifact = materialize_artifact_locator(
                    artifact_path,
                    trusted_root=self.vault_root,
                )
            except ArtifactLocatorError:
                errors.append(
                    "every artifact path must be a native absolute or canonical "
                    "vault-relative locator"
                )
                continue
            try:
                artifact_probe = probe_pdf_artifact(
                    materialized_artifact,
                    trusted_root=self.vault_root,
                )
            except PdfEvidenceError as exc:
                errors.append(
                    "every artifact PDF must pass the bounded integrity probe "
                    f"({exc.reason_code})"
                )
                continue
            if artifact_probe.page_count != artifact.get("page_count"):
                errors.append(
                    "every artifact page_count must match the bounded PDF probe"
                )
            if artifact.get("artifact_scope") == "slide_region":
                trusted_slide_region_probe = artifact_probe
        if (
            promoted_pdf is not None
            and state.trusted_slide_region
            and trusted_slide_region_probe is not None
        ):
            try:
                promoted_probe = probe_pdf_artifact(
                    promoted_pdf,
                    trusted_root=self.vault_root,
                )
            except PdfEvidenceError as exc:
                errors.append(
                    "the promoted slide PDF must pass the bounded integrity probe "
                    f"({exc.reason_code})"
                )
            else:
                if promoted_probe.page_count != trusted_slide_region_probe.page_count:
                    errors.append(
                        "the promoted slide PDF page count must match the trusted "
                        "slide_region artifact"
                    )
                if (
                    promoted_probe.source_sha256
                    != trusted_slide_region_probe.source_sha256
                ):
                    errors.append(
                        "the promoted slide PDF digest must match the trusted "
                        "slide_region artifact"
                    )
        if errors:
            self.talk_add(
                index,
                "blocking",
                "video_extraction_provenance_invalid",
                "video extraction manifest is structurally or referentially invalid",
                field="structured_data.video_extraction",
                expected="complete schema-v3 manifest with existing source/artifacts",
                actual=errors,
                artifact_path=promoted_pdf,
            )
            return
        if require_trusted and not state.trusted_slide_region:
            self.talk_add(
                index,
                "blocking",
                "video_extraction_untrusted",
                "video frames have not passed verified manual crop review",
                field="structured_data.video_extraction.review_required",
                expected=False,
                actual=extraction.get("review_required"),
                artifact_path=promoted_pdf,
            )

    def _validate_source_identity(self, index: int) -> None:
        talk = self.talks[index]
        if "source_identity" not in talk:
            return  # The v1 evidence block is optional for legacy records.
        evidence = talk.get("source_identity")
        if not isinstance(evidence, dict):
            self.talk_add(
                index,
                "blocking",
                "source_identity_shape_invalid",
                "source_identity must be an object",
                field="source_identity",
                expected="object",
                actual=type(evidence).__name__,
            )
            return

        schema_version = evidence.get("schema_version")
        if schema_version is None:
            self.talk_add(
                index,
                "warning",
                "source_identity_schema_missing",
                "source_identity has no schema_version; validating known fields",
                field="source_identity.schema_version",
                expected=SOURCE_IDENTITY_SCHEMA_VERSION,
                actual=None,
            )
        elif (
            type(schema_version) is not int
            or schema_version != SOURCE_IDENTITY_SCHEMA_VERSION
        ):
            self.talk_add(
                index,
                "warning",
                "source_identity_schema_unsupported",
                "source_identity schema version is not the version this preflight owns; "
                "validating known fields only",
                field="source_identity.schema_version",
                expected=SOURCE_IDENTITY_SCHEMA_VERSION,
                actual=schema_version,
            )

        provider = evidence.get("provider")
        if provider is not None and provider != "youtube":
            self.talk_add(
                index,
                "warning",
                "source_identity_provider_unknown",
                "source_identity provider is not currently understood",
                field="source_identity.provider",
                expected="youtube",
                actual=provider,
            )

        evidence_id = evidence.get("video_id")
        expected_id = self.youtube_ids.get(index)
        if evidence_id is None:
            self._identity_gap(index, "video_id")
        elif not isinstance(evidence_id, str) or not YOUTUBE_ID_RE.fullmatch(
            evidence_id
        ):
            self.talk_add(
                index,
                "blocking",
                "source_identity_video_id_invalid",
                "source_identity video_id must be an 11-character YouTube ID",
                field="source_identity.video_id",
                expected="11-character YouTube ID",
                actual=evidence_id,
            )
        elif expected_id is not None and evidence_id != expected_id:
            self.talk_add(
                index,
                "blocking",
                "source_identity_video_id_mismatch",
                "recorded identity evidence names a different video",
                field="source_identity.video_id",
                expected=expected_id,
                actual=evidence_id,
            )

        self._validate_identity_provider_facts(
            index,
            evidence,
            evidence_id,
            expected_id,
        )
        self._validate_identity_title(index, evidence)
        self._validate_identity_speakers(index, evidence)
        self._validate_identity_dates(index, evidence)
        self._validate_identity_duration(index, evidence)

    def _validate_identity_provider_facts(
        self,
        index: int,
        evidence: dict[str, Any],
        evidence_id: Any,
        expected_id: str | None,
    ) -> None:
        for field in ("uploader", "uploader_id"):
            value = evidence.get(field)
            if value is not None and _nonempty_string(value) is None:
                self.talk_add(
                    index,
                    "blocking",
                    "source_identity_provider_fact_invalid",
                    f"source_identity {field} must be a nonempty string when present",
                    field=f"source_identity.{field}",
                    expected="nonempty string",
                    actual=value,
                )

        anchor_id = (
            evidence_id
            if isinstance(evidence_id, str) and YOUTUBE_ID_RE.fullmatch(evidence_id)
            else expected_id
        )
        webpage_url = evidence.get("webpage_url")
        webpage_url_id: str | None = None
        if webpage_url is not None:
            webpage_url_id = parse_youtube_id(webpage_url)
            if webpage_url_id is None:
                self.talk_add(
                    index,
                    "blocking",
                    "source_identity_webpage_url_invalid",
                    "source_identity webpage_url must be a supported YouTube URL",
                    field="source_identity.webpage_url",
                    expected="YouTube URL with an 11-character video ID",
                    actual=webpage_url,
                )
            elif anchor_id is not None and webpage_url_id != anchor_id:
                self.talk_add(
                    index,
                    "blocking",
                    "source_identity_webpage_identity_mismatch",
                    "captured webpage URL identifies a different video",
                    field="source_identity.webpage_url",
                    expected=anchor_id,
                    actual=webpage_url_id,
                )

        webpage_video_id = evidence.get("webpage_video_id")
        if webpage_video_id is not None:
            if not isinstance(webpage_video_id, str) or not YOUTUBE_ID_RE.fullmatch(
                webpage_video_id
            ):
                self.talk_add(
                    index,
                    "blocking",
                    "source_identity_webpage_video_id_invalid",
                    "source_identity webpage_video_id must be an 11-character YouTube ID",
                    field="source_identity.webpage_video_id",
                    expected="11-character YouTube ID",
                    actual=webpage_video_id,
                )
            else:
                comparison_id = anchor_id or webpage_url_id
                if comparison_id is not None and webpage_video_id != comparison_id:
                    self.talk_add(
                        index,
                        "blocking",
                        "source_identity_webpage_identity_mismatch",
                        "captured webpage ID identifies a different video",
                        field="source_identity.webpage_video_id",
                        expected=comparison_id,
                        actual=webpage_video_id,
                    )

        captured_at = evidence.get("captured_at")
        if captured_at is not None and not _is_timezone_aware_timestamp(captured_at):
            self.talk_add(
                index,
                "blocking",
                "source_identity_captured_at_invalid",
                "source_identity captured_at must be a timezone-aware ISO-8601 timestamp",
                field="source_identity.captured_at",
                expected="ISO-8601 timestamp with timezone",
                actual=captured_at,
            )

    def _identity_gap(self, index: int, field: str) -> None:
        self.talk_add(
            index,
            "warning",
            f"source_identity_{field}_missing",
            f"source_identity has no {field} evidence",
            field=f"source_identity.{field}",
            expected=f"recorded {field} evidence",
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
                index,
                "blocking",
                "source_identity_title_invalid",
                "source_identity title must be a nonempty string",
                field="source_identity.title",
                expected="nonempty title",
                actual=observed,
            )
            return
        expected_title = _nonempty_string(expected)
        if expected_title is None:
            self.talk_add(
                index,
                "warning",
                "source_identity_title_uncheckable",
                "talk has no title to compare with recorded title evidence",
                field="title",
                expected="talk title",
                actual=expected,
            )
            return
        if not titles_agree(expected_title, observed_title):
            self.talk_add(
                index,
                "blocking",
                "source_identity_title_mismatch",
                "recorded video title does not materially overlap the catalog title",
                field="source_identity.title",
                expected=expected_title,
                actual=observed_title,
            )
        event_agrees, catalog_event, provider_events = event_agreement(
            self.talks[index].get("conference"),
            observed_title,
            self.event_aliases,
        )
        if event_agrees is False:
            self.talk_add(
                index,
                "blocking",
                "source_identity_event_mismatch",
                "recorded video title explicitly names a different catalog event",
                field="source_identity.title",
                expected={
                    "conference": self.talks[index].get("conference"),
                    "event_alias": " ".join(catalog_event or ()),
                },
                actual={
                    "title": observed_title,
                    "event_aliases": [" ".join(alias) for alias in provider_events],
                },
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
                index,
                "blocking",
                "source_identity_speakers_invalid",
                "source_identity speakers must be a nonempty array of nonempty names",
                field="source_identity.speakers",
                expected="nonempty string array",
                actual=observed,
            )
            return

        expected = expected_speakers(self.talks[index], self.config)
        if not expected:
            self.talk_add(
                index,
                "warning",
                "source_identity_speakers_uncheckable",
                "catalog and config have no expected speaker name",
                field="speaker",
                expected="catalog or config speaker",
                actual=None,
            )
            return
        if not any(names_agree(left, right) for left in expected for right in observed):
            self.talk_add(
                index,
                "blocking",
                "source_identity_speaker_mismatch",
                "recorded speaker evidence does not name an expected speaker",
                field="source_identity.speakers",
                expected=expected,
                actual=observed,
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
                index,
                "warning",
                "source_identity_date_uncheckable",
                "catalog date is absent or not YYYY/ISO-8601; source dates cannot be compared",
                field="date",
                expected="YYYY or YYYY-MM-DD",
                actual=self.talks[index].get("date"),
            )
            return

        catalog_day, catalog_year = talk_date
        if recorded is not None:
            if recorded.year != catalog_year:
                self.talk_add(
                    index,
                    "blocking",
                    "source_identity_recorded_year_mismatch",
                    "recorded date and catalog date are in different years",
                    field="source_identity.recorded_date",
                    expected=catalog_year,
                    actual=recorded.isoformat(),
                )
            elif catalog_day is not None and recorded != catalog_day:
                self.talk_add(
                    index,
                    "warning",
                    "source_identity_recorded_date_differs",
                    "recorded date differs from the catalog day within the same year",
                    field="source_identity.recorded_date",
                    expected=catalog_day.isoformat(),
                    actual=recorded.isoformat(),
                )
        if upload is not None:
            predates = (
                upload < catalog_day
                if catalog_day is not None
                else upload.year < catalog_year
            )
            if predates:
                self.talk_add(
                    index,
                    "blocking",
                    "source_identity_upload_predates_talk",
                    "recorded upload date predates the cataloged delivery",
                    field="source_identity.upload_date",
                    expected=(
                        catalog_day.isoformat() if catalog_day else f">={catalog_year}"
                    ),
                    actual=upload.isoformat(),
                )

    def _parse_evidence_date(
        self,
        index: int,
        field: str,
        value: Any,
    ) -> date | None:
        if value is None:
            return None
        if not isinstance(value, str):
            self.talk_add(
                index,
                "blocking",
                "source_identity_date_invalid",
                f"source_identity {field} must be an ISO-8601 calendar date",
                field=f"source_identity.{field}",
                expected="YYYY-MM-DD",
                actual=value,
            )
            return None
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            self.talk_add(
                index,
                "blocking",
                "source_identity_date_invalid",
                f"source_identity {field} must be an ISO-8601 calendar date",
                field=f"source_identity.{field}",
                expected="YYYY-MM-DD",
                actual=value,
            )
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            self.talk_add(
                index,
                "blocking",
                "source_identity_date_invalid",
                f"source_identity {field} must be an ISO-8601 calendar date",
                field=f"source_identity.{field}",
                expected="YYYY-MM-DD",
                actual=value,
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
                index,
                "blocking",
                "source_identity_duration_invalid",
                "source_identity duration_seconds must be a positive number",
                field="source_identity.duration_seconds",
                expected="positive seconds",
                actual=observed,
            )
            return

        expected = expected_duration_seconds(self.talks[index])
        if expected is None:
            return
        tolerance = max(60.0, expected * 0.05)
        if abs(float(observed) - expected) > tolerance:
            self.talk_add(
                index,
                "blocking",
                "source_identity_duration_mismatch",
                "recorded duration differs from catalog duration beyond 60 seconds or 5%",
                field="source_identity.duration_seconds",
                expected=expected,
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
                    index,
                    "blocking",
                    "source_relation_invalid",
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
                    index,
                    "blocking",
                    "source_relation_invalid",
                    "source relation target must name another catalog record",
                    field="source_relation.target_filename",
                    expected="another existing filename",
                    actual=target,
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
                        index,
                        "blocking",
                        "source_relation_identity_mismatch",
                        "duplicate/borrowed relation target must carry the same YouTube identity",
                        field="source_relation.target_filename",
                        expected=source_id,
                        actual=target_id,
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
                _nonempty_string(self.talks[index].get("filename")) or f"talk[{index}]"
                for index in indexes
            ]
            self.add(
                "blocking",
                "duplicate_youtube_id",
                "YouTube ID is used by multiple talks without an explicit "
                "duplicate/borrowed-recording relation",
                field="youtube_id",
                expected="one canonical record plus explicit relations",
                actual={"youtube_id": video_id, "filenames": filenames},
            )

    def report(self, talk_count: int) -> dict[str, Any]:
        severity_order = {"blocking": 0, "warning": 1}
        self.findings.sort(
            key=lambda finding: (
                severity_order.get(finding["severity"], 9),
                finding["filename"] or "",
                finding["talk_index"] if finding["talk_index"] is not None else -1,
                finding["code"],
                finding["message"],
            )
        )
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
        candidates.extend(
            [
                structured.get("video_duration_seconds"),
                structured.get("recording_duration_seconds"),
                structured.get("duration_seconds"),
            ]
        )
    for value in candidates:
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)) and math.isfinite(value) and value > 0:
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


def _is_direct_database_locator(value: object) -> bool:
    """Recognize the raw final basename without materializing or probing it."""
    if not isinstance(value, (str, os.PathLike)):
        return False
    try:
        raw = os.fspath(value)
    except TypeError:
        return False
    if not isinstance(raw, str):
        return False
    final_separator = max(raw.rfind("/"), raw.rfind("\\"))
    return raw[final_separator + 1 :].casefold() == "tracking-database.json"


def resolve_input(value: str | Path) -> tuple[Path, Path]:
    """Bind a vault root to its canonical database without filesystem probes.

    Only a case-insensitive ``tracking-database.json`` basename is a direct
    database locator; every other value is the vault root.
    """
    is_database = _is_direct_database_locator(value)
    path = materialize_native_authority(
        value,
        authority="database_path" if is_database else "cli_root",
    )
    if not is_database:
        return path, path / "tracking-database.json"
    return path.parent, path


def error_report(
    vault_root: Path, database_path: Path, code: str, message: str
) -> dict[str, Any]:
    validator = VaultPreflight({}, vault_root, database_path)
    validator.add("blocking", code, message)
    return validator.report(0)


def vault_root_authority_error_report(
    error: VaultRootAuthorityError,
) -> dict[str, Any]:
    """Return one path-neutral report when no input root was admitted."""
    finding = _vault_root_authority_finding(error)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "ok": False,
        "database": None,
        "vault_root": None,
        "talk_count": 0,
        "blocking_count": 1,
        "warning_count": 0,
        "summary": {
            "by_severity": {"blocking": 1, "warning": 0},
            "by_code": {error.reason_code: 1},
        },
        "findings": [finding],
    }


def run_preflight(value: str | Path) -> dict[str, Any]:
    """Load and validate a vault, returning a report without mutating it."""
    try:
        vault_root, database_path = resolve_input(value)
    except VaultRootAuthorityError as exc:
        return vault_root_authority_error_report(exc)
    try:
        snapshot = snapshot_tracking_database(database_path)
        database = decode_json_object(snapshot)
    except TrackingDatabaseIOError as exc:
        message = str(exc)
        if "not valid UTF-8" in message:
            code = "database_encoding_invalid"
        elif (
            "not valid JSON" in message
            or "duplicate object key" in message
            or ("non-standard JSON number" in message)
            or "root must be a JSON object" in message
        ):
            code = "database_json_invalid"
        else:
            code = "database_unreadable"
        return error_report(
            vault_root,
            database_path,
            code,
            message,
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
                Path.cwd(),
                Path.cwd() / "tracking-database.json",
                "invalid_arguments",
                "expected one vault directory or database path",
            )
            print(json.dumps(report, indent=2, sort_keys=True))
        raise

    report = run_preflight(args.vault_or_database)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["blocking_count"] == 0 else 1


def run_cli() -> int:
    """Run the CLI behind its failure boundary. Returns the process exit code.

    Importable so the boundary's contract is testable without executing the
    module as a script.
    """
    try:
        return main()
    # Callers read a non-zero exit without report JSON as a silent preflight
    # failure and may proceed to claim work; emit one closed report because
    # propagation would suppress the machine-readable blocking signal that gates
    # claiming.
    except Exception as exc:  # noqa: BLE001 - outer-boundary-process-contract
        print(
            json.dumps(
                {
                    "schema_version": REPORT_SCHEMA_VERSION,
                    "ok": False,
                    # Present on every normal report; a consumer reading them
                    # unconditionally must not KeyError on the failure shape.
                    "database": None,
                    "vault_root": None,
                    "talk_count": 0,
                    "blocking_count": 1,
                    "warning_count": 0,
                    "summary": {
                        "by_severity": {"blocking": 1, "warning": 0},
                        "by_code": {"preflight_unexpected_failure": 1},
                    },
                    "findings": [
                        {
                            "severity": "blocking",
                            "code": "preflight_unexpected_failure",
                            "talk_index": None,
                            "filename": None,
                            "field": None,
                            "message": (
                                "preflight aborted before completing its checks; "
                                "its findings are unknown, so no talk may be "
                                "claimed"
                            ),
                            "expected": None,
                            "actual": type(exc).__name__,
                            "artifact_path": None,
                            "capability_fact": None,
                        }
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        print(
            "vault-ingress preflight failed unexpectedly; treat the vault as "
            "unverified and do not begin claiming. Rerun after repairing the "
            "condition named by the exception type above",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(run_cli())
