"""Regression tests for the offline vault identity/source preflight."""

from copy import deepcopy
import importlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest


VIDEO_ID = "AbCdEfGhI_1"
OTHER_VIDEO_ID = "ZyXwVuTsR_2"
DRIVE_ID = "drive-file-123"
QUEUE_STATE_SCRIPT = (
    Path(__file__).parents[1]
    / "skills"
    / "vault-ingress"
    / "scripts"
    / "queue-state.py"
)


@pytest.fixture
def vault_fixture(tmp_path):
    vault = tmp_path / "vault"
    transcripts = vault / "transcripts"
    slides = vault / "slides"
    pptx_source = tmp_path / "presentations"
    transcripts.mkdir(parents=True)
    slides.mkdir()
    pptx_source.mkdir()
    return {
        "root": vault,
        "transcripts": transcripts,
        "slides": slides,
        "pptx_source": pptx_source,
        "database": vault / "tracking-database.json",
    }


def base_talk(**updates: Any) -> dict[str, Any]:
    talk = {
        "filename": "2026-07-30-perfect-ingress.md",
        "title": "Perfect Vault Ingress",
        "date": "2026-07-30",
        "video_url": f"https://www.youtube.com/watch?v={VIDEO_ID}",
        "youtube_id": VIDEO_ID,
        "transcript_source": "youtube_auto",
        "slide_source": "none",
        "status": "processed",
    }
    talk.update(updates)
    return talk


def current_v5_talk(preflight_vault, **updates: Any) -> dict[str, Any]:
    talk = base_talk()
    talk.update({
        "schema_version": 5,
        "pattern_scoring_generation_status": "current",
        "pattern_scoring_generation_reasons": [],
        "pattern_scoring_schema_version": (
            preflight_vault.PATTERN_SCORING_SCHEMA_VERSION
        ),
        "pattern_observations": {
            "evidence_schema_version": (
                preflight_vault.PATTERN_EVIDENCE_SCHEMA_VERSION
            ),
        },
    })
    talk.update(updates)
    return talk


def source_identity(**updates):
    evidence = {
        "schema_version": 1,
        "provider": "youtube",
        "video_id": VIDEO_ID,
        "title": "Perfect Vault Ingress — Baruch Sadogursky",
        "uploader": "Conference Channel",
        "uploader_id": "@conference",
        "speakers": ["Baruch Sadogursky"],
        "recorded_date": "2026-07-30",
        "upload_date": "2026-07-31",
        "duration_seconds": 2700,
        "webpage_url": f"https://www.youtube.com/watch?v={VIDEO_ID}",
        "webpage_video_id": VIDEO_ID,
        "captured_at": "2026-07-31T12:00:00Z",
    }
    evidence.update(updates)
    return evidence


def write_database(fixture, talks, config=None):
    database = {
        "config": config or {
            "speaker_name": "Baruch Sadogursky",
            "pptx_source_dir": str(fixture["pptx_source"]),
        },
        "talks": talks,
    }
    fixture["database"].write_text(
        json.dumps(database, indent=2), encoding="utf-8"
    )
    return fixture["database"]


def materialize_transcript(fixture, video_id=VIDEO_ID):
    path = fixture["transcripts"] / f"{video_id}.txt"
    # Long enough to remain plausible for the 45-minute provider-duration
    # fixtures. Tests targeting identity/provenance should not accidentally
    # exercise the shared partial-transcript guard.
    text = " ".join(["substantive transcript evidence"] * 600)
    path.write_text(text, encoding="utf-8")
    transcript_timing = importlib.import_module("transcript_timing")
    transcript_timing.write_quality_receipt(
        path,
        text,
        transcript_timing.build_quality_policy(400),
        {"kind": "fixed_default"},
    )
    return path


def trusted_video_manifest(fixture, page_count=1):
    rebuild = fixture["root"] / "slides-rebuild" / VIDEO_ID
    rebuild.mkdir(parents=True, exist_ok=True)
    source_video = rebuild / f"{VIDEO_ID}.mp4"
    source_video.write_bytes(b"video fixture")
    candidate = rebuild / f"{VIDEO_ID}.slide-region.pdf"
    candidate.write_bytes(b"%PDF cropped fixture")
    retained = [
        {"page_number": page, "frame_index": page - 1,
         "timestamp_seconds": float((page - 1) * 2)}
        for page in range(1, page_count + 1)
    ]
    return {
        "slide_source": "video_extracted",
        "schema_version": 3,
        "pipeline_version": "0.10.0",
        "source_video_id": VIDEO_ID,
        "source_video_path": str(source_video),
        "total_frames_extracted": page_count,
        "unique_frame_count": page_count,
        "authored_slide_count": None,
        "hash_threshold_used": 8,
        "slide_region_detected": False,
        "slide_region_applied": True,
        "slide_region_method": "manual",
        "slide_region_verified": True,
        "slide_region": [0.05, 0.02, 0.78, 0.98],
        "fps_used": 0.5,
        "retained_frames": retained,
        "review_required": False,
        "review_reason": None,
        "artifacts": [{
            "path": str(candidate),
            "artifact_scope": "slide_region",
            "page_count": page_count,
            "source_video_id": VIDEO_ID,
            "source_video_path": str(source_video),
            "crop_method": "manual",
            "crop_verified": True,
            "trusted_for_authored_slide_analysis": True,
        }],
    }


def context_video_manifest(fixture, page_count=1):
    manifest = trusted_video_manifest(fixture, page_count)
    rebuild = fixture["root"] / "slides-rebuild" / VIDEO_ID
    context = rebuild / f"{VIDEO_ID}.context.pdf"
    context.write_bytes(b"%PDF context fixture")
    source_video = manifest["source_video_path"]
    manifest.update({
        "slide_region_detected": False,
        "slide_region_applied": False,
        "slide_region_method": "none",
        "slide_region_verified": False,
        "slide_region": None,
        "review_required": True,
        "review_reason": "No verified slide region is available.",
        "artifacts": [{
            "path": str(context),
            "artifact_scope": "full_frame_context",
            "page_count": page_count,
            "source_video_id": VIDEO_ID,
            "source_video_path": source_video,
            "crop_method": "none",
            "crop_verified": False,
            "trusted_for_authored_slide_analysis": False,
        }],
    })
    return manifest


def finding_codes(report, severity=None):
    return {
        finding["code"]
        for finding in report["findings"]
        if severity is None or finding["severity"] == severity
    }


@pytest.mark.parametrize(("url", "expected"), [
    (f"https://www.youtube.com/watch?v={VIDEO_ID}&t=42", VIDEO_ID),
    (f"https://youtu.be/{VIDEO_ID}?feature=shared", VIDEO_ID),
    (f"https://www.youtube.com/shorts/{VIDEO_ID}?si=x", VIDEO_ID),
    (f"https://www.youtube.com/embed/{VIDEO_ID}", VIDEO_ID),
    (f"https://www.youtube-nocookie.com/embed/{VIDEO_ID}", VIDEO_ID),
])
def test_youtube_id_parser_covers_supported_source_forms(preflight_vault, url, expected):
    assert preflight_vault.parse_youtube_id(url) == expected


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=too-short",
    "https://www.youtube.com/live/AbCdEfGhI_1",
    "https://videos.example.com/watch?v=AbCdEfGhI_1",
])
def test_youtube_id_parser_rejects_unsupported_or_invalid_urls(preflight_vault, url):
    assert preflight_vault.parse_youtube_id(url) is None


def test_clean_record_has_no_findings(preflight_vault, vault_fixture):
    materialize_transcript(vault_fixture)
    (vault_fixture["slides"] / f"{DRIVE_ID}.pdf").write_bytes(b"%PDF fixture")
    pptx = vault_fixture["pptx_source"] / "Conf" / "Perfect.pptx"
    pptx.parent.mkdir()
    pptx.write_bytes(b"PPTX fixture")
    talk = base_talk(
        slide_source="both",
        google_drive_id=DRIVE_ID,
        pptx_path="Conf/Perfect.pptx",
        duration_seconds=2700,
        source_identity=source_identity(),
    )
    write_database(vault_fixture, [talk])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert report["ok"] is True
    assert report["blocking_count"] == 0
    assert report["warning_count"] == 0
    assert report["findings"] == []


def test_missing_quality_receipt_is_actionable_for_completed_evidence(
    preflight_vault,
    vault_fixture,
):
    transcript = materialize_transcript(vault_fixture)
    transcript.with_suffix(".quality.json").unlink()
    talk = base_talk(source_identity=source_identity())
    write_database(vault_fixture, [talk])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert "transcript_quality_receipt_unverified" in finding_codes(
        report, "warning")
    finding = next(
        item for item in report["findings"]
        if item["code"] == "transcript_quality_receipt_unverified"
    )
    assert finding["capability_fact"]["repair_capabilities"] == ["transcript"]


def test_current_v5_missing_quality_receipt_remains_blocking(
    preflight_vault,
    vault_fixture,
):
    transcript = materialize_transcript(vault_fixture)
    transcript.with_suffix(".quality.json").unlink()
    talk = current_v5_talk(
        preflight_vault,
        source_identity=source_identity(),
    )
    write_database(vault_fixture, [talk])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert "transcript_quality_receipt_unverified" in finding_codes(
        report, "blocking")


def test_current_v5_missing_declared_artifact_remains_blocking(
    preflight_vault,
    vault_fixture,
):
    talk = current_v5_talk(
        preflight_vault,
        video_url=None,
        youtube_id=None,
        transcript_source="manual",
        transcript_path="transcripts/missing.txt",
    )
    write_database(vault_fixture, [talk])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert "transcript_artifact_missing" in finding_codes(report, "blocking")


def test_legacy_quality_warning_allows_normalize_to_requeue(
    preflight_vault,
    vault_fixture,
):
    transcript = materialize_transcript(vault_fixture)
    transcript.with_suffix(".quality.json").unlink()
    write_database(vault_fixture, [base_talk()])

    report = preflight_vault.run_preflight(vault_fixture["root"])
    assert report["ok"] is True
    assert "transcript_quality_receipt_unverified" in finding_codes(
        report, "warning")

    completed = subprocess.run(
        [
            sys.executable,
            str(QUEUE_STATE_SCRIPT),
            str(vault_fixture["database"]),
            "normalize",
        ],
        cwd=QUEUE_STATE_SCRIPT.parents[3],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    normalized = json.loads(vault_fixture["database"].read_text(encoding="utf-8"))
    assert normalized["talks"][0]["status"] == "needs-reprocessing"
    assert normalized["talks"][0]["reprocess_reason"].endswith(
        ":missing_generation_status"
    )


def test_quality_receipt_duration_uses_acquisition_level_tolerance(
    preflight_vault,
    vault_fixture,
):
    transcript = materialize_transcript(vault_fixture)
    transcript_timing = importlib.import_module("transcript_timing")
    text = transcript.read_text(encoding="utf-8")
    transcript_timing.write_quality_receipt(
        transcript,
        text,
        transcript_timing.build_quality_policy(
            400, trusted_duration_seconds=2700.0),
        {
            "kind": "youtube_duration",
            "video_id": VIDEO_ID,
            "duration_seconds": 2700.0,
        },
    )
    # This would have passed the retired max(60 seconds, 5%) comparison.
    talk = base_talk(source_identity=source_identity(duration_seconds=2702.0))
    write_database(vault_fixture, [talk])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert "transcript_quality_provenance_mismatch" in finding_codes(
        report, "blocking")


def test_h1b_upload_before_delivery_is_blocking(preflight_vault, vault_fixture):
    """H1b shape: source evidence predates the event it allegedly records."""
    materialize_transcript(vault_fixture)
    talk = base_talk(
        duration_seconds=2700,
        source_identity=source_identity(upload_date="2025-12-31"),
    )
    write_database(vault_fixture, [talk])

    report = preflight_vault.run_preflight(vault_fixture["database"])

    assert "source_identity_upload_predates_talk" in finding_codes(
        report, "blocking"
    )
    assert report["ok"] is False


def test_h4_wrong_recording_evidence_is_blocking(preflight_vault, vault_fixture):
    """H4 shape: valid metadata was captured, but for an unrelated recording."""
    materialize_transcript(vault_fixture)
    talk = base_talk(
        duration_seconds=2700,
        source_identity=source_identity(
            video_id=OTHER_VIDEO_ID,
            title="Kubernetes Security from First Principles",
            speakers=["Alice Example"],
            duration_seconds=300,
        ),
    )
    write_database(vault_fixture, [talk])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert {
        "source_identity_video_id_mismatch",
        "source_identity_title_mismatch",
        "source_identity_speaker_mismatch",
        "source_identity_duration_mismatch",
    } <= finding_codes(report, "blocking")


def test_short_provider_title_with_matching_event_passes_identity_preflight(
    preflight_vault, vault_fixture,
):
    materialize_transcript(vault_fixture)
    catalog_title = (
        "Coding Fast and Slow: Applying Kahneman's Insights to Improve "
        "Development Practices and Efficiency"
    )
    talk = base_talk(
        title=catalog_title,
        conference="Dev2Next 2026",
        source_identity=source_identity(
            title="Coding Fast and Slow at Dev2Next 2026",
        ),
    )
    write_database(vault_fixture, [talk])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert "source_identity_title_mismatch" not in finding_codes(report)
    assert "source_identity_event_mismatch" not in finding_codes(report)


def test_short_provider_title_from_wrong_event_is_blocking(
    preflight_vault, vault_fixture,
):
    materialize_transcript(vault_fixture)
    catalog_title = (
        "Coding Fast and Slow: Applying Kahneman's Insights to Improve "
        "Development Practices and Efficiency"
    )
    active = base_talk(
        title=catalog_title,
        conference="Conference Alpha 2024",
        date="2024-06-26",
        source_identity=source_identity(
            title="Coding Fast and Slow at Devoxx Poland 2024",
            recorded_date="2024-06-26",
            upload_date="2024-07-01",
        ),
    )
    known_other_event = base_talk(
        filename="2024-06-19-devoxx-poland-catalog-only.md",
        title=catalog_title,
        conference="Devoxx Poland 2024",
        date="2024-06-19",
        video_url=None,
        youtube_id=None,
        transcript_source="none",
        status="skipped_no_sources",
    )
    write_database(vault_fixture, [active, known_other_event])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert "source_identity_title_mismatch" not in finding_codes(report)
    assert "source_identity_event_mismatch" in finding_codes(
        report, "blocking",
    )


def test_speaker_match_accepts_surname_but_not_unrelated_given_name(preflight_vault):
    assert preflight_vault.names_agree("Baruch Sadogursky", "Sadogursky")
    assert preflight_vault.names_agree(
        "Baruch Sadogursky", "Sadogursky, Baruch (JFrog)"
    )
    assert not preflight_vault.names_agree("Baruch Sadogursky", "Baruch")


def test_url_and_stored_youtube_id_must_agree(preflight_vault, vault_fixture):
    materialize_transcript(vault_fixture, OTHER_VIDEO_ID)
    talk = base_talk(youtube_id=OTHER_VIDEO_ID)
    write_database(vault_fixture, [talk])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    finding = next(
        item for item in report["findings"]
        if item["code"] == "youtube_id_mismatch"
    )
    assert finding["expected"] == VIDEO_ID
    assert finding["actual"] == OTHER_VIDEO_ID
    assert finding["severity"] == "blocking"


def test_duplicate_video_requires_an_explicit_relation(preflight_vault, vault_fixture):
    materialize_transcript(vault_fixture)
    first = base_talk()
    second = deepcopy(first)
    second["filename"] = "2026-07-31-second-catalog-record.md"
    write_database(vault_fixture, [first, second])

    unqualified = preflight_vault.run_preflight(vault_fixture["root"])
    assert "duplicate_youtube_id" in finding_codes(unqualified, "blocking")

    second["source_relation"] = {
        "type": "borrowed_recording",
        "target_filename": first["filename"],
    }
    write_database(vault_fixture, [first, second])
    qualified = preflight_vault.run_preflight(vault_fixture["root"])
    assert "duplicate_youtube_id" not in finding_codes(qualified)
    assert qualified["blocking_count"] == 0


def test_known_bad_source_cannot_be_reactivated_in_another_url_form(
    preflight_vault, vault_fixture,
):
    materialize_transcript(vault_fixture)
    talk = base_talk(source_rejections=[{
        "source_type": "video",
        "url": f"https://youtu.be/{VIDEO_ID}",
        "reason": "wrong_delivery",
        "evidence": "provider metadata names a different conference",
        "verified_at": "2026-07-31T14:00:00-05:00",
    }])
    write_database(vault_fixture, [talk])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert "rejected_source_reactivated" in finding_codes(report, "blocking")


def test_inactive_well_formed_source_rejection_is_valid(
    preflight_vault, vault_fixture,
):
    talk = base_talk(
        video_url=None,
        youtube_id=None,
        transcript_source="none",
        source_rejections=[{
            "source_type": "video",
            "url": f"https://youtu.be/{VIDEO_ID}",
            "reason": "non_delivery_clip",
            "evidence": "duration is only 226 seconds",
            "verified_at": "2026-07-31T14:00:00-05:00",
        }],
    )
    write_database(vault_fixture, [talk])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert report["blocking_count"] == 0
    assert not finding_codes(report)


def test_known_bad_slide_source_cannot_return_in_another_drive_url_form(
    preflight_vault, vault_fixture,
):
    materialize_transcript(vault_fixture)
    talk = base_talk(
        slides_url=f"https://drive.google.com/open?id={DRIVE_ID}",
        source_rejections=[{
            "source_type": "slides",
            "url": f"https://drive.google.com/file/d/{DRIVE_ID}/view",
            "reason": "wrong_delivery",
            "evidence": "the footer names a different conference",
            "verified_at": "2026-07-31T14:00:00-05:00",
        }],
    )
    write_database(vault_fixture, [talk])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert "rejected_source_reactivated" in finding_codes(report, "blocking")


@pytest.mark.parametrize("bad_rejections", [
    {},
    ["not an object"],
    [{"source_type": "video", "url": "https://example.com"}],
    [{
        "source_type": "video", "url": "https://example.com",
        "reason": "wrong", "evidence": "verified",
        "verified_at": "2026-07-31T14:00:00",
    }],
])
def test_malformed_source_rejection_is_blocking(
    preflight_vault, vault_fixture, bad_rejections,
):
    materialize_transcript(vault_fixture)
    talk = base_talk(source_rejections=bad_rejections)
    write_database(vault_fixture, [talk])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert finding_codes(report, "blocking") & {
        "source_rejections_shape_invalid", "source_rejection_invalid",
    }


def test_legacy_duplicate_relation_only_waives_the_same_recording(
    preflight_vault, vault_fixture,
):
    materialize_transcript(vault_fixture)
    first = base_talk()
    second = deepcopy(first)
    second.update({
        "filename": "legacy-duplicate.md",
        "_duplicate_of": first["filename"],
    })
    write_database(vault_fixture, [first, second])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert "duplicate_youtube_id" not in finding_codes(report)
    assert report["blocking_count"] == 0


@pytest.mark.parametrize(("fault_code", "severity"), [
    ("slide_source_unsupported", "blocking"),
    ("slide_pptx_reference_missing", "warning"),
    ("slide_pptx_artifact_missing", "warning"),
    ("slide_pdf_reference_missing", "warning"),
    ("slide_pdf_artifact_missing", "warning"),
    ("slide_video_reference_missing", "blocking"),
    ("slide_video_artifact_missing", "warning"),
])
def test_all_seven_slide_contract_fault_classes_are_reported(
    preflight_vault, vault_fixture, fault_code, severity,
):
    materialize_transcript(vault_fixture)
    talk = base_talk()
    if fault_code == "slide_source_unsupported":
        talk["slide_source"] = "transcript_only"
    elif fault_code == "slide_pptx_reference_missing":
        talk["slide_source"] = "pptx"
    elif fault_code == "slide_pptx_artifact_missing":
        talk.update(slide_source="pptx", pptx_path="missing.pptx")
    elif fault_code == "slide_pdf_reference_missing":
        talk["slide_source"] = "pdf"
    elif fault_code == "slide_pdf_artifact_missing":
        talk.update(slide_source="pdf", google_drive_id=DRIVE_ID)
    elif fault_code == "slide_video_reference_missing":
        talk.update(
            slide_source="video_extracted", video_url=None, youtube_id=None,
            transcript_source="none",
        )
    elif fault_code == "slide_video_artifact_missing":
        talk["slide_source"] = "video_extracted"
    write_database(vault_fixture, [talk])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert fault_code in finding_codes(report, severity)
    assert fault_code in preflight_vault.SLIDE_CONTRACT_CODES


def test_pending_artifact_gaps_are_warnings_not_blockers(
    preflight_vault, vault_fixture,
):
    talk = base_talk(status="pending", slide_source="video_extracted")
    write_database(vault_fixture, [talk])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert report["blocking_count"] == 0
    assert report["ok"] is True
    assert {
        "transcript_artifact_missing",
        "slide_video_artifact_missing",
    } <= finding_codes(report, "warning")


def test_recoverable_legacy_processed_artifact_gaps_are_warnings(
    preflight_vault, vault_fixture,
):
    talk = base_talk(slide_source="pdf", google_drive_id=DRIVE_ID)
    write_database(vault_fixture, [talk])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert {
        "transcript_artifact_missing",
        "slide_pdf_artifact_missing",
    } <= finding_codes(report, "warning")
    assert report["ok"] is True


def test_legacy_missing_remote_pdf_is_a_reacquisition_warning(
    preflight_vault,
    vault_fixture,
):
    talk = base_talk(
        video_url=None,
        youtube_id=None,
        transcript_source="none",
        slide_source="pdf",
        slides_url=f"https://drive.google.com/file/d/{DRIVE_ID}/view",
        google_drive_id=DRIVE_ID,
    )
    write_database(vault_fixture, [talk])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert report["ok"] is True
    finding = next(
        item for item in report["findings"]
        if item["code"] == "slide_pdf_artifact_missing"
    )
    assert finding["severity"] == "warning"
    assert finding["capability_fact"]["acquisition_capabilities"] == ["slides"]


def test_transcript_only_partial_record_can_repair_a_missing_slide_lane(
    preflight_vault,
    vault_fixture,
):
    transcript = vault_fixture["transcripts"] / "manual.txt"
    text = " ".join(["substantive transcript evidence"] * 600)
    transcript.write_text(text, encoding="utf-8")
    transcript_timing = importlib.import_module("transcript_timing")
    transcript_timing.write_quality_receipt(
        transcript,
        text,
        transcript_timing.build_quality_policy(400),
        {"kind": "fixed_default"},
    )
    talk = base_talk(
        status="processed_partial",
        video_url=None,
        youtube_id=None,
        transcript_source="manual",
        transcript_path="transcripts/manual.txt",
        slide_source="pdf",
        google_drive_id=None,
    )
    write_database(vault_fixture, [talk])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert report["ok"] is True
    finding = next(
        item for item in report["findings"]
        if item["code"] == "slide_pdf_reference_missing"
    )
    assert finding["severity"] == "warning"
    assert finding["capability_fact"]["verified_capabilities"] == ["transcript"]


@pytest.mark.parametrize(
    "field", ["slides_local_path", "slides_pdf_path", "pdf_path"]
)
@pytest.mark.parametrize("slide_source", ["pdf", "video_extracted"])
def test_explicit_local_pdf_path_satisfies_legacy_artifact_contract(
    preflight_vault, vault_fixture, field, slide_source,
):
    materialize_transcript(vault_fixture)
    artifact = vault_fixture["slides"] / "descriptive-legacy-name.pdf"
    artifact.write_bytes(b"%PDF fixture")
    talk = base_talk(
        status=("needs-reprocessing" if slide_source == "video_extracted" else "processed"),
        slide_source=slide_source,
        google_drive_id=None,
        **{field: "slides/descriptive-legacy-name.pdf"},
    )
    write_database(vault_fixture, [talk])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert report["blocking_count"] == 0
    if slide_source == "video_extracted":
        assert finding_codes(report, "warning") == {
            "video_extraction_provenance_missing"
        }
    else:
        assert not finding_codes(report)


@pytest.mark.parametrize(
    ("slide_source", "expected_code"), [
        ("pdf", "slide_pdf_artifact_missing"),
        ("video_extracted", "slide_video_artifact_missing"),
    ]
)
def test_missing_explicit_local_pdf_does_not_fall_back_to_another_identity(
    preflight_vault, vault_fixture, slide_source, expected_code,
):
    materialize_transcript(vault_fixture)
    (vault_fixture["slides"] / f"{VIDEO_ID}.pdf").write_bytes(b"%PDF fixture")
    (vault_fixture["slides"] / f"{DRIVE_ID}.pdf").write_bytes(b"%PDF fixture")
    talk = base_talk(
        slide_source=slide_source,
        google_drive_id=DRIVE_ID,
        slides_local_path="slides/missing-explicit.pdf",
    )
    write_database(vault_fixture, [talk])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert expected_code in finding_codes(report, "warning")


def test_video_pdf_page_count_is_never_treated_as_authored_slide_count(
    preflight_vault, vault_fixture,
):
    materialize_transcript(vault_fixture)
    # It only has to exist: the preflight never imports a PDF parser or counts
    # pages, and never compares either count with the authored slide_count.
    (vault_fixture["slides"] / f"{VIDEO_ID}.pdf").write_bytes(
        b"%PDF-1.4 fake fixture /Count 99"
    )
    talk = base_talk(
        slide_source="video_extracted",
        slide_count=3,
        structured_data={
            "video_extraction": trusted_video_manifest(vault_fixture, 99),
        },
    )
    write_database(vault_fixture, [talk])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert report["blocking_count"] == 0
    assert not any("slide_count" in item["code"] for item in report["findings"])


@pytest.mark.parametrize("manifest_factory", [
    trusted_video_manifest,
    context_video_manifest,
])
def test_processed_partial_video_manifest_needs_no_promoted_deck(
    preflight_vault, vault_fixture, manifest_factory,
):
    materialize_transcript(vault_fixture)
    manifest = manifest_factory(vault_fixture)
    write_database(
        vault_fixture,
        [base_talk(
            status="processed_partial",
            slide_source="video_extracted",
            structured_data={"video_extraction": manifest},
        )],
    )

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert report["blocking_count"] == 0
    assert not finding_codes(report)


def test_context_video_manifest_cannot_back_a_promoted_deck(
    preflight_vault, vault_fixture,
):
    materialize_transcript(vault_fixture)
    promoted = vault_fixture["slides"] / f"{VIDEO_ID}.pdf"
    promoted.write_bytes(b"%PDF context copied into slides by mistake")
    manifest = context_video_manifest(vault_fixture)
    write_database(
        vault_fixture,
        [base_talk(
            status="processed_partial",
            slide_source="video_extracted",
            slides_local_path=f"slides/{VIDEO_ID}.pdf",
            structured_data={"video_extraction": manifest},
        )],
    )

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert "video_extraction_untrusted" in finding_codes(report, "blocking")


def test_completed_legacy_video_pdf_without_provenance_is_repairable(
    preflight_vault, vault_fixture,
):
    materialize_transcript(vault_fixture)
    (vault_fixture["slides"] / f"{VIDEO_ID}.pdf").write_bytes(b"%PDF fixture")
    write_database(
        vault_fixture,
        [base_talk(slide_source="video_extracted")],
    )

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert "video_extraction_provenance_missing" in finding_codes(
        report, "warning"
    )


def test_requeued_legacy_video_pdf_without_provenance_is_a_warning(
    preflight_vault, vault_fixture,
):
    materialize_transcript(vault_fixture)
    (vault_fixture["slides"] / f"{VIDEO_ID}.pdf").write_bytes(b"%PDF fixture")
    write_database(
        vault_fixture,
        [base_talk(status="needs-reprocessing", slide_source="video_extracted")],
    )

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert report["blocking_count"] == 0
    assert "video_extraction_provenance_missing" in finding_codes(
        report, "warning"
    )


def test_unverified_video_crop_cannot_support_completed_deck_analysis(
    preflight_vault, vault_fixture,
):
    materialize_transcript(vault_fixture)
    (vault_fixture["slides"] / f"{VIDEO_ID}.pdf").write_bytes(b"%PDF fixture")
    manifest = trusted_video_manifest(vault_fixture)
    rebuild = vault_fixture["root"] / "slides-rebuild" / VIDEO_ID
    context = rebuild / f"{VIDEO_ID}.context.pdf"
    context.write_bytes(b"%PDF context fixture")
    manifest.update({
        "slide_region_detected": True,
        "slide_region_method": "auto",
        "slide_region_verified": False,
        "review_required": True,
        "review_reason": "auto crop needs review",
    })
    manifest["artifacts"][0].update({
        "crop_method": "auto",
        "crop_verified": False,
        "trusted_for_authored_slide_analysis": False,
    })
    manifest["artifacts"].append({
        "path": str(context),
        "artifact_scope": "full_frame_context",
        "page_count": manifest["unique_frame_count"],
        "source_video_id": VIDEO_ID,
        "source_video_path": manifest["source_video_path"],
        "crop_method": "none",
        "crop_verified": False,
        "trusted_for_authored_slide_analysis": False,
    })
    write_database(
        vault_fixture,
        [base_talk(
            slide_source="video_extracted",
            structured_data={"video_extraction": manifest},
        )],
    )

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert "video_extraction_untrusted" in finding_codes(report, "blocking")


def test_absent_legacy_identity_metadata_is_not_a_finding(
    preflight_vault, vault_fixture,
):
    materialize_transcript(vault_fixture)
    write_database(vault_fixture, [base_talk()])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert report["findings"] == []


def test_partial_identity_metadata_gaps_are_warnings(
    preflight_vault, vault_fixture,
):
    materialize_transcript(vault_fixture)
    write_database(
        vault_fixture,
        [base_talk(source_identity={"schema_version": 1, "provider": "youtube"})],
    )

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert report["blocking_count"] == 0
    assert {
        "source_identity_video_id_missing",
        "source_identity_title_missing",
        "source_identity_speakers_missing",
        "source_identity_date_missing",
        "source_identity_duration_seconds_missing",
    } <= finding_codes(report, "warning")


@pytest.mark.parametrize(("field", "value", "code"), [
    ("transcript_source", "captions_maybe", "transcript_source_unsupported"),
    ("transcript_source", ["youtube_auto"], "transcript_source_unsupported"),
    ("slide_source", "transcript_only", "slide_source_unsupported"),
    ("slide_source", ["pdf"], "slide_source_unsupported"),
])
def test_source_enums_are_closed(
    preflight_vault, vault_fixture, field, value, code,
):
    materialize_transcript(vault_fixture)
    write_database(vault_fixture, [base_talk(**{field: value})])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert code in finding_codes(report, "blocking")


@pytest.mark.parametrize("status", ["skipped_no_sources", "skipped_no_video"])
def test_source_less_skip_status_cannot_hide_pdf_source(
    preflight_vault, vault_fixture, status,
):
    talk = base_talk(
        status=status,
        video_url=None,
        youtube_id=None,
        transcript_source="none",
        slide_source="pdf",
        slides_url=f"https://drive.google.com/file/d/{DRIVE_ID}/view",
        google_drive_id=DRIVE_ID,
    )
    write_database(vault_fixture, [talk])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    finding = next(
        item for item in report["findings"]
        if item["code"] == "status_source_reachability_conflict"
    )
    assert finding["severity"] == "blocking"
    assert finding["actual"] == {
        "status": status,
        "independent_sources": ["pdf"],
    }


def test_source_less_skip_status_cannot_hide_pptx_source(
    preflight_vault, vault_fixture,
):
    talk = base_talk(
        status="skipped_no_video",
        video_url=None,
        youtube_id=None,
        transcript_source="none",
        slide_source="pptx",
        pptx_path="Conference/Talk.pptx",
    )
    write_database(vault_fixture, [talk])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert "status_source_reachability_conflict" in finding_codes(
        report, "blocking"
    )


def test_video_extraction_without_independent_slides_is_not_reachable(
    preflight_vault, vault_fixture,
):
    talk = base_talk(
        status="skipped_no_sources",
        video_url=None,
        youtube_id=None,
        transcript_source="none",
        slide_source="video_extracted",
    )
    write_database(vault_fixture, [talk])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert "status_source_reachability_conflict" not in finding_codes(report)


def test_filenames_must_be_nonempty_and_unique(preflight_vault, vault_fixture):
    talks = [
        {"filename": " ", "status": "skipped_no_sources"},
        {"filename": "same.md", "status": "skipped_no_sources"},
        {"filename": "same.md", "status": "skipped_no_sources"},
    ]
    write_database(vault_fixture, talks)

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert {"filename_missing", "duplicate_filename"} <= finding_codes(
        report, "blocking"
    )


def test_source_indexes_survive_a_malformed_talk(preflight_vault, vault_fixture):
    talks = [
        None,
        {"filename": "same.md", "status": "skipped_no_sources"},
        {"filename": "same.md", "status": "skipped_no_sources"},
    ]
    write_database(vault_fixture, talks)

    report = preflight_vault.run_preflight(vault_fixture["root"])

    duplicate = next(
        item for item in report["findings"] if item["code"] == "duplicate_filename"
    )
    assert duplicate["actual"] == [1, 2]


def test_unhashable_relation_type_is_reported_not_raised(
    preflight_vault, vault_fixture,
):
    materialize_transcript(vault_fixture)
    talk = base_talk(source_relation={
        "type": ["duplicate"],
        "target_filename": "other.md",
    })
    write_database(vault_fixture, [talk])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert "source_relation_invalid" in finding_codes(report, "blocking")


def test_identity_date_and_duration_types_are_validated(
    preflight_vault, vault_fixture,
):
    materialize_transcript(vault_fixture)
    evidence = source_identity(
        recorded_date=20260730,
        upload_date=None,
        duration_seconds=float("inf"),
    )
    write_database(vault_fixture, [base_talk(source_identity=evidence)])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert finding_codes(report, "blocking") == {"database_json_invalid"}
    assert "non-standard JSON number Infinity" in report["findings"][0]["message"]
    # The report remains strict JSON even when Python's input decoder accepted
    # a non-standard Infinity token from a legacy artifact.
    json.dumps(report, allow_nan=False)


def test_identity_date_requires_hyphenated_iso_form(
    preflight_vault, vault_fixture,
):
    materialize_transcript(vault_fixture)
    evidence = source_identity(recorded_date="20260730", upload_date=None)
    write_database(vault_fixture, [base_talk(source_identity=evidence)])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert "source_identity_date_invalid" in finding_codes(report, "blocking")


@pytest.mark.parametrize(("field", "value", "code"), [
    ("uploader", [], "source_identity_provider_fact_invalid"),
    ("uploader_id", " ", "source_identity_provider_fact_invalid"),
    ("webpage_url", "https://videos.example.com/watch?v=AbCdEfGhI_1",
     "source_identity_webpage_url_invalid"),
    ("webpage_url", f"https://www.youtube.com/watch?v={OTHER_VIDEO_ID}",
     "source_identity_webpage_identity_mismatch"),
    ("webpage_video_id", "too-short", "source_identity_webpage_video_id_invalid"),
    ("webpage_video_id", OTHER_VIDEO_ID,
     "source_identity_webpage_identity_mismatch"),
    ("captured_at", "2026-07-31T12:00:00",
     "source_identity_captured_at_invalid"),
])
def test_identity_provider_facts_are_validated_when_present(
    preflight_vault,
    vault_fixture,
    field,
    value,
    code,
):
    materialize_transcript(vault_fixture)
    evidence = source_identity(**{field: value})
    write_database(vault_fixture, [base_talk(
        duration_seconds=2700,
        source_identity=evidence,
    )])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    finding = next(item for item in report["findings"] if item["code"] == code)
    assert finding["severity"] == "blocking"
    assert finding["field"] == f"source_identity.{field}"


def test_live_audit_provider_proposal_satisfies_preflight_contract(
    preflight_vault,
    audit_source_identities,
    vault_fixture,
):
    materialize_transcript(vault_fixture)
    metadata = {
        "id": VIDEO_ID,
        "title": "Perfect Vault Ingress",
        "uploader": "Conference Channel",
        "uploader_id": "@conference",
        "upload_date": "20260731",
        "duration": 2700,
        "webpage_url": f"https://www.youtube.com/watch?v={VIDEO_ID}",
    }
    evidence, faults = audit_source_identities.provider_evidence(
        VIDEO_ID,
        metadata,
        "2026-07-31T12:00:00Z",
    )
    proposal = audit_source_identities.proposed_source_identity(evidence)
    assert faults == []

    talk = base_talk(duration_seconds=2700, source_identity=proposal)
    write_database(vault_fixture, [talk])
    clean = preflight_vault.run_preflight(vault_fixture["root"])

    assert clean["blocking_count"] == 0
    assert finding_codes(clean, "warning") == {"source_identity_speakers_missing"}

    corrupt = deepcopy(proposal)
    corrupt["webpage_video_id"] = OTHER_VIDEO_ID
    write_database(vault_fixture, [base_talk(
        duration_seconds=2700,
        source_identity=corrupt,
    )])
    rejected = preflight_vault.run_preflight(vault_fixture["root"])

    assert "source_identity_webpage_identity_mismatch" in finding_codes(
        rejected,
        "blocking",
    )


def test_boolean_identity_schema_version_is_not_version_one(
    preflight_vault, vault_fixture,
):
    materialize_transcript(vault_fixture)
    evidence = source_identity(schema_version=True)
    write_database(vault_fixture, [base_talk(source_identity=evidence)])

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert "source_identity_schema_unsupported" in finding_codes(report, "warning")


def test_report_is_deterministic_and_preflight_is_read_only(
    preflight_vault, vault_fixture,
):
    materialize_transcript(vault_fixture)
    database = write_database(vault_fixture, [base_talk()])
    before = database.read_bytes()

    first = preflight_vault.run_preflight(database)
    second = preflight_vault.run_preflight(vault_fixture["root"])

    assert first == second
    assert database.read_bytes() == before


def test_cli_emits_json_and_only_blocks_on_integrity_errors(
    preflight_vault, vault_fixture,
):
    pending = base_talk(status="pending", slide_source="video_extracted")
    write_database(vault_fixture, [pending])
    warning_run = subprocess.run(
        [sys.executable, preflight_vault.__file__, str(vault_fixture["root"])],
        capture_output=True,
        text=True,
        check=False,
    )
    warning_report = json.loads(warning_run.stdout)
    assert warning_run.returncode == 0
    assert warning_report["warning_count"] > 0
    assert warning_report["blocking_count"] == 0

    write_database(vault_fixture, [base_talk(youtube_id=OTHER_VIDEO_ID)])
    blocking_run = subprocess.run(
        [sys.executable, preflight_vault.__file__, str(vault_fixture["database"])],
        capture_output=True,
        text=True,
        check=False,
    )
    blocking_report = json.loads(blocking_run.stdout)
    assert blocking_run.returncode == 1
    assert blocking_report["blocking_count"] > 0


def test_unreadable_database_is_a_structured_blocking_report(
    preflight_vault, vault_fixture,
):
    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert report["blocking_count"] == 1
    assert report["findings"][0]["code"] == "database_unreadable"


def test_malformed_json_is_a_structured_blocking_report(
    preflight_vault, vault_fixture,
):
    vault_fixture["database"].write_text('{"talks": [}', encoding="utf-8")

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert report["blocking_count"] == 1
    assert report["findings"][0]["code"] == "database_json_invalid"


def test_non_utf8_database_is_a_structured_blocking_report(
    preflight_vault, vault_fixture,
):
    vault_fixture["database"].write_bytes(b"\xff\xfe\x00")

    report = preflight_vault.run_preflight(vault_fixture["root"])

    assert report["blocking_count"] == 1
    assert report["findings"][0]["code"] == "database_encoding_invalid"
