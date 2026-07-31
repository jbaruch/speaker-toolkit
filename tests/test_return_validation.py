"""Contract tests for the shared vault-ingress return validator."""

import copy
import json
import os
import subprocess
import sys

import pytest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VALIDATE_SCRIPT = os.path.join(
    REPO_ROOT, "skills", "vault-ingress", "scripts", "validate-returns.py")


def _return(**overrides):
    value = {
        "filename": "talk.md",
        "queue_claim": {
            "run_id": "reparse",
            "batch_id": "25",
            "reprocess_generation": 1,
        },
        "status": "processed",
        "slide_source": "pptx",
        "transcript_source": "youtube_auto",
        "rhetoric_notes": "Dimensions 1 through 13.",
        "areas_for_improvement": "Tighten the close.",
        "adherence_assessment": "Near the running baseline.",
        "new_patterns": "",
        "summary_updates": "",
        "structured_data": {
            "delivery_language": "en",
            "co_presenter": False,
        },
        "verbatim_examples": {"jokes": []},
        "pattern_observations": {
            "patterns_detected": [{
                "pattern_id": "narrative-arc",
                "confidence": "strong",
                "evidence_source": "transcript",
                "evidence": "The argument moves through four named acts.",
                "dimensions": [2, 5],
            }],
            "antipatterns_detected": [{
                "pattern_id": "shortchanged",
                "confidence": "weak",
                "evidence_source": "transcript",
                "evidence": "The final summary is compressed.",
                "dimensions": [12, 14],
            }],
            "evidence_sources": ["transcript", "native_deck", "static_slides",
                                 "source_comparison"],
            "not_evaluable": [],
            "pattern_score": {
                "patterns_used": 1,
                "antipatterns_detected": 1,
                "score": 0,
            },
        },
        "catalog_feedback": {
            "unmatched_observations": [],
            "confusable_pairs": [],
            "definition_problems": [],
            "scoring_problems": [],
            "tensions": [],
        },
    }
    value.update(overrides)
    return value


def _canonical_visual_rows():
    """Return a small, wholly synthetic canonical visual ledger."""
    return [
        {
            "slide_number": 1,
            "background_color_name": "purple_halftone",
            "content_type": "title",
            "image_composition": "full_bleed_with_text",
            "has_speech_bubble": False,
            "has_starburst": False,
            "has_footer": True,
        },
        {
            "slide_number": 2,
            "background_color_name": "white_clean",
            "content_type": "meme_with_text",
            "image_composition": "meme_with_caption",
            "has_speech_bubble": True,
            "has_starburst": False,
            "has_footer": False,
        },
    ]


def _return_with_canonical_visuals():
    value = _return()
    value["structured_data"].update({
        "slide_count": 2,
        "meme_count": 1,
        "background_color_sequence": ["purple_halftone", "white_clean"],
        "per_slide_visual": _canonical_visual_rows(),
    })
    return value


def _video_manifest(*, trusted=True, source_video_id="abcDEF12345"):
    root = f"/vault/slides-rebuild/{source_video_id}"
    source_path = f"{root}/{source_video_id}.mp4"
    shared = {
        "page_count": 2,
        "source_video_id": source_video_id,
        "source_video_path": source_path,
    }
    if trusted:
        region = [0.05, 0.02, 0.78, 0.98]
        method = "manual"
        verified = True
        artifacts = [{
            "path": f"{root}/{source_video_id}.slide-region.pdf",
            "artifact_scope": "slide_region",
            "crop_method": "manual",
            "crop_verified": True,
            "trusted_for_authored_slide_analysis": True,
            **shared,
        }]
        review_required = False
        review_reason = None
    else:
        region = None
        method = "none"
        verified = False
        artifacts = [{
            "path": f"{root}/{source_video_id}.context.pdf",
            "artifact_scope": "full_frame_context",
            "crop_method": "none",
            "crop_verified": False,
            "trusted_for_authored_slide_analysis": False,
            **shared,
        }]
        review_required = True
        review_reason = "No verified slide region is available."
    return {
        "slide_source": "video_extracted",
        "schema_version": 3,
        "pipeline_version": "0.10.0",
        "source_video_id": source_video_id,
        "source_video_path": source_path,
        "total_frames_extracted": 4,
        "unique_frame_count": 2,
        "authored_slide_count": None,
        "hash_threshold_used": 8,
        "slide_region_detected": False,
        "slide_region_applied": region is not None,
        "slide_region_method": method,
        "slide_region_verified": verified,
        "slide_region": region,
        "fps_used": 0.5,
        "retained_frames": [
            {"page_number": 1, "frame_index": 0, "timestamp_seconds": 0.0},
            {"page_number": 2, "frame_index": 3, "timestamp_seconds": 6.0},
        ],
        "artifacts": artifacts,
        "review_required": review_required,
        "review_reason": review_reason,
    }


def _video_return(*, trusted=True, promoted=True, **overrides):
    source_video_id = "abcDEF12345"
    value = _return(
        status="processed" if trusted and promoted else "processed_partial",
        slide_source="video_extracted",
        structured_data={
            "delivery_language": "en",
            "co_presenter": False,
            "video_extraction": _video_manifest(
                trusted=trusted, source_video_id=source_video_id),
        },
        clear_fields=[] if trusted and promoted else ["slides_local_path"],
    )
    value["pattern_observations"]["evidence_sources"] = [
        "transcript", "delivery_video",
    ]
    if trusted and promoted:
        value["slides_local_path"] = f"slides/{source_video_id}.pdf"
        value["pattern_observations"]["evidence_sources"].append("static_slides")
    value.update(overrides)
    return value


def _error(return_validation, value):
    with pytest.raises(return_validation.ReturnValidationError) as excinfo:
        return_validation.validate_batch([value])
    return str(excinfo.value)


def _complete_unavailable_source_gates(return_validation, value):
    """Record every catalog gate the fixture's inspected sources cannot score."""
    available = set(value["pattern_observations"]["evidence_sources"])
    catalog = return_validation.load_catalog()
    value["pattern_observations"]["not_evaluable"] = [{
        "pattern_id": pattern_id,
        "evidence_source": sorted(available)[0],
        "reason": "The inspected fixture sources cannot evaluate this pattern.",
    } for pattern_id, entry in sorted(catalog.entries.items())
        if entry.observable and entry.evaluable_from is not None and
        not return_validation.qualifying_evidence_groups(
            entry.evaluable_from, available)]
    return value


def _claimed_talk(ret, **overrides):
    talk = {
        "filename": ret["filename"],
        "status": "reprocessing-inflight",
        "reprocess_generation": ret["queue_claim"]["reprocess_generation"],
        "video_url": "https://youtu.be/AbCdEfGhI_1",
        "youtube_id": "AbCdEfGhI_1",
        "pptx_path": "Conference/Talk.pptx",
        "slides_url": "https://drive.google.com/file/d/slides-id/view",
        "_queue_claim": {
            "schema_version": 1,
            **ret["queue_claim"],
            "claimed_at": "2026-07-31T18:00:00+00:00",
            "previous_status": "needs-reprocessing",
            "state": "claimed",
        },
    }
    talk.update(overrides)
    return talk


def test_valid_return_resolves_the_catalog_fingerprint(return_validation):
    catalog = return_validation.validate_batch([_return()])
    assert len(catalog.entries) == 111
    assert len(catalog.fingerprint) == 64


def test_trusted_video_return_requires_complete_manifest_and_promoted_path(
        return_validation):
    return_validation.validate_batch([
        _complete_unavailable_source_gates(return_validation, _video_return())])

    missing_path = _video_return()
    del missing_path["slides_local_path"]
    assert "requires a trusted schema-v3" in _error(return_validation, missing_path)


def test_video_enum_alone_does_not_make_static_slides_available(return_validation):
    value = _video_return(trusted=False, promoted=False)
    del value["structured_data"]["video_extraction"]
    assert "complete structured_data.video_extraction" in _error(
        return_validation, value)


def test_context_video_cannot_promote_or_cite_static_slides(return_validation):
    promoted = _video_return(trusted=False, promoted=False)
    promoted["slides_local_path"] = "slides/abcDEF12345.pdf"
    assert "cannot promote an untrusted" in _error(return_validation, promoted)

    cited = _video_return(trusted=False, promoted=False)
    cited["pattern_observations"]["evidence_sources"].append("static_slides")
    assert "no trusted schema-v3 slide_region" in _error(return_validation, cited)


def test_trusted_unpromoted_video_can_support_partial_static_analysis(
        return_validation):
    value = _video_return(trusted=True, promoted=False)
    value["pattern_observations"]["evidence_sources"].append("static_slides")
    value["structured_data"]["slide_design_style"] = "comic_book"
    _complete_unavailable_source_gates(return_validation, value)
    return_validation.validate_batch([value])


def test_context_video_rejects_authored_slide_structured_evidence(return_validation):
    value = _video_return(trusted=False, promoted=False)
    value["structured_data"]["slide_design_style"] = "comic_book"
    assert "cannot return authored-slide evidence" in _error(return_validation, value)


def test_context_video_rejects_image_source_distribution_basis(return_validation):
    value = _video_return(trusted=False, promoted=False)
    value["structured_data"]["image_source_distribution_basis"] = (
        "Unit: slide; classify the dominant source per slide from asset manifests; "
        "unverified origins count as unknown.")
    assert "cannot return authored-slide evidence" in _error(return_validation, value)


def test_context_video_must_clear_a_stale_promoted_path(return_validation):
    value = _video_return(trusted=False, promoted=False)
    value["clear_fields"] = []
    assert "must clear slides_local_path" in _error(return_validation, value)


def test_context_delivery_video_still_requires_comparison_gates_not_evaluable(
        return_validation):
    value = _complete_unavailable_source_gates(
        return_validation,
        _video_return(trusted=False, promoted=False),
    )
    not_evaluable = {
        item["pattern_id"]: item
        for item in value["pattern_observations"]["not_evaluable"]
    }

    assert not_evaluable["gradual-consistency"]["evidence_source"] == \
        "delivery_video"
    assert not_evaluable["invisibility"]["evidence_source"] == "delivery_video"
    return_validation.validate_batch([value])

    value["pattern_observations"]["not_evaluable"] = [
        item for pattern_id, item in not_evaluable.items()
        if pattern_id not in {"gradual-consistency", "invisibility"}
    ]
    error = _error(return_validation, value)
    assert "gradual-consistency" in error
    assert "invisibility" in error


def test_slides_only_return_requires_verbal_layer_patterns_not_evaluable(
        return_validation):
    value = _return(
        status="processed_partial",
        slide_source="pdf",
        transcript_source="none",
    )
    observations = value["pattern_observations"]
    observations["evidence_sources"] = ["static_slides"]
    for detection in (
            observations["patterns_detected"] +
            observations["antipatterns_detected"]):
        detection["evidence_source"] = "static_slides"
    _complete_unavailable_source_gates(return_validation, value)
    not_evaluable = {
        item["pattern_id"]: item
        for item in observations["not_evaluable"]
    }

    assert not_evaluable["second-look"]["evidence_source"] == "static_slides"
    assert not_evaluable["vacation-photos"]["evidence_source"] == \
        "static_slides"
    return_validation.validate_batch([value])

    observations["not_evaluable"] = [
        item for pattern_id, item in not_evaluable.items()
        if pattern_id not in {"second-look", "vacation-photos"}
    ]
    error = _error(return_validation, value)
    assert "second-look" in error
    assert "vacation-photos" in error


def test_transcript_only_return_requires_visual_layer_patterns_not_evaluable(
        return_validation):
    value = _return(
        status="processed_partial",
        slide_source="none",
        transcript_source="manual",
    )
    observations = value["pattern_observations"]
    observations["evidence_sources"] = ["transcript"]
    _complete_unavailable_source_gates(return_validation, value)
    not_evaluable = {
        item["pattern_id"]: item
        for item in observations["not_evaluable"]
    }

    assert not_evaluable["second-look"]["evidence_source"] == "transcript"
    assert not_evaluable["vacation-photos"]["evidence_source"] == "transcript"
    return_validation.validate_batch([value])

    observations["not_evaluable"] = [
        item for pattern_id, item in not_evaluable.items()
        if pattern_id not in {"second-look", "vacation-photos"}
    ]
    error = _error(return_validation, value)
    assert "second-look" in error
    assert "vacation-photos" in error


def test_unavailable_source_gates_must_be_explicitly_not_evaluable(return_validation):
    value = _video_return(trusted=False, promoted=False)
    value["pattern_observations"]["evidence_sources"] = ["transcript"]
    error = _error(return_validation, value)
    assert "must be marked not_evaluable" in error

    catalog = return_validation.load_catalog()
    value["pattern_observations"]["not_evaluable"] = [{
        "pattern_id": pattern_id,
        "evidence_source": "transcript",
        "reason": "Only transcript and untrusted context frames were available.",
    } for pattern_id, entry in sorted(catalog.entries.items())
        if entry.observable and entry.evaluable_from is not None and
        not return_validation.qualifying_evidence_groups(
            entry.evaluable_from, {"transcript"})]
    return_validation.validate_batch([value])


@pytest.mark.parametrize("mutation,expected", [
    (lambda manifest: manifest.update(schema_version=2), "schema_version"),
    (lambda manifest: manifest.update(review_required=False), "review_required"),
    (lambda manifest: manifest["artifacts"][0].update(
        trusted_for_authored_slide_analysis=True), "full_frame_context"),
    (lambda manifest: manifest["artifacts"][0].update(
        source_video_path="/vault/another.mp4"), "must match source_video_path"),
    (lambda manifest: manifest["artifacts"][0].update(page_count=99),
     "must equal unique_frame_count"),
    (lambda manifest: manifest["artifacts"][0].update(page_count=True),
     "must equal unique_frame_count"),
    (lambda manifest: manifest["retained_frames"][1].update(frame_index=4),
     "below total_frames_extracted"),
    (lambda manifest: manifest["retained_frames"][1].update(timestamp_seconds=5.0),
     "must equal frame_index / fps_used"),
])
def test_video_manifest_rejects_spoofed_or_inconsistent_provenance(
        return_validation, mutation, expected):
    value = _video_return(trusted=False, promoted=False)
    mutation(value["structured_data"]["video_extraction"])
    assert expected in _error(return_validation, value)


def test_video_manifest_accepts_extractor_timestamp_rounding(return_validation):
    value = _video_return()
    manifest = value["structured_data"]["video_extraction"]
    manifest["fps_used"] = 0.3
    manifest["retained_frames"][1].update({
        "frame_index": 1,
        "timestamp_seconds": 3.333,
    })
    _complete_unavailable_source_gates(return_validation, value)
    return_validation.validate_batch([value])


def test_video_manifest_identity_is_bound_to_the_claimed_talk(return_validation):
    value = _video_return()
    talk = _claimed_talk(value,
        video_url="https://youtu.be/otherID1234",
        youtube_id="otherID1234",
    )
    with pytest.raises(return_validation.ReturnValidationError) as excinfo:
        return_validation.validate_claim_against_talk(talk, value)
    assert "does not match talk youtube_id" in str(excinfo.value)


def test_claim_generation_must_equal_talk_generation(return_validation):
    value = _return()
    talk = _claimed_talk(value, reprocess_generation=2)

    with pytest.raises(return_validation.ReturnValidationError) as excinfo:
        return_validation.validate_claim_against_talk(talk, value)

    assert "disagrees with talk generation 2" in str(excinfo.value)


def test_complete_claim_batch_rejects_partial_and_superset_membership(
        return_validation):
    returns = [_return(filename=f"{name}.md") for name in ("a", "b", "c")]
    talks = [_claimed_talk(ret) for ret in returns]

    with pytest.raises(return_validation.ReturnValidationError) as excinfo:
        return_validation.validate_batch_claims_against_talks(
            talks, returns[:2], required_state="claimed")
    assert "must exactly match" in str(excinfo.value)
    assert "missing ['c.md']" in str(excinfo.value)

    with pytest.raises(return_validation.ReturnValidationError) as excinfo:
        return_validation.validate_batch_claims_against_talks(
            talks[:2], returns, required_state="claimed")
    assert "unexpected ['c.md']" in str(excinfo.value)


def test_complete_claim_batch_rejects_mixed_run_or_batch_identity(
        return_validation):
    first = _return(filename="a.md")
    second = _return(filename="b.md")
    second["queue_claim"] = {
        **second["queue_claim"], "batch_id": "26"}

    with pytest.raises(return_validation.ReturnValidationError) as excinfo:
        return_validation.validate_batch_claims_against_talks(
            [_claimed_talk(first), _claimed_talk(second)],
            [first, second],
            required_state="claimed",
        )
    assert "one queue run_id/batch_id identity" in str(excinfo.value)


def test_complete_claim_batch_rejects_closed_or_stranded_member(
        return_validation):
    returns = [_return(filename=f"{name}.md") for name in ("a", "b")]
    talks = [_claimed_talk(ret) for ret in returns]
    closed = talks[0]
    closed["status"] = "processed"
    closed["_queue_claim"].update({
        "state": "completed",
        "released_at": "2026-07-31T18:05:00+00:00",
        "release_reason": "return_persisted",
        "result_status": "processed",
    })

    with pytest.raises(return_validation.ReturnValidationError) as excinfo:
        return_validation.validate_batch_claims_against_talks(
            talks, returns, required_state="claimed")
    assert "closed or stranded member" in str(excinfo.value)
    assert "a.md" in str(excinfo.value)

    # A member can also be stranded while the claim still says `claimed`.
    closed["_queue_claim"] = _claimed_talk(returns[0])["_queue_claim"]
    with pytest.raises(return_validation.ReturnValidationError) as excinfo:
        return_validation.validate_batch_claims_against_talks(
            talks, returns, required_state="claimed")
    assert "expected 'reprocessing-inflight'" in str(excinfo.value)


def test_current_claim_requires_exact_state_schema(return_validation):
    value = _return()
    talk = _claimed_talk(value)
    talk["_queue_claim"]["released_at"] = None

    with pytest.raises(return_validation.ReturnValidationError) as excinfo:
        return_validation.validate_claim_against_talk(talk, value)

    assert "must use exactly the schema fields" in str(excinfo.value)
    assert "released_at" in str(excinfo.value)


def test_return_claim_requires_exact_identity_schema(return_validation):
    value = _return()
    value["queue_claim"]["state"] = "claimed"

    assert "must use exactly the schema fields" in _error(return_validation, value)


def test_wrong_transcript_return_cannot_resurrect_repaired_source(
        return_validation):
    value = _return(status="processed_partial", slide_source="pdf")
    value["pattern_observations"]["evidence_sources"] = [
        "transcript", "static_slides"]
    _complete_unavailable_source_gates(return_validation, value)
    return_validation.validate_batch([value])
    talk = _claimed_talk(
        value,
        video_url=None,
        youtube_id=None,
        pptx_path=None,
        google_drive_id="slides-id",
        transcript_source="none",
        slide_source="pdf",
    )

    with pytest.raises(return_validation.ReturnValidationError) as excinfo:
        return_validation.validate_claim_against_talk(talk, value)

    assert "no transcript reference or active video source" in str(excinfo.value)


def test_corrected_pdf_only_return_is_backed_by_claimed_talk(
        return_validation):
    value = _return(
        status="processed_partial",
        slide_source="pdf",
        transcript_source="none",
    )
    observations = value["pattern_observations"]
    observations["evidence_sources"] = ["static_slides"]
    for detection in (
            observations["patterns_detected"] +
            observations["antipatterns_detected"]):
        detection["evidence_source"] = "static_slides"
    _complete_unavailable_source_gates(return_validation, value)
    return_validation.validate_batch([value])
    talk = _claimed_talk(
        value,
        video_url=None,
        youtube_id=None,
        pptx_path=None,
        google_drive_id="slides-id",
        transcript_source="none",
        slide_source="pdf",
    )

    return_validation.validate_claim_against_talk(talk, value)


def test_active_video_allows_newly_fetched_transcript(return_validation):
    value = _return()
    talk = _claimed_talk(value)
    return_validation.validate_claim_against_talk(talk, value)


@pytest.mark.parametrize(("slide_source", "expected"), [
    ("pptx", "no pptx_path"),
    ("pdf", "no independent PDF source"),
])
def test_return_slide_source_must_be_backed_by_claimed_talk(
        return_validation, slide_source, expected):
    value = _return(slide_source=slide_source)
    talk = _claimed_talk(value)
    talk.pop("pptx_path")
    talk.pop("slides_url")

    with pytest.raises(return_validation.ReturnValidationError) as excinfo:
        return_validation.validate_claim_against_talk(talk, value)

    assert expected in str(excinfo.value)


@pytest.mark.parametrize("status", [None, "reprocessing-inflight", "skipped_no_video"])
def test_status_must_be_a_terminal_return_state(return_validation, status):
    value = _return()
    if status is None:
        del value["status"]
    else:
        value["status"] = status
    assert "status is required" in _error(return_validation, value)


@pytest.mark.parametrize("claim", [
    None,
    {"run_id": "reparse", "batch_id": "25", "reprocess_generation": 0},
    {"run_id": "bad run", "batch_id": "25", "reprocess_generation": 1},
])
def test_return_must_carry_a_valid_queue_generation(return_validation, claim):
    value = _return()
    if claim is None:
        del value["queue_claim"]
    else:
        value["queue_claim"] = claim
    assert "queue_claim" in _error(return_validation, value)


def test_skipped_return_accepts_only_terminal_claim_metadata(return_validation):
    value = {
        "filename": "talk.md",
        "queue_claim": {
            "run_id": "reparse",
            "batch_id": "25",
            "reprocess_generation": 1,
        },
        "status": "skipped_no_sources",
    }
    return_validation.validate_batch([value])

    value["rhetoric_notes"] = "must not replace the prior analysis"
    assert "cannot mutate or clear prior analysis fields" in _error(
        return_validation, value)


@pytest.mark.parametrize(("field", "value"), [
    ("processed_date", "2026-07-31T18:05:00+00:00"),
    ("transcript_source", "none"),
    ("slide_source", "none"),
    ("clear_fields", []),
])
def test_skipped_return_rejects_analysis_metadata(
        return_validation, field, value):
    value = {
        "filename": "talk.md",
        "queue_claim": {
            "run_id": "reparse",
            "batch_id": "25",
            "reprocess_generation": 1,
        },
        "status": "skipped_no_sources",
        field: value,
    }

    assert "cannot mutate or clear prior analysis fields" in _error(
        return_validation, value)


def test_unknown_pattern_id_is_rejected(return_validation):
    value = _return()
    value["pattern_observations"]["patterns_detected"][0]["pattern_id"] = \
        "terminal-as-deck-until-it-exists"
    assert "is not in the Presentation Patterns catalog" in _error(return_validation, value)


def test_pattern_in_antipattern_lane_is_rejected(return_validation):
    value = _return()
    value["pattern_observations"]["antipatterns_detected"][0]["pattern_id"] = \
        "narrative-arc"
    assert "catalog pattern" in _error(return_validation, value)


def test_unobservable_pattern_is_rejected(return_validation):
    value = _return()
    value["pattern_observations"]["patterns_detected"][0]["pattern_id"] = \
        "red-yellow-green"
    assert "observable:false" in _error(return_validation, value)


def test_source_gated_pattern_rejects_nonqualifying_evidence(return_validation):
    value = _return()
    value["pattern_observations"]["patterns_detected"][0]["pattern_id"] = \
        "composite-animation"
    assert "cannot be evaluated from 'transcript'" in _error(return_validation, value)


def test_detection_source_must_have_been_inspected(return_validation):
    value = _return()
    value["pattern_observations"]["patterns_detected"][0]["evidence_source"] = \
        "delivery_video"
    assert "is not listed in pattern_observations.evidence_sources" in _error(
        return_validation, value)


def test_native_deck_source_requires_pptx_artifact(return_validation):
    value = _return(slide_source="pdf")
    assert "native_deck but slide_source is 'pdf'" in _error(return_validation, value)


def test_source_comparison_marker_does_not_count_as_underlying_source(
        return_validation):
    value = _return()
    value["pattern_observations"]["evidence_sources"] = [
        "static_slides", "source_comparison"]
    assert "requires at least two underlying sources" in _error(
        return_validation, value)


def test_source_comparison_requires_a_visual_underlying_source(
        return_validation, monkeypatch):
    monkeypatch.setattr(
        return_validation,
        "EVIDENCE_SOURCES",
        return_validation.EVIDENCE_SOURCES | {"speaker_notes"},
    )
    observations = {
        "evidence_sources": [
            "transcript", "speaker_notes", "source_comparison"],
    }

    with pytest.raises(return_validation.ReturnValidationError) as excinfo:
        return_validation._validate_available_sources(
            observations,
            "pptx",
            "manual",
        )

    assert "including at least one visual source" in str(excinfo.value)


@pytest.mark.parametrize("pattern_id", ["second-look", "vacation-photos"])
@pytest.mark.parametrize(
    ("slide_source", "transcript_source", "sources", "detection_source"),
    [
        ("pdf", "none", ["delivery_video"], "delivery_video"),
        (
            "pdf",
            "manual",
            ["static_slides", "transcript", "source_comparison"],
            "source_comparison",
        ),
        (
            "pptx",
            "manual",
            ["native_deck", "transcript", "source_comparison"],
            "source_comparison",
        ),
    ],
)
def test_verbal_layer_gates_accept_singleton_or_conjunctive_evidence(
    return_validation,
    pattern_id,
    slide_source,
    transcript_source,
    sources,
    detection_source,
):
    value = _return(
        slide_source=slide_source,
        transcript_source=transcript_source,
    )
    observations = value["pattern_observations"]
    observations["evidence_sources"] = sources
    observations["patterns_detected"][0].update({
        "pattern_id": pattern_id,
        "evidence_source": detection_source,
    })
    observations["antipatterns_detected"][0]["evidence_source"] = \
        detection_source
    _complete_unavailable_source_gates(return_validation, value)

    return_validation.validate_batch([value])


def test_conjunctive_gate_requires_source_comparison_marker(return_validation):
    value = _return(slide_source="pdf", transcript_source="manual")
    observations = value["pattern_observations"]
    observations["evidence_sources"] = ["static_slides", "transcript"]
    _complete_unavailable_source_gates(return_validation, value)
    not_evaluable_ids = {
        item["pattern_id"] for item in observations["not_evaluable"]}

    assert {"second-look", "vacation-photos"} <= not_evaluable_ids
    return_validation.validate_batch([value])


def test_conjunctive_detection_must_cite_source_comparison(return_validation):
    value = _return(slide_source="pdf", transcript_source="manual")
    observations = value["pattern_observations"]
    observations["evidence_sources"] = [
        "static_slides", "transcript", "source_comparison"]
    observations["patterns_detected"][0]["pattern_id"] = "second-look"
    _complete_unavailable_source_gates(return_validation, value)

    assert "cannot be evaluated from 'transcript'" in _error(
        return_validation, value)


def test_source_gated_pattern_can_be_recorded_as_not_evaluable(return_validation):
    value = _return()
    value["pattern_observations"]["not_evaluable"] = [{
        "pattern_id": "composite-animation",
        "evidence_source": "static_slides",
        "reason": "The static export contains no animation timing.",
    }]
    return_validation.validate_batch([value])


def test_ungated_pattern_cannot_be_recorded_as_not_evaluable(return_validation):
    value = _return()
    value["pattern_observations"]["not_evaluable"] = [{
        "pattern_id": "narrative-arc",
        "evidence_source": "transcript",
        "reason": "No reason can override available transcript evidence.",
    }]
    assert "has no source-aware evidence gate" in _error(return_validation, value)


def test_detected_pattern_cannot_also_be_not_evaluable(return_validation):
    value = _return()
    value["pattern_observations"]["patterns_detected"][0].update({
        "pattern_id": "progressive-reveal",
        "evidence_source": "static_slides",
    })
    value["pattern_observations"]["not_evaluable"] = [{
        "pattern_id": "progressive-reveal",
        "evidence_source": "static_slides",
        "reason": "Contradictory state.",
    }]
    assert "both detected and not_evaluable" in _error(return_validation, value)


def test_duplicate_detection_is_rejected(return_validation):
    value = _return()
    value["pattern_observations"]["patterns_detected"].append(
        copy.deepcopy(value["pattern_observations"]["patterns_detected"][0]))
    assert "duplicate id" in _error(return_validation, value)


@pytest.mark.parametrize("field,bad", [
    ("confidence", "certain"),
    ("evidence", ""),
    ("dimensions", [0, 15]),
])
def test_detection_evidence_contract_is_enforced(return_validation, field, bad):
    value = _return()
    value["pattern_observations"]["patterns_detected"][0][field] = bad
    assert field in _error(return_validation, value)


@pytest.mark.parametrize("field,bad", [
    ("patterns_used", 2),
    ("antipatterns_detected", 0),
    ("score", 1),
])
def test_all_declared_score_counts_are_cross_checked(
        return_validation, field, bad):
    value = _return()
    value["pattern_observations"]["pattern_score"][field] = bad
    assert f"pattern_score.{field}" in _error(return_validation, value)


def test_co_presenter_requires_a_name_array(return_validation):
    value = _return()
    value["structured_data"]["co_presenter"] = True
    assert "co_presenters must name" in _error(return_validation, value)


def test_co_presenters_rejects_a_scalar(return_validation):
    value = _return()
    value["structured_data"].update({"co_presenter": True, "co_presenters": "Alex"})
    assert "array of non-empty names" in _error(return_validation, value)


def test_delivery_language_requires_a_code(return_validation):
    value = _return()
    value["structured_data"]["delivery_language"] = "English"
    assert "lowercase language code" in _error(return_validation, value)


def test_canonical_per_slide_visual_rows_are_accepted(return_validation):
    return_validation.validate_batch([_return_with_canonical_visuals()])


@pytest.mark.parametrize("legacy_row", [
    {
        # Synthetic counterexample for a legacy four-key row shape.
        "slide_number": 1,
        "content_type": "title",
        "background": "purple_halftone",
        "has_text_footer": True,
    },
    {
        # Synthetic counterexample for a legacy alias-based row shape.
        "slide": 1,
        "type": "title",
        "devices": [],
    },
])
def test_legacy_per_slide_visual_shapes_are_rejected(
        return_validation, legacy_row):
    value = _return()
    value["structured_data"].update({
        "slide_count": 1,
        "per_slide_visual": [legacy_row],
    })
    message = _error(return_validation, value)
    assert "must contain exactly the canonical fields" in message
    assert "missing" in message
    assert "unexpected" in message


def test_per_slide_visual_rows_reject_extra_fields(return_validation):
    value = _return_with_canonical_visuals()
    value["structured_data"]["per_slide_visual"][0]["devices"] = ["footer"]
    message = _error(return_validation, value)
    assert "must contain exactly the canonical fields" in message
    assert "unexpected ['devices']" in message


def test_per_slide_visual_rows_require_every_canonical_field(return_validation):
    value = _return_with_canonical_visuals()
    del value["structured_data"]["per_slide_visual"][0]["has_footer"]
    message = _error(return_validation, value)
    assert "must contain exactly the canonical fields" in message
    assert "missing ['has_footer']" in message


@pytest.mark.parametrize("field,bad,expected", [
    ("slide_number", True, "slide_number must be 1"),
    ("background_color_name", "", "must be a non-empty string"),
    ("background_color_name", 7, "must be a non-empty string"),
    ("content_type", "custom_diagram", "content_type must be one of"),
    ("content_type", ["title"], "content_type must be one of"),
    ("image_composition", "unknown_layout", "image_composition must be one of"),
    ("image_composition", None, "image_composition must be one of"),
    ("has_speech_bubble", 0, "has_speech_bubble must be a boolean"),
    ("has_starburst", "false", "has_starburst must be a boolean"),
    ("has_footer", None, "has_footer must be a boolean"),
])
def test_per_slide_visual_field_types_and_vocabularies_are_enforced(
        return_validation, field, bad, expected):
    value = _return_with_canonical_visuals()
    value["structured_data"]["per_slide_visual"][0][field] = bad
    assert expected in _error(return_validation, value)


@pytest.mark.parametrize("slide_numbers", [
    [1, 1],
    [1, 3],
    [2, 1],
])
def test_per_slide_visual_must_cover_slides_once_in_order(
        return_validation, slide_numbers):
    value = _return_with_canonical_visuals()
    for row, slide_number in zip(
            value["structured_data"]["per_slide_visual"], slide_numbers):
        row["slide_number"] = slide_number
    assert "uniquely and contiguously cover" in _error(return_validation, value)


@pytest.mark.parametrize("slide_count", [None, True, 0, "2", 2.0, 1, 3])
def test_per_slide_visual_requires_matching_positive_slide_count(
        return_validation, slide_count):
    value = _return_with_canonical_visuals()
    if slide_count is None:
        del value["structured_data"]["slide_count"]
    else:
        value["structured_data"]["slide_count"] = slide_count
    message = _error(return_validation, value)
    assert ("positive integer" in message or
            "must contain exactly slide_count" in message)


def test_per_slide_visual_requires_an_array_of_objects(return_validation):
    value = _return_with_canonical_visuals()
    value["structured_data"]["per_slide_visual"] = "slides"
    assert "per_slide_visual must be an array" in _error(return_validation, value)

    value = _return_with_canonical_visuals()
    value["structured_data"]["per_slide_visual"][0] = ["slide"]
    assert "per_slide_visual[0] must be an object" in _error(
        return_validation, value)


def test_per_slide_visual_cross_checks_backgrounds_and_meme_count(
        return_validation):
    value = _return_with_canonical_visuals()
    value["structured_data"]["background_color_sequence"][1] = "red_halftone"
    assert "background_color_sequence must exactly match" in _error(
        return_validation, value)

    value = _return_with_canonical_visuals()
    value["structured_data"]["meme_count"] = 0
    assert "per_slide_visual contains 1 meme slides" in _error(
        return_validation, value)


def test_image_source_distribution_accepts_provenance_counts(return_validation):
    value = _return()
    value["structured_data"]["image_source_distribution"] = {
        "ai_generated": 0,
        "speaker_created": 4,
        "unknown": 2,
        "none": 1,
    }
    value["structured_data"]["image_source_distribution_basis"] = (
        "Unit: slide; classify each slide by its dominant image source using "
        "asset manifests; origins without provenance count as unknown.")
    return_validation.validate_batch([value])


def test_image_source_distribution_requires_a_basis(return_validation):
    value = _return()
    value["structured_data"]["image_source_distribution"] = {"unknown": 2}
    assert "image_source_distribution_basis is required" in _error(
        return_validation, value)


@pytest.mark.parametrize("basis", [None, "", "   ", 7, True, ["per slide"]])
def test_image_source_distribution_basis_must_be_a_non_empty_string(
        return_validation, basis):
    value = _return()
    value["structured_data"].update({
        "image_source_distribution": {"unknown": 2},
        "image_source_distribution_basis": basis,
    })
    assert "image_source_distribution_basis must be a non-empty string" in _error(
        return_validation, value)


@pytest.mark.parametrize("distribution", [
    {"ai_generated": 0, "classification_note": "unverified"},
    {"unknown": -1},
    {"unknown": True},
    {"": 1},
    {1: 1},
    ["unknown"],
])
def test_image_source_distribution_rejects_non_count_metadata(
        return_validation, distribution):
    value = _return()
    value["structured_data"].update({
        "image_source_distribution": distribution,
        "image_source_distribution_basis": (
            "Unit: asset; classify each asset from embedded provenance metadata; "
            "unverified origins count as unknown."),
    })
    assert "image_source_distribution" in _error(return_validation, value)


def test_catalog_feedback_requires_every_audit_lane(return_validation):
    value = _return()
    del value["catalog_feedback"]["definition_problems"]
    assert "catalog_feedback.definition_problems is required" in _error(
        return_validation, value)


def test_prose_fields_reject_shape_drift(return_validation):
    value = _return()
    value["summary_updates"] = [{"section": 4, "content": "new"}]
    assert "summary_updates must be a string" in _error(return_validation, value)


def test_duplicate_batch_filename_is_rejected(return_validation):
    assert "duplicate return filename" in _error_batch(
        return_validation, [_return(), _return()])


def _error_batch(return_validation, values):
    with pytest.raises(return_validation.ReturnValidationError) as excinfo:
        return_validation.validate_batch(values)
    return str(excinfo.value)


@pytest.mark.parametrize("path", [
    "status",
    "structured_data",
    "unknown.path",
    "structured_data..slide_count",
])
def test_clear_fields_is_confined_to_analysis_owned_leaves(return_validation, path):
    value = _return(clear_fields=[path])
    assert "clear_fields" in _error(return_validation, value)


def test_validator_cli_emits_structured_report(tmp_path):
    batch = tmp_path / "returns.json"
    batch.write_text(json.dumps([_return()]))
    result = subprocess.run(
        [sys.executable, VALIDATE_SCRIPT, str(batch)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["valid"] is True
    assert report["returns"] == 1
    assert report["catalog_entries"] == 111


def test_validator_cli_reports_the_filename_on_failure(tmp_path):
    batch = tmp_path / "returns.json"
    value = _return()
    del value["status"]
    batch.write_text(json.dumps([value]))
    result = subprocess.run(
        [sys.executable, VALIDATE_SCRIPT, str(batch)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "talk.md" in result.stderr
    assert "status is required" in result.stderr


def test_validator_cli_flattens_a_directory_of_single_returns(tmp_path):
    first = _return(filename="a.md")
    second = _return(filename="b.md")
    (tmp_path / "a.json").write_text(json.dumps(first))
    (tmp_path / "b.json").write_text(json.dumps(second))
    result = subprocess.run(
        [sys.executable, VALIDATE_SCRIPT, str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["returns"] == 2
    assert report["filenames"] == ["a.md", "b.md"]
    assert len(report["input_files"]) == 2


def test_validator_cli_catches_duplicates_across_input_files(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps(_return()))
    (tmp_path / "b.json").write_text(json.dumps([_return()]))
    result = subprocess.run(
        [sys.executable, VALIDATE_SCRIPT, str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "duplicate return filename" in result.stderr


def test_validator_cli_reports_every_invalid_return(tmp_path):
    first = _return(filename="a.md")
    second = _return(filename="b.md")
    del first["status"]
    second["structured_data"]["delivery_language"] = "English"
    (tmp_path / "a.json").write_text(json.dumps(first))
    (tmp_path / "b.json").write_text(json.dumps(second))
    result = subprocess.run(
        [sys.executable, VALIDATE_SCRIPT, str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "a.md" in result.stderr
    assert "b.md" in result.stderr
    assert "2 validation error(s) across 2 return(s)" in result.stderr
