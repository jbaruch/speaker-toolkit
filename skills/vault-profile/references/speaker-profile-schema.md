# Speaker Profile Schema

The speaker profile (`speaker-profile.json`) is the machine-readable bridge between
the rhetoric-knowledge-vault (analysis) and the presentation-creator skill
(generation). It lives in the vault root alongside `rhetoric-style-summary.md` and
`slide-design-spec.md`.

The narrative summary is the *constitution* (rich, prose, nuanced). The speaker profile
is the *specification* (structured, extractable, actionable). Both are needed — the
profile cannot replace the summary, but the summary alone cannot drive presentation
creation at runtime.

## When to Generate

- **First generation:** After 10+ talks are parsed AND the clarification session has
  resolved key ambiguities (presentation modes, deliberate vs accidental patterns,
  confirmed design rules).
- **Updates:** After each subsequent vault run (new talks parsed or new PPTX extractions),
  the profile should be regenerated to incorporate new data.
- **Manual trigger:** The user can request "update speaker profile" at any time.

## Schema Versioning

Current `schema_version`: **4**. The validator (`scripts/validate-profile.py`,
`CURRENT_SCHEMA_VERSION`) accepts only the current version.

- **v1 → v2** adds the coaching-outcome fields, all additive: `pattern_profile.score_drivers`,
  `pattern_breadth`, `underused_patterns`, `by_mode`, `strengths`/`strengths_note`, and
  `pacing.adherence`.
- **v2 → v3** makes the Presentation Pattern cohort auditable. It adds the canonical
  `pattern_profile.pattern_baseline` snapshot and exact sorted
  `baseline_talk_filenames`, and requires every catalog-derived denominator to use that
  cohort. This is a generation boundary, not an additive coaching field.
- **v3 → v4** binds occurrence history to scoring-v5's exhaustive per-talk outcomes.
  It separates `eligible_talk_count` from raw-score-comparable `talks_scored`, adds
  exact per-pattern opportunity denominators and coverage, and makes classification
  availability explicit. Until a speaker-owned classification policy is versioned,
  all novelty, mastery, recurring-severity, underuse, combination, and trend fields
  use fail-closed sentinels.
- **Generation:** vault-profile writes only v4. Stored v1/v2/v3 profiles are non-current and
  `scripts/validate-profile.py` rejects them as generation output. Compatibility for
  non-owner readers is a separate rollout concern; an old profile never authorizes the
  writer to reuse legacy pattern aggregates.
- **Migration:** vault-profile regenerates the profile wholesale each run. An older file is
  replaced by a v4 file on the next run — no in-place migration step. The only value carried
  across regenerations is `infrastructure.template_layouts[].use_for` (merged by the
  `(master_index, name)` pair, version-independent).
- **Generation reset:** when either the catalog fingerprint or pattern-scoring schema
  changes, catalog-derived diffs across the boundary are a reset. Do not describe score,
  usage, mastery, or trend changes across those identities as speaker regressions.

## Schema

```json
{
  "schema_version": 4,
  "generated_date": "2026-02-22",
  "talks_analyzed": 24,

  "speaker": {
    "name": "",
    "handle": "",
    "website": "",
    "bio_short": "one-sentence bio used on slides",
    "bio_context": "career trajectory or credentials chain shown on bio slides"
  },

  "infrastructure": {
    "template_pptx_path": "/path/to/template.pptx",
    "template_name": "human-readable name for the template",
    "template_layouts": [
      {
        "index": 0,
        "master_index": 0,
        "name": "TITLE",
        "placeholders": [{"idx": 0, "type": "CENTER_TITLE"}],
        "use_for": "opening title slide, section dividers"
      }
    ],
    // template_layouts: structural fields (index, master_index, name,
    // placeholders) come from skills/vault-ingress/scripts/pptx-extraction.py.
    // The use_for field is speaker-curated and persists across
    // regenerations; the vault-profile aggregator merges fresh structural
    // data with prior use_for values by keying on the (master_index, name)
    // pair — name alone is unsafe because PowerPoint permits identical
    // layout names under different masters.
    "presentation_file_convention": "{presentations_dir}/{conference}/{year}/{talk-slug}/",
    "font_pair": {
      "title": {"name": "", "source": "google_fonts|system|custom"},
      "body": {"name": "", "source": "google_fonts|system|custom"},
      "code": {"name": "", "source": "google_fonts|system|custom", "optional": true}
    },
    "slide_dimensions": {"width_inches": 10.0, "height_inches": 5.63, "aspect": "16:9"}
  },

  "presentation_modes": [
    {
      "id": "a",
      "name": "human-readable mode name",
      "description": "1-2 sentence description of this mode",
      "when_to_use": "what spec signals suggest this mode",
      "slide_density_per_min": 1.4,
      "meme_density_per_slide": 0.24,
      "humor_register": "none|light|moderate|heavy",
      "audience_interaction": true,
      "anti_sell_applicable": true,
      "commercial_intent": "none|subtle|direct",
      "profanity_default": "zero|moderate|heavy",
      "closing_default": "name of default closing pattern for this mode",
      "typical_engine": "pptx|presenterm — optional; the engine this mode usually renders in"
    }
  ],

  "presentation_engines": [
    {
      "id": "pptx",
      "name": "human-readable engine name",
      "renderer": "pptx|presenterm",
      "when_to_use": "what spec signals suggest this engine",
      "default_theme": "theme/template name for this engine, or null",
      "usage_count": 18,
      "out_of": 24
    }
  ],

  "design_rules": {
    "background_color_strategy": "random_non_repeating|theme_sequence|mode_dependent",
    "background_color_pool": "description of which colors to pick from",
    "background_adjacent_repeat": false,
    "white_black_reserved_for": "full-bleed image/meme slides only",
    "slide_numbers": "never|always|optional",
    "footer": {
      "always_present": true,
      "pattern": "the footer template string with placeholders",
      "elements": ["@handle", "#conference", "#topic", "website"],
      "co_presented_extra": "co-presenter handle position and rule",
      "font": "",
      "font_size_pt": 16,
      "position": {"left": 0.01, "top": 5.22, "width": 10.0, "height": 0.37},
      "color_adapts_to_background": true,
      "outline_for_legibility": true
    },
    "memes_always_full_bleed": true,
    "default_bullet_symbol": "multiplication_sign|dash|circle|custom",
    "contextual_bullet_symbols": true,
    "corporate_watermark": "never|always|conditional",
    "section_dividers": "text_cue|numbered_slide|color_change|none"
  },

  "rhetoric_defaults": {
    "default_duration_minutes": 45,
    "modular_design": true,
    "default_opening": "description of the default opening pattern",
    "delayed_self_intro": {"enabled": true, "brief_bio_slide": 3, "full_reintro": "mid-talk"},
    "profanity_calibration": "per_audience|fixed|none",
    "on_slide_profanity": "never_default|needs_explicit_approval",
    "anti_sell_pattern": true,
    "three_part_close": true,
    "shownotes_slide_position": "early (slide 4-5)"
  },

  "confirmed_intents": [
    {
      "schema_version": 1,
      "pattern": "name of the pattern",
      "intent": "deliberate",
      "rule": "what the presentation-creator should do about it",
      "note": "additional context from the speaker"
    }
  ],

  "pacing": {
    "wpm_range": {"min": 127, "max": 162, "comfortable": 135},
    "slides_per_minute": {"comfortable": 1.4, "max": 1.5},
    "meme_section_pace": "30-40 sec/slide",
    "data_section_pace": "60-90 sec/slide",
    "demo_pace": "minimal slides, live tool is the content",
    "adherence": {
      "cohort": "current_instrumentation_talks",
      "talks_over_budget": 5,
      "talks_scored": 24,
      "over_budget_rate": 0.21,
      "trend": "improving|stable|worsening",
      "worst_offenders": [
        {"filename": "2024-04-10-talk-slug.md", "slides_per_minute": 2.1, "budget_slides_per_minute": 1.5, "over_by": "40%"}
      ],
      "note": "Quantitative time/slide pacing, computed by scripts/compute-pacing-adherence.py from the separately named current_instrumentation_talks cohort. It uses each talk's structured_data.slide_count and structured_data.talk_duration_estimate vs guardrail_sources.slide_budgets. This is not the Presentation Pattern cohort and its talks_scored may differ from pattern_profile.talks_scored. Duration parsing and budget-band selection live in that script's docstring. Distinct from the qualitative 'rushing' read in vault Dimension 14 (transcript-evident time panic) — this is the corpus-level count. The duration estimate is transcript-derived and approximate; treat marginal overages as soft signals, not hard failures."
    }
  },

  "guardrail_sources": {
    "slide_budgets": [
      {"duration_min": 20, "max_slides": 30, "slides_per_min": 1.5},
      {"duration_min": 30, "max_slides": 45, "slides_per_min": 1.5},
      {"duration_min": 45, "max_slides": 70, "slides_per_min": 1.5},
      {"duration_min": 60, "max_slides": 90, "slides_per_min": 1.5},
      {"duration_min": 75, "max_slides": 110, "slides_per_min": 1.5},
      {"duration_min": 90, "max_slides": 130, "slides_per_min": 1.4}
    ],
    "act1_ratio_limits": [
      {"duration_range": "20-30 min", "max_percent": 40},
      {"duration_range": "45 min", "max_percent": 45},
      {"duration_range": "60+ min", "max_percent": 50},
      {"duration_range": "75+ min", "max_percent": 65}
    ],
    "recurring_issues": [
      {
        "id": "short_identifier",
        "source_lane": "non_pattern",
        "description": "what tends to go wrong",
        "guardrail": "specific check or rule to prevent it",
        "severity": "hard_limit|warning|info"
      }
    ]
  },

  "instrument_catalog": {
    "opening_patterns": [
      {
        "code": "a",
        "name": "",
        "best_for": "when to use this pattern",
        "description": "1-2 sentences on how it works",
        "frequency": 0
      }
    ],
    "narrative_structures": [
      {
        "name": "",
        "best_for": "which modes/contexts",
        "acts": "brief act breakdown",
        "time_allocation": "percentage split"
      }
    ],
    "humor_techniques": [
      {
        "name": "",
        "register": "safe|moderate|heavy|venue_specific",
        "description": ""
      }
    ],
    "audience_interactions": [
      {"name": "", "best_for": "", "description": ""}
    ],
    "transition_techniques": [
      {"name": "", "description": ""}
    ],
    "closing_patterns": [
      {"name": "", "best_for": "", "structure": ""}
    ],
    "persuasion_techniques": [
      {"name": "", "category": "exposing_problems|building_credibility|selling|creating_frameworks", "description": ""}
    ],
    "verbal_signatures": [
      {"phrase": "", "usage": "when/how it's used", "frequency": "high|medium|low|rare"}
    ],
    "pop_culture_notes": "general guidance on how this speaker uses pop-culture references"
  },

  "visual_style_history": {
    "default_illustration_style": "the speaker's most common illustration aesthetic, or null if no pattern",
    "default_image_source": "most common image source type: ai_generated, meme, screenshot, stock_photo, custom_artwork, mixed",
    "style_departures": [
      {
        "style": "name of the departure style (e.g., retro_tech_manual)",
        "trigger": "what caused the departure: mode, co-presenter, topic, venue",
        "talks": ["list of talk filenames that used this style"],
        "description": "human-readable description of the style, specific enough to inform a prompt"
      }
    ],
    "mode_visual_profiles": [
      {
        "mode_id": "a",
        "typical_style": "illustration aesthetic typically used in this mode",
        "image_source_mix": "what image sources dominate in this mode",
        "notes": "any mode-specific visual tendencies"
      }
    ],
    "evolution_notes": "narrative of how the speaker's visual style has changed over time",
    "visual_continuity_patterns": ["recurring devices across talks: numbering schemes, mascots, progressive elements"],
    "confirmed_visual_intents": [
      {
        "pattern": "name of the visual pattern",
        "intent": "deliberate",
        "rule": "what the presentation-creator should do about it",
        "note": "additional context from the speaker"
      }
    ]
  },

  "pattern_profile": {
    "pattern_baseline": {
      "schema_version": 2,
      "as_of": "2026-02-22T12:00:00+00:00",
      "scope": "global",
      "active_batch_excluded": false,
      "excluded_filenames": [],
      "eligible_statuses": ["processed", "processed_partial"],
      "pattern_scoring_generation_status": "current",
      "pattern_scoring_generation_reasons": [],
      "pattern_catalog_fingerprint": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      "pattern_scoring_schema_version": 5,
      "scored_talk_count": 24,
      "pattern_score_sum": 163,
      "average_pattern_score": 6.79,
      "eligible_talk_count": 24,
      "opportunity_coverage_identity": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
      "raw_score_comparison_status": "available",
      "raw_score_comparison_reason": null
    },
    "baseline_talk_filenames": [
      "example-01.md",
      "example-02.md",
      "example-03.md",
      "example-04.md",
      "example-05.md",
      "example-06.md",
      "example-07.md",
      "example-08.md",
      "example-09.md",
      "example-10.md",
      "example-11.md",
      "example-12.md",
      "example-13.md",
      "example-14.md",
      "example-15.md",
      "example-16.md",
      "example-17.md",
      "example-18.md",
      "example-19.md",
      "example-20.md",
      "example-21.md",
      "example-22.md",
      "example-23.md",
      "example-24.md"
    ],
    "eligible_talk_count": 24,
    "talks_scored": 24,
    "average_pattern_score": 6.79,
    "score_trend": "unavailable",
    "pattern_breadth": {
      "avg_distinct_patterns_per_talk": null,
      "trend": "unavailable",
      "note": "Unavailable until a speaker-owned coverage-comparable breadth policy is versioned."
    },
    "underused_patterns": [],
    "score_drivers": {
      "direction": "unavailable",
      "antipattern_drivers": [],
      "pattern_drivers": [],
      "note": "Unavailable until a speaker-owned trend policy is versioned."
    },
    "by_mode": [],
    "strengths": [],
    "strengths_note": "Unavailable until a speaker-owned classification policy is versioned.",
    "note": "Only observable patterns are included. Patterns marked observable: false in the taxonomy (pre-event logistics, hidden authoring/provenance processes, physical stage behaviors, post-event follow-up, and external systems the current artifacts cannot prove) are excluded from scoring and surfaced as a go-live checklist in creator Phase 6 instead.",
    // Opportunity arrays are abbreviated here for readability. Generated
    // profiles contain one sorted row for every observable catalog entry of
    // the matching polarity.
    "pattern_usage": [
      {
        "pattern_id": "narrative-arc",
        "detected_count": 22,
        "evaluable_count": 24,
        "unevaluable_count": 0,
        "not_applicable_count": 0,
        "eligible_cohort_count": 24,
        "coverage": 1.0,
        "times_used": 22,
        "out_of": 24,
        "usage_rate": 0.9166666666666666
      }
    ],
    "antipattern_frequency": [
      {
        "pattern_id": "shortchanged",
        "detected_count": 8,
        "evaluable_count": 24,
        "unevaluable_count": 0,
        "not_applicable_count": 0,
        "eligible_cohort_count": 24,
        "coverage": 1.0,
        "times_detected": 8,
        "out_of": 24,
        "frequency_rate": 0.3333333333333333
      }
    ],
    "never_used_patterns": [],
    "signature_combinations": [],
    "mastery_levels": {
      "signature": [],
      "regular": [],
      "occasional": [],
      "rare": [],
      "never_tried": []
    },
    "classification_availability": {
      "schema_version": 1,
      "status": "unavailable",
      "reason_codes": ["owner_policy_unconfigured"]
    }
  },

  "badges": [
    {
      "id": "short_identifier",
      "source_lane": "non_pattern",
      "name": "Badge display name",
      "description": "What this badge represents — fun, self-deprecating, grounded in vault data",
      "evidence": "specific data point(s) from the vault that earned this badge"
    }
  ],

  "publishing_process": {
    "shownotes": {
      "enabled": true,
      "source": {
        "type": "local_jekyll|local_hugo|local_eleventy|local_astro|remote_url|none",
        "path_or_url": "/path/to/shownotes-site-root (or a remote https URL for remote_url)",
        "talks_subdir": "_talks"
      },
      "url": {
        "base": "https://speaking.example.com",
        "template": "/{slug}/"
      },
      "thumbnail_path_template": "assets/images/thumbnails/{slug}-thumbnail.png",
      "slug_convention": {
        "template": "{venue-compact}{yy}-{short-id}",
        "examples": ["jfokus26-monkey", "devnexus26-robocoders"]
      },
      "ssg_template_pointer": "{source.path_or_url}/_layouts/default.html",
      "publishing_method": "description of how shownotes are published (git push, CMS, manual)",
      "shownotes_template": "path to the SSG template file for new talk pages, or null"
    },
    "export_format": "pdf|pptx_only|both",
    "export_method": "description of how to export (e.g., PowerPoint AppleScript, LibreOffice CLI, manual)",
    "export_script": "optional: literal script/command to run for export, or null",
    "qr_code": {
      "enabled": true,
      "target": "shownotes_url|custom_url",
      "custom_url": "a full https URL (only when target=custom_url)",
      "insert_into_deck": true,
      "slide_position": "shownotes_slide|closing|both",
      "shortener": "bitly|rebrandly|none",
      "bitly_domain": "jbaru.ch | null",
      "rebrandly_domain": "jbaru.ch | null",
      "bg_color_match": true
    },
    "thumbnail": {
      "enabled": true,
      "speaker_photo_path": "/path/to/headshot.jpg",
      "aesthetic_preference": "photo|comic_book",
      "style_preference": "slide_dominant|split_panel|overlay",
      "title_position": "top|bottom|overlay",
      "brand_colors": ["#hex1", "#hex2"],
      "notes": "speaker-specific thumbnail preferences"
    },
    "video_publishing": {
      "enabled": true,
      "embed_method": "youtube_embed|link_only|both",
      "shownotes_video_section": "where/how video goes in shownotes",
      "video_description_template": "template with {conference} {year} {shownotes_url} placeholders"
    },
    "additional_steps": [
      {
        "name": "step name",
        "description": "what to do",
        "automated": true,
        "script": "optional command/script, or null"
      }
    ],
    "notes": "any speaker-specific publishing quirks or preferences"
  }
}
```

Confirmed-intent `intent` values are non-empty speaker-owned classification labels,
not a closed three-value enum. `deliberate`, `accidental`, and
`context_dependent` are recommended defaults, while established labels such as
`accepted_tradeoff`, `fact`, or `deliberate_signature` remain authoritative.

The `confirmed_intents[].schema_version` shown in the profile is the independent
public profile-domain intent schema, not the tracking-database record version.
`load-vault.py` projects only `pattern`, `intent`, `rule`, and `note` from stored
intent records; it strips database schema and capture provenance before profile
generation. Storage-only fields such as `confirmed_date`, source-talk pointers,
and `retrofit_targets` intentionally do not enter the semantic profile. The
profile producer then emits the profile-domain schema-v1 intent object shown
above.

### Pattern Cohort Provenance

`pattern_profile.pattern_baseline` is copied unchanged from the loader's
`pattern_baseline` payload. It uses the vault-ingress adherence-baseline schema and
must describe the active catalog fingerprint and scoring schema with
`active_batch_excluded: false` and `excluded_filenames: []`.
For scoring schema v5, the loader also requires every selected talk's persisted
source-location ledger and citations to remain fresh against the live vault and
configured source roots, plus one canonical exhaustive `pattern_outcomes` matrix and
matching `opportunity_coverage_identity`. Generation identity alone cannot authorize
the cohort.
`baseline_talk_filenames` is the sorted, unique list of exact filenames from
`baseline_talks`; its length and `pattern_profile.eligible_talk_count` equal
`pattern_baseline.eligible_talk_count`. That eligible count is also copied into every
opportunity row. A row's `out_of` is its own evaluable count, not the global cohort
count. `pattern_usage` and `antipattern_frequency` contain one sorted row for every
observable catalog entry of the matching polarity, including when no talk supplied an
evaluable opportunity. Their exact fields and arithmetic are owned by
`scripts/pattern_opportunities.py`.

Raw score fields are a separate lane. `talks_scored` and `average_pattern_score`
exactly mirror the validated baseline's raw-score-comparison count and average. When
eligible talks have mixed opportunity identities, or when their shared identity has
no evaluable (`detected` or `undetected`) opportunity, the baseline explicitly reports
`raw_score_comparison_status: "unavailable"`, zero scored talks, and a null average.
The respective stable reasons are `mixed_opportunity_coverage` and
`no_evaluable_pattern_opportunities`; the per-pattern occurrence rows remain
available.

All `pattern_profile` fields in the schema are required in v4. The current
`classification_availability` sentinel states that no speaker-owned versioned
classification policy exists. Therefore zero detections cannot authorize
`never_used_patterns`, and occurrence rates cannot authorize mastery, recurring
severity, strengths, underuse, combinations, mode splits, or trends. Those fields use
the exact empty/unavailable shapes in the example until the owner versions such a
policy. `talks_analyzed` may still count every processed talk. Pacing uses the
separately named `current_instrumentation_talks` cohort and never borrows the pattern
denominator.

`pattern_profile` is the only v4 storage lane for catalog history.
`rhetoric_defaults` must not duplicate mastery, signatures, usage, scores, or other
pattern-history fields. `guardrail_sources.recurring_issues[]` and `badges[]` are
non-pattern-only lanes: every entry carries `source_lane: "non_pattern"` and must not
carry pattern IDs, scores, mastery, catalog identity, occurrence fields, or a pattern
denominator. Consumers derive catalog warnings and reinforcement directly from the
validated `pattern_profile`; the writer never materializes duplicate catalog-derived
recurring issues or badges.

Writers and readers call
`scripts/profile_pattern_provenance.py::assess_pattern_profile` for the same strict
decision. `current_contract: true` means the v4 provenance is structurally canonical;
`catalog_fields_available: true` additionally requires a non-empty eligible cohort.
`classification_fields_available: false` suppresses every derived history tier even
when exact occurrence rows are present. The owner additionally runs
`"{python_path}" "{speaker_toolkit_root}/skills/vault-profile/scripts/validate-profile.py" --vault-root <path>`;
it recomputes the cohort from the
live tracking database and rejects structurally valid but source-fabricated rows.
A reader may continue using unrelated non-pattern fields from an older profile, but it
must treat that profile's historical pattern fields as unavailable rather than migrate
or infer provenance.

When the current pattern cohort is empty, preserve the canonical zero-count baseline,
an empty `baseline_talk_filenames`, `eligible_talk_count: 0`, `talks_scored: 0`, and
`average_pattern_score: null`. Keep the exhaustive positive and negative catalog rows
with zero counts and null rates/coverage. Set `score_trend`, `pattern_breadth.trend`,
and `score_drivers.direction` to `"unavailable"`; set the breadth average to `null`
and every classification-derived array/mastery tier to `[]`. Never fall back to an
older profile, the rhetoric summary, excluded scoring generations, or the
instrumentation cohort.

## How the Presentation Creator Uses Each Section

The presentation-creator skill reads the profile at runtime. Its reference files define
the PROCESS; the profile provides the DATA. No generation step is needed — the creator
automatically picks up changes when the profile is regenerated.

| Profile section | Creator phase that reads it | What it drives |
|---|---|---|
| `speaker` + `infrastructure` | Phase 0 (load) | Vault path, template reference, file conventions |
| `presentation_modes` | Phase 2 (architecture) | Mode selection menu and recommendations |
| `presentation_engines` | Phase 2 (Decision #2 — engine & theme sourcing), Phase 5 (slide generation) | Engine sourcing menu; Phase 5 reads the chosen renderer. Optional/additive — absent on older profiles, which fall back to a flat pptx/presenterm menu |
| `design_rules` | Phase 5 (slide generation) | Background colors, footer specs, shape vocabulary |
| `rhetoric_defaults` | Phase 1-3 (spec, architecture, content) | Voice calibration, opening/closing defaults |
| `confirmed_intents` | Phase 2-4 (architecture, guardrails) | Hard rules that override pattern inference |
| `pacing` | Phase 3-4 (content, guardrails) | Slide budget tables, WPM targets |
| `guardrail_sources` | Phase 4 (guardrails) | All guardrail checks with thresholds |
| `instrument_catalog` | Phase 2 (architecture) | Complete instrument menu by dimension |
| `visual_style_history` | Phase 2 (architecture — illustration strategy) | Default aesthetic, mode-specific departures, style proposals |
| `pattern_profile` | Phase 2 (architecture), Phase 4 (guardrails) | Auditable occurrence rows; 4-tier recommendations and recurring antipattern warnings only when the shared gate explicitly authorizes classification fields |
| `badges` | Informational | Fun speaker achievements mined from vault data |
| `infrastructure.template_layouts` | Phase 5 (slide generation) | Layout map and selection logic |
| `infrastructure.font_pair` | Phase 5 (slide generation) | Font usage rules |
| `publishing_process` | Phase 6 (publishing), Phase 7 (post-event) | Export, shownotes, QR code, distribution steps, thumbnail prefs, video publishing |
