#!/usr/bin/env python3
"""Validate and atomically replace Section 15 pattern-history provenance.

The human narrative in ``rhetoric-style-summary.md`` is never a machine
baseline. Exactly one uniquely delimited current block may exist inside
Markdown Section 15. The payload it binds carries a complete
``pattern_profile`` plus redundant generation/cohort identity. The shared
``profile_pattern_provenance`` assessor remains the authority for the payload.

This module owns the payload's state artifact,
``rhetoric-pattern-history.json`` (``SIDECAR_NAME``), which sits beside the
summary in the vault root:

- Schema: one JSON object with exactly ``schema_version`` (3),
  ``source_lane`` (``current_pattern_history``),
  ``pattern_catalog_fingerprint``, ``pattern_scoring_schema_version``,
  ``baseline_talk_filenames`` and ``pattern_profile`` (speaker-profile
  schema-v5 ``pattern_profile``), canonically encoded: sorted keys, two-space
  indent, UTF-8, one trailing newline.
- Binding: Section 15's current block is a short stub naming the sidecar and
  the sha256 of its exact bytes. ``render_section15_stub`` owns that shape.
- Writer: ``replace`` alone. Under the summary writer lock it installs the
  sidecar, then the summary, each by atomic rename after rechecking that the
  summary still holds the bytes it read. A crash between the two renames
  leaves either an older inline block that still reads, or a stub whose
  sha256 no longer matches the sidecar; ``assess`` refuses the latter until
  ``replace`` runs again.
- Readers: ``assess`` / ``assess_section15_pattern_history`` follow the stub,
  refuse a missing sidecar or one whose bytes do not hash to the stub's
  sha256, then validate the payload. Other components read pattern history
  through these functions or after ``assess`` exits 0.
- Legacy: an inline JSON block inside Section 15 (occurrence-only v2 or
  policy-bound v3) still reads; only ``replace`` migrates it, by writing the
  sidecar and swapping the inline block for the stub.

Usage:
    section15_pattern_history.py assess <rhetoric-style-summary.md>
    section15_pattern_history.py replace <rhetoric-style-summary.md> \
        <pattern-profile-or-speaker-profile.json> <tracking-database.json>

``assess`` writes a status object to stdout and exits 0 only for a current
contract (including the explicit empty-cohort form). ``replace`` validates the
complete candidate before touching either file, replaces only the delimited
block, and writes a result object to stdout. Argument errors exit 2; file,
JSON, contract, or write failures exit 1.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from collections.abc import Mapping
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


# A sibling skill shares this skill directory's naming under Tessl and ACR alike.
_SKILL = Path(__file__).resolve().parents[1]
INGRESS_SCRIPTS = (
    _SKILL.with_name(_SKILL.name.replace("vault-profile", "vault-ingress")) / "scripts"
)
if str(INGRESS_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(INGRESS_SCRIPTS))

from profile_pattern_provenance import (  # noqa: E402
    REASON_INVALID_CONTRACT,
    PatternProfileAssessment,
    assess_pattern_profile,
)

# Pyright cannot resolve this sibling script module added to sys.path at runtime.
from adherence_baseline import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    AdherenceBaselineError,
    EvidenceFreshnessAssessor,
)
from pattern_cohort_snapshot import (  # noqa: E402
    PatternCohortSnapshotError,
    build_current_pattern_snapshot,
    configured_evidence_freshness_assessor,
)
from pattern_opportunities import PatternOpportunityError  # noqa: E402
from pattern_classification_runtime import (  # noqa: E402
    classify_pattern_profile,
    resolve_classification_policy,
    validate_policy_stamp,
)

# Pyright cannot resolve this sibling script module added to sys.path at runtime.
from cooperative_lock import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    CooperativeLockError,
)

# Pyright cannot resolve this sibling script module added to sys.path at runtime.
from return_validation import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    ReturnValidationError,
)

# Pyright cannot resolve this sibling script module added to sys.path at runtime.
from summary_lock import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    rhetoric_summary_lock,
)

# Pyright cannot resolve this sibling script module added to sys.path at runtime.
from tracking_database import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    TrackingDatabaseError,
    assess_tracking_database,
    local_audio_declarations,
)

# Pyright cannot resolve this sibling script module added to sys.path at runtime.
from tracking_database_io import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    DATABASE_READ_DIAGNOSTICS,
    DATABASE_READ_FALLBACK,
    TrackingDatabaseIOError,
    decode_json_object,
    snapshot_tracking_database,
)

# Pyright cannot resolve this sibling script module added to sys.path at runtime.
from vault_root_authority import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    VaultRootAuthorityError,
    materialize_native_authority,
    resolve_vault_root_authority,
)


LEGACY_BLOCK_SCHEMA_VERSION = 2
BLOCK_SCHEMA_VERSION = 3
BLOCK_SOURCE_LANE = "current_pattern_history"
SIDECAR_NAME = "rhetoric-pattern-history.json"
# Read-only legacy forms: the JSON payload inline in Section 15.
LEGACY_BLOCK_TOKEN = "speaker-toolkit:section15-current-pattern-history:v2"
INLINE_BLOCK_TOKEN = "speaker-toolkit:section15-current-pattern-history:v3"
LEGACY_BLOCK_START = f"<!-- {LEGACY_BLOCK_TOKEN}:start -->"
LEGACY_BLOCK_END = f"<!-- {LEGACY_BLOCK_TOKEN}:end -->"
INLINE_BLOCK_START = f"<!-- {INLINE_BLOCK_TOKEN}:start -->"
INLINE_BLOCK_END = f"<!-- {INLINE_BLOCK_TOKEN}:end -->"
# The written form: a stub binding the sidecar's v3 payload by sha256.
STUB_TOKEN = "speaker-toolkit:section15-pattern-history-sidecar:v3"
STUB_START = f"<!-- {STUB_TOKEN}:start -->"
STUB_END = f"<!-- {STUB_TOKEN}:end -->"
NON_BASELINE_NOTICE = (
    "_All other Section 15 prose is historical narrative and non-baseline; "
    "it cannot authorize catalog-derived claims._"
)
_STUB_BEFORE_DIGEST = (
    f"Machine-readable current pattern history lives in `{SIDECAR_NAME}` "
    "beside this file (sha256 `"
)
_STUB_AFTER_DIGEST = "`); only `section15_pattern_history.py replace` writes it."

REASON_BLOCK_MISSING = "section15_current_block_missing"
REASON_BLOCK_INVALID = "section15_current_block_invalid"
REASON_BLOCK_DUPLICATE = "section15_current_block_duplicate"

_SECTION_15_HEADING = re.compile(
    r"^##[ \t]+15\.[^\r\n]*(?=\r?$)",
    re.MULTILINE,
)
_NEXT_H2_HEADING = re.compile(r"^##[ \t]+", re.MULTILINE)
# token -> (payload schema_version, start marker, end marker)
_BLOCK_MARKERS = {
    LEGACY_BLOCK_TOKEN: (
        LEGACY_BLOCK_SCHEMA_VERSION,
        LEGACY_BLOCK_START,
        LEGACY_BLOCK_END,
    ),
    INLINE_BLOCK_TOKEN: (BLOCK_SCHEMA_VERSION, INLINE_BLOCK_START, INLINE_BLOCK_END),
    STUB_TOKEN: (BLOCK_SCHEMA_VERSION, STUB_START, STUB_END),
}


def _block_body_pattern(start: str, end: str) -> re.Pattern[str]:
    return re.compile(
        re.escape(start)
        + r"\n```json\n(?P<payload>.*?)\n```\n\n"
        + re.escape(NON_BASELINE_NOTICE)
        + r"\n"
        + re.escape(end),
        re.DOTALL,
    )


_STUB_PATTERN = re.compile(
    re.escape(STUB_START + "\n" + _STUB_BEFORE_DIGEST)
    + r"(?P<sha256>[0-9a-f]{64})"
    + re.escape(_STUB_AFTER_DIGEST + "\n\n" + NON_BASELINE_NOTICE + "\n" + STUB_END)
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


class _BlockLocationError(Section15PatternHistoryError):
    """Raised when Section 15 holds no unambiguous place for the current block."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


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
    available_classification_domains: frozenset[str] = frozenset()
    block_schema_version: int | None = None
    policy_semantic_sha256: str | None = None

    def as_status_dict(self) -> dict[str, object]:
        """Return status without echoing the potentially large history payload."""
        return {
            "current_contract": self.current_contract,
            "catalog_fields_available": self.catalog_fields_available,
            "classification_fields_available": (self.classification_fields_available),
            "available_classification_domains": sorted(
                self.available_classification_domains
            ),
            "block_schema_version": self.block_schema_version,
            "policy_semantic_sha256": self.policy_semantic_sha256,
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


def _locate_block(summary: str) -> tuple[str | None, int, int]:
    """Return ``(token, start, end)`` of the sole current block in Section 15.

    A ``None`` token means Section 15 holds no current block; ``start == end``
    then marks the end of the Section 15 heading, where ``replace`` inserts one.
    """
    section = _section_15_bounds(summary)
    if section is None:
        raise _BlockLocationError(
            REASON_BLOCK_INVALID,
            "rhetoric summary must contain exactly one Markdown H2 Section 15",
        )
    heading, section_end = section

    marker_counts = {
        token: (
            summary.count(token),
            summary.count(start),
            summary.count(end),
        )
        for token, (_version, start, end) in _BLOCK_MARKERS.items()
    }
    if all(counts == (0, 0, 0) for counts in marker_counts.values()):
        return None, heading.end(), heading.end()
    if (
        sum(counts[1] for counts in marker_counts.values()) > 1
        or sum(counts[2] for counts in marker_counts.values()) > 1
    ):
        raise _BlockLocationError(
            REASON_BLOCK_DUPLICATE,
            "Section 15 must contain exactly one current pattern-history block; "
            "remove the duplicate markers",
        )
    valid_tokens = [
        token for token, counts in marker_counts.items() if counts == (2, 1, 1)
    ]
    if len(valid_tokens) != 1 or any(
        counts != (0, 0, 0) and counts != (2, 1, 1) for counts in marker_counts.values()
    ):
        raise _BlockLocationError(
            REASON_BLOCK_INVALID,
            "Section 15 current-block markers are mixed, torn, or malformed; "
            "repair them so exactly one start/end pair remains",
        )
    token = valid_tokens[0]
    _, block_start, block_end = _BLOCK_MARKERS[token]
    start = summary.index(block_start)
    end_marker_start = summary.index(block_end)
    end = end_marker_start + len(block_end)
    if start < heading.end() or end > section_end or end_marker_start <= start:
        raise _BlockLocationError(
            REASON_BLOCK_INVALID,
            "the current pattern-history block markers must be ordered wholly "
            "inside Section 15",
        )
    return token, start, end


def _sidecar_path(summary_path: Path) -> Path:
    return summary_path.with_name(SIDECAR_NAME)


def _payload_text(
    summary: str,
    sidecar: bytes | None,
) -> tuple[str, int] | Section15PatternHistoryAssessment:
    """Return the bound payload text and its schema version, or a refusal."""
    try:
        token, start, end = _locate_block(summary)
    except _BlockLocationError as exc:
        return _invalid_assessment(exc.reason_code, str(exc))
    if token is None:
        return _invalid_assessment(
            REASON_BLOCK_MISSING,
            "Section 15 has no machine-readable current pattern-history block",
        )
    block_version, block_start, block_end = _BLOCK_MARKERS[token]
    block = summary[start:end].replace("\r\n", "\n")
    if token != STUB_TOKEN:
        inline = _block_body_pattern(block_start, block_end).fullmatch(block)
        if inline is None:
            return _invalid_assessment(
                REASON_BLOCK_INVALID,
                "Section 15 current block has a torn fence, marker, or notice",
            )
        return inline.group("payload"), block_version

    stub = _STUB_PATTERN.fullmatch(block)
    if stub is None:
        return _invalid_assessment(
            REASON_BLOCK_INVALID,
            "Section 15 pattern-history stub is torn or malformed; rerun "
            "`section15_pattern_history.py replace` to rewrite it",
        )
    if sidecar is None:
        return _invalid_assessment(
            REASON_BLOCK_INVALID,
            f"{SIDECAR_NAME} is missing beside the rhetoric summary; rerun "
            "`section15_pattern_history.py replace` to rewrite it",
        )
    if hashlib.sha256(sidecar).hexdigest() != stub.group("sha256"):
        return _invalid_assessment(
            REASON_BLOCK_INVALID,
            f"{SIDECAR_NAME} does not match the sha256 Section 15 binds; it "
            "changed outside `section15_pattern_history.py replace` or a "
            "replace was interrupted. Rerun the replace to rewrite both files",
        )
    try:
        return sidecar.decode("utf-8"), block_version
    except UnicodeDecodeError as exc:
        return _invalid_assessment(
            REASON_BLOCK_INVALID,
            f"{SIDECAR_NAME} is not UTF-8: {exc}",
        )


def _assess_payload(
    payload: object, *, block_schema_version: int
) -> Section15PatternHistoryAssessment:
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
    if payload.get("schema_version") != block_schema_version or isinstance(
        payload.get("schema_version"), bool
    ):
        errors.append(
            "Section 15 current block schema_version must match its marker "
            f"version {block_schema_version}"
        )
    if payload.get("source_lane") != BLOCK_SOURCE_LANE:
        errors.append(
            f"Section 15 current block source_lane must be {BLOCK_SOURCE_LANE!r}"
        )

    raw_pattern_profile = payload.get("pattern_profile")
    profile_assessment: PatternProfileAssessment = assess_pattern_profile(
        raw_pattern_profile,
        expected_contract_version=(
            4 if block_schema_version == LEGACY_BLOCK_SCHEMA_VERSION else 5
        ),
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
            block_schema_version=block_schema_version,
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
        available_classification_domains=(
            profile_assessment.available_classification_domains
        ),
        block_schema_version=block_schema_version,
        policy_semantic_sha256=profile_assessment.policy_semantic_sha256,
    )


def _assess_summary(
    summary: str,
    sidecar: bytes | None,
) -> Section15PatternHistoryAssessment:
    """Assess Section 15's current block against the given sidecar bytes."""
    located = _payload_text(summary, sidecar)
    if isinstance(located, Section15PatternHistoryAssessment):
        return located
    payload_text, block_schema_version = located
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
    return _assess_payload(payload, block_schema_version=block_schema_version)


def assess_section15_pattern_history(
    summary_path: Path,
) -> Section15PatternHistoryAssessment:
    """Assess the summary's current block, following its stub to the sidecar.

    Raises ``OSError`` or ``UnicodeDecodeError`` when the summary, or a
    sidecar that exists, cannot be read; every contract failure is a
    fail-closed assessment instead.
    """
    summary = summary_path.read_text(encoding="utf-8")
    try:
        sidecar = _sidecar_path(summary_path).read_bytes()
    except FileNotFoundError:
        sidecar = None
    return _assess_summary(summary, sidecar)


def render_pattern_history_sidecar(pattern_profile: object) -> bytes:
    """Render canonical sidecar bytes from a complete shared-assessor payload."""
    assessment = assess_pattern_profile(pattern_profile, expected_contract_version=5)
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
    return (encoded + "\n").encode("utf-8")


def render_section15_stub(sidecar: bytes) -> str:
    """Render the Section 15 stub that binds ``sidecar`` by its sha256."""
    digest = hashlib.sha256(sidecar).hexdigest()
    return (
        f"{STUB_START}\n{_STUB_BEFORE_DIGEST}{digest}{_STUB_AFTER_DIGEST}\n\n"
        f"{NON_BASELINE_NOTICE}\n{STUB_END}"
    )


def _replace_block_text(summary: str, rendered_block: str) -> str:
    token, start, end = _locate_block(summary)
    if token is None:
        newline = "\r\n" if "\r\n" in summary else "\n"
        rendered = rendered_block.replace("\n", newline)
        suffix = summary[start:]
        after_block = "" if suffix.startswith(newline + newline) else newline
        return summary[:start] + newline + newline + rendered + after_block + suffix
    newline = "\r\n" if "\r\n" in summary[start:end] else "\n"
    rendered = rendered_block.replace("\n", newline)
    return summary[:start] + rendered + summary[end:]


def replace_section15_current_block(
    summary_path: Path,
    pattern_profile: object,
    tracking_database: object,
    *,
    evidence_freshness_assessor: EvidenceFreshnessAssessor,
    classification_policy_stamp: object | None = None,
) -> Section15WriteResult:
    """Validate a complete candidate, then atomically install sidecar and stub."""
    if not isinstance(pattern_profile, Mapping):
        raise Section15PatternHistoryError("pattern_profile must be an object")
    canonical_input = copy.deepcopy(dict(pattern_profile))
    sidecar = render_pattern_history_sidecar(pattern_profile)
    _validate_complete_tracking_cohort(
        canonical_input,
        tracking_database,
        evidence_freshness_assessor=evidence_freshness_assessor,
        classification_policy_stamp=classification_policy_stamp,
    )
    # The status-block writer replaces its own delimited block in this same
    # file. Two writers that read, splice, and rename without excluding each
    # other drop whichever update renamed first, so both take the summary's
    # shared writer lock for their whole read-splice-install section. The
    # sidecar is written only here, under the same lock.
    stack = ExitStack()
    try:
        lock = stack.enter_context(rhetoric_summary_lock(summary_path))
    except CooperativeLockError as exc:
        raise Section15PatternHistoryError(
            f"cannot take the rhetoric summary writer lock for {summary_path}: {exc}"
        ) from exc
    # An unlock or close that failed is recorded on the lock rather than
    # raised — the guarded write already happened. Dropping those warnings
    # would leave incomplete lock cleanup with no diagnostic naming it.
    try:
        return _replace_under_summary_lock(
            summary_path,
            stack,
            sidecar=sidecar,
            canonical_input=canonical_input,
        )
    finally:
        for warning in lock.warnings:
            print(f"WARNING: {warning}", file=sys.stderr)


def _replace_under_summary_lock(
    summary_path: Path,
    stack: ExitStack,
    *,
    sidecar: bytes,
    canonical_input: dict[str, Any],
) -> Section15WriteResult:
    """Read, validate, and install sidecar and stub while the lock is held."""
    with stack:
        try:
            original_bytes = summary_path.read_bytes()
            original = original_bytes.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise Section15PatternHistoryError(
                f"cannot read UTF-8 rhetoric summary at {summary_path}: {exc}"
            ) from exc
        sidecar_path = _sidecar_path(summary_path)
        try:
            existing_sidecar: bytes | None = sidecar_path.read_bytes()
        except FileNotFoundError:
            existing_sidecar = None
        except OSError as exc:
            raise Section15PatternHistoryError(
                f"cannot read {SIDECAR_NAME} at {sidecar_path}: {exc}"
            ) from exc

        candidate = _replace_block_text(original, render_section15_stub(sidecar))
        candidate_assessment = _assess_summary(candidate, sidecar)
        if not candidate_assessment.current_contract:
            details = "; ".join(
                candidate_assessment.errors or candidate_assessment.reason_codes
            )
            raise Section15PatternHistoryError(
                "rendered Section 15 candidate failed validation: " + details
            )
        if candidate_assessment.pattern_profile != canonical_input:
            raise Section15PatternHistoryError(
                "rendered Section 15 candidate does not round-trip the full "
                "pattern_profile"
            )

        count = candidate_assessment.scored_talk_count
        eligible_count = candidate_assessment.eligible_talk_count
        assert isinstance(count, int)  # shared-assessor postcondition
        assert isinstance(eligible_count, int)  # shared-assessor postcondition
        summary_changed = candidate != original
        sidecar_changed = existing_sidecar != sidecar
        if not summary_changed and not sidecar_changed:
            return Section15WriteResult(
                path=str(summary_path),
                changed=False,
                scored_talk_count=count,
                eligible_talk_count=eligible_count,
                catalog_fields_available=(
                    candidate_assessment.catalog_fields_available
                ),
            )

        # Sidecar first: interrupted before the summary rename, an older
        # inline block still reads as it did, and an older stub no longer
        # matches, which readers refuse until the next replace.
        if sidecar_changed:
            _install_bytes(
                sidecar_path,
                sidecar,
                summary_path=summary_path,
                expected_summary=original_bytes,
            )
        if summary_changed:
            _install_bytes(
                summary_path,
                candidate.encode("utf-8"),
                summary_path=summary_path,
                expected_summary=original_bytes,
            )

        return Section15WriteResult(
            path=str(summary_path),
            changed=True,
            scored_talk_count=count,
            eligible_talk_count=eligible_count,
            catalog_fields_available=candidate_assessment.catalog_fields_available,
        )


def _install_bytes(
    target: Path,
    payload: bytes,
    *,
    summary_path: Path,
    expected_summary: bytes,
) -> None:
    """Rename ``payload`` over ``target``, refusing when the summary moved.

    Called with the writer lock held, so no other toolkit writer sits between
    the recheck and the rename. The recheck is what covers the writer no lock
    reaches — a human saving the summary in an editor. ``target`` takes the
    summary's permission bits.
    """
    mode = stat.S_IMODE(summary_path.stat().st_mode)
    temporary_path: Path | None = None
    file_descriptor: int | None = None
    try:
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
        )
        temporary_path = Path(temporary_name)
        os.fchmod(file_descriptor, mode)
        handle = os.fdopen(file_descriptor, "wb")
        file_descriptor = None
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            current = summary_path.read_bytes()
        except OSError as exc:
            raise Section15PatternHistoryError(
                f"cannot re-read rhetoric summary at {summary_path} before "
                f"installing {target.name}: {exc}"
            ) from exc
        if current != expected_summary:
            raise Section15PatternHistoryError(
                f"rhetoric summary at {summary_path} changed while the Section 15 "
                "replacement was staged; re-run the replace against the current file"
            )
        os.replace(temporary_path, target)
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


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
        # Never carry the exception text forward: this error is printed, and
        # decoder messages name the rejected key or value verbatim. The typed
        # reason code routes to the shared closed vocabulary instead.
        _code, message = DATABASE_READ_DIAGNOSTICS.get(
            exc.reason_code, DATABASE_READ_FALLBACK
        )
        # The path goes no further either: this message is printed, and the
        # host path is the other half of what the redaction contract keeps out
        # of output. The caller supplied the path and already knows it.
        raise Section15PatternHistoryError(
            f"cannot load the strict tracking database: {message}"
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
    classification_policy_stamp: object | None = None,
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
    try:
        policy_stamp = (
            validate_policy_stamp(pattern_profile.get("classification_policy"))
            if classification_policy_stamp is None
            else validate_policy_stamp(classification_policy_stamp)
        )
        expected_classification = classify_pattern_profile(
            snapshot["baseline_talks"], policy_stamp
        )
    except (RuntimeError, ValueError) as exc:
        raise Section15PatternHistoryError(
            f"cannot recompute policy-bound classifications: {exc}"
        ) from exc
    for field, expected in expected_classification.items():
        if pattern_profile.get(field) != expected:
            raise Section15PatternHistoryError(
                f"pattern_profile.{field} does not equal deterministic "
                "classifications recomputed from the complete tracking cohort"
            )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    assess_parser = subparsers.add_parser("assess")
    assess_parser.add_argument("summary", type=Path)
    replace_parser = subparsers.add_parser("replace")
    replace_parser.add_argument("summary", type=Path)
    replace_parser.add_argument("pattern_profile", type=Path)
    replace_parser.add_argument("tracking_database")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "assess":
            assessment = assess_section15_pattern_history(args.summary)
            print(json.dumps(assessment.as_status_dict(), sort_keys=True))
            return 0 if assessment.current_contract else 1

        tracking_database_path = materialize_native_authority(
            args.tracking_database,
            authority="database_path",
        )
        tracking_database = _load_tracking_database(tracking_database_path)
        vault_root = resolve_vault_root_authority(
            database_path=tracking_database_path,
            config=tracking_database.get("config"),
        )
        candidate = _pattern_profile_candidate(_load_json(args.pattern_profile))
        result = replace_section15_current_block(
            args.summary,
            candidate,
            tracking_database,
            evidence_freshness_assessor=configured_evidence_freshness_assessor(
                vault_root,
                tracking_database.get("config"),
                local_audio=local_audio_declarations(tracking_database),
            ),
            classification_policy_stamp=resolve_classification_policy(vault_root),
        )
        print(json.dumps(result.as_dict(), sort_keys=True))
        return 0
    except (
        OSError,
        UnicodeDecodeError,
        PatternCohortSnapshotError,
        Section15PatternHistoryError,
        VaultRootAuthorityError,
        ValueError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
