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

## Prerequisites

- **10+ talks parsed** AND `config.clarification_sessions_completed >= 1`.
- Also runs on explicit request (overrides prerequisites).
- Auto-triggered by vault-ingress Step 7 (Regenerate Speaker Profile) if profile already exists.

Process the steps below in order; each step's output (vault payload, aggregated data, validated profile) feeds the next. Do not skip ahead.

## Step 1 — Load Vault Sources

Run `scripts/load-vault.py` to read `tracking-database.json`, `rhetoric-style-summary.md`, and `slide-design-spec.md` from the vault root. The script emits a single JSON payload on stdout.

```bash
python3 scripts/load-vault.py > /tmp/vault-payload.json
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
python3 ../vault-ingress/scripts/pptx-extraction.py "$TEMPLATE_PPTX_PATH"
```

Store the layouts list under `infrastructure.template_layouts` in the profile being constructed. If `template_pptx_path` is not set, leave `template_layouts` as an empty list and continue.

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

Set `schema_version` to `1` and `generated_date` to today's date in `YYYY-MM-DD` form.

Proceed immediately to Step 5.

## Step 5 — Validate the Profile

Pipe the constructed profile dict through `scripts/validate-profile.py` to verify all required top-level keys exist and `schema_version` is `1`.

```bash
echo "$PROFILE_JSON" | python3 scripts/validate-profile.py
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
- **New presentation modes** — flag prominently since they affect creator-skill behavior more than other field changes.

If no prior profile exists, skip this step and proceed.

Proceed immediately to Step 7.

## Step 7 — Save the Profile

Write the validated profile to `{vault_root}/speaker-profile.json` with 2-space indentation. Confirm: `"speaker-profile.json written — {N} talks, {M} confirmed intents."`

Proceed immediately to Step 8.

## Step 8 — Generate Achievement Badges

Generate fun, self-deprecating achievements grounded in real vault data (e.g., `"Narrative Arc Master 22/24"`, `"Pattern Polyglot 12+ patterns"`). The badge tone matters: badges should sound like the speaker's own voice, not corporate gamification. Append the resulting array to the profile's `badges` field and re-save.

Finish here.
