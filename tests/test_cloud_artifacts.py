"""Cloud readiness and cost reports use probe facts, never artifact byte I/O."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "skills/vault-ingress/scripts"))

from cloud_artifacts import (  # noqa: E402
    cloud_artifact_blocking_reason,
    cloud_artifacts,
    summarize_cloud_artifacts,
)


def assessment(
    source="static_slides",
    *,
    reason="pdf_cloud_placeholder_unavailable",
    size=1200,
    path="/vault/slides/deck.pdf",
):
    return {
        "verified_capabilities": ("transcript",),
        "acquisition_capabilities": ("slides",),
        "unavailable_evidence_sources": {
            source: {
                "reason_code": reason,
                "artifact_path": path,
                "details": {"size_bytes": size},
            }
        },
    }


@pytest.mark.parametrize(
    ("source", "reason"),
    [
        ("static_slides", "pdf_cloud_placeholder_unavailable"),
        ("native_deck", "pptx_cloud_placeholder_unavailable"),
        ("delivery_video", "video_cloud_placeholder_unavailable"),
    ],
)
def test_independent_sources_do_not_hide_pending_cloud_evidence(source, reason):
    report = assessment(source, reason=reason)
    assert cloud_artifacts(report)[0]["size_bytes"] == 1200
    message = cloud_artifact_blocking_reason(report)
    assert message is not None
    assert "artifact_dataless" in message
    assert "download" in message


@pytest.mark.parametrize(
    "reason", ["pdf_artifact_unavailable", "pdf_probe_timeout", "pdf_invalid_container"]
)
def test_absent_or_invalid_evidence_is_not_reported_as_cloud(reason):
    assert cloud_artifact_blocking_reason(assessment(reason=reason)) is None


def test_cost_counts_one_file_shared_by_two_talks_once():
    report = summarize_cloud_artifacts(
        [
            ("first.md", assessment()),
            ("second.md", assessment()),
            (
                "second.md",
                assessment(
                    "native_deck",
                    reason="pptx_cloud_placeholder_unavailable",
                    size=800,
                    path="/vault/source.pptx",
                ),
            ),
        ]
    )
    assert report["artifact_count"] == 2
    assert report["talk_count"] == 2
    assert report["total_bytes"] == 2000
    assert report["unknown_size_count"] == 0
    assert report["artifacts"][0]["filenames"] == ["first.md", "second.md"]


@pytest.mark.parametrize("size", [None, True, -1, "1200"])
def test_unknown_cost_stays_explicit(size):
    report = summarize_cloud_artifacts([("talk.md", assessment(size=size))])
    assert report["artifact_count"] == 1
    assert report["total_bytes"] == 0
    assert report["unknown_size_count"] == 1


def test_changed_size_cannot_be_reported_as_a_confident_total():
    report = summarize_cloud_artifacts(
        [
            ("one.md", assessment(size=1200)),
            ("two.md", assessment(size=1400)),
        ]
    )
    assert report["unknown_size_count"] == 1
    assert report["total_bytes"] == 0


def test_available_fallback_does_not_erase_declared_cloud_artifact():
    retained = cloud_artifacts(assessment())
    report = {"cloud_artifacts": retained, "unavailable_evidence_sources": {}}
    assert cloud_artifact_blocking_reason(report) is not None
    assert summarize_cloud_artifacts([("talk.md", report)])["total_bytes"] == 1200
