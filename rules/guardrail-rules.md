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
completeness, cut lines, data attribution, profanity, and branding. It emits historical
recurring antipattern lines only when the exact-generation authorization passes. Add
the remaining checks (time-sensitive, current-outline contextual antipatterns,
illustration coverage, pattern strategy) to the report manually.

A disabled pattern-history result affects only catalog-derived speaker history. Keep
independent profile configuration and guardrails enabled. Suppress signature and
contextual-history tiers, New-to-You claims, strengths, underuse, by-mode history,
historical recurring labels, and pattern-derived recurring issues or badges. Always
retain the current-taxonomy scan of the new outline.

Schema-v4 top-level `guardrail_sources.recurring_issues[]` and `badges[]` are usable
only when each consumed entry explicitly declares `source_lane: "non_pattern"`.
Suppress legacy or ambiguous entries. Catalog-derived warnings and reinforcement come
only from authorized `pattern_profile` history.

## Antipattern Tags

Every antipattern flag MUST be tagged as one of:

- `[RECURRING]` — matches an authorized current-generation pattern in the speaker's
  `antipattern_frequency` or pattern-derived `recurring_issues` history. Use this label
  only when `pattern_history_status.py` reports `history_enabled: true`.
- `[CONTEXTUAL]` — detected in the current outline but NOT in the speaker's
  authorized historical profile. It is a current-outline finding, not necessarily a
  first-time issue when history is unavailable.

Never use generic unlabeled antipattern warnings.

## 4-Tier Pattern Strategy

When `pattern_history_status.py` reports `history_enabled: true`, organize
recommendations into exactly four tiers:

1. **Signature** — current-cohort `mastery_levels.signature` patterns
2. **Contextual history** — current-cohort regular/occasional patterns worth considering here
3. **New to You** — current-cohort never-tried patterns that fit this talk
4. **Shake It Up** — exactly 1-2 wild card patterns for experimentation. Never 0, never 3+.

When history is disabled, do not manufacture those tiers from legacy profiles or
unprovenanced prose. Present a flat relevant-pattern list from the current taxonomy
without usage or novelty claims. A catalog fingerprint or scoring-schema change is a
generation reset, never evidence of improvement or regression.

`opportunity_rows_available: true` is an audit signal, not history authorization. Raw
occurrence rows do not establish novelty, mastery, recurring severity, or trend. The
four tiers and `[RECURRING]` labels also require
`classification_fields_available: true`; current owner-policy-unconfigured schema-v4
profiles stay on the flat taxonomy path.
