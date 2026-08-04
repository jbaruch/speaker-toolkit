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
    filenames = (
        []
        if count == 0
        else ["example-a.md", "example-b.md"]
        if count == 2
        else [f"example-{index:02d}.md" for index in range(count)]
    )
    score_sum = count * 7
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


def _v5_profile(*, recurring_detections: int = 4) -> tuple[dict[str, Any], str]:
    opportunities = importlib.import_module("pattern_opportunities")
    pattern_evidence = importlib.import_module("pattern_evidence")
    provenance = importlib.import_module("profile_pattern_provenance")
    classification_runtime = importlib.import_module("pattern_classification_runtime")
    catalog = opportunities.load_catalog()
    fingerprint, scoring_schema = provenance.active_pattern_generation_identity()
    observable = sorted(
        (pattern_id, entry)
        for pattern_id, entry in catalog.entries.items()
        if entry.observable
    )
    recurring_id = next(
        pattern_id
        for pattern_id, entry in observable
        if entry.entry_type == "antipattern"
    )
    talks = []
    for index in range(8):
        outcomes = []
        positive_detections = []
        negative_detections = []
        for pattern_id, entry in observable:
            outcome = (
                "undetected"
                if entry.absence_evaluable_from is not None
                else "not_evaluable"
            )
            if pattern_id == recurring_id and index < recurring_detections:
                outcome = "detected"
                negative_detections.append({"pattern_id": pattern_id})
            outcomes.append({"pattern_id": pattern_id, "outcome": outcome})
        identity = pattern_evidence.opportunity_coverage_identity(
            outcomes,
            pattern_catalog_fingerprint=fingerprint,
            pattern_scoring_schema_version=scoring_schema,
        )
        talks.append(
            {
                "filename": f"example-{index:02d}.md",
                "date": f"2025-01-{index + 1:02d}",
                "pattern_score": 0,
                "pattern_observations": {
                    "pattern_score": 0,
                    "patterns_detected": positive_detections,
                    "antipatterns_detected": negative_detections,
                    "pattern_outcomes": outcomes,
                    "opportunity_coverage_identity": identity,
                },
            }
        )
    rows = opportunities.build_pattern_opportunity_rows(talks, catalog=catalog)
    policy_stamp = classification_runtime.resolve_classification_policy(
        ROOT / "tests" / "__no_pattern_policy_override__"
    )
    classification = classification_runtime.classify_pattern_profile(
        talks, policy_stamp, catalog=catalog
    )
    profile = {
        "schema_version": 5,
        "pattern_profile": {
            "pattern_baseline": {
                "schema_version": 2,
                "as_of": "2025-01-09T00:00:00+00:00",
                "scope": "global",
                "active_batch_excluded": False,
                "excluded_filenames": [],
                "eligible_statuses": ["processed", "processed_partial"],
                "pattern_scoring_generation_status": "current",
                "pattern_scoring_generation_reasons": [],
                "pattern_catalog_fingerprint": fingerprint,
                "pattern_scoring_schema_version": scoring_schema,
                "scored_talk_count": 8,
                "pattern_score_sum": 0,
                "average_pattern_score": 0.0,
                "eligible_talk_count": 8,
                "opportunity_coverage_identity": talks[0]["pattern_observations"][
                    "opportunity_coverage_identity"
                ],
                "raw_score_comparison_status": "available",
                "raw_score_comparison_reason": None,
            },
            "baseline_talk_filenames": [talk["filename"] for talk in talks],
            "eligible_talk_count": 8,
            "talks_scored": 8,
            "average_pattern_score": 0.0,
            "note": "Observable catalog entries only.",
            "pattern_usage": rows["pattern_usage"],
            "antipattern_frequency": rows["antipattern_frequency"],
            **classification,
        },
    }
    return profile, recurring_id


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
    assert "occurrence-only" in status.reasons[0]
    assert status.available_classification_domains == ()
    assert status.policy_semantic_sha256 is None


def test_v5_enables_each_policy_domain_independently(pattern_history_status):
    profile, _ = _v5_profile()

    status = pattern_history_status.assess_creator_pattern_history(profile)

    assert status.history_enabled is True
    assert status.history_source == "profile"
    assert status.opportunity_rows_available is True
    assert status.classification_fields_available is True
    assert status.available_classification_domains == (
        "antipattern_recurrence",
        "mastery_and_novelty",
        "signature_combinations",
        "underuse",
    )
    assert status.domain_available("mastery_and_novelty") is True
    assert status.domain_available("antipattern_recurrence") is True
    assert status.domain_available("trends") is False
    assert status.domain_available("modes") is False
    assert isinstance(status.policy_semantic_sha256, str)


def test_v5_new_to_you_projection_contains_only_confirmed_never_tried(
    pattern_history_status,
):
    profile, _ = _v5_profile()
    resolution = pattern_history_status.resolve_creator_pattern_history(profile)

    assert resolution.status.domain_available("mastery_and_novelty") is True
    assert resolution.pattern_profile is not None
    pattern_profile = resolution.pattern_profile
    never_tried = pattern_profile["mastery_levels"]["never_tried"]
    assert never_tried
    assert pattern_profile["never_used_patterns"] == never_tried
    classifications = {
        row["pattern_id"]: row["classification"]
        for row in pattern_profile["pattern_classifications"]
    }
    assert all(
        classifications[pattern_id] == "never_tried" for pattern_id in never_tried
    )
    assert not any(
        pattern_id in never_tried
        for pattern_id, classification in classifications.items()
        if classification == "not_yet_observed"
    )


def _section15_summary(pattern_profile: dict[str, Any], *, version: int) -> str:
    section15 = importlib.import_module("section15_pattern_history")
    if version == 3:
        block = section15.render_section15_current_block(pattern_profile)
    else:
        baseline = pattern_profile["pattern_baseline"]
        payload = {
            "schema_version": 2,
            "source_lane": section15.BLOCK_SOURCE_LANE,
            "pattern_catalog_fingerprint": baseline["pattern_catalog_fingerprint"],
            "pattern_scoring_schema_version": baseline[
                "pattern_scoring_schema_version"
            ],
            "baseline_talk_filenames": pattern_profile["baseline_talk_filenames"],
            "pattern_profile": pattern_profile,
        }
        encoded = json.dumps(payload, indent=2, sort_keys=True)
        block = (
            f"{section15.LEGACY_BLOCK_START}\n```json\n{encoded}\n```\n\n"
            f"{section15.NON_BASELINE_NOTICE}\n{section15.LEGACY_BLOCK_END}"
        )
    return f"## 15. Presentation Pattern History\n\n{block}\n"


def test_section15_v3_can_supply_policy_bound_fallback(pattern_history_status):
    profile, _ = _v5_profile()
    summary = _section15_summary(profile["pattern_profile"], version=3)

    status = pattern_history_status.assess_creator_pattern_history(
        _profile(schema_version=4), summary
    )

    assert status.history_enabled is True
    assert status.history_source == "section15_current_block"
    assert status.domain_available("mastery_and_novelty") is True
    assert status.domain_available("trends") is False


def test_section15_v2_remains_occurrence_only(pattern_history_status):
    summary = _section15_summary(_pattern_profile(), version=2)

    status = pattern_history_status.assess_creator_pattern_history(
        {"schema_version": 3}, summary
    )

    assert status.history_enabled is False
    assert status.opportunity_rows_available is True
    assert status.classification_fields_available is False
    assert status.available_classification_domains == ()
    assert "pattern_classification_policy_unavailable" in status.reason_codes


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


def test_status_cli_exposes_independent_policy_domains(
    pattern_history_status,
    tmp_path,
    capsys,
):
    profile, _ = _v5_profile()
    profile_path = tmp_path / "speaker-profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")

    return_code = pattern_history_status.main(
        ["pattern_history_status.py", str(profile_path)]
    )
    payload = json.loads(capsys.readouterr().out)

    assert return_code == 0
    assert payload["history_enabled"] is True
    assert payload["available_classification_domains"] == [
        "antipattern_recurrence",
        "mastery_and_novelty",
        "signature_combinations",
        "underuse",
    ]
    assert isinstance(payload["policy_semantic_sha256"], str)
    assert payload["warning"] == ""


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


def test_guardrail_suppresses_recurring_labels_for_occurrence_only_v4(
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
        "index": (creator / "references" / "patterns" / "_index.md").read_text(
            encoding="utf-8"
        ),
    }


def _normalized_doc(text: str) -> str:
    return " ".join(text.split())


def test_phase_instructions_share_the_independent_domain_gate():
    docs = _creator_docs()

    assert "pattern_history_status.py" in docs["skill"]
    assert "pattern_history_status.py" in docs["phase0"]
    assert "available_classification_domains" in docs["skill"]
    assert "available_classification_domains" in docs["phase0"]
    assert "available_classification_domains" in docs["phase2"]
    assert "available_classification_domains" in docs["phase4"]
    assert "at least one policy-bound domain" in docs["rules"]


def test_docs_keep_nonpattern_and_contextual_lanes_enabled():
    docs = _creator_docs()

    assert 'source_lane: "non_pattern"' in docs["skill"]
    assert 'source_lane: "non_pattern"' in docs["phase0"]
    assert 'source_lane: "non_pattern"' in docs["phase4"]
    assert "current-outline scan always runs" in docs["phase4"]
    assert "Current-taxonomy scans of the new outline remain enabled" in docs["skill"]
    assert "current-outline scan" in docs["index"]


def test_docs_suppress_history_tiers_and_cross_generation_diffs():
    docs = _creator_docs()

    assert "flat current-taxonomy menu" in docs["skill"]
    assert "flat relevant-patterns list" in docs["phase2"]
    assert "generation reset" in docs["skill"]
    assert "generation reset" in docs["phase0"]
    assert "classification-comparison reset" in docs["skill"]
    assert "classification comparison reset" in _normalized_doc(docs["phase0"])
    assert "Neither reset is\never evidence" in docs["rules"]


def test_docs_define_exact_novelty_and_delegate_recurrence_filtering():
    docs = _creator_docs()

    for name in ("skill", "phase2", "rules", "index"):
        assert "never_tried" in docs[name]
        assert "not_yet_observed" in docs[name]
    for name in ("skill", "phase2", "phase4", "rules", "index"):
        assert "recurring_antipatterns" in docs[name]
        assert "high_frequency" not in docs[name]
        assert "moderate_frequency" not in docs[name]
    assert "recurring_pattern_history_items()" in docs["phase4"]
    assert "{action}" not in docs["phase4"]


def test_docs_delegate_history_source_precedence_once():
    docs = _creator_docs()

    for name in ("skill", "phase0", "phase2", "phase4"):
        assert "history_source" in docs[name]
    assert "resolve_creator_pattern_history()" in docs["phase0"]
    assert (
        sum(text.count("resolve_creator_pattern_history()") for text in docs.values())
        == 1
    )


def test_docs_distinguish_occurrence_only_and_policy_bound_contracts():
    docs = _creator_docs()

    for name in ("skill", "phase0", "phase2", "rules"):
        normalized = _normalized_doc(docs[name])
        assert "schema v4" in normalized.lower()
        assert "schema v5" in normalized.lower()
        assert "Section 15 v2" in normalized
        assert "Section 15 v3" in normalized


def test_pattern_strategy_eval_fails_closed_on_deliberately_legacy_provenance():
    task = (ROOT / "evals" / "pattern-strategy-4-tier" / "task.md").read_text(
        encoding="utf-8"
    )
    criteria = json.loads(
        (ROOT / "evals" / "pattern-strategy-4-tier" / "criteria.json").read_text(
            encoding="utf-8"
        )
    )

    assert "installed creator requires speaker-profile schema\n`5`" in task
    assert "pattern-scoring schema `5`" in task
    assert "schema v4 remains occurrence-only" in task
    assert "speaker-toolkit-default@1" in task
    assert '"schema_version": 4' in task
    assert '"pattern_scoring_schema_version": 4' in task
    assert "occurrence-compatible speaker-profile schema `4`" in task
    assert '"pattern_catalog_fingerprint": "' + ("a" * 64) + '"' in task
    assert '"baseline_talk_filenames"' in task
    assert sum(item["max_score"] for item in criteria["checklist"]) == 100
    assert criteria["checklist"][0]["name"] == "Legacy provenance fails closed"
    assert "history-disabled" in criteria["checklist"][0]["description"]
    assert any(
        item["name"] == "No catalog recurrence from raw rows"
        for item in criteria["checklist"]
    )
