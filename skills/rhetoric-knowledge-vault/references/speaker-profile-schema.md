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

## Schema

```json
{
  "schema_version": 1,
  "generated_date": "2026-02-22",
  "talks_analyzed": 24,

  "speaker": {
    "name": "",
    "handle": "",
    "website": "",
    "shownotes_url_pattern": "{website}/{slug}",
    "bio_short": "one-sentence bio used on slides",
    "bio_context": "career trajectory or credentials chain shown on bio slides"
  },

  "infrastructure": {
    "template_pptx_path": "/path/to/template.pptx",
    "template_name": "human-readable name for the template",
    "template_layouts": [
      {
        "index": 0,
        "name": "TITLE",
        "placeholders": [{"idx": 0, "type": "CENTER_TITLE"}],
        "use_for": "opening title slide, section dividers"
      }
    ],
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
      "closing_default": "name of default closing pattern for this mode"
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
    "demo_pace": "minimal slides, live tool is the content"
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

  "publishing_process": {
    "export_format": "pdf|pptx_only|both",
    "export_method": "description of how to export (e.g., PowerPoint AppleScript, LibreOffice CLI, manual)",
    "export_script": "optional: literal script/command to run for export, or null",
    "shownotes_publishing": {
      "enabled": true,
      "method": "description of how shownotes are published (e.g., git push to site repo, CMS, manual)",
      "shownotes_repo_path": "path to shownotes repo, or null",
      "shownotes_template": "path to shownotes template file, or null"
    },
    "qr_code": {
      "enabled": true,
      "target": "shownotes_url|custom_url",
      "insert_into_deck": true,
      "slide_position": "early (slide 4-5)|closing|both"
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
| `design_rules` | Phase 5 (slide generation) | Background colors, footer specs, shape vocabulary |
| `rhetoric_defaults` | Phase 1-3 (spec, architecture, content) | Voice calibration, opening/closing defaults |
| `confirmed_intents` | Phase 2-4 (architecture, guardrails) | Hard rules that override pattern inference |
| `pacing` | Phase 3-4 (content, guardrails) | Slide budget tables, WPM targets |
| `guardrail_sources` | Phase 4 (guardrails) | All guardrail checks with thresholds |
| `instrument_catalog` | Phase 2 (architecture) | Complete instrument menu by dimension |
| `infrastructure.template_layouts` | Phase 5 (slide generation) | Layout map and selection logic |
| `infrastructure.font_pair` | Phase 5 (slide generation) | Font usage rules |
| `publishing_process` | Phase 6 (publishing) | Export, shownotes, QR code, distribution steps |
