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

1. Read `rhetoric-style-summary.md`, `slide-design-spec.md`, and `confirmed_intents`.
   - If `rhetoric-style-summary.md` is missing, abort with: "No rhetoric summary found.
     Run vault-ingress first to process talks."
   - If all talks have empty `structured_data`, warn and fall back to prose extraction.
2. Aggregate `structured_data` from processed talks (skip empty, fall back to prose).
3. If `template_pptx_path` is set, extract slide layouts via python-pptx.
   See the pptx-extraction script (in vault-ingress references) for the approach.
4. Generate `speaker-profile.json` per [references/speaker-profile-schema.md](references/speaker-profile-schema.md).
   Map config → `speaker`/`infrastructure`, summary sections →
   `instrument_catalog`/`presentation_modes`, confirmed intents →
   `rhetoric_defaults`, aggregated data → `pacing`/`guardrail_sources`,
   pattern observations → `pattern_profile`, illustration style observations
   (dimension 13f) → `visual_style_history`.

   The output must include these top-level sections with their expected structure:
   ```json
   {
     "schema_version": 1,
     "generated_date": "YYYY-MM-DD",
     "speaker": { "name": "...", "handle": "...", "website": "...", "bio_short": "..." },
     "infrastructure": {
       "template_pptx_path": "...", "template_layouts": [],
       "presentation_file_convention": "..."
     },
     "presentation_modes": [
       { "id": "...", "name": "...", "when_to_use": "...", "description": "..." }
     ],
     "instrument_catalog": {
       "opening_patterns": [{ "name": "...", "best_for": "...", "examples": [] }],
       "narrative_structures": [{ "name": "...", "acts": [], "time_allocation": {} }],
       "humor_techniques": [], "closing_patterns": [], "verbal_signatures": []
     },
     "rhetoric_defaults": {
       "profanity_calibration": "...", "on_slide_profanity": "...",
       "default_duration_minutes": 45, "three_part_close": true,
       "modular_design": true
     },
     "confirmed_intents": [],
     "guardrail_sources": {
       "slide_budgets": [{ "duration_min": 45, "max_slides": 70, "slides_per_min": 1.5 }],
       "act1_ratio_limits": [{ "duration_range": "20-30", "max_percent": 40 }],
       "recurring_issues": [{ "pattern": "...", "severity": "...", "guardrail": "..." }]
     },
     "pacing": { "wpm_range": [140, 170], "slides_per_minute": 1.5 },
     "pattern_profile": {
       "pattern_usage": [{ "pattern_id": "...", "times_used": 22, "mastery_level": "signature" }],
       "antipattern_frequency": [{ "pattern_id": "...", "times_detected": 8, "severity": "recurring" }],
       "never_used_patterns": ["..."]
     },
     "visual_style_history": {
       "default_illustration_style": "...", "style_departures": [],
       "mode_visual_profiles": [], "confirmed_visual_intents": []
     },
     "publishing_process": {
       "export_format": "pdf", "export_method": "...",
       "shownotes_publishing": {}, "qr_code": {}, "additional_steps": []
     },
     "design_rules": {
       "background_color_strategy": "...", "footer": { "pattern": "...", "elements": [] },
       "slide_numbers": "never", "default_bullet_symbol": "..."
     },
     "badges": []
   }
   ```
   See [references/speaker-profile-schema.md](references/speaker-profile-schema.md) for the complete schema
   with all fields and descriptions.
5. **Validate** — verify all required top-level keys exist and `schema_version` is 1.
   If validation fails, fix and retry before saving.
6. Diff against existing profile; report changes (new instruments, revised thresholds,
   new guardrails). Flag new presentation modes prominently.
7. Save to `{vault_root}/speaker-profile.json`.
8. **Generate speaker badges** — fun, self-deprecating achievements grounded in real
   vault data (e.g., "Narrative Arc Master 22/24", "Pattern Polyglot 12+ patterns").
