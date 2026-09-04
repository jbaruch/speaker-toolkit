"""Documentation guards for current and archival claim generations."""

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
INGRESS = REPO_ROOT / "skills" / "vault-ingress"

DOC_PATHS = {
    "skill": INGRESS / "SKILL.md",
    "bootstrap": INGRESS / "references" / "bootstrap-and-preflight.md",
    "persistence": INGRESS / "references" / "batch-persistence.md",
    "selection": INGRESS / "references" / "queue-selection.md",
    "processing": INGRESS / "references" / "processing-rules.md",
    "schemas": INGRESS / "references" / "schemas-db.md",
    "worker": INGRESS / "references" / "subagent-instructions.md",
    "queue": INGRESS / "scripts" / "queue-state.py",
}


def _docs() -> dict[str, str]:
    return {name: path.read_text(encoding="utf-8") for name, path in DOC_PATHS.items()}


def _schema_current_return_example() -> dict:
    text = DOC_PATHS["schemas"].read_text(encoding="utf-8")
    section = text.split("## Per-Talk Subagent Return Schema", 1)[1]
    payload = section.split("```json", 1)[1].split("```", 1)[0]
    return json.loads(payload)


def test_claim_issuance_is_live_and_version_bound() -> None:
    docs = _docs()
    for name, text in docs.items():
        assert "#157" not in text, f"{name} still carries the temporary issue gate"
        assert "issuance pause" not in text.lower()

    assert '"schema_version": 7' in docs["queue"]
    assert '"required_return_schema_version": 7' in docs["queue"]
    assert '"adherence_baseline": {"schema_version": 2' in docs["queue"]
    assert "Fresh claims always use schema v7 and require return v7" in docs["queue"]
    assert (
        "Saved claim schemas v1/v2 authorize only return schemas v1/v2"
        in docs["schemas"]
    )
    assert (
        "schema v3 authorizes only v3; schema v4 authorizes only archival v4; "
        "schema v5\nauthorizes only v5; schema v6 authorizes only v6" in docs["schemas"]
    )
    assert "Recover a live legacy lease" in docs["worker"]


def test_source_video_preflight_requires_the_supervised_runtime_lane() -> None:
    docs = _docs()
    bootstrap = docs["bootstrap"]

    runtime_gate = "--lanes core,source-video --require-lanes core,source-video"
    assert runtime_gate in bootstrap
    assert bootstrap.index(runtime_gate) < bootstrap.index("scripts/preflight-vault.py")
    assert "Do not pre-open, hash, hydrate, or invoke `ffprobe` directly" in bootstrap
    assert "disables only source-video evidence" in bootstrap
    for field in (
        "structured_data.video_extraction.source_video_path",
        "video_local_path",
        "video_path",
    ):
        assert field in bootstrap
        assert field in docs["skill"]
    assert (
        "independently\nverified transcript, rendered-PDF, or native-PPTX evidence"
        in bootstrap
    )
    assert "references/bootstrap-and-preflight.md" in docs["skill"]


def test_returned_source_video_requires_runtime_gate_before_persistence() -> None:
    docs = _docs()
    persistence = docs["persistence"]

    runtime_gate = "--lanes core,source-video --require-lanes core,source-video"
    assert runtime_gate in persistence
    assert persistence.index(runtime_gate) < persistence.index("persist-results.py")
    for field in (
        "structured_data.video_extraction.source_video_path",
        "video_local_path",
        "video_path",
    ):
        assert field in persistence
        assert field in docs["skill"]
    assert "validation, persistence, and analysis rendering" in persistence
    assert "references/batch-persistence.md" in docs["skill"]


def test_workers_use_the_immutable_claim_baseline_not_section_15() -> None:
    docs = _docs()
    assert "references/subagent-instructions.md" in docs["skill"]
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
    for name in ("processing", "schemas", "worker"):
        assert "adherence_comparison" in docs[name]
        assert "legacy-unverified" in docs[name]
    assert "references/processing-rules.md" in docs["skill"]

    assert "fewer than 10 `scored_talk_count`" in docs["processing"]
    assert "at least 10 scored talks" in docs["processing"]
    assert "exact empty adherence sentinel" in docs["processing"]
    assert "2–4 punctuation-terminated sentences" in docs["processing"]
    assert "Validators deliberately do not parse prose" in docs["processing"]
    assert "renderer generates this anchor mechanically" in docs["processing"]
    assert '"return_schema_version": 7' in docs["schemas"]


def test_schema_worker_example_delegates_weighted_score_completion() -> None:
    schemas = _docs()["schemas"]
    example = _schema_current_return_example()

    assert "pattern_score" not in example["pattern_observations"]
    assert "pattern_score_basis" not in example["pattern_observations"]
    assert "scripts/build-score-basis.py" in schemas
    assert "inserts `pattern_score` and `pattern_score_basis`" in schemas


def test_native_picture_render_threshold_is_script_owned() -> None:
    schemas = _docs()["schemas"]

    assert "`PPTX_TEXT_BEARING_IMAGE_AREA_RATIO`" in schemas
    assert "image_area_ratio >= 0.5" not in schemas


def test_post_batch_contract_is_explicit_without_repeating_section15_filter() -> None:
    docs = _docs()
    for name in ("persistence", "schemas"):
        assert "current_adherence_baseline" in docs[name]
        assert "active_batch_excluded: false" in docs[name]

    assert "current_adherence_baseline" in docs["processing"]
    assert "only after every merge succeeds" in docs["processing"]
    assert "complete baseline contract" in docs["processing"]
    assert "Do not reproduce its cohort\nselection" in docs["processing"]
    assert "section15_pattern_history.py" in docs["processing"]
    assert "active_batch_excluded: false" not in docs["processing"]
    assert "after the entire batch has persisted successfully" in docs["processing"]
    assert "never update it after an\nindividual member merge" in docs["processing"]
    assert "must not recompute after member 1" in docs["schemas"]


def test_claim_replay_recovery_and_closure_matrix_are_documented() -> None:
    docs = _docs()
    assert (
        "Idempotent replay returns the\nstored claim and leaves DB bytes unchanged"
        in docs["schemas"]
    )
    assert "Recovery never rewrites a claim snapshot" in docs["schemas"]
    assert "closes v1 as v2 and closes v2–v7 at\ntheir own versions" in docs["schemas"]
    assert "receiptless completed v1 claim" in docs["persistence"]
    assert "takes a fresh pre-mutation snapshot" in docs["selection"]


def test_archival_v4_and_current_v5_evidence_generations_are_distinct() -> None:
    docs = _docs()
    assert "Two incompatible v3 lineages were emitted" in docs["schemas"]
    assert "v4 is their source-located union and remains archival" in docs["schemas"]

    assert '"pattern_scoring_schema_version": 5' in docs["schemas"]
    assert '"evidence_schema_version": 2' in docs["schemas"]
    assert "pattern_outcomes" in docs["worker"]
    assert "opportunity_coverage_identity" in docs["worker"]

    for name in ("persistence", "processing", "schemas", "worker"):
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


def test_current_v5_freshness_filter_is_owned_by_section15_helper() -> None:
    docs = _docs()
    assert "shared freshness assessor" in docs["selection"]
    assert "configured source roots" in docs["selection"]
    assert "section15_pattern_history.py" in docs["processing"]
    assert "Do not reproduce its\ncohort filter" in docs["processing"]
    assert "artifact freshness against the vault" not in docs["processing"]
    assert "shared root-aware assessor" in docs["selection"]
    assert "remote video/slide acquisition remains eligible" in docs["selection"]


def test_source_located_receipt_is_public_and_range_bound() -> None:
    docs = _docs()
    for name in ("processing", "schemas", "worker"):
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
    assert "persistence derives" in docs["worker"]
    assert "artifact root/path/hash fields" in docs["worker"]
    assert (
        "raw-return receipt remains the\nhash of exactly what the worker sent"
        in docs["schemas"]
    )
    assert "non-English `delivery_language`" in docs["worker"]
    assert "non-empty\nEnglish `translation` is required" in docs["schemas"]

    schema_example = (
        docs["schemas"]
        .split("Each subagent returns this JSON after processing one talk:", 1)[1]
        .split("```json", 1)[1]
        .split("```", 1)[0]
    )
    worker_example = (
        docs["worker"]
        .split("Minimal processed structure for a fresh v7 claim", 1)[1]
        .split("```json", 1)[1]
        .split("```", 1)[0]
    )
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
    for name in ("persistence", "processing", "schemas", "worker"):
        assert "source_gate_pending_owner_review" in docs[name]
    for name in ("processing", "schemas", "worker"):
        assert "missing_required_source_coverage" in docs[name]
    assert "fails closed" in docs["processing"]
    assert "fail-closed" in docs["schemas"]
    assert "fails closed" in docs["worker"]

    assert "contains exactly `pattern_id` and `reason_code`" in docs["processing"]
    assert "prose-bearing" in docs["processing"]


def test_claim_return_talk_and_scoring_axes_preserve_archival_v4() -> None:
    docs = _docs()
    assert "The four version axes are deliberately explicit" in docs["schemas"]
    assert (
        "| v4 | v4 only | archival source-located v4 | never current v5 |"
        in docs["schemas"]
    )
    assert "| v5 | v5 only | migrated v8 | never current v6 |" in docs["schemas"]
    assert (
        "| v6 | v6 only | migrated v8 | v6 when canonical evidence/outcomes are fresh |"
        in docs["schemas"]
    )
    assert (
        "| v7 | v7 only | v8 | v6 when canonical evidence/outcomes are fresh |"
        in docs["schemas"]
    )
    assert "Fresh queue work uses claim schema v7" in docs["selection"]
    assert (
        "fresh return generation eligible for pattern-scoring schema v6"
        in docs["worker"]
    )


def test_transcript_freshness_revalidates_quality_provenance() -> None:
    docs = _docs()
    assert (
        "hash-bound quality policy against current owner/provider duration"
        in docs["selection"]
    )
    assert "transcript_quality_context_drift" in docs["schemas"]


def _worker_current_example() -> dict:
    """Parse the fenced return example the per-talk workers copy."""
    doc = DOC_PATHS["worker"].read_text(encoding="utf-8")
    marker = '{\n  "filename": "2026-01-01-example.md"'
    start = doc.index(marker)
    return json.loads(doc[start : doc.index("```", start)].strip())


def test_worker_example_declares_the_version_its_heading_claims(
    return_validation,
) -> None:
    """The block every subagent copies is headed with the current claim.

    It previously declared version 5, which a v6 claim rejects outright, and the
    rejection read as the worker analysing badly rather than the instruction
    being wrong.
    """
    example = _worker_current_example()
    assert example["return_schema_version"] == return_validation.RETURN_SCHEMA_VERSION


def test_worker_example_uses_only_declared_verbatim_lanes(return_validation) -> None:
    """Invented lane names are rejected as unknown snapshot lanes."""
    example = _worker_current_example()
    assert (
        set(example.get("verbatim_examples", {}))
        <= return_validation.VERBATIM_EXAMPLE_FIELDS
    )


def test_the_documented_flow_turns_the_example_into_a_valid_return() -> None:
    """Example plus basis builder must equal something the validator accepts.

    The block deliberately omits `pattern_score` and `pattern_score_basis`; the
    reference tells the worker to generate both. This exercises that sequence
    end to end, so the documented flow is what is under test rather than a copy
    of the script's output pasted into the page.
    """
    import subprocess
    import sys
    import tempfile

    example = _worker_current_example()
    assert "pattern_score" not in example["pattern_observations"], (
        "the example must not restate script-owned arithmetic"
    )
    assert "pattern_score_basis" not in example["pattern_observations"], (
        "the example must not restate script-owned output"
    )
    scripts = INGRESS / "scripts"

    with tempfile.TemporaryDirectory() as work:
        path = Path(work) / "example.json"
        path.write_text(json.dumps(example), encoding="utf-8")

        built = subprocess.run(
            [sys.executable, str(scripts / "build-score-basis.py"), str(path)],
            capture_output=True,
            text=True,
        )
        assert built.returncode == 0, built.stderr
        # the builder emits the completed return, so nothing is merged by hand
        path.write_text(built.stdout, encoding="utf-8")

        validated = subprocess.run(
            [
                sys.executable,
                str(scripts / "validate-returns.py"),
                str(path),
                "--catalog-dir",
                str(
                    REPO_ROOT
                    / "skills"
                    / "presentation-creator"
                    / "references"
                    / "patterns"
                ),
            ],
            capture_output=True,
            text=True,
        )

    assert validated.returncode == 0, validated.stderr
    assert json.loads(validated.stdout)["valid"] is True
