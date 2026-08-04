"""Documentation guards for generation-bound coaching goals."""

from pathlib import Path


ROOT = Path(__file__).parents[1]
SKILL = (ROOT / "skills" / "vault-clarification" / "SKILL.md").read_text()
SCHEMA = (
    ROOT / "skills" / "vault-clarification" / "references" / "schemas-config.md"
).read_text()
INGRESS = (ROOT / "skills" / "vault-ingress" / "SKILL.md").read_text()
PROCESSING = (
    ROOT / "skills" / "vault-ingress" / "references" / "processing-rules.md"
).read_text()


def test_owner_creates_generation_bound_schema_v2_pattern_goals():
    assert "schema-v2 `improvement_goals`" in SKILL
    assert "pattern_profile.pattern_baseline" in SKILL
    assert "Never\nparse the numeric baseline" in SKILL
    assert "`supersedes_goal_id` points to it" in SKILL
    assert '"schema_version": 2' in SCHEMA
    assert '"lane": "pattern_scoring"' in SCHEMA
    assert '"pattern_scoring_schema_version": 5' in SCHEMA
    assert '"opportunity_coverage_identity"' in SCHEMA


def test_owner_keeps_pacing_and_pattern_provenance_separate():
    assert "`pacing` uses the separate `pacing`\nlane" in SKILL
    assert "Pacing/independent records omit\n  `pattern_baseline`" in SCHEMA
    assert "An `other` goal cannot be used to evade pattern provenance" in SCHEMA


def test_reader_runs_mechanical_gate_and_never_scores_mismatch():
    script = "skills/vault-clarification/scripts/goal_generation_provenance.py"
    assert script in SKILL
    assert script in INGRESS
    assert '`"{python_path}"' in SKILL
    assert '"{python_path}"' in INGRESS
    assert "needs_rebaseline" in PROCESSING
    assert "must not set `status` to\n  `achieved`" in PROCESSING


def test_owner_documents_goal_gate_cli_contract():
    assert '"goals": [<candidate-goal-object>]' in SKILL
    assert '"current_pattern_baseline": <pattern_profile.pattern_baseline' in SKILL
    assert '"schema_version": 1, "assessments":' in SKILL
    assert "Require exit 0 and one assessment for the candidate" in SKILL
    assert 'Write the candidate only for\n`"comparable": true`' in SKILL
    assert "violation exits 1, writes no stdout" in SKILL
    assert "`ERROR: <diagnostic>` to stderr" in SKILL


def test_legacy_pattern_goal_is_read_only_until_speaker_rebaseline():
    assert "schema-v1 pattern goal is historical and unverifiable" in SKILL
    assert (
        "Existing schema-v1 `antipattern`/`underuse` goals remain read-only" in SCHEMA
    )
    assert "preserve the old record, retire it" in SCHEMA
