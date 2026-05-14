"""check-rhetorical.py — structural gap-check over the closed pattern taxonomy.

Walks the validated Outline and reports whether the talk has the
structural elements its declared architecture requires. Output is
deterministic (script territory per rules/script-delegation.md) — every
check returns PASS, FLAG, or N/A with a short reason. The agent can
synthesize commentary on top of this report; the report itself is
purely mechanical.

Usage:
    check-rhetorical.py <outline.yaml>              # report mode (exit 0)
    check-rhetorical.py <outline.yaml> --strict     # exit 1 if any FLAG

Output: rhetorical-review.md content to stdout.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import yaml  # noqa: E402
from pydantic import ValidationError  # noqa: E402

import outline_schema as _os  # noqa: E402


@dataclass
class CheckResult:
    name: str
    status: str  # PASS | FLAG | N/A | INFO
    detail: str


def _all_applied_patterns(outline: _os.Outline) -> list[tuple[str, _os.AppliedPattern]]:
    """Walk every applied_pattern with a location label."""
    out: list[tuple[str, _os.AppliedPattern]] = []
    for p in outline.talk.applied_patterns:
        out.append(("talk", p))
    for s in outline.slides:
        for p in s.applied_patterns:
            out.append((f"slide {s.n}", p))
    for il in outline.interludes:
        for p in il.applied_patterns:
            out.append((f"interlude {il.id}", p))
    return out


# ── Individual checks ────────────────────────────────────────────────


def _check_opening_punch(outline: _os.Outline) -> CheckResult:
    """At least one slide in the first 10% of the deck declares opening-punch
    with at least one flavor."""
    cutoff = max(1, int(0.1 * len(outline.slides)) + 1)
    opening_slides = outline.slides[:cutoff]
    flavored: list[tuple[int, list[str]]] = []
    flavorless: list[int] = []
    for s in opening_slides:
        for p in s.applied_patterns:
            if p.id == "opening-punch":
                flavors = [f.value for f in (p.flavors or [])]
                if flavors:
                    flavored.append((s.n, flavors))
                else:
                    flavorless.append(s.n)
    if not flavored:
        if flavorless:
            return CheckResult(
                "Opening PUNCH",
                "FLAG",
                f"`opening-punch` declared on slide(s) {flavorless} but with "
                "no `flavors:` set — pick at least one of "
                "{personal, unexpected, novel, challenging, humorous}.",
            )
        return CheckResult(
            "Opening PUNCH",
            "FLAG",
            f"No `opening-punch` declared in the first {cutoff} slides. "
            "Audiences grant ~2 min before forming a verdict — the opening "
            "needs at least one PUNCH flavor.",
        )
    where = "; ".join(
        f"slide {n}: flavors={flavors}" for n, flavors in flavored
    )
    return CheckResult("Opening PUNCH", "PASS", where)


def _check_big_idea(outline: _os.Outline) -> CheckResult:
    """Exactly one slide carries big_idea=true (already enforced by the
    schema validator — this report-side check surfaces *where* it lives)."""
    marked = [s for s in outline.slides if s.big_idea]
    if len(marked) != 1:
        return CheckResult(
            "Big Idea singleton",
            "FLAG",
            f"Found {len(marked)} big_idea slides "
            f"(schema requires exactly 1) — this should have been caught by "
            "schema validation.",
        )
    slide = marked[0]
    # Look for the actual text on the call-to-adventure pattern, if present
    big_idea_text = None
    for p in slide.applied_patterns:
        if p.id == "call-to-adventure" and p.big_idea_text:
            big_idea_text = p.big_idea_text
            break
    detail = f"slide {slide.n}: \"{slide.title}\""
    if big_idea_text:
        detail += f" — text: {big_idea_text!r}"
    return CheckResult("Big Idea singleton", "PASS", detail)


def _check_thesis_ordering(outline: _os.Outline) -> CheckResult:
    """thesis: preview must come before thesis: payoff (when both present)."""
    previews = [s.n for s in outline.slides if s.thesis == "preview"]
    payoffs = [s.n for s in outline.slides if s.thesis == "payoff"]
    if not previews and not payoffs:
        return CheckResult(
            "Thesis preview/payoff",
            "N/A",
            "No thesis preview or payoff declared.",
        )
    if previews and not payoffs:
        return CheckResult(
            "Thesis preview/payoff",
            "FLAG",
            f"Preview at slide {previews} but no payoff declared.",
        )
    if payoffs and not previews:
        return CheckResult(
            "Thesis preview/payoff",
            "FLAG",
            f"Payoff at slide {payoffs} but no preview declared.",
        )
    if max(previews) >= min(payoffs):
        return CheckResult(
            "Thesis preview/payoff",
            "FLAG",
            f"Preview slides {previews} not strictly before payoff "
            f"slides {payoffs}.",
        )
    return CheckResult(
        "Thesis preview/payoff",
        "PASS",
        f"preview slide {previews[0]} → payoff slide {payoffs[0]}",
    )


def _check_sparkline_requirements(outline: _os.Outline) -> list[CheckResult]:
    """When architecture == sparkline, the talk must declare:
    - exactly one call-to-adventure
    - exactly one call-to-action
    - exactly one new-bliss
    - at least one star-moment
    """
    if outline.talk.architecture != "sparkline":
        return [CheckResult(
            "Sparkline elements",
            "N/A",
            f"Architecture is `{outline.talk.architecture}`, not sparkline.",
        )]
    counts: dict[str, list[str]] = {
        "call-to-adventure": [],
        "call-to-action": [],
        "new-bliss": [],
        "star-moment": [],
    }
    for location, p in _all_applied_patterns(outline):
        if p.id in counts:
            counts[p.id].append(location)
    out: list[CheckResult] = []
    for pid, expected_min, expected_max, label in [
        ("call-to-adventure", 1, 1, "Call to Adventure"),
        ("call-to-action", 1, 1, "Call to Action"),
        ("new-bliss", 1, 1, "New Bliss"),
        ("star-moment", 1, None, "S.T.A.R. moments"),
    ]:
        n = len(counts[pid])
        if n < expected_min:
            out.append(CheckResult(
                label,
                "FLAG",
                f"Sparkline requires ≥{expected_min}, found {n}.",
            ))
        elif expected_max is not None and n > expected_max:
            out.append(CheckResult(
                label,
                "FLAG",
                f"Sparkline requires exactly {expected_max}, found {n} at "
                f"{counts[pid]}.",
            ))
        else:
            out.append(CheckResult(
                label,
                "PASS",
                f"{n} declared at {counts[pid]}",
            ))
    return out


def _check_master_story_threading(outline: _os.Outline) -> CheckResult:
    """Each master-story id must have `introduce` before any `recall-N`,
    and recall indexes should appear in increasing order."""
    threads: dict[str, list[tuple[int, str]]] = {}
    for s in outline.slides:
        for p in s.applied_patterns:
            if p.id == "master-story" and p.story_id:
                threads.setdefault(p.story_id, []).append(
                    (s.n, p.beat.value if p.beat else "?"),
                )
    if not threads:
        return CheckResult(
            "Master story threading",
            "N/A",
            "No master-story patterns declared.",
        )
    problems: list[str] = []
    summary: list[str] = []
    for story, beats in threads.items():
        beats.sort(key=lambda x: x[0])
        beat_seq = " → ".join(f"{b}@slide {n}" for n, b in beats)
        summary.append(f"`{story}`: {beat_seq}")
        kinds = [b for _, b in beats]
        if "introduce" not in kinds:
            problems.append(f"`{story}` missing `introduce` beat")
            continue
        intro_idx = kinds.index("introduce")
        if intro_idx != 0:
            problems.append(
                f"`{story}` introduce is not the first beat (kinds={kinds})",
            )
        recalls = [k for k in kinds if k.startswith("recall-")]
        if recalls != sorted(recalls):
            problems.append(
                f"`{story}` recall beats out of order: {recalls}",
            )
    if problems:
        return CheckResult(
            "Master story threading",
            "FLAG",
            "; ".join(problems) + ". Threads: " + " | ".join(summary),
        )
    return CheckResult(
        "Master story threading",
        "PASS",
        " | ".join(summary),
    )


def _check_inoculation_count(outline: _os.Outline) -> CheckResult:
    """phase3-content.md: inoculations should be ≤3 per talk; reserved
    for objections that would derail the room."""
    count = 0
    where: list[str] = []
    for location, p in _all_applied_patterns(outline):
        if p.id == "inoculation":
            count += 1
            vector = p.resistance_vector.value if p.resistance_vector else "?"
            where.append(f"{location} ({vector})")
    if count == 0:
        return CheckResult(
            "Inoculation count",
            "INFO",
            "No inoculation beats declared. Persuasive talks usually want "
            "1–3 to preempt the strongest derailing objection.",
        )
    if count > 3:
        return CheckResult(
            "Inoculation count",
            "FLAG",
            f"{count} inoculations (recommended ≤3 — overuse makes the talk "
            f"feel defensive): {where}",
        )
    return CheckResult(
        "Inoculation count",
        "PASS",
        f"{count}/3: {where}",
    )


def _check_progressive_lists(outline: _os.Outline) -> CheckResult:
    """Each progressive_list id's item indexes should be contiguous starting at 1."""
    lists: dict[str, list[int]] = {}
    for s in outline.slides:
        for pl in s.progressive_lists:
            lists.setdefault(pl.id, []).append(pl.item_index)
    if not lists:
        return CheckResult(
            "Progressive lists",
            "N/A",
            "No progressive lists declared.",
        )
    problems: list[str] = []
    summary: list[str] = []
    for lid, idxs in lists.items():
        idxs.sort()
        summary.append(f"`{lid}` items {idxs}")
        if idxs != list(range(1, len(idxs) + 1)):
            problems.append(f"`{lid}` indexes not contiguous from 1: {idxs}")
    if problems:
        return CheckResult(
            "Progressive lists",
            "FLAG",
            "; ".join(problems),
        )
    return CheckResult(
        "Progressive lists",
        "PASS",
        " | ".join(summary),
    )


def _check_running_gags(outline: _os.Outline) -> CheckResult:
    """A running gag should appear ≥2 times (otherwise it's a one-shot, not a gag)."""
    gags: dict[str, list[int]] = {}
    for s in outline.slides:
        for rg in s.running_gags:
            gags.setdefault(rg.id, []).append(rg.appearance_index)
    if not gags:
        return CheckResult(
            "Running gags",
            "N/A",
            "No running gags declared.",
        )
    problems: list[str] = []
    summary: list[str] = []
    for gid, idxs in gags.items():
        idxs.sort()
        summary.append(f"`{gid}` appearances {idxs}")
        if len(idxs) < 2:
            problems.append(
                f"`{gid}` only has {len(idxs)} appearance "
                f"— gags need ≥2 escalations",
            )
        if idxs != list(range(1, len(idxs) + 1)):
            problems.append(f"`{gid}` indexes not contiguous from 1: {idxs}")
    if problems:
        return CheckResult(
            "Running gags",
            "FLAG",
            "; ".join(problems),
        )
    return CheckResult(
        "Running gags",
        "PASS",
        " | ".join(summary),
    )


def _check_duration_accounting(outline: _os.Outline) -> CheckResult:
    """Chapter target_min should sum to roughly the talk duration_min."""
    chapter_sum = sum(c.target_min for c in outline.chapters)
    talk_dur = outline.talk.duration_min
    diff = chapter_sum - talk_dur
    pct = abs(diff) / talk_dur * 100 if talk_dur else 0
    detail = (
        f"chapter sum {chapter_sum:g} min vs talk duration {talk_dur:g} min "
        f"(diff {diff:+.1f} min, {pct:.0f}%)"
    )
    if pct > 20:
        return CheckResult(
            "Duration accounting",
            "FLAG",
            detail + " — >20% off; Q&A budget aside, this needs reconciling.",
        )
    return CheckResult("Duration accounting", "PASS", detail)


def _check_callback_ledger(outline: _os.Outline) -> CheckResult:
    """Already enforced by schema validator; this surfaces the chains."""
    chains: dict[str, dict[str, list[str]]] = {}
    for s in outline.slides:
        for cb in s.callbacks:
            entry = chains.setdefault(cb.id, {"plant": [], "pay": []})
            entry[cb.kind].append(f"slide {s.n}")
    for il in outline.interludes:
        for cb in il.callbacks:
            entry = chains.setdefault(cb.id, {"plant": [], "pay": []})
            entry[cb.kind].append(f"interlude {il.id}")
    if not chains:
        return CheckResult(
            "Callback chains",
            "N/A",
            "No callbacks declared.",
        )
    summary = " | ".join(
        f"`{cid}`: plant {e['plant']} → pay {e['pay']}"
        for cid, e in chains.items()
    )
    return CheckResult("Callback chains", "PASS", summary)


# ── Report rendering ─────────────────────────────────────────────────


_STATUS_BADGE = {
    "PASS": "✅ **PASS**",
    "FLAG": "⚠️  **FLAG**",
    "N/A": "— *N/A*",
    "INFO": "ℹ️  *INFO*",
}


def render(outline: _os.Outline) -> tuple[str, int]:
    """Render rhetorical-review.md and return (content, flag_count)."""
    checks: list[CheckResult] = [
        _check_opening_punch(outline),
        _check_big_idea(outline),
        _check_thesis_ordering(outline),
        *_check_sparkline_requirements(outline),
        _check_master_story_threading(outline),
        _check_inoculation_count(outline),
        _check_progressive_lists(outline),
        _check_running_gags(outline),
        _check_callback_ledger(outline),
        _check_duration_accounting(outline),
    ]
    flag_count = sum(1 for c in checks if c.status == "FLAG")

    lines: list[str] = []
    lines.append(f"# {outline.talk.title} — Rhetorical Review")
    lines.append("")
    lines.append(
        f"**Architecture:** `{outline.talk.architecture}` · "
        f"**{len(outline.slides)} slides** across "
        f"**{len(outline.chapters)} chapters** · "
        f"**{len(outline.interludes)} interludes**",
    )
    lines.append("")
    lines.append(
        "> Mechanical gap-check over the closed pattern taxonomy. Every "
        "row is one structural assertion the talk's architecture either "
        "satisfies (PASS), fails (FLAG), or doesn't apply (N/A). FLAGs "
        "indicate structural gaps — investigate, don't auto-fix.",
    )
    lines.append("")

    if flag_count == 0:
        lines.append(f"## ✅ Summary — no FLAGs ({len(checks)} checks)")
    else:
        lines.append(
            f"## ⚠️ Summary — {flag_count} FLAG"
            f"{'s' if flag_count != 1 else ''} of {len(checks)} checks",
        )
    lines.append("")

    for c in checks:
        badge = _STATUS_BADGE.get(c.status, c.status)
        lines.append(f"### {c.name} — {badge}")
        lines.append("")
        lines.append(c.detail)
        lines.append("")

    # Collapse blank runs
    cleaned: list[str] = []
    prev_blank = False
    for line in lines:
        is_blank = line.strip() == ""
        if is_blank and prev_blank:
            continue
        cleaned.append(line)
        prev_blank = is_blank
    while cleaned and cleaned[-1].strip() == "":
        cleaned.pop()
    cleaned.append("")
    return "\n".join(cleaned), flag_count


def main(argv: list[str]) -> int:
    strict = "--strict" in argv
    args = [a for a in argv[1:] if a != "--strict"]
    if len(args) != 1:
        print(
            "usage: check-rhetorical.py <outline.yaml> [--strict]\n"
            "       prints rhetorical-review.md to stdout\n"
            "       --strict: exit 1 if any FLAG (default: always exit 0)",
            file=sys.stderr,
        )
        return 2
    try:
        outline = _os.load_outline(args[0])
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        print(f"failed to load {args[0]}: {exc}", file=sys.stderr)
        return 1
    content, flag_count = render(outline)
    sys.stdout.write(content)
    if strict and flag_count > 0:
        print(
            f"\n{flag_count} FLAG(s) found — strict mode exit non-zero",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
