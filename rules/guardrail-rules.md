---
alwaysApply: false
applyTo: "skills/presentation-creator/** — when generating or checking a presentation outline"
---

# Guardrail Rules

## Guardrail Check Script

Run `python3 skills/presentation-creator/scripts/guardrail-check.py <outline.yaml> <speaker-profile.json>`
to compute guardrail checks. The script handles the
three-outcome PASS/WARN/FAIL logic:

- `[FAIL]` — value exceeds the limit
- `[WARN]` — value is under the limit but within 5 percentage points of it
- `[PASS]` — value is under the limit by more than 5 percentage points

The script checks pattern-history authorization, slide budget, Act 1 ratio, closing
completeness, cut lines, data attribution, profanity, and branding. Its
`recurring_antipatterns` array is the complete catalog recurrence output. Render those
records without re-filtering them or adding movement data.
Add the remaining checks (time-sensitive, current-outline contextual antipatterns,
illustration coverage, pattern strategy, AI writing patterns) to the report
manually.

The AI-writing-pattern scan is delegated to `blog-writer`, never reimplemented
here, and it reports findings without applying them. Its execution contract —
invocation, voice suppression, classification, and the absent-scanner path — is
in `skills/presentation-creator/references/phase4-guardrails.md`.

A disabled pattern-history result affects only catalog-derived speaker history. Keep
independent profile configuration and guardrails enabled. When history is partially
available, require the exact domain for each derived field:

- Use `mastery_and_novelty` for tiers, strengths, and novelty.
- Use `underuse` for underuse.
- Use `signature_combinations` for combinations.
- Use the `antipattern_recurrence` domain only through the script's
  `recurring_antipatterns` output.
- Use `trends` for movements and score/breadth trend.
- Use `modes` for by-mode history.
- Always retain the current-taxonomy scan of the new outline.

Schema-v4/v5 top-level `guardrail_sources.recurring_issues[]` and `badges[]` are usable
only when each consumed entry explicitly declares `source_lane: "non_pattern"`.
Suppress legacy or ambiguous entries. Catalog-derived warnings and reinforcement come
only from authorized `pattern_profile` history.

## Antipattern Tags

Every antipattern flag MUST be tagged as one of:

- `[RECURRING]`. Render one `guardrail-check.py` `recurring_antipatterns` record.
  - Preserve its `recurrence_classification`, `evidence`, and optional `trend` fields.
  - Do not reclassify the record.
- `[CONTEXTUAL]` — detected in the current outline but NOT in the speaker's
  authorized historical profile. It is a current-outline finding, not necessarily a
  first-time issue when history is unavailable.

Never use generic unlabeled antipattern warnings.

## 4-Tier Pattern Strategy

When `pattern_history_status.py` reports the `mastery_and_novelty` domain, organize
recommendations into exactly four tiers:

1. **Signature.** Use current-cohort `mastery_levels.signature` patterns.
2. **Contextual history.** Use current-cohort regular/occasional patterns worth
   considering here.
3. **New to You.** Use exactly `mastery_levels.never_tried` /
   `never_used_patterns` entries that fit this talk.
   - Do not treat a first detection in the newest talk or `not_yet_observed` as
     New-to-You.
4. **Shake It Up.** Use exactly 1-2 wild card patterns for experimentation.
   - Do not use zero or three or more wild card patterns.

When the mastery domain is unavailable, do not manufacture those tiers from legacy
profiles or unprovenanced prose. Present a flat relevant-pattern list from the current
taxonomy without usage or novelty claims. A catalog fingerprint or scoring-schema
change is a generation reset, never evidence of improvement or regression.

`history_enabled: true` means at least one policy-bound domain is available, not that
all classification fields are authorized. `opportunity_rows_available: true` is an
audit signal, not history authorization. Raw occurrence rows do not establish novelty,
mastery, recurrence, or trend. Profile schema v4 and Section 15 v2 are occurrence-only;
profile schema v5 and Section 15 v3 bind classifications to the versioned policy.

A catalog/scoring identity change is a generation reset. Within one generation, a
changed `policy_semantic_sha256` is a classification-comparison reset. Neither reset is
ever evidence of speaker improvement or regression.
