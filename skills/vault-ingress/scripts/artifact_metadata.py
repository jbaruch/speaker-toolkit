#!/usr/bin/env python3
"""Platform-neutral, path-safe artifact metadata inspection primitives."""

from __future__ import annotations

import os
import stat as stat_module
import sys
from dataclasses import dataclass
from pathlib import Path

from artifact_supervisor import FileGeneration


METADATA_SCHEMA_VERSION = 1
MACOS_DATALESS_FLAG = int(
    getattr(
        stat_module,
        "SF_DATALESS",
        0x40000000 if sys.platform == "darwin" else 0,
    )
)
WINDOWS_OFFLINE_ATTRIBUTE = 0x001000
WINDOWS_RECALL_ON_OPEN_ATTRIBUTE = 0x040000
WINDOWS_RECALL_ON_DATA_ACCESS_ATTRIBUTE = 0x400000
WINDOWS_UNAVAILABLE_CLOUD_ATTRIBUTES = (
    WINDOWS_OFFLINE_ATTRIBUTE
    | WINDOWS_RECALL_ON_OPEN_ATTRIBUTE
    | WINDOWS_RECALL_ON_DATA_ACCESS_ATTRIBUTE
)
WINDOWS_REPARSE_POINT_ATTRIBUTE = 0x000400
WINDOWS_CLOUD_REPARSE_TAGS = frozenset(
    0x9000001A + (suffix << 12) for suffix in range(16)
)
METADATA_FAILURE_KINDS = frozenset(
    {"io", "missing", "not_regular", "root_escape", "symlink_or_reparse"}
)


class ArtifactMetadataMalformed(ValueError):
    """A worker metadata request is structurally invalid before artifact I/O."""


class ArtifactMetadataUnavailable(OSError):
    """A stable, path-free artifact metadata failure."""

    def __init__(
        self,
        failure_kind: str,
        *,
        exception_type: str | None = None,
    ) -> None:
        if failure_kind not in METADATA_FAILURE_KINDS:
            raise ValueError("invalid metadata failure kind")
        self.failure_kind = failure_kind
        self.exception_type = exception_type
        super().__init__(failure_kind)


def canonicalize_trusted_artifact_locator(
    path: Path,
    trusted_root: Path | None,
) -> tuple[Path, Path | None]:
    """Admit a configured symlink root without resolving the artifact leaf.

    The vault root is trusted configuration and may intentionally be a symlink.
    Descendants remain lexical and are still checked component-by-component by
    the metadata worker after the root locator is mapped to its storage target.
    """
    if trusted_root is None:
        return path, None
    try:
        canonical_root = trusted_root.resolve(strict=True)
    except (OSError, RuntimeError):
        return path, trusted_root
    try:
        relative = path.relative_to(trusted_root)
    except ValueError:
        return path, canonical_root
    return canonical_root / relative, canonical_root


@dataclass(frozen=True)
class ArtifactAvailability:
    """Closed platform availability facts for one exact file generation."""

    state: str
    macos_dataless: bool
    windows_offline: bool
    windows_recall_on_open: bool
    windows_recall_on_data_access: bool

    @classmethod
    def from_generation(
        cls,
        generation: FileGeneration,
        *,
        macos_dataless_flag: int = MACOS_DATALESS_FLAG,
        windows_cloud_file_attributes: int = WINDOWS_UNAVAILABLE_CLOUD_ATTRIBUTES,
    ) -> ArtifactAvailability:
        flags = generation.flags or 0
        attributes = generation.file_attributes or 0
        active_attributes = attributes & windows_cloud_file_attributes
        macos_dataless = bool(macos_dataless_flag and flags & macos_dataless_flag)
        windows_offline = bool(active_attributes & WINDOWS_OFFLINE_ATTRIBUTE)
        windows_recall_on_open = bool(
            active_attributes & WINDOWS_RECALL_ON_OPEN_ATTRIBUTE
        )
        windows_recall_on_data_access = bool(
            active_attributes & WINDOWS_RECALL_ON_DATA_ACCESS_ATTRIBUTE
        )
        unavailable = (
            macos_dataless
            or windows_offline
            or windows_recall_on_open
            or windows_recall_on_data_access
        )
        return cls(
            state="unavailable" if unavailable else "local",
            macos_dataless=macos_dataless,
            windows_offline=windows_offline,
            windows_recall_on_open=windows_recall_on_open,
            windows_recall_on_data_access=windows_recall_on_data_access,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "macos_dataless": self.macos_dataless,
            "windows_offline": self.windows_offline,
            "windows_recall_on_open": self.windows_recall_on_open,
            "windows_recall_on_data_access": self.windows_recall_on_data_access,
        }


@dataclass(frozen=True)
class ArtifactMetadataReceipt:
    """One admitted file generation and its trusted-root identity/availability."""

    generation: FileGeneration
    root_generation: FileGeneration | None
    reparse_tag: int | None


def reparse_tag(
    snapshot: os.stat_result,
    *,
    reparse_point_attribute: int = WINDOWS_REPARSE_POINT_ATTRIBUTE,
) -> int | None:
    """Return a Windows reparse tag, or ``-1`` when the tag is unavailable."""
    attributes = int(getattr(snapshot, "st_file_attributes", 0))
    if not attributes & reparse_point_attribute:
        return None
    raw_tag = getattr(snapshot, "st_reparse_tag", None)
    return (
        int(raw_tag)
        if isinstance(raw_tag, int) and not isinstance(raw_tag, bool)
        else -1
    )


def is_unsupported_reparse(
    snapshot: os.stat_result,
    *,
    allow_hydrated_cloud_file: bool,
    reparse_point_attribute: int = WINDOWS_REPARSE_POINT_ATTRIBUTE,
    cloud_reparse_tags: frozenset[int] = WINDOWS_CLOUD_REPARSE_TAGS,
) -> bool:
    """Reject redirecting reparse points while permitting known cloud leaves."""
    tag = reparse_tag(
        snapshot,
        reparse_point_attribute=reparse_point_attribute,
    )
    if tag is None:
        return False
    return not (allow_hydrated_cloud_file and tag in cloud_reparse_tags)


def _failure(
    failure_kind: str,
    exc: Exception | None = None,
) -> ArtifactMetadataUnavailable:
    return ArtifactMetadataUnavailable(
        failure_kind,
        exception_type=type(exc).__name__ if exc is not None else None,
    )


def inspect_metadata_generation(
    path: Path,
    *,
    trusted_root: Path | None,
    reparse_point_attribute: int = WINDOWS_REPARSE_POINT_ATTRIBUTE,
    cloud_reparse_tags: frozenset[int] = WINDOWS_CLOUD_REPARSE_TAGS,
) -> ArtifactMetadataReceipt:
    """Inspect one file without following links, for bounded-worker use only."""
    if not path.is_absolute() or Path(os.path.abspath(path)) != path:
        raise ArtifactMetadataMalformed("artifact path must be lexical absolute")

    target = path
    snapshot: os.stat_result | None = None
    root_generation: FileGeneration | None = None
    if trusted_root is not None:
        if (
            not trusted_root.is_absolute()
            or Path(os.path.abspath(trusted_root)) != trusted_root
        ):
            raise ArtifactMetadataMalformed("trusted root must be lexical absolute")
        try:
            relative = path.relative_to(trusted_root)
        except ValueError as exc:
            raise _failure("root_escape") from exc
        if not relative.parts or any(
            component in {"", ".", ".."} for component in relative.parts
        ):
            raise _failure("root_escape")
        try:
            root_snapshot = trusted_root.lstat()
        except FileNotFoundError as exc:
            raise _failure("missing", exc) from exc
        except (OSError, RuntimeError) as exc:
            raise _failure("io", exc) from exc
        if (
            stat_module.S_ISLNK(root_snapshot.st_mode)
            or is_unsupported_reparse(
                root_snapshot,
                allow_hydrated_cloud_file=False,
                reparse_point_attribute=reparse_point_attribute,
                cloud_reparse_tags=cloud_reparse_tags,
            )
            or not stat_module.S_ISDIR(root_snapshot.st_mode)
        ):
            raise _failure("root_escape")
        root_generation = FileGeneration.from_directory_identity(root_snapshot)
        target = trusted_root
        for index, component in enumerate(relative.parts):
            target = target / component
            try:
                snapshot = target.lstat()
            except FileNotFoundError as exc:
                raise _failure("missing", exc) from exc
            except OSError as exc:
                raise _failure("io", exc) from exc
            is_leaf = index == len(relative.parts) - 1
            if stat_module.S_ISLNK(snapshot.st_mode) or is_unsupported_reparse(
                snapshot,
                allow_hydrated_cloud_file=is_leaf,
                reparse_point_attribute=reparse_point_attribute,
                cloud_reparse_tags=cloud_reparse_tags,
            ):
                raise _failure("symlink_or_reparse")
            if not is_leaf and not stat_module.S_ISDIR(snapshot.st_mode):
                raise _failure("not_regular")
    else:
        try:
            snapshot = target.lstat()
        except FileNotFoundError as exc:
            raise _failure("missing", exc) from exc
        except OSError as exc:
            raise _failure("io", exc) from exc

    if snapshot is None:  # pragma: no cover - guarded by non-empty relative parts
        raise ArtifactMetadataMalformed("metadata walk did not reach the artifact")
    if stat_module.S_ISLNK(snapshot.st_mode) or is_unsupported_reparse(
        snapshot,
        allow_hydrated_cloud_file=True,
        reparse_point_attribute=reparse_point_attribute,
        cloud_reparse_tags=cloud_reparse_tags,
    ):
        raise _failure("symlink_or_reparse")
    if not stat_module.S_ISREG(snapshot.st_mode):
        raise _failure("not_regular")
    generation = FileGeneration.from_stat(snapshot)
    return ArtifactMetadataReceipt(
        generation=generation,
        root_generation=root_generation,
        reparse_tag=reparse_tag(
            snapshot,
            reparse_point_attribute=reparse_point_attribute,
        ),
    )


def decode_artifact_metadata_payload(
    payload: object,
    *,
    unavailable_reason_code: str,
    reparse_point_attribute: int = WINDOWS_REPARSE_POINT_ATTRIBUTE,
    cloud_reparse_tags: frozenset[int] = WINDOWS_CLOUD_REPARSE_TAGS,
) -> ArtifactMetadataReceipt:
    """Decode the closed metadata envelope without assigning public semantics."""
    from collections.abc import Mapping

    if not isinstance(payload, Mapping):
        raise ArtifactMetadataMalformed("metadata payload must be an object")
    if payload.get("schema_version") != METADATA_SCHEMA_VERSION:
        raise ArtifactMetadataMalformed("metadata schema version is invalid")
    status = payload.get("status")
    if status == "unavailable":
        if set(payload) != {"schema_version", "status", "reason_code", "details"}:
            raise ArtifactMetadataMalformed("metadata failure fields are invalid")
        details = payload.get("details")
        if (
            payload.get("reason_code") != unavailable_reason_code
            or not isinstance(details, Mapping)
            or set(details) - {"failure_kind", "exception_type"}
            or not isinstance(details.get("failure_kind"), str)
            or details.get("failure_kind") not in METADATA_FAILURE_KINDS
        ):
            raise ArtifactMetadataMalformed("metadata failure payload is invalid")
        exception_type = details.get("exception_type")
        if exception_type is not None and (
            not isinstance(exception_type, str)
            or not exception_type
            or len(exception_type) > 128
        ):
            raise ArtifactMetadataMalformed("metadata exception type is invalid")
        raise ArtifactMetadataUnavailable(
            str(details["failure_kind"]),
            exception_type=(
                str(exception_type) if exception_type is not None else None
            ),
        )
    if status != "available" or set(payload) != {
        "schema_version",
        "status",
        "generation",
        "root_generation",
        "reparse_tag",
    }:
        raise ArtifactMetadataMalformed("metadata success fields are invalid")
    raw_generation = payload.get("generation")
    if not isinstance(raw_generation, Mapping):
        raise ArtifactMetadataMalformed("metadata generation is invalid")
    try:
        generation = FileGeneration.from_dict(raw_generation)
    except (TypeError, ValueError) as exc:
        raise ArtifactMetadataMalformed("metadata generation is invalid") from exc
    raw_root_generation = payload.get("root_generation")
    if raw_root_generation is None:
        root_generation = None
    elif isinstance(raw_root_generation, Mapping):
        try:
            root_generation = FileGeneration.from_dict(raw_root_generation)
        except (TypeError, ValueError) as exc:
            raise ArtifactMetadataMalformed(
                "metadata root generation is invalid"
            ) from exc
        if (
            not stat_module.S_ISDIR(root_generation.mode)
            or root_generation.size != 0
            or root_generation.mtime_ns != 0
            or root_generation.ctime_ns != 0
        ):
            raise ArtifactMetadataMalformed("metadata root identity is invalid")
    else:
        raise ArtifactMetadataMalformed("metadata root generation is invalid")
    observed_reparse_tag = payload.get("reparse_tag")
    if observed_reparse_tag is not None and (
        isinstance(observed_reparse_tag, bool)
        or not isinstance(observed_reparse_tag, int)
    ):
        raise ArtifactMetadataMalformed("metadata reparse tag is invalid")
    attributes = generation.file_attributes or 0
    has_reparse_attribute = bool(attributes & reparse_point_attribute)
    if (
        generation.size < 0
        or not stat_module.S_ISREG(generation.mode)
        or has_reparse_attribute != (observed_reparse_tag is not None)
        or (
            observed_reparse_tag is not None
            and observed_reparse_tag not in cloud_reparse_tags
        )
    ):
        raise ArtifactMetadataMalformed("metadata generation is inconsistent")
    return ArtifactMetadataReceipt(
        generation=generation,
        root_generation=root_generation,
        reparse_tag=observed_reparse_tag,
    )


def generation_cloud_placeholder_details(
    generation: FileGeneration,
    *,
    macos_dataless_flag: int = MACOS_DATALESS_FLAG,
    windows_cloud_file_attributes: int = WINDOWS_UNAVAILABLE_CLOUD_ATTRIBUTES,
) -> dict[str, object] | None:
    """Return closed platform facts when a generation is not locally readable."""
    return cloud_placeholder_details(
        flags=generation.flags,
        file_attributes=generation.file_attributes,
        macos_dataless_flag=macos_dataless_flag,
        windows_cloud_file_attributes=windows_cloud_file_attributes,
    )


def cloud_placeholder_details(
    *,
    flags: int | None,
    file_attributes: int | None,
    macos_dataless_flag: int = MACOS_DATALESS_FLAG,
    windows_cloud_file_attributes: int = WINDOWS_UNAVAILABLE_CLOUD_ATTRIBUTES,
) -> dict[str, object] | None:
    """Classify unavailable cloud bits without requiring a full generation."""
    normalized_flags = flags or 0
    normalized_attributes = file_attributes or 0
    if macos_dataless_flag and normalized_flags & macos_dataless_flag:
        return {"st_flags": normalized_flags}
    if (
        windows_cloud_file_attributes
        and normalized_attributes & windows_cloud_file_attributes
    ):
        return {"file_attributes": normalized_attributes}
    return None
