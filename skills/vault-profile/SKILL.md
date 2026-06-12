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

Generate or update `speaker-profile.json` from vault data. This profile is the
structured bridge between the vault and the presentation-creator skill.

The vault lives at `~/.claude/rhetoric-knowledge-vault/` (may be a symlink).
Read `tracking-database.json` from there to get `vault_root`.

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
| `scripts/validate-profile.py` | Validate profile required keys + `schema_version` |
| `scripts/compute-pacing-adherence.py` | Compute `pacing.adherence` from scored talks + slide budgets |

## Prerequisites

- **10+ talks parsed** AND `config.clarification_sessions_completed >= 1`.
- Also runs on explicit request (overrides prerequisites).
- Auto-triggered by vault-ingress Step 7 (Regenerate Speaker Profile) if profile already exists.

Process the steps below in order; each step's output (vault payload, aggregated data, validated profile) feeds the next. Do not skip ahead.

## Step 1 — Load Vault Sources

Run `scripts/load-vault.py` to read `tracking-database.json`, `rhetoric-style-summary.md`, and `slide-design-spec.md` from the vault root. The script emits a single JSON payload on stdout.

```bash
python3 skills/vault-profile/scripts/load-vault.py > /tmp/vault-payload.json
```

**I/O contract:**
- Args: optional vault-root path; defaults to `~/.claude/rhetoric-knowledge-vault`.
- Stdout (JSON): `{vault_root, config, confirmed_intents, talks, processed_talks, summary, design_spec}`.
- Exit non-zero with stderr message if `tracking-database.json` or `rhetoric-style-summary.md` are missing or malformed.

If the script aborts on missing `rhetoric-style-summary.md`, run vault-ingress first. If `slide-design-spec.md` is missing, `design_spec` is `""` and the design-spec section of the profile remains empty — continue without aborting.

Proceed immediately to Step 2.

## Step 2 — Aggregate Structured Data

Aggregate `structured_data` from `processed_talks` in the Step 1 payload. Skip talks with empty `structured_data`; for those, fall back to prose extraction from `summary` (the `rhetoric-style-summary.md` contents) for the matching dimensions.

If **all** processed talks have empty `structured_data`, warn the speaker and fall back entirely to prose extraction. Continue.

Proceed immediately to Step 3.

## Step 3 — Extract Template Layouts

If `config.template_pptx_path` is set, call the vault-ingress PPTX extraction script:

```bash
python3 skills/vault-ingress/scripts/pptx-extraction.py "$TEMPLATE_PPTX_PATH" > /tmp/template-layouts.json
```

**I/O contract** (defined in vault-ingress; see `skills/vault-ingress/scripts/pptx-extraction.py`):
- Args: path to a `.pptx` file.
- Stdout (JSON): per-slide visual data, shape types, global design stats, and the master layouts list under the top-level `template_layouts` key. Each layout entry has `{index, master_index, name, placeholders: [{idx, type}]}`.
- Exit non-zero with stderr message if the file is missing, unreadable, or not a valid `.pptx`.

Merge the resulting layouts list into `infrastructure.template_layouts` in the profile being constructed. The script emits structural fields (`index`, `master_index`, `name`, `placeholders`); the `use_for` field is speaker-curated and is **not** emitted. When merging, key by the `(master_index, name)` pair — PowerPoint allows the same layout name to appear under different slide masters, so name alone is insufficient. For each fresh layout, copy any existing `use_for` value from the prior profile's matching `(master_index, name)` entry. Layouts present in the prior profile but absent from the fresh extraction are dropped — the script is the source of truth for layout existence. If `template_pptx_path` is not set, leave `template_layouts` as an empty list and continue.

Proceed immediately to Step 4.

## Step 4 — Construct the Profile

Construct the `speaker-profile.json` dict per [references/speaker-profile-schema.md](references/speaker-profile-schema.md). Map vault sources to profile sections:

| Profile section | Source |
|---|---|
| `speaker` / `infrastructure` | `config` (from Step 1 payload) |
| `presentation_modes` / `instrument_catalog` | `summary` sections (from Step 1 payload) |
| `rhetoric_defaults` | `confirmed_intents` (from Step 1 payload) |
| `pacing` / `guardrail_sources` | aggregated `structured_data` (from Step 2) |
| `pattern_profile` | `pattern_observations` across `processed_talks` |
| `visual_style_history` | dimension 13f observations from `summary` |

Top-level keys (full nested schema in [references/speaker-profile-schema.md](references/speaker-profile-schema.md)):

```
schema_version, generated_date, talks_analyzed, speaker, infrastructure,
presentation_modes, instrument_catalog, rhetoric_defaults, confirmed_intents,
guardrail_sources, pacing, pattern_profile, visual_style_history,
publishing_process, design_rules, badges
```

When building `pattern_profile`, attribute `score_trend` instead of leaving it a
bare label. A declining score has two symmetric causes — bad things present and
good things absent — and `score_drivers` MUST name whichever moved:
- **Antipatterns rising** — every `antipattern_frequency` entry with `trend` `increasing`.
- **Patterns fading or breadth narrowing** — every `pattern_usage` entry with `trend`
  `decreasing` (signature OR regular), and a `pattern_breadth.trend` of `narrowing`,
  which drives a decline even when no single pattern fades. Underuse alone can lower
  the score with zero antipatterns.

Also compute `pattern_breadth` (average distinct observable patterns per talk +
trend) and `underused_patterns` — the union of `never_used_patterns` with the
patterns in the `never_tried` and `rare` tiers of `mastery_levels`, kept only where
the pattern's taxonomy Vault Dims fit the speaker's `presentation_modes`. This is the
positive-space coaching signal, framed as growth, not deficiency.

Compute `pattern_profile.by_mode` — the per-mode baseline. The tracking DB has no
per-talk mode field. Assign each `processed_talk` to the `presentation_modes` entry
whose `when_to_use` best matches the talk's `structured_data` — `slide_count` and
`meme_count` density, `audience_interaction_count`, `opening_type`,
`narrative_arc_type`, and `slide_design_style`. This assignment is a classification
judgment, not a stored value — it stays LLM-side. Then, for each mode with **≥3 assigned talks**, emit
`average_pattern_score`, `avg_distinct_patterns_per_talk`, `top_antipatterns`, and
`stable: true`. Modes below 3 talks are omitted (or `stable: false`); consumers fall
back to the global baseline. This prevents false underuse findings when a short-format
mode is judged against a keynote baseline.

Compute `pattern_profile.strengths` — the speaker's signature patterns (from
`mastery_levels.signature`) and `signature_combinations`, each with a `lean_in` line.
This is the positive-space counterpart to `recurring_issues`/`underused_patterns`;
keep it distinct from Step 8 badges (badges are celebratory, strengths are actionable
reinforcement the creator skill amplifies).

Compute `pacing.adherence` by running `scripts/compute-pacing-adherence.py`. The
deterministic arithmetic — duration parsing, slides-per-minute, budget-band
classification, over-budget counts, rate, and trend — lives in the script per
`script-delegation`, not in this prose.

```bash
echo "$PACING_INPUT" | python3 skills/vault-profile/scripts/compute-pacing-adherence.py
```

**I/O contract** (parse + budget-band rules in the script's top-of-file docstring):
- Stdin (JSON): `{"talks": [...], "slide_budgets": [...]}`. Pass each scored talk as
  `{filename, date, slide_count, talk_duration_estimate}`, taking `slide_count` and
  `talk_duration_estimate` from the talk's `structured_data`; pass
  `guardrail_sources.slide_budgets` unchanged.
- Stdout (JSON): the `pacing.adherence` object (`talks_over_budget`, `talks_scored`,
  `over_budget_rate`, `trend`, `worst_offenders`). Copy it into `pacing.adherence`.
- Exit non-zero on malformed input.

This is the quantitative counterpart to Dimension 14's transcript-evident "rushing"
read. The duration estimate is approximate. Flag marginal overages softly.

Cross-check against Section 15 of `rhetoric-style-summary.md`, which carries the same
baselines in prose. See
[references/speaker-profile-schema.md](references/speaker-profile-schema.md)
`pattern_profile`.

Set `schema_version` to `2` and `generated_date` to today's date in `YYYY-MM-DD` form.

Proceed immediately to Step 5.

## Step 5 — Validate the Profile

Pipe the constructed profile dict through `scripts/validate-profile.py` to verify all required top-level keys exist and `schema_version` is `2`.

```bash
echo "$PROFILE_JSON" | python3 skills/vault-profile/scripts/validate-profile.py
```

**I/O contract:**
- Stdin (JSON): the profile dict.
- Stdout (JSON): `{valid, schema_version, missing_keys}`.
- Exit code: `0` on valid, `1` on invalid.

If exit code is `1`, list every missing key from the script output and abort without writing. Fix the offending fields in Step 4 and rerun this step.

Proceed immediately to Step 6.

## Step 6 — Diff Against Existing Profile

If `{vault_root}/speaker-profile.json` already exists, diff the new profile against it. Report to the speaker:
- New instruments added to `instrument_catalog`
- Revised thresholds in `guardrail_sources`
- New guardrails added to `recurring_issues`
- Shifts in `pattern_profile.score_drivers` — a newly `declining` direction, a new `antipattern_drivers` entry with a rising `frequency_trend`, or a `pattern_breadth.trend` flipping to `narrowing` (using fewer of the toolkit) is a regression signal worth flagging.
- A worsening `pacing.adherence.trend` or a rising `over_budget_rate` — the speaker is increasingly running long.
- **New presentation modes** — flag prominently (the highest-signal field change for creator-skill behavior).

If no prior profile exists, skip this step and proceed.

Proceed immediately to Step 7.

## Step 7 — Save the Profile

Write the validated profile to `{vault_root}/speaker-profile.json` with 2-space indentation. Confirm: `"speaker-profile.json written — {N} talks, {M} confirmed intents."`

Proceed immediately to Step 8.

## Step 8 — Generate Achievement Badges

Generate fun, self-deprecating achievements grounded in real vault data (e.g., `"Narrative Arc Master 22/24"`, `"Pattern Polyglot 12+ patterns"`). The badge tone matters: badges should sound like the speaker's own voice, not corporate gamification. Append the resulting array to the profile's `badges` field and re-save.

Finish here.
