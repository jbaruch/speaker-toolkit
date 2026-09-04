"""Project metadata-only cloud-placeholder receipts into queue/preflight reports.

The evidence probes own platform flags and generation checks. This module never
opens, stats, hashes, or hydrates an artifact. Sizes are apparent download bytes,
not allocated disk blocks. Repeated references to one path count once.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


CLOUD_PLACEHOLDER_REASONS = frozenset(
    {
        "pdf_cloud_placeholder_unavailable",
        "pptx_cloud_placeholder_unavailable",
        "video_cloud_placeholder_unavailable",
    }
)
ARTIFACT_DATALESS = "artifact_dataless"


def unavailable_cloud_artifacts(sources: object) -> list[dict[str, Any]]:
    """Retain only closed placeholder failures, including unknown-size facts."""
    if not isinstance(sources, Mapping):
        return []
    result = []
    for source, record in sorted(sources.items()):
        if not isinstance(record, Mapping):
            continue
        if record.get("reason_code") not in CLOUD_PLACEHOLDER_REASONS:
            continue
        details = record.get("details")
        size = details.get("size_bytes") if isinstance(details, Mapping) else None
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            size = None
        result.append(
            {
                "source": source,
                "artifact_path": record.get("artifact_path"),
                "size_bytes": size,
                "reason_code": record["reason_code"],
            }
        )
    return result


def cloud_artifacts(assessment: Mapping[str, object]) -> list[dict[str, Any]]:
    """Read retained declarations, including sources superseded by a fallback."""
    retained = assessment.get("cloud_artifacts")
    result = [dict(item) for item in retained] if isinstance(retained, list) else []
    result.extend(
        unavailable_cloud_artifacts(assessment.get("unavailable_evidence_sources"))
    )
    unique = {(item["source"], item["artifact_path"]): item for item in result}
    return sorted(
        unique.values(), key=lambda item: (item["source"], str(item["artifact_path"]))
    )


def cloud_artifact_blocking_reason(assessment: Mapping[str, object]) -> str | None:
    """Explain the owner action needed before any fresh claim can proceed."""
    if not cloud_artifacts(assessment):
        return None
    return (
        f"{ARTIFACT_DATALESS}: declared local evidence is not downloaded; "
        "review preflight's cloud_artifacts count, total_bytes, and paths, "
        "download those files with the cloud provider, then rerun preflight"
    )


def summarize_cloud_artifacts(
    records: Iterable[tuple[str, Mapping[str, object]]],
) -> dict[str, Any]:
    """Report distinct paths, affected talks, and explicitly incomplete costs."""
    artifacts: dict[object, dict[str, Any]] = {}
    for filename, assessment in records:
        for item in cloud_artifacts(assessment):
            path = item["artifact_path"]
            key = path if path is not None else (filename, item["source"])
            if key not in artifacts:
                artifacts[key] = {
                    "artifact_path": path,
                    "size_bytes": item["size_bytes"],
                    "filenames": set(),
                    "sources": set(),
                }
            entry = artifacts[key]
            # A path observed with different sizes changed during this report;
            # do not turn either generation into a confident cost estimate.
            if entry["size_bytes"] != item["size_bytes"]:
                entry["size_bytes"] = None
            entry["filenames"].add(filename)
            entry["sources"].add(item["source"])
    rows = [
        {
            **entry,
            "filenames": sorted(entry["filenames"]),
            "sources": sorted(entry["sources"]),
        }
        for entry in artifacts.values()
    ]
    rows.sort(key=lambda row: (str(row["artifact_path"]), row["filenames"]))
    return {
        "schema_version": 1,
        "artifact_count": len(rows),
        "talk_count": len({name for row in rows for name in row["filenames"]}),
        "total_bytes": sum(row["size_bytes"] or 0 for row in rows),
        "unknown_size_count": sum(row["size_bytes"] is None for row in rows),
        "artifacts": rows,
    }
