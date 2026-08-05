"""Regression guards for the typed config-mutation contract."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_config_deletion_and_reserved_marker_recovery_are_documented() -> None:
    schema = _read("skills/vault-ingress/references/schemas-db.md")
    bootstrap = _read("skills/vault-ingress/references/bootstrap-and-preflight.md")
    normalized_schema = " ".join(schema.split())
    normalized_bootstrap = " ".join(bootstrap.split())

    assert '"delete": true' in schema
    assert "invalid as a `set_config` value" in normalized_schema
    assert "Any other present value fails the precondition" in normalized_schema
    assert "`before_exists: true` and `after_exists: false`" in schema
    assert "never pass the missing marker as a `value`" in normalized_bootstrap


def test_pptx_exclusion_bootstrap_uses_code_owned_defaults_without_prompting() -> None:
    bootstrap = _read("skills/vault-ingress/references/bootstrap-and-preflight.md")
    profile_schema = _read("skills/vault-profile/references/schemas-config.md")
    normalized_bootstrap = " ".join(bootstrap.split())
    normalized_profile = " ".join(profile_schema.split())

    assert "pptx_discovery_contract.py::DEFAULT_PPTX_DIRECTORY_EXCLUSIONS" in (
        bootstrap
    )
    assert "The exclusion field is not a missing-field question" in (
        normalized_bootstrap
    )
    assert "only when the speaker explicitly wants to customize" in (
        normalized_bootstrap
    )
    assert "read-only compatibility and owner-migration state" in normalized_profile
    assert "never current or writable" in normalized_profile
    assert "cannot authorize PPTX catalog coverage or an absence conclusion" in (
        normalized_profile
    )
