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

## Pattern Taxonomy and Generation Recovery

Run `skills/vault-ingress/scripts/queue-state.py <tracking-database.json>
normalize` before claiming work. The command owns both legacy source-status
migration and pattern-generation recovery as one copy-on-write transaction. It
uses `partition_pattern_scoring_cohort` from
`skills/vault-ingress/scripts/adherence_baseline.py`; do not duplicate that
selection logic or approximate it with `processed_date`.

Every valid `processed`/`processed_partial` result excluded from the active
generation is moved to `needs-reprocessing`. The stored machine reason is
`pattern_scoring_generation:<reason-code>[+<reason-code>...]`, preserving the
selector's ordered codes, and the same codes and observed/expected generation
identity appear in the command's `normalizations` JSON. That gives every clean
consumer exclusion a deterministic queue path instead of leaving the current
cohort permanently empty.

Malformed or unknown generation identity, a current result with non-empty
generation reasons, incomplete current identity, and invalid or divergent
current score lanes reject the whole command with no DB write. Inflight,
pending, already-queued, and skipped records remain outside generation recovery.
Repeating normalization after a successful recovery is byte-stable. Existing
completed claim and history evidence is preserved; the next ordinary queue claim
archives the prior current claim under the normal generation transition.

## Pattern Tagging Rules

Scan observations against the pattern taxonomy index at
`skills/presentation-creator/references/patterns/_index.md` (path relative to plugin root).
Skip patterns marked `observable: false` — these are pre-event logistics and physical
stage behaviors that cannot be detected from transcripts or slides.

For every other entry, inspect `evaluable_from`, optional
`strong_evaluable_from` and `absence_evaluable_from`, `evidence_requirements`,
and `not_evaluable_when` when present. The allowed evidence-source values and
their limits are defined in the index's Evidence-Source Contract. A strong
detection uses `strong_evaluable_from` (defaulting to `evaluable_from`);
moderate and weak detections use `evaluable_from`. Only score an entry when an
available eligible source establishes its requirements. Every detected pattern
or antipattern must record concrete `evidence` and the qualifying
`evidence_source`. When that source is `source_comparison`, also return the
duplicate-free `evidence_sources_used` array. It must exactly equal one
qualifying all-of group, while the prose evidence names what was compared.

For an entry with no positive detection, use `absence_evaluable_from`
(defaulting to `evaluable_from`) to decide whether the inspected sources can
support an undetected outcome. If that gate is not satisfied, or a stated
disqualifier prevents either outcome, add an item to
`pattern_observations.not_evaluable` with the `pattern_id`, best available
`evidence_source`, and a precise `reason`. A valid positive detection takes
precedence: never add the same ID to `not_evaluable` merely because the absence
gate is unavailable. Do not guess and do not interpret `not_evaluable` as
absence. Exclude not-evaluable entries from the score. Compute per-talk pattern
score as count(detected patterns) − count(detected antipatterns), then return
the detections, not-evaluable observations, and score in
`pattern_observations`.

This is exhaustive for source gates: every undetected observable catalog entry
for which no effective absence alternative is satisfied by the return's
inspected sources must be represented in `not_evaluable`. A string alternative
needs that one source. A nested alternative needs every named underlying source
plus the `source_comparison` marker in the global inspected `evidence_sources`.
For absence evaluation, that global list is the complete proof; there is no
detection object, detection `evidence_source`, or `evidence_sources_used` field.
Artifact scope still controls what counts as a source. In particular, an
untrusted video
`full_frame_context` may support concrete `delivery_video` observations but never
creates `static_slides` or `native_deck` evidence.

## Structured Field Extraction

The subagent's job is to **return** every structured field it identifies (co-presenter,
delivery language, slide counts, opening/closing types, etc.) in the `structured_data`
block per the return schema — never to leave them buried only in `rhetoric_notes` free
text. If it's in the analysis, it must be in `structured_data`.

Persisting those fields is deterministic and script-owned, not a manual per-run mapping —
SKILL.md Step 4 uses `skills/vault-ingress/scripts/persist-results.py` for the merge. Authors do not re-derive
that logic here.

## Adherence Assessment

`adherence_assessment` measures how consistent a talk is with the speaker's
**established** rhetorical baseline — not whether the talk was good in the
abstract. Adherence is consistency with this speaker's own validated style, which
is why it can only be computed once a baseline exists.

**Authority:** for return schema v3, the only numeric authority is the immutable
`talk._queue_claim.adherence_baseline` captured before the active batch changed
state. Workers MUST NOT parse Section 15, infer a date cohort, or recompute an
average from the live DB. Every member of one batch carries the same snapshot;
`active_batch_excluded: true` means every selected filename was removed before
its old score could enter the population.

**Gate:** inspect `adherence_baseline.scored_talk_count` exactly.

- Fewer than 10 talks: `adherence_assessment` MUST be the exact empty string
  `""`, and `adherence_comparison` MUST be absent.
- 10 or more talks: `adherence_comparison` is required and contains exactly
  schema version 1, a value-for-value copy of the claim's complete baseline, and
  `talk_pattern_score` equal to the validated return score. The prose assessment
  is also required.

This is a global, generation-bound comparison. The baseline includes only
`processed`/`processed_partial` talks stamped `current` with the exact catalog
fingerprint and pattern-scoring schema captured by the claim. An unscored talk
cannot be assessed, and a stale catalog/scoring generation requires recovery
and a fresh claim rather than reinterpretation.

**Three checks, in order:**
1. **Numeric anchor** — interpret the validated `pattern_score` against the
   claim baseline's `average_pattern_score` and `scored_talk_count`. The
   renderer generates this anchor mechanically from `adherence_comparison`; the
   worker's prose need not restate the numbers.
2. **Current-talk evidence** — interpret that difference using the patterns and
   antipatterns detected in this return. Name a detected antipattern when one
   materially explains the score; do not invent population frequency that the
   baseline schema does not carry.
3. **Departure classification** — use claim/talk context and confirmed intent,
   when present, to distinguish a deliberate mode, co-presenter, or venue choice
   from likely backsliding. Context may explain the number but cannot replace or
   modify the claim snapshot.

**Required interpretation:** the assessment explains the mechanically generated
anchor using current-talk evidence. Validators deliberately do not parse prose
for numeric agreement. If the prose happens to repeat a number, that number is
untrusted narrative; the structured comparison and renderer-generated anchor
remain authoritative.

**Bound:** 2–4 punctuation-terminated sentences of prose, not a second score. Enforcement is
deterministic: every `.`, `?`, or `!` punctuation cluster followed by whitespace
or end of text is one sentence boundary, including a period in an abbreviation;
the final sentence must be terminated. Spell out abbreviations that would create
a false boundary.

Non-empty adherence prose from a return v1/v2 artifact remains replayable only
as archival `legacy-unverified` text. It is never a verified numeric comparison,
never enters a current baseline or Section 15 aggregate, and is never profile
input.

## Rhetoric Summary — Improvement & Adherence Sections (15–16)

`rhetoric-style-summary.md` Sections 1–14 mirror the 14 analysis dimensions.
Sections 15–16 are cross-talk narratives. Rebuild Section 15 in Step 5 only
after the entire batch has persisted successfully; never update it after an
individual member merge.

### Section 15 — Improvement & Adherence Baseline

Section 15 is a human-readable account of the verified current cohort, not the
numeric authority for a worker. `persist-results.py` stdout supplies the
post-batch `current_adherence_baseline` only after every merge succeeds. That
schema-v1 payload is all-inclusive (`active_batch_excluded: false`,
`excluded_filenames: []`) and provides the canonical scored count, sum, and
ROUND_HALF_EVEN average for the complete candidate.

For all other Section 15 counts, read only talks with status
`processed`/`processed_partial`, `pattern_scoring_generation_status: current`,
empty generation reasons, the exact current catalog fingerprint, and the exact
current pattern-scoring schema version. Never approximate this cohort by
`processed_date`. Exclude skipped, legacy-unbaselineable, stale-fingerprint,
stale-schema, and archival `legacy-unverified` adherence prose. Five required
subsections:

1. **Recurring improvement themes** — issues appearing in 2+ talks. One entry per
   theme: the issue, the related antipattern ID where one applies (Dimension 14
   lists the candidates), `severity` (`hard_limit|warning|info`), the count of
   talks exhibiting it, and the first/last talk filenames where it appeared.
   Source: aggregate `pattern_observations.antipatterns_detected` and
   `areas_for_improvement` across the exact current-generation cohort defined
   above.
2. **Pattern-score & breadth baseline** — copy the global scored count, sum, and
   `average_pattern_score` from the post-batch payload, with its human-readable
   trajectory (`improving|stable|declining`), plus pattern
   breadth (average distinct patterns per talk) with its trend
   (`widening|stable|narrowing`). Track both: a score can decline from antipatterns
   rising OR from breadth narrowing (using fewer patterns), and these are different
   coaching messages. Maintain the same figures **per presentation mode** once a
   mode has ≥3 scored talks (mirrors the profile's `pattern_profile.by_mode`) by
   filtering that same exact current generation. These mode figures are a
   human-readable mirror of profile output; they do not replace the immutable
   global claim baseline for a per-talk v3 comparison.
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

Section 15 is the human-readable mirror of the profile's `pattern_profile` and
`guardrail_sources.recurring_issues` (see
[../../vault-profile/references/speaker-profile-schema.md](../../vault-profile/references/speaker-profile-schema.md));
keep the two consistent when both update. Profile generation must independently
apply the same exact current-generation filter; Section 15 prose and legacy
adherence text are not machine-readable numeric inputs.

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

Before calculating any metric, run
`skills/vault-clarification/scripts/goal_generation_provenance.py` with the complete
active-goal array and the structured post-batch full-cohort pattern baseline. The
script emits one assessment with a stable `decision` and `reason_codes` per goal;
exit 1 blocks all goal writes. It is the sole authority for generation
comparability—do not reproduce its fingerprint/schema predicate and never parse
Section 15 prose as its baseline.

- A `comparable` assessment authorizes the metric and outcome rubric below.
- For `needs_rebaseline` or `unverifiable`, copy the assessment decision to
  `verification_state` and its codes to `verification_reasons`. In either case,
  preserve `current_value` and must not set `status` to
  `achieved`, `improving`, `stalled`, or `regressed`. A speaker-confirmed
  rebaseline is owned by vault-clarification; ingress never restamps the fixed
  baseline.
- Pacing and independent goals continue through their own provenance lanes and
  are not invalidated by a pattern-catalog generation change.

For each comparable goal with `status` not in (`achieved`, `retired`):
- Compute `current_value` for the goal's `metric` from the current Section 15
  cohort data — and, for `pacing` and mode-specific goals, from the freshly regenerated
  speaker profile (this step runs after Step 7, so `pacing.adherence` and
  `pattern_profile.by_mode` are current). Examples by `kind`: `antipattern` → the
  antipattern's frequency over recent talks; `underuse` → the pattern's recent usage
  or distinct-pattern breadth; `pacing` → `pacing.adherence.over_budget_rate`. Write
  `current_value`, `last_checked` (today), `checked_by: "vault-ingress"`,
  `verification_state: "current"`, and empty `verification_reasons`.
- Set `status` by comparing `current_value` against `baseline_value` and `target`:
  - `achieved` — `current_value` meets or beats `target`.
  - `improving` — moved toward `target` versus `baseline_value` but not there yet.
  - `stalled` — no meaningful movement from `baseline_value`.
  - `regressed` — moved away from `target` (worse than `baseline_value`).
- Only count talks processed after `set_date` toward movement — a goal can't
  be judged on talks that predate it.
- Never overwrite `baseline_value`, `target`, `issue`, or `set_date` — those are the
  fixed yardstick; verification is non-owner and touches status fields only.

Report each goal's status in the run summary. A `regressed` or `stalled` goal is the
strongest signal to surface — it is the speaker's own priority, not a machine-chosen
one.
