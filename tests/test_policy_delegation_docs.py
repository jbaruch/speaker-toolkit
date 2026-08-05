"""Regression guards for prose that delegates policy-owned decisions to scripts."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_profile_skill_treats_owner_validator_as_black_box() -> None:
    skill = _read("skills/vault-profile/SKILL.md")

    assert "scripts/validate-profile.py" in skill
    assert "sole owner-validation contract" in skill
    assert "Write nothing unless the command exits `0`" in skill
    for internal_narration in (
        "same shared cohort/classification builders",
        "rejects any candidate baseline",
        "policy stamp/digest, availability domain, or derived row",
    ):
        assert internal_narration not in skill


def test_ingress_delegates_section15_assessment_and_replacement() -> None:
    rules = _read("skills/vault-ingress/references/processing-rules.md")

    assert 'section15_pattern_history.py" assess' in rules
    assert 'section15_pattern_history.py" replace' in rules
    assert "On exit `1`, it emits a diagnostic to stderr and makes no write" in rules
    for classifier_owned_predicate in (
        "For every Section 15 current-block count",
        "zero detections become",
        "recomputes the full current cohort from the database",
        "trends and modes are independently",
        "mixed identities make raw-score",
        "apply the same exact current-generation filter",
    ):
        assert classifier_owned_predicate not in rules


def test_speaker_profile_eval_requires_opaque_loader_outputs() -> None:
    task = _read("evals/speaker-profile-from-vault/task.md")
    criteria = json.loads(_read("evals/speaker-profile-from-vault/criteria.json"))
    descriptions = "\n".join(item["description"] for item in criteria["checklist"])

    assert "scripts/load-vault.py" in task
    assert "opaque fixture" in task
    assert "pattern_classification object emitted by load-vault.py" in descriptions
    assert (
        "uses only current_instrumentation_talks emitted by load-vault.py"
        in descriptions
    )
    assert "contains at least one field with a numeric value" not in descriptions
    for hardcoded_verdict in (
        "mastery/novelty, antipattern-recurrence",
        "trends and modes remain explicitly unavailable",
        "Mastery/novelty, antipattern recurrence, underuse, and combinations",
    ):
        assert hardcoded_verdict not in task
        assert hardcoded_verdict not in descriptions
