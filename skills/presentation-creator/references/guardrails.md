# Presentation Creator — Guardrails

This file defines the guardrail **check structure** — what to check, how to check it,
and how to report results.

**Thresholds and speaker-specific rules come from the vault at runtime:**
- Slide budget tables → `speaker-profile.json` → `guardrail_sources.slide_budgets[]`
- Act 1 ratio limits → `speaker-profile.json` → `guardrail_sources.act1_ratio_limits[]`
- Recurring issues → `speaker-profile.json` → `guardrail_sources.recurring_issues[]`
- Branding checklist → `speaker-profile.json` → `design_rules.footer`
- Profanity rules → `speaker-profile.json` → `rhetoric_defaults`
- Confirmed intents → `speaker-profile.json` → `confirmed_intents[]`

If the speaker profile is not available, fall back to the rhetoric vault summary
Sections 15 (Areas for Improvement) and 16 (Speaker-Confirmed Intent) for prose rules.

Run these checks after Phase 3 delivery and after each Phase 4 revision.

---

## 1. Slide Budget

Read `guardrail_sources.slide_budgets[]` from the speaker profile for the thresholds.
Match the talk's duration to the closest budget entry.

**Progressive-reveal slides count toward the budget.** If you show the same chart
3 times with different bars highlighted, that's 3 slides, not 1. Flag progressive
reveals as budget-expensive and ask if the emphasis is worth the cost.

**Demo-driven talks are the exception.** If the selected mode is demo-driven,
apply a much lower slide count (the live demo IS the content).

### Check

```
[PASS/FAIL] Slide count: {actual}/{budget} for {duration}-minute slot
```

If over budget, suggest specific cuts. Prioritize cutting:
1. Progressive reveals that could be combined into one slide
2. Meme-only slides in Act 1 (meme accretion is a common pattern)
3. Redundant evidence slides (keep the strongest 2-3)

---

## 2. Act 1 Ratio (Problem Section Balance)

Read `guardrail_sources.act1_ratio_limits[]` from the speaker profile for the limits.

### Check

```
[PASS/WARN/FAIL] Act 1 ratio: {act1_slides}/{total_slides} = {percentage}%
                 (limit: {max}% for {duration}-min slot)
```

WARN if within 5% of limit. FAIL if over.

---

## 3. Conference Branding Checklist

Read `design_rules.footer` from the speaker profile for the footer elements.
Generate the checklist dynamically from `footer.elements[]`:

- [ ] Each footer element matches THIS venue
- [ ] Co-presenter element correct (if applicable, per `footer.co_presented_extra`)
- [ ] No stale conference names in slides
- [ ] No stale conference logos
- [ ] Shownotes URL slug matches this talk

### Check

```
[PASS/FAIL] Branding: Footer elements specified for {conference}
[WARN] Branding: Conference hashtag not yet confirmed — flag for author
```

---

## 4. Profanity Audit

Read `rhetoric_defaults.profanity_calibration` and `rhetoric_defaults.on_slide_profanity`
from the speaker profile.

The key rule (common across speakers): **keep profanity verbal-only by default.**
On-slide profanity limits deck reuse across venues.

### Check

```
[PASS/FAIL] Profanity register: {spec_register} applied consistently
[WARN/FAIL] On-slide profanity: {count} instances found — {approved/not approved}
```

If on-slide profanity is present without explicit approval, flag it:
"Slide {N} has baked-in profanity: '{text}'. This limits reuse at corporate/
family-friendly events. Keep it verbal-only, or explicitly approve for this talk?"

---

## 5. Data Attribution

Survey data without visible source attribution creates credibility risk.

### Check every data slide for:

- [ ] Source name visible
- [ ] Citation ID if available
- [ ] No orphaned percentages without context ("84% of developers..." — 84% of what survey?)

```
[PASS/FAIL] Data attribution: {N} data slides checked, {M} missing sources
            Slides needing sources: {list}
```

---

## 6. Time-Sensitive Content

Expired dates, deadlines, and promotional material appear on reused slides.

### Check for:

- [ ] Registration deadlines
- [ ] Early-bird pricing
- [ ] "Coming soon" for things already launched
- [ ] Conference-specific dates
- [ ] Version numbers that may be outdated
- [ ] Cultural references that have expired (memes have a half-life)

```
[PASS/FAIL] Time-sensitive content: {count} items found
            {list with slide numbers and content}
```

---

## 7. Closing Completeness

Even compressed formats need a structured close. Read `rhetoric_defaults.three_part_close`
from the speaker profile for whether the speaker defaults to a full three-part close.

Minimum viable close:
- [ ] Summary: At least 2-3 bullet points crystallizing the argument
- [ ] CTA: At least one specific, actionable next step
- [ ] Social: Speaker handles + shownotes URL

### Check

```
[PASS/FAIL] Closing: {summary present?} | {CTA present?} | {social present?}
[WARN] Closing: Missing {component} — intentional or oversight?
```

---

## 8. Modular Cut Lines

Read `rhetoric_defaults.default_duration_minutes` and `rhetoric_defaults.modular_design`
from the speaker profile. If modular design is enabled, the outline should include
explicit cut lines:

- [ ] `[CUT LINE]` markers for shorter slot adaptation
- [ ] `[EXPAND ZONE]` markers for sections that can grow for longer slots

### Check

```
[PASS/FAIL] Cut lines: {present/missing} for sub-default adaptation
[PASS/FAIL] Expand zones: {present/missing} for longer adaptation
```

---

## 9. Anti-Pattern Flags

Read `guardrail_sources.recurring_issues[]` from the speaker profile. Each entry
describes a known weakness and its specific guardrail check.

For each `recurring_issues` entry, run the check described in its `guardrail` field
and report at the severity level in its `severity` field.

Common anti-patterns (may or may not apply to a given speaker):
- **Meme accretion**: If Act 1 has more than 60% meme/image-only slides, flag it
- **Theoretical framing delay**: If an opening framework section exceeds 10% of time, flag it
- **Missing anti-sell beat**: If commercial intent + applicable mode but no anti-sell
- **Edgy humor overshoot**: Flag culturally sensitive humor targets

---

## Guardrail Summary Template

Use this template after each check:

```
GUARDRAIL CHECK — {talk title} — {date}
================================================
[PASS] Slide budget: {actual}/{max} for {duration}-min slot
[PASS/WARN/FAIL] Act 1 ratio: {%} (limit: {max}%)
[PASS/FAIL] Branding: {status}
[PASS/FAIL] Profanity: {register} applied, {on-slide count} on-slide
[PASS/FAIL] Data attribution: {N} slides checked, {M} issues
[PASS/FAIL] Time-sensitive: {count} items
[PASS/FAIL] Closing: summary={y/n} CTA={y/n} social={y/n}
[PASS/FAIL] Cut lines: {present/missing}
[INFO] Anti-patterns: {any flags from recurring_issues}
================================================
```
