#!/usr/bin/env python3
"""Compute the speaker-profile `pacing.adherence` object from scored talks.

Deterministic helper for vault-profile Step 4 (per `rules/script-delegation.md`):
parses each talk's duration, derives slides-per-minute, classifies it against the
speaker's slide budgets, and emits the corpus-level adherence summary. The skill
orchestrator pipes in the scored talks plus the budget table and copies the result
into `pacing.adherence`.

Contract
--------
Stdin (JSON):
    {
      "talks": [
        {"filename": "...", "date": "YYYY-MM-DD",
         "slide_count": <int>, "talk_duration_estimate": "35 min"}
      ],
      "slide_budgets": [
        {"duration_min": <int>, "max_slides": <int>, "slides_per_min": <float>}
      ],
      "worst_n": 5            # optional, default 5
    }

Stdout (JSON):
    {
      "talks_over_budget": <int>,
      "talks_scored":      <int>,
      "over_budget_rate":  <float>,          # 0.0 when nothing scored
      "trend":             "improving|stable|worsening",
      "worst_offenders": [
        {"filename": "...", "slides_per_minute": <float>,
         "budget_slides_per_minute": <float>, "over_by": "40%"}
      ]
    }

Duration parsing: the first integer in `talk_duration_estimate` is the value;
an "hour"/"hr" unit multiplies it by 60 (so "1 hour" -> 60). Talks with no
parseable minutes, missing/zero slide_count, or zero minutes are skipped (not
scored). Budget band: the entry with the largest `duration_min` <= the talk's
minutes, or the smallest band when the talk is shorter than every band.
Trend compares the over-budget rate of the older half vs. the newer half of the
date-sorted scored talks; fewer than 4 scored talks yields "stable".

Exit codes:
    0   success
    1   malformed stdin JSON or wrong shape. Diagnostic goes to stderr.
"""

from __future__ import annotations

import json
import re
import sys


TREND_EPSILON = 0.10
MIN_TALKS_FOR_TREND = 4
DEFAULT_WORST_N = 5


def parse_minutes(estimate: object) -> int | None:
    """First integer in the string, ×60 when an hour unit is present."""
    if not isinstance(estimate, str):
        return None
    match = re.search(r"\d+", estimate)
    if match is None:
        return None
    value = int(match.group())
    if re.search(r"\b(hour|hr)s?\b", estimate, re.IGNORECASE):
        value *= 60
    return value or None


def budget_for(minutes: int, budgets: list[dict]) -> float | None:
    """slides_per_min of the applicable band (largest duration_min <= minutes)."""
    if not budgets:
        return None
    ordered = sorted(budgets, key=lambda b: b["duration_min"])
    applicable = [b for b in ordered if b["duration_min"] <= minutes]
    band = applicable[-1] if applicable else ordered[0]
    value = float(band["slides_per_min"])
    if value <= 0:
        raise ValueError(f"slide budget slides_per_min must be positive, got {value}")
    return value


def _over_budget_rate(talks: list[dict]) -> float:
    if not talks:
        return 0.0
    return sum(1 for t in talks if t["over_budget"]) / len(talks)


def compute(payload: dict) -> dict:
    budgets = payload.get("slide_budgets", [])
    worst_n = payload.get("worst_n", DEFAULT_WORST_N)
    scored: list[dict] = []

    for talk in payload.get("talks", []):
        slide_count = talk.get("slide_count")
        minutes = parse_minutes(talk.get("talk_duration_estimate", ""))
        if not slide_count or not minutes:
            continue
        budget = budget_for(minutes, budgets)
        if budget is None:
            continue
        spm = slide_count / minutes
        scored.append({
            "filename": talk.get("filename"),
            "date": talk.get("date", ""),
            "slides_per_minute": round(spm, 2),
            "budget_slides_per_minute": budget,
            "over_budget": spm > budget,
            "over_by_ratio": (spm / budget) - 1.0,
        })

    over = [t for t in scored if t["over_budget"]]
    worst = sorted(over, key=lambda t: t["over_by_ratio"], reverse=True)[:worst_n]

    trend = "stable"
    if len(scored) >= MIN_TALKS_FOR_TREND:
        chrono = sorted(scored, key=lambda t: t["date"])
        half = len(chrono) // 2
        delta = _over_budget_rate(chrono[half:]) - _over_budget_rate(chrono[:half])
        if delta > TREND_EPSILON:
            trend = "worsening"
        elif delta < -TREND_EPSILON:
            trend = "improving"

    return {
        "talks_over_budget": len(over),
        "talks_scored": len(scored),
        "over_budget_rate": round(_over_budget_rate(scored), 2),
        "trend": trend,
        "worst_offenders": [
            {
                "filename": t["filename"],
                "slides_per_minute": t["slides_per_minute"],
                "budget_slides_per_minute": t["budget_slides_per_minute"],
                "over_by": f"{round(t['over_by_ratio'] * 100)}%",
            }
            for t in worst
        ],
    }


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError as exc:
        print(f"ERROR: stdin is not valid JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(payload, dict):
        print("ERROR: stdin JSON must be an object with 'talks' and "
              "'slide_budgets'.", file=sys.stderr)
        return 1
    if not isinstance(payload.get("talks", []), list) or not isinstance(
        payload.get("slide_budgets", []), list
    ):
        print("ERROR: 'talks' and 'slide_budgets' must be JSON arrays.",
              file=sys.stderr)
        return 1
    try:
        result = compute(payload)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        print(f"ERROR: malformed payload shape: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
