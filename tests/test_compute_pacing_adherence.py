"""Tests for compute-pacing-adherence.py — the pacing.adherence helper.

Fixtures are built programmatically (per testing-standards); no random inputs.
"""

import io
import json


BUDGETS = [
    {"duration_min": 20, "max_slides": 30, "slides_per_min": 1.5},
    {"duration_min": 45, "max_slides": 70, "slides_per_min": 1.5},
    {"duration_min": 90, "max_slides": 130, "slides_per_min": 1.4},
]


def _talk(filename, date, slides, dur):
    return {
        "filename": filename, "date": date,
        "slide_count": slides, "talk_duration_estimate": dur,
    }


# ── parse_minutes ────────────────────────────────────────────────────

def test_parse_minutes_plain(compute_pacing_adherence):
    assert compute_pacing_adherence.parse_minutes("35 min") == 35


def test_parse_minutes_hours_multiply(compute_pacing_adherence):
    assert compute_pacing_adherence.parse_minutes("1 hour") == 60
    assert compute_pacing_adherence.parse_minutes("2 hrs") == 120


def test_parse_minutes_unparseable_is_none(compute_pacing_adherence):
    assert compute_pacing_adherence.parse_minutes("") is None
    assert compute_pacing_adherence.parse_minutes("about a while") is None
    assert compute_pacing_adherence.parse_minutes(None) is None


# ── budget_for ───────────────────────────────────────────────────────

def test_budget_band_picks_largest_le(compute_pacing_adherence):
    # 60 min -> 45-min band (largest duration_min <= 60)
    assert compute_pacing_adherence.budget_for(60, BUDGETS) == 1.5
    # 90 min -> 90-min band
    assert compute_pacing_adherence.budget_for(90, BUDGETS) == 1.4


def test_budget_band_short_talk_uses_smallest(compute_pacing_adherence):
    # 10 min is shorter than every band -> smallest band
    assert compute_pacing_adherence.budget_for(10, BUDGETS) == 1.5


# ── compute: counts + rate ───────────────────────────────────────────

def test_over_budget_count_and_rate(compute_pacing_adherence):
    talks = [
        _talk("over.md", "2024-01-01", 90, "45 min"),    # 2.0 spm > 1.5 -> over
        _talk("under.md", "2024-02-01", 60, "45 min"),   # 1.33 spm < 1.5 -> ok
    ]
    out = compute_pacing_adherence.compute({"talks": talks, "slide_budgets": BUDGETS})
    assert out["talks_scored"] == 2
    assert out["talks_over_budget"] == 1
    assert out["over_budget_rate"] == 0.5


def test_worst_offenders_sorted_by_over_by_desc(compute_pacing_adherence):
    talks = [
        _talk("a.md", "2024-01-01", 90, "45 min"),   # 2.0/1.5 -> +33%
        _talk("c.md", "2024-02-01", 180, "90 min"),  # 2.0/1.4 -> +43%
    ]
    out = compute_pacing_adherence.compute({"talks": talks, "slide_budgets": BUDGETS})
    offenders = out["worst_offenders"]
    assert [o["filename"] for o in offenders] == ["c.md", "a.md"]
    assert offenders[0]["over_by"] == "43%"
    assert offenders[1]["over_by"] == "33%"


def test_hour_format_talk_is_scored(compute_pacing_adherence):
    # "1 hour" -> 60 min -> 45 band (1.5); 60 slides -> 1.0 spm -> not over
    talks = [_talk("hour.md", "2024-01-01", 60, "1 hour")]
    out = compute_pacing_adherence.compute({"talks": talks, "slide_budgets": BUDGETS})
    assert out["talks_scored"] == 1
    assert out["talks_over_budget"] == 0


def test_unparseable_and_zero_slides_skipped(compute_pacing_adherence):
    talks = [
        _talk("noslides.md", "2024-01-01", 0, "45 min"),
        _talk("nodur.md", "2024-02-01", 50, ""),
        _talk("good.md", "2024-03-01", 90, "45 min"),
    ]
    out = compute_pacing_adherence.compute({"talks": talks, "slide_budgets": BUDGETS})
    assert out["talks_scored"] == 1
    assert out["worst_offenders"][0]["filename"] == "good.md"


# ── compute: trend ───────────────────────────────────────────────────

def test_trend_worsening(compute_pacing_adherence):
    # older two ok, newer two over -> worsening
    talks = [
        _talk("t1.md", "2024-01-01", 60, "45 min"),
        _talk("t2.md", "2024-02-01", 60, "45 min"),
        _talk("t3.md", "2024-03-01", 90, "45 min"),
        _talk("t4.md", "2024-04-01", 90, "45 min"),
    ]
    out = compute_pacing_adherence.compute({"talks": talks, "slide_budgets": BUDGETS})
    assert out["trend"] == "worsening"


def test_trend_improving(compute_pacing_adherence):
    talks = [
        _talk("t1.md", "2024-01-01", 90, "45 min"),
        _talk("t2.md", "2024-02-01", 90, "45 min"),
        _talk("t3.md", "2024-03-01", 60, "45 min"),
        _talk("t4.md", "2024-04-01", 60, "45 min"),
    ]
    out = compute_pacing_adherence.compute({"talks": talks, "slide_budgets": BUDGETS})
    assert out["trend"] == "improving"


def test_trend_stable_when_too_few(compute_pacing_adherence):
    talks = [
        _talk("t1.md", "2024-01-01", 90, "45 min"),
        _talk("t2.md", "2024-02-01", 90, "45 min"),
    ]
    out = compute_pacing_adherence.compute({"talks": talks, "slide_budgets": BUDGETS})
    assert out["trend"] == "stable"


def test_empty_input(compute_pacing_adherence):
    out = compute_pacing_adherence.compute({"talks": [], "slide_budgets": BUDGETS})
    assert out == {
        "talks_over_budget": 0, "talks_scored": 0, "over_budget_rate": 0.0,
        "trend": "stable", "worst_offenders": [],
    }


# ── main: I/O contract ───────────────────────────────────────────────

def test_main_reads_stdin_emits_json(compute_pacing_adherence, monkeypatch, capsys):
    payload = {"talks": [_talk("o.md", "2024-01-01", 90, "45 min")], "slide_budgets": BUDGETS}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    rc = compute_pacing_adherence.main()
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["talks_over_budget"] == 1


def test_main_rejects_non_json(compute_pacing_adherence, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    rc = compute_pacing_adherence.main()
    err = capsys.readouterr().err
    assert rc == 1
    assert "valid JSON" in err


def test_main_rejects_wrong_shape_talks(compute_pacing_adherence, monkeypatch, capsys):
    # talks as a string must yield a controlled ERROR + rc 1, not a traceback.
    monkeypatch.setattr(
        "sys.stdin", io.StringIO(json.dumps({"talks": "oops", "slide_budgets": []}))
    )
    rc = compute_pacing_adherence.main()
    err = capsys.readouterr().err
    assert rc == 1
    assert "ERROR" in err


def test_main_rejects_nonpositive_budget(compute_pacing_adherence, monkeypatch, capsys):
    # slides_per_min of 0 would divide-by-zero; must be a controlled ERROR + rc 1.
    payload = {
        "talks": [_talk("a.md", "2024-01-01", 90, "45 min")],
        "slide_budgets": [{"duration_min": 20, "max_slides": 30, "slides_per_min": 0}],
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    rc = compute_pacing_adherence.main()
    err = capsys.readouterr().err
    assert rc == 1
    assert "positive" in err


def test_main_rejects_malformed_budget(compute_pacing_adherence, monkeypatch, capsys):
    # budget entries missing required keys are caught at the boundary, not raised.
    payload = {
        "talks": [_talk("a.md", "2024-01-01", 90, "45 min")],
        "slide_budgets": [{"oops": 1}],
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    rc = compute_pacing_adherence.main()
    err = capsys.readouterr().err
    assert rc == 1
    assert "ERROR" in err
