#!/usr/bin/env python3
"""Host-deterministic lexical materialization for persisted artifact locators.

Classification deliberately happens before constructing a host-native
``pathlib.Path``.  The functions in this module perform no filesystem access and
never expand a home directory or process-relative path.
"""

from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath
from typing import Literal, NamedTuple, NoReturn


ArtifactLocatorKind = Literal[
    "relative",
    "posix_absolute",
    "windows_drive_absolute",
    "windows_unc_absolute",
]

_REASON_CODES = frozenset(
    {
        "artifact_locator_not_text",
        "artifact_locator_empty_or_whitespace",
        "artifact_locator_nul_byte",
        "artifact_locator_home_expansion_unsupported",
        "artifact_locator_dot_segment",
        "artifact_locator_windows_device_namespace",
        "artifact_locator_windows_drive_relative",
        "artifact_locator_windows_current_drive_rooted",
        "artifact_locator_ambiguous_double_slash",
        "artifact_locator_malformed_unc",
        "artifact_locator_windows_reserved_character",
        "artifact_locator_windows_trimmed_component",
        "artifact_locator_windows_reserved_name",
        "artifact_locator_noncanonical_relative",
        "artifact_locator_foreign_absolute",
        "artifact_locator_trusted_root_required",
        "artifact_root_not_native_absolute",
    }
)
_WINDOWS_DEVICE_PREFIXES = ("\\\\?\\", "\\\\.\\", "\\??\\", "\\\\??\\")
_WINDOWS_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")
_WINDOWS_RESERVED_CHARACTERS = frozenset('<>:"|?*')
_WINDOWS_RESERVED_BASENAME = re.compile(
    r"^(?:CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9\u00b9\u00b2\u00b3]|LPT[1-9\u00b9\u00b2\u00b3])$",
    re.IGNORECASE,
)


class ArtifactLocatorError(ValueError):
    """A closed, path-neutral artifact locator rejection."""

    def __init__(self, reason_code: str) -> None:
        if reason_code not in _REASON_CODES:
            raise ValueError("invalid artifact locator reason code")
        self.reason_code = reason_code
        super().__init__(reason_code)


class _ClassifiedLocator(NamedTuple):
    kind: ArtifactLocatorKind
    text: str
    relative_parts: tuple[str, ...]


def _reject(reason_code: str) -> NoReturn:
    raise ArtifactLocatorError(reason_code)


def _locator_text(raw: object) -> str:
    if not isinstance(raw, (str, os.PathLike)):
        _reject("artifact_locator_not_text")
    try:
        value = os.fspath(raw)
    except TypeError:
        _reject("artifact_locator_not_text")
    if not isinstance(value, str):
        _reject("artifact_locator_not_text")
    if not value or not value.strip():
        _reject("artifact_locator_empty_or_whitespace")
    if "\x00" in value:
        _reject("artifact_locator_nul_byte")
    if value.startswith("~"):
        _reject("artifact_locator_home_expansion_unsupported")
    return value


def _contains_dot_segment(value: str) -> bool:
    return any(
        segment in {".", ".."}
        for slash_segment in value.split("/")
        for segment in slash_segment.split("\\")
    )


def _validate_windows_file_components(
    components: tuple[str, ...],
    *,
    reject_reserved_names: bool = True,
) -> None:
    """Reject Win32 aliases and namespaces before a locator reaches ``Path``."""
    for component in components:
        if any(
            character in _WINDOWS_RESERVED_CHARACTERS or ord(character) < 32
            for character in component
        ):
            _reject("artifact_locator_windows_reserved_character")
        if component.endswith((".", " ")):
            _reject("artifact_locator_windows_trimmed_component")
        basename = component.split(".", 1)[0].rstrip(" ")
        if (
            reject_reserved_names
            and _WINDOWS_RESERVED_BASENAME.fullmatch(basename) is not None
        ):
            _reject("artifact_locator_windows_reserved_name")


def _validate_unc(value: str) -> None:
    windows_value = value.replace("/", "\\")
    if not windows_value.startswith("\\\\") or windows_value.startswith("\\\\\\"):
        _reject("artifact_locator_malformed_unc")
    components = windows_value[2:].split("\\")
    if components and components[-1] == "":
        components = components[:-1]
    if (
        len(components) < 2
        or any(not component for component in components)
        or ":" in components[0]
        or ":" in components[1]
    ):
        _reject("artifact_locator_malformed_unc")


def _classify_artifact_locator(raw: object) -> _ClassifiedLocator:
    value = _locator_text(raw)
    windows_value = value.replace("/", "\\")

    if windows_value.startswith(_WINDOWS_DEVICE_PREFIXES):
        _reject("artifact_locator_windows_device_namespace")

    drive_match = _WINDOWS_DRIVE_PREFIX.match(value)
    if drive_match is not None:
        drive_tail = value[2:]
        if not drive_tail.startswith(("/", "\\")):
            _reject("artifact_locator_windows_drive_relative")
        if _contains_dot_segment(value):
            _reject("artifact_locator_dot_segment")
        windows_parts = tuple(
            component
            for component in drive_tail.replace("/", "\\").split("\\")
            if component
        )
        _validate_windows_file_components(windows_parts)
        return _ClassifiedLocator("windows_drive_absolute", value, ())

    if value.startswith("//"):
        _reject("artifact_locator_ambiguous_double_slash")

    if value.startswith("\\\\"):
        _validate_unc(value)
        if _contains_dot_segment(value):
            _reject("artifact_locator_dot_segment")
        unc_parts = tuple(
            component
            for component in value.replace("/", "\\")[2:].split("\\")
            if component
        )
        _validate_windows_file_components(
            unc_parts[:2],
            reject_reserved_names=False,
        )
        _validate_windows_file_components(unc_parts[2:])
        return _ClassifiedLocator("windows_unc_absolute", value, ())

    if value.startswith("\\"):
        _reject("artifact_locator_windows_current_drive_rooted")

    if value.startswith("/"):
        if _contains_dot_segment(value):
            _reject("artifact_locator_dot_segment")
        return _ClassifiedLocator("posix_absolute", value, ())

    if value != value.strip():
        _reject("artifact_locator_empty_or_whitespace")

    if _contains_dot_segment(value):
        _reject("artifact_locator_dot_segment")
    if "\\" in value:
        _reject("artifact_locator_noncanonical_relative")

    relative = PurePosixPath(value)
    parts = relative.parts
    if not parts or relative.is_absolute() or relative.as_posix() != value:
        _reject("artifact_locator_noncanonical_relative")
    if any(_WINDOWS_DRIVE_PREFIX.match(part) is not None for part in parts):
        _reject("artifact_locator_windows_drive_relative")
    _validate_windows_file_components(parts)
    return _ClassifiedLocator("relative", value, parts)


def classify_artifact_locator(raw: object) -> ArtifactLocatorKind:
    """Return the locator's lexical flavor without consulting the host or disk."""
    return _classify_artifact_locator(raw).kind


def _is_native_absolute(kind: ArtifactLocatorKind) -> bool:
    if os.name == "nt":
        return kind in {"windows_drive_absolute", "windows_unc_absolute"}
    return kind == "posix_absolute"


def materialize_native_root(raw: object) -> Path:
    """Materialize a native absolute trusted root without normalization or I/O."""
    classified = _classify_artifact_locator(raw)
    if classified.kind == "relative":
        _reject("artifact_root_not_native_absolute")
    if not _is_native_absolute(classified.kind):
        _reject("artifact_locator_foreign_absolute")
    return Path(classified.text)


def materialize_artifact_locator(
    raw: object,
    trusted_root: object | None = None,
) -> Path:
    """Materialize one native absolute or canonical root-relative locator.

    A supplied trusted root is validated even when ``raw`` is already absolute,
    but this lexical helper does not impose containment on absolute locators.
    Callers that require containment retain ownership of that policy.
    """
    classified = _classify_artifact_locator(raw)
    if classified.kind == "relative":
        if trusted_root is None:
            _reject("artifact_locator_trusted_root_required")
        root = materialize_native_root(trusted_root)
        return root.joinpath(*classified.relative_parts)

    if not _is_native_absolute(classified.kind):
        _reject("artifact_locator_foreign_absolute")
    if trusted_root is not None:
        materialize_native_root(trusted_root)
    return Path(classified.text)


__all__ = [
    "ArtifactLocatorError",
    "ArtifactLocatorKind",
    "classify_artifact_locator",
    "materialize_artifact_locator",
    "materialize_native_root",
]
