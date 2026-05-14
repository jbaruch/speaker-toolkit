#!/usr/bin/env python3
"""Run profile-aware guardrail checks on outline.yaml.

Reads `outline.yaml` (validated by `outline_schema.py`) and a speaker profile.
Computes profile-thresholded checks (slide budget, Act 1 ratio, branding,
profanity, closing completeness, cut-line availability, data-attribution
heuristics). Outputs a structured report with [PASS], [WARN], or [FAIL]
labels.

Structural pattern checks (opening PUNCH, big-idea singleton, sparkline
elements, callback ledger, master-story threading, etc.) are handled by
`check-rhetorical.py` — those need no profile. Run both scripts in Phase 4.

Usage:
    guardrail-check.py <outline.yaml> <speaker-profile.json>

Output: report to stdout; exits 0 even if FAIL — the report is informational.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import yaml  # noqa: E402
from pydantic import ValidationError  # noqa: E402

import outline_schema as _os  # noqa: E402


# ── Helpers ──────────────────────────────────────────────────────────


def _slide_count_expanded(outline: _os.Outline) -> int:
    """Slide entries expanded by build steps — what the deck actually shows."""
    return sum(max(len(s.builds), 1) for s in outline.slides)


def _all_script_lines(outline: _os.Outline) -> list[tuple[str, str]]:
    """Yield (location, line_text) for every dialogue line in slides + interludes."""
    out: list[tuple[str, str]] = []
    for s in outline.slides:
        for item in s.script:
            if item.line is not None:
                out.append((f"slide {s.n}", item.line))
    for il in outline.interludes:
        for item in il.script:
            if item.line is not None:
                out.append((f"interlude {il.id}", item.line))
    return out


def _duration_in_range(duration: float, range_str: str) -> bool:
    """Test whether `duration` falls within a profile `duration_range` string.

    Supports `"N min"` (exact), `"A-B min"` (inclusive range), and
    `"N+ min"` (open-ended upper bound).
    """
    if not range_str:
        return False
    s = range_str.strip().lower().replace("min", "").strip()
    # "N+" form
    if s.endswith("+"):
        try:
            lo = float(s[:-1].strip())
            return duration >= lo
        except ValueError:
            return False
    # "A-B" form
    if "-" in s:
        try:
            lo, hi = (float(x.strip()) for x in s.split("-", 1))
            return lo <= duration <= hi
        except ValueError:
            return False
    # "N" form
    try:
        return abs(float(s) - duration) < 0.5
    except ValueError:
        return False


def _slide_text_blob(slide: _os.Slide) -> str:
    """All on-slide text concatenated — visual + text_overlay (NOT script)."""
    parts: list[str] = []
    if slide.visual:
        parts.append(slide.visual)
    if slide.text_overlay:
        parts.append(slide.text_overlay)
    return " | ".join(parts)


# ── Checks ───────────────────────────────────────────────────────────


def check_slide_budget(outline: _os.Outline, profile: dict) -> tuple[str, str]:
    """Slide count vs profile threshold for the talk duration.

    Matches the budget entry whose `duration_minutes` (or `duration_min`)
    is closest to the talk's duration, per phase4-guardrails.md's
    "Match the talk's duration to the closest budget entry" rule.
    """
    expanded = _slide_count_expanded(outline)
    duration = outline.talk.duration_min
    budgets = profile.get("guardrail_sources", {}).get("slide_budgets", [])

    max_slides: int | None = None
    best_diff: float | None = None
    for b in budgets:
        dur_key = b.get("duration_minutes") or b.get("duration_min")
        if dur_key is None:
            continue
        diff = abs(dur_key - duration)
        if best_diff is None or diff < best_diff:
            best_diff = diff
            max_slides = b.get("max_slides")
    if max_slides is None:
        max_slides = int(duration * 1.5)  # fallback default

    if expanded > max_slides:
        return "FAIL", f"{expanded}/{max_slides} for {duration:g}-min slot"
    if max_slides - expanded <= max_slides * 0.05:
        return "WARN", f"{expanded}/{max_slides} for {duration:g}-min slot (near limit)"
    return "PASS", f"{expanded}/{max_slides} for {duration:g}-min slot"


def check_act1_ratio(outline: _os.Outline, profile: dict) -> tuple[str, str]:
    """Act 1 minute-ratio vs profile limit.

    Act 1 = the chapter(s) framing the problem before the thesis preview.
    Heuristic: chapters preceding the chapter that contains the big_idea
    slide are Act 1; if no big_idea is located among chapters, fall back
    to the first chapter only.
    """
    duration = outline.talk.duration_min
    if duration <= 0:
        return "PASS", "no duration"

    # Find chapter containing the big_idea slide
    big_idea_slide = next((s for s in outline.slides if s.big_idea), None)
    big_idea_chapter = big_idea_slide.chapter if big_idea_slide else None

    act1_chapters = []
    for c in outline.chapters:
        if c.id == big_idea_chapter:
            break
        act1_chapters.append(c)
    if not act1_chapters and outline.chapters:
        act1_chapters = [outline.chapters[0]]

    act1_min = sum(c.target_min for c in act1_chapters)
    ratio = (act1_min / duration) * 100

    limits = profile.get("guardrail_sources", {}).get("act1_ratio_limits", [])
    max_pct: float = 45
    # Pick the entry whose declared duration range covers the talk's
    # duration. Supports the schema's documented range forms (see
    # vault-profile/references/speaker-profile-schema.md):
    #   "30 min"        → exact
    #   "20-30 min"     → inclusive range
    #   "60+ min"       → open-ended upper
    matched = False
    for lim in limits:
        if _duration_in_range(duration, lim.get("duration_range") or ""):
            max_pct = lim.get("max_percentage") or lim.get("max_percent", 45)
            matched = True
            break
    if not matched and limits:
        first = limits[0]
        max_pct = first.get("max_percentage") or first.get("max_percent", 45)

    names = ", ".join(c.title for c in act1_chapters)
    detail = (
        f"{ratio:.1f}% (limit: {max_pct}%) — Act 1 = {names} "
        f"({act1_min:g}/{duration:g} min)"
    )
    if ratio > max_pct:
        return "FAIL", detail
    if max_pct - ratio <= 5:
        return "WARN", detail + " — near limit"
    return "PASS", detail


def check_closing(outline: _os.Outline) -> tuple[str, str]:
    """Last chapter should have summary + CTA + social signals."""
    if not outline.chapters:
        return "FAIL", "no chapters"
    closing = outline.chapters[-1]
    closing_slide_ns = [s.n for s in outline.slides if s.chapter == closing.id]
    closing_slides = [s for s in outline.slides if s.n in closing_slide_ns]

    blob = " ".join(
        _slide_text_blob(s) + " " + " ".join(
            item.line or "" for item in s.script if item.line
        )
        for s in closing_slides
    ).lower()

    has_summary = any(t in blob for t in ("summary", "takeaway", "recap", "cheat sheet"))
    has_cta = any(t in blob for t in (
        "call to action", "cta", "action item", "this week",
        "doer", "monday", "next step",
    ))
    # "thank" alone is insufficient — the documented minimum close requires
    # a real social/link signal (handle, shownotes URL, QR). Tokens chosen
    # so a bare "Thanks!" doesn't pass the social check.
    has_social = any(t in blob for t in (
        "shownotes", "social", "qr", "@",
    )) or ("thank" in blob and any(t in blob for t in ("@", "http", ".com", ".dev", ".io", "/")))

    parts = [
        ("summary", has_summary),
        ("CTA", has_cta),
        ("social", has_social),
    ]
    missing = [name for name, present in parts if not present]
    summary_str = " ".join(f"{name}={'y' if present else 'n'}" for name, present in parts)
    if missing:
        return "FAIL", f"{summary_str} — missing: {', '.join(missing)}"
    return "PASS", summary_str


def check_cut_lines(outline: _os.Outline, profile: dict) -> tuple[str, str]:
    """Talks shorter than the speaker's default need cuttable content to flex.

    Per phase4-guardrails.md §8: the check is conditional on the speaker
    profile's `rhetoric_defaults.modular_design` flag. Speakers who opt
    out of modular_design don't get penalized for inflexible decks.
    """
    modular = (
        profile.get("rhetoric_defaults", {}).get("modular_design") is True
    )
    cuttable_chapters = [c for c in outline.chapters if c.cuttable]
    cuttable_slides = [s for s in outline.slides if s.cuttable]
    cuttable_min = sum(c.target_min for c in cuttable_chapters)

    if not cuttable_chapters and not cuttable_slides:
        if not modular:
            return "PASS", "modular_design disabled in profile — cut lines not required"
        return "FAIL", (
            "no `cuttable: true` markers on any chapter or slide — talk "
            "cannot compress for shorter slots (profile has modular_design enabled)"
        )
    return "PASS", (
        f"{cuttable_min:g} min of cuttable chapters "
        f"({[c.id for c in cuttable_chapters]}); "
        f"{len(cuttable_slides)} cuttable slides"
    )


def check_data_attribution(outline: _os.Outline) -> tuple[str, str]:
    """Heuristic: slides with percentages / large numbers should mention a source.

    Numeric-claim patterns include percentages, currency, large bare
    numbers (4+ digits), shorthand magnitudes (11M, 2.5K, 3 million),
    and spelled-out magnitudes (million/billion/thousand). The source
    heuristic deliberately excludes bare `report` — phrases like "report
    alert fatigue" make unsourced claims pass attribution. A claim with
    a sourced report needs an attribution token like `source`, `via`,
    a year citation `(2024)`, etc.
    """
    pct_re = re.compile(
        r"""
        \d{1,3}\s*%                # percentage
        | \$\s*\d                  # currency
        | \d{4,}\b                 # bare 4+ digit number
        | \b\d+(?:\.\d+)?\s*(?:k|m|b)\b   # 2.5K, 11M, 1.2B
        | \b\d+(?:\.\d+)?\s+(?:million|billion|thousand|trillion)\b
        """,
        re.IGNORECASE | re.VERBOSE,
    )
    source_re = re.compile(
        r"\bsource\b|\bcitation\b|\bref\b|\bvia\b|\(20\d{2}\)|\bsurvey\b|"
        r"\bstudy\b|\baccording to\b|https?://",
        re.IGNORECASE,
    )
    missing: list[int] = []
    for s in outline.slides:
        blob = _slide_text_blob(s)
        if pct_re.search(blob) and not source_re.search(blob):
            missing.append(s.n)
    if missing:
        return "FAIL", (
            f"{len(missing)} slide(s) with numeric claims and no source mention: "
            f"slides {missing}"
        )
    return "PASS", "all numeric-claim slides reference a source"


def check_profanity(outline: _os.Outline, profile: dict) -> tuple[str, str]:
    """Scan dialogue + on-slide text for profanity vs profile register."""
    register = (
        outline.talk.profanity_register
        or profile.get("rhetoric_defaults", {}).get("profanity_calibration")
        or "moderate"
    )
    words = ["damn", "hell", "shit", "fuck", "fucking", "ass", "crap", "bullshit"]

    on_slide_hits: list[str] = []
    spoken_hits: list[str] = []

    for s in outline.slides:
        blob = _slide_text_blob(s).lower()
        for w in words:
            if re.search(rf"\b{re.escape(w)}\b", blob):
                on_slide_hits.append(f'"{w}" on slide {s.n}')

    for location, line in _all_script_lines(outline):
        lower = line.lower()
        for w in words:
            if re.search(rf"\b{re.escape(w)}\b", lower):
                spoken_hits.append(f'"{w}" in {location}')

    if "none" in register.lower() and (on_slide_hits or spoken_hits):
        return "FAIL", (
            f"register '{register}' — on-slide: {len(on_slide_hits)}; "
            f"spoken: {len(spoken_hits)}"
        )
    if on_slide_hits and "never on slide" in register.lower():
        return "FAIL", (
            f"register '{register}' — on-slide hits forbidden: {on_slide_hits[:5]}"
        )
    if on_slide_hits:
        return "WARN", (
            f"register '{register}' — {len(on_slide_hits)} on-slide instances "
            f"(limits deck reuse): {on_slide_hits[:5]}"
        )
    return "PASS", f"register '{register}' applied; {len(spoken_hits)} spoken, 0 on-slide"


def check_branding(outline: _os.Outline, profile: dict) -> tuple[str, str]:
    """Footer must include every required element from the speaker profile.

    Profile's `design_rules.footer.elements` is the speaker's footer
    checklist (handle, conference hashtag, shownotes URL, etc.). Each
    element token should appear in at least one slide's text overlay or
    visual — usually the footer rendered into every slide's overlay.
    """
    footer = profile.get("design_rules", {}).get("footer") or {}
    elements = footer.get("elements") or []
    if not elements:
        return "WARN", "speaker profile has no design_rules.footer.elements — skipping"

    # Build one big text-blob from all slide overlays/visuals and search
    # for each footer element as a literal substring (case-insensitive).
    blob = " ".join(
        ((s.text_overlay or "") + " " + (s.visual or ""))
        for s in outline.slides
    ).lower()

    missing: list[str] = []
    for elem in elements:
        elem_l = (elem or "").lower().strip()
        if not elem_l:
            continue
        # Strip template placeholders like {conference}/{topic} before matching
        elem_l = re.sub(r"\{[^}]+\}", "", elem_l).strip()
        if not elem_l:
            continue
        if elem_l not in blob:
            missing.append(elem)
    if missing:
        return "FAIL", (
            f"required footer elements not detected in any slide overlay: "
            f"{missing}"
        )
    return "PASS", f"all required footer elements present ({len(elements)})"


# ── Main ─────────────────────────────────────────────────────────────


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(
            f"Usage: {argv[0]} <outline.yaml> <speaker-profile.json>",
            file=sys.stderr,
        )
        return 2

    outline_path, profile_path = argv[1], argv[2]
    try:
        outline = _os.load_outline(outline_path)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        print(f"failed to load {outline_path}: {exc}", file=sys.stderr)
        return 1

    try:
        with open(profile_path) as f:
            profile = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"failed to load {profile_path}: {exc}", file=sys.stderr)
        return 1

    print(f"GUARDRAIL CHECK — {outline.talk.title}")
    print("=" * 60)

    checks = [
        ("Slide budget", check_slide_budget(outline, profile)),
        ("Act 1 ratio", check_act1_ratio(outline, profile)),
        ("Branding", check_branding(outline, profile)),
        ("Profanity", check_profanity(outline, profile)),
        ("Data attribution", check_data_attribution(outline)),
        ("Closing", check_closing(outline)),
        ("Cut lines", check_cut_lines(outline, profile)),
    ]

    for name, (label, detail) in checks:
        print(f"[{label}] {name}: {detail}")

    print("=" * 60)
    print(
        "Structural taxonomy checks (PUNCH, big-idea, sparkline, master-story, "
        "callbacks, etc.) → run scripts/check-rhetorical.py",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
