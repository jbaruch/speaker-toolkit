"""Profile schema-v4 tests for exact per-pattern opportunity provenance."""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
from pathlib import Path
from typing import Any

import pytest


def _transcript_projection(catalog) -> tuple[list[dict], list[dict], list[dict]]:
    """Build the active catalog's mechanically valid transcript-only outcomes."""
    outcomes: list[dict] = []
    not_evaluable: list[dict] = []
    assessments: list[dict] = []
    transcript = frozenset({"transcript"})
    for pattern_id, entry in sorted(catalog.entries.items()):
        if not entry.observable:
            continue
        if entry.applicability_evaluable_from is not None:
            if transcript not in entry.applicability_evaluable_from:
                outcomes.append({"pattern_id": pattern_id, "outcome": "not_evaluable"})
                not_evaluable.append({"pattern_id": pattern_id})
                continue
            assessments.append({"pattern_id": pattern_id, "result": "applicable"})
        outcome = (
            "undetected"
            if entry.absence_evaluable_from is not None
            and transcript in entry.absence_evaluable_from
            else "not_evaluable"
        )
        outcomes.append({"pattern_id": pattern_id, "outcome": outcome})
        if outcome == "not_evaluable":
            not_evaluable.append({"pattern_id": pattern_id})
    return outcomes, not_evaluable, assessments


def _pattern_baseline(validate_profile, *, count: int = 2) -> dict[str, Any]:
    score_sum = 0
    average = 0.0 if count else None
    catalog_fingerprint, scoring_schema = (
        validate_profile.active_pattern_generation_identity()
    )
    opportunities = importlib.import_module("pattern_opportunities")
    pattern_evidence = importlib.import_module("pattern_evidence")
    catalog = opportunities.load_catalog()
    pattern_outcomes, _, _ = _transcript_projection(catalog)
    opportunity_identity = (
        pattern_evidence.opportunity_coverage_identity(
            pattern_outcomes,
            pattern_catalog_fingerprint=catalog_fingerprint,
            pattern_scoring_schema_version=scoring_schema,
        )
        if count
        else None
    )
    return {
        "schema_version": 2,
        "as_of": "2025-01-02T03:04:05+00:00",
        "scope": "global",
        "active_batch_excluded": False,
        "excluded_filenames": [],
        "eligible_statuses": ["processed", "processed_partial"],
        "pattern_scoring_generation_status": "current",
        "pattern_scoring_generation_reasons": [],
        "pattern_catalog_fingerprint": catalog_fingerprint,
        "pattern_scoring_schema_version": scoring_schema,
        "scored_talk_count": count,
        "pattern_score_sum": score_sum,
        "average_pattern_score": average,
        "eligible_talk_count": count,
        "opportunity_coverage_identity": opportunity_identity,
        "raw_score_comparison_status": ("available" if count else "unavailable"),
        "raw_score_comparison_reason": (None if count else "empty_current_cohort"),
    }


def _pattern_profile(validate_profile, *, count: int = 2) -> dict[str, Any]:
    empty = count == 0
    filenames = [] if empty else ["example-a.md", "example-b.md"]
    opportunities = importlib.import_module("pattern_opportunities")
    provenance = importlib.import_module("profile_pattern_provenance")
    catalog = opportunities.load_catalog()
    pattern_outcomes, _, _ = _transcript_projection(catalog)
    rows = opportunities.build_pattern_opportunity_rows(
        [
            {
                "filename": filename,
                "pattern_observations": {
                    "patterns_detected": [],
                    "antipatterns_detected": [],
                    "pattern_outcomes": copy.deepcopy(pattern_outcomes),
                },
            }
            for filename in filenames
        ],
        catalog=catalog,
    )
    return {
        "pattern_baseline": _pattern_baseline(validate_profile, count=count),
        "baseline_talk_filenames": filenames,
        "eligible_talk_count": count,
        "talks_scored": count,
        "average_pattern_score": None if empty else 0.0,
        "score_trend": "unavailable",
        "pattern_breadth": {
            "avg_distinct_patterns_per_talk": None,
            "trend": "unavailable",
            "note": "Pattern breadth from the exact current cohort.",
        },
        "underused_patterns": [],
        "score_drivers": {
            "direction": "unavailable",
            "antipattern_drivers": [],
            "pattern_drivers": [],
            "note": "Score drivers from the exact current cohort.",
        },
        "by_mode": [],
        "strengths": [],
        "strengths_note": "Current-generation strengths only.",
        "note": "Only observable catalog entries are included.",
        "pattern_usage": rows["pattern_usage"],
        "antipattern_frequency": rows["antipattern_frequency"],
        "never_used_patterns": [],
        "signature_combinations": [],
        "mastery_levels": {
            "signature": [],
            "regular": [],
            "occasional": [],
            "rare": [],
            "never_tried": [],
        },
        "classification_availability": (
            provenance.unavailable_classification_availability()
        ),
    }


def _profile(validate_profile, *, count: int = 2) -> dict[str, Any]:
    return {
        "schema_version": 5,
        "generated_date": "2025-01-02",
        "talks_analyzed": 4,
        "speaker": {},
        "infrastructure": {},
        "presentation_modes": [],
        "instrument_catalog": {},
        "rhetoric_defaults": {},
        "confirmed_intents": [],
        "guardrail_sources": {"recurring_issues": []},
        "pacing": {},
        "pattern_profile": _v5_pattern_profile(validate_profile, count=count),
        "visual_style_history": {},
        "publishing_process": {},
        "design_rules": {},
        "badges": [],
    }


def _v5_pattern_profile(validate_profile, *, count: int = 2) -> dict[str, Any]:
    profile = _pattern_profile(validate_profile, count=count)
    filenames = profile["baseline_talk_filenames"]
    catalog = importlib.import_module("pattern_opportunities").load_catalog()
    pattern_outcomes, _, _ = _transcript_projection(catalog)
    talks = [
        {
            "filename": filename,
            "pattern_score": 0,
            "pattern_observations": {
                "pattern_score": 0,
                "patterns_detected": [],
                "antipatterns_detected": [],
                "pattern_outcomes": copy.deepcopy(pattern_outcomes),
            },
        }
        for filename in filenames
    ]
    runtime = importlib.import_module("pattern_classification_runtime")
    profile.update(
        runtime.classify_pattern_profile(
            talks,
            runtime.resolve_classification_policy(
                Path(__file__).resolve().parent / "__no_policy_override__"
            ),
            catalog=catalog,
        )
    )
    return profile


def _run(validate_profile, profile, tmp_path, capsys, *, extra_talks=None):
    fingerprint, scoring_schema = validate_profile.active_pattern_generation_identity()
    opportunities = importlib.import_module("pattern_opportunities")
    pattern_evidence = importlib.import_module("pattern_evidence")
    transcript_timing = importlib.import_module("transcript_timing")
    catalog = opportunities.load_catalog()
    pattern_outcomes, not_evaluable, assessments = _transcript_projection(catalog)
    eligible_count = profile.get("pattern_profile", {}).get("eligible_talk_count", 2)
    filenames = [] if eligible_count == 0 else ["example-a.md", "example-b.md"]
    scores = [0, 0]
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir(exist_ok=True)
    talks = []
    for index, (filename, score) in enumerate(zip(filenames, scores)):
        video_id = f"video{index:06d}"
        source_duration = 60.0
        artifact = transcripts / f"{video_id}.txt"
        content = ("synthetic evidence " * 225).strip() + "\n"
        transcript_timing.write_transcript_bundle(
            artifact,
            content,
            [{"text": content, "start": 0.0, "end": 10.0}],
            source="captions",
            timing_provenance=transcript_timing.youtube_timing_provenance(
                "captions", video_id, source_duration
            ),
            quality_policy=transcript_timing.build_quality_policy(400),
            quality_policy_provenance={"kind": "fixed_default"},
        )
        quality_artifact = artifact.with_suffix(".quality.json")
        timing_artifact = artifact.with_suffix(".segments.json")
        relative = artifact.relative_to(tmp_path).as_posix()
        quality_relative = quality_artifact.relative_to(tmp_path).as_posix()
        timing_relative = timing_artifact.relative_to(tmp_path).as_posix()
        artifact_digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        quality_digest = hashlib.sha256(quality_artifact.read_bytes()).hexdigest()
        timing_digest = hashlib.sha256(timing_artifact.read_bytes()).hexdigest()
        located_assessments = []
        for assessment in assessments:
            entry = catalog.entries[assessment["pattern_id"]]
            channel = (
                "transcript"
                if "transcript" in entry.evidence_channels
                else "timed_transcript"
            )
            citation = {
                "source": "transcript",
                "channel": channel,
                "quote": "synthetic evidence synthetic evidence",
                "line_start": 1,
                "line_end": 1,
                "artifact_root": "vault",
                "artifact_path": relative,
                "artifact_sha256": artifact_digest,
                "quality_artifact_root": "vault",
                "quality_artifact_path": quality_relative,
                "quality_artifact_sha256": quality_digest,
                "timing_artifact_root": "vault",
                "timing_artifact_path": timing_relative,
                "timing_artifact_sha256": timing_digest,
            }
            if channel == "timed_transcript":
                citation.update(
                    {
                        "start_seconds": 0.0,
                        "end_seconds": 10.0,
                    }
                )
            located_assessments.append(
                {
                    **assessment,
                    "evidence_source": "transcript",
                    "evidence": "The complete transcript establishes applicability.",
                    "evidence_citations": [citation],
                }
            )
        talks.append(
            {
                "filename": filename,
                "status": "processed",
                "pattern_scoring_generation_status": "current",
                "pattern_scoring_generation_reasons": [],
                "pattern_catalog_fingerprint": fingerprint,
                "pattern_scoring_schema_version": scoring_schema,
                "pattern_score": score,
                "transcript_path": relative,
                "transcript_source": "youtube_auto",
                "youtube_id": video_id,
                "source_identity": {
                    "schema_version": 1,
                    "provider": "youtube",
                    "video_id": video_id,
                    "duration_seconds": source_duration,
                },
                "pattern_observations": {
                    "pattern_score": score,
                    "patterns_detected": [],
                    "antipatterns_detected": [],
                    "not_evaluable": copy.deepcopy(not_evaluable),
                    "applicability_assessments": located_assessments,
                    "pattern_outcomes": copy.deepcopy(pattern_outcomes),
                    "opportunity_coverage_identity": (
                        pattern_evidence.opportunity_coverage_identity(
                            pattern_outcomes,
                            pattern_catalog_fingerprint=fingerprint,
                            pattern_scoring_schema_version=scoring_schema,
                        )
                    ),
                    "evidence_schema_version": 2,
                    "evidence_sources": ["transcript"],
                    "source_inspection": [
                        {
                            "source": "transcript",
                            "line_ranges": [[1, 1]],
                            "line_count": 1,
                            "coverage_complete": True,
                            "absence_capability_complete": True,
                            "absence_capability_reason": "authorized_transcript",
                            "artifact_root": "vault",
                            "artifact_path": relative,
                            "artifact_sha256": artifact_digest,
                            "timing_artifact_root": "vault",
                            "timing_artifact_path": timing_relative,
                            "timing_artifact_sha256": timing_digest,
                            "quality_artifact_root": "vault",
                            "quality_artifact_path": quality_relative,
                            "quality_artifact_sha256": quality_digest,
                        }
                    ],
                },
            }
        )
    freshness = importlib.import_module("return_validation")
    for talk in talks:
        reasons = freshness.assess_current_persisted_pattern_evidence_freshness(
            talk,
            vault_root=tmp_path,
            catalog=catalog,
        )
        assert reasons == (), "\n".join(reasons)
    talks.extend(extra_talks or [])
    (tmp_path / "tracking-database.json").write_text(
        json.dumps({"config": {}, "talks": talks}),
        encoding="utf-8",
    )
    path = tmp_path / "speaker-profile.json"
    path.write_text(json.dumps(profile))
    return_code = validate_profile.main(
        ["validate-profile.py", str(path), "--vault-root", str(tmp_path)]
    )
    captured = capsys.readouterr()
    return return_code, json.loads(captured.out)


def test_current_profile_binds_every_pattern_denominator_to_one_cohort(
    validate_profile,
    tmp_path,
    capsys,
):
    return_code, report = _run(
        validate_profile,
        _profile(validate_profile),
        tmp_path,
        capsys,
    )

    assert return_code == 0, "\n".join(report["errors"])
    assert report == {
        "valid": True,
        "schema_version": 5,
        "missing_keys": [],
        "errors": [],
    }


def test_live_validation_rejects_duplicate_filenames_in_ineligible_rows(
    validate_profile,
    tmp_path,
    capsys,
):
    pending_duplicate = {
        "filename": "example-a.md",
        "status": "pending",
        "pattern_scoring_generation_status": "future",
    }

    return_code, report = _run(
        validate_profile,
        _profile(validate_profile),
        tmp_path,
        capsys,
        extra_talks=[pending_duplicate],
    )

    assert return_code == 1
    assert report["valid"] is False
    assert any("duplicate talk filename" in error for error in report["errors"])


def test_reusable_assessment_distinguishes_current_empty_and_stale_history(
    validate_profile,
):
    current = validate_profile.assess_pattern_profile(
        _pattern_profile(validate_profile)
    )
    empty = validate_profile.assess_pattern_profile(
        _pattern_profile(validate_profile, count=0)
    )
    stale_profile = _pattern_profile(validate_profile)
    stale_profile["pattern_baseline"]["pattern_catalog_fingerprint"] = "0" * 64
    stale = validate_profile.assess_pattern_profile(stale_profile)

    assert (
        current.current_contract,
        current.catalog_fields_available,
        current.scored_talk_count,
        current.reason_codes,
    ) == (True, True, 2, ("pattern_classification_policy_unavailable",))
    assert current.classification_fields_available is False
    assert (
        empty.current_contract,
        empty.catalog_fields_available,
        empty.scored_talk_count,
        empty.reason_codes,
    ) == (
        True,
        False,
        0,
        (
            "empty_current_pattern_cohort",
            "pattern_classification_policy_unavailable",
        ),
    )
    assert stale.current_contract is False
    assert stale.catalog_fields_available is False
    assert stale.reason_codes == (
        "pattern_catalog_fingerprint_mismatch",
        "invalid_pattern_profile_contract",
    )


def test_v5_assessment_enables_independent_policy_domains(validate_profile):
    pattern_profile = _v5_pattern_profile(validate_profile)

    assessment = validate_profile.assess_pattern_profile(
        pattern_profile, expected_contract_version=5
    )

    assert assessment.current_contract is True
    assert assessment.classification_fields_available is True
    assert assessment.available_classification_domains == frozenset(
        {
            "mastery_and_novelty",
            "antipattern_recurrence",
            "underuse",
            "signature_combinations",
        }
    )
    assert assessment.domain_available("trends") is False
    assert assessment.domain_available("modes") is False
    assert (
        assessment.policy_semantic_sha256
        == pattern_profile["classification_policy"]["semantic_sha256"]
    )


def test_v5_assessment_rejects_policy_digest_tampering(validate_profile):
    pattern_profile = _v5_pattern_profile(validate_profile)
    pattern_profile["classification_policy"]["semantic_sha256"] = "0" * 64

    assessment = validate_profile.assess_pattern_profile(
        pattern_profile, expected_contract_version=5
    )

    provenance_module = importlib.import_module("profile_pattern_provenance")
    assert assessment.current_contract is False
    assert (
        provenance_module.REASON_CLASSIFICATION_POLICY_INVALID
        in assessment.reason_codes
    )
    assert any("semantic_sha256" in error for error in assessment.errors)


def test_mixed_opportunity_identity_keeps_occurrences_and_suppresses_raw_average(
    validate_profile,
):
    profile = _pattern_profile(validate_profile)
    baseline = profile["pattern_baseline"]
    baseline.update(
        {
            "scored_talk_count": 0,
            "pattern_score_sum": 0,
            "average_pattern_score": None,
            "opportunity_coverage_identity": None,
            "raw_score_comparison_status": "unavailable",
            "raw_score_comparison_reason": "mixed_opportunity_coverage",
        }
    )
    profile["talks_scored"] = 0
    profile["average_pattern_score"] = None

    assessment = validate_profile.assess_pattern_profile(profile)

    assert assessment.current_contract is True
    assert assessment.catalog_fields_available is True
    assert assessment.eligible_talk_count == 2
    assert assessment.scored_talk_count == 0


def test_all_unknown_opportunities_keep_rows_but_suppress_raw_zero(
    validate_profile,
):
    profile = _pattern_profile(validate_profile)
    opportunities = importlib.import_module("pattern_opportunities")
    adherence_baseline = importlib.import_module("adherence_baseline")
    catalog = opportunities.load_catalog()
    observable_ids = sorted(
        pattern_id for pattern_id, entry in catalog.entries.items() if entry.observable
    )
    rows = opportunities.build_pattern_opportunity_rows(
        [
            {
                "filename": filename,
                "pattern_observations": {
                    "patterns_detected": [],
                    "antipatterns_detected": [],
                    "pattern_outcomes": [
                        {
                            "pattern_id": pattern_id,
                            "outcome": "not_evaluable",
                        }
                        for pattern_id in observable_ids
                    ],
                },
            }
            for filename in profile["baseline_talk_filenames"]
        ],
        catalog=catalog,
    )
    profile["pattern_baseline"].update(
        {
            "scored_talk_count": 0,
            "pattern_score_sum": 0,
            "average_pattern_score": None,
            "opportunity_coverage_identity": None,
            "raw_score_comparison_status": "unavailable",
            "raw_score_comparison_reason": (
                adherence_baseline.NO_EVALUABLE_PATTERN_OPPORTUNITIES_REASON
            ),
        }
    )
    profile["talks_scored"] = 0
    profile["average_pattern_score"] = None
    profile["pattern_usage"] = rows["pattern_usage"]
    profile["antipattern_frequency"] = rows["antipattern_frequency"]

    assessment = validate_profile.assess_pattern_profile(profile)

    assert assessment.current_contract is True
    assert assessment.catalog_fields_available is True
    assert assessment.classification_fields_available is False
    assert assessment.eligible_talk_count == 2
    assert assessment.scored_talk_count == 0
    for row in profile["pattern_usage"] + profile["antipattern_frequency"]:
        assert row["evaluable_count"] == 0
        assert row["unevaluable_count"] == 2
        assert row["out_of"] == 0
        assert row.get("usage_rate", row.get("frequency_rate")) is None


def test_profile_v3_is_noncurrent_and_rejected(validate_profile, tmp_path, capsys):
    profile = _profile(validate_profile)
    profile["schema_version"] = 3

    return_code, report = _run(validate_profile, profile, tmp_path, capsys)

    assert return_code == 1
    assert report["valid"] is False
    assert report["errors"] == ["schema_version is 3 (expected 5)"]


def test_missing_pattern_baseline_is_rejected(validate_profile, tmp_path, capsys):
    profile = _profile(validate_profile)
    del profile["pattern_profile"]["pattern_baseline"]

    return_code, report = _run(validate_profile, profile, tmp_path, capsys)

    assert return_code == 1
    assert any("pattern_baseline" in error for error in report["errors"])


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "pattern_catalog_fingerprint",
            "0" * 64,
            "does not match the active catalog",
        ),
        (
            "pattern_scoring_schema_version",
            1,
            "expected active schema",
        ),
    ],
)
def test_stale_scoring_generation_is_rejected(
    validate_profile,
    tmp_path,
    capsys,
    field,
    value,
    message,
):
    profile = _profile(validate_profile)
    profile["pattern_profile"]["pattern_baseline"][field] = value

    return_code, report = _run(validate_profile, profile, tmp_path, capsys)

    assert return_code == 1
    assert any(message in error for error in report["errors"])


def test_noncanonical_baseline_arithmetic_is_rejected(
    validate_profile,
    tmp_path,
    capsys,
):
    profile = _profile(validate_profile)
    profile["pattern_profile"]["pattern_baseline"]["average_pattern_score"] = 7.1

    return_code, report = _run(validate_profile, profile, tmp_path, capsys)

    assert return_code == 1
    assert "ROUND_HALF_EVEN count/sum result" in report["errors"][0]


def test_claim_time_baseline_is_not_valid_profile_provenance(
    validate_profile,
    tmp_path,
    capsys,
):
    profile = _profile(validate_profile)
    baseline = profile["pattern_profile"]["pattern_baseline"]
    baseline["active_batch_excluded"] = True
    baseline["excluded_filenames"] = ["active-talk.md"]

    return_code, report = _run(validate_profile, profile, tmp_path, capsys)

    assert return_code == 1
    assert any("full-cohort snapshot" in error for error in report["errors"])
    assert any("excluded_filenames must be []" in error for error in report["errors"])


@pytest.mark.parametrize(
    "filenames",
    [
        ["example-b.md", "example-a.md"],
        ["example-a.md", "example-a.md"],
        ["example-a.md"],
    ],
)
def test_cohort_filename_identity_must_be_canonical_and_complete(
    validate_profile,
    tmp_path,
    capsys,
    filenames,
):
    profile = _profile(validate_profile)
    profile["pattern_profile"]["baseline_talk_filenames"] = filenames

    return_code, report = _run(validate_profile, profile, tmp_path, capsys)

    assert return_code == 1
    assert any("baseline_talk_filenames" in error for error in report["errors"])


def test_talks_scored_must_equal_baseline_count(validate_profile, tmp_path, capsys):
    profile = _profile(validate_profile)
    profile["pattern_profile"]["talks_scored"] = 3

    return_code, report = _run(validate_profile, profile, tmp_path, capsys)

    assert return_code == 1
    assert any("talks_scored must equal" in error for error in report["errors"])


def test_profile_average_must_equal_canonical_baseline(
    validate_profile,
    tmp_path,
    capsys,
):
    profile = _profile(validate_profile)
    profile["pattern_profile"]["average_pattern_score"] = 6.9

    return_code, report = _run(validate_profile, profile, tmp_path, capsys)

    assert return_code == 1
    assert any(
        "average_pattern_score must equal" in error for error in report["errors"]
    )


def test_boolean_profile_average_is_not_a_number(validate_profile, tmp_path, capsys):
    profile = _profile(validate_profile)
    profile["pattern_profile"]["pattern_baseline"]["pattern_score_sum"] = 2
    profile["pattern_profile"]["pattern_baseline"]["average_pattern_score"] = 1.0
    profile["pattern_profile"]["average_pattern_score"] = True

    return_code, report = _run(validate_profile, profile, tmp_path, capsys)

    assert return_code == 1
    assert any(
        "average_pattern_score must equal" in error for error in report["errors"]
    )


def test_nonempty_profile_requires_complete_nested_schema(
    validate_profile,
    tmp_path,
    capsys,
):
    profile = _profile(validate_profile)
    del profile["pattern_profile"]["pattern_usage"]
    del profile["pattern_profile"]["pattern_breadth"]["note"]

    return_code, report = _run(validate_profile, profile, tmp_path, capsys)

    assert return_code == 1
    assert any(
        "missing required schema-v5 fields" in error for error in report["errors"]
    )
    assert any(
        "pattern_breadth is missing required fields" in error
        for error in report["errors"]
    )


def test_current_profile_rejects_unknown_nested_shape(
    validate_profile,
    tmp_path,
    capsys,
):
    profile = _profile(validate_profile)
    profile["pattern_profile"]["legacy_score"] = 9
    profile["pattern_profile"]["mastery_levels"]["unknown"] = []

    return_code, report = _run(validate_profile, profile, tmp_path, capsys)

    assert return_code == 1
    assert any("unknown schema-v5 fields" in error for error in report["errors"])
    assert any("unknown tiers" in error for error in report["errors"])


def test_nonempty_cohort_rejects_unconfigured_trend_claim(
    validate_profile,
    tmp_path,
    capsys,
):
    profile = _profile(validate_profile)
    profile["pattern_profile"]["score_trend"] = "declining"
    profile["pattern_profile"]["score_drivers"]["direction"] = "declining"

    return_code, report = _run(validate_profile, profile, tmp_path, capsys)

    assert return_code == 1
    assert any("score_trend must project" in error for error in report["errors"])


def test_nested_out_of_denominator_cannot_use_another_cohort(
    validate_profile,
    tmp_path,
    capsys,
):
    profile = _profile(validate_profile)
    profile["pattern_profile"]["pattern_usage"][0]["out_of"] = 4

    return_code, report = _run(validate_profile, profile, tmp_path, capsys)

    assert return_code == 1
    assert any(
        "pattern_profile.pattern_usage[0].out_of" in error for error in report["errors"]
    )


def test_owner_validator_rejects_self_consistent_rows_absent_from_live_vault(
    validate_profile,
    tmp_path,
    capsys,
):
    profile = _profile(validate_profile)
    row = profile["pattern_profile"]["pattern_usage"][0]
    row["detected_count"] = 1
    row["times_used"] = 1
    row["usage_rate"] = 0.5

    return_code, report = _run(validate_profile, profile, tmp_path, capsys)

    assert return_code == 1
    assert any(
        "does not equal the live canonical positive opportunity rows" in error
        for error in report["errors"]
    )


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("pattern_usage", 0, "times_used"), 3, "times_used"),
        (("antipattern_frequency", 0, "times_detected"), -1, "times_detected"),
    ],
)
def test_catalog_counts_must_fit_the_current_cohort(
    validate_profile,
    tmp_path,
    capsys,
    path,
    value,
    message,
):
    profile = _profile(validate_profile)
    profile["pattern_profile"][path[0]][path[1]][path[2]] = value

    return_code, report = _run(validate_profile, profile, tmp_path, capsys)

    assert return_code == 1
    assert any(message in error for error in report["errors"])


def test_per_mode_count_cannot_exceed_global_cohort(
    validate_profile,
    tmp_path,
    capsys,
):
    profile = _profile(validate_profile)
    profile["pattern_profile"]["by_mode"] = [
        {"mode_id": "example", "talks_in_mode": 3, "stable": True}
    ]

    return_code, report = _run(validate_profile, profile, tmp_path, capsys)

    assert return_code == 1
    assert any("by_mode must be []" in error for error in report["errors"])


def test_empty_current_cohort_is_explicitly_unavailable(
    validate_profile,
    tmp_path,
    capsys,
):
    return_code, report = _run(
        validate_profile,
        _profile(validate_profile, count=0),
        tmp_path,
        capsys,
    )

    assert return_code == 0, "\n".join(report["errors"])
    assert report["valid"] is True


def test_empty_current_cohort_rejects_legacy_pattern_fallback(
    validate_profile,
    tmp_path,
    capsys,
):
    profile = _profile(validate_profile, count=0)
    pattern_profile = profile["pattern_profile"]
    pattern_profile["score_trend"] = "stable"
    pattern_profile["mastery_levels"]["signature"] = ["legacy-pattern"]

    return_code, report = _run(validate_profile, profile, tmp_path, capsys)

    assert return_code == 1
    assert any("score_trend must project" in error for error in report["errors"])
    assert any(
        "mastery_levels is not the deterministic projection" in error
        for error in report["errors"]
    )


def test_pattern_baseline_rejects_unknown_fields(validate_profile, tmp_path, capsys):
    profile = copy.deepcopy(_profile(validate_profile))
    profile["pattern_profile"]["pattern_baseline"]["legacy_average"] = 7.0

    return_code, report = _run(validate_profile, profile, tmp_path, capsys)

    assert return_code == 1
    assert "fields are noncanonical" in report["errors"][0]


@pytest.mark.parametrize("duplicate", ["signature_combinations", "mastery_levels"])
def test_rhetoric_defaults_cannot_duplicate_pattern_history(
    validate_profile,
    tmp_path,
    capsys,
    duplicate,
):
    profile = _profile(validate_profile)
    profile["rhetoric_defaults"][duplicate] = [] if duplicate.endswith("s") else {}

    return_code, report = _run(validate_profile, profile, tmp_path, capsys)

    assert return_code == 1
    assert any(
        "rhetoric_defaults duplicates catalog history" in error
        for error in report["errors"]
    )


@pytest.mark.parametrize(
    ("container", "entry"),
    [
        ("recurring_issues", {"id": "ambiguous"}),
        ("recurring_issues", {"id": "pattern-copy", "source_lane": "pattern_catalog"}),
        (
            "badges",
            {
                "id": "pattern-copy",
                "source_lane": "non_pattern",
                "pattern_id": "example",
            },
        ),
    ],
)
def test_catalog_history_cannot_hide_in_top_level_entries(
    validate_profile,
    tmp_path,
    capsys,
    container,
    entry,
):
    profile = _profile(validate_profile)
    if container == "recurring_issues":
        profile["guardrail_sources"][container] = [entry]
    else:
        profile[container] = [entry]

    return_code, report = _run(validate_profile, profile, tmp_path, capsys)

    assert return_code == 1
    assert any(container in error for error in report["errors"])


def test_explicit_non_pattern_entries_remain_available(
    validate_profile,
    tmp_path,
    capsys,
):
    profile = _profile(validate_profile)
    profile["guardrail_sources"]["recurring_issues"] = [
        {
            "id": "pacing-overrun",
            "source_lane": "non_pattern",
            "guardrail": "Leave enough time for the close.",
        }
    ]
    profile["badges"] = [
        {
            "id": "visual-continuity",
            "source_lane": "non_pattern",
            "evidence": "A recurring visual device appears across decks.",
        }
    ]

    return_code, report = _run(validate_profile, profile, tmp_path, capsys)

    assert return_code == 0, report
    assert report["valid"] is True
