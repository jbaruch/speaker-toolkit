"""Cross-consumer integrity tests for Presentation Pattern catalog loading."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest


def _copy_bundled_catalog(return_validation, tmp_path: Path, name: str) -> Path:
    return Path(
        shutil.copytree(return_validation.default_catalog_dir(), tmp_path / name)
    )


def test_auditor_and_return_validator_share_complete_fingerprint(
    tmp_path,
    audit_pattern_catalog,
    return_validation,
):
    baseline_root = _copy_bundled_catalog(
        return_validation, tmp_path, "baseline-patterns"
    )
    changed_root = _copy_bundled_catalog(
        return_validation, tmp_path, "changed-patterns"
    )
    changed_index = changed_root / "_index.md"
    changed_index.write_bytes(
        changed_index.read_bytes() + b"\n<!-- fingerprint regression -->\n"
    )

    baseline_report = audit_pattern_catalog.audit_catalog(baseline_root)
    changed_report = audit_pattern_catalog.audit_catalog(changed_root)
    baseline_catalog = return_validation.load_catalog(baseline_root)
    changed_catalog = return_validation.load_catalog(changed_root)

    assert baseline_report["valid"] is True
    assert changed_report["valid"] is True
    assert baseline_report["catalog"]["fingerprint"] == baseline_catalog.fingerprint
    assert changed_report["catalog"]["fingerprint"] == changed_catalog.fingerprint
    assert changed_catalog.fingerprint != baseline_catalog.fingerprint


def test_duplicate_nested_yaml_key_fails_every_catalog_consumer(
    tmp_path,
    aggregate_catalog_feedback,
    audit_pattern_catalog,
    return_validation,
):
    root = _copy_bundled_catalog(return_validation, tmp_path, "patterns")
    entry_path = root / "build" / "bookends.md"
    original = entry_path.read_text(encoding="utf-8")
    entry_path.write_text(
        original.replace(
            "id: bookends\n",
            "id: bookends\nintegrity_probe:\n  result: first\n  result: second\n",
            1,
        ),
        encoding="utf-8",
    )

    audit_report = audit_pattern_catalog.audit_catalog(root)
    feedback_path = tmp_path / "return.json"
    feedback_path.write_text(
        json.dumps(
            {
                "filename": "talk.md",
                "status": "processed",
                "catalog_feedback": {},
            }
        ),
        encoding="utf-8",
    )
    aggregate_report = aggregate_catalog_feedback.aggregate_feedback(
        [feedback_path], catalog_path=root
    )

    assert audit_report["valid"] is False
    assert "frontmatter_duplicate_key" in {
        issue["code"] for issue in audit_report["errors"]
    }
    assert aggregate_report["ok"] is False
    assert "catalog_frontmatter_duplicate_key" in {
        issue["code"] for issue in aggregate_report["catalog"]["errors"]
    }
    with pytest.raises(
        return_validation.ReturnValidationError,
        match="duplicate YAML frontmatter keys",
    ):
        return_validation.load_catalog(root)
