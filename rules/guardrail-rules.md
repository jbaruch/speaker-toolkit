# Guardrail Rules

## Guardrail Check Script

Run `scripts/guardrail-check.py <outline.md> <speaker-profile.json>` to compute
guardrail checks. The script handles the three-outcome PASS/WARN/FAIL logic:

- `[FAIL]` — value exceeds the limit
- `[WARN]` — value is under the limit but within 5 percentage points of it
- `[PASS]` — value is under the limit by more than 5 percentage points

The script checks: slide budget, Act 1 ratio, closing completeness, cut lines,
data attribution, and profanity. Add the remaining checks (branding, time-sensitive,
anti-patterns, illustration coverage, pattern strategy) to the report manually.

## Antipattern Tags

Every antipattern flag MUST be tagged as one of:

- `[RECURRING]` — matches a pattern in the speaker's `antipattern_frequency`
  or `recurring_issues` profile history. The speaker has done this before.
- `[CONTEXTUAL]` — detected in the current outline but NOT in the speaker's
  historical profile. First-time issue for this talk.

Never use generic unlabeled antipattern warnings.

## 4-Tier Pattern Strategy

When recommending presentation patterns, organize into exactly four tiers:

1. **Signature** — patterns the speaker already uses consistently (from `signature_patterns`)
2. **Contextual** — patterns the speaker uses sometimes, worth considering here (from `contextual_patterns`)
3. **New to You** — patterns the speaker has never used but would fit this talk
4. **Shake It Up** — exactly 1-2 wild card patterns for experimentation. Never 0, never 3+.
