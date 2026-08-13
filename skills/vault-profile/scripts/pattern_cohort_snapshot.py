"""Build the canonical live pattern cohort consumed by vault-profile.

This module is the shared deterministic boundary between ``load-vault.py`` and
the owner-side profile validator.  Both callers therefore select the same fresh
scoring-v5 talks, build the same raw-score baseline, and aggregate the same
per-pattern opportunity rows.  It performs no profile classification.
"""

from __future__ import annotations

import pathlib
import sys
from collections.abc import Mapping
from typing import Any, TypedDict


_INGRESS_SCRIPTS = (
    pathlib.Path(__file__).resolve().parents[2] / "vault-ingress" / "scripts"
)
if str(_INGRESS_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_INGRESS_SCRIPTS))

from adherence_baseline import (  # noqa: E402
    AdherenceBaselineError,
    ELIGIBLE_STATUSES,
    EvidenceFreshnessAssessor,
    build_current_cohort_baseline,
    partition_pattern_scoring_cohort,
)
from pattern_opportunities import (  # noqa: E402
    PatternOpportunityError,
    build_pattern_opportunity_rows,
)
from persisted_pattern_observations import (  # noqa: E402
    persisted_observation_assessor,
)
from return_validation import (  # noqa: E402
    PATTERN_SCORING_SCHEMA_VERSION,
    ReturnValidationError,
    assess_current_persisted_pattern_evidence_freshness,
    load_catalog,
)
from video_evidence import VideoEvidenceAssessment  # noqa: E402
from vault_root_authority import (  # noqa: E402
    VaultRootAuthorityError,
    resolve_vault_root_authority,
)


class PatternCohortSnapshotError(ValueError):
    """The canonical profile cohort could not be selected or aggregated."""


class PatternCohortSnapshot(TypedDict):
    """Canonical typed payload shared by every profile cohort consumer."""

    baseline_talks: list[Mapping[str, object]]
    baseline_talk_filenames: list[str]
    excluded_pattern_scoring_talks: list[Mapping[str, object]]
    pattern_scoring_exclusions: list[dict[str, object]]
    pattern_baseline: dict[str, object]
    pattern_opportunities: dict[str, object]


def configured_evidence_freshness_assessor(
    vault_root: pathlib.Path,
    config: object,
    *,
    catalog: Any | None = None,
) -> EvidenceFreshnessAssessor:
    """Bind the shared evidence-freshness check to trusted live source roots."""
    source_roots = dict(config) if isinstance(config, Mapping) else {}
    try:
        evidence_vault_root = resolve_vault_root_authority(
            database_path=vault_root / "tracking-database.json",
            config=config,
            cli_vault_root=vault_root,
        )
    except VaultRootAuthorityError as exc:
        raise PatternCohortSnapshotError(str(exc)) from exc
    video_evidence_assessment = VideoEvidenceAssessment()
    freshness_cache: dict[int, tuple[str, ...]] = {}

    def assess(talk: Mapping[str, object]) -> tuple[str, ...]:
        identity = id(talk)
        if identity not in freshness_cache:
            freshness_cache[identity] = tuple(
                assess_current_persisted_pattern_evidence_freshness(
                    talk,
                    vault_root=evidence_vault_root,
                    source_roots=source_roots,
                    catalog=catalog,
                    video_evidence_assessment=video_evidence_assessment,
                )
            )
        return freshness_cache[identity]

    return assess


def build_current_pattern_snapshot(
    talks: object,
    *,
    as_of: object,
    evidence_freshness_assessor: EvidenceFreshnessAssessor,
    catalog: Any | None = None,
) -> PatternCohortSnapshot:
    """Return the one canonical current-cohort payload for profile generation."""
    try:
        if isinstance(talks, (str, bytes, Mapping)) or not isinstance(talks, list):
            raise AdherenceBaselineError("talks must be an array of talk objects")
        invalid_index = next(
            (
                index
                for index, talk in enumerate(talks)
                if not isinstance(talk, Mapping)
            ),
            None,
        )
        if invalid_index is not None:
            raise AdherenceBaselineError(f"talks[{invalid_index}] must be an object")
        processed_talks = [
            talk for talk in talks if talk.get("status") in ELIGIBLE_STATUSES
        ]
        resolved_catalog = catalog or load_catalog()
        observation_assessor = persisted_observation_assessor(resolved_catalog)
        (
            baseline_talks,
            excluded_pattern_talks,
            pattern_scoring_exclusions,
        ) = partition_pattern_scoring_cohort(
            processed_talks,
            excluded_filenames=(),
            pattern_catalog_fingerprint=resolved_catalog.fingerprint,
            pattern_scoring_schema_version=PATTERN_SCORING_SCHEMA_VERSION,
            evidence_freshness_assessor=evidence_freshness_assessor,
            persisted_observation_assessor=observation_assessor,
        )
        pattern_baseline = build_current_cohort_baseline(
            processed_talks,
            as_of=as_of,
            pattern_catalog_fingerprint=resolved_catalog.fingerprint,
            pattern_scoring_schema_version=PATTERN_SCORING_SCHEMA_VERSION,
            evidence_freshness_assessor=evidence_freshness_assessor,
            persisted_observation_assessor=observation_assessor,
        )
        pattern_opportunities = build_pattern_opportunity_rows(
            baseline_talks,
            catalog=resolved_catalog,
        )
        baseline_talk_filenames = sorted(
            str(talk["filename"]) for talk in baseline_talks
        )
        return {
            "baseline_talks": baseline_talks,
            "baseline_talk_filenames": baseline_talk_filenames,
            "excluded_pattern_scoring_talks": excluded_pattern_talks,
            "pattern_scoring_exclusions": pattern_scoring_exclusions,
            "pattern_baseline": pattern_baseline,
            "pattern_opportunities": pattern_opportunities,
        }
    except (
        AdherenceBaselineError,
        PatternOpportunityError,
        ReturnValidationError,
    ) as exc:
        raise PatternCohortSnapshotError(str(exc)) from exc
