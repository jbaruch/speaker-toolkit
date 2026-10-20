"""Regression guards for the typed config-mutation contract."""

from pathlib import Path
import re

from conftest import SCRIPTS_VI, _import_script


ROOT = Path(__file__).resolve().parent.parent
# A sentence naming one config schema number. Plural "schemas" lists are
# version inventories, not a statement of which one is current.
CONFIG_SCHEMA_SENTENCE = re.compile(r"[^.]*\bconfig\s+schema\s+v?(\d+)\b[^.]*\.", re.I)
CURRENTNESS = re.compile(r"\b(?:requires?|current|stamps?|writes?)\b", re.I)
LEGACY_CONTEXT = re.compile(
    r"\b(?:legacy|migrat\w*|readable|input|historical|never current)\b", re.I
)


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_standalone_metadata_repair_requires_explicit_owner_root_migration() -> None:
    skill = " ".join(_read("skills/vault-ingress/SKILL.md").split())
    schema = " ".join(_read("skills/vault-ingress/references/schemas-db.md").split())

    assert "standalone catalog metadata repair" in skill
    assert "root-only owner migration" in skill
    assert "Do not select a batch, reparse, or regenerate derived artifacts" in skill
    assert "--root-only" in schema
    assert "Deploy the dual readers before applying" in schema
    assert "migrate_tracking_database_root" in schema
    assert "Metadata mutations still require the current root" in schema
    assert "standalone repair exception" not in schema
    assert "under `stateful-artifacts` Migration Policy" not in skill


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


def test_no_operational_reference_calls_a_superseded_config_current() -> None:
    """A doc that requires an old config generation sends agents to refuse the
    current one; only the code's version may be named as current."""
    current = _import_script(
        str(Path(SCRIPTS_VI) / "tracking_database.py"), "tracking_database"
    ).CONFIG_RECORD_SCHEMA_VERSION
    failures: list[str] = []
    for path in sorted((ROOT / "skills").rglob("*.md")):
        text = " ".join(path.read_text(encoding="utf-8").split())
        for match in CONFIG_SCHEMA_SENTENCE.finditer(text):
            sentence = match.group(0).strip()
            if (
                int(match.group(1)) != current
                and CURRENTNESS.search(sentence)
                and not LEGACY_CONTEXT.search(sentence)
            ):
                failures.append(f"{path.relative_to(ROOT)}: {sentence}")
    assert not failures, "\n" + "\n".join(failures)
