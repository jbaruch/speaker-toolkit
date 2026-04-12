# Vault DB & Subagent Schemas

## Tracking Database Schema

The tracking database (`tracking-database.json`) is the single source of truth.
Canonical path: `~/.claude/rhetoric-knowledge-vault/tracking-database.json`.

```json
{
  "config": {
    "vault_root": "~/.claude/rhetoric-knowledge-vault",
    "vault_storage_path": "/actual/path/if/custom (null when using default location)",
    "talks_source_dir": "/path/to/_talks",
    "pptx_source_dir": "/path/to/Presentations",
    "python_path": "/path/to/python3",
    "template_skip_patterns": ["template"],
    "clarification_sessions_completed": 0
  },
  "talks": [{
    "filename": "2024-04-10-talk-slug.md",
    "title": "Talk Title", "conference": "Name", "date": "2024-04-10",
    "slides_url": "https://drive.google.com/file/d/{ID}/view  (optional — slides extracted from video if absent)",
    "video_url": "https://www.youtube.com/watch?v={ID}  (required — only source needed for processing)",
    "youtube_id": "aBcDeFg", "google_drive_id": "1AbCdEfGhIjK",
    "pptx_path": "Conference/Year/Talk Name.pptx  (optional — highest quality slide source when available)",
    "transcript_source": "youtube_auto|whisper|manual|none  (how the transcript was obtained)",
    "slide_source": "pptx|pdf|both|video_extracted|none  (set in Step 2 per slide source hierarchy)",
    "pptx_visual_status": "pending|extracted|no_pptx",
    "status": "pending|processed|processed_partial|needs-reprocessing|skipped_no_sources|skipped_download_failed",
    "reprocess_reason": "null|pattern_scoring_added  (set when status changed to needs-reprocessing by migration)",
    "rhetoric_notes": "", "areas_for_improvement": "",
    "structured_data": {}, "verbatim_examples": {},
    "adherence_assessment": "", "processed_date": null,
    "pattern_observations": {
      "pattern_ids": [],
      "antipattern_ids": [],
      "pattern_score": 0
    }
  }],
  "pptx_catalog": [{
    "pptx_path": "Conference/Year/Talk Name.pptx",
    "talk_filename": "2024-04-10-talk-slug.md or null",
    "matched": true,
    "slide_count": 60,
    "visual_extracted": false
  }],
  "confirmed_intents": []
}
```

## Per-Talk Subagent Return Schema

Each subagent returns this JSON after processing one talk:

```json
{
  "filename": "the .md filename",
  "rhetoric_notes": "500-1000 words: qualitative observations across dimensions 1-13",
  "areas_for_improvement": "100-300 words: honest critical reflection (dimension 14)",
  "transcript_source": "youtube_auto|whisper|manual  (how the transcript was obtained)",
  "structured_data": {
    "delivery_language": "en|de|ru|etc  (primary language of the talk)",
    "co_presenter": false,
    "slide_count": 60,
    "talk_duration_estimate": "35 min (from transcript length/pacing clues)",
    "meme_count": 15,
    "image_only_slide_count": 25,
    "audience_interaction_count": 3,
    "opening_type": "provocative_image|failure_framing|audience_poll|story|bold_claim|demo_cold_open",
    "closing_type": "summary_cta|callback|open_question|demo_finale|resource_list",
    "narrative_arc_type": "problem_diagnosis_solution|discovery_demo|chronological|listicle",
    "slide_design_style": "comic_book|minimal_dark|demo_scaffolding|mixed",
    "illustration_style": "name of dominant illustration aesthetic, or 'none'",
    "illustration_coherence": "unified|mixed|none",
    "image_source_distribution": {"ai_generated": 0, "meme": 5, "screenshot": 3, "stock_photo": 0, "none": 12},
    "visual_continuity_devices": ["FIG_numbering", "progressive_form", "recurring_mascot"],
    "opening_sequence": ["title", "provocative_hook", "bio", "shownotes_url", "first_argument"],
    "closing_sequence": ["summary_bullets", "cta_with_qr", "thanks_with_humor"],
    "color_coded_backgrounds": {
      "purple_halftone": "slide numbers and semantic register"
    },
    "background_color_sequence": ["purple", "white", "red", "yellow", "...for every slide"],
    "per_slide_visual": [
      {
        "slide_number": 1,
        "background_color_name": "purple_halftone|red_halftone|yellow_halftone|etc",
        "content_type": "title|bio|shownotes|content_bullets|data_chart|quote|meme_only|meme_with_text|section_divider|progressive_reveal|comparison_table|hot_take|cta|thanks",
        "image_composition": "full_bleed|full_bleed_with_text|image_left_text_right|image_right_text_left|centered_image_with_title|inset_image|progressive_reveal|screenshot|meme_with_caption|none",
        "has_speech_bubble": false,
        "has_starburst": false,
        "has_footer": true
      }
    ],
    "typography_observations": {
      "title_font_description": "hand-lettered comic style, appears to be...",
      "body_font_description": "...",
      "bullet_character": "multiplication_sign|dash|circle|custom",
      "title_color_adapts_to_background": true
    },
    "footer_observations": {
      "element_count": 4,
      "separator_character": "|",
      "footer_color_adapts_to_background": false,
      "watermark_present": true,
      "watermark_description": "description of any corporate/sponsor logo or branding"
    },
    "shape_observations": {
      "speech_bubble_slides": [1, 15, 42],
      "starburst_slides": [8, 23, 55],
      "speech_bubble_description": "white fill, black outline, tail pointing down-left",
      "starburst_description": "red fill, white text, explosion/irregular star shape"
    }
  },
  "verbatim_examples": {
    "signature_phrases": ["actual phrases from transcript, e.g. 'is not a thing'"],
    "jokes": ["verbatim joke/humor lines from transcript"],
    "transitions": ["actual transition phrases, e.g. 'Next thing you know...'"],
    "audience_addresses": ["how speaker addresses audience, e.g. 'raise your hand if...'"],
    "opening_lines": ["first 2-3 sentences of the talk, verbatim"],
    "closing_lines": ["last 2-3 sentences of the talk, verbatim"]
  },
  "adherence_assessment": "1-3 sentences, or '' if <10 talks parsed",
  "new_patterns": "100-300 words on NEW patterns not in summary, or ''",
  "summary_updates": "50-200 words: additions for rhetoric-style-summary.md by section #, or ''",
  "pattern_observations": {
    "patterns_detected": [
      {
        "pattern_id": "narrative-arc",
        "confidence": "strong|moderate|weak",
        "evidence": "brief description of what was observed",
        "dimensions": [2, 5]
      }
    ],
    "antipatterns_detected": [
      {
        "pattern_id": "shortchanged",
        "confidence": "strong|moderate|weak",
        "evidence": "brief description of what was observed",
        "dimensions": [12, 14]
      }
    ],
    "pattern_score": {
      "patterns_used": 8,
      "antipatterns_detected": 2,
      "score": 6
    }
  }
}
```

## Video Extraction Output Schema

Produced by `scripts/video-slide-extraction.py`.
Stored in `structured_data.video_extraction` on the talk entry:

```json
{
  "slide_source": "video_extracted",
  "total_frames_extracted": 1500,
  "unique_slides_count": 85,
  "hash_threshold_used": 8,
  "slide_region_detected": true,
  "slide_region": [0.05, 0.02, 0.78, 0.98],
  "output_pdf": "slides/{youtube_id}.pdf",
  "fps_used": 0.5
}
```

The resulting PDF is named `{youtube_id}.pdf` in the `slides/` directory and analyzed
the same as a Google Drive PDF for dimension 13 (slide design patterns).

## PPTX Extraction Output Schema

Produced by `scripts/pptx-extraction.py`.

### What the Script Extracts (mapped to slide-design-spec.md sections)

| Spec Section | Extraction Coverage | Field |
|---|---|---|
| 2. Background Colors | Exact hex values + fill type | `background_color_hex`, `background_type` |
| 3. Typography | Font names, sizes, colors, bold/italic | `shapes_summary[].font_*` |
| 4. Footer | Position, font, color, separator | `footer_text`, footer shape properties |
| 5. Image Placement | Whether image is present (composition type needs PDF visual classification) | `has_image` |
| 6. Bubbles/Starbursts | Auto-shape type enum, fill/line colors | `auto_shape_type`, `fill_color`, `line_color` |
| 7. Layout Taxonomy | PowerPoint layout name per slide | `layout_name` |
| 10. Color Sequencing | Full sequence of hex values | `color_sequence` |

### What the Script Does NOT Extract (still needs PDF visual analysis)

- **Image composition type** (full-bleed vs side-by-side vs inset) — python-pptx can
  tell you an image exists and its position/size, but classifying the COMPOSITION
  PATTERN requires visual judgment
- **Content type** (meme vs data chart vs quote) — requires understanding the content,
  not just the shapes
- **Section divider identification** — requires understanding the rhetorical function
- **Background color NAME** (the semantic register label like "purple_halftone") —
  python-pptx gives hex values; mapping hex to register names requires building the
  lookup table from the first few extractions

### Schema:

```json
{
  "pptx_path": "Conference/Year/Talk.pptx",
  "slide_count": 60,
  "aspect_ratio": "16:9",
  "per_slide_visual": [
    {
      "slide_number": 1,
      "background_color_hex": "#5B2C6F",
      "background_type": "solid|pattern|image|gradient",
      "layout_name": "TITLE",
      "shape_count": 3,
      "has_text_placeholder": true,
      "has_image": false,
      "text_content_preview": "Talk Title",
      "footer_text": "@handle | #conf | #topic | website",
      "has_speaker_notes": true,
      "shapes_summary": [
        {"type": "placeholder", "name": "Title 1", "font": "Bangers", "font_size": 36, "font_color": "#FFFFFF", "bold": true},
        {"type": "autoshape", "shape_type": "CLOUD_CALLOUT", "fill_color": "#FFFFFF", "line_color": "#000000"}
      ]
    }
  ],
  "global_design": {
    "fonts_used": {"Bangers": 45, "Arial": 10},
    "background_colors": {"#5B2C6F": 12, "#C0392B": 8},
    "footer_pattern": {
      "position_left": 0.5, "position_bottom": 0.1,
      "font": "Arial", "font_size": 8, "font_color": "#FFFFFF", "separator": " | "
    },
    "shape_types_used": {"CLOUD_CALLOUT": 15, "EXPLOSION1": 8},
    "color_sequence": ["#5B2C6F", "#FFFFFF", "#C0392B", "..."]
  }
}
```
