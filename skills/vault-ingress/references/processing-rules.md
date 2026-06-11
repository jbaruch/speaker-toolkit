# Processing Rules

## Language Policy — English Only

All analysis output, rhetoric summary updates, tracking DB entries, and profile data
MUST be written in English regardless of the talk's delivery language. For non-English talks:

- **Verbatim quotes**: ALWAYS write English translation FIRST, then the original in
  parentheses. Never the reverse. Format: `"English text" (оригинальный текст)`.
  Example: `"That's the whole point" (В этом весь смысл)` — NOT
  `"В этом весь смысл" (That's the whole point)`
- **Verbal signatures**: store separately tagged with language code (e.g.,
  `[ru] "получается что"`) — do NOT merge into the main English signature list
- **Slide text**: translate in the analysis, note original language
- **Humor/wordplay**: note when a joke is language-dependent and untranslatable
- Tag the talk entry with `delivery_language` in the tracking DB

## Pattern Taxonomy Migration

If the pattern taxonomy exists (`skills/presentation-creator/references/patterns/_index.md`)
but any talks with status `"processed"` or `"processed_partial"` have no
`pattern_observations` (or `pattern_observations.pattern_ids` is empty), mark them
`"needs-reprocessing"` with `reprocess_reason: "pattern_scoring_added"`. Report:
"N talks need reprocessing for pattern scoring."

## Pattern Tagging Rules

Scan observations against the pattern taxonomy index at
`skills/presentation-creator/references/patterns/_index.md` (path relative to tile root).
Skip patterns marked `observable: false` — these are pre-event logistics and physical
stage behaviors that cannot be detected from transcripts or slides. For each observable
pattern/antipattern, determine if the talk exhibits it (strong/moderate/weak confidence),
record evidence, and compute per-talk pattern score:
count(patterns) − count(antipatterns). Return in the `pattern_observations` field.

## Structured Field Extraction

When the analysis identifies co-presenters, delivery language, or other structured
metadata, populate the corresponding DB fields (`co_presenter`, `delivery_language`,
etc.) — do NOT leave structured data buried only in `rhetoric_notes` free text.

Backfill empty `structured_data` from earlier runs using `rhetoric_notes`.

## Adherence Assessment

`adherence_assessment` measures how consistent a talk is with the speaker's
**established** rhetorical baseline — not whether the talk was good in the
abstract. Adherence is consistency with this speaker's own validated style, which
is why it can only be computed once a baseline exists.

**Gate:** produce an assessment only when 10+ **scored** talks exist — talks with
status `processed`/`processed_partial` that carry a `pattern_score`. The assessment
anchors to `pattern_score` vs. the baseline. An unscored talk cannot be assessed.
Below that, return `""`. The subagent reads the baseline from
Section 15 of `rhetoric-style-summary.md` (signature patterns, recurring
antipatterns, running average pattern score) — see Rhetoric Summary — Improvement
& Adherence Sections below.

**Three checks, in order:**
1. **Pattern adherence** — did the talk deploy the speaker's signature patterns
   and avoid their recurring antipatterns? Underuse counts here too: skipping
   signature patterns or a narrow range (few distinct patterns) is non-adherence
   even with zero antipatterns. Anchor to this talk's `pattern_score` and distinct
   pattern count versus the baseline — use the talk's **mode** baseline when Section
   15 has a stable one (≥3 talks in that mode), otherwise the global baseline. A
   lightning talk measured against a keynote baseline produces false "underuse"
   findings; match like to like.
2. **Intent adherence** — does the talk honor confirmed intents and design rules,
   or violate one? A violated confirmed intent is the strongest non-adherence
   signal.
3. **Departure classification** — classify each divergence as a deliberate
   mode-driven choice (different presentation mode, co-presenter, venue) or
   unintentional backsliding (a recurring antipattern resurfacing). Only
   backsliding counts against adherence; deliberate departures are noted, not
   penalized.

**Required anchors** — the assessment MUST:
- State this talk's `pattern_score` relative to the running average (e.g., "4 vs.
  6.8 average").
- Name any recurring antipattern already tracked in Section 15 that reappeared in
  this talk.

**Bound:** 2–4 sentences of prose, not a score — the numeric signal already lives
in `pattern_observations.pattern_score`; the assessment interprets it against the
baseline.

## Rhetoric Summary — Improvement & Adherence Sections (15–16)

`rhetoric-style-summary.md` Sections 1–14 mirror the 14 analysis dimensions.
Sections 15–16 are cross-talk aggregates, updated in Step 5 each batch.

### Section 15 — Improvement & Adherence Baseline

The running baseline that per-talk `adherence_assessment` measures against. Five
required subsections:

1. **Recurring improvement themes** — issues appearing in 2+ talks. One entry per
   theme: the issue, the related antipattern ID where one applies (Dimension 14
   lists the candidates), `severity` (`hard_limit|warning|info`), the count of
   talks exhibiting it, and the first/last talk filenames where it appeared.
   Source: aggregate `pattern_observations.antipatterns_detected` and
   `areas_for_improvement` across processed talks.
2. **Pattern-score & breadth baseline** — running `average_pattern_score` across
   scored talks with its trajectory (`improving|stable|declining`), plus pattern
   breadth (average distinct patterns per talk) with its trend
   (`widening|stable|narrowing`). Track both: a score can decline from antipatterns
   rising OR from breadth narrowing (using fewer patterns), and these are different
   coaching messages. Maintain the same figures **per presentation mode** once a
   mode has ≥3 scored talks (mirrors the profile's `pattern_profile.by_mode`); these
   per-mode figures are what mode-aware adherence compares against. This is the
   baseline per-talk adherence cites.
3. **Signature patterns & strengths** — the speaker's high-usage patterns (the
   adherence reference set). A talk that drops them is a departure to classify;
   chronic dropping is underuse, not just a one-off. Also surface these as
   **strengths** — "lean in / double down" — the positive counterpart to recurring
   issues, so the baseline isn't purely deficit-oriented. Mirrors the profile's
   `pattern_profile.strengths`.
4. **Underused patterns (growth)** — observable patterns the speaker never or
   rarely uses that fit their established modes. Framed as range to expand, not a
   deficiency — the positive-space counterpart to recurring antipatterns. Mirrors
   the profile's `pattern_profile.underused_patterns`.
5. **Resolved issues** — themes that previously recurred but have not appeared in
   the last 3+ talks. Move an entry here from "recurring themes" once it stops;
   never delete it — the trajectory is itself signal.

Section 15 is the human-readable source for the profile's `pattern_profile` and
`guardrail_sources.recurring_issues` (see
[../../vault-profile/references/speaker-profile-schema.md](../../vault-profile/references/speaker-profile-schema.md));
keep the two consistent when both update.

### Section 16 — Speaker-Confirmed Intent

Patterns the speaker confirmed as deliberate or accidental during a clarification
session (see vault-clarification). Read-only during ingress — populated by
clarification, consumed here as the intent-adherence input for Section 15.

## Improvement Goal Verification

Each ingress run, after the final Section 15 baseline is current, verifies the
speaker's active `improvement_goals` (set during clarification — record schema in
[../../vault-clarification/references/schemas-config.md](../../vault-clarification/references/schemas-config.md)).
This closes the loop: the system stops merely diagnosing and checks whether the
issue the speaker chose to work on actually moved.

For each goal with `status` not in (`achieved`, `retired`):
- Compute `current_value` for the goal's `metric` from the current Section 15
  baseline — and, for `pacing` and mode-specific goals, from the freshly regenerated
  speaker profile (this step runs after Step 7, so `pacing.adherence` and
  `pattern_profile.by_mode` are current). Examples by `kind`: `antipattern` → the
  antipattern's frequency over recent talks; `underuse` → the pattern's recent usage
  or distinct-pattern breadth; `pacing` → `pacing.adherence.over_budget_rate`. Write
  `current_value`, `last_checked` (today), `checked_by: "vault-ingress"`.
- Set `status` by comparing `current_value` against `baseline_value` and `target`:
  - `achieved` — `current_value` meets or beats `target`.
  - `improving` — moved toward `target` versus `baseline_value` but not there yet.
  - `stalled` — no meaningful movement from `baseline_value`.
  - `regressed` — moved away from `target` (worse than `baseline_value`).
- Only count talks newly processed since `set_date` toward movement — a goal can't
  be judged on talks that predate it.
- Never overwrite `baseline_value`, `target`, `issue`, or `set_date` — those are the
  fixed yardstick; verification is non-owner and touches status fields only.

Report each goal's status in the run summary. A `regressed` or `stalled` goal is the
strongest signal to surface — it is the speaker's own priority, not a machine-chosen
one.
