"""Section 15 current-block provenance and creator fallback tests."""

from __future__ import annotations

import copy
import fcntl
import hashlib
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
PROFILE_SCRIPTS = ROOT / "skills" / "vault-profile" / "scripts"
CREATOR_SCRIPTS = ROOT / "skills" / "presentation-creator" / "scripts"
OUTLINE = Path(__file__).parent / "fixtures" / "outline-example.yaml"
for script_directory in (PROFILE_SCRIPTS, CREATOR_SCRIPTS):
    if str(script_directory) not in sys.path:
        sys.path.insert(0, str(script_directory))

section15 = importlib.import_module("section15_pattern_history")
# section15 puts the vault-ingress scripts on sys.path; the summary's writer
# lock lives there, shared with the status-block writer.
cooperative_lock = importlib.import_module("cooperative_lock")
pattern_history_status = importlib.import_module("pattern_history_status")
provenance = importlib.import_module("profile_pattern_provenance")
classification_runtime = importlib.import_module("pattern_classification_runtime")
opportunities = importlib.import_module("pattern_opportunities")
pattern_evidence = importlib.import_module("pattern_evidence")
adherence_baseline = importlib.import_module("adherence_baseline")
transcript_timing = importlib.import_module("transcript_timing")


def _foreign_absolute_vault_root() -> str:
    return "/foreign/vault" if sys.platform == "win32" else r"C:\foreign\vault"


DOT_SEGMENT_VAULT_ROOT = (
    r"C:\trusted\other\..\vault"
    if sys.platform == "win32"
    else "/trusted/other/../vault"
)
INVALID_VAULT_ROOT_LOCATORS = (
    ("", "artifact_locator_empty_or_whitespace"),
    ("   ", "artifact_locator_empty_or_whitespace"),
    ("relative-vault", "artifact_root_not_native_absolute"),
    ("C:vault", "artifact_locator_windows_drive_relative"),
    ("~/vault", "artifact_locator_home_expansion_unsupported"),
    (_foreign_absolute_vault_root(), "artifact_locator_foreign_absolute"),
    (r"\\?\C:\vault", "artifact_locator_windows_device_namespace"),
    (r"\vault", "artifact_locator_windows_current_drive_rooted"),
    (DOT_SEGMENT_VAULT_ROOT, "artifact_locator_dot_segment"),
)


def _fresh_evidence(_talk: object) -> tuple[str, ...]:
    return ()


def _transcript_projection() -> tuple[list[dict], list[dict], list[dict]]:
    catalog = opportunities.load_catalog()
    transcript = frozenset({"transcript"})
    outcomes = []
    not_evaluable = []
    assessments = []
    for pattern_id, entry in sorted(catalog.entries.items()):
        if not entry.observable:
            continue
        if entry.applicability_evaluable_from is not None:
            if transcript not in entry.applicability_evaluable_from:
                outcomes.append({"pattern_id": pattern_id, "outcome": "not_evaluable"})
                not_evaluable.append({"pattern_id": pattern_id})
                continue
            assessments.append({"pattern_id": pattern_id, "result": "applicable"})
        outcome = (
            "undetected"
            if entry.absence_evaluable_from is not None
            and transcript in entry.absence_evaluable_from
            else "not_evaluable"
        )
        outcomes.append({"pattern_id": pattern_id, "outcome": outcome})
        if outcome == "not_evaluable":
            not_evaluable.append({"pattern_id": pattern_id})
    return outcomes, not_evaluable, assessments


def _pattern_profile(*, note: str = "Current exact cohort.") -> dict[str, Any]:
    fingerprint, scoring_schema = provenance.active_pattern_generation_identity()
    assert scoring_schema == 5
    filenames = ["example-a.md", "example-b.md"]
    outcome_talks = _outcome_talks(filenames)
    rows = opportunities.build_pattern_opportunity_rows(outcome_talks)
    opportunity_identity = outcome_talks[0]["pattern_observations"][
        "opportunity_coverage_identity"
    ]
    classification = classification_runtime.classify_pattern_profile(
        outcome_talks,
        classification_runtime.resolve_classification_policy(
            Path(__file__).resolve().parent / "__no_policy_override__"
        ),
    )
    return {
        "pattern_baseline": {
            "schema_version": 2,
            "as_of": "2025-01-02T03:04:05+00:00",
            "scope": "global",
            "active_batch_excluded": False,
            "excluded_filenames": [],
            "eligible_statuses": ["processed", "processed_partial"],
            "pattern_scoring_generation_status": "current",
            "pattern_scoring_generation_reasons": [],
            "pattern_catalog_fingerprint": fingerprint,
            "pattern_scoring_schema_version": scoring_schema,
            "scored_talk_count": 2,
            "pattern_score_sum": 0,
            "average_pattern_score": 0.0,
            "eligible_talk_count": 2,
            "opportunity_coverage_identity": opportunity_identity,
            "raw_score_comparison_status": "available",
            "raw_score_comparison_reason": None,
        },
        "baseline_talk_filenames": filenames,
        "eligible_talk_count": 2,
        "talks_scored": 2,
        "average_pattern_score": 0.0,
        "note": note,
        "pattern_usage": rows["pattern_usage"],
        "antipattern_frequency": rows["antipattern_frequency"],
        **classification,
    }


def _legacy_pattern_profile() -> dict[str, Any]:
    """Project a valid v5 fixture back to the readable occurrence-only v4 shape."""
    profile = _pattern_profile(note="Legacy occurrence-only payload.")
    for field in (
        "classification_schema_version",
        "classification_policy",
        "pattern_classifications",
        "antipattern_classifications",
        "trend_analysis",
    ):
        profile.pop(field)
    profile.update(
        {
            "score_trend": "unavailable",
            "pattern_breadth": {
                "avg_distinct_patterns_per_talk": None,
                "trend": "unavailable",
                "note": "Occurrence-only v4 compatibility.",
            },
            "underused_patterns": [],
            "score_drivers": {
                "direction": "unavailable",
                "antipattern_drivers": [],
                "pattern_drivers": [],
                "note": "Occurrence-only v4 compatibility.",
            },
            "by_mode": [],
            "strengths": [],
            "strengths_note": "Occurrence-only v4 compatibility.",
            "never_used_patterns": [],
            "signature_combinations": [],
            "mastery_levels": {
                "signature": [],
                "regular": [],
                "occasional": [],
                "rare": [],
                "never_tried": [],
            },
            "classification_availability": (
                provenance.unavailable_classification_availability()
            ),
        }
    )
    return profile


def _outcome_talks(
    filenames: list[str],
    scores: list[int] | None = None,
    *,
    outcome: str | None = None,
) -> list[dict[str, Any]]:
    catalog = opportunities.load_catalog()
    observable_ids = sorted(
        pattern_id for pattern_id, entry in catalog.entries.items() if entry.observable
    )
    resolved_scores = scores or [0] * len(filenames)
    fingerprint, scoring_schema = provenance.active_pattern_generation_identity()
    talks = []
    for filename, score in zip(filenames, resolved_scores):
        if outcome is None:
            pattern_outcomes, not_evaluable, assessments = _transcript_projection()
        else:
            pattern_outcomes = [
                {"pattern_id": pattern_id, "outcome": outcome}
                for pattern_id in observable_ids
            ]
            not_evaluable = (
                [{"pattern_id": pattern_id} for pattern_id in observable_ids]
                if outcome == "not_evaluable"
                else []
            )
            assessments = []
        talks.append(
            {
                "filename": filename,
                "pattern_score": score,
                "pattern_observations": {
                    "pattern_score": score,
                    "patterns_detected": [],
                    "antipatterns_detected": [],
                    "not_evaluable": copy.deepcopy(not_evaluable),
                    "applicability_assessments": copy.deepcopy(assessments),
                    "pattern_outcomes": pattern_outcomes,
                    "opportunity_coverage_identity": (
                        pattern_evidence.opportunity_coverage_identity(
                            pattern_outcomes,
                            pattern_catalog_fingerprint=fingerprint,
                            pattern_scoring_schema_version=scoring_schema,
                        )
                    ),
                },
            }
        )
    return talks


def _tracking_database(
    pattern_profile: dict[str, Any],
    *,
    outcome: str | None = None,
) -> dict[str, Any]:
    baseline = pattern_profile["pattern_baseline"]
    filenames = pattern_profile["baseline_talk_filenames"]
    scores = [baseline["pattern_score_sum"], *([0] * (len(filenames) - 1))]
    talks = _outcome_talks(filenames, scores, outcome=outcome)
    for talk in talks:
        talk.update(
            {
                "status": "processed",
                "pattern_scoring_generation_status": "current",
                "pattern_scoring_generation_reasons": [],
                "pattern_catalog_fingerprint": baseline["pattern_catalog_fingerprint"],
                "pattern_scoring_schema_version": baseline[
                    "pattern_scoring_schema_version"
                ],
            }
        )
    return {"talks": talks}


def _all_unknown_pattern_profile() -> dict[str, Any]:
    profile = _pattern_profile(note="All opportunities are unknown.")
    filenames = profile["baseline_talk_filenames"]
    outcome_talks = _outcome_talks(filenames, outcome="not_evaluable")
    rows = opportunities.build_pattern_opportunity_rows(outcome_talks)
    profile["pattern_baseline"].update(
        {
            "scored_talk_count": 0,
            "pattern_score_sum": 0,
            "average_pattern_score": None,
            "opportunity_coverage_identity": None,
            "raw_score_comparison_status": "unavailable",
            "raw_score_comparison_reason": (
                adherence_baseline.NO_EVALUABLE_PATTERN_OPPORTUNITIES_REASON
            ),
        }
    )
    profile["talks_scored"] = 0
    profile["average_pattern_score"] = None
    profile["pattern_usage"] = rows["pattern_usage"]
    profile["antipattern_frequency"] = rows["antipattern_frequency"]
    profile.update(
        classification_runtime.classify_pattern_profile(
            outcome_talks,
            classification_runtime.resolve_classification_policy(
                Path(__file__).resolve().parent / "__no_policy_override__"
            ),
        )
    )
    return profile


def _add_fresh_transcript_evidence(
    database: dict[str, Any],
    vault_root: Path,
) -> None:
    transcripts = vault_root / "transcripts"
    transcripts.mkdir(exist_ok=True)
    for talk in database["talks"]:
        video_id = hashlib.sha256(talk["filename"].encode("utf-8")).hexdigest()[:11]
        source_duration = 60.0
        artifact = transcripts / f"{video_id}.txt"
        content = ("synthetic evidence " * 225).strip() + "\n"
        transcript_timing.write_transcript_bundle(
            artifact,
            content,
            [{"text": content, "start": 0.0, "end": 10.0}],
            source="captions",
            timing_provenance=transcript_timing.youtube_timing_provenance(
                "captions", video_id, source_duration
            ),
            quality_policy=transcript_timing.build_quality_policy(400),
            quality_policy_provenance={"kind": "fixed_default"},
        )
        quality_artifact = artifact.with_suffix(".quality.json")
        timing_artifact = artifact.with_suffix(".segments.json")
        relative = artifact.relative_to(vault_root).as_posix()
        quality_relative = quality_artifact.relative_to(vault_root).as_posix()
        timing_relative = timing_artifact.relative_to(vault_root).as_posix()
        artifact_digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        quality_digest = hashlib.sha256(quality_artifact.read_bytes()).hexdigest()
        timing_digest = hashlib.sha256(timing_artifact.read_bytes()).hexdigest()
        catalog = opportunities.load_catalog()
        located_assessments = []
        for assessment in talk["pattern_observations"].get(
            "applicability_assessments", []
        ):
            entry = catalog.entries[assessment["pattern_id"]]
            channel = (
                "transcript"
                if "transcript" in entry.evidence_channels
                else "timed_transcript"
            )
            citation = {
                "source": "transcript",
                "channel": channel,
                "quote": "synthetic evidence synthetic evidence",
                "line_start": 1,
                "line_end": 1,
                "artifact_root": "vault",
                "artifact_path": relative,
                "artifact_sha256": artifact_digest,
                "timing_artifact_root": "vault",
                "timing_artifact_path": timing_relative,
                "timing_artifact_sha256": timing_digest,
                "quality_artifact_root": "vault",
                "quality_artifact_path": quality_relative,
                "quality_artifact_sha256": quality_digest,
            }
            if channel == "timed_transcript":
                citation.update(
                    {
                        "start_seconds": 0.0,
                        "end_seconds": 10.0,
                    }
                )
            located_assessments.append(
                {
                    **assessment,
                    "evidence_source": "transcript",
                    "evidence": "The complete transcript establishes applicability.",
                    "evidence_citations": [citation],
                }
            )
        talk["transcript_path"] = relative
        talk["transcript_source"] = "youtube_auto"
        talk["youtube_id"] = video_id
        talk["source_identity"] = {
            "schema_version": 1,
            "provider": "youtube",
            "video_id": video_id,
            "duration_seconds": source_duration,
        }
        talk["pattern_observations"].update(
            {
                "evidence_schema_version": 2,
                "evidence_sources": ["transcript"],
                "source_inspection": [
                    {
                        "source": "transcript",
                        "line_ranges": [[1, 1]],
                        "line_count": 1,
                        "coverage_complete": True,
                        "absence_capability_complete": True,
                        "absence_capability_reason": "authorized_transcript",
                        "artifact_root": "vault",
                        "artifact_path": relative,
                        "artifact_sha256": artifact_digest,
                        "timing_artifact_root": "vault",
                        "timing_artifact_path": timing_relative,
                        "timing_artifact_sha256": timing_digest,
                        "quality_artifact_root": "vault",
                        "quality_artifact_path": quality_relative,
                        "quality_artifact_sha256": quality_digest,
                    }
                ],
                "patterns_detected": [],
                "antipatterns_detected": [],
                "applicability_assessments": located_assessments,
            }
        )
        validation = importlib.import_module("return_validation")
        reasons = validation.assess_current_persisted_pattern_evidence_freshness(
            talk,
            vault_root=vault_root,
            catalog=catalog,
        )
        assert reasons == (), "\n".join(reasons)


def _payload(pattern_profile: dict[str, Any]) -> dict[str, Any]:
    baseline = pattern_profile["pattern_baseline"]
    return {
        "schema_version": section15.BLOCK_SCHEMA_VERSION,
        "source_lane": section15.BLOCK_SOURCE_LANE,
        "pattern_catalog_fingerprint": baseline["pattern_catalog_fingerprint"],
        "pattern_scoring_schema_version": baseline["pattern_scoring_schema_version"],
        "baseline_talk_filenames": pattern_profile["baseline_talk_filenames"],
        "pattern_profile": pattern_profile,
    }


def _block_from_json(payload_json: str) -> str:
    return (
        f"{section15.BLOCK_START}\n"
        "```json\n"
        f"{payload_json}\n"
        "```\n\n"
        f"{section15.NON_BASELINE_NOTICE}\n"
        f"{section15.BLOCK_END}"
    )


def _legacy_block_from_json(payload_json: str) -> str:
    return (
        f"{section15.LEGACY_BLOCK_START}\n"
        "```json\n"
        f"{payload_json}\n"
        "```\n\n"
        f"{section15.NON_BASELINE_NOTICE}\n"
        f"{section15.LEGACY_BLOCK_END}"
    )


def _summary(block: str = "") -> str:
    block_area = f"\n{block}\n" if block else "\n"
    return (
        "# Synthetic rhetoric summary\n\n"
        "## 14. Slide-to-Speech Relationship\n\n"
        "Synthetic prior prose.\n\n"
        "## 15. Reflection: Recurring Areas for Improvement\n"
        f"{block_area}\n"
        "- Historical narrative count: 99 of 100. This is not a baseline.\n\n"
        "## 16. Speaker-Confirmed Intent\n\n"
        "Synthetic following prose.\n"
    )


def _summary_from_payload(payload: dict[str, Any]) -> str:
    return _summary(
        _block_from_json(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))
    )


def test_exact_current_block_accepts_complete_scoring_v5_cohort():
    profile = _pattern_profile()
    block = section15.render_section15_current_block(profile)

    assessment = section15.assess_section15_pattern_history(_summary(block))

    assert assessment.current_contract is True
    assert assessment.catalog_fields_available is True
    assert assessment.scored_talk_count == 2
    assert assessment.reason_codes == ()
    assert assessment.classification_fields_available is True
    assert assessment.block_schema_version == 3
    assert assessment.available_classification_domains == frozenset(
        {
            "mastery_and_novelty",
            "antipattern_recurrence",
            "underuse",
            "signature_combinations",
        }
    )
    assert assessment.pattern_profile == profile
    assert profile["pattern_baseline"]["pattern_scoring_schema_version"] == 5


def test_v2_block_remains_readable_as_occurrence_only():
    profile = _legacy_pattern_profile()
    baseline = profile["pattern_baseline"]
    payload = {
        "schema_version": 2,
        "source_lane": section15.BLOCK_SOURCE_LANE,
        "pattern_catalog_fingerprint": baseline["pattern_catalog_fingerprint"],
        "pattern_scoring_schema_version": baseline["pattern_scoring_schema_version"],
        "baseline_talk_filenames": profile["baseline_talk_filenames"],
        "pattern_profile": profile,
    }
    block = _legacy_block_from_json(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False)
    )

    assessment = section15.assess_section15_pattern_history(_summary(block))

    assert assessment.current_contract is True
    assert assessment.block_schema_version == 2
    assert assessment.classification_fields_available is False
    assert assessment.available_classification_domains == frozenset()
    assert assessment.reason_codes == (
        provenance.REASON_CLASSIFICATION_POLICY_UNAVAILABLE,
    )


def test_writer_replaces_v2_in_place_with_one_v3_block():
    legacy = _legacy_pattern_profile()
    baseline = legacy["pattern_baseline"]
    payload = {
        "schema_version": 2,
        "source_lane": section15.BLOCK_SOURCE_LANE,
        "pattern_catalog_fingerprint": baseline["pattern_catalog_fingerprint"],
        "pattern_scoring_schema_version": baseline["pattern_scoring_schema_version"],
        "baseline_talk_filenames": legacy["baseline_talk_filenames"],
        "pattern_profile": legacy,
    }
    original = _summary(
        _legacy_block_from_json(
            json.dumps(payload, indent=2, sort_keys=True, allow_nan=False)
        )
    )

    candidate = section15._replace_block_text(
        original,
        section15.render_section15_current_block(_pattern_profile()),
    )

    assert section15.LEGACY_BLOCK_TOKEN not in candidate
    assert candidate.count(section15.BLOCK_START) == 1
    assert candidate.count(section15.BLOCK_END) == 1
    assert (
        section15.assess_section15_pattern_history(candidate).current_contract is True
    )


def test_mixed_v2_v3_markers_fail_closed():
    profile = _legacy_pattern_profile()
    baseline = profile["pattern_baseline"]
    payload = {
        "schema_version": 2,
        "source_lane": section15.BLOCK_SOURCE_LANE,
        "pattern_catalog_fingerprint": baseline["pattern_catalog_fingerprint"],
        "pattern_scoring_schema_version": baseline["pattern_scoring_schema_version"],
        "baseline_talk_filenames": profile["baseline_talk_filenames"],
        "pattern_profile": profile,
    }
    block = _legacy_block_from_json(json.dumps(payload)).replace(
        section15.LEGACY_BLOCK_END, section15.BLOCK_END
    )

    assessment = section15.assess_section15_pattern_history(_summary(block))

    assert assessment.current_contract is False
    assert assessment.reason_codes == (section15.REASON_BLOCK_INVALID,)
    assert profile["baseline_talk_filenames"] == sorted(
        profile["baseline_talk_filenames"]
    )


def test_all_unknown_cohort_stays_raw_score_unavailable_through_section15_and_creator(
    tmp_path,
):
    profile = _all_unknown_pattern_profile()
    database = _tracking_database(profile, outcome="not_evaluable")
    summary_path = tmp_path / "rhetoric-style-summary.md"
    summary_path.write_text(_summary(), encoding="utf-8")

    result = section15.replace_section15_current_block(
        summary_path,
        profile,
        database,
        evidence_freshness_assessor=_fresh_evidence,
    )
    summary = summary_path.read_text(encoding="utf-8")
    assessment = section15.assess_section15_pattern_history(summary)
    creator_status = pattern_history_status.assess_creator_pattern_history(
        {"schema_version": 5, "pattern_profile": profile},
        summary,
    )

    assert result.scored_talk_count == 0
    assert result.eligible_talk_count == 2
    assert assessment.current_contract is True
    assert assessment.catalog_fields_available is True
    assert assessment.scored_talk_count == 0
    assert assessment.pattern_profile is not None
    baseline = assessment.pattern_profile["pattern_baseline"]
    assert baseline["average_pattern_score"] is None
    assert baseline["raw_score_comparison_status"] == "unavailable"
    assert baseline["raw_score_comparison_reason"] == (
        adherence_baseline.NO_EVALUABLE_PATTERN_OPPORTUNITIES_REASON
    )
    assert creator_status.history_enabled is True
    assert creator_status.history_source == "profile"
    assert creator_status.opportunity_rows_available is True
    assert creator_status.classification_fields_available is True
    assert "mastery_and_novelty" in creator_status.available_classification_domains
    assert creator_status.scored_talk_count == 0


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        (
            "pattern_catalog_fingerprint",
            "0" * 64,
            provenance.REASON_CATALOG_FINGERPRINT_MISMATCH,
        ),
        (
            "pattern_scoring_schema_version",
            3,
            provenance.REASON_SCORING_SCHEMA_MISMATCH,
        ),
    ],
)
def test_stale_generation_identity_fails_closed(field, value, reason):
    profile = _pattern_profile()
    profile["pattern_baseline"][field] = value
    payload = _payload(profile)
    payload[field] = value

    assessment = section15.assess_section15_pattern_history(
        _summary_from_payload(payload)
    )

    assert assessment.current_contract is False
    assert assessment.catalog_fields_available is False
    assert reason in assessment.reason_codes
    assert assessment.pattern_profile is None


def test_incomplete_pattern_history_payload_fails_shared_assessor():
    profile = _pattern_profile()
    del profile["strengths"]

    assessment = section15.assess_section15_pattern_history(
        _summary_from_payload(_payload(profile))
    )

    assert assessment.current_contract is False
    assert provenance.REASON_INVALID_CONTRACT in assessment.reason_codes
    assert any(
        "missing required schema-v5 fields" in error for error in assessment.errors
    )


def test_duplicate_block_and_torn_markers_fail_closed():
    block = section15.render_section15_current_block(_pattern_profile())

    duplicate = section15.assess_section15_pattern_history(
        _summary(block + "\n\n" + block)
    )
    torn = section15.assess_section15_pattern_history(
        _summary(section15.BLOCK_START + "\n```json\n{}")
    )

    assert duplicate.reason_codes == (section15.REASON_BLOCK_DUPLICATE,)
    assert torn.reason_codes == (section15.REASON_BLOCK_INVALID,)
    assert duplicate.pattern_profile is None
    assert torn.pattern_profile is None


def test_duplicate_json_keys_fail_closed():
    payload_json = json.dumps(_payload(_pattern_profile()), sort_keys=True)
    payload_json = payload_json.replace(
        '"schema_version": 2',
        '"schema_version": 2, "schema_version": 2',
        1,
    )

    assessment = section15.assess_section15_pattern_history(
        _summary(_block_from_json(payload_json))
    )

    assert assessment.reason_codes == (section15.REASON_BLOCK_INVALID,)
    assert "duplicate JSON key" in assessment.errors[0]


def test_nonfinite_json_number_fails_closed():
    payload_json = json.dumps(_payload(_pattern_profile()), sort_keys=True)
    payload_json = payload_json.replace('"talks_scored": 2', '"talks_scored": NaN')

    assessment = section15.assess_section15_pattern_history(
        _summary(_block_from_json(payload_json))
    )

    assert assessment.reason_codes == (section15.REASON_BLOCK_INVALID,)
    assert "non-finite JSON number" in assessment.errors[0]


def test_ordinary_section15_prose_never_restores_history():
    assessment = section15.assess_section15_pattern_history(_summary())
    status = pattern_history_status.assess_creator_pattern_history(
        {"schema_version": 2},
        _summary(),
    )

    assert assessment.reason_codes == (section15.REASON_BLOCK_MISSING,)
    assert status.history_enabled is False
    assert status.history_source is None
    assert section15.REASON_BLOCK_MISSING in status.reason_codes


def test_policy_bound_profile_wins_without_merging_section15():
    profile_history = _pattern_profile(note="Profile payload wins.")
    summary_history = _pattern_profile(note="Summary payload must be ignored.")
    profile = {"schema_version": 5, "pattern_profile": profile_history}
    summary = _summary(section15.render_section15_current_block(summary_history))

    resolution = pattern_history_status.resolve_creator_pattern_history(
        profile,
        summary,
    )

    assert resolution.status.history_enabled is True
    assert resolution.status.opportunity_rows_available is True
    assert resolution.status.classification_fields_available is True
    assert resolution.status.history_source == "profile"
    assert resolution.pattern_profile is not None
    assert resolution.pattern_profile["note"] == "Profile payload wins."


def test_policy_bound_section15_is_used_when_profile_history_is_unavailable():
    summary_history = _pattern_profile()
    summary = _summary(section15.render_section15_current_block(summary_history))

    resolution = pattern_history_status.resolve_creator_pattern_history(
        {"schema_version": 2},
        summary,
    )

    assert resolution.status.history_enabled is True
    assert resolution.status.opportunity_rows_available is True
    assert resolution.status.classification_fields_available is True
    assert resolution.status.history_source == "section15_current_block"
    assert resolution.status.reason_codes == ()
    assert resolution.pattern_profile == summary_history


def test_status_cli_uses_valid_fallback_when_profile_file_is_malformed(
    tmp_path,
    capsys,
):
    profile_path = tmp_path / "speaker-profile.json"
    profile_path.write_text("{torn", encoding="utf-8")
    summary_path = tmp_path / "rhetoric-style-summary.md"
    summary_path.write_text(
        _summary(section15.render_section15_current_block(_pattern_profile())),
        encoding="utf-8",
    )

    return_code = pattern_history_status.main(
        [
            "pattern_history_status.py",
            str(profile_path),
            str(summary_path),
        ]
    )
    captured = capsys.readouterr()
    assert captured.out, captured.err
    payload = json.loads(captured.out)

    assert return_code == 0
    assert payload["history_enabled"] is True
    assert payload["opportunity_rows_available"] is True
    assert payload["classification_fields_available"] is True
    assert payload["history_source"] == "section15_current_block"


def test_status_cli_reports_current_rows_without_authorizing_classifications(
    tmp_path,
    capsys,
):
    profile_path = tmp_path / "speaker-profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "schema_version": 4,
                "pattern_profile": _legacy_pattern_profile(),
            }
        ),
        encoding="utf-8",
    )
    return_code = pattern_history_status.main(
        [
            "pattern_history_status.py",
            str(profile_path),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert return_code == 0
    assert payload["history_enabled"] is False
    assert payload["opportunity_rows_available"] is True
    assert payload["classification_fields_available"] is False
    assert payload["history_source"] is None


def test_atomic_replacement_preserves_all_bytes_outside_unique_block(tmp_path):
    old_block = section15.render_section15_current_block(
        _pattern_profile(note="Old payload.")
    )
    summary_path = tmp_path / "rhetoric-style-summary.md"
    summary_path.write_text(_summary(old_block), encoding="utf-8")
    original = summary_path.read_bytes()
    before, remainder = original.split(section15.BLOCK_START.encode(), 1)
    _, after = remainder.split(section15.BLOCK_END.encode(), 1)

    result = section15.replace_section15_current_block(
        summary_path,
        _pattern_profile(note="New payload."),
        _tracking_database(_pattern_profile(note="New payload.")),
        evidence_freshness_assessor=_fresh_evidence,
    )
    updated = summary_path.read_bytes()
    updated_before, updated_remainder = updated.split(section15.BLOCK_START.encode(), 1)
    _, updated_after = updated_remainder.split(section15.BLOCK_END.encode(), 1)

    assert result.changed is True
    assert before == updated_before
    assert after == updated_after
    assert b"New payload." in updated
    assert b"Old payload." not in updated


def test_section15_writer_cannot_omit_freshness_assessment(tmp_path):
    summary_path = tmp_path / "rhetoric-style-summary.md"
    summary_path.write_text(_summary(), encoding="utf-8")
    profile = _pattern_profile()

    with pytest.raises(TypeError, match="evidence_freshness_assessor"):
        section15.replace_section15_current_block(
            summary_path,
            profile,
            _tracking_database(profile),
        )


def test_section15_replace_cli_binds_real_vault_freshness(
    tmp_path,
    capsys,
):
    profile = _pattern_profile()
    database = _tracking_database(profile)
    database["config"] = {}
    _add_fresh_transcript_evidence(database, tmp_path)
    summary_path = tmp_path / "rhetoric-style-summary.md"
    summary_path.write_text(_summary(), encoding="utf-8")
    profile_path = tmp_path / "pattern-profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    database_path = tmp_path / "tracking-database.json"
    database_path.write_text(json.dumps(database), encoding="utf-8")

    return_code = section15.main(
        [
            "replace",
            str(summary_path),
            str(profile_path),
            str(database_path),
        ]
    )
    captured = capsys.readouterr()
    assert captured.out, captured.err
    payload = json.loads(captured.out)

    assert return_code == 0
    assert payload["changed"] is True
    assert section15.BLOCK_START in summary_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("database_locator", "locator_reason"),
    INVALID_VAULT_ROOT_LOCATORS,
)
def test_replace_cli_rejects_invalid_database_locator_before_any_input_io(
    tmp_path,
    monkeypatch,
    capsys,
    database_locator,
    locator_reason,
):
    input_calls = []

    def forbidden_input(*_args, **_kwargs):
        input_calls.append("input_io")
        pytest.fail("invalid tracking-database locator reached input I/O")

    monkeypatch.setattr(section15, "_load_json", forbidden_input)
    monkeypatch.setattr(section15, "_load_tracking_database", forbidden_input)

    return_code = section15.main(
        [
            "replace",
            str(tmp_path / "missing-summary.md"),
            str(tmp_path / "missing-profile.json"),
            database_locator,
        ]
    )
    captured = capsys.readouterr()

    assert return_code == 1
    assert captured.out == ""
    assert input_calls == []
    assert f"vault_root_database_path_invalid:{locator_reason}" in captured.err
    if database_locator.strip():
        assert database_locator not in captured.err


@pytest.mark.parametrize(
    ("configured_root", "locator_reason"),
    INVALID_VAULT_ROOT_LOCATORS,
)
def test_replace_cli_rejects_invalid_config_before_freshness_or_summary_io(
    tmp_path,
    monkeypatch,
    capsys,
    configured_root,
    locator_reason,
):
    profile_path = tmp_path / "pattern-profile.json"
    profile_path.write_text(json.dumps(_pattern_profile()), encoding="utf-8")
    database_path = tmp_path / "tracking-database.json"
    database_path.write_text(
        json.dumps(
            {
                "config": {"vault_storage_path": configured_root},
                "talks": [],
            }
        ),
        encoding="utf-8",
    )
    summary_path = tmp_path / "missing-summary.md"
    monkeypatch.setattr(
        section15,
        "_load_json",
        lambda *_args, **_kwargs: pytest.fail(
            "invalid configured root reached profile input I/O"
        ),
    )
    monkeypatch.setattr(
        section15,
        "configured_evidence_freshness_assessor",
        lambda *_args, **_kwargs: pytest.fail(
            "invalid configured root reached freshness assessment"
        ),
    )

    return_code = section15.main(
        [
            "replace",
            str(summary_path),
            str(profile_path),
            str(database_path),
        ]
    )
    captured = capsys.readouterr()

    assert return_code == 1
    assert captured.out == ""
    assert not summary_path.exists()
    assert f"vault_root_config_invalid:{locator_reason}" in captured.err
    if configured_root.strip():
        assert configured_root not in captured.err


def _section15_directory_symlink(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("directory policy does not permit symlink creation")


def test_replace_cli_accepts_matching_symlink_lexical_authority(
    tmp_path,
    monkeypatch,
    capsys,
):
    storage = tmp_path / "storage"
    storage.mkdir()
    locator = tmp_path / "vault-alias"
    _section15_directory_symlink(locator, storage)
    profile_path = tmp_path / "pattern-profile.json"
    profile_path.write_text("{}", encoding="utf-8")
    database_path = storage / "tracking-database.json"
    database_path.write_text(
        json.dumps(
            {
                "config": {"vault_storage_path": str(locator)},
                "talks": [],
            }
        ),
        encoding="utf-8",
    )
    observed = {}

    def capture_freshness(vault_root, config):
        observed.update(vault_root=vault_root, config=config)
        return _fresh_evidence

    monkeypatch.setattr(
        section15,
        "configured_evidence_freshness_assessor",
        capture_freshness,
    )
    monkeypatch.setattr(
        section15,
        "replace_section15_current_block",
        lambda summary, *_args, **_kwargs: section15.Section15WriteResult(
            path=str(summary),
            changed=False,
            scored_talk_count=0,
            eligible_talk_count=0,
            catalog_fields_available=True,
        ),
    )

    return_code = section15.main(
        [
            "replace",
            str(tmp_path / "unused-summary.md"),
            str(profile_path),
            str(locator / "tracking-database.json"),
        ]
    )
    captured = capsys.readouterr()

    assert return_code == 0, captured.err
    assert observed == {
        "vault_root": locator,
        "config": {"vault_storage_path": str(locator)},
    }


def test_replace_cli_rejects_symlink_target_locator_mismatch_without_paths(
    tmp_path,
    monkeypatch,
    capsys,
):
    storage = tmp_path / "credential-bearing-storage"
    storage.mkdir()
    locator = tmp_path / "credential-bearing-alias"
    _section15_directory_symlink(locator, storage)
    profile_path = tmp_path / "pattern-profile.json"
    profile_path.write_text("{}", encoding="utf-8")
    database_path = storage / "tracking-database.json"
    database_path.write_text(
        json.dumps(
            {
                "config": {"vault_storage_path": str(storage)},
                "talks": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        section15,
        "configured_evidence_freshness_assessor",
        lambda *_args, **_kwargs: pytest.fail(
            "mismatched root reached freshness assessment"
        ),
    )

    return_code = section15.main(
        [
            "replace",
            str(tmp_path / "missing-summary.md"),
            str(profile_path),
            str(locator / "tracking-database.json"),
        ]
    )
    captured = capsys.readouterr()

    assert return_code == 1
    assert captured.out == ""
    assert "vault_root_authority_mismatch:database_path:config_root" in captured.err
    assert str(storage) not in captured.err
    assert str(locator) not in captured.err


def test_replace_cli_catches_freshness_authority_error_without_traceback(
    tmp_path,
    monkeypatch,
    capsys,
):
    profile_path = tmp_path / "pattern-profile.json"
    profile_path.write_text("{}", encoding="utf-8")
    database_path = tmp_path / "tracking-database.json"
    database_path.write_text(
        json.dumps({"config": {}, "talks": []}),
        encoding="utf-8",
    )

    def fail_freshness(*_args, **_kwargs):
        raise section15.PatternCohortSnapshotError(
            "vault_root_config_invalid:artifact_locator_dot_segment"
        )

    monkeypatch.setattr(
        section15,
        "configured_evidence_freshness_assessor",
        fail_freshness,
    )

    return_code = section15.main(
        [
            "replace",
            str(tmp_path / "missing-summary.md"),
            str(profile_path),
            str(database_path),
        ]
    )
    captured = capsys.readouterr()

    assert return_code == 1
    assert captured.out == ""
    assert "vault_root_config_invalid:artifact_locator_dot_segment" in captured.err
    assert str(tmp_path) not in captured.err
    assert "Traceback" not in captured.err


def test_replace_cli_gates_future_database_before_config_path_semantics(
    tmp_path,
    monkeypatch,
    capsys,
):
    profile = _pattern_profile()
    summary_path = tmp_path / "rhetoric-style-summary.md"
    summary_path.write_text(_summary(), encoding="utf-8")
    original_summary = summary_path.read_bytes()
    profile_path = tmp_path / "pattern-profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    database_path = tmp_path / "tracking-database.json"
    database_path.write_text(
        json.dumps(
            {
                "schema_version": 99,
                "config": {"vault_storage_path": "\u0000"},
                "talks": [],
            }
        ),
        encoding="utf-8",
    )
    original_database = database_path.read_bytes()

    def forbidden_path_semantics(*_args, **_kwargs):
        pytest.fail("configured path semantics ran before the owner schema gate")

    monkeypatch.setattr(
        section15,
        "configured_evidence_freshness_assessor",
        forbidden_path_semantics,
    )

    return_code = section15.main(
        [
            "replace",
            str(summary_path),
            str(profile_path),
            str(database_path),
        ]
    )
    captured = capsys.readouterr()

    assert return_code == 1
    assert captured.out == ""
    assert "no usable prior state" in captured.err
    assert "tracking_database_schema_version_unsupported" in captured.err
    assert "Traceback" not in captured.err
    assert summary_path.read_bytes() == original_summary
    assert database_path.read_bytes() == original_database


def test_atomic_helper_inserts_once_then_reports_noop(tmp_path):
    summary_path = tmp_path / "rhetoric-style-summary.md"
    summary_path.write_text(_summary(), encoding="utf-8")
    profile = _pattern_profile()

    database = _tracking_database(profile)
    inserted = section15.replace_section15_current_block(
        summary_path,
        profile,
        database,
        evidence_freshness_assessor=_fresh_evidence,
    )
    first_bytes = summary_path.read_bytes()
    unchanged = section15.replace_section15_current_block(
        summary_path,
        profile,
        database,
        evidence_freshness_assessor=_fresh_evidence,
    )

    assert inserted.changed is True
    assert unchanged.changed is False
    assert summary_path.read_bytes() == first_bytes
    assert first_bytes.count(section15.BLOCK_START.encode()) == 1
    assert first_bytes.count(section15.BLOCK_END.encode()) == 1


def test_invalid_candidate_and_torn_summary_are_no_write_failures(tmp_path):
    summary_path = tmp_path / "rhetoric-style-summary.md"
    summary_path.write_text(_summary(), encoding="utf-8")
    original = summary_path.read_bytes()
    invalid_profile = _pattern_profile()
    invalid_profile["baseline_talk_filenames"] = [
        "example-b.md",
        "example-a.md",
    ]

    with pytest.raises(section15.Section15PatternHistoryError):
        section15.replace_section15_current_block(
            summary_path,
            invalid_profile,
            _tracking_database(invalid_profile),
            evidence_freshness_assessor=_fresh_evidence,
        )
    assert summary_path.read_bytes() == original

    torn = _summary(section15.BLOCK_START + "\n```json\n{}")
    summary_path.write_text(torn, encoding="utf-8")
    with pytest.raises(section15.Section15PatternHistoryError):
        section15.replace_section15_current_block(
            summary_path,
            _pattern_profile(),
            _tracking_database(_pattern_profile()),
            evidence_freshness_assessor=_fresh_evidence,
        )
    assert summary_path.read_text(encoding="utf-8") == torn


def test_replace_rejects_duplicate_filenames_in_ineligible_rows(tmp_path):
    profile = _pattern_profile()
    database = _tracking_database(profile)
    database["talks"].append(
        {
            "filename": profile["baseline_talk_filenames"][0],
            "status": "pending",
            "pattern_scoring_generation_status": "future",
        }
    )
    summary_path = tmp_path / "rhetoric-style-summary.md"
    summary_path.write_text(_summary(), encoding="utf-8")

    before = summary_path.read_bytes()
    with pytest.raises(
        section15.Section15PatternHistoryError,
        match="duplicate talk filename",
    ):
        section15.replace_section15_current_block(
            summary_path,
            profile,
            database,
            evidence_freshness_assessor=_fresh_evidence,
        )
    assert summary_path.read_bytes() == before


def test_replace_rejects_future_tracking_database_without_write(tmp_path):
    profile = _pattern_profile()
    database = _tracking_database(profile)
    database["schema_version"] = 99
    summary_path = tmp_path / "rhetoric-style-summary.md"
    summary_path.write_text(_summary(), encoding="utf-8")
    before = summary_path.read_bytes()

    with pytest.raises(
        section15.Section15PatternHistoryError,
        match="no usable prior state",
    ):
        section15.replace_section15_current_block(
            summary_path,
            profile,
            database,
            evidence_freshness_assessor=_fresh_evidence,
        )

    assert summary_path.read_bytes() == before


def test_failed_atomic_swap_leaves_original_and_no_temp_file(
    tmp_path,
    monkeypatch,
):
    old_block = section15.render_section15_current_block(
        _pattern_profile(note="Original payload.")
    )
    summary_path = tmp_path / "rhetoric-style-summary.md"
    summary_path.write_text(_summary(old_block), encoding="utf-8")
    original = summary_path.read_bytes()

    def fail_swap(_source, _destination):
        raise OSError("synthetic atomic-swap failure")

    monkeypatch.setattr(section15.os, "replace", fail_swap)
    with pytest.raises(OSError, match="synthetic atomic-swap failure"):
        section15.replace_section15_current_block(
            summary_path,
            _pattern_profile(note="Candidate payload."),
            _tracking_database(_pattern_profile(note="Candidate payload.")),
            evidence_freshness_assessor=_fresh_evidence,
        )

    assert summary_path.read_bytes() == original
    assert list(tmp_path.glob(f".{summary_path.name}.*.tmp")) == []


def test_replace_holds_the_shared_summary_writer_lock(tmp_path, monkeypatch):
    """The status-block writer replaces its own block in this same file.

    Two writers that read, splice, and rename without excluding each other drop
    whichever update renamed first. Both take the summary's one writer lock,
    keyed on the target path, so the exclusion holds across the two scripts.
    """
    summary_path = tmp_path / "rhetoric-style-summary.md"
    summary_path.write_text(_summary(), encoding="utf-8")
    lock_path = cooperative_lock.lock_path_for(summary_path)
    observed: list[str] = []
    real_replace = section15.os.replace

    def probe_then_replace(source, destination):
        descriptor = os.open(lock_path, os.O_RDWR)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            observed.append("acquired")
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        except BlockingIOError:
            observed.append("excluded")
        finally:
            os.close(descriptor)
        return real_replace(source, destination)

    monkeypatch.setattr(section15.os, "replace", probe_then_replace)
    profile = _pattern_profile(note="Candidate payload.")
    result = section15.replace_section15_current_block(
        summary_path,
        profile,
        _tracking_database(profile),
        evidence_freshness_assessor=_fresh_evidence,
    )

    assert result.changed is True
    assert observed == ["excluded"]
    # The same sibling lock the status-block writer takes, so the two exclude
    # each other rather than each locking a private name.
    assert lock_path == summary_path.parent / f".{summary_path.name}.lock"
    assert lock_path.is_file()


def test_lock_cleanup_failure_is_reported_not_dropped(tmp_path, monkeypatch, capsys):
    """A release that failed is a warning, never silence.

    The guarded write already happened, so cleanup cannot fail the call — but
    dropping the warning leaves incomplete lock cleanup with nothing naming it.
    """
    summary_path = tmp_path / "rhetoric-style-summary.md"
    summary_path.write_text(_summary(), encoding="utf-8")
    real_flock = cooperative_lock.fcntl.flock

    def fail_unlock(descriptor, operation):
        outcome = real_flock(descriptor, operation)
        if operation == fcntl.LOCK_UN:
            raise OSError("simulated unlock failure")
        return outcome

    monkeypatch.setattr(cooperative_lock.fcntl, "flock", fail_unlock)
    profile = _pattern_profile(note="Candidate payload.")

    result = section15.replace_section15_current_block(
        summary_path,
        profile,
        _tracking_database(profile),
        evidence_freshness_assessor=_fresh_evidence,
    )

    assert result.changed is True
    assert (
        "could not unlock cooperative rhetoric-summary lock" in capsys.readouterr().err
    )


def test_replace_refuses_a_summary_edited_while_the_block_was_staged(
    tmp_path,
    monkeypatch,
):
    """The lock excludes toolkit writers; a human editor holds none."""
    summary_path = tmp_path / "rhetoric-style-summary.md"
    summary_path.write_text(_summary(), encoding="utf-8")
    edited = _summary() + "\nA sentence a human added while the tool ran.\n"
    real_fsync = section15.os.fsync

    def edit_then_fsync(descriptor):
        # A human saves the file after the replacement bytes are staged and
        # before the rename that would install them.
        summary_path.write_text(edited, encoding="utf-8")
        return real_fsync(descriptor)

    monkeypatch.setattr(section15.os, "fsync", edit_then_fsync)
    profile = _pattern_profile(note="Candidate payload.")

    with pytest.raises(
        section15.Section15PatternHistoryError,
        match="changed while the Section 15 replacement was staged",
    ):
        section15.replace_section15_current_block(
            summary_path,
            profile,
            _tracking_database(profile),
            evidence_freshness_assessor=_fresh_evidence,
        )

    assert summary_path.read_text(encoding="utf-8") == edited
    assert list(tmp_path.glob(f".{summary_path.name}.*.tmp")) == []


def test_replace_rejects_stale_same_generation_profile_cohort(tmp_path):
    profile = _pattern_profile()
    database = _tracking_database(profile)
    extra = copy.deepcopy(database["talks"][0])
    extra["filename"] = "example-c.md"
    extra["pattern_score"] = 0
    extra["pattern_observations"]["pattern_score"] = 0
    database["talks"].append(extra)
    summary_path = tmp_path / "rhetoric-style-summary.md"
    summary_path.write_text(_summary(), encoding="utf-8")
    original = summary_path.read_bytes()

    with pytest.raises(
        section15.Section15PatternHistoryError,
        match="complete tracking-database scoring cohort",
    ):
        section15.replace_section15_current_block(
            summary_path,
            profile,
            database,
            evidence_freshness_assessor=_fresh_evidence,
        )

    assert summary_path.read_bytes() == original


def test_replace_rejects_self_consistent_rows_not_present_in_live_database(tmp_path):
    profile = _pattern_profile()
    row = next(row for row in profile["pattern_usage"] if row["evaluable_count"] == 2)
    row["detected_count"] = 1
    row["times_used"] = 1
    row["usage_rate"] = 0.5
    database = _tracking_database(_pattern_profile())
    summary_path = tmp_path / "rhetoric-style-summary.md"
    summary_path.write_text(_summary(), encoding="utf-8")
    original = summary_path.read_bytes()

    with pytest.raises(
        section15.Section15PatternHistoryError,
        match="exact raw A/E/D/U row",
    ):
        section15.replace_section15_current_block(
            summary_path,
            profile,
            database,
            evidence_freshness_assessor=_fresh_evidence,
        )

    assert summary_path.read_bytes() == original


def test_replace_recomputes_policy_derived_rows_from_live_talks(tmp_path):
    profile = _pattern_profile()
    profile["pattern_classifications"][0]["reason_codes"] = [
        "plausible_but_not_canonical"
    ]
    database = _tracking_database(_pattern_profile())
    summary_path = tmp_path / "rhetoric-style-summary.md"
    summary_path.write_text(_summary(), encoding="utf-8")
    original = summary_path.read_bytes()

    with pytest.raises(
        section15.Section15PatternHistoryError,
        match="deterministic classifications recomputed",
    ):
        section15.replace_section15_current_block(
            summary_path,
            profile,
            database,
            evidence_freshness_assessor=_fresh_evidence,
        )

    assert summary_path.read_bytes() == original


def test_replace_rejects_profile_whose_persisted_evidence_is_stale(tmp_path):
    profile = _pattern_profile()
    database = _tracking_database(profile)
    summary_path = tmp_path / "rhetoric-style-summary.md"
    summary_path.write_text(_summary(), encoding="utf-8")
    original = summary_path.read_bytes()

    def assess(talk):
        if talk["filename"] == "example-a.md":
            return ("source_inspection[0]:artifact_digest_mismatch",)
        return ()

    with pytest.raises(
        section15.Section15PatternHistoryError,
        match="complete tracking-database scoring cohort",
    ):
        section15.replace_section15_current_block(
            summary_path,
            profile,
            database,
            evidence_freshness_assessor=assess,
        )

    assert summary_path.read_bytes() == original


def test_replace_cli_reports_catalog_domain_failure_without_traceback(
    tmp_path,
    monkeypatch,
    capsys,
):
    profile = _pattern_profile()
    database = _tracking_database(profile)
    summary_path = tmp_path / "rhetoric-style-summary.md"
    summary_path.write_text(_summary(), encoding="utf-8")
    original = summary_path.read_bytes()
    profile_path = tmp_path / "pattern-profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    database_path = tmp_path / "tracking-database.json"
    database_path.write_text(json.dumps(database), encoding="utf-8")

    def fail_snapshot(*_args, **_kwargs):
        raise section15.ReturnValidationError("synthetic active catalog failure")

    monkeypatch.setattr(section15, "build_current_pattern_snapshot", fail_snapshot)

    return_code = section15.main(
        [
            "replace",
            str(summary_path),
            str(profile_path),
            str(database_path),
        ]
    )
    captured = capsys.readouterr()

    assert return_code == 1
    assert captured.out == ""
    assert "cannot verify the complete tracking-database cohort" in captured.err
    assert "synthetic active catalog failure" in captured.err
    assert "Traceback" not in captured.err
    assert summary_path.read_bytes() == original


def test_guardrail_uses_policy_bound_section15_without_inventing_recurrence(
    guardrail_check,
    tmp_path,
    capsys,
):
    summary_path = tmp_path / "rhetoric-style-summary.md"
    summary_path.write_text(
        _summary(section15.render_section15_current_block(_pattern_profile())),
        encoding="utf-8",
    )

    return_code = guardrail_check.main(
        [
            "guardrail-check.py",
            str(OUTLINE),
            "-",
            str(summary_path),
        ]
    )
    report = json.loads(capsys.readouterr().out)
    checks = {item["name"]: item for item in report["checks"]}

    assert return_code == 0
    assert "policy-bound domains enabled" in checks["Pattern history"]["detail"]
    assert report["pattern_history"]["history_source"] == "section15_current_block"
    assert (
        "antipattern_recurrence"
        in (report["pattern_history"]["available_classification_domains"])
    )
    assert report["recurring_antipatterns"] == []


def test_creator_docs_delegate_history_source_resolution():
    creator = ROOT / "skills" / "presentation-creator"
    docs = {
        # SKILL.md keeps the pattern_history_status.py invocation and routes to
        # this file, which owns the Section 15 eligibility contract.
        "pattern_history": (
            creator / "references" / "pattern-history-authorization.md"
        ).read_text(encoding="utf-8"),
        "phase0": (creator / "references" / "phase0-intake.md").read_text(
            encoding="utf-8"
        ),
        "phase4": (creator / "references" / "phase4-guardrails.md").read_text(
            encoding="utf-8"
        ),
    }
    skill = (creator / "SKILL.md").read_text(encoding="utf-8")

    for text in docs.values():
        assert "history_source" in text
    assert "references/pattern-history-authorization.md" in skill
    assert "resolve_creator_pattern_history()" in docs["phase0"]
    assert "section15_pattern_history.py" in docs["pattern_history"]
    assert "section15_pattern_history.py" in docs["phase0"]
    assert "section15_pattern_history.py" not in docs["phase4"]
    assert "recurring_pattern_history_items()" in docs["phase4"]


def test_ingress_docs_require_live_database_for_current_block_replace():
    ingress = ROOT / "skills" / "vault-ingress"
    skill = (ingress / "SKILL.md").read_text(encoding="utf-8")
    processing = (ingress / "references" / "processing-rules.md").read_text(
        encoding="utf-8"
    )

    assert "references/processing-rules.md" in skill
    assert "section15_pattern_history.py" in skill
    assert "tracking-database.json" in skill
    assert "stale" in skill
    assert 'section15_pattern_history.py" replace' in processing
    assert "tracking-database.json" in processing
    assert "stale" in processing
