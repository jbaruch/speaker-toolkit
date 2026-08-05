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
