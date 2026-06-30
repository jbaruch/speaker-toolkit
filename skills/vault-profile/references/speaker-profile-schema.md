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

Current `schema_version`: **2**. The validator (`scripts/validate-profile.py`,
`CURRENT_SCHEMA_VERSION`) accepts only the current version.

- **v1 → v2** adds the coaching-outcome fields, all additive: `pattern_profile.score_drivers`,
  `pattern_breadth`, `underused_patterns`, `by_mode`, `strengths`/`strengths_note`, and
  `pacing.adherence`.
- **Reader tolerance (dual-accept):** a reader written for v1 ignores the new fields; a
  v2-aware reader (presentation-creator) treats each new field as optional and falls back
  when it is absent on an older profile, the same way it already handles `presentation_engines`.
- **Migration:** vault-profile regenerates the profile wholesale each run. A v1 file is
  replaced by a v2 file on the next run — no in-place migration step. The only value carried
  across regenerations is `infrastructure.template_layouts[].use_for` (merged by the
  `(master_index, name)` pair, version-independent).

## Schema

```json
{
  "schema_version": 2,
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
      "pattern": "name of the pattern",
      "intent": "deliberate|accidental|context_dependent",
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
      "talks_over_budget": 5,
      "talks_scored": 24,
      "over_budget_rate": 0.21,
      "trend": "improving|stable|worsening",
      "worst_offenders": [
        {"filename": "2024-04-10-talk-slug.md", "slides_per_minute": 2.1, "budget_slides_per_minute": 1.5, "over_by": "40%"}
      ],
      "note": "Quantitative time/slide pacing, computed by scripts/compute-pacing-adherence.py from each talk's structured_data.slide_count and structured_data.talk_duration_estimate vs guardrail_sources.slide_budgets. Duration parsing and budget-band selection live in that script's docstring. Distinct from the qualitative 'rushing' read in vault Dimension 14 (transcript-evident time panic) — this is the corpus-level count. The duration estimate is transcript-derived and approximate; treat marginal overages as soft signals, not hard failures."
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
        "intent": "deliberate|accidental|context_dependent",
        "rule": "what the presentation-creator should do about it",
        "note": "additional context from the speaker"
      }
    ]
  },

  "pattern_profile": {
    "talks_scored": 24,
    "average_pattern_score": 6.8,
    "score_trend": "improving|stable|declining",
    "pattern_breadth": {
      "avg_distinct_patterns_per_talk": 7.4,
      "trend": "widening|stable|narrowing",
      "note": "Distinct observable patterns deployed per talk, averaged across scored talks — the 'are you using enough of your toolkit' dimension, isolated from antipattern avoidance. A narrowing trend lowers pattern_score with zero antipatterns involved. Breadth is range, not a target to maximize: more patterns is not automatically better (cramming is its own antipattern), but a contracting range is a regression signal symmetric to rising antipatterns."
    },
    "underused_patterns": [
      {
        "pattern_id": "sparkline",
        "mastery_level": "never_tried|rare",
        "fits_modes": ["b"],
        "note": "observable, high-fit for an established mode, never or rarely deployed — a growth opportunity, NOT a deficiency. Sourced from both never_used_patterns and the never_tried/rare tiers of mastery_levels, filtered to patterns whose Vault Dims match the speaker's modes. Surfaced so coaching covers positive space, not only antipatterns. Distinct from a fading_pattern, which the speaker DID use and dropped."
      }
    ],
    "score_drivers": {
      "direction": "improving|stable|declining|insufficient_history",
      "antipattern_drivers": [
        {"pattern_id": "shortchanged", "frequency_trend": "increasing", "evidence": "detected in 4 of the last 6 talks, up from 1 of the prior 6"}
      ],
      "pattern_drivers": [
        {"pattern_id": "bookends", "usage_trend": "decreasing", "evidence": "signature pattern absent from the last 3 talks"}
      ],
      "note": "Attribution for score_trend — names which patterns/antipatterns moved the score, in EITHER direction. Array names denote the metric, not the direction; each entry's own trend field (frequency_trend / usage_trend, each 'increasing'|'decreasing'|'stable') is authoritative. antipattern_drivers = antipattern_frequency entries whose movement shifted the score (frequency_trend='increasing' lowers it, 'decreasing' raises it). pattern_drivers = pattern_usage entries, each keyed by a concrete pattern_id with its usage_trend, whose movement shifted the score, signature OR regular (usage_trend='decreasing' lowers it, 'increasing' raises it). Breadth is NOT encoded as a pattern_drivers entry — read the sibling pattern_breadth.trend as an additional driver when it is not 'stable' ('narrowing' lowers the score, 'widening' raises it). For direction='declining', list the rising antipatterns + the fading/narrowing patterns; for 'improving', the receding antipatterns + the growing patterns/breadth. Underuse alone can drive a decline with zero antipatterns. Empty driver arrays are valid only when direction is 'stable' or 'insufficient_history' (<10 talks_scored). When talks_scored <10, direction='insufficient_history' and score_trend MUST be 'stable' (its neutral value — trend is not yet meaningful); never pair direction='insufficient_history' with a directional score_trend ('improving'/'declining')."
    },
    "by_mode": [
      {
        "mode_id": "a",
        "talks_in_mode": 11,
        "stable": true,
        "average_pattern_score": 7.2,
        "avg_distinct_patterns_per_talk": 8.1,
        "top_antipatterns": ["shortchanged"],
        "note": "Per-mode baseline. Adherence, breadth, and underuse should compare a talk to ITS mode's baseline, not the global one — a lightning talk that 'underuses audience interaction' is a false positive, not the same finding as a keynote doing so. stable=true only when talks_in_mode >= 3; below that, omit the mode or mark stable=false and fall back to the global baseline."
      }
    ],
    "strengths": [
      {
        "pattern_id": "narrative-arc",
        "kind": "signature_pattern|signature_combination",
        "mastery_level": "signature",
        "evidence": "deployed in 22 of 24 talks at strong confidence",
        "lean_in": "your structural backbone — keep building talks around it; it's what audiences remember"
      }
    ],
    "strengths_note": "The positive counterpart to recurring_issues and underused_patterns: what the speaker already does well, framed as 'lean in / double down', so coaching is not purely deficit-oriented. Sourced from mastery_levels.signature and signature_combinations. Distinct from badges (which are fun/celebratory) — strengths are actionable reinforcement the creator skill can amplify. For kind='signature_combination', pattern_id holds the combination label.",
    "note": "Only observable patterns are included. Patterns marked observable: false in the taxonomy (pre-event logistics, physical stage behaviors, external systems) are excluded from scoring and surfaced as a go-live checklist in creator Phase 6 instead.",
    "pattern_usage": [
      {
        "pattern_id": "narrative-arc",
        "times_used": 22,
        "out_of": 24,
        "usage_rate": 0.92,
        "average_confidence": "strong|moderate|weak",
        "trend": "consistent|increasing|decreasing",
        "mastery_level": "signature|regular|occasional|rare"
      }
    ],
    "antipattern_frequency": [
      {
        "pattern_id": "shortchanged",
        "times_detected": 8,
        "out_of": 24,
        "frequency_rate": 0.33,
        "trend": "increasing|stable|decreasing",
        "severity": "recurring|occasional|rare"
      }
    ],
    "never_used_patterns": ["takahashi", "cave-painting", "greek-chorus (observable patterns only — unobservable patterns excluded)"],
    "signature_combinations": [
      {
        "patterns": ["narrative-arc", "bookends", "foreshadowing"],
        "frequency": 15,
        "label": "Story Sandwich"
      }
    ],
    "mastery_levels": {
      "signature": [],
      "regular": [],
      "occasional": [],
      "rare": [],
      "never_tried": []
    }
  },

  "badges": [
    {
      "id": "short_identifier",
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
| `pattern_profile` | Phase 2 (architecture), Phase 4 (guardrails) | Pattern Strategy 4-tier recommendations, antipattern warnings |
| `badges` | Informational | Fun speaker achievements mined from vault data |
| `infrastructure.template_layouts` | Phase 5 (slide generation) | Layout map and selection logic |
| `infrastructure.font_pair` | Phase 5 (slide generation) | Font usage rules |
| `publishing_process` | Phase 6 (publishing), Phase 7 (post-event) | Export, shownotes, QR code, distribution steps, thumbnail prefs, video publishing |
