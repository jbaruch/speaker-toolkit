# Pattern-History Authorization — Detail

Load this after `pattern_history_status.py` returns and before consuming any
catalog-derived historical field. Phase 0 runs the script; this file defines what
its output authorizes.

## The status payload

```bash
"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/pattern_history_status.py" \
  path/to/speaker-profile.json path/to/rhetoric-style-summary.md
```

Use `-` for the profile path in summary-only mode. The command emits
`{history_enabled, history_source, profile_schema_version, scored_talk_count,
eligible_talk_count, opportunity_rows_available, classification_fields_available,
available_classification_domains, policy_semantic_sha256, reason_codes, reasons,
warning}`.

`history_enabled` means at least one policy-bound domain is available. It is not
permission to consume every derived field. In JSON, require membership in
`available_classification_domains` for each use. Python consumers call
`domain_available(domain)`.

## Domain contracts

| Domain | Authorizes |
|---|---|
| `mastery_and_novelty` | Mastery tiers, strengths, and New-to-You |
| `underuse` | `underused_patterns` |
| `signature_combinations` | `signature_combinations` |
| `antipattern_recurrence` | Historical recurrence, consumed only through Phase 4's emitted `recurring_antipatterns` output |
| `trends` | Pattern and antipattern movements, score/breadth trend, score drivers |
| `modes` | `by_mode` history |

`[NEW]` is exactly `mastery_levels.never_tried` / `never_used_patterns`. It is
never first detection in the newest talk, and never a `not_yet_observed`
classification.

A recurrence claim may be available without a trend claim.

## Source selection

A non-null `history_source` selects the sole catalog-history input. Use the
emitted value without reproducing source-selection logic and without merging
inputs. Surface a disabled result's `warning` verbatim and recommend profile
regeneration.

Continue using independent non-pattern fields regardless of history status:
pacing, visual rules, presentation modes, infrastructure, publishing config, and
confirmed intents.

## Schema tiers

- Stored profile schemas v1/v2/v3 remain readable for non-pattern fields only.
- Schema v4 is occurrence-only.
- Schema v5 binds derived classifications to a versioned policy.

Exact occurrence rows may remain auditable when `opportunity_rows_available` is
true, but that status never authorizes a classification.

Suppress each catalog-derived historical field when its required domain is
absent. Do not collapse the available domains behind the global history flag.

Top-level recurring issues and badges in schema-v4/v5 profiles remain usable only
when their entries explicitly declare `source_lane: "non_pattern"`. Legacy or
ambiguous entries do not authorize history.
Current-taxonomy scans of the new outline remain enabled.

## Summary-only mode

If no profile exists, run in summary-only mode: default guardrail thresholds
(1.5 slides/min, 45% Act 1 cap) and ask for template/publishing data
interactively.

Section 15 v3 classifications are usable only when its uniquely delimited current
block passes:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-profile/scripts/section15_pattern_history.py"
```

plus the same strict pattern-profile assessment. Require the relevant domain just
as for profile history. Section 15 v2 is occurrence-only. Ordinary, stale, or
occurrence-only Section 15 data authorizes taxonomy-only recommendations, never
speaker-history claims.

## Comparing two profiles

Compare pattern catalog fingerprints and scoring schemas first. A mismatch is a
generation reset — do not call cross-generation pattern differences improvements
or regressions.

Raw scores are also incomparable when the baseline reports an unavailable or
changed `opportunity_coverage_identity`.

Within one catalog/scoring generation, a changed `policy_semantic_sha256` is a
classification-comparison reset: do not describe changed tiers, recurrence
classes, combinations, or trends as speaker improvement or regression across that
boundary.
