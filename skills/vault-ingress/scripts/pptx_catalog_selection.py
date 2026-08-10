"""Live-observation selection for PPTX catalog visual evidence (#229).

A persisted receipt is a hint; what is on disk is the authority
(`stateful-artifacts` -> Hints, Not Authority). This module makes the two live
observations `classify_pptx_visual_evidence` requires — the deck's fingerprint
and the extraction artifact's digest — and returns one classified row per
catalog record.

One authority, two surfaces: `preflight-vault.py` turns these rows into
findings, and `classify-pptx-evidence.py` prints them as JSON for the ingress
workflow. Neither reimplements the observation or the classification.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from artifact_locator import ArtifactLocatorError, materialize_artifact_locator
from pptx_evidence import (
    PPTX_EXTRACTION_PIPELINE_VERSION,
    PPTX_EXTRACTION_SCHEMA_VERSION,
)
from tracking_database import (
    TrackingDatabaseError,
    classify_pptx_visual_evidence,
    pptx_visual_evidence_needs_extraction,
)

SELECTION_SCHEMA_VERSION = 1
_READ_CHUNK_BYTES = 1024 * 1024


def digest_and_size(path: object, root: object) -> tuple[str, int] | None:
    """SHA-256 and byte count of one artifact, or None when it cannot be read.

    None is the honest answer for an unresolvable locator or an unreadable
    file: the caller must not be able to mistake "not observed" for "matches".
    """
    if not isinstance(path, str) or not path.strip():
        return None
    try:
        resolved = materialize_artifact_locator(path, root)
    except ArtifactLocatorError:
        return None
    digest = hashlib.sha256()
    size = 0
    try:
        with open(resolved, "rb") as source:
            for chunk in iter(lambda: source.read(_READ_CHUNK_BYTES), b""):
                digest.update(chunk)
                size += len(chunk)
    except OSError:
        return None
    return digest.hexdigest(), size


def observed_source_fingerprint(
    pptx_path: object, pptx_source_dir: object
) -> dict[str, object] | None:
    """Fingerprint the deck as it exists now, in the extractor's shape."""
    observed = digest_and_size(pptx_path, pptx_source_dir)
    if observed is None:
        return None
    digest, size = observed
    return {"algorithm": "sha256", "digest": digest, "size_bytes": size}


def observed_artifact_digest(evidence: object, vault_root: object) -> str | None:
    """Digest the extraction artifact a receipt names, if it still exists.

    ``artifact.path`` is vault-root-relative. A deleted or replaced artifact
    must not stay authoritative.
    """
    if not isinstance(evidence, Mapping):
        return None
    artifact = evidence.get("artifact")
    if not isinstance(artifact, Mapping):
        return None
    observed = digest_and_size(artifact.get("path"), vault_root)
    return None if observed is None else observed[0]


def classify_catalog(
    database: Mapping[str, Any],
    *,
    vault_root: Path | str,
    pptx_source_dir: object,
) -> list[dict[str, Any]]:
    """Classify every catalog record against the live deck and artifact.

    A record whose receipt cannot be read is reported with a null
    classification and ``needs_extraction: true`` rather than dropped — a
    missing row would read as "nothing to regenerate".
    """
    catalog = database.get("pptx_catalog")
    if not isinstance(catalog, list):
        return []
    rows: list[dict[str, Any]] = []
    for index, record in enumerate(catalog):
        if not isinstance(record, Mapping):
            continue
        source = observed_source_fingerprint(record.get("pptx_path"), pptx_source_dir)
        artifact = observed_artifact_digest(record.get("visual_evidence"), vault_root)
        row: dict[str, Any] = {
            "index": index,
            "pptx_path": record.get("pptx_path"),
            "source_observed": source is not None,
            "artifact_observed": artifact is not None,
        }
        try:
            classification = classify_pptx_visual_evidence(
                record,
                extractor_schema_version=PPTX_EXTRACTION_SCHEMA_VERSION,
                pipeline_version=PPTX_EXTRACTION_PIPELINE_VERSION,
                observed_source_fingerprint=source,
                observed_artifact_digest=artifact,
            )
        except TrackingDatabaseError as exc:
            row["classification"] = None
            row["needs_extraction"] = True
            row["error"] = str(exc)
        else:
            row["classification"] = classification
            row["needs_extraction"] = pptx_visual_evidence_needs_extraction(
                classification
            )
        rows.append(row)
    return rows


__all__ = [
    "SELECTION_SCHEMA_VERSION",
    "classify_catalog",
    "digest_and_size",
    "observed_artifact_digest",
    "observed_source_fingerprint",
]
