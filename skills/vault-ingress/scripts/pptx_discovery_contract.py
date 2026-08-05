"""Versioned policy for bounded PPTX directory discovery.

This module is deliberately stdlib-only so database migration, preflight, and
the contained directory worker share one exact exclusion and completeness
contract without importing the PPTX extraction runtime.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Mapping, Sequence, cast


PPTX_DIRECTORY_BATCH_SCHEMA_VERSION = 1
PPTX_DIRECTORY_BATCH_KIND = "pptx_directory_batch"
PPTX_DIRECTORY_MANIFEST_SCHEMA_VERSION = 2
PPTX_DIRECTORY_MANIFEST_KIND = "directory"

PPTX_DIRECTORY_EXCLUSION_MAX_COUNT = 64
PPTX_DIRECTORY_EXCLUSION_MAX_CHARS = 255
DEFAULT_PPTX_DIRECTORY_EXCLUSIONS = (
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

# These skips are deliberate policy boundaries. Encountering only these still
# proves that every eligible directory and deck was considered.
PPTX_DIRECTORY_POLICY_SKIP_REASON_CODES = frozenset(
    {
        "pptx_batch_conflict_copy",
        "pptx_batch_directory_excluded",
        "pptx_batch_office_lock_file",
        "pptx_batch_reparse_point_rejected",
        "pptx_batch_skip_pattern",
        "pptx_batch_static_export",
        "pptx_batch_symlink_rejected",
    }
)

# Every other closed skip means an eligible subtree or deck was not proved.
# Public and private envelopes derive completeness from this set; callers never
# maintain a second taxonomy.
PPTX_DIRECTORY_INCOMPLETE_REASON_CODES = frozenset(
    {
        "pptx_archive_recovery_required",
        "pptx_artifact_changed",
        "pptx_artifact_unavailable",
        "pptx_batch_cloud_placeholder_unavailable",
        "pptx_batch_depth_limit",
        "pptx_batch_directory_changed",
        "pptx_batch_directory_identity_collision",
        "pptx_batch_directory_identity_unavailable",
        "pptx_batch_directory_limit",
        "pptx_batch_directory_unavailable",
        "pptx_batch_discovery_output_limit",
        "pptx_batch_discovery_protocol_invalid",
        "pptx_batch_discovery_resource_unavailable",
        "pptx_batch_discovery_start_failure",
        "pptx_batch_discovery_timeout",
        "pptx_batch_discovery_worker_failure",
        "pptx_batch_entry_limit",
        "pptx_batch_entry_unavailable",
        "pptx_batch_file_limit",
        "pptx_batch_input_limit",
        "pptx_batch_manifest_invalid",
        "pptx_batch_output_limit",
        "pptx_batch_path_invalid",
        "pptx_batch_path_limit",
        "pptx_batch_request_invalid",
        "pptx_batch_root_invalid",
        "pptx_batch_root_unavailable",
        "pptx_batch_scan_incomplete_file_limit",
        "pptx_batch_wall_limit",
        "pptx_cloud_placeholder_unavailable",
        "pptx_dependency_unavailable",
        "pptx_evidence_invalid",
        "pptx_extraction_failed",
        "pptx_invalid_container",
        "pptx_no_slides",
        "pptx_parse_failure",
        "pptx_probe_containment_unavailable",
        "pptx_probe_crash",
        "pptx_probe_exception",
        "pptx_probe_malformed_result",
        "pptx_probe_materialization_changed",
        "pptx_probe_monitor_identity_changed",
        "pptx_probe_monitor_unavailable",
        "pptx_probe_request_oversized",
        "pptx_probe_resource_unavailable",
        "pptx_probe_result_oversized",
        "pptx_probe_start_failure",
        "pptx_probe_timeout",
        "pptx_recovery_failure",
        "pptx_structural_damage",
    }
)
PPTX_DIRECTORY_SKIP_REASON_CODES = frozenset(
    {
        *PPTX_DIRECTORY_POLICY_SKIP_REASON_CODES,
        *PPTX_DIRECTORY_INCOMPLETE_REASON_CODES,
    }
)

# These reasons describe failure of the directory operation itself, rather
# than one eligible deck. They are valid only as the sole root receipt in a
# top-level error envelope.
PPTX_DIRECTORY_WHOLE_ROOT_REASON_CODES = frozenset(
    {
        "pptx_batch_discovery_output_limit",
        "pptx_batch_discovery_protocol_invalid",
        "pptx_batch_discovery_resource_unavailable",
        "pptx_batch_discovery_start_failure",
        "pptx_batch_discovery_timeout",
        "pptx_batch_discovery_worker_failure",
        "pptx_batch_manifest_invalid",
        "pptx_batch_request_invalid",
        "pptx_batch_root_invalid",
        "pptx_batch_root_unavailable",
    }
)

# A wall deadline can expire before discovery starts or after safe results have
# accumulated. The former may use a top-level error; the latter remains an
# ordinary partial envelope.
PPTX_DIRECTORY_ERROR_REASON_CODES = frozenset(
    {
        *PPTX_DIRECTORY_WHOLE_ROOT_REASON_CODES,
        "pptx_batch_wall_limit",
    }
)

# Public diagnostics expose only one optional path-neutral supervisor code.
# Keep the vocabulary closed so arbitrary worker strings, locators, and parser
# details cannot cross the public boundary.
PPTX_DIRECTORY_SUPERVISOR_REASON_CODES = frozenset(
    {
        "invalid_worker_command",
        "invalid_worker_request",
        "invalid_worker_response",
        "invalid_worker_response_bindings",
        "invalid_worker_response_body",
        "protocol_isolation_failed",
        "pptx_batch_request_invalid",
        "pptx_batch_root_invalid",
        "pptx_batch_root_unavailable",
        "unsafe_worker_process_metadata",
        "worker_cleanup_failed",
        "worker_containment_unavailable",
        "worker_diagnostic_limit_exceeded",
        "worker_diagnostic_read_failed",
        "worker_exit",
        "worker_exit_before_barrier",
        "worker_generation_binding_mismatch",
        "worker_generation_changed",
        "worker_input_limit_exceeded",
        "worker_memory_limit_exceeded",
        "worker_monitor_identity_changed",
        "worker_monitor_unavailable",
        "worker_output_limit_exceeded",
        "worker_output_read_failed",
        "worker_pipe_setup_failed",
        "worker_process_limit_exceeded",
        "worker_process_tree_leak",
        "worker_request_write_failed",
        "worker_response_authentication_failed",
        "worker_response_binding_mismatch",
        "worker_response_bindings_mismatch",
        "worker_response_body_mismatch",
        "worker_start_failed",
        "worker_timeout",
    }
)

_FORBIDDEN_PATTERN_CHARACTERS = frozenset("*?[]{}()|^$+")


class PptxDiscoveryContractError(ValueError):
    """PPTX directory discovery state violates its closed contract."""


@dataclass(frozen=True)
class PptxDirectoryBatchAssessment:
    """Completeness decision for a public directory-batch value."""

    state: str
    schema_version: int
    complete: bool | None
    incomplete_reason_codes: tuple[str, ...]


def validate_pptx_directory_exclusions(
    value: object,
    *,
    label: str = "pptx_directory_exclusions",
) -> list[str]:
    """Return one bounded exact-component exclusion list or raise."""
    if not isinstance(value, (list, tuple)) or len(value) > (
        PPTX_DIRECTORY_EXCLUSION_MAX_COUNT
    ):
        raise PptxDiscoveryContractError(
            f"{label} must be an array of at most "
            f"{PPTX_DIRECTORY_EXCLUSION_MAX_COUNT} directory components"
        )
    normalized: list[str] = []
    seen: set[str] = set()
    for index, component in enumerate(value):
        item_label = f"{label}[{index}]"
        if (
            not isinstance(component, str)
            or not component
            or component != component.strip()
            or len(component) > PPTX_DIRECTORY_EXCLUSION_MAX_CHARS
            or component in {".", ".."}
            or "/" in component
            or "\\" in component
            or any(
                unicodedata.category(character) in {"Cc", "Cf", "Cs"}
                for character in component
            )
            or any(character in _FORBIDDEN_PATTERN_CHARACTERS for character in component)
        ):
            raise PptxDiscoveryContractError(
                f"{item_label} must be one literal directory-name component"
            )
        identity = component.casefold()
        if identity in seen:
            raise PptxDiscoveryContractError(
                f"{label} contains a case-insensitive duplicate {component!r}"
            )
        seen.add(identity)
        normalized.append(component)
    return normalized


def directory_component_is_excluded(
    component: str,
    exclusions: Sequence[str],
) -> bool:
    """Match one directory name by exact case-folded component identity."""
    return component.casefold() in {item.casefold() for item in exclusions}


def _validate_skipped(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise PptxDiscoveryContractError("skipped must be an array")
    skipped: list[dict[str, str]] = []
    seen_receipts: set[tuple[str, str]] = set()
    seen_nonroot_paths: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, Mapping) or set(item) != {"path", "reason"}:
            raise PptxDiscoveryContractError(
                f"skipped[{index}] must contain only path and reason"
            )
        path = item.get("path")
        reason = item.get("reason")
        if not isinstance(path, str) or not path:
            raise PptxDiscoveryContractError(
                f"skipped[{index}].path must be a nonempty string"
            )
        if not isinstance(reason, str) or reason not in PPTX_DIRECTORY_SKIP_REASON_CODES:
            raise PptxDiscoveryContractError(
                f"skipped[{index}].reason is outside the closed taxonomy"
            )
        receipt = (path, reason)
        if receipt in seen_receipts or (path != "." and path in seen_nonroot_paths):
            raise PptxDiscoveryContractError(
                f"skipped[{index}] duplicates an existing path receipt"
            )
        seen_receipts.add(receipt)
        if path != ".":
            seen_nonroot_paths.add(path)
        skipped.append({"path": path, "reason": reason})
    for path in seen_nonroot_paths:
        components = path.split("/")
        for length in range(1, len(components)):
            ancestor = "/".join(components[:length])
            if ancestor in seen_nonroot_paths:
                raise PptxDiscoveryContractError(
                    "skipped contains a descendant of another skipped path"
                )
    return skipped


def directory_incomplete_reason_codes(skipped: object) -> list[str]:
    """Derive stable unique completeness failures from closed skip receipts."""
    validated = _validate_skipped(skipped)
    return sorted(
        {
            item["reason"]
            for item in validated
            if item["reason"] in PPTX_DIRECTORY_INCOMPLETE_REASON_CODES
        }
    )


def build_pptx_directory_batch(
    results: object,
    skipped: object,
    *,
    error: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build the strict public v1 envelope from safe results and receipts."""
    if not isinstance(results, list) or any(
        not isinstance(result, Mapping) for result in results
    ):
        raise PptxDiscoveryContractError("results must be an array of objects")
    validated_skipped = _validate_skipped(skipped)
    reasons = directory_incomplete_reason_codes(validated_skipped)
    whole_root_receipts = [
        item
        for item in validated_skipped
        if item["reason"] in PPTX_DIRECTORY_WHOLE_ROOT_REASON_CODES
    ]
    if whole_root_receipts and error is None:
        raise PptxDiscoveryContractError(
            "whole-root receipts require a matching top-level error"
        )
    output: dict[str, object] = {
        "schema_version": PPTX_DIRECTORY_BATCH_SCHEMA_VERSION,
        "kind": PPTX_DIRECTORY_BATCH_KIND,
        "complete": not reasons,
        "incomplete_reason_codes": reasons,
        "results": results,
        "skipped": validated_skipped,
    }
    if error is not None:
        if set(error) != {"reason_code", "details"}:
            raise PptxDiscoveryContractError(
                "error must contain only reason_code and details"
            )
        reason_code = error.get("reason_code")
        details = error.get("details")
        if (
            not isinstance(reason_code, str)
            or reason_code not in PPTX_DIRECTORY_ERROR_REASON_CODES
            or not isinstance(details, Mapping)
            or results
            or validated_skipped != [{"path": ".", "reason": reason_code}]
        ):
            raise PptxDiscoveryContractError(
                "whole-root error must bind one incomplete root receipt and no results"
            )
        if set(details) - {"supervisor_reason_code"}:
            raise PptxDiscoveryContractError(
                "error.details may contain only supervisor_reason_code"
            )
        supervisor_reason_code = details.get("supervisor_reason_code")
        if (
            "supervisor_reason_code" in details
            and (
                not isinstance(supervisor_reason_code, str)
                or supervisor_reason_code
                not in PPTX_DIRECTORY_SUPERVISOR_REASON_CODES
            )
        ):
            raise PptxDiscoveryContractError(
                "error.details supervisor_reason_code is outside the closed taxonomy"
            )
        public_details = (
            {"supervisor_reason_code": supervisor_reason_code}
            if "supervisor_reason_code" in details
            else {}
        )
        output["error"] = {
            "reason_code": reason_code,
            "details": public_details,
        }
    return output


def decode_pptx_directory_batch(value: object) -> dict[str, object]:
    """Validate and copy one strict public v1 batch envelope."""
    if not isinstance(value, Mapping):
        raise PptxDiscoveryContractError("directory batch must be an object")
    expected = {
        "schema_version",
        "kind",
        "complete",
        "incomplete_reason_codes",
        "results",
        "skipped",
    }
    has_error = "error" in value
    if set(value) != expected | ({"error"} if has_error else set()):
        raise PptxDiscoveryContractError("directory batch has an invalid shape")
    if (
        type(value.get("schema_version")) is not int
        or value.get("schema_version") != PPTX_DIRECTORY_BATCH_SCHEMA_VERSION
        or value.get("kind") != PPTX_DIRECTORY_BATCH_KIND
        or type(value.get("complete")) is not bool
        or not isinstance(value.get("incomplete_reason_codes"), list)
    ):
        raise PptxDiscoveryContractError("directory batch has an invalid generation")
    error = value.get("error") if has_error else None
    built = build_pptx_directory_batch(
        value.get("results"),
        value.get("skipped"),
        error=error if isinstance(error, Mapping) else None,
    )
    if has_error and not isinstance(error, Mapping):
        raise PptxDiscoveryContractError("directory batch error must be an object")
    if value.get("complete") != built["complete"] or value.get(
        "incomplete_reason_codes"
    ) != built["incomplete_reason_codes"]:
        raise PptxDiscoveryContractError(
            "directory batch completeness does not match its skip receipts"
        )
    return built


def assess_pptx_directory_batch(value: object) -> PptxDirectoryBatchAssessment:
    """Classify v1 output; legacy unversioned output is completeness-unknown."""
    if isinstance(value, Mapping) and set(value) == {"results", "skipped"}:
        if not isinstance(value.get("results"), list) or not isinstance(
            value.get("skipped"), list
        ):
            raise PptxDiscoveryContractError("legacy directory batch is malformed")
        return PptxDirectoryBatchAssessment(
            state="unknown_legacy",
            schema_version=0,
            complete=None,
            incomplete_reason_codes=("pptx_directory_batch_completeness_unknown",),
        )
    decoded = decode_pptx_directory_batch(value)
    reasons = tuple(cast(list[str], decoded["incomplete_reason_codes"]))
    return PptxDirectoryBatchAssessment(
        state="complete" if decoded["complete"] else "partial",
        schema_version=PPTX_DIRECTORY_BATCH_SCHEMA_VERSION,
        complete=bool(decoded["complete"]),
        incomplete_reason_codes=reasons,
    )
