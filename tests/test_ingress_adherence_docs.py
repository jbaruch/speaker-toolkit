"""Documentation guards for live claim-v5 and archival-v4 adherence."""

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
    return {name: path.read_text(encoding="utf-8") for name, path in DOC_PATHS.items()}


def test_claim_issuance_is_live_and_version_bound() -> None:
    docs = _docs()
    for name, text in docs.items():
        assert "#157" not in text, f"{name} still carries the temporary issue gate"
        assert "issuance pause" not in text.lower()

    assert '"schema_version": 5' in docs["queue"]
    assert '"required_return_schema_version": 5' in docs["queue"]
    assert '"adherence_baseline": {"schema_version": 2' in docs["queue"]
    assert "Fresh claims always use schema v5 and require return v5" in docs["queue"]
    assert (
        "Saved claim schemas v1/v2 authorize only return schemas v1/v2"
        in docs["schemas"]
    )
    assert "schema v3 authorizes only v3; schema v4 authorizes only archival v4" in docs[
        "schemas"
    ]
    assert "Recover a live legacy lease" in docs["worker"]


def test_workers_use_the_immutable_claim_baseline_not_section_15() -> None:
    docs = _docs()
    assert "MUST NOT\nparse Section 15 for numeric adherence" in docs["skill"]
    assert "MUST NOT be\nparsed for numeric adherence" in docs["worker"]
    assert "the claim baseline remains immutable" in docs["processing"]
    assert "Workers MUST\nNOT parse Section 15" in docs["processing"]
    assert "adherence_baseline.as_of` to equal" in docs["schemas"]
    assert (
        "exclusion happens before generation identity or score inspection"
        in docs["schemas"]
    )


def test_threshold_and_structured_comparison_contract_is_documented() -> None:
    docs = _docs()
    for name in ("skill", "processing", "schemas", "worker"):
        assert "adherence_comparison" in docs[name]
        assert "legacy-unverified" in docs[name]

    assert "fewer than 10 `scored_talk_count`" in docs["processing"]
    assert "at least 10 scored talks" in docs["processing"]
    assert "exact empty adherence sentinel" in docs["processing"]
    assert "2–4 punctuation-terminated sentences" in docs["processing"]
    assert "Validators deliberately do not parse prose" in docs["processing"]
    assert "renderer generates this anchor mechanically" in docs["processing"]
    assert '"return_schema_version": 5' in docs["schemas"]
    assert '"return_schema_version": 5' in docs["worker"]


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
    assert (
        "Idempotent replay returns the\nstored claim and leaves DB bytes unchanged"
        in docs["schemas"]
    )
    assert "Recovery never rewrites a claim snapshot" in docs["schemas"]
    assert (
        "closes v1 as v2 and closes v2–v5 at\ntheir own versions" in docs["schemas"]
    )
    assert "receiptless completed v1 claim" in docs["skill"]
    assert "takes a fresh pre-mutation snapshot" in docs["skill"]


def test_archival_v4_and_current_v5_evidence_generations_are_distinct() -> None:
    docs = _docs()
    assert "Two incompatible v3 lineages were emitted" in docs["schemas"]
    assert "v4 is their source-located union and remains archival" in docs["schemas"]


    assert '"pattern_scoring_schema_version": 5' in docs["schemas"]
    assert '"evidence_schema_version": 2' in docs["schemas"]
    assert "pattern_outcomes" in docs["worker"]
    assert "opportunity_coverage_identity" in docs["worker"]

    for name in ("skill", "processing", "schemas", "worker"):
        assert "evidence_source" in docs[name]
        assert "evidence_citations" in docs[name]

    assert "Pattern Evidence Citation Schema" in docs["schemas"]
    assert "source_comparison" in docs["processing"]
    assert "every underlying member" in docs["processing"]
    assert "cannot replace its qualifying source/outcome gate" in docs["worker"]
    assert '"evidence_schema_version": 1' not in docs["worker"]
    assert "writer-owned persisted state" in docs["schemas"]
    assert '"source": "transcript"' in docs["worker"]
    assert '"channel": "transcript"' in docs["worker"]


def test_canonical_coverage_alone_never_authorizes_current_absence() -> None:
    docs = _docs()
    schemas = docs["schemas"]

    assert "V4\nabsence remains archival and is never current" in schemas
    assert (
        "complete canonical\ninspection coverage is necessary but never sufficient to authorize absence"
        in schemas
    )
    assert "`absence_capability_complete: true`" in schemas
    assert "`absence_evaluable_from` singleton gate" in schemas
    assert (
        "V4/v5\nabsence is authorized only by complete canonical inspection coverage"
        not in schemas
    )


def test_current_v5_cohort_requires_live_artifact_freshness() -> None:
    docs = _docs()
    assert "shared freshness assessor" in docs["skill"]
    assert "configured source roots" in docs["skill"]
    assert "artifact freshness against the vault" in docs["processing"]
    assert "shared root-aware assessor" in docs["skill"]
    assert "remote video/slide acquisition remains eligible" in docs["skill"]


def test_source_located_receipt_is_public_and_range_bound() -> None:
    docs = _docs()
    for name in ("skill", "processing", "schemas", "worker"):
        assert "source_inspection" in docs[name]

    for field in ("line_ranges", "page_ranges", "time_ranges"):
        assert field in docs["schemas"]
        assert field in docs["worker"]

    assert 'comparison_scope: "full"|"partial"' in docs["processing"]
    assert "Multiple\n  comparison records" in docs["processing"]
    assert "may be adjacent but may not overlap" in docs["processing"]
    assert "has no gaps" in docs["processing"]
    assert "Artifact coexistence without actual comparison" in docs["worker"]


def test_source_located_worker_and_engine_evidence_ownership_is_explicit() -> None:
    docs = _docs()
    assert "Those are the complete worker-side shapes" in docs["schemas"]
    assert "must not copy `line_start`, `line_end`" in docs["schemas"]
    assert "metadata `value`/`owner_value_after_return`" in docs["worker"]
    assert "persistence derives" in docs["skill"]
    assert "artifact roots/paths/hashes" in docs["skill"]
    assert "raw-return receipt remains the\nhash of exactly what the worker sent" in docs[
        "schemas"
    ]
    assert "non-English `delivery_language`" in docs["worker"]
    assert "non-empty\nEnglish `translation` is required" in docs["schemas"]

    schema_example = docs["schemas"].split(
        "Each subagent returns this JSON after processing one talk:", 1
    )[1].split("```json", 1)[1].split("```", 1)[0]
    worker_example = docs["worker"].split(
        "Minimal processed structure for a fresh v5 claim", 1
    )[1].split("```json", 1)[1].split("```", 1)[0]
    for raw_example in (schema_example, worker_example):
        for engine_field in (
            '"artifact_root"',
            '"artifact_path"',
            '"artifact_sha256"',
            '"coverage_complete"',
            '"absence_capability_complete"',
            '"absence_capability_reason"',
            '"evidence_schema_version"',
            '"pattern_outcomes"',
            '"opportunity_coverage_identity"',
            '"line_count"',
            '"page_count"',
            '"dimensions"',
        ):
            assert engine_field not in raw_example


def test_source_located_not_evaluable_is_reason_code_only_and_fail_closed() -> None:
    docs = _docs()
    for name in ("skill", "processing", "schemas", "worker"):
        assert "source_gate_pending_owner_review" in docs[name]
    for name in ("processing", "schemas", "worker"):
        assert "missing_required_source_coverage" in docs[name]
    assert "fails closed" in docs["processing"]
    assert "fail-closed" in docs["schemas"]
    assert "fails closed" in docs["worker"]

    assert "contains exactly `pattern_id` and `reason_code`" in docs[
        "processing"
    ]
    assert "prose-bearing" in docs["processing"]


def test_claim_return_talk_and_scoring_axes_preserve_archival_v4() -> None:
    docs = _docs()
    assert "The four version axes are deliberately explicit" in docs["schemas"]
    assert "| v4 | v4 only | archival source-located v4 | never current v5 |" in docs[
        "schemas"
    ]
    assert "| v5 | v5 only | v5 | v5 when canonical evidence/outcomes are fresh |" in docs[
        "schemas"
    ]
    assert "Saved claim schemas\nv1–v4 authorize only their same-numbered return schemas" in docs[
        "skill"
    ]
    assert "only return generation eligible for pattern-scoring schema v5" in docs[
        "skill"
    ]


def test_transcript_freshness_revalidates_quality_provenance() -> None:
    docs = _docs()
    assert "hash-bound quality policy against current owner/provider duration" in docs[
        "skill"
    ]
    assert "transcript_quality_context_drift" in docs["schemas"]
