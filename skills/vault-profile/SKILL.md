---
name: vault-profile
description: >
  Generates or updates the structured speaker-profile.json from vault data. Aggregates
  rhetoric summary, slide design spec, confirmed intents, and structured talk data into
  a machine-readable profile used by the presentation-creator skill. Also generates
  speaker achievement badges.
  Triggers: "generate speaker profile", "update speaker profile",
  "regenerate speaker profile", "sync speaker profile".
user-invocable: true
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
Set `host_python` to the current host's explicit absolute interpreter path (not
a PATH lookup). The sole interpreter-bootstrap exception is one stdlib-only
strict-owner read:

```bash
"{host_python}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/read-tracking-database.py" \
  "~/.claude/rhetoric-knowledge-vault/tracking-database.json"
```

Use its JSON report to resolve `vault_root` and the exact non-empty
`database.config.python_path`. Set `python_path` to that value, then immediately
repeat the same owner-read command with `"{python_path}"` and the resolved
`{vault_root}/tracking-database.json`; require its database and SHA-256 to match
the bootstrap report. The unconfigured `host_python` above is authorized for
that one owner-reader invocation only, never for another toolkit script.
If vault-ingress Step 7 invoked this skill, accept its resolved `{vault_root}`
and `{python_path}` as handoff context, then re-read the database and require the stored value to match.
Before running any other toolkit script, read `config.python_path` from that tracking
database and set `python_path` to that exact value. It is the interpreter
authority for every operational command in this skill.
If `python_path` is absent, empty, mismatched, or cannot execute the core runtime
probe below, stop and direct the speaker to vault-ingress Step 1 to repair the
configuration. Never fall back to whichever `python3` happens to be on `PATH`.

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/check-runtime.py" \
  --lanes core,pptx --require-lanes core
```

## Required References

- Read [profile-construction-rules.md](references/profile-construction-rules.md)
  before Steps 2, 4, and 6. It owns cohort use, merge rules, fail-closed edge cases,
  and diff semantics.
- Use [speaker-profile-schema.md](references/speaker-profile-schema.md) for the full
  JSON shape and [schemas-config.md](references/schemas-config.md) for config and
  confirmed intents.
- Treat `tracking-database.json` as source of truth and `speaker-profile.json` as the
  output. Toolkit scripts, not prose, own cohort, opportunity, classification, pacing,
  and validation arithmetic.

## Prerequisites

- **10+ talks parsed** AND `config.clarification_sessions_completed >= 1`.
- Also runs on explicit request (overrides prerequisites).
- Auto-triggered by vault-ingress Step 7 (Regenerate Speaker Profile) if profile already exists.

If any talk declares a preserved local recording through
`structured_data.video_extraction.source_video_path`, `video_local_path`, or
`video_path`, first require the configured interpreter's source-video evidence
lane:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/check-runtime.py" \
  --lanes core,source-video --require-lanes core,source-video
```

This check gates the load and validation commands below, which may inspect that
recording while assessing artifact freshness. Let the toolkit scripts perform
the bounded, exact-generation probe; do not pre-open, hash, hydrate, or invoke
`ffprobe` on a source recording directly. Use `source-video` for evidence over
an existing recording and the separate `video` lane only for frame extraction.
If a recording cannot be verified, only source-video capability is removed;
independently verified transcript, PDF, and PPTX evidence remains valid.

## Step 1 — Load Vault Sources

Load `tracking-database.json`, `rhetoric-style-summary.md`, and
`slide-design-spec.md` into one payload:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-profile/scripts/load-vault.py" \
  "{vault_root}" > /tmp/vault-payload.json
```

**I/O contract:**

- Args: optional vault-root path and optional timezone-aware `--as-of` timestamp;
  defaults are documented in the script's top-of-file contract.
- Stdout (JSON): `{vault_root, config, confirmed_intents, talks, processed_talks,
  baseline_talks, excluded_pattern_scoring_talks, pattern_scoring_exclusions,
  pattern_baseline, pattern_opportunities, pattern_classification,
  current_instrumentation_talks,
  stale_instrumentation_talks, baseline_note, instrumentation_note, summary,
  design_spec}`.
- Exit non-zero with stderr message if arguments, vault sources, catalog identity,
  scoring-generation metadata, or a present classification-policy override is invalid.

Apply the loader and missing-source rules in the construction reference.

Proceed immediately to Step 2.

## Step 2 — Aggregate Structured Data

Aggregate the three named cohorts exactly as defined in
[profile-construction-rules.md](references/profile-construction-rules.md). Keep
catalog, non-catalog, and pacing sources separate. Copy the deterministic
`pattern_opportunities` and `pattern_classification` payloads; never recalculate either.

Proceed immediately to Step 3.

## Step 3 — Extract Template Layouts

If `config.template_pptx_path` is set, require the configured interpreter's PPTX lane,
then extract layouts. An unavailable lane blocks extraction and must not be replaced
with another interpreter:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/check-runtime.py" \
  --lanes core,pptx --require-lanes core,pptx
```

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/pptx-extraction.py" \
  "$TEMPLATE_PPTX_PATH" > /tmp/template-layouts.json
```

**I/O contract:**

- Args: path to a `.pptx` file.
- Stdout (JSON): per-slide visual data, shape types, global design stats, and
  `template_layouts`; each layout has
  `{index, master_index, name, placeholders: [{idx, type}]}`.
- Exit non-zero with stderr message if the file is missing, unreadable, or not a valid `.pptx`.

Apply the extraction-version and `(master_index, name)` merge rules in the
construction reference. If no template path is configured, emit an empty layout list.

Proceed immediately to Step 4.

## Step 4 — Construct the Profile

Read [profile-construction-rules.md](references/profile-construction-rules.md) in full,
then construct `speaker-profile.json` with the exact field ownership, cohort,
classification, empty-cohort, and non-pattern provenance rules there. Use
[speaker-profile-schema.md](references/speaker-profile-schema.md) for the complete
schema. Copy deterministic baseline, opportunity, policy stamp, availability, and
derived classification data; do not infer or recalculate catalog history. Regenerating
these profile fields reads existing tracking rows and does not reparse any talk.

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

Set `schema_version` to `5` and `generated_date` to today's date in `YYYY-MM-DD` form.

Proceed immediately to Step 5.

## Step 5 — Validate the Profile

Pipe the constructed profile dict through
`"{python_path}" "{speaker_toolkit_root}/skills/vault-profile/scripts/validate-profile.py" --vault-root "$VAULT_ROOT"`.
Schema-v5 owner validation rereads the live tracking database with the same shared
cohort/classification builders as Step 1 and rejects any candidate baseline, filename
set, opportunity row, policy stamp/digest, availability domain, or derived row that is
not source-exact. This is database re-analysis, not talk reparsing; raw persisted talk
rows remain unchanged.

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

If `{vault_root}/speaker-profile.json` exists, apply the generation-boundary and
same-generation reporting rules in
[profile-construction-rules.md](references/profile-construction-rules.md). If no prior
profile exists, skip the diff.

Proceed immediately to Step 7.

## Step 7 — Save the Profile

Write the validated profile to `{vault_root}/speaker-profile.json` with 2-space indentation. Confirm: `"speaker-profile.json written — {N} talks, {M} confirmed intents."`

Proceed immediately to Step 8.

## Step 8 — Generate Achievement Badges

Generate badges under the non-pattern provenance rules in the construction reference.
Append the array, rerun Step 5 validation, and re-save only when the final profile is
valid.

Finish here.
