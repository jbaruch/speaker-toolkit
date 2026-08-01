"""Fail-closed creator tests for exact-generation pattern history."""

from __future__ import annotations

import copy
import importlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT / "skills" / "presentation-creator" / "scripts" / "pattern_history_status.py"
)
OUTLINE = Path(__file__).parent / "fixtures" / "outline-example.yaml"


@pytest.fixture(scope="module")
def pattern_history_status():
    spec = importlib.util.spec_from_file_location("pattern_history_status", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _pattern_profile(*, count: int = 2) -> dict[str, Any]:
    provenance = importlib.import_module("profile_pattern_provenance")
    opportunities = importlib.import_module("pattern_opportunities")
    pattern_evidence = importlib.import_module("pattern_evidence")
    fingerprint, scoring_schema = provenance.active_pattern_generation_identity()
    filenames = [] if count == 0 else ["example-a.md", "example-b.md"]
    score_sum = 0 if count == 0 else 14
    average = None if count == 0 else 7.0
    catalog = opportunities.load_catalog()
    observable_ids = sorted(
        pattern_id for pattern_id, entry in catalog.entries.items() if entry.observable
    )
    outcome_talks = []
    for filename in filenames:
        pattern_outcomes = [
            {"pattern_id": pattern_id, "outcome": "undetected"}
            for pattern_id in observable_ids
        ]
        outcome_talks.append(
            {
                "filename": filename,
                "pattern_observations": {
                    "patterns_detected": [],
                    "antipatterns_detected": [],
                    "pattern_outcomes": pattern_outcomes,
                },
            }
        )
    rows = opportunities.build_pattern_opportunity_rows(
        outcome_talks,
        catalog=catalog,
    )
    opportunity_identity = (
        pattern_evidence.opportunity_coverage_identity(
            outcome_talks[0]["pattern_observations"]["pattern_outcomes"],
            pattern_catalog_fingerprint=fingerprint,
            pattern_scoring_schema_version=scoring_schema,
        )
        if count
        else None
    )
    return {
        "pattern_baseline": {
            "schema_version": 2,
            "as_of": "2025-01-02T03:04:05+00:00",
            "scope": "global",
            "active_batch_excluded": False,
            "excluded_filenames": [],
            "eligible_statuses": ["processed", "processed_partial"],
            "pattern_scoring_generation_status": "current",
            "pattern_scoring_generation_reasons": [],
            "pattern_catalog_fingerprint": fingerprint,
            "pattern_scoring_schema_version": scoring_schema,
            "scored_talk_count": count,
            "pattern_score_sum": score_sum,
            "average_pattern_score": average,
            "eligible_talk_count": count,
            "opportunity_coverage_identity": opportunity_identity,
            "raw_score_comparison_status": ("available" if count else "unavailable"),
            "raw_score_comparison_reason": (None if count else "empty_current_cohort"),
        },
        "baseline_talk_filenames": filenames,
        "eligible_talk_count": count,
        "talks_scored": count,
        "average_pattern_score": average,
        "score_trend": "unavailable",
        "pattern_breadth": {
            "avg_distinct_patterns_per_talk": None,
            "trend": "unavailable",
            "note": "Exact current cohort.",
        },
        "underused_patterns": [],
        "score_drivers": {
            "direction": "unavailable",
            "antipattern_drivers": [],
            "pattern_drivers": [],
            "note": "Exact current cohort.",
        },
        "by_mode": [],
        "strengths": [],
        "strengths_note": "Exact current cohort.",
        "note": "Observable catalog entries only.",
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


def _profile(*, schema_version: int = 4, count: int = 2) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "pattern_profile": _pattern_profile(count=count),
    }


def test_matching_v4_rows_suppress_unconfigured_classifications(
    pattern_history_status,
):
    status = pattern_history_status.assess_creator_pattern_history(_profile())

    assert status.history_enabled is False
    assert status.opportunity_rows_available is True
    assert status.classification_fields_available is False
    assert status.scored_talk_count == 2
    assert status.eligible_talk_count == 2
    assert status.reason_codes == ("pattern_classification_policy_unavailable",)
    assert "owner thresholds" in status.reasons[0]


@pytest.mark.parametrize("schema_version", [1, 2, 3])
def test_legacy_profile_schema_disables_only_history(
    pattern_history_status,
    schema_version,
):
    profile = _profile(schema_version=schema_version)
    profile["publishing_process"] = {"export_method": "still-usable"}

    status = pattern_history_status.assess_creator_pattern_history(profile)

    assert status.history_enabled is False
    assert status.reason_codes == (
        pattern_history_status.REASON_PROFILE_SCHEMA_MISMATCH,
    )
    assert profile["publishing_process"] == {"export_method": "still-usable"}
    assert "Regenerate speaker-profile.json" in (
        pattern_history_status.disabled_history_warning(status)
    )


@pytest.mark.parametrize(
    ("field", "value", "reason_constant"),
    [
        (
            "pattern_catalog_fingerprint",
            "0" * 64,
            "REASON_CATALOG_FINGERPRINT_MISMATCH",
        ),
        (
            "pattern_scoring_schema_version",
            2,
            "REASON_SCORING_SCHEMA_MISMATCH",
        ),
    ],
)
def test_wrong_generation_identity_disables_history_with_shared_reason(
    pattern_history_status,
    field,
    value,
    reason_constant,
):
    profile = _profile()
    profile["pattern_profile"]["pattern_baseline"][field] = value
    provenance = importlib.import_module("profile_pattern_provenance")

    status = pattern_history_status.assess_creator_pattern_history(profile)

    assert status.history_enabled is False
    assert getattr(provenance, reason_constant) in status.reason_codes
    assert status.reasons


def test_inconsistent_cohort_disables_history_with_exact_error(
    pattern_history_status,
):
    profile = _profile()
    profile["pattern_profile"]["baseline_talk_filenames"] = ["example-a.md"]
    provenance = importlib.import_module("profile_pattern_provenance")

    status = pattern_history_status.assess_creator_pattern_history(profile)

    assert status.history_enabled is False
    assert provenance.REASON_INVALID_CONTRACT in status.reason_codes
    assert status.reasons == (
        "pattern_profile.baseline_talk_filenames length must equal "
        "pattern_baseline.eligible_talk_count 2, got 1",
    )


def test_missing_pattern_profile_fails_closed(pattern_history_status):
    status = pattern_history_status.assess_creator_pattern_history(
        {"schema_version": 4, "pacing": {"still": "usable"}}
    )
    provenance = importlib.import_module("profile_pattern_provenance")

    assert status.history_enabled is False
    assert status.reason_codes == (provenance.REASON_INVALID_CONTRACT,)
    assert status.reasons == ("pattern_profile must be an object",)


def test_empty_current_cohort_is_current_but_history_disabled(
    pattern_history_status,
):
    status = pattern_history_status.assess_creator_pattern_history(_profile(count=0))
    provenance = importlib.import_module("profile_pattern_provenance")

    assert status.history_enabled is False
    assert status.scored_talk_count == 0
    assert status.reason_codes == (
        provenance.REASON_EMPTY_CURRENT_COHORT,
        provenance.REASON_CLASSIFICATION_POLICY_UNAVAILABLE,
    )
    assert "no talks in the active catalog" in status.reasons[0]


def test_status_cli_emits_machine_readable_disabled_state(
    pattern_history_status,
    tmp_path,
    capsys,
):
    profile_path = tmp_path / "speaker-profile.json"
    profile_path.write_text(json.dumps(_profile(schema_version=2)), encoding="utf-8")

    return_code = pattern_history_status.main(
        ["pattern_history_status.py", str(profile_path)]
    )
    payload = json.loads(capsys.readouterr().out)

    assert return_code == 0
    assert payload["history_enabled"] is False
    assert payload["reason_codes"] == ["profile_schema_version_mismatch"]
    assert "Regenerate speaker-profile.json" in payload["warning"]


def _guardrail_profile(*, current_history: bool) -> dict[str, Any]:
    profile = _profile(schema_version=4 if current_history else 2)
    source_lane = {"source_lane": "non_pattern"} if current_history else {}
    profile.update(
        {
            "rhetoric_defaults": {
                "modular_design": False,
                "profanity_calibration": "verbal-only — never on slides",
            },
            "guardrail_sources": {
                "slide_budgets": [
                    {"duration_minutes": 30, "max_slides": 5},
                ],
                "act1_ratio_limits": [{"max_percentage": 45}],
                "recurring_issues": [
                    {
                        "id": "legacy-issue-sentinel",
                        "guardrail": "do not leak",
                        **source_lane,
                    },
                ],
            },
            "design_rules": {"footer": {"elements": []}},
            "badges": [{"id": "legacy-badge-sentinel", **source_lane}],
        }
    )
    return profile


def test_guardrail_keeps_nonpattern_checks_and_contextual_scan_when_history_disabled(
    guardrail_check,
    tmp_path,
    capsys,
):
    profile_path = tmp_path / "speaker-profile.json"
    profile_path.write_text(
        json.dumps(_guardrail_profile(current_history=False)),
        encoding="utf-8",
    )

    return_code = guardrail_check.main(
        ["guardrail-check.py", str(OUTLINE), str(profile_path)]
    )
    report = json.loads(capsys.readouterr().out)
    checks = {item["name"]: item for item in report["checks"]}

    assert return_code == 0
    assert checks["Slide budget"]["status"] == "FAIL"
    assert checks["Slide budget"]["detail"].startswith("11/5")
    assert report["contextual_taxonomy_scan"]["enabled"] is True
    assert report["pattern_history"]["suppressed_fields"]
    assert report["recurring_antipatterns"] == []
    assert "history-antipattern-sentinel" not in json.dumps(report)
    assert "legacy-issue-sentinel" not in json.dumps(report)
    assert "legacy-badge-sentinel" not in json.dumps(report)


def test_guardrail_suppresses_recurring_labels_without_owner_policy(
    guardrail_check,
    tmp_path,
    capsys,
):
    profile = _guardrail_profile(current_history=True)
    profile_path = tmp_path / "speaker-profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")

    return_code = guardrail_check.main(
        ["guardrail-check.py", str(OUTLINE), str(profile_path)]
    )
    report = json.loads(capsys.readouterr().out)
    checks = {item["name"]: item for item in report["checks"]}

    assert return_code == 0
    assert checks["Pattern history"]["status"] == "WARN"
    assert "Pattern classifications disabled" in checks["Pattern history"]["detail"]
    assert report["recurring_antipatterns"] == []


def test_assessment_does_not_mutate_profile(pattern_history_status):
    profile = _profile()
    before = copy.deepcopy(profile)

    pattern_history_status.assess_creator_pattern_history(profile)

    assert profile == before


def _creator_docs() -> dict[str, str]:
    creator = ROOT / "skills" / "presentation-creator"
    return {
        "skill": (creator / "SKILL.md").read_text(encoding="utf-8"),
        "phase0": (creator / "references" / "phase0-intake.md").read_text(
            encoding="utf-8"
        ),
        "phase2": (creator / "references" / "phase2-architecture.md").read_text(
            encoding="utf-8"
        ),
        "phase4": (creator / "references" / "phase4-guardrails.md").read_text(
            encoding="utf-8"
        ),
        "rules": (ROOT / "rules" / "guardrail-rules.md").read_text(encoding="utf-8"),
    }


def test_phase_instructions_share_the_fail_closed_history_gate():
    docs = _creator_docs()

    assert "pattern_history_status.py" in docs["skill"]
    assert "pattern_history_status.py" in docs["phase0"]
    assert "history_enabled: true" in docs["phase2"]
    assert "history is disabled" in docs["phase4"]
    assert "history_enabled: true" in docs["rules"]


def test_docs_keep_nonpattern_and_contextual_lanes_enabled():
    docs = _creator_docs()

    assert 'source_lane: "non_pattern"' in docs["skill"]
    assert 'source_lane: "non_pattern"' in docs["phase0"]
    assert 'source_lane: "non_pattern"' in docs["phase4"]
    assert "current-outline scan always runs" in docs["phase4"]
    assert "Current-taxonomy scans of the new outline remain enabled" in docs["skill"]


def test_docs_suppress_history_tiers_and_cross_generation_diffs():
    docs = _creator_docs()

    assert "flat current-taxonomy menu" in docs["skill"]
    assert "without the four\nhistory tiers" in docs["phase2"]
    assert "generation reset" in docs["skill"]
    assert "generation reset" in docs["phase0"]
    assert "never evidence of improvement or regression" in docs["rules"]


def test_pattern_strategy_eval_fails_closed_on_deliberately_legacy_provenance():
    task = (ROOT / "evals" / "pattern-strategy-4-tier" / "task.md").read_text(
        encoding="utf-8"
    )
    criteria = json.loads(
        (ROOT / "evals" / "pattern-strategy-4-tier" / "criteria.json").read_text(
            encoding="utf-8"
        )
    )

    assert "installed creator requires speaker-profile schema\n`4`" in task
    assert "pattern-scoring schema `5`" in task
    assert '"schema_version": 3' in task
    assert '"pattern_scoring_schema_version": 4' in task
    assert "deliberately stale" in task
    assert '"pattern_catalog_fingerprint": "' + ("a" * 64) + '"' in task
    assert '"baseline_talk_filenames"' in task
    assert sum(item["max_score"] for item in criteria["checklist"]) == 100
    assert criteria["checklist"][0]["name"] == "Legacy provenance fails closed"
    assert "history-disabled" in criteria["checklist"][0]["description"]
    assert any(item["name"] == "No recurring labels" for item in criteria["checklist"])
