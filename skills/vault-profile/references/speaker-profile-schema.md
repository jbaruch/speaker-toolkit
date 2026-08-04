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

Current `schema_version`: **5**. The validator (`scripts/validate-profile.py`,
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
  availability explicit. Its derived fields remain fail-closed because v4 carries no
  policy identity.
- **v4 → v5** adds deterministic policy-derived history. It embeds the normalized
  policy plus its canonical semantic digest, adds exhaustive positive and antipattern
  classification rows, makes availability independent per derived domain, and retains
  the complete trend audit used by projections.
- **Generation:** vault-profile writes only v5. Stored v1/v2/v3/v4 profiles are
  non-current and `scripts/validate-profile.py` rejects them as generation output. A
  compatible reader may expose a validated v4 profile's occurrence rows only; every v4
  mastery, novelty, severity, combination, underuse, and trend field remains
  unavailable because v4 has no policy stamp.
- **Migration:** vault-profile regenerates the profile wholesale each run. An older file is
  replaced by a v5 file on the next run — no in-place migration step and no talk reparse.
  Existing current-generation tracking rows are read without mutation. The only value carried
  across regenerations is `infrastructure.template_layouts[].use_for` (merged by the
  `(master_index, name)` pair, version-independent).
- **Generation reset:** when either the catalog fingerprint or pattern-scoring schema
  changes, catalog-derived diffs across the boundary are a reset. Do not describe score,
  usage, mastery, or trend changes across those identities as speaker regressions.
  Within one generation, a changed classification-policy semantic digest resets only
  policy-derived comparisons; raw occurrence rows remain comparable.

## Schema

```json
{
  "schema_version": 5,
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
    "score_trend": "improving",
    "pattern_breadth": {
      "avg_distinct_patterns_per_talk": 6.3,
      "trend": "widening",
      "note": "Breadth is the mean count of detected positive catalog patterns per current-generation talk."
    },
    "underused_patterns": [],
    "score_drivers": {
      "direction": "improving",
      "antipattern_drivers": ["going-meta"],
      "pattern_drivers": [],
      "note": "Drivers include only catalog IDs whose conservative 5+5 interval crossed the policy movement threshold."
    },
    "by_mode": [],
    "strengths": ["narrative-arc"],
    "strengths_note": "Deterministic projection of regular and signature positive-pattern classifications.",
    "note": "Only observable patterns are included. Patterns marked observable: false in the taxonomy (pre-event logistics, hidden authoring/provenance processes, physical stage behaviors, post-event follow-up, and external systems the current artifacts cannot prove) are excluded from scoring and surfaced as a go-live checklist in creator Phase 6 instead.",
    // Opportunity arrays are abbreviated here for readability. Generated
    // profiles contain one sorted row for every observable catalog entry of
    // the matching polarity.
    "pattern_usage": [
      {
        "pattern_id": "narrative-arc",
        "detected_count": 22,
        "evaluable_count": 22,
        "unevaluable_count": 2,
        "not_applicable_count": 0,
        "eligible_cohort_count": 24,
        "coverage": 0.9166666666666666,
        "times_used": 22,
        "out_of": 22,
        "usage_rate": 1.0
      }
    ],
    "antipattern_frequency": [
      {
        "pattern_id": "going-meta",
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
      "signature": ["narrative-arc"],
      "regular": [],
      "occasional": [],
      "rare": [],
      "never_tried": []
    },
    "classification_schema_version": 1,
    "classification_policy": {
      "schema_version": 1,
      "policy_id": "speaker-toolkit-default",
      "policy_version": 1,
      "source": "bundled_default",
      "semantic_sha256": "ab327a0418794df3905a31794c6e079f12dae3abda66dbcc58be9b55e28d1f77",
      "semantic_policy": {
        "schema_version": 1,
        "policy_id": "speaker-toolkit-default",
        "policy_version": 1,
        "positive_patterns": {
          "signature": {"minimum_applicable": 8, "minimum_lower": 0.7},
          "regular": {"minimum_evaluable": 8, "minimum_applicable_coverage": 0.8, "minimum_lower": 0.4, "maximum_upper_exclusive": 0.7},
          "occasional": {"minimum_evaluable": 8, "minimum_applicable_coverage": 0.8, "minimum_lower": 0.15, "maximum_upper_exclusive": 0.4},
          "rare": {"minimum_evaluable": 8, "minimum_applicable_coverage": 0.8, "minimum_detections": 1, "maximum_upper_exclusive": 0.15},
          "never_tried": {"minimum_applicable": 8, "require_complete_evaluation": true, "maximum_detections": 0}
        },
        "antipattern_recurrence": {
          "high_frequency": {"minimum_applicable": 8, "minimum_detections": 4, "minimum_lower": 0.5},
          "moderate_frequency": {"minimum_evaluable": 8, "minimum_applicable_coverage": 0.8, "minimum_detections": 3, "minimum_lower": 0.25, "maximum_upper_exclusive": 0.5},
          "occasional": {"minimum_evaluable": 8, "minimum_applicable_coverage": 0.8, "minimum_detections": 1, "maximum_upper_exclusive": 0.25},
          "confirmed_none": {"minimum_applicable": 8, "require_complete_evaluation": true, "maximum_detections": 0}
        },
        "signature_combinations": {
          "eligible_member_classifications": ["regular", "signature"],
          "member_counts": [2, 3],
          "minimum_applicable": 8,
          "minimum_detections": 4,
          "minimum_lower": 0.4,
          "maximum_results": 10
        },
        "trends": {
          "minimum_comparable_talks": 10,
          "window_size": 5,
          "score_delta": 0.5,
          "breadth_delta": 0.5,
          "pattern_movement_delta": 0.2
        }
      }
    },
    "classification_availability": {
      "schema_version": 2,
      "mastery_and_novelty": {"status": "available", "reason_codes": []},
      "antipattern_recurrence": {"status": "available", "reason_codes": []},
      "underuse": {"status": "available", "reason_codes": []},
      "signature_combinations": {"status": "available", "reason_codes": []},
      "trends": {"status": "available", "reason_codes": []},
      "modes": {"status": "unavailable", "reason_codes": ["talk_mode_assignments_unavailable"]}
    },
    // Both arrays below are exhaustive and catalog-sorted in generated profiles;
    // one representative row from each polarity is shown here.
    "pattern_classifications": [
      {
        "pattern_id": "narrative-arc",
        "classification": "signature",
        "observation_status": "observed",
        "absence_conclusion_capable": false,
        "evidence": {
          "applicable_count": 24,
          "evaluable_count": 22,
          "detected_count": 22,
          "unevaluable_count": 2,
          "applicable_coverage": 0.9166666666666666,
          "lower": 0.9166666666666666,
          "upper": 1.0
        },
        "reason_codes": ["meets_signature_thresholds"]
      }
    ],
    "antipattern_classifications": [
      {
        "pattern_id": "going-meta",
        "classification": "moderate_frequency",
        "observation_status": "observed",
        "absence_conclusion_capable": true,
        "evidence": {
          "applicable_count": 24,
          "evaluable_count": 24,
          "detected_count": 8,
          "unevaluable_count": 0,
          "applicable_coverage": 1.0,
          "lower": 0.3333333333333333,
          "upper": 0.3333333333333333
        },
        "reason_codes": ["meets_moderate_frequency_thresholds"]
      }
    ],
    "trend_analysis": {
      "status": "available",
      "reason_codes": [],
      "sample": {
        "required_talk_count": 10,
        "valid_date_talk_count": 24,
        "invalid_date_filenames": [],
        "selected_filenames": ["example-15.md", "example-16.md", "example-17.md", "example-18.md", "example-19.md", "example-20.md", "example-21.md", "example-22.md", "example-23.md", "example-24.md"],
        "opportunity_coverage_identity": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
      },
      "score": {"status": "improving", "prior_average": 6.0, "recent_average": 7.0, "delta": 1.0},
      "breadth": {"status": "widening", "prior_average": 5.0, "recent_average": 6.0, "delta": 1.0},
      // Movement arrays are exhaustive when trends are available and empty when
      // the trend domain is unavailable. One representative row is shown per lane.
      "pattern_movements": [
        {
          "pattern_id": "narrative-arc",
          "movement": "indeterminate",
          "prior_evidence": {"applicable_count": 5, "evaluable_count": 4, "detected_count": 4, "unevaluable_count": 1, "applicable_coverage": 0.8, "lower": 0.8, "upper": 1.0},
          "recent_evidence": {"applicable_count": 5, "evaluable_count": 4, "detected_count": 4, "unevaluable_count": 1, "applicable_coverage": 0.8, "lower": 0.8, "upper": 1.0},
          "reason_codes": ["uncertainty_spans_movement_threshold"]
        }
      ],
      "antipattern_movements": [
        {
          "pattern_id": "going-meta",
          "movement": "decreasing",
          "prior_evidence": {"applicable_count": 5, "evaluable_count": 5, "detected_count": 3, "unevaluable_count": 0, "applicable_coverage": 1.0, "lower": 0.6, "upper": 0.6},
          "recent_evidence": {"applicable_count": 5, "evaluable_count": 5, "detected_count": 1, "unevaluable_count": 0, "applicable_coverage": 1.0, "lower": 0.2, "upper": 0.2},
          "reason_codes": ["conservative_interval_decrease"]
        }
      ]
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

All `pattern_profile` fields in the schema are required in v5. If the vault has no
`pattern-classification-policy.json`, the loader automatically applies the bundled
`speaker-toolkit-default@1` policy; users are not asked to invent thresholds. A present
override is strict and fail-closed: an unreadable file, duplicate key, non-finite
number, unknown/missing field, unsupported version, oversized file, or invalid
threshold aborts profile generation rather than silently selecting the default.

`classification_policy` is self-contained. `semantic_policy` is the complete normalized
policy used for the run, and `semantic_sha256` is the SHA-256 of its canonical sorted
JSON. `policy_id`, `policy_version`, and `source` identify it for humans, but the digest
is the comparison identity; whitespace and object-key order do not change it. The
bundled file is `references/pattern-classification-policy-v1.json`. A vault override
uses the same closed schema and records `source: "vault_override"`.

`pattern_classifications` and `antipattern_classifications` contain one sorted row for
every observable catalog entry of the matching polarity. Each row preserves the exact
evaluable denominator and exposes classifier-produced evidence counts, coverage, and
conservative bounds. Positive and antipattern rows use the label vocabularies shown in
the schema example; row-level `unclassified` results remain part of the exhaustive
output.

#### Classifier-Owned Policy Semantics

Thresholds, formulas, tier predicates, combination selection, trend windows, and
movement decisions are not restated in this reference. See
`references/pattern-classification-policy-v1.json` for the complete bundled semantic
policy and `scripts/classify-pattern-profile.py` — `validate_policy()` and
`classify_pattern_profile()` — for its executable contract. Each generated profile
embeds the normalized policy that was actually applied, plus its semantic digest.
Consumers copy the classifier's rows and projections unchanged.

`mastery_levels`, `strengths`, `underused_patterns`, `never_used_patterns`, signature
combinations, and trend analysis are deterministic classifier projections. Consumers
must not reconstruct them from raw rates or from the prose summary.

`never_tried` and `not_yet_observed` are deliberately not synonyms. `never_tried` is a
policy-backed absence classification. `not_yet_observed` says that this corpus has no
positive detection while absence remains unknown. A conclusive absence that does not
reach a named tier remains `unclassified` with observation status `confirmed_absent`.
Only classifier-emitted `never_tried` IDs enter `never_used_patterns`; no other zero
state may be presented as proof that the speaker has never tried the technique. The
antipattern equivalent is `confirmed_none`; every other zero-detection antipattern
remains non-recurring unless the classifier says otherwise.

`classification_availability` is schema v2 and independent per domain. Mastery/novelty,
antipattern recurrence, underuse, combinations, trends, and modes each carry their own
`{status, reason_codes}`. The default policy makes the first four domains evaluable from
opportunity rows; the classifier determines trend availability from its policy and
input evidence. Modes remain unavailable until talk-mode assignments exist. A consumer
must gate only the requested domain and retain row-level unclassified results; one
unavailable domain never erases another available one.
`trend_analysis` retains the complete selected sample, metric values, exhaustive
pattern movements, and reasons behind those projections.

A validated schema-v4 profile remains compatible only as occurrence history:
`pattern_baseline`, filenames, raw score availability, `pattern_usage`, and
`antipattern_frequency` may be read under their v4 provenance contract. Because v4 has
no policy stamp, readers must ignore its mastery, novelty, recurrence, strength,
underuse, combination, mode, and trend projections. Regenerate to v5 from the tracking
database to obtain those fields; this re-analysis does not reparse talks or modify raw
talk/opportunity rows.

`talks_analyzed` may count every processed talk. Pacing uses the separately named
`current_instrumentation_talks` cohort and never borrows the pattern denominator.

`pattern_profile` is the only v5 storage lane for catalog history.
`rhetoric_defaults` must not duplicate mastery, signatures, usage, scores, or other
pattern-history fields. `guardrail_sources.recurring_issues[]` and `badges[]` are
non-pattern-only lanes: every entry carries `source_lane: "non_pattern"` and must not
carry pattern IDs, scores, mastery, catalog identity, occurrence fields, or a pattern
denominator. Consumers derive catalog warnings and reinforcement directly from the
validated `pattern_profile`; the writer never materializes duplicate catalog-derived
recurring issues or badges.

Writers and readers use the shared profile provenance/classification validator for the
same strict decision. Current v5 catalog availability requires source-exact cohort and
opportunity rows; each classification domain then follows its own availability object.
The owner additionally runs
`"{python_path}" "{speaker_toolkit_root}/skills/vault-profile/scripts/validate-profile.py" --vault-root <path>`;
it recomputes the cohort from the
live tracking database and rejects structurally valid but source-fabricated occurrence,
policy, classification, availability, or projection rows.
A reader may continue using unrelated non-pattern fields from an older profile and the
explicitly supported v4 occurrence-only lane above, but it must treat all other legacy
pattern history as unavailable rather than migrate or infer provenance.

When the current pattern cohort is empty, preserve the canonical zero-count baseline,
an empty `baseline_talk_filenames`, `eligible_talk_count: 0`, `talks_scored: 0`, and
`average_pattern_score: null`. Keep the exhaustive positive and negative catalog rows
with zero counts and null rates/coverage, plus exhaustive classification rows with
their classifier-owned unavailable/unclassified evidence. Set `score_trend`,
`pattern_breadth.trend`, and `score_drivers.direction` to `"unavailable"`; set the
breadth average to `null` and derived list/mastery projections to `[]`. Never fall back
to an older profile, the rhetoric summary, excluded scoring generations, or the
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
| `pattern_profile` | Phase 2 (architecture), Phase 4 (guardrails) | Auditable occurrence and exhaustive classification rows; recommendations and warnings gated by the relevant availability domain and row evidence |
| `badges` | Informational | Fun speaker achievements mined from vault data |
| `infrastructure.template_layouts` | Phase 5 (slide generation) | Layout map and selection logic |
| `infrastructure.font_pair` | Phase 5 (slide generation) | Font usage rules |
| `publishing_process` | Phase 6 (publishing), Phase 7 (post-event) | Export, shownotes, QR code, distribution steps, thumbnail prefs, video publishing |
