"""Lexical trusted-vault-root authority contract tests."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
import sys

import pytest


SCRIPTS = Path(__file__).parents[1] / "skills" / "vault-ingress" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

vault_root_authority = importlib.import_module("vault_root_authority")


def _native_root_text(name: str = "vault") -> str:
    if os.name == "nt":
        return rf"C:\trusted\{name}"
    return f"/trusted/{name}"


def _native_database_text(name: str = "vault") -> str:
    return str(Path(_native_root_text(name)) / "tracking-database.json")


def _foreign_root_text() -> str:
    return "/foreign/vault" if os.name == "nt" else r"C:\foreign\vault"


def _native_dot_root_text() -> str:
    return (
        r"C:\trusted\other\..\vault" if os.name == "nt" else "/trusted/other/../vault"
    )


@pytest.mark.parametrize(
    "config",
    (
        None,
        {},
        {"schema_version": 1},
        {"vault_storage_path": None},
    ),
)
def test_absent_or_null_configured_root_falls_back_to_database_parent(
    config: object,
) -> None:
    resolved = vault_root_authority.resolve_vault_root_authority(
        database_path=_native_database_text(),
        config=config,
    )

    assert resolved == Path(_native_root_text())


def test_matching_cli_and_config_roots_preserve_native_absolute_authority() -> None:
    root = _native_root_text()
    trailing_separator = "\\" if os.name == "nt" else "/"

    resolved = vault_root_authority.resolve_vault_root_authority(
        database_path=_native_database_text(),
        config={"vault_storage_path": root + trailing_separator},
        cli_vault_root=root,
    )

    assert resolved == Path(root)
    assert resolved.is_absolute()


@pytest.mark.parametrize(
    ("raw", "locator_reason"),
    (
        ("", "artifact_locator_empty_or_whitespace"),
        (" ", "artifact_locator_empty_or_whitespace"),
        ("relative/vault", "artifact_root_not_native_absolute"),
        ("C:vault", "artifact_locator_windows_drive_relative"),
        (r"\vault", "artifact_locator_windows_current_drive_rooted"),
        (_native_dot_root_text(), "artifact_locator_dot_segment"),
        ("~/vault", "artifact_locator_home_expansion_unsupported"),
        (
            r"\\?\C:\credential-bearing\vault",
            "artifact_locator_windows_device_namespace",
        ),
    ),
)
def test_present_invalid_configured_root_fails_closed(
    raw: object,
    locator_reason: str,
) -> None:
    with pytest.raises(vault_root_authority.VaultRootAuthorityError) as caught:
        vault_root_authority.resolve_vault_root_authority(
            database_path=_native_database_text(),
            config={"vault_storage_path": raw},
        )

    assert caught.value.reason_code == "vault_root_config_invalid"
    assert caught.value.locator_reason_code == locator_reason
    assert caught.value.authorities is None
    assert str(caught.value) == f"vault_root_config_invalid:{locator_reason}"
    assert "credential-bearing" not in str(caught.value)
    assert "credential-bearing" not in repr(caught.value)


def test_foreign_configured_root_fails_closed() -> None:
    with pytest.raises(vault_root_authority.VaultRootAuthorityError) as caught:
        vault_root_authority.resolve_vault_root_authority(
            database_path=_native_database_text(),
            config={"vault_storage_path": _foreign_root_text()},
        )

    assert caught.value.reason_code == "vault_root_config_invalid"
    assert caught.value.locator_reason_code == "artifact_locator_foreign_absolute"


def test_dot_segment_configured_root_fails_before_lexical_comparison() -> None:
    raw = r"C:\trusted\other\..\vault" if os.name == "nt" else "/trusted/other/../vault"

    with pytest.raises(vault_root_authority.VaultRootAuthorityError) as caught:
        vault_root_authority.resolve_vault_root_authority(
            database_path=_native_database_text(),
            config={"vault_storage_path": raw},
        )

    assert caught.value.reason_code == "vault_root_config_invalid"
    assert caught.value.locator_reason_code == "artifact_locator_dot_segment"


@pytest.mark.parametrize("config", ("/trusted/vault", [], 7, True))
def test_non_object_config_fails_closed(config: object) -> None:
    with pytest.raises(vault_root_authority.VaultRootAuthorityError) as caught:
        vault_root_authority.resolve_vault_root_authority(
            database_path=_native_database_text(),
            config=config,
        )

    assert caught.value.reason_code == "vault_root_config_invalid"
    assert caught.value.locator_reason_code is None
    assert str(caught.value) == "vault_root_config_invalid"


def test_configured_root_mismatch_names_only_the_closed_authorities() -> None:
    with pytest.raises(vault_root_authority.VaultRootAuthorityError) as caught:
        vault_root_authority.resolve_vault_root_authority(
            database_path=_native_database_text(),
            config={"vault_storage_path": _native_root_text("other")},
        )

    assert caught.value.reason_code == "vault_root_authority_mismatch"
    assert caught.value.locator_reason_code is None
    assert caught.value.authorities == ("database_path", "config_root")
    assert str(caught.value) == (
        "vault_root_authority_mismatch:database_path:config_root"
    )
    assert "trusted" not in str(caught.value)


def test_cli_root_mismatch_names_only_the_closed_authorities() -> None:
    with pytest.raises(vault_root_authority.VaultRootAuthorityError) as caught:
        vault_root_authority.resolve_vault_root_authority(
            database_path=_native_database_text(),
            config=None,
            cli_vault_root=_native_root_text("other"),
        )

    assert caught.value.reason_code == "vault_root_authority_mismatch"
    assert caught.value.authorities == ("database_path", "cli_root")
    assert str(caught.value) == ("vault_root_authority_mismatch:database_path:cli_root")


def test_invalid_cli_root_is_classified_before_database_authority() -> None:
    with pytest.raises(vault_root_authority.VaultRootAuthorityError) as caught:
        vault_root_authority.resolve_vault_root_authority(
            database_path="also/relative.json",
            config=None,
            cli_vault_root="relative/vault",
        )

    assert caught.value.reason_code == "vault_root_cli_invalid"
    assert caught.value.locator_reason_code == "artifact_root_not_native_absolute"


def test_invalid_database_path_is_path_neutral() -> None:
    secret = "credential-bearing/tracking-database.json"

    with pytest.raises(vault_root_authority.VaultRootAuthorityError) as caught:
        vault_root_authority.resolve_vault_root_authority(
            database_path=secret,
            config=None,
        )

    assert caught.value.reason_code == "vault_root_database_path_invalid"
    assert caught.value.locator_reason_code == "artifact_root_not_native_absolute"
    assert secret not in str(caught.value)
    assert secret not in repr(caught.value)


def test_error_constructor_rejects_open_diagnostics() -> None:
    with pytest.raises(ValueError, match="invalid vault-root authority reason code"):
        vault_root_authority.VaultRootAuthorityError("/secret/root")
    with pytest.raises(ValueError, match="invalid artifact locator reason code"):
        vault_root_authority.VaultRootAuthorityError(
            "vault_root_config_invalid",
            locator_reason_code="/secret/root",
        )
    with pytest.raises(ValueError, match="root mismatch requires an authority pair"):
        vault_root_authority.VaultRootAuthorityError("vault_root_authority_mismatch")
    with pytest.raises(ValueError, match="invalid vault-root authority pair"):
        vault_root_authority.VaultRootAuthorityError(
            "vault_root_authority_mismatch",
            authorities=("database_path", "database_path"),
        )


def test_invalid_authority_selector_is_a_programming_error() -> None:
    with pytest.raises(ValueError, match="invalid vault-root authority kind"):
        vault_root_authority.materialize_native_authority(
            _native_root_text(),
            authority="untrusted",
        )
