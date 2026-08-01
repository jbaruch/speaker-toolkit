"""Documentation guards for the live claim-v3 adherence workflow."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
INGRESS = REPO_ROOT / "skills" / "vault-ingress"
DOC_PATHS = {
    "skill": INGRESS / "SKILL.md",
    "processing": INGRESS / "references" / "processing-rules.md",
    "schemas": INGRESS / "references" / "schemas-db.md",
    "worker": INGRESS / "references" / "subagent-instructions.md",
    "queue": INGRESS / "scripts" / "queue-state.py",
}


def _docs() -> dict[str, str]:
    return {
        name: path.read_text(encoding="utf-8")
        for name, path in DOC_PATHS.items()
    }


def test_claim_issuance_is_live_and_version_bound() -> None:
    docs = _docs()
    for name, text in docs.items():
        assert "#157" not in text, f"{name} still carries the temporary issue gate"
        assert "issuance pause" not in text.lower()

    assert '"schema_version": 3' in docs["queue"]
    assert '"required_return_schema_version": 3' in docs["queue"]
    assert "Fresh claims always use schema v3 and require return v3" in docs["queue"]
    assert "Claim schemas v1/v2 authorize return schemas v1/v2 only" in docs["schemas"]
    assert "Never attach return v3 to a legacy claim" in docs["worker"]


def test_workers_use_the_immutable_claim_baseline_not_section_15() -> None:
    docs = _docs()
    assert "MUST NOT\nparse Section 15 for numeric adherence" in docs["skill"]
    assert "MUST NOT be\nparsed for numeric adherence" in docs["worker"]
    assert "only numeric authority is the immutable" in docs["processing"]
    assert "Workers MUST NOT parse Section 15" in docs["processing"]
    assert "adherence_baseline.as_of` to equal" in docs["schemas"]
    assert "exclusion happens before generation identity or score inspection" in \
        docs["schemas"]


def test_threshold_and_structured_comparison_contract_is_documented() -> None:
    docs = _docs()
    for name in ("skill", "processing", "schemas", "worker"):
        assert "adherence_comparison" in docs[name]
        assert "legacy-unverified" in docs[name]

    assert "Fewer than 10 talks" in docs["processing"]
    assert "10 or more talks" in docs["processing"]
    assert "exact empty string" in docs["processing"]
    assert "2–4 punctuation-terminated sentences" in docs["processing"]
    assert "Validators deliberately do not parse prose" in docs["processing"]
    assert "renderer generates this anchor mechanically" in docs["processing"]
    assert '"return_schema_version": 3' in docs["schemas"]
    assert '"return_schema_version": 3' in docs["worker"]


def test_post_batch_cohort_and_section_15_filter_are_explicit() -> None:
    docs = _docs()
    for name in ("skill", "processing", "schemas"):
        assert "current_adherence_baseline" in docs[name]
        assert "active_batch_excluded: false" in docs[name]

    assert "only after every merge succeeds" in docs["processing"]
    assert "Never approximate this cohort by\n`processed_date`" in docs["processing"]
    assert "after the entire batch has persisted successfully" in docs["processing"]
    assert "never rebuild after member 1" in docs["skill"]
    assert "must not recompute after member 1" in docs["schemas"]


def test_claim_replay_recovery_and_closure_matrix_are_documented() -> None:
    docs = _docs()
    assert "Idempotent replay returns the\nstored claim and leaves DB bytes unchanged" in \
        docs["schemas"]
    assert "Recovery never rewrites a claim snapshot" in docs["schemas"]
    assert "closes v1 as v2, v2 as v2, and v3 as v3" in docs["schemas"]
    assert "receiptless completed v1 claim" in docs["skill"]
    assert "takes a fresh pre-mutation snapshot" in docs["skill"]
