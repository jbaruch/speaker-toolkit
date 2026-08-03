#!/usr/bin/env python3
"""Resolve one lexical, host-native authority for a rhetoric vault root.

The tracking-database location is the primary authority.  An explicit CLI
vault root and ``config.vault_storage_path`` are constraints on that authority,
not aliases that may be resolved through the filesystem.  Every raw value is
therefore classified before ``pathlib.Path`` materialization, and agreement is
lexical: native ``Path`` equality only, with no home expansion, absolutization,
filesystem resolution, or stat call.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Literal, NoReturn

from artifact_locator import ArtifactLocatorError, materialize_native_root


VaultAuthority = Literal["database_path", "cli_root", "config_root"]
VaultAuthorityPair = tuple[Literal["database_path"], Literal["cli_root", "config_root"]]

_AUTHORITY_ERROR_CODES: dict[VaultAuthority, str] = {
    "database_path": "vault_root_database_path_invalid",
    "cli_root": "vault_root_cli_invalid",
    "config_root": "vault_root_config_invalid",
}
_REASON_CODES = frozenset(
    {
        *_AUTHORITY_ERROR_CODES.values(),
        "vault_root_authority_mismatch",
    }
)
_AUTHORITY_PAIRS: frozenset[VaultAuthorityPair] = frozenset(
    {
        ("database_path", "cli_root"),
        ("database_path", "config_root"),
    }
)


class VaultRootAuthorityError(ValueError):
    """A closed, path-neutral trusted-root authority rejection."""

    def __init__(
        self,
        reason_code: str,
        *,
        locator_reason_code: str | None = None,
        authorities: VaultAuthorityPair | None = None,
    ) -> None:
        if reason_code not in _REASON_CODES:
            raise ValueError("invalid vault-root authority reason code")
        if locator_reason_code is not None:
            try:
                ArtifactLocatorError(locator_reason_code)
            except ValueError as exc:
                raise ValueError("invalid artifact locator reason code") from exc
        if authorities is not None and reason_code != "vault_root_authority_mismatch":
            raise ValueError("authority pair is valid only for a root mismatch")
        if reason_code == "vault_root_authority_mismatch" and authorities is None:
            raise ValueError("root mismatch requires an authority pair")
        if authorities is not None and authorities not in _AUTHORITY_PAIRS:
            raise ValueError("invalid vault-root authority pair")
        self.reason_code = reason_code
        self.locator_reason_code = locator_reason_code
        self.authorities = authorities
        message = reason_code
        if locator_reason_code is not None:
            message = f"{message}:{locator_reason_code}"
        if authorities is not None:
            message = f"{message}:{authorities[0]}:{authorities[1]}"
        super().__init__(message)


def _reject(
    reason_code: str,
    *,
    authorities: VaultAuthorityPair | None = None,
) -> NoReturn:
    raise VaultRootAuthorityError(reason_code, authorities=authorities)


def materialize_native_authority(
    raw: object,
    *,
    authority: VaultAuthority,
) -> Path:
    """Materialize one native absolute authority after lexical classification.

    ``database_path`` identifies the tracking-database file. ``cli_root`` and
    ``config_root`` identify the vault directory.  The distinction selects only
    a stable diagnostic family; this function performs no filesystem access.
    """
    if authority not in _AUTHORITY_ERROR_CODES:
        raise ValueError("invalid vault-root authority kind")
    try:
        return materialize_native_root(raw)
    except ArtifactLocatorError as exc:
        raise VaultRootAuthorityError(
            _AUTHORITY_ERROR_CODES[authority],
            locator_reason_code=exc.reason_code,
        ) from exc


def resolve_vault_root_authority(
    *,
    database_path: object,
    config: object,
    cli_vault_root: object | None = None,
) -> Path:
    """Return the database-bound vault root after all authorities agree.

    A missing config object, an absent ``vault_storage_path`` key, and an
    explicit JSON null all fall back to the database parent.  Every other
    configured value is an asserted authority: invalid or lexically different
    values fail closed.
    """
    cli_root = None
    if cli_vault_root is not None:
        cli_root = materialize_native_authority(
            cli_vault_root,
            authority="cli_root",
        )

    native_database_path = materialize_native_authority(
        database_path,
        authority="database_path",
    )
    database_root = native_database_path.parent

    if cli_root is not None and cli_root != database_root:
        _reject(
            "vault_root_authority_mismatch",
            authorities=("database_path", "cli_root"),
        )

    if config is None:
        return database_root
    if not isinstance(config, Mapping):
        _reject("vault_root_config_invalid")
    if "vault_storage_path" not in config:
        return database_root

    configured_raw = config["vault_storage_path"]
    if configured_raw is None:
        return database_root
    configured_root = materialize_native_authority(
        configured_raw,
        authority="config_root",
    )
    if configured_root != database_root:
        _reject(
            "vault_root_authority_mismatch",
            authorities=("database_path", "config_root"),
        )
    return database_root


__all__ = [
    "VaultAuthority",
    "VaultAuthorityPair",
    "VaultRootAuthorityError",
    "materialize_native_authority",
    "resolve_vault_root_authority",
]
