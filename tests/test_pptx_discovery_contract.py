"""Tests for versioned PPTX directory discovery policy."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest


SCRIPTS = Path(__file__).parents[1] / "skills" / "vault-ingress" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pptx_discovery_contract as contract  # noqa: E402 - import follows script-path injection


def test_canonical_directory_exclusions_are_narrow_and_stable() -> None:
    assert contract.DEFAULT_PPTX_DIRECTORY_EXCLUSIONS == (
        ".venv",
        "venv",
        "node_modules",
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        ".tessl",
    )
    assert not {
        "templates",
        "slides",
        "decks",
        "build",
        "dist",
        "vendor",
        "archive",
    } & set(contract.DEFAULT_PPTX_DIRECTORY_EXCLUSIONS)


@pytest.mark.parametrize(
    "value",
    [
        None,
        "venv",
        [""],
        ["   "],
        ["."],
        [".."],
        ["nested/venv"],
        [r"nested\venv"],
        ["venv*"],
        ["^venv$"],
        ["venv[0-9]"],
        ["venv\ncache"],
        ["venv\x85cache"],
        ["venv\u202ecache"],
        ["venv", "VENV"],
        ["x" * (contract.PPTX_DIRECTORY_EXCLUSION_MAX_CHARS + 1)],
        ["x"] * (contract.PPTX_DIRECTORY_EXCLUSION_MAX_COUNT + 1),
    ],
)
def test_directory_exclusion_validation_rejects_patterns_and_ambiguous_values(
    value: object,
) -> None:
    with pytest.raises(contract.PptxDiscoveryContractError):
        contract.validate_pptx_directory_exclusions(value)


def test_directory_exclusion_caps_accept_exact_boundaries() -> None:
    components = [
        f"cache-{index}"
        for index in range(contract.PPTX_DIRECTORY_EXCLUSION_MAX_COUNT - 1)
    ]
    components.append("x" * contract.PPTX_DIRECTORY_EXCLUSION_MAX_CHARS)

    assert contract.validate_pptx_directory_exclusions(components) == components


def test_directory_exclusions_use_exact_casefolded_component_matching() -> None:
    exclusions = contract.validate_pptx_directory_exclusions(
        [".VENV", "generated assets"]
    )

    assert contract.directory_component_is_excluded(".venv", exclusions) is True
    assert (
        contract.directory_component_is_excluded("generated assets", exclusions)
        is True
    )
    assert contract.directory_component_is_excluded("my.venv", exclusions) is False
    assert (
        contract.directory_component_is_excluded("generated assets old", exclusions)
        is False
    )


def test_policy_skips_do_not_make_a_complete_scan_partial() -> None:
    skipped = [
        {"path": f"safe-{index}", "reason": reason}
        for index, reason in enumerate(
            sorted(contract.PPTX_DIRECTORY_POLICY_SKIP_REASON_CODES)
        )
    ]

    batch = contract.build_pptx_directory_batch([], skipped)

    assert batch["complete"] is True
    assert batch["incomplete_reason_codes"] == []


@pytest.mark.parametrize(
    "reason_code",
    sorted(contract.PPTX_DIRECTORY_INCOMPLETE_REASON_CODES),
)
def test_every_incomplete_reason_fails_closed(reason_code: str) -> None:
    error = (
        {"reason_code": reason_code, "details": {}}
        if reason_code in contract.PPTX_DIRECTORY_WHOLE_ROOT_REASON_CODES
        else None
    )
    batch = contract.build_pptx_directory_batch(
        [],
        [{"path": ".", "reason": reason_code}],
        error=error,
    )

    assert batch["complete"] is False
    assert batch["incomplete_reason_codes"] == [reason_code]


def test_public_batch_round_trip_is_strict_and_recomputes_completeness() -> None:
    batch = contract.build_pptx_directory_batch(
        [{"pptx_path": "talk.pptx"}],
        [
            {"path": ".venv", "reason": "pptx_batch_directory_excluded"},
            {"path": "bad.pptx", "reason": "pptx_parse_failure"},
        ],
    )

    assert batch == {
        "schema_version": 1,
        "kind": "pptx_directory_batch",
        "complete": False,
        "incomplete_reason_codes": ["pptx_parse_failure"],
        "results": [{"pptx_path": "talk.pptx"}],
        "skipped": [
            {"path": ".venv", "reason": "pptx_batch_directory_excluded"},
            {"path": "bad.pptx", "reason": "pptx_parse_failure"},
        ],
    }
    assert contract.decode_pptx_directory_batch(batch) == batch
    assert contract.assess_pptx_directory_batch(batch).state == "partial"

    for field, false_value in (
        ("complete", True),
        ("incomplete_reason_codes", []),
        ("schema_version", True),
        ("kind", "directory"),
    ):
        malformed = {**batch, field: false_value}
        with pytest.raises(contract.PptxDiscoveryContractError):
            contract.decode_pptx_directory_batch(malformed)


def test_public_batch_rejects_nonobjects_unknown_reasons_and_duplicate_receipts() -> None:
    for results, skipped in (
        (["not-an-object"], []),
        ([], [{"path": ".", "reason": "typo"}]),
        (
            [],
            [
                {"path": "one.pptx", "reason": "pptx_parse_failure"},
                {"path": "one.pptx", "reason": "pptx_probe_timeout"},
            ],
        ),
    ):
        with pytest.raises(contract.PptxDiscoveryContractError):
            contract.build_pptx_directory_batch(results, skipped)


def test_public_batch_rejects_descendant_skip_receipts() -> None:
    with pytest.raises(
        contract.PptxDiscoveryContractError,
        match="descendant of another skipped path",
    ):
        contract.build_pptx_directory_batch(
            [],
            [
                {
                    "path": "unavailable",
                    "reason": "pptx_batch_directory_unavailable",
                },
                {
                    "path": "unavailable/deck.pptx",
                    "reason": "pptx_batch_entry_unavailable",
                },
            ],
        )


def test_whole_root_failure_is_bound_to_the_same_public_envelope() -> None:
    batch = contract.build_pptx_directory_batch(
        [],
        [{"path": ".", "reason": "pptx_batch_discovery_start_failure"}],
        error={
            "reason_code": "pptx_batch_discovery_start_failure",
            "details": {"supervisor_reason_code": "worker_start_failed"},
        },
    )

    assert batch["complete"] is False
    assert batch["results"] == []
    assert contract.decode_pptx_directory_batch(batch) == batch


def test_whole_root_receipt_requires_error_and_zero_results() -> None:
    receipt = [
        {"path": ".", "reason": "pptx_batch_discovery_start_failure"}
    ]
    with pytest.raises(
        contract.PptxDiscoveryContractError,
        match="require a matching top-level error",
    ):
        contract.build_pptx_directory_batch([], receipt)

    with pytest.raises(
        contract.PptxDiscoveryContractError,
        match="one incomplete root receipt and no results",
    ):
        contract.build_pptx_directory_batch(
            [{"pptx_path": "safe.pptx"}],
            receipt,
            error={
                "reason_code": "pptx_batch_discovery_start_failure",
                "details": {},
            },
        )

    with pytest.raises(
        contract.PptxDiscoveryContractError,
        match="one incomplete root receipt and no results",
    ):
        contract.build_pptx_directory_batch(
            [],
            receipt,
            error={
                "reason_code": "pptx_batch_discovery_timeout",
                "details": {},
            },
        )


def test_top_level_error_rejects_per_file_reason_promotion() -> None:
    with pytest.raises(
        contract.PptxDiscoveryContractError,
        match="one incomplete root receipt and no results",
    ):
        contract.build_pptx_directory_batch(
            [],
            [{"path": ".", "reason": "pptx_parse_failure"}],
            error={"reason_code": "pptx_parse_failure", "details": {}},
        )


@pytest.mark.parametrize(
    "details",
    [
        {"path": "/private/decks"},
        {"unexpected": "worker_start_failed"},
        {"supervisor_reason_code": "arbitrary_future_or_injected_value"},
        {"supervisor_reason_code": ["worker_start_failed"]},
    ],
)
def test_top_level_error_details_are_closed_and_path_neutral(details: object) -> None:
    with pytest.raises(contract.PptxDiscoveryContractError):
        contract.build_pptx_directory_batch(
            [],
            [
                {
                    "path": ".",
                    "reason": "pptx_batch_discovery_start_failure",
                }
            ],
            error={
                "reason_code": "pptx_batch_discovery_start_failure",
                "details": details,
            },
        )


def test_legacy_unversioned_batch_never_authorizes_absence() -> None:
    assessment = contract.assess_pptx_directory_batch(
        {"results": [], "skipped": []}
    )

    assert assessment.state == "unknown_legacy"
    assert assessment.schema_version == 0
    assert assessment.complete is None
    assert assessment.incomplete_reason_codes == (
        "pptx_directory_batch_completeness_unknown",
    )


def test_ingress_and_config_docs_bind_directory_completeness_and_migration() -> None:
    root = Path(__file__).parents[1]
    relative_paths = {
        "skill": "skills/vault-ingress/SKILL.md",
        "bootstrap": (
            "skills/vault-ingress/references/bootstrap-and-preflight.md"
        ),
        "followup": "skills/vault-ingress/references/pptx-followup.md",
        "schemas": "skills/vault-ingress/references/schemas-db.md",
        "preflight": (
            "skills/vault-ingress/references/source-identity-preflight.md"
        ),
        "profile_config": "skills/vault-profile/references/schemas-config.md",
        "clarification": "skills/vault-clarification/SKILL.md",
        "clarification_config": (
            "skills/vault-clarification/references/schemas-config.md"
        ),
    }
    docs = {
        name: (root / relative).read_text(encoding="utf-8")
        for name, relative in relative_paths.items()
    }

    for name in ("skill", "bootstrap", "followup"):
        assert "{directory_exclusion_arguments}" in docs[name]
    for name in ("bootstrap", "followup", "schemas", "preflight"):
        assert "complete: true" in docs[name]
        assert "legacy unversioned" in docs[name].lower()
    for name in ("bootstrap", "schemas", "profile_config"):
        assert "pptx_directory_exclusions" in docs[name]
        assert (
            '"schema_version": 2' in docs[name]
            or "`schema_version: 2`" in docs[name]
        )
    assert "config schema 2" in docs["clarification"]
    assert "config schema v2" in docs["clarification_config"]
    assert "per-deck extractor schema v4" in docs["schemas"]
    assert "separate finite policy\nenumeration ceiling" in docs["schemas"]
    assert "response echoes that exact ordered list" in docs["schemas"]
    assert "per-deck failures cannot be promoted" in docs["schemas"]
    assert docs["bootstrap"].count("DEFAULT_PPTX_DIRECTORY_EXCLUSIONS") == 1
    assert "DEFAULT_PPTX_DIRECTORY_EXCLUSIONS" not in docs["profile_config"]
    assert "DEFAULT_PPTX_DIRECTORY_EXCLUSIONS" not in docs["schemas"]
    assert '"pptx_directory_exclusions": ["example-tool-cache"]' in (
        docs["profile_config"]
    )
    assert '"pptx_directory_exclusions": ["example-tool-cache"]' in docs["schemas"]
    taxonomy_reference = (
        "pptx_discovery_contract.py::{PPTX_DIRECTORY_POLICY_SKIP_REASON_CODES,"
        "PPTX_DIRECTORY_INCOMPLETE_REASON_CODES}"
    )
    assert taxonomy_reference in docs["schemas"]
    assert all(
        taxonomy_reference not in document
        for name, document in docs.items()
        if name != "schemas"
    )
    assert "never reclassify receipts by\nreason string" in docs["bootstrap"]
    assert "without an explicit speaker-specific customization" in (
        docs["bootstrap"]
    )
    assert "without an explicit speaker-specific customization" in (
        docs["profile_config"]
    )
