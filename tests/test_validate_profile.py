"""Tests for validate-profile.py — required-key + schema_version validation.

Locks in the graceful fallback for the engine-sourcing feature: a profile that
predates `presentation_engines` must still validate, since the field is
optional/additive and not part of REQUIRED_KEYS.
"""

import json


# Built programmatically per testing-standards (no fixture file). The validator
# checks key presence + schema_version only, so placeholder values are fine.
def _minimal_profile():
    return {k: [] for k in (
        "generated_date", "talks_analyzed", "speaker", "infrastructure",
        "presentation_modes", "instrument_catalog", "rhetoric_defaults",
        "confirmed_intents", "guardrail_sources", "pacing", "pattern_profile",
        "visual_style_history", "publishing_process", "design_rules", "badges",
    )} | {"schema_version": 2}


def _run(validate_profile, profile, tmp_path):
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(profile))
    rc = validate_profile.main(["validate-profile.py", str(path)])
    return rc


def test_profile_without_engines_still_validates(validate_profile, tmp_path, capsys):
    # The whole point: presentation_engines is optional/additive — a profile that
    # never heard of it is still valid.
    profile = _minimal_profile()
    assert "presentation_engines" not in profile
    rc = _run(validate_profile, profile, tmp_path)
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["valid"] is True
    assert out["missing_keys"] == []


def test_profile_with_engines_validates(validate_profile, tmp_path, capsys):
    profile = _minimal_profile()
    profile["presentation_engines"] = [
        {"id": "pptx", "renderer": "pptx", "usage_count": 18, "out_of": 24}
    ]
    rc = _run(validate_profile, profile, tmp_path)
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["valid"] is True


def test_profile_missing_required_key_is_invalid(validate_profile, tmp_path, capsys):
    profile = _minimal_profile()
    del profile["design_rules"]
    rc = _run(validate_profile, profile, tmp_path)
    out = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert out["valid"] is False
    assert "design_rules" in out["missing_keys"]


def test_profile_with_outdated_schema_version_is_invalid(validate_profile, tmp_path, capsys):
    # The v1→v2 bump (coaching-outcome fields) must be enforced: a v1 profile
    # is rejected so a stale write can't pass validation.
    profile = _minimal_profile() | {"schema_version": 1}
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
