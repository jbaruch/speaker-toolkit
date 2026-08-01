#!/usr/bin/env python3
"""Report whether Presentation Pattern history is safe for creator use.

The speaker profile remains useful when pattern history is unavailable: pacing,
visual, publishing, infrastructure, and other non-catalog fields are independent.
This module therefore returns a fail-closed status instead of rejecting the whole
profile.  The strict pattern-profile contract, active catalog identity, scoring
schema, baseline arithmetic, and cohort validation stay owned by
``vault-profile/scripts/profile_pattern_provenance.py``.

Usage:
    pattern_history_status.py <speaker-profile.json>

Output:
    One JSON object on stdout.  A readable profile whose pattern history is
    disabled is a successful assessment and exits 0.  File/JSON failures exit 1;
    argument errors exit 2.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path


_PROFILE_SCRIPTS = (
    Path(__file__).resolve().parents[2] / "vault-profile" / "scripts"
)
if str(_PROFILE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_PROFILE_SCRIPTS))

# The sibling skill directory is inserted above at runtime; static analysis cannot
# resolve that deliberate plugin-local path mutation.
from profile_pattern_provenance import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    REASON_EMPTY_CURRENT_COHORT,
    assess_pattern_profile,
)


CURRENT_PROFILE_SCHEMA_VERSION = 3
REASON_INVALID_PROFILE = "invalid_speaker_profile_contract"
REASON_PROFILE_SCHEMA_MISMATCH = "profile_schema_version_mismatch"


@dataclass(frozen=True)
class CreatorPatternHistoryStatus:
    """Creator-facing authorization state for catalog-derived speaker history."""

    history_enabled: bool
    profile_schema_version: object
    scored_talk_count: int | None
    reason_codes: tuple[str, ...]
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Return a stable JSON-serializable status payload."""
        return asdict(self)


def assess_creator_pattern_history(
    profile: object,
) -> CreatorPatternHistoryStatus:
    """Authorize history only for a current schema-v3 profile and provenance.

    The shared vault-profile assessor owns every pattern-specific invariant.  This
    wrapper adds only the outer profile-version gate required by the creator.
    """
    if not isinstance(profile, Mapping):
        return CreatorPatternHistoryStatus(
            history_enabled=False,
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
    reasons = assessment.errors
    if assessment.reason_codes == (REASON_EMPTY_CURRENT_COHORT,):
        reasons = (
            "pattern_profile has no talks in the active catalog and scoring "
            "generation",
        )

    return CreatorPatternHistoryStatus(
        history_enabled=(
            assessment.current_contract and assessment.catalog_fields_available
        ),
        profile_schema_version=schema_version,
        scored_talk_count=assessment.scored_talk_count,
        reason_codes=assessment.reason_codes,
        reasons=reasons,
    )


def disabled_history_warning(status: CreatorPatternHistoryStatus) -> str:
    """Render one actionable warning without leaking untrusted history fields."""
    if status.history_enabled:
        return ""
    details = "; ".join(status.reasons or status.reason_codes)
    return (
        f"Pattern history disabled ({', '.join(status.reason_codes)}): {details}. "
        "Regenerate speaker-profile.json with the current vault-profile skill; "
        "reprocess stale talks first when the active cohort is empty."
    )


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"Usage: {argv[0]} <speaker-profile.json>", file=sys.stderr)
        return 2

    profile_path = Path(argv[1])
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"failed to load {profile_path}: {exc}", file=sys.stderr)
        return 1

    status = assess_creator_pattern_history(profile)
    payload = status.as_dict()
    payload["warning"] = disabled_history_warning(status)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
