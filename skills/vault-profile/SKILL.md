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

## Prerequisites

- **10+ talks parsed** AND `config.clarification_sessions_completed >= 1`.
- Also runs on explicit request (overrides prerequisites).
- Auto-triggered by vault-ingress Step 7 (Regenerate Speaker Profile) if profile already exists.

## Process

1. **Read source files.** Load `rhetoric-style-summary.md`, `slide-design-spec.md`, and `confirmed_intents` from `tracking-database.json`.

   ```python
   import json, pathlib

   vault_root = pathlib.Path("~/.claude/rhetoric-knowledge-vault").expanduser().resolve()
   db = json.loads((vault_root / "tracking-database.json").read_text())
   config = db.get("config", {})
   confirmed_intents = db.get("confirmed_intents", [])
   talks = db.get("talks", [])
   processed = [t for t in talks if t.get("status") in ("processed", "processed_partial")]

   summary_path = vault_root / "rhetoric-style-summary.md"
   if not summary_path.exists():
       raise SystemExit("No rhetoric summary found. Run vault-ingress first to process talks.")
   summary = summary_path.read_text()

   design_spec_path = vault_root / "slide-design-spec.md"
   design_spec = design_spec_path.read_text() if design_spec_path.exists() else ""
   ```

   - If `rhetoric-style-summary.md` is missing, abort with the message above.
   - If `slide-design-spec.md` is missing, the design-spec section of the profile remains empty (continue without aborting).
   - If all processed talks have empty `structured_data`, warn and fall back to prose extraction from the summary.

2. **Aggregate `structured_data`** from the processed talks. Skip talks with empty `structured_data`; for those, fall back to prose extraction from `rhetoric-style-summary.md` for the matching dimensions.

3. **Extract slide-template layouts** if `config.template_pptx_path` is set. Call the vault-ingress PPTX extraction script (`skills/vault-ingress/scripts/pptx-extraction.py <path.pptx>`); store the layouts list under `infrastructure.template_layouts`.

4. **Generate `speaker-profile.json`** per [references/speaker-profile-schema.md](references/speaker-profile-schema.md). The mapping from vault sources to profile sections:

   | Profile section | Source |
   |---|---|
   | `speaker` / `infrastructure` | `tracking-database.json` `config` block |
   | `presentation_modes` / `instrument_catalog` | `rhetoric-style-summary.md` sections |
   | `rhetoric_defaults` | `confirmed_intents` |
   | `pacing` / `guardrail_sources` | aggregated `structured_data` from step 2 |
   | `pattern_profile` | `pattern_observations` across processed talks |
   | `visual_style_history` | dimension 13f observations |

   Top-level keys (full nested schema in [references/speaker-profile-schema.md](references/speaker-profile-schema.md)):

   ```
   schema_version, generated_date, talks_analyzed, speaker, infrastructure,
   presentation_modes, instrument_catalog, rhetoric_defaults, confirmed_intents,
   guardrail_sources, pacing, pattern_profile, visual_style_history,
   publishing_process, design_rules, badges
   ```

5. **Validate.** Verify all required top-level keys exist and `schema_version` is 1. If validation fails, list every missing or invalid key and abort without writing. Pass the profile dict produced in step 4 to `validate_profile()`:

   ```python
   def validate_profile(profile):
       REQUIRED_KEYS = [
           "schema_version", "generated_date", "talks_analyzed", "speaker",
           "infrastructure", "presentation_modes", "instrument_catalog",
           "rhetoric_defaults", "confirmed_intents", "guardrail_sources",
           "pacing", "pattern_profile", "visual_style_history",
           "publishing_process", "design_rules", "badges",
       ]
       missing = [k for k in REQUIRED_KEYS if k not in profile]
       if missing or profile.get("schema_version") != 1:
           raise ValueError(f"Profile invalid — missing: {missing}, "
                            f"schema_version: {profile.get('schema_version')}")
   ```

6. **Diff against the existing profile** at `{vault_root}/speaker-profile.json` (if present). Report changes — new instruments, revised thresholds, new guardrails — to the speaker. **Flag new presentation modes prominently** since they affect creator-skill behavior more than other field changes.

7. **Save** to `{vault_root}/speaker-profile.json` with 2-space indentation. Confirm: `"speaker-profile.json written — {N} talks, {M} confirmed intents."`

8. **Generate speaker badges** — fun, self-deprecating achievements grounded in real vault data (e.g., `"Narrative Arc Master 22/24"`, `"Pattern Polyglot 12+ patterns"`). The badge tone matters: badges should sound like the speaker's own voice, not corporate gamification. Append the resulting array to the profile's `badges` field and re-save.
