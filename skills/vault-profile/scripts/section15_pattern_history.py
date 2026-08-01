#!/usr/bin/env python3
"""Validate and atomically replace Section 15 pattern-history provenance.

The human narrative in ``rhetoric-style-summary.md`` is never a machine
baseline.  This module recognizes only one versioned, uniquely delimited JSON
block inside Markdown Section 15.  The block carries a complete
``pattern_profile`` plus redundant generation/cohort identity.  The shared
``profile_pattern_provenance`` assessor remains the authority for the payload.

Usage:
    section15_pattern_history.py assess <rhetoric-style-summary.md>
    section15_pattern_history.py replace <rhetoric-style-summary.md> \
        <pattern-profile-or-speaker-profile.json> <tracking-database.json>

``assess`` writes a status object to stdout and exits 0 only for a current
contract (including the explicit empty-cohort form). ``replace`` validates the
complete candidate before touching the summary, replaces only the delimited
block with ``os.replace``, and writes a result object to stdout. Argument errors
exit 2; file, JSON, contract, or write failures exit 1.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import stat
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


INGRESS_SCRIPTS = Path(__file__).resolve().parents[2] / "vault-ingress" / "scripts"
if str(INGRESS_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(INGRESS_SCRIPTS))

from profile_pattern_provenance import (  # noqa: E402
    REASON_INVALID_CONTRACT,
    PatternProfileAssessment,
    assess_pattern_profile,
)
from adherence_baseline import (  # noqa: E402
    AdherenceBaselineError,
    EvidenceFreshnessAssessor,
)
from pattern_cohort_snapshot import (  # noqa: E402
    PatternCohortSnapshotError,
    build_current_pattern_snapshot,
    configured_evidence_freshness_assessor,
)
from pattern_opportunities import PatternOpportunityError  # noqa: E402
from return_validation import (  # noqa: E402
    ReturnValidationError,
)
from tracking_database import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    TrackingDatabaseError,
    assess_tracking_database,
)
# Pyright cannot resolve this sibling script module added to sys.path at runtime.
from tracking_database_io import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    TrackingDatabaseIOError,
    decode_json_object,
    snapshot_tracking_database,
)


BLOCK_SCHEMA_VERSION = 2
BLOCK_SOURCE_LANE = "current_pattern_history"
BLOCK_TOKEN = "speaker-toolkit:section15-current-pattern-history:v2"
BLOCK_START = f"<!-- {BLOCK_TOKEN}:start -->"
BLOCK_END = f"<!-- {BLOCK_TOKEN}:end -->"
NON_BASELINE_NOTICE = (
    "_All other Section 15 prose is historical narrative and non-baseline; "
    "it cannot authorize catalog-derived claims._"
)

REASON_BLOCK_MISSING = "section15_current_block_missing"
REASON_BLOCK_INVALID = "section15_current_block_invalid"
REASON_BLOCK_DUPLICATE = "section15_current_block_duplicate"

_SECTION_15_HEADING = re.compile(
    r"^##[ \t]+15\.[^\r\n]*(?=\r?$)",
    re.MULTILINE,
)
_NEXT_H2_HEADING = re.compile(r"^##[ \t]+", re.MULTILINE)
_BLOCK_BODY = re.compile(
    re.escape(BLOCK_START)
    + r"\n```json\n(?P<payload>.*?)\n```\n\n"
    + re.escape(NON_BASELINE_NOTICE)
    + r"\n"
    + re.escape(BLOCK_END),
    re.DOTALL,
)
_REQUIRED_BLOCK_FIELDS = frozenset(
    {
        "schema_version",
        "source_lane",
        "pattern_catalog_fingerprint",
        "pattern_scoring_schema_version",
        "baseline_talk_filenames",
        "pattern_profile",
    }
)


class Section15PatternHistoryError(ValueError):
    """Raised when a Section 15 block cannot be safely read or replaced."""


class _DuplicateJsonKeyError(ValueError):
    """Raised by the strict JSON loader for any duplicate object key."""


class _InvalidJsonConstantError(ValueError):
    """Raised when Python's JSON extension accepts a non-JSON number."""


@dataclass(frozen=True)
class Section15PatternHistoryAssessment:
    """Fail-closed assessment of the sole machine-readable Section 15 block."""

    current_contract: bool
    catalog_fields_available: bool
    scored_talk_count: int | None
    eligible_talk_count: int | None
    reason_codes: tuple[str, ...]
    errors: tuple[str, ...]
    pattern_profile: dict[str, object] | None
    classification_fields_available: bool = False

    def as_status_dict(self) -> dict[str, object]:
        """Return status without echoing the potentially large history payload."""
        return {
            "current_contract": self.current_contract,
            "catalog_fields_available": self.catalog_fields_available,
            "classification_fields_available": (self.classification_fields_available),
            "scored_talk_count": self.scored_talk_count,
            "eligible_talk_count": self.eligible_talk_count,
            "reason_codes": self.reason_codes,
            "errors": self.errors,
        }


@dataclass(frozen=True)
class Section15WriteResult:
    """Result of one validated atomic block replacement."""

    path: str
    changed: bool
    scored_talk_count: int
    eligible_talk_count: int
    catalog_fields_available: bool

    def as_dict(self) -> dict[str, object]:
        """Return a stable JSON-serializable result."""
        return asdict(self)


def _dedupe(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _invalid_assessment(
    reason_code: str,
    *errors: str,
) -> Section15PatternHistoryAssessment:
    return Section15PatternHistoryAssessment(
        current_contract=False,
        catalog_fields_available=False,
        scored_talk_count=None,
        eligible_talk_count=None,
        reason_codes=(reason_code,),
        errors=tuple(errors),
        pattern_profile=None,
    )


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKeyError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise _InvalidJsonConstantError(f"non-finite JSON number {value!r}")


def _strict_json_loads(value: str) -> object:
    return json.loads(
        value,
        object_pairs_hook=_strict_object,
        parse_constant=_reject_json_constant,
    )


def _section_15_bounds(summary: str) -> tuple[re.Match[str], int] | None:
    headings = list(_SECTION_15_HEADING.finditer(summary))
    if len(headings) != 1:
        return None
    heading = headings[0]
    next_heading = _NEXT_H2_HEADING.search(summary, heading.end())
    section_end = next_heading.start() if next_heading is not None else len(summary)
    return heading, section_end


def _extract_payload_text(
    summary: str,
) -> tuple[str | None, Section15PatternHistoryAssessment | None]:
    section = _section_15_bounds(summary)
    if section is None:
        return None, _invalid_assessment(
            REASON_BLOCK_INVALID,
            "rhetoric summary must contain exactly one Markdown H2 Section 15",
        )
    heading, section_end = section

    start_count = summary.count(BLOCK_START)
    end_count = summary.count(BLOCK_END)
    token_count = summary.count(BLOCK_TOKEN)
    if start_count == 0 and end_count == 0:
        if token_count:
            return None, _invalid_assessment(
                REASON_BLOCK_INVALID,
                "Section 15 current-block marker is torn or malformed",
            )
        return None, _invalid_assessment(
            REASON_BLOCK_MISSING,
            "Section 15 has no machine-readable current pattern-history block",
        )
    if start_count > 1 or end_count > 1:
        return None, _invalid_assessment(
            REASON_BLOCK_DUPLICATE,
            "Section 15 must contain exactly one current pattern-history block",
        )
    if start_count != 1 or end_count != 1 or token_count != 2:
        return None, _invalid_assessment(
            REASON_BLOCK_INVALID,
            "Section 15 current-block markers are incomplete or malformed",
        )

    start = summary.index(BLOCK_START)
    end_marker_start = summary.index(BLOCK_END)
    end = end_marker_start + len(BLOCK_END)
    if start < heading.end() or end > section_end or end_marker_start <= start:
        return None, _invalid_assessment(
            REASON_BLOCK_INVALID,
            "the current pattern-history block must be wholly inside Section 15",
        )

    block = summary[start:end].replace("\r\n", "\n")
    match = _BLOCK_BODY.fullmatch(block)
    if match is None:
        return None, _invalid_assessment(
            REASON_BLOCK_INVALID,
            "Section 15 current block has a torn fence, marker, or notice",
        )
    return match.group("payload"), None


def _assess_payload(payload: object) -> Section15PatternHistoryAssessment:
    if not isinstance(payload, Mapping):
        return _invalid_assessment(
            REASON_BLOCK_INVALID,
            "Section 15 current-block JSON must be an object",
        )

    errors: list[str] = []
    fields = set(payload)
    missing = sorted(_REQUIRED_BLOCK_FIELDS - fields)
    unknown = sorted(fields - _REQUIRED_BLOCK_FIELDS, key=str)
    if missing:
        errors.append(
            "Section 15 current block is missing required fields: " + ", ".join(missing)
        )
    if unknown:
        errors.append(
            "Section 15 current block has unknown fields: "
            + ", ".join(str(field) for field in unknown)
        )
    if payload.get("schema_version") != BLOCK_SCHEMA_VERSION or isinstance(
        payload.get("schema_version"), bool
    ):
        errors.append(
            f"Section 15 current block schema_version must be {BLOCK_SCHEMA_VERSION}"
        )
    if payload.get("source_lane") != BLOCK_SOURCE_LANE:
        errors.append(
            f"Section 15 current block source_lane must be {BLOCK_SOURCE_LANE!r}"
        )

    raw_pattern_profile = payload.get("pattern_profile")
    profile_assessment: PatternProfileAssessment = assess_pattern_profile(
        raw_pattern_profile
    )
    errors.extend(profile_assessment.errors)

    baseline: Mapping[str, object] | None = None
    if isinstance(raw_pattern_profile, Mapping):
        raw_baseline = raw_pattern_profile.get("pattern_baseline")
        if isinstance(raw_baseline, Mapping):
            baseline = raw_baseline

    if baseline is None:
        errors.append("Section 15 pattern_profile.pattern_baseline must be an object")
    else:
        if payload.get("pattern_catalog_fingerprint") != baseline.get(
            "pattern_catalog_fingerprint"
        ):
            errors.append(
                "Section 15 top-level pattern_catalog_fingerprint must equal "
                "pattern_profile.pattern_baseline.pattern_catalog_fingerprint"
            )
        if payload.get("pattern_scoring_schema_version") != baseline.get(
            "pattern_scoring_schema_version"
        ):
            errors.append(
                "Section 15 top-level pattern_scoring_schema_version must equal "
                "pattern_profile.pattern_baseline.pattern_scoring_schema_version"
            )

    if not isinstance(raw_pattern_profile, Mapping):
        errors.append("Section 15 pattern_profile must be an object")
    elif payload.get("baseline_talk_filenames") != raw_pattern_profile.get(
        "baseline_talk_filenames"
    ):
        errors.append(
            "Section 15 top-level baseline_talk_filenames must equal "
            "pattern_profile.baseline_talk_filenames"
        )

    reason_codes = list(profile_assessment.reason_codes)
    if errors:
        reason_codes.append(REASON_INVALID_CONTRACT)
        return Section15PatternHistoryAssessment(
            current_contract=False,
            catalog_fields_available=False,
            scored_talk_count=profile_assessment.scored_talk_count,
            eligible_talk_count=profile_assessment.eligible_talk_count,
            reason_codes=_dedupe(reason_codes),
            errors=_dedupe(errors),
            pattern_profile=None,
            classification_fields_available=False,
        )

    assert isinstance(raw_pattern_profile, Mapping)
    canonical_profile = copy.deepcopy(dict(raw_pattern_profile))
    return Section15PatternHistoryAssessment(
        current_contract=profile_assessment.current_contract,
        catalog_fields_available=profile_assessment.catalog_fields_available,
        scored_talk_count=profile_assessment.scored_talk_count,
        eligible_talk_count=profile_assessment.eligible_talk_count,
        reason_codes=profile_assessment.reason_codes,
        errors=profile_assessment.errors,
        pattern_profile=canonical_profile,
        classification_fields_available=(
            profile_assessment.classification_fields_available
        ),
    )


def assess_section15_pattern_history(
    summary: str,
) -> Section15PatternHistoryAssessment:
    """Assess only the uniquely delimited Section 15 current block."""
    payload_text, structural_error = _extract_payload_text(summary)
    if structural_error is not None:
        return structural_error
    assert payload_text is not None
    try:
        payload = _strict_json_loads(payload_text)
    except (
        json.JSONDecodeError,
        _DuplicateJsonKeyError,
        _InvalidJsonConstantError,
    ) as exc:
        return _invalid_assessment(
            REASON_BLOCK_INVALID,
            f"Section 15 current-block JSON is invalid: {exc}",
        )
    return _assess_payload(payload)


def render_section15_current_block(pattern_profile: object) -> str:
    """Render a canonical block from a complete shared-assessor payload."""
    assessment = assess_pattern_profile(pattern_profile)
    if not assessment.current_contract:
        details = "; ".join(assessment.errors or assessment.reason_codes)
        raise Section15PatternHistoryError(
            "pattern_profile is not a current complete contract: " + details
        )
    if not isinstance(pattern_profile, Mapping):
        raise Section15PatternHistoryError("pattern_profile must be an object")

    canonical_profile = copy.deepcopy(dict(pattern_profile))
    baseline = canonical_profile.get("pattern_baseline")
    filenames = canonical_profile.get("baseline_talk_filenames")
    assert isinstance(baseline, Mapping)  # shared-assessor postcondition
    assert isinstance(filenames, list)  # shared-assessor postcondition
    payload = {
        "schema_version": BLOCK_SCHEMA_VERSION,
        "source_lane": BLOCK_SOURCE_LANE,
        "pattern_catalog_fingerprint": baseline["pattern_catalog_fingerprint"],
        "pattern_scoring_schema_version": baseline["pattern_scoring_schema_version"],
        "baseline_talk_filenames": filenames,
        "pattern_profile": canonical_profile,
    }
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise Section15PatternHistoryError(
            f"pattern_profile cannot be encoded as canonical JSON: {exc}"
        ) from exc
    return (
        f"{BLOCK_START}\n```json\n{encoded}\n```\n\n{NON_BASELINE_NOTICE}\n{BLOCK_END}"
    )


def _replace_block_text(summary: str, rendered_block: str) -> str:
    section = _section_15_bounds(summary)
    if section is None:
        raise Section15PatternHistoryError(
            "rhetoric summary must contain exactly one Markdown H2 Section 15"
        )
    heading, section_end = section

    start_count = summary.count(BLOCK_START)
    end_count = summary.count(BLOCK_END)
    token_count = summary.count(BLOCK_TOKEN)
    if start_count == 0 and end_count == 0 and token_count == 0:
        newline = "\r\n" if "\r\n" in summary else "\n"
        rendered = rendered_block.replace("\n", newline)
        suffix = summary[heading.end() :]
        after_block = "" if suffix.startswith(newline + newline) else newline
        return (
            summary[: heading.end()]
            + newline
            + newline
            + rendered
            + after_block
            + suffix
        )
    if start_count > 1 or end_count > 1:
        raise Section15PatternHistoryError(
            "Section 15 has duplicate current-block markers; repair it before "
            "replacement"
        )
    if start_count != 1 or end_count != 1 or token_count != 2:
        raise Section15PatternHistoryError(
            "Section 15 current-block markers are torn or malformed; repair them "
            "before replacement"
        )

    start = summary.index(BLOCK_START)
    end_marker_start = summary.index(BLOCK_END)
    end = end_marker_start + len(BLOCK_END)
    if start < heading.end() or end > section_end or end_marker_start <= start:
        raise Section15PatternHistoryError(
            "the sole current-block markers must be ordered wholly inside Section 15"
        )
    newline = "\r\n" if "\r\n" in summary[start:end] else "\n"
    rendered = rendered_block.replace("\n", newline)
    return summary[:start] + rendered + summary[end:]


def replace_section15_current_block(
    summary_path: Path,
    pattern_profile: object,
    tracking_database: object,
    *,
    evidence_freshness_assessor: EvidenceFreshnessAssessor,
) -> Section15WriteResult:
    """Validate a complete candidate, then atomically replace only its block."""
    if not isinstance(pattern_profile, Mapping):
        raise Section15PatternHistoryError("pattern_profile must be an object")
    canonical_input = copy.deepcopy(dict(pattern_profile))
    rendered = render_section15_current_block(pattern_profile)
    _validate_complete_tracking_cohort(
        canonical_input,
        tracking_database,
        evidence_freshness_assessor=evidence_freshness_assessor,
    )
    try:
        original_bytes = summary_path.read_bytes()
        original = original_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise Section15PatternHistoryError(
            f"cannot read UTF-8 rhetoric summary at {summary_path}: {exc}"
        ) from exc

    candidate = _replace_block_text(original, rendered)
    candidate_assessment = assess_section15_pattern_history(candidate)
    if not candidate_assessment.current_contract:
        details = "; ".join(
            candidate_assessment.errors or candidate_assessment.reason_codes
        )
        raise Section15PatternHistoryError(
            "rendered Section 15 candidate failed validation: " + details
        )
    if candidate_assessment.pattern_profile != canonical_input:
        raise Section15PatternHistoryError(
            "rendered Section 15 candidate does not round-trip the full pattern_profile"
        )

    count = candidate_assessment.scored_talk_count
    eligible_count = candidate_assessment.eligible_talk_count
    assert isinstance(count, int)  # shared-assessor postcondition
    assert isinstance(eligible_count, int)  # shared-assessor postcondition
    if candidate == original:
        return Section15WriteResult(
            path=str(summary_path),
            changed=False,
            scored_talk_count=count,
            eligible_talk_count=eligible_count,
            catalog_fields_available=(candidate_assessment.catalog_fields_available),
        )

    mode = stat.S_IMODE(summary_path.stat().st_mode)
    temporary_path: Path | None = None
    file_descriptor: int | None = None
    try:
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{summary_path.name}.",
            suffix=".tmp",
            dir=summary_path.parent,
        )
        temporary_path = Path(temporary_name)
        os.fchmod(file_descriptor, mode)
        handle = os.fdopen(file_descriptor, "wb")
        file_descriptor = None
        with handle:
            handle.write(candidate.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, summary_path)
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass

    return Section15WriteResult(
        path=str(summary_path),
        changed=True,
        scored_talk_count=count,
        eligible_talk_count=eligible_count,
        catalog_fields_available=candidate_assessment.catalog_fields_available,
    )


def _load_json(path: Path) -> object:
    try:
        return _strict_json_loads(path.read_text(encoding="utf-8"))
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        _DuplicateJsonKeyError,
        _InvalidJsonConstantError,
    ) as exc:
        raise Section15PatternHistoryError(
            f"cannot load strict JSON from {path}: {exc}"
        ) from exc


def _require_usable_tracking_database(tracking_database: object) -> None:
    """Reject malformed or unreadable owner generations before config semantics."""
    if not isinstance(tracking_database, Mapping):
        raise Section15PatternHistoryError("tracking database must be a JSON object")
    try:
        assessment = assess_tracking_database(tracking_database)
    except TrackingDatabaseError as exc:
        raise Section15PatternHistoryError(
            f"tracking database schema is invalid: {exc}"
        ) from exc
    if not assessment.usable:
        raise Section15PatternHistoryError(
            "tracking database has no usable prior state for this reader: "
            + ", ".join(assessment.reason_codes)
        )


def _load_tracking_database(path: Path) -> dict[str, Any]:
    try:
        snapshot = snapshot_tracking_database(path)
        tracking_database = decode_json_object(snapshot)
    except TrackingDatabaseIOError as exc:
        raise Section15PatternHistoryError(
            f"cannot load strict tracking database from {path}: {exc}"
        ) from exc
    _require_usable_tracking_database(tracking_database)
    return tracking_database


def _pattern_profile_candidate(value: object) -> object:
    if isinstance(value, Mapping) and "pattern_profile" in value:
        return value["pattern_profile"]
    return value


def _validate_complete_tracking_cohort(
    pattern_profile: Mapping[str, object],
    tracking_database: object,
    *,
    evidence_freshness_assessor: EvidenceFreshnessAssessor,
) -> None:
    """Bind a write candidate to the complete live scoring cohort."""
    _require_usable_tracking_database(tracking_database)
    assert isinstance(tracking_database, Mapping)
    talks = tracking_database.get("talks")
    if not isinstance(talks, list):
        raise Section15PatternHistoryError(
            "tracking database must contain a talks array"
        )
    baseline = pattern_profile.get("pattern_baseline")
    filenames = pattern_profile.get("baseline_talk_filenames")
    if not isinstance(baseline, Mapping) or not isinstance(filenames, list):
        raise Section15PatternHistoryError(
            "pattern_profile lacks its validated baseline/cohort identity"
        )
    try:
        snapshot = build_current_pattern_snapshot(
            talks,
            as_of=baseline.get("as_of"),
            evidence_freshness_assessor=evidence_freshness_assessor,
        )
    except (
        AdherenceBaselineError,
        PatternCohortSnapshotError,
        PatternOpportunityError,
        ReturnValidationError,
    ) as exc:
        raise Section15PatternHistoryError(
            f"cannot verify the complete tracking-database cohort: {exc}"
        ) from exc
    expected_baseline = snapshot["pattern_baseline"]
    expected_filenames = snapshot["baseline_talk_filenames"]
    expected_opportunities = snapshot["pattern_opportunities"]
    if dict(baseline) != expected_baseline:
        raise Section15PatternHistoryError(
            "pattern_profile.pattern_baseline does not equal the complete "
            "tracking-database scoring cohort"
        )
    if filenames != expected_filenames:
        raise Section15PatternHistoryError(
            "pattern_profile.baseline_talk_filenames does not equal the complete "
            "tracking-database scoring cohort"
        )
    if (
        pattern_profile.get("eligible_talk_count")
        != expected_opportunities["eligible_cohort_count"]
    ):
        raise Section15PatternHistoryError(
            "pattern_profile.eligible_talk_count does not equal the complete "
            "tracking-database scoring-v5 occurrence cohort"
        )
    if pattern_profile.get("pattern_usage") != expected_opportunities["pattern_usage"]:
        raise Section15PatternHistoryError(
            "pattern_profile.pattern_usage does not equal deterministic rows "
            "recomputed from the complete tracking-database scoring cohort"
        )
    if (
        pattern_profile.get("antipattern_frequency")
        != expected_opportunities["antipattern_frequency"]
    ):
        raise Section15PatternHistoryError(
            "pattern_profile.antipattern_frequency does not equal deterministic "
            "rows recomputed from the complete tracking-database scoring cohort"
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    assess_parser = subparsers.add_parser("assess")
    assess_parser.add_argument("summary", type=Path)
    replace_parser = subparsers.add_parser("replace")
    replace_parser.add_argument("summary", type=Path)
    replace_parser.add_argument("pattern_profile", type=Path)
    replace_parser.add_argument("tracking_database", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "assess":
            summary = args.summary.read_text(encoding="utf-8")
            assessment = assess_section15_pattern_history(summary)
            print(json.dumps(assessment.as_status_dict(), sort_keys=True))
            return 0 if assessment.current_contract else 1

        candidate = _pattern_profile_candidate(_load_json(args.pattern_profile))
        tracking_database = _load_tracking_database(args.tracking_database)
        result = replace_section15_current_block(
            args.summary,
            candidate,
            tracking_database,
            evidence_freshness_assessor=configured_evidence_freshness_assessor(
                args.tracking_database.expanduser().resolve().parent,
                (
                    tracking_database.get("config")
                    if isinstance(tracking_database, Mapping)
                    else None
                ),
            ),
        )
        print(json.dumps(result.as_dict(), sort_keys=True))
        return 0
    except (OSError, UnicodeDecodeError, Section15PatternHistoryError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
