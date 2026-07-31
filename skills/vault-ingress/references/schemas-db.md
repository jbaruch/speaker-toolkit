# Vault DB & Subagent Schemas

## Tracking Database Schema

The tracking database (`tracking-database.json`) is the single source of truth.
Canonical path: `~/.claude/rhetoric-knowledge-vault/tracking-database.json`.

```json
{
  "config": {
    "vault_root": "~/.claude/rhetoric-knowledge-vault",
    "vault_storage_path": "/actual/path/if/custom (null when using default location)",
    "pptx_source_dir": "/path/to/Presentations",
    "python_path": "/path/to/python3",
    "template_skip_patterns": ["template"],
    "shownotes": {
      "enabled": true,
      "source": {
        "type": "local_jekyll|local_hugo|local_eleventy|local_astro|remote_url|none",
        "path_or_url": "/path/to/shownotes-site-root (or a remote https URL for remote_url)",
        "talks_subdir": "_talks"
      },
      "url": {"base": "https://speaking.example.com", "template": "/{slug}/"},
      "thumbnail_path_template": "assets/images/thumbnails/{slug}-thumbnail.png",
      "slug_convention": {"template": "{venue-compact}{yy}-{short-id}", "examples": []},
      "ssg_template_pointer": "{source.path_or_url}/_layouts/default.html"
    },
    "clarification_sessions_completed": 0
  },
  "talks": [{
    "filename": "2024-04-10-talk-slug.md",
    "title": "Talk Title", "conference": "Name", "date": "2024-04-10",
    "slides_url": "Google Drive file URL (optional — slides extracted from video if absent)",
    "video_url": "YouTube watch URL (required — only source needed for processing)",
    "youtube_id": "dQw4w9WgXcQ", "google_drive_id": "1AbCdEfGhIjK",
    "source_identity": {
      "schema_version": 1, "provider": "youtube", "video_id": "dQw4w9WgXcQ",
      "title": "Title recorded at the source", "speakers": ["Speaker Name"],
      "recorded_date": "2024-04-10", "upload_date": "2024-04-11",
      "duration_seconds": 2700, "captured_at": "2026-07-31T12:00:00Z"
    },
    "source_relation": {"type": "duplicate|borrowed_recording", "target_filename": "canonical-talk.md"},
    "source_rejections": [{
      "source_type": "video", "url": "known-bad upstream URL",
      "reason": "non_delivery_clip|wrong_delivery|unrelated_recording",
      "evidence": "how the rejection was verified",
      "verified_at": "timezone-aware ISO-8601 timestamp"
    }],
    "pptx_path": "Conference/Year/Talk Name.pptx  (optional — highest quality slide source when available)",
    "schema_version": 3,
    "transcript_source": "youtube_auto|whisper|manual|none  (how the transcript was obtained; MAY BE ABSENT — see below)",
    "slide_source": "pptx|pdf|both|video_extracted|none  (set in Step 2 per slide source hierarchy)",
    "slides_local_path": "slides/<artifact>.pdf  (optional explicit local PDF; legacy readers also accept slides_pdf_path/pdf_path)",
    "pptx_visual_status": "pending|extracted|no_pptx",
    "status": "pending|needs-reprocessing|reprocessing-inflight|processed|processed_partial|skipped_no_sources|skipped_download_failed|skipped_duplicate",
    "reprocess_reason": "machine-readable reason for needs-reprocessing, or null",
    "reprocess_generation": 1,
    "_queue_claim": {
      "schema_version": 1,
      "run_id": "reparse-2026-07",
      "batch_id": "25",
      "claimed_at": "2026-07-31T18:00:00+00:00",
      "previous_status": "needs-reprocessing",
      "reprocess_generation": 1,
      "state": "claimed|completed|stale_recovered|superseded",
      "released_at": "timezone-aware ISO-8601; present on a closed claim",
      "release_reason": "return_persisted|lease_expired|new_generation_claimed",
      "result_status": "terminal status; present when state is completed"
    },
    "_queue_claim_history": [],
    "rhetoric_notes": "", "areas_for_improvement": "",
    "structured_data": {}, "verbatim_examples": {},
    "adherence_assessment": "", "processed_date": null,
    "_comment_queryable_scalars": "Promoted from the subagent return by scripts/persist-results.py (PROMOTE list) — do NOT hand-map in Step 4.",
    "co_presenter": false, "co_presenters": [], "delivery_language": "en",
    "slide_count": 0, "slide_design_style": null, "illustration_style": null,
    "opening_type": null, "closing_type": null, "narrative_arc_type": null,
    "audience_interaction_count": 0, "pattern_score": 0,
    "pattern_scoring_schema_version": 2,
    "pattern_catalog_fingerprint": "sha256 of the exact catalog files used",
    "pattern_observations": {
      "evidence_sources": ["transcript", "static_slides"],
      "pattern_ids": [],
      "antipattern_ids": [],
      "not_evaluable_ids": [],
      "pattern_score": 0,
      "patterns_detected": [],
      "antipatterns_detected": [],
      "not_evaluable": []
    }
  }],
  "_comment_schema_version": "Talk-record schema version, stamped by persist-results.py. v1 is the implicit unversioned shape. v2 makes transcript_source optional. v3 adds optional queue-generation, catalog-fingerprint, scoring-version, evidence-source, and not-evaluable fields plus explicit corrective clears. Existing field representations do not change, so older readers ignore the additions; a validated re-analysis supplies the generation-specific fields.",
  "_comment_absent_transcript_source": "Absent transcript_source: the key may be MISSING on a talk, and missing is meaningful — it means provenance is unknown, not that no transcript exists (that is the explicit value `none`). It arises on one path: fetch-transcript.py returning method `existing`, where a valid transcript was already on disk and no fetch ran, so nothing was learned about where it came from. Writers MUST NOT backfill a guess; `manual` in particular asserts a human produced it. Readers gauging transcript reliability MUST treat absent as unknown and MUST NOT default it to any value.",
  "pptx_catalog": [{
    "pptx_path": "Conference/Year/Talk Name.pptx",
    "talk_filename": "2024-04-10-talk-slug.md or null",
    "matched": true,
    "slide_count": 60,
    "visual_extracted": false
  }],
  "qr_codes": [{
    "talk_slug": "arc-of-ai",
    "target_url": "canonical talk URL",
    "shortener": "bitly|rebrandly|none",
    "short_path": "shortener's back-half/slashtag, null for none",
    "short_url": "shortened URL, equal to target_url when shortener=none",
    "shortener_link_id": "API-side ID needed for updates; null for none",
    "qr_png_rel_path": "illustrations/arcofai-qr.png (relative to vault or deck dir)",
    "created_at": "2026-04-15",
    "updated_at": "2026-04-15"
  }],
  "confirmed_intents": [],
  "improvement_goals": []
}
```

`source_identity` and `source_relation` are optional. Their owned shape,
offline comparison rules, duplicate semantics, and compatibility policy are in
[source-identity-preflight.md](source-identity-preflight.md). Do not fetch live
metadata during validation; record evidence separately, then run the preflight.

`improvement_goals` is the coaching-loop artifact — speaker-chosen focus areas that
a later ingress run verifies. vault-clarification owns the record shape; vault-ingress
writes only the verification fields. Record schema, lifecycle, and owner/reader
contract:
[../../vault-clarification/references/schemas-config.md](../../vault-clarification/references/schemas-config.md)
Improvement Goals Schema. Verification rubric: [processing-rules.md](processing-rules.md)
Improvement Goal Verification.

## Per-Talk Subagent Return Schema

Each subagent returns this JSON after processing one talk:

```json
{
  "filename": "the .md filename",
  "queue_claim": {
    "run_id": "copied from talk._queue_claim.run_id",
    "batch_id": "copied from talk._queue_claim.batch_id",
    "reprocess_generation": 1
  },
  "status": "processed|processed_partial|skipped_no_sources|skipped_download_failed|skipped_duplicate",
  "slide_source": "pptx|pdf|both|video_extracted|none",
  "clear_fields": [
    "analysis-owned dotted paths disproved by this re-analysis; omit when none"
  ],
  "rhetoric_notes": "500-1000 words: qualitative observations across dimensions 1-13",
  "areas_for_improvement": "100-300 words: honest critical reflection (Dimension 14); name the related antipattern ID + severity per issue where a Dimension 14 antipattern applies",
  "transcript_source": "youtube_auto|whisper|manual  (how the transcript was obtained; OMIT the key entirely when provenance is unknown — see Absent transcript_source in the DB schema above)",
  "structured_data": {
    "delivery_language": "en|de|ru|etc  (primary language of the talk)",
    "co_presenter": false,
    "co_presenters": ["Full Name; required and non-empty when co_presenter is true"],
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
  "adherence_assessment": "2-4 sentences vs. the Section 15 baseline — cite pattern_score vs running average + any recurring antipattern that reappeared; '' if <10 talks scored. See processing-rules.md Adherence Assessment",
  "new_patterns": "100-300 words on NEW patterns not in summary, or ''",
  "summary_updates": "50-200 words: additions for rhetoric-style-summary.md by section #, or ''",
  "pattern_observations": {
    "evidence_sources": [
      "every source actually inspected: static_slides|native_deck|delivery_video|transcript|source_comparison"
    ],
    "patterns_detected": [
      {
        "pattern_id": "narrative-arc",
        "confidence": "strong|moderate|weak",
        "evidence_source": "static_slides|native_deck|delivery_video|transcript|source_comparison",
        "evidence": "brief description of what was observed",
        "dimensions": [2, 5]
      }
    ],
    "antipatterns_detected": [
      {
        "pattern_id": "shortchanged",
        "confidence": "strong|moderate|weak",
        "evidence_source": "static_slides|native_deck|delivery_video|transcript|source_comparison",
        "evidence": "brief description of what was observed",
        "dimensions": [12, 14]
      }
    ],
    "not_evaluable": [
      {
        "pattern_id": "composite-animation",
        "evidence_source": "static_slides",
        "reason": "Only a flattened PDF was available, so simultaneous layered animation and timing could not be established."
      }
    ],
    "pattern_score": {
      "patterns_used": 8,
      "antipatterns_detected": 2,
      "score": 6
    }
  },
  "catalog_feedback": {
    "unmatched_observations": [],
    "confusable_pairs": [],
    "definition_problems": [],
    "scoring_problems": [],
    "tensions": []
  }
}
```

Every processed return carries the complete analysis shape, including empty
strings/arrays for findings that did not occur. A skipped terminal return may
contain only `filename`, `queue_claim`, `status`, and any known provenance. Both
writers reject a missing/unknown status or a return whose queue generation does
not match the talk's active claim. `persist-results.py` closes the claim as
`completed`; `write-analysis.py` accepts that same completed generation and
rejects an older one.

`clear_fields` is the only mechanism that deletes prior analysis. Allowed paths
are top-level analysis prose/provenance scalars or leaves under
`structured_data`, `verbatim_examples`, and `pattern_observations`. It cannot
clear queue identity, source URLs, catalog metadata, or the talk record itself.
Clearing a promoted structured scalar clears its top-level copy too. Ordinary
empty values remain additive no-ops.

`evidence_source` uses the enum defined by the pattern index's Evidence-Source Contract.
Detected entries must name a qualifying source; `source_comparison` evidence must name
both compared artifacts. `not_evaluable` is a separate array for source-gated entries
that cannot be judged from the available evidence. Its entries are excluded from
`pattern_ids`, `antipattern_ids`, and every `pattern_score` count. Never put an
unavailable entry in a detected array or treat it as an absent pattern.

## Video Extraction Output Schema

Produced by `skills/vault-ingress/scripts/video-slide-extraction.py`.
Stored in `structured_data.video_extraction` on the talk entry:

```json
{
  "slide_source": "video_extracted",
  "schema_version": 2,
  "pipeline_version": "0.9.0",
  "total_frames_extracted": 1500,
  "unique_slides_count": 85,
  "hash_threshold_used": 8,
  "slide_region_detected": true,
  "slide_region_applied": true,
  "slide_region_method": "auto|manual|none",
  "slide_region_verified": false,
  "slide_region": [0.05, 0.02, 0.78, 0.98],
  "output_pdf": "slides/{youtube_id}.pdf",
  "fps_used": 0.5
}
```

The owner of this record's shape is `skills/vault-ingress/scripts/video-slide-extraction.py`.
Two version fields track two independent axes:

- `schema_version` (integer) — the record's **field shape**. Current value: `2`. The
  script bumps it on any field add/remove/rename. **Reader contract:** a record with no
  `schema_version` is the legacy pre-versioning shape — treat it as `schema_version 0`
  and read the fields that are present; a record with a `schema_version` higher than the
  reader accepts is "no usable prior state" (re-extract to refresh). Readers never
  migrate in place — the owner script rewrites the record on the next extraction.
- `pipeline_version` (string) — the extractor **behavior** (`PIPELINE_VERSION`) that
  produced the entry. The script bumps it when extraction behavior changes (see
  `skills/vault-ingress/references/video-slide-extraction.md` — "Pipeline Versioning").
  The same value is
  mirrored in the output PDF's producer/creator metadata. A pre-versioning entry has no
  `pipeline_version`.

The resulting PDF is named `{youtube_id}.pdf` in the `slides/` directory and analyzed
the same as a Google Drive PDF for dimension 13 (slide design patterns).

Version 2 adds crop provenance. `slide_region_detected` is true only when the
auto-detector returned a region; it is false for a manual region.
`slide_region_applied` says whether any crop was used for hashing,
`slide_region_method` records `auto`, `manual`, or `none`, and
`slide_region_verified` is true only when the operator explicitly marked a manual
crop as visually checked. For a version-1 record, readers may infer method `auto`,
applied from whether `slide_region` is present, and verified `false`; re-extraction
is still required before treating an old crop as verified.

## PPTX Extraction Output Schema

Produced by `skills/vault-ingress/scripts/pptx-extraction.py`.

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
      "background_type": "solid|pattern|image|gradient|solid_from_layout|unknown",
      "layout_name": "Title Slide  (free text from slide.slide_layout.name — not an enum)",
      "shape_count": 3,
      "has_text_frame_shapes": true,
      "has_image": false,
      "image_area_ratio": 0.0,
      "text_extraction_confidence": "high|low",
      "text_content_preview": "Talk Title",
      "ocr_text": "",
      "text_extraction_method": "shapes|shapes+ocr|shapes+ocr_unavailable",
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

**`text_extraction_confidence` gates how the text fields may be read.**
`text_content_preview` comes from PPTX *shapes*; text rendered inside a picture
is invisible to the shape walk. On a `"low"` slide:

- empty `text_content_preview` means *unreadable by shapes*, never wordless
- `ocr_text` holds the script-owned OCR inventory from picture blobs when the
  engine ran (`text_extraction_method: "shapes+ocr"`). Use it for cites,
  transcript cross-checks, language policy on slide text, and pattern evidence
- `text_extraction_method` is `"shapes"` when OCR was not attempted (high
  confidence, `--no-ocr`, or no picture blob), `"shapes+ocr"` when it ran,
  `"shapes+ocr_unavailable"` when the engine was missing
- Dimensions 8/13 **design** judgment (density, two-layer legibility, composition)
  still requires the rendered image — OCR is inventory, not layout (see
  [known-issues.md](known-issues.md) § "Shape Extraction Is Blind to Text Baked
  Into Images" and [subagent-instructions.md](subagent-instructions.md))

`has_text_frame_shapes` reports shapes carrying text frames — not whether the
slide shows text.

`image_area_ratio` is the **largest** PICTURE shape's area as a fraction of the
slide, rounded to 3 decimals; always present. `0.0` means no picture, unreadable
picture geometry, **or** a picture small enough to round down — it is not proof
that the slide has no picture. The confidence threshold
compares against the unrounded value, so a reported ratio equal to the
threshold is not proof of which way the slide was classified.

It measures picture **shapes** only. A slide whose image is a *background*
reports `background_type: "image"` and `text_extraction_confidence: "low"`
while `image_area_ratio` stays `0.0` — the background covers the canvas by
definition and has no picture geometry to measure. Read the confidence, never
the ratio, to decide whether a slide needs a visual pass.
