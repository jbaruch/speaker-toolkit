# Presentation Creator — Guardrails

Phase 4 runs two complementary checkers against `outline.yaml`:

| Script | Surface | Output |
|--------|---------|--------|
| `scripts/check-rhetorical.py outline.yaml` | Closed pattern taxonomy — opening PUNCH, big-idea singleton, thesis preview/payoff, sparkline elements, master-story threading, callback ledger, inoculation count, progressive-list contiguity, running gags, duration accounting | `rhetorical-review.md` |
| `scripts/guardrail-check.py outline.yaml <speaker-profile.json>` | Profile-aware rules — slide budget per profile, Act 1 ratio limits, branding, profanity, anti-pattern frequency, illustration coverage | stdout report |

The two scripts are independent — run both. `check-rhetorical.py` needs no
profile and emits a deterministic report regardless of the speaker. `guardrail-check.py`
fuses outline data with profile thresholds and venue context.

This file defines the guardrail **check structure** — what each check covers,
how it's wired to schema fields, and how results are reported.

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

**Always check this.** Read `rhetoric_defaults.default_duration_minutes` and
`rhetoric_defaults.modular_design` from the speaker profile.

In `outline.yaml`, cuttable chapters and slides carry `cuttable: true`. The
guardrail counts cuttable minutes and verifies the talk can compress to
shorter slots.

### Check

```
[PASS/FAIL] Cut lines: {cuttable_min} min of cuttable content
            (cuttable chapters: {ids}; cuttable slides: {ns})
```

FAIL if no chapter or slide carries `cuttable: true` and the talk duration
is shorter than the speaker's default (the talk can't compress).

---

## 9. Anti-Pattern Flags

This check has **two layers**: speaker-specific recurring issues from the vault, and
taxonomy-based antipattern scanning from the Presentation Patterns reference.

### 9A. Speaker-Specific Recurring Issues

Read `guardrail_sources.recurring_issues[]` from the speaker profile. Each entry
describes a known weakness and its specific guardrail check.

For each `recurring_issues` entry, run the check described in its `guardrail` field
and report at the severity level in its `severity` field.

Common anti-patterns (may or may not apply to a given speaker):
- **Meme accretion**: If Act 1 has more than 60% meme/image-only slides, flag it
- **Theoretical framing delay**: If an opening framework section exceeds 10% of time, flag it
- **Missing anti-sell beat**: If commercial intent + applicable mode but no anti-sell
- **Edgy humor overshoot**: Flag culturally sensitive humor targets

### 9B. Presentation Patterns Taxonomy Scan

Read [references/patterns/_index.md](patterns/_index.md) (Phase 4 section of the phase-grouped lookup table)
and `profile → pattern_profile.antipattern_frequency` if available.

**Speaker-specific antipatterns** — scan `pattern_profile.antipattern_frequency` for
patterns with `severity: "recurring"`. These are flagged as `[RECURRING]` with the
speaker's historical frequency and trend.

**Contextual antipatterns** — scan the outline against ALL antipatterns from the taxonomy.
For each match, read the individual pattern file for detection heuristics and scoring
criteria. These are flagged as `[CONTEXTUAL]` (new detection, not historically tracked).

Contextual detection rules:
- **Bullet-Riddled Corpse** — flag slides with 5+ bullet points or complete sentences
- **Ant Fonts** — flag text descriptions suggesting small or cramped content
- **Cookie Cutter** — flag ideas awkwardly split across slide boundaries
- **Shortchanged** — flag if duration is shorter than speaker's default with no cut lines
- **Dual-Headed Monster** — flag if co-presented with no handoff protocol
- **Slideuments** — flag if outline suggests dual-purpose slides (handout + presentation)
- **Borrowed Shoes** — flag if adapting another speaker's materials
- **Dead Demo** — flag demos without clear narrative purpose
- **Alienating Artifact** — flag humor/references that could exclude audience segments
- **Tower of Babble** — flag unexplained jargon for the stated audience level

Report format:
```
[RECURRING] Shortchanged (8/24, decreasing) — plan cut lines for the 20-min slot
[RECURRING] Meme accretion (5/24, stable) — Act 1 meme ratio at 55%
[CONTEXTUAL] Bullet-Riddled Corpse — slides 14, 22 have 6+ bullet points
[CONTEXTUAL] Dual-Headed Monster — co-presented talk, handoff points not defined
```

---

## 10. Illustration Coverage

**Only runs when the outline includes an Illustration Style Anchor section.**
When no illustration strategy exists, output `[SKIP] Illustrations: no illustration
strategy defined` in the guardrail report and skip all sub-checks below.

### Checks

**Visual coverage ratio** — what percentage of non-EXCEPTION slides have image prompts.
Not every slide needs an illustration (text-only slides, transition slides), but the
ratio should reflect the author's intent for the deck's visual density.

**Format consistency** — every slide has a Format field (`FULL`, `IMG+TXT`, `EXCEPTION`,
or a custom format from the format vocabulary).

**EXCEPTION justification** — every EXCEPTION slide has a reason explaining why it uses
a real asset instead of a generated illustration.

**Style anchor reference** — every image prompt starts with `[STYLE ANCHOR]` (the token
the generation script replaces with the actual anchor text).

**Prompt quality** — no prompts that are just the Illustration description copy-pasted.
The image prompt should be richer and more specific than the human-readable description
(it includes composition details, labeling, specific visual elements).

### Check

```
[PASS/FAIL] Illustration coverage: {N}/{M} illustrated slides have image prompts
[PASS/FAIL] Format tags: {N}/{total} slides have format specified
[WARN] EXCEPTION slides: {N} without justification
[PASS/FAIL] Style anchor reference: {N}/{M} prompts start with [STYLE ANCHOR]
[PASS/WARN] Prompt quality: {N} prompts appear to be copy-paste of description
```

**Build coverage check** — when slides define `- Builds:` sections:

```
[PASS/SKIP] Build coverage: {N} slides have builds defined, {M} build-step images generated
```

SKIP if no slides define builds. PASS if all defined build steps have corresponding
images in `illustrations/builds/`. Report missing steps if any.

**Prompt quality anti-patterns** — flag prompts likely to produce poor results:

```
[WARN] Prompt anti-patterns: {N} prompts with potential issues
```

Detection rules (check all edit/fix/generation prompts):
- **Missing preservation instructions:** Flag edit prompts that remove or change content
  without explicit "keep [X]" instructions. Gemini removes elements it was not asked to
  remove — a prompt saying "remove the label" without "keep the soldiers, keep the
  border" will often damage unrelated elements.
- **Missing safety suffixes:** Flag edit prompts missing "DO NOT add any new elements"
  (Gemini aggressively adds unwanted decorative elements during edits) and/or "let
  background continue naturally" (Gemini fills erased areas with flat-colored patches).
- **Simplified style anchor:** Flag prompts that use a shortened or paraphrased version
  of the style anchor instead of the full text. The full specificity IS what produces
  the distinctive style — a prompt using "military style, pen and ink" instead of the
  full multi-line anchor will produce generic results. Heuristic: if a generation
  prompt's style description is significantly shorter than the anchor, flag it.
- **Content addition via edit:** Flag prompts that attempt to ADD new visual content
  (new characters, new objects, new text) using image editing. Content additions should
  use regeneration from the full prompt, not editing — editing strips the style when
  the model draws new elements, producing style mismatches.
- **PIL/programmatic manipulation:** Flag any use of PIL, Pillow, ImageMagick, or
  programmatic image manipulation for creating builds or fixing illustrations. These
  produce visible texture mismatches. Always use the model's native image editing.

---

## 11. Murder-Your-Darlings Filter Pass

**Always runs.** This is the convergent-thinking cut pass that asks of every section in the outline: *does this directly support the Big Idea?* Per the "Murder Your Darlings — The Pre-Delivery Cut Pass" subsection in `patterns/prepare/crucible.md`.

### Check

For each top-level section in the outline:
- Identify which Big Idea component the section serves (POV reinforcement / stakes elaboration / proof / call-to-action setup / new-bliss preparation / inoculation).
- If you cannot name the component a section serves, the section is a candidate for the cut — flag it.
- Especially scrutinize sections marked `[CALLBACK: master-story reference]`, sections labeled with a personal anecdote that doesn't tie back to the thesis, and sections containing data-rich material that took significant effort to gather. These are the most-loved-by-author and most-likely-to-be-darlings.
- The cut is rarely "remove the section entirely" — usually it's "compress to one beat" or "move into the speaker notes for reference."

```
[PASS/WARN/FAIL] Big Idea alignment: {N}/{total} sections traceable to Big Idea components
[WARN] Candidate darlings: {section names} — flagged for review
```

The pass produces *flags*, not automatic deletions. The author makes the actual cut decisions; the guardrail surfaces the candidates.

## 12. Emotion-Balance Check

**Always runs.** Per `patterns/build/sparkline.md` (the "Three Contrast Types" subsection) and Duarte's *kairos* principle, the analytical/emotional ratio of the outline must match the audience type.

### Check

Categorize each content section as **analytical** (data, logic, argument, technical detail) or **emotional** (story, image, anecdote, evocative language). Compare the ratio against the audience profile from the spec:

- **Analytical audience** (scientists, engineers, accountants, board members): aim for 70–80% analytical content, 20–30% emotional content. Less emotion than this strips persuasive power; more reads as manipulation.
- **Broad audience** (general professional, mixed-discipline conference): aim for 50–60% analytical, 40–50% emotional.
- **Emotionally-charged context** (advocacy, fundraising, cause-driven keynote): can run 30–40% analytical, 60–70% emotional. Not less analytical than 30% even here — emotion without proof loses credibility.

```
[PASS/WARN] Emotion balance: {N}% analytical / {M}% emotional vs. {target}% target for {audience type}
```

WARN if the ratio is more than 15 percentage points off the target in either direction. The check is descriptive, not prescriptive — the author decides whether the imbalance is intentional (some talks deliberately skew). Surface the imbalance so it's a conscious choice.

## 13. Screening with Critics — Pre-Lock Gate

**Runs before final spec lock for high-stakes talks** (keynotes, sales pitches, fundraising presentations, executive briefings). Per the "Screening with Critics — Beyond Copyediting" subsection in `patterns/build/peer-review.md`.

### Check

Has the author scheduled (or executed) a formal screening session with the following properties?

- 3× the duration of the presentation (60-min talk → 3-hour screening)
- Screeners selected from outside the speaker's organization (or, if internal, explicitly free of the six dysfunctional review patterns: Conceited Captain / Political Paranoia / Message Magic / Vacuum Visionary / Lackey Leader / Customer Cold-Shoulder)
- Screeners match the target audience profile (industry, role, knowledge level)
- Each screener has access to slides + speaker notes for line-level critique
- Output: structural critiques + language critiques + resistance discoveries (which feed back into Phase 3 inoculation moves)

```
[PASS/WARN/SKIP] Screening: {scheduled / completed / not applicable for this stakes level}
```

SKIP for low-stakes talks (internal demos, small-group presentations, tutorial sessions). For everything else, WARN if no screening is scheduled or completed.

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
[RECURRING/CONTEXTUAL] Presentation Patterns: {taxonomy-based antipattern flags}
[PASS/FAIL/SKIP] Illustrations: {coverage ratio} | {format tags} | {prompt quality}
[PASS/SKIP] Builds: {N} defined, {M} images generated
[WARN] Prompt anti-patterns: {N} issues found
[PASS/WARN/FAIL] Big Idea alignment: {N}/{total} sections traceable to Big Idea
[PASS/WARN] Emotion balance: {N}% analytical / {M}% emotional vs. {target}%
[PASS/WARN/SKIP] Screening with critics: {scheduled / completed / not applicable}
================================================
```

The Illustrations, Builds, and Prompt anti-patterns lines show `[SKIP]` when no
illustration strategy is defined.
