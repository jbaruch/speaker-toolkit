# Profile Construction Rules

Read this reference before aggregating or constructing `speaker-profile.json`, and
again before diffing an existing profile. The profile schema remains authoritative for
the complete JSON shape; this file defines source ownership, merge behavior, and
fail-closed edge cases used by the eight-step workflow in `../SKILL.md`.

## Contents

- [Loader and cohort semantics](#loader-and-cohort-semantics)
- [Non-catalog aggregation](#non-catalog-aggregation)
- [Template-layout merge](#template-layout-merge)
- [Profile field ownership](#profile-field-ownership)
- [Pattern-profile construction](#pattern-profile-construction)
- [Empty-cohort behavior](#empty-cohort-behavior)
- [Pacing and Section 15](#pacing-and-section-15)
- [Existing-profile diff](#existing-profile-diff)
- [Achievement badges](#achievement-badges)

## Loader and Cohort Semantics

`baseline_talks` is the exact active Presentation Pattern scoring generation whose
persisted source-located artifacts still match their recorded identities. The loader
passes the vault root and database-configured source roots to the shared read-only
freshness assessor. The loader has already excluded scoring-v5 records whose persisted
citation artifacts are missing, replaced, or inconsistent with their recorded root and
digest; never restore them from another cohort or a prior profile.

`pattern_baseline.eligible_talk_count` is the occurrence-cohort size. Its raw-score
count and average are available only when every eligible talk shares one
`opportunity_coverage_identity` containing at least one evaluable opportunity.
Otherwise retain the explicit mixed-coverage or no-evaluable-opportunities unavailable
state. `pattern_opportunities` contains the canonical exhaustive positive and negative
rows; copy them rather than recalculating them. `pattern_scoring_exclusions` explains
every otherwise eligible talk omitted from the cohort, including artifact drift.

`current_instrumentation_talks` and `stale_instrumentation_talks` form a separate
extractor cohort for pacing-sensitive analysis. Instrumentation membership never
confers pattern-baseline eligibility.

Legacy database schema 0 and current schema 1 are read-only inputs. An unsupported
future database or record schema has no usable prior state. Compatibility stays
internal, adds no payload fields, and never migrates the database.

A missing `rhetoric-style-summary.md` blocks profile generation and requires
vault-ingress. A missing `slide-design-spec.md` yields `design_spec: ""`; leave the
design-spec section empty and continue.

## Non-Catalog Aggregation

Keep these cohorts distinct:

- `processed_talks` supplies `talks_analyzed` and non-catalog narrative/profile data.
- `baseline_talks` is available for source review only; deterministic
  `pattern_opportunities` supplies catalog occurrence rows.
- `current_instrumentation_talks` supplies pacing data only.

For non-catalog dimensions, skip processed talks with empty `structured_data` and use
matching `summary` prose when needed. If every processed talk lacks structured data,
warn the speaker and use prose only for non-catalog fields. Never use prose,
`processed_talks`, `excluded_pattern_scoring_talks`, either instrumentation cohort, or
a prior profile to fill a missing pattern aggregate.

## Template-Layout Merge

Accept extraction schema v1, v2, v3, or v4 for `template_layouts` only. Missing or
legacy v0 output and unknown future versions are unusable; obtain current extraction
output. A v1 record has no timing contract and must not be interpreted as zero timing.

Merge fresh layouts into `infrastructure.template_layouts`. Structural fields
(`index`, `master_index`, `name`, and `placeholders`) come from extraction;
speaker-curated `use_for` does not. Match prior `use_for` values by
`(master_index, name)`, because layout names are not unique across masters. Drop prior
layouts absent from fresh extraction. When `config.template_pptx_path` is unset, emit
an empty layout list.

## Profile Field Ownership

| Profile section | Sole source |
|---|---|
| `speaker`, `infrastructure` | Step 1 `config` |
| `presentation_modes`, `instrument_catalog` | Step 1 `summary` |
| `rhetoric_defaults` | Step 1 `confirmed_intents` |
| `pacing` | `current_instrumentation_talks` |
| `guardrail_sources` | Aggregated non-pattern data |
| `pattern_profile` | `pattern_baseline` and deterministic `pattern_opportunities` |
| `visual_style_history` | Summary dimension 13f observations |

Use every top-level key required by `speaker-profile-schema.md`. Set
`schema_version` to `4`, `generated_date` to today's `YYYY-MM-DD` date, and
`talks_analyzed` to the count of all `processed_talks`.

The required top-level keys are `schema_version`, `generated_date`,
`talks_analyzed`, `speaker`, `infrastructure`, `presentation_modes`,
`instrument_catalog`, `rhetoric_defaults`, `confirmed_intents`,
`guardrail_sources`, `pacing`, `pattern_profile`, `visual_style_history`,
`publishing_process`, `design_rules`, and `badges`.

Keep `pattern_profile` as the only catalog-history storage lane. Never copy mastery,
signatures, scores, usage, or another pattern aggregate into `rhetoric_defaults`.
Never materialize catalog-derived `guardrail_sources.recurring_issues` or `badges`;
consumers derive those directly from validated `pattern_profile`. Every top-level
recurring issue and badge is non-pattern data with `source_lane: "non_pattern"`.

## Pattern-Profile Construction

Copy `pattern_baseline` unchanged to `pattern_profile.pattern_baseline`. Set
`baseline_talk_filenames` to the sorted unique exact filenames from `baseline_talks`,
copy `pattern_baseline.eligible_talk_count` to `eligible_talk_count`, and take
`talks_scored` plus `average_pattern_score` from the baseline's raw-score-comparison
fields. A non-empty eligible cohort can validly have zero scored talks and a null
average when opportunity identities are mixed or no outcome is evaluable. Never turn
missing opportunity coverage into a zero average.

Copy `pattern_opportunities.pattern_usage` and
`pattern_opportunities.antipattern_frequency` unchanged. Their denominators are
pattern-specific evaluable counts, not the global eligible count. Preserve exhaustive
rows even for an empty cohort, including their canonical null rate and coverage
sentinels.

No versioned classification policy exists in schema v4. Copy the exact
owner-policy-unconfigured `classification_availability` sentinel from
`speaker-profile-schema.md`. Fail closed: score trend, breadth trend/average, and
score-driver direction are unavailable; driver arrays, `never_used_patterns`, mastery
tiers, signatures, strengths, underuse, and `by_mode` are empty. Zero detections never
mean never used, and a positive frequency never means recurring.

## Empty-Cohort Behavior

When `baseline_talks` is empty, retain the zero-count baseline, empty filenames, and
exhaustive zero-opportunity rows. Set score and breadth averages to null and pattern
trend/direction fields to `unavailable`. Never borrow pattern values from a prior
profile, summary prose, an excluded scoring generation, or an instrumentation cohort.

## Pacing and Section 15

Pacing is quantitative but approximate. Treat marginal slide-budget overages softly;
the result complements, rather than replaces, Dimension 14's transcript-evident
"rushing" assessment.

Use Section 15 of `rhetoric-style-summary.md` only for narrative consistency review.
It cannot override or fill the current pattern cohort.

## Existing-Profile Diff

If no prior profile exists, skip the diff.

Otherwise compare `pattern_catalog_fingerprint` and
`pattern_scoring_schema_version` first. A change in either is a pattern-generation
reset: do not describe catalog-derived score, trend, usage, mastery, or strength
differences across it as speaker improvement or regression.

Within one exact generation, do not report raw-score movement across a changed or
unavailable `opportunity_coverage_identity`. Do not infer policy-derived changes while
`classification_availability.status` is `unavailable`.

Report these same-generation non-pattern changes:

- New `instrument_catalog` instruments.
- Revised `guardrail_sources` thresholds.
- New non-pattern `recurring_issues` guardrails.
- Worsening `pacing.adherence.trend` or rising `over_budget_rate`.
- New presentation modes, prominently; this is the highest-signal creator behavior
  change.

## Achievement Badges

Generate fun, self-deprecating badges from pacing, visual, publishing, talk-count, or
confirmed-intent data. Use the speaker's voice rather than corporate gamification.
Never derive a badge from catalog pattern usage, mastery, strength, antipattern, score,
or absence. Set `source_lane: "non_pattern"` on every badge.
