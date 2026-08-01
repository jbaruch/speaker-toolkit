"""Tests for validate-profile.py — required-key + schema_version validation.

Locks in the graceful fallback for the engine-sourcing feature: a profile that
predates `presentation_engines` must still validate, since the field is
optional/additive and not part of REQUIRED_KEYS.
"""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest


CATALOG = "c" * 64
OTHER_CATALOG = "d" * 64
AS_OF = "2026-07-31T13:30:45.987654-05:00"


# Built programmatically per testing-standards (no fixture file). A current
# profile carries explicit zero-cohort pattern provenance rather than borrowing
# historical pattern values.
def _minimal_profile(validate_profile):
    catalog_fingerprint, scoring_schema = (
        validate_profile.active_pattern_generation_identity()
    )
    profile = {k: [] for k in (
        "generated_date", "talks_analyzed", "speaker", "infrastructure",
        "presentation_modes", "instrument_catalog", "rhetoric_defaults",
        "confirmed_intents", "guardrail_sources", "pacing", "pattern_profile",
        "visual_style_history", "publishing_process", "design_rules", "badges",
    )} | {"schema_version": 3}
    profile["pattern_profile"] = {
        "pattern_baseline": {
            "schema_version": 1,
            "as_of": "2025-01-02T03:04:05+00:00",
            "scope": "global",
            "active_batch_excluded": False,
            "excluded_filenames": [],
            "eligible_statuses": ["processed", "processed_partial"],
            "pattern_scoring_generation_status": "current",
            "pattern_scoring_generation_reasons": [],
            "pattern_catalog_fingerprint": catalog_fingerprint,
            "pattern_scoring_schema_version": scoring_schema,
            "scored_talk_count": 0,
            "pattern_score_sum": 0,
            "average_pattern_score": None,
        },
        "baseline_talk_filenames": [],
        "talks_scored": 0,
        "average_pattern_score": None,
        "score_trend": "unavailable",
        "pattern_breadth": {
            "avg_distinct_patterns_per_talk": None,
            "trend": "unavailable",
            "note": "No current pattern cohort.",
        },
        "underused_patterns": [],
        "score_drivers": {
            "direction": "unavailable",
            "antipattern_drivers": [],
            "pattern_drivers": [],
            "note": "No current pattern cohort.",
        },
        "by_mode": [],
        "strengths": [],
        "strengths_note": "No current pattern cohort.",
        "note": "Only current observable patterns are included.",
        "pattern_usage": [],
        "antipattern_frequency": [],
        "never_used_patterns": [],
        "signature_combinations": [],
        "mastery_levels": {
            "signature": [],
            "regular": [],
            "occasional": [],
            "rare": [],
            "never_tried": [],
        },
    }
    profile["rhetoric_defaults"] = {}
    profile["guardrail_sources"] = {"recurring_issues": []}
    return profile


def _run(validate_profile, profile, tmp_path):
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(profile))
    rc = validate_profile.main(["validate-profile.py", str(path)])
    return rc


def test_profile_without_engines_still_validates(validate_profile, tmp_path, capsys):
    # The whole point: presentation_engines is optional/additive — a profile that
    # never heard of it is still valid.
    profile = _minimal_profile(validate_profile)
    assert "presentation_engines" not in profile
    rc = _run(validate_profile, profile, tmp_path)
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["valid"] is True
    assert out["missing_keys"] == []


def test_profile_with_engines_validates(validate_profile, tmp_path, capsys):
    profile = _minimal_profile(validate_profile)
    profile["presentation_engines"] = [
        {"id": "pptx", "renderer": "pptx", "usage_count": 18, "out_of": 24}
    ]
    rc = _run(validate_profile, profile, tmp_path)
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["valid"] is True


def test_profile_missing_required_key_is_invalid(validate_profile, tmp_path, capsys):
    profile = _minimal_profile(validate_profile)
    del profile["design_rules"]
    rc = _run(validate_profile, profile, tmp_path)
    out = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert out["valid"] is False
    assert "design_rules" in out["missing_keys"]


def test_profile_with_outdated_schema_version_is_invalid(validate_profile, tmp_path, capsys):
    # Profiles before v3 have no exact pattern-generation provenance and cannot
    # pass the owner writer's current-generation gate.
    profile = _minimal_profile(validate_profile) | {"schema_version": 1}
    rc = _run(validate_profile, profile, tmp_path)
    out = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert out["valid"] is False
    assert out["schema_version"] == 1


# --- load-vault instrumentation partitioning -------------------------------

def _talks(*dates):
    return [{"filename": f"t{i}.md", "status": "processed", "processed_date": d}
            for i, d in enumerate(dates)]


def test_partition_splits_on_the_epoch(load_vault):
    current, stale = load_vault.partition_by_instrumentation(
        _talks("2026-07-27", "2026-07-26", "2026-07-25", "2026-05-01"))
    assert [t["processed_date"] for t in current] == ["2026-07-27", "2026-07-26"]
    assert [t["processed_date"] for t in stale] == ["2026-07-25", "2026-05-01"]


def test_undated_talks_are_treated_as_stale(load_vault):
    """Excluding an undated talk only narrows the sample; including it would
    silently contaminate the baseline."""
    talks = _talks("2026-07-27")
    talks.append({"filename": "x.md", "status": "processed"})
    talks.append({"filename": "y.md", "status": "processed", "processed_date": None})
    current, stale = load_vault.partition_by_instrumentation(talks)
    assert len(current) == 1
    assert {t["filename"] for t in stale} == {"x.md", "y.md"}


def test_epoch_is_injectable_for_callers(load_vault):
    current, stale = load_vault.partition_by_instrumentation(
        _talks("2020-01-01"), epoch="2019-01-01")
    assert len(current) == 1 and not stale


# --- load-vault exact pattern-scoring cohort -------------------------------

def _scored_talk(
    filename,
    score,
    *,
    processed_date="2026-07-27",
    status="processed",
    catalog=CATALOG,
    scoring_schema=3,
    generation_status="current",
    generation_reasons=None,
):
    if generation_reasons is None:
        generation_reasons = []
    return {
        "filename": filename,
        "status": status,
        "processed_date": processed_date,
        "pattern_scoring_generation_status": generation_status,
        "pattern_scoring_generation_reasons": generation_reasons,
        "pattern_catalog_fingerprint": catalog,
        "pattern_scoring_schema_version": scoring_schema,
        "pattern_score": score,
        "pattern_observations": {"pattern_score": score},
    }


def _write_vault(vault_root, talks):
    (vault_root / "tracking-database.json").write_text(
        json.dumps(
            {
                "config": {"synthetic": True},
                "confirmed_intents": [],
                "talks": talks,
            }
        )
    )
    (vault_root / "rhetoric-style-summary.md").write_text("Synthetic summary\n")


def _run_load_vault(load_vault, vault_root, monkeypatch, capsys):
    monkeypatch.setattr(
        load_vault,
        "load_catalog",
        lambda: SimpleNamespace(fingerprint=CATALOG),
    )
    rc = load_vault.main(
        ["load-vault.py", str(vault_root), "--as-of", AS_OF]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out) if captured.out else None
    return rc, payload, captured.err


def test_load_vault_separates_pattern_generation_from_instrumentation(
    load_vault,
    tmp_path,
    monkeypatch,
    capsys,
):
    exact_old = _scored_talk(
        "current-old-date.md",
        2,
        processed_date="2026-01-01",
        scoring_schema=load_vault.PATTERN_SCORING_SCHEMA_VERSION,
    )
    legacy_recent = _scored_talk(
        "legacy-recent.md",
        100,
        generation_status="legacy_unbaselineable",
    )
    old_catalog_recent = _scored_talk(
        "old-catalog-recent.md",
        90,
        catalog=OTHER_CATALOG,
        scoring_schema=load_vault.PATTERN_SCORING_SCHEMA_VERSION,
    )
    old_schema_recent = _scored_talk(
        "old-schema-recent.md",
        80,
        scoring_schema=load_vault.PATTERN_SCORING_SCHEMA_VERSION - 1,
    )
    missing_generation = _scored_talk(
        "missing-generation.md",
        70,
        scoring_schema=load_vault.PATTERN_SCORING_SCHEMA_VERSION,
    )
    missing_generation.pop("pattern_scoring_generation_status")
    pending = _scored_talk(
        "pending.md",
        60,
        status="pending",
        generation_status="future",
    )
    _write_vault(
        tmp_path,
        [
            exact_old,
            legacy_recent,
            old_catalog_recent,
            old_schema_recent,
            missing_generation,
            pending,
        ],
    )

    rc, payload, error = _run_load_vault(
        load_vault, tmp_path, monkeypatch, capsys
    )

    assert rc == 0
    assert error == ""
    assert [talk["filename"] for talk in payload["baseline_talks"]] == [
        "current-old-date.md"
    ]
    assert [
        talk["filename"] for talk in payload["excluded_pattern_scoring_talks"]
    ] == [
        "legacy-recent.md",
        "old-catalog-recent.md",
        "old-schema-recent.md",
        "missing-generation.md",
    ]
    assert {
        detail["filename"]: detail["reason_codes"]
        for detail in payload["pattern_scoring_exclusions"]
    } == {
        "legacy-recent.md": ["legacy_generation"],
        "old-catalog-recent.md": ["catalog_fingerprint_mismatch"],
        "old-schema-recent.md": ["scoring_schema_version_mismatch"],
        "missing-generation.md": ["missing_generation_status"],
    }
    assert [
        talk["filename"] for talk in payload["current_instrumentation_talks"]
    ] == [
        "legacy-recent.md",
        "old-catalog-recent.md",
        "old-schema-recent.md",
        "missing-generation.md",
    ]
    assert [
        talk["filename"] for talk in payload["stale_instrumentation_talks"]
    ] == ["current-old-date.md"]
    assert payload["pattern_baseline"] == {
        "schema_version": 1,
        "as_of": "2026-07-31T18:30:45+00:00",
        "scope": "global",
        "active_batch_excluded": False,
        "excluded_filenames": [],
        "eligible_statuses": ["processed", "processed_partial"],
        "pattern_scoring_generation_status": "current",
        "pattern_scoring_generation_reasons": [],
        "pattern_catalog_fingerprint": CATALOG,
        "pattern_scoring_schema_version": (
            load_vault.PATTERN_SCORING_SCHEMA_VERSION
        ),
        "scored_talk_count": 1,
        "pattern_score_sum": 2,
        "average_pattern_score": 2.0,
    }
    assert "snapshot observation time" in payload["baseline_note"]
    assert "processed_date" in payload["baseline_note"]
    assert "does not confer pattern-scoring" in payload["instrumentation_note"]


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("unknown_status", "pattern_scoring_generation_status must be one of"),
        ("current_reasons", "pattern_scoring_generation_reasons must be exactly"),
        ("missing_fingerprint", "missing required identity fields"),
        ("malformed_fingerprint", "must be a lowercase 64-character"),
        ("divergent_score", "promoted pattern_score 5 diverges"),
    ],
)
def test_load_vault_rejects_malformed_current_generation_records(
    load_vault,
    tmp_path,
    monkeypatch,
    capsys,
    case,
    message,
):
    talk = _scored_talk(
        "malformed.md",
        5,
        scoring_schema=load_vault.PATTERN_SCORING_SCHEMA_VERSION,
    )
    if case == "unknown_status":
        talk["pattern_scoring_generation_status"] = "future"
    elif case == "current_reasons":
        talk["pattern_scoring_generation_reasons"] = ["contradiction"]
    elif case == "missing_fingerprint":
        talk.pop("pattern_catalog_fingerprint")
    elif case == "malformed_fingerprint":
        talk["pattern_catalog_fingerprint"] = "not-a-sha"
    elif case == "divergent_score":
        talk["pattern_observations"]["pattern_score"] = 4
    _write_vault(tmp_path, [talk])

    rc, payload, error = _run_load_vault(
        load_vault, tmp_path, monkeypatch, capsys
    )

    assert rc == 1
    assert payload is None
    assert message in error


def test_load_vault_does_not_fallback_when_current_pattern_cohort_is_empty(
    load_vault,
    tmp_path,
    monkeypatch,
    capsys,
):
    legacy = _scored_talk(
        "legacy.md",
        100,
        generation_status="legacy_unbaselineable",
    )
    _write_vault(tmp_path, [legacy])

    rc, payload, error = _run_load_vault(
        load_vault, tmp_path, monkeypatch, capsys
    )

    assert rc == 0
    assert error == ""
    assert payload["baseline_talks"] == []
    assert [
        talk["filename"] for talk in payload["excluded_pattern_scoring_talks"]
    ] == ["legacy.md"]
    assert payload["pattern_baseline"]["scored_talk_count"] == 0
    assert payload["pattern_baseline"]["pattern_score_sum"] == 0
    assert payload["pattern_baseline"]["average_pattern_score"] is None


def test_default_as_of_uses_injected_time_and_canonical_whole_seconds(load_vault):
    now = datetime(2026, 7, 31, 18, 30, 45, 987654, tzinfo=timezone.utc)

    assert load_vault.default_as_of(now) == "2026-07-31T18:30:45+00:00"
