---
name: vault-profile
description: >
  Generates or updates the structured speaker-profile.json from vault data. Aggregates
  rhetoric summary, slide design spec, confirmed intents, and structured talk data into
  a machine-readable profile used by the presentation-creator skill. Also generates
  speaker achievement badges.
  Triggers: "generate speaker profile", "update speaker profile",
  "regenerate speaker profile", "sync speaker profile".
user_invocable: true
---

# Vault Profile — Speaker Profile Generator

Process steps in order. Do not skip ahead.

Resolve the absolute path of this loaded `SKILL.md`, then set
`speaker_toolkit_root` to the plugin root two directories above the directory
containing this file. Never derive it from the consumer working directory.
Treat `{speaker_toolkit_root}` as absolute in every toolkit-owned command;
vault paths remain consumer-owned.

Generate or update `speaker-profile.json` from vault data. This profile is the
structured bridge between the vault and the presentation-creator skill.

The vault lives at `~/.claude/rhetoric-knowledge-vault/` (may be a symlink).
Read `tracking-database.json` from there to get `vault_root`.

Before running any toolkit script, read `config.python_path` from that tracking
database and set `python_path` to that exact value. It is the interpreter
authority for every operational command in this skill. If vault-ingress Step 7
invoked this skill, accept its resolved `{vault_root}` and `{python_path}` as
handoff context, then re-read the database and require the stored value to match.
If `python_path` is absent, empty, mismatched, or cannot execute the core runtime
probe below, stop and direct the speaker to vault-ingress Step 1 to repair the
configuration. Never fall back to whichever `python3` happens to be on `PATH`.

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/check-runtime.py" \
  --lanes core,pptx --require-lanes core
```

## Key Files & References

| File / Reference | Purpose |
|------------------|---------|
| `tracking-database.json` | Source of truth — talks, config, confirmed intents |
| `rhetoric-style-summary.md` | Running rhetoric & style narrative |
| `slide-design-spec.md` | Visual design rules from PDF + PPTX analysis |
| `speaker-profile.json` | Output — machine-readable profile |
| [references/speaker-profile-schema.md](references/speaker-profile-schema.md) | Profile JSON schema |
| [references/schemas-config.md](references/schemas-config.md) | Config fields + confirmed intents schema |
| `scripts/load-vault.py` | Read vault sources, emit JSON payload to stdout |
| `scripts/validate-profile.py` | Validate profile v4 against the live vault cohort |
| `scripts/pattern_cohort_snapshot.py` | Shared fresh-cohort selection used by loader and validator |
| `scripts/pattern_opportunities.py` | Exact scoring-v5 opportunity-row aggregation and validation |
| `scripts/profile_pattern_provenance.py` | Shared occurrence/classification availability contract for writers/readers |
| `scripts/compute-pacing-adherence.py` | Compute `pacing.adherence` from scored talks + slide budgets |

## Prerequisites

- **10+ talks parsed** AND `config.clarification_sessions_completed >= 1`.
- Also runs on explicit request (overrides prerequisites).
- Auto-triggered by vault-ingress Step 7 (Regenerate Speaker Profile) if profile already exists.

## Step 1 — Load Vault Sources

Run `"{python_path}" "{speaker_toolkit_root}/skills/vault-profile/scripts/load-vault.py"` to read `tracking-database.json`, `rhetoric-style-summary.md`, and `slide-design-spec.md` from the vault root. The script emits a single JSON payload on stdout.

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-profile/scripts/load-vault.py" \
  "{vault_root}" > /tmp/vault-payload.json
```

**I/O contract:**
- Args: optional vault-root path and optional timezone-aware `--as-of` timestamp;
  defaults are documented in the script's top-of-file contract.
- Stdout (JSON): `{vault_root, config, confirmed_intents, talks, processed_talks,
  baseline_talks, excluded_pattern_scoring_talks, pattern_scoring_exclusions,
  pattern_baseline, pattern_opportunities, current_instrumentation_talks,
  stale_instrumentation_talks, baseline_note, instrumentation_note, summary,
  design_spec}`.
- `baseline_talks` is the exact active Presentation Pattern scoring generation whose
  persisted source-located artifacts still match their recorded identities. The
  loader passes both the vault root and database-configured source roots to the
  shared read-only freshness assessor. `pattern_baseline.eligible_talk_count` is the
  occurrence cohort size. Its raw-score count and average are available only when all
  eligible talks share one `opportunity_coverage_identity` and that identity contains
  at least one evaluable opportunity; otherwise the baseline carries the explicit
  mixed-coverage or no-evaluable-opportunities unavailable state. `pattern_opportunities`
  contains the canonical exhaustive positive and negative rows. Copy those rows; do
  not recalculate them in the model. `pattern_scoring_exclusions` explains every
  eligible talk omitted from the cohort, including deterministic artifact-drift
  details.
- `current_instrumentation_talks` and `stale_instrumentation_talks` are a separate
  extractor cohort used for pacing-sensitive analysis. Instrumentation membership
  never confers pattern-baseline eligibility.
- Exit non-zero with stderr message if arguments, vault sources, catalog identity, or
  scoring-generation metadata are missing or malformed.

If the script aborts on missing `rhetoric-style-summary.md`, run vault-ingress first. If `slide-design-spec.md` is missing, `design_spec` is `""` and the design-spec section of the profile remains empty — continue without aborting.

Proceed immediately to Step 2.

## Step 2 — Aggregate Structured Data

Keep three explicitly named cohorts while aggregating:

- `processed_talks` supplies `talks_analyzed` and non-catalog narrative/profile data.
- `baseline_talks` supplies only source review; the deterministic
  `pattern_opportunities` payload supplies catalog occurrence rows.
- `current_instrumentation_talks` supplies the separately named pacing cohort.

For non-catalog dimensions, skip processed talks with empty `structured_data` and use
the matching prose in `summary` when necessary. If every processed talk lacks
`structured_data`, warn the speaker and use prose only for those non-catalog fields.
Never use prose, `processed_talks`, `excluded_pattern_scoring_talks`, either
instrumentation cohort, or a prior profile to fill a missing pattern aggregate.

Proceed immediately to Step 3.

## Step 3 — Extract Template Layouts

If `config.template_pptx_path` is set, call the vault-ingress PPTX extraction script:

First require the configured interpreter's PPTX lane; an unavailable lane blocks
this extraction but must not be replaced with another interpreter:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/check-runtime.py" \
  --lanes core,pptx --require-lanes core,pptx
```

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/pptx-extraction.py" \
  "$TEMPLATE_PPTX_PATH" > /tmp/template-layouts.json
```

**I/O contract** (defined in vault-ingress; see `skills/vault-ingress/scripts/pptx-extraction.py`):
- Args: path to a `.pptx` file.
- Stdout (JSON): per-slide visual data, shape types, global design stats, and the master layouts list under the top-level `template_layouts` key. Each layout entry has `{index, master_index, name, placeholders: [{idx, type}]}`.
- Exit non-zero with stderr message if the file is missing, unreadable, or not a valid `.pptx`.

Check the extraction root's `schema_version` before reading layouts. This
layout-only consumer accepts v1 and v2 for `template_layouts` only.
Missing/legacy v0 or an unknown future version is not
usable prior output: rerun the current extractor and read that result. Do not
interpret a v1 record as carrying zero timing; it carries no timing contract.

Merge the resulting layouts list into `infrastructure.template_layouts` in the profile being constructed. The script emits structural fields (`index`, `master_index`, `name`, `placeholders`); the `use_for` field is speaker-curated and is **not** emitted. When merging, key by the `(master_index, name)` pair — PowerPoint allows the same layout name to appear under different slide masters, so name alone is insufficient. For each fresh layout, copy any existing `use_for` value from the prior profile's matching `(master_index, name)` entry. Layouts present in the prior profile but absent from the fresh extraction are dropped — the script is the source of truth for layout existence. If `template_pptx_path` is not set, leave `template_layouts` as an empty list and continue.

Proceed immediately to Step 4.

## Step 4 — Construct the Profile

Construct the `speaker-profile.json` dict per [references/speaker-profile-schema.md](references/speaker-profile-schema.md). Map vault sources to profile sections:

| Profile section | Source |
|---|---|
| `speaker` / `infrastructure` | `config` (from Step 1 payload) |
| `presentation_modes` / `instrument_catalog` | `summary` sections (from Step 1 payload) |
| `rhetoric_defaults` | `confirmed_intents` (from Step 1 payload) |
| `pacing` | `current_instrumentation_talks` only (separate non-pattern cohort) |
| `guardrail_sources` | aggregated non-pattern data only; catalog history stays in `pattern_profile` |
| `pattern_profile` | Step 1 `pattern_baseline` and deterministic `pattern_opportunities`; `baseline_talks` only for source review |
| `visual_style_history` | dimension 13f observations from `summary` |

Top-level keys (full nested schema in [references/speaker-profile-schema.md](references/speaker-profile-schema.md)):

```
schema_version, generated_date, talks_analyzed, speaker, infrastructure,
presentation_modes, instrument_catalog, rhetoric_defaults, confirmed_intents,
guardrail_sources, pacing, pattern_profile, visual_style_history,
publishing_process, design_rules, badges
```

Copy Step 1 `pattern_baseline` unchanged into
`pattern_profile.pattern_baseline`. Set
`pattern_profile.baseline_talk_filenames` to the sorted, unique exact filenames from
`baseline_talks`, and copy `pattern_baseline.eligible_talk_count` to
`pattern_profile.eligible_talk_count`. Set `talks_scored` and
`average_pattern_score` from the baseline's raw-score-comparison fields. They may be
`0` and `null` while `eligible_talk_count` is non-zero when opportunity identities are
mixed or no outcome is evaluable; never turn missing opportunity coverage into a zero
average.

Copy `pattern_opportunities.pattern_usage` and
`pattern_opportunities.antipattern_frequency` unchanged into the matching profile
fields. Their per-pattern denominators are not the global eligible count: the exact
row contract belongs to `scripts/pattern_opportunities.py`. Keep the exhaustive rows
even when the cohort is empty; their rates and coverage then use the script's null
sentinels.
The loader has already excluded scoring-v5 records whose persisted citation
artifacts are missing, replaced, or inconsistent with their recorded root and digest;
never restore them from another cohort or a prior profile.

No speaker-owned versioned classification policy exists yet. Copy the exact
owner-policy-unconfigured `classification_availability` sentinel from
[references/speaker-profile-schema.md](references/speaker-profile-schema.md), and
fail closed for every policy-derived claim: `score_trend`, breadth trend/average, and
score-driver direction are unavailable; driver arrays, `never_used_patterns`, mastery
tiers, signatures, strengths, underuse, and `by_mode` are empty. Zero detections do not
mean never used, and a positive frequency does not mean recurring. `talks_analyzed`
may remain the count of all `processed_talks`.

Keep `pattern_profile` as the only catalog-history storage lane. Do not copy mastery,
signatures, scores, usage, or other pattern aggregates into `rhetoric_defaults`. Do not
materialize catalog-derived `guardrail_sources.recurring_issues` or `badges`; consumers
derive those warnings and reinforcement directly from validated `pattern_profile`.
Every top-level recurring issue or badge is non-pattern data and carries
`source_lane: "non_pattern"`.

If `baseline_talks` is empty, emit the explicit unavailable form from
[references/speaker-profile-schema.md](references/speaker-profile-schema.md): retain
the zero-count `pattern_baseline`, use empty filenames, preserve the exhaustive
zero-opportunity rows, set both score and breadth averages to null, and use
`unavailable` for the pattern trend/direction fields. Do not reuse pattern values from
the prior profile or summary.

Compute `pacing.adherence` by running `"{python_path}" "{speaker_toolkit_root}/skills/vault-profile/scripts/compute-pacing-adherence.py"`. The
deterministic arithmetic — duration parsing, slides-per-minute, budget-band
classification, over-budget counts, rate, and trend — lives in the script per
`script-delegation`, not in this prose.

```bash
echo "$PACING_INPUT" | "{python_path}" "{speaker_toolkit_root}/skills/vault-profile/scripts/compute-pacing-adherence.py"
```

**I/O contract** (parse + budget-band rules in the script's top-of-file docstring):
- Stdin (JSON): `{"talks": [...], "slide_budgets": [...]}`. Pass each talk from
  `current_instrumentation_talks` as
  `{filename, date, slide_count, talk_duration_estimate}`, taking `slide_count` and
  `talk_duration_estimate` from the talk's `structured_data`; pass
  `guardrail_sources.slide_budgets` unchanged.
- Stdout (JSON): the `pacing.adherence` data fields (`talks_over_budget`,
  `talks_scored`, `over_budget_rate`, `trend`, `worst_offenders`). Copy them into
  `pacing.adherence`; also set `pacing.adherence.cohort` to
  `current_instrumentation_talks`. The schema's `note` is optional descriptive text
  (as elsewhere in the schema) and is not emitted by the script.
- Exit non-zero on malformed input.

This is the quantitative counterpart to Dimension 14's transcript-evident "rushing"
read. The duration estimate is approximate. Flag marginal overages softly.

Cross-check Section 15 of `rhetoric-style-summary.md` only as a narrative consistency
review. It cannot override or fill the current pattern cohort. See
[references/speaker-profile-schema.md](references/speaker-profile-schema.md)
`pattern_profile`.

Set `schema_version` to `4` and `generated_date` to today's date in `YYYY-MM-DD` form.

Proceed immediately to Step 5.

## Step 5 — Validate the Profile

Pipe the constructed profile dict through
`"{python_path}" "{speaker_toolkit_root}/skills/vault-profile/scripts/validate-profile.py" --vault-root "$VAULT_ROOT"`.
Schema-v4 owner validation reparses the live tracking database with the same shared
cohort builder as Step 1 and rejects any candidate baseline, filename set, eligible
count, or opportunity row that is not source-exact.

```bash
echo "$PROFILE_JSON" | "{python_path}" "{speaker_toolkit_root}/skills/vault-profile/scripts/validate-profile.py" --vault-root "$VAULT_ROOT"
```

**I/O contract:**
- Args: required `--vault-root <path>`; profile JSON is read from stdin when no profile
  path is supplied.
- Stdin (JSON): the profile dict.
- Stdout (JSON): `{valid, schema_version, missing_keys, errors}`.
- Exit code: `0` on valid, `1` on invalid.

If exit code is `1`, report every `missing_keys` and `errors` entry and abort without
writing. Fix the offending fields in Step 4 and rerun this step.

Proceed immediately to Step 6.

## Step 6 — Diff Against Existing Profile

If `{vault_root}/speaker-profile.json` already exists, compare
`pattern_profile.pattern_baseline.pattern_catalog_fingerprint` and
`pattern_profile.pattern_baseline.pattern_scoring_schema_version` first. If either identity differs, report a pattern
generation reset and do not classify any catalog-derived score, trend, usage, mastery,
or strength difference across that boundary as a regression.

Within the same exact pattern generation, diff non-pattern profile data. Do not report
raw-score movement across a changed or unavailable
`pattern_baseline.opportunity_coverage_identity`, and do not infer policy-derived
pattern changes while `classification_availability.status` is `unavailable`. Report to
the speaker:
- New instruments added to `instrument_catalog`
- Revised thresholds in `guardrail_sources`
- New non-pattern guardrails added to `recurring_issues`
- A worsening `pacing.adherence.trend` or a rising `over_budget_rate` — the speaker is increasingly running long.
- **New presentation modes** — flag prominently (the highest-signal field change for creator-skill behavior).

If no prior profile exists, skip this step and proceed.

Proceed immediately to Step 7.

## Step 7 — Save the Profile

Write the validated profile to `{vault_root}/speaker-profile.json` with 2-space indentation. Confirm: `"speaker-profile.json written — {N} talks, {M} confirmed intents."`

Proceed immediately to Step 8.

## Step 8 — Generate Achievement Badges

Generate fun, self-deprecating non-pattern achievements grounded in pacing, visual,
publishing, talk-count, or confirmed-intent data (for example, a visual-continuity or
slide-budget badge). Do not generate a badge from catalog pattern usage, mastery,
strength, antipattern, score, or absence; that reinforcement already lives in
`pattern_profile`. Set `source_lane: "non_pattern"` on every badge. The tone should
sound like the speaker's own voice, not corporate gamification. Append the array,
rerun Step 5 validation on the final profile, then re-save only if it remains valid.

Finish here.
