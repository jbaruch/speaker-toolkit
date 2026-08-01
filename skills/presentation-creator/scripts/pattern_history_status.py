#!/usr/bin/env python3
"""Report whether Presentation Pattern history is safe for creator use.

The speaker profile remains useful when pattern history is unavailable: pacing,
visual, publishing, infrastructure, and other non-catalog fields are independent.
This module therefore returns a fail-closed status instead of rejecting the whole
profile.  The strict pattern-profile contract, active catalog identity, scoring
schema, baseline arithmetic, opportunity rows, and cohort validation stay owned by
``vault-profile/scripts/profile_pattern_provenance.py``.

Usage:
    pattern_history_status.py <speaker-profile.json|-> \
        [rhetoric-style-summary.md]

Output:
    One JSON object on stdout.  A readable profile whose pattern history is
    disabled is a successful assessment and exits 0.  File/JSON failures exit 1;
    argument errors exit 2.
"""

from __future__ import annotations

import copy
import json
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path


_PROFILE_SCRIPTS = Path(__file__).resolve().parents[2] / "vault-profile" / "scripts"
if str(_PROFILE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_PROFILE_SCRIPTS))

# The sibling skill directory is inserted above at runtime; static analysis cannot
# resolve that deliberate plugin-local path mutation.
from profile_pattern_provenance import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    REASON_CLASSIFICATION_POLICY_UNAVAILABLE,
    REASON_EMPTY_CURRENT_COHORT,
    assess_pattern_profile,
)
from section15_pattern_history import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    Section15PatternHistoryAssessment,
    assess_section15_pattern_history,
)


CURRENT_PROFILE_SCHEMA_VERSION = 4
REASON_INVALID_PROFILE = "invalid_speaker_profile_contract"
REASON_PROFILE_SCHEMA_MISMATCH = "profile_schema_version_mismatch"


@dataclass(frozen=True)
class CreatorPatternHistoryStatus:
    """Creator-facing authorization state for catalog-derived speaker history."""

    history_enabled: bool
    history_source: str | None
    profile_schema_version: object
    scored_talk_count: int | None
    reason_codes: tuple[str, ...]
    reasons: tuple[str, ...]
    eligible_talk_count: int | None = None
    opportunity_rows_available: bool = False
    classification_fields_available: bool = False

    def as_dict(self) -> dict[str, object]:
        """Return a stable JSON-serializable status payload."""
        return asdict(self)


@dataclass(frozen=True)
class CreatorPatternHistoryResolution:
    """Authorization status plus the sole payload that status authorizes."""

    status: CreatorPatternHistoryStatus
    pattern_profile: dict[str, object] | None


def _assess_profile_pattern_history(
    profile: object,
) -> CreatorPatternHistoryStatus:
    """Authorize classifications only for a current schema-v4 profile and policy.

    The shared vault-profile assessor owns every pattern-specific invariant.  This
    wrapper adds only the outer profile-version gate required by the creator.
    """
    if not isinstance(profile, Mapping):
        return CreatorPatternHistoryStatus(
            history_enabled=False,
            history_source=None,
            profile_schema_version=None,
            scored_talk_count=None,
            reason_codes=(REASON_INVALID_PROFILE,),
            reasons=("speaker profile must be a JSON object",),
        )

    schema_version = profile.get("schema_version")
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != CURRENT_PROFILE_SCHEMA_VERSION
    ):
        return CreatorPatternHistoryStatus(
            history_enabled=False,
            history_source=None,
            profile_schema_version=schema_version,
            scored_talk_count=None,
            reason_codes=(REASON_PROFILE_SCHEMA_MISMATCH,),
            reasons=(
                "speaker profile schema_version "
                f"{schema_version!r} does not authorize pattern history; "
                f"expected {CURRENT_PROFILE_SCHEMA_VERSION}",
            ),
        )

    assessment = assess_pattern_profile(profile.get("pattern_profile"))
    reasons = list(assessment.errors)
    if REASON_EMPTY_CURRENT_COHORT in assessment.reason_codes:
        reasons.append(
            "pattern_profile has no talks in the active catalog and scoring generation"
        )
    if REASON_CLASSIFICATION_POLICY_UNAVAILABLE in assessment.reason_codes:
        reasons.append(
            "pattern occurrence rows are current, but owner thresholds for "
            "never-used, mastery, recurring severity, and trends are not configured"
        )

    return CreatorPatternHistoryStatus(
        history_enabled=(
            assessment.current_contract
            and assessment.catalog_fields_available
            and assessment.classification_fields_available
        ),
        history_source=(
            "profile"
            if assessment.current_contract
            and assessment.catalog_fields_available
            and assessment.classification_fields_available
            else None
        ),
        profile_schema_version=schema_version,
        scored_talk_count=assessment.scored_talk_count,
        reason_codes=assessment.reason_codes,
        reasons=tuple(reasons),
        eligible_talk_count=assessment.eligible_talk_count,
        opportunity_rows_available=(
            assessment.current_contract and assessment.catalog_fields_available
        ),
        classification_fields_available=(
            assessment.current_contract and assessment.classification_fields_available
        ),
    )


def _dedupe(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _fallback_status(
    profile_status: CreatorPatternHistoryStatus,
    summary_assessment: Section15PatternHistoryAssessment,
) -> CreatorPatternHistoryStatus:
    if (
        summary_assessment.current_contract
        and summary_assessment.catalog_fields_available
        and summary_assessment.classification_fields_available
    ):
        return CreatorPatternHistoryStatus(
            history_enabled=True,
            history_source="section15_current_block",
            profile_schema_version=profile_status.profile_schema_version,
            scored_talk_count=summary_assessment.scored_talk_count,
            reason_codes=(),
            reasons=(),
            eligible_talk_count=summary_assessment.eligible_talk_count,
            opportunity_rows_available=True,
            classification_fields_available=True,
        )

    reasons = list(summary_assessment.errors)
    if REASON_EMPTY_CURRENT_COHORT in summary_assessment.reason_codes:
        reasons.append(
            "Section 15 current block has no talks in the active catalog and "
            "scoring generation"
        )
    if REASON_CLASSIFICATION_POLICY_UNAVAILABLE in (summary_assessment.reason_codes):
        reasons.append(
            "Section 15 occurrence rows are current, but owner classification "
            "thresholds are not configured"
        )
    return CreatorPatternHistoryStatus(
        history_enabled=False,
        history_source=None,
        profile_schema_version=profile_status.profile_schema_version,
        scored_talk_count=summary_assessment.scored_talk_count,
        reason_codes=_dedupe(
            profile_status.reason_codes + summary_assessment.reason_codes
        ),
        reasons=_dedupe(profile_status.reasons + tuple(reasons)),
        eligible_talk_count=summary_assessment.eligible_talk_count,
        opportunity_rows_available=(
            summary_assessment.current_contract
            and summary_assessment.catalog_fields_available
        ),
        classification_fields_available=False,
    )


def resolve_creator_pattern_history(
    profile: object,
    summary_text: str | None = None,
) -> CreatorPatternHistoryResolution:
    """Resolve one authorized history payload without merging source lanes.

    A valid current profile always wins. Section 15 is consulted only when the
    profile lane is disabled and only its explicit current block is eligible.
    """
    profile_status = _assess_profile_pattern_history(profile)
    if profile_status.history_enabled:
        assert isinstance(profile, Mapping)
        pattern_profile = profile.get("pattern_profile")
        assert isinstance(pattern_profile, Mapping)  # shared-assessor postcondition
        return CreatorPatternHistoryResolution(
            status=profile_status,
            pattern_profile=copy.deepcopy(dict(pattern_profile)),
        )
    if summary_text is None:
        return CreatorPatternHistoryResolution(
            status=profile_status,
            pattern_profile=None,
        )

    summary_assessment = assess_section15_pattern_history(summary_text)
    status = _fallback_status(profile_status, summary_assessment)
    pattern_profile = (
        copy.deepcopy(summary_assessment.pattern_profile)
        if status.history_enabled
        else None
    )
    return CreatorPatternHistoryResolution(
        status=status,
        pattern_profile=pattern_profile,
    )


def assess_creator_pattern_history(
    profile: object,
    summary_text: str | None = None,
) -> CreatorPatternHistoryStatus:
    """Return the creator authorization status for profile then safe fallback."""
    return resolve_creator_pattern_history(profile, summary_text).status


def disabled_history_warning(status: CreatorPatternHistoryStatus) -> str:
    """Render one actionable warning without leaking untrusted history fields."""
    if status.history_enabled:
        return ""
    details = "; ".join(status.reasons or status.reason_codes)
    if REASON_CLASSIFICATION_POLICY_UNAVAILABLE in status.reason_codes:
        warning = (
            "Pattern classifications disabled "
            f"({', '.join(status.reason_codes)}): {details}. Current occurrence "
            "rows remain auditable, but do not emit signature, New-to-You, "
            "underuse, recurring-severity, mastery, or trend claims until the "
            "speaker owns a versioned classification policy."
        )
    else:
        warning = (
            f"Pattern history disabled ({', '.join(status.reason_codes)}): "
            f"{details}. Regenerate speaker-profile.json with the current "
            "vault-profile skill; reprocess stale talks first when the active "
            "cohort is empty."
        )
    if any(code.startswith("section15_current_block_") for code in status.reason_codes):
        warning += (
            " Regenerate the uniquely delimited Section 15 current block from a "
            "complete post-batch candidate before using summary fallback."
        )
    return warning


def main(argv: list[str]) -> int:
    if len(argv) not in {2, 3}:
        print(
            f"Usage: {argv[0]} <speaker-profile.json|-> [rhetoric-style-summary.md]",
            file=sys.stderr,
        )
        return 2

    profile_load_error: tuple[Path, OSError | json.JSONDecodeError] | None = None
    if argv[1] == "-":
        profile: object = {}
    else:
        profile_path = Path(argv[1])
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            profile = None
            profile_load_error = (profile_path, exc)

    profile_only_status = assess_creator_pattern_history(profile)
    summary_text: str | None = None
    if not profile_only_status.history_enabled and len(argv) == 3:
        summary_path = Path(argv[2])
        try:
            summary_text = summary_path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"failed to load {summary_path}: {exc}", file=sys.stderr)
            return 1
    elif profile_load_error is not None:
        profile_path, exc = profile_load_error
        print(f"failed to load {profile_path}: {exc}", file=sys.stderr)
        return 1

    status = assess_creator_pattern_history(profile, summary_text)
    payload = status.as_dict()
    payload["warning"] = disabled_history_warning(status)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
