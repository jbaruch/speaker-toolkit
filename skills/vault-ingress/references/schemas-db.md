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
    "video_url": "YouTube watch URL (optional when a usable transcript or slide source exists)",
    "youtube_id": "dQw4w9WgXcQ", "google_drive_id": "1AbCdEfGhIjK",
    "source_identity": {
      "schema_version": 1, "provider": "youtube", "video_id": "dQw4w9WgXcQ",
      "title": "Title recorded at the source",
      "uploader": "Conference Channel", "uploader_id": "@conference",
      "speakers": ["Speaker Name"],
      "recorded_date": "2024-04-10", "upload_date": "2024-04-11",
      "duration_seconds": 2700,
      "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
      "webpage_video_id": "dQw4w9WgXcQ",
      "captured_at": "2026-07-31T12:00:00Z"
    },
    "source_relation": {"type": "duplicate|borrowed_recording", "target_filename": "canonical-talk.md"},
    "source_rejections": [{
      "source_type": "video|slides", "url": "known-bad upstream URL",
      "reason": "non_delivery_clip|wrong_delivery|unrelated_recording",
      "evidence": "how the rejection was verified",
      "verified_at": "timezone-aware ISO-8601 timestamp"
    }],
    "pptx_path": "Conference/Year/Talk Name.pptx  (optional — highest quality slide source when available)",
    "transcript_path": "transcripts/<artifact>.txt  (optional explicit local transcript)",
    "schema_version": 3,
    "transcript_source": "youtube_auto|whisper|manual|none  (how the transcript was obtained; MAY BE ABSENT — see below)",
    "slide_source": "pptx|pdf|both|video_extracted|none  (set in Step 2 per slide source hierarchy)",
    "slides_local_path": "slides/<artifact>.pdf  (optional explicit local PDF; legacy readers also accept slides_pdf_path/pdf_path)",
    "pptx_visual_status": "pending|extracted|no_pptx",
    "status": "pending|needs-reprocessing|reprocessing-inflight|processed|processed_partial|skipped_no_sources|skipped_download_failed|skipped_duplicate",
    "reprocess_reason": "machine-readable reason for needs-reprocessing, or null",
    "reprocess_generation": 1,
    "_queue_claim": {
      "schema_version": 2,
      "run_id": "reparse-2026-07",
      "batch_id": "25",
      "claimed_at": "2026-07-31T18:00:00+00:00",
      "previous_status": "needs-reprocessing",
      "reprocess_generation": 1,
      "state": "claimed|completed|stale_recovered|superseded",
      "released_at": "timezone-aware ISO-8601; present on a closed claim",
      "release_reason": "return_persisted|lease_expired|new_generation_claimed",
      "result_status": "terminal status; present when state is completed",
      "result_payload_sha256": "canonical return JSON receipt; present when state is completed"
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
metadata during validation. Capture provider evidence separately with the
read-only flow in [source-identity-audit.md](source-identity-audit.md), review it,
then run the preflight. Uploader/upload date never establish speaker/recorded
date, and a captured webpage URL is never an automatic active-source repair.

Queue eligibility is not encoded by `video_url` alone. `queue-state.py` derives
auditable `source_capabilities` from declared video, transcript, and slide references;
any one can support a claim after preflight. Legacy no-video/no-transcript statuses
normalize to `skipped_no_sources` only when that capability list is empty.

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
  "slides_local_path": "slides/<artifact>.pdf  (optional; required for processed video_extracted)",
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
    "unmatched_observations": [{
      "observation": "Observed move with no exact catalog fit",
      "why_no_pattern_fits": "Boundaries checked and why each fails",
      "proposed_name": "new-pattern-name",
      "proposed_polarity": "pattern|antipattern"
    }],
    "tensions": [{
      "pattern_ids": ["exact-pattern-id", "exact-antipattern-id"],
      "nature": "How the entries trade against one another",
      "evidence": "Talk-specific evidence"
    }],
    "definition_problems": [{
      "pattern_id": "exact-catalog-id",
      "problem": "ambiguous|undetectable|unfalsifiable|miscategorized|overlapping",
      "detail": "Why the documented boundary cannot be applied"
    }],
    "scoring_problems": [{
      "issue": "Model-level scoring defect",
      "detail": "Evidence and consequence"
    }],
    "confusable_pairs": [{
      "pattern_ids": ["first-exact-id", "second-exact-id"],
      "detail": "The missing discriminator"
    }]
  }
}
```

Every processed return carries the complete analysis shape, including empty
strings/arrays for findings that did not occur. A skipped terminal return may
contain only `filename`, `queue_claim`, `status`, and any known provenance. Both
writers reject a missing/unknown status or a return whose queue generation does
not match the talk's active claim. Returns should omit `processed_date`: the
persistence writer's normalized batch `--run-date` (or generated UTC timestamp)
owns that field. A legacy return-side value remains accepted for compatibility
but cannot override persistence or rendered provenance. Date-only values are
advisory; a full timezone-aware return timestamp is an explicit assertion and
must normalize to the authoritative batch stamp or both writers reject it.

The return filenames must exactly equal every tracking-DB member carrying the
same `run_id` and `batch_id`, with each member's own generation matching its
claim. Partial, superset, mixed-identity, duplicate, or lifecycle-split batches
fail before either artifact changes. `persist-results.py` requires the whole
batch in `claimed` state and closes it as `completed`; `write-analysis.py`
requires that same whole batch in `completed` state. A genuinely one-member
batch is complete and remains supported. A partially closed or stranded batch
must be recovered into a fresh queue generation rather than finished piecemeal.

Queue-claim schema v2 adds `result_payload_sha256` to completed claims. The
receipt hashes the exact return payload after stable JSON key/whitespace
canonicalization. `persist-results.py` accepts an active v1 or v2 lease, upgrades
it to v2 when closing it, and stores the receipt; new claims are v2. The analysis
writer recomputes the receipt and rejects a substituted payload. `queue-state.py`
owns stored-claim migration: an already completed v1 claim becomes v2 with an
explicit null receipt because the original payload cannot be reconstructed, and
therefore cannot authorize an analysis replacement until a fresh generation is
processed. Unknown future claim versions fail closed.

Before rendering a processed result, `write-analysis.py` also requires the
talk's `pattern_catalog_fingerprint` and `pattern_scoring_schema_version` to
equal the catalog and scoring contract it just validated. Skipped results do not
render or restamp prior analysis-generation metadata.

`slides_local_path` is a top-level analysis provenance scalar. Returns use the
portable canonical form `slides/<artifact>.pdf`; persistence copies it to the talk
record and the analysis writer renders it in the provenance header. For
`slide_source: "video_extracted"`, the filename must be
`slides/{structured_data.video_extraction.source_video_id}.pdf`. `status: "processed"`
requires that path plus a complete schema-v3 manifest whose top-level crop provenance
and `slide_region` artifact independently agree on a verified manual crop. The return's
manifest identity is also matched against the claimed talk's `youtube_id` before either
writer changes state.

Any video-extracted return without a promoted artifact must omit
`slides_local_path`, include it in `clear_fields`, and cannot finish `processed`. A
trusted but unpromoted verified `slide_region` may still supply `static_slides` evidence
to a `processed_partial` return. An untrusted manifest is context-only: do not list
`static_slides` and do not return authored-slide structured evidence. A
`full_frame_context` artifact may still qualify as `delivery_video` evidence for room,
speaker, PiP, and delivery/timing phenomena that it actually establishes; its scope can
never be promoted into authored-slide evidence.

`clear_fields` is the only mechanism that deletes prior analysis. Allowed paths
are top-level analysis prose/provenance scalars or leaves under
`structured_data`, `verbatim_examples`, and `pattern_observations`. It cannot
clear queue identity, source URLs, catalog metadata, or the talk record itself.
Clearing a promoted structured scalar clears its top-level copy too. Ordinary
empty values remain additive no-ops.

`evidence_source` uses the enum defined by the pattern index's Evidence-Source Contract.
Detected entries must name a qualifying source; `source_comparison` evidence must name
both compared sources. A nested `evaluable_from` alternative requires all named
underlying sources plus the `source_comparison` marker, which does not count as an
underlying source. `not_evaluable` is a separate array for source-gated entries that
cannot be judged from the available evidence. Every observable gated catalog entry with
no satisfied singleton or conjunctive alternative must appear there; an entry may also
appear when an otherwise eligible source cannot establish its stated evidence
requirements. Its entries are excluded from
`pattern_ids`, `antipattern_ids`, and every `pattern_score` count. Never put an
unavailable entry in a detected array or treat it as an absent pattern.

`catalog_feedback` is mandatory on current processed returns and uses only the
five lanes shown above (empty arrays are valid). Exact IDs and
pattern/antipattern polarity are validated against catalog YAML; new suggested
names occupy a separate namespace and carry `proposed_polarity`. The read-only
aggregator also audits historical returns, reports legacy compatibility issues
without silently repairing them, and preserves per-entry provenance. Its owned
schema and aggregation contract are in
[catalog-feedback-intake.md](catalog-feedback-intake.md).

## Video Extraction Output Schema

Produced by `skills/vault-ingress/scripts/video-slide-extraction.py`.
Stored in `structured_data.video_extraction` on the talk entry:

```json
{
  "slide_source": "video_extracted",
  "schema_version": 3,
  "pipeline_version": "0.10.0",
  "source_video_id": "aBcDeFg",
  "source_video_path": "/vault/slides-rebuild/aBcDeFg/aBcDeFg.mp4",
  "total_frames_extracted": 1500,
  "unique_frame_count": 85,
  "authored_slide_count": null,
  "hash_threshold_used": 8,
  "slide_region_detected": true,
  "slide_region_applied": true,
  "slide_region_method": "manual",
  "slide_region_verified": true,
  "slide_region": [0.05, 0.02, 0.78, 0.98],
  "fps_used": 0.5,
  "retained_frames": [
    {"page_number": 1, "frame_index": 0, "timestamp_seconds": 0.0},
    {"page_number": 2, "frame_index": 6, "timestamp_seconds": 12.0}
  ],
  "artifacts": [
    {
      "path": "/vault/slides-rebuild/aBcDeFg/aBcDeFg.slide-region.pdf",
      "artifact_scope": "slide_region",
      "page_count": 85,
      "source_video_id": "aBcDeFg",
      "source_video_path": "/vault/slides-rebuild/aBcDeFg/aBcDeFg.mp4",
      "crop_method": "manual",
      "crop_verified": true,
      "trusted_for_authored_slide_analysis": true
    },
    {
      "path": "/vault/slides-rebuild/aBcDeFg/aBcDeFg.context.pdf",
      "artifact_scope": "full_frame_context",
      "page_count": 85,
      "source_video_id": "aBcDeFg",
      "source_video_path": "/vault/slides-rebuild/aBcDeFg/aBcDeFg.mp4",
      "crop_method": "none",
      "crop_verified": false,
      "trusted_for_authored_slide_analysis": false
    }
  ],
  "review_required": false,
  "review_reason": null
}
```

The owner of this record's shape is `skills/vault-ingress/scripts/video-slide-extraction.py`.
Two version fields track two independent axes:

- `schema_version` (integer) — the record's **field shape**. Current value: `3`. The
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

Version 2 added crop provenance. `slide_region_detected` is true only when the
auto-detector returned a region; it is false for a manual region.
`slide_region_applied` says whether any crop was used for hashing,
`slide_region_method` records `auto`, `manual`, or `none`, and
`slide_region_verified` is true only when the operator explicitly marked a manual
crop as visually checked. For a version-1 record, readers may infer method `auto`,
applied from whether `slide_region` is present, and verified `false`; re-extraction
is still required before treating an old crop as verified.

Version 3 separates derived artifacts by provenance and scope. `artifacts[].path` and
`source_video_path` are absolute, symlink-resolved paths at extraction time.
`artifact_scope` is one of:

- `slide_region` — pages are physically cropped to the selected region. This is trusted
  for authored-slide analysis only when `crop_method` is `manual`, `crop_verified` is
  true, `trusted_for_authored_slide_analysis` is true, and top-level
  `review_required` is false.
- `full_frame_context` — uncropped broadcast frames for room, stage, speaker, or PiP
  analysis. This is never an authored deck and is never a source for slide design,
  authored slide count, or slide-pattern claims.

Ingress validates the manifest as one referential unit before trusting it: schema and
pipeline versions are present; source and artifact identities agree; normalized region
geometry agrees with `slide_region_method`, `slide_region_applied`,
`slide_region_detected`, and `slide_region_verified`; retained-frame and artifact page
counts agree with `unique_frame_count`; and artifact scope, crop method, verification,
and trust flags are mutually consistent. `review_required: false` is accepted only for
a verified manual `slide_region`; setting one optimistic flag cannot turn a context PDF
into a deck. Persistence replaces this complete owner-versioned manifest rather than
deep-merging it, so obsolete v1/v2 fields cannot survive inside a schema-v3 record.

`retained_frames` maps each PDF page to the zero-based index in the sampled frame
sequence and its approximate video timestamp (`frame_index / fps_used`). Both artifacts
use the same page order. `unique_frame_count` is the number of retained samples and each
artifact's `page_count`; it is not an authored slide count. The extractor deliberately
leaves `authored_slide_count` null. Populate the talk's queryable `slide_count` only from
corroborated deck numbering, a native deck, or another authored source.

An unverified auto or manual crop may still produce a `slide_region` candidate, but it
must carry `trusted_for_authored_slide_analysis: false` and
`review_required: true`. Visually inspect it against the source/context, then rerun with
the checked coordinates and `--region-verified`; do not promote the candidate to
`slides/{youtube_id}.pdf` or `slides_local_path`. A version-2 `output_pdf` may contain
uncropped broadcast frames even when a crop was applied, and its
`unique_slides_count` was actually a retained-frame count. Treat both fields as legacy,
untrusted evidence and re-extract rather than inferring version-3 artifact scope.

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
| Text-channel provenance | Recursive shape text, table cells, picture OCR, background OCR | `text_channels[]` |
| Unsupported visual containers | SmartArt, charts, OLE/media, unknown graphic frames, damaged assets | `unsupported_content[]`, `render_required_reasons[]` |
| Native timing structure | Raw timing containers, behavior elements, visibility sets, transitions, and media timing | `native_timing`, `native_timing_summary` |

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
- **Observed playback, concurrency, perceived target, or delivery quality** — raw
  timing elements establish package structure only. Counts do not show which markup
  branch or build ran, whether effects were simultaneous, or what the audience saw

### Schema:

```json
{
  "schema_version": 2,
  "pipeline_version": "1.1.0",
  "input_fingerprint": {
    "algorithm": "sha256",
    "digest": "64 lowercase hex characters",
    "size_bytes": 123456
  },
  "pptx_path": "Conference/Year/Talk.pptx",
  "slide_count": 60,
  "aspect_ratio": "16:9",
  "slide_width_inches": 13.33,
  "slide_height_inches": 7.5,
  "corrupt_assets": [
    {
      "part_name": "ppt/media/image7.png",
      "error_type": "crc_mismatch",
      "status": "recovered_with_placeholder"
    }
  ],
  "per_slide_visual": [
    {
      "slide_number": 1,
      "background_color_hex": "#5B2C6F",
      "background_type": "solid|pattern|image|gradient|solid_from_layout|solid_from_master|unknown",
      "layout_name": "Title Slide  (free text from slide.slide_layout.name — not an enum)",
      "shape_count": 3,
      "shape_count_recursive": 5,
      "has_text_frame_shapes": true,
      "has_extracted_text": true,
      "has_image": false,
      "image_area_ratio": 0.0,
      "text_extraction_confidence": "high|low",
      "text_content_preview": "Talk Title",
      "ocr_text": "",
      "text_extraction_method": "shapes|shapes+ocr|shapes+ocr_unavailable",
      "text_channels": [
        {
          "channel": "shape_text|table_cell_text|picture_ocr|background_image_ocr|<unsupported-kind>_text|group_container_text",
          "text": "Talk Title",
          "confidence": "high|medium|low",
          "status": "extracted|empty|skipped|unavailable|unsupported|requires_render",
          "provenance": {
            "source": "pptx_shape_text_frame",
            "shape_path": ["Group 1", "Title 2"]
          }
        }
      ],
      "unsupported_content": [
        {
          "content_type": "smartart|chart|graphic_frame|embedded_ole_object|linked_ole_object|media|unreadable_picture|corrupt_embedded_asset",
          "shape_name": "Diagram 4",
          "shape_path": ["Diagram 4"],
          "graphic_data_uri": "http://schemas.openxmlformats.org/drawingml/2006/diagram",
          "reason": "visible text or labels may not be represented in PPTX text frames",
          "render_required": true
        }
      ],
      "has_unsupported_content": true,
      "render_required": true,
      "render_required_reasons": ["smartart"],
      "footer_text": "@handle | #conf | #topic | website",
      "has_speaker_notes": true,
      "native_timing": {
        "timing_element_present": true,
        "timing_element_count": 1,
        "transition_count": 1,
        "set_action_count": 2,
        "visibility_set_action_count": 1,
        "animation_behavior_counts": {
          "general": 1,
          "color": 0,
          "effect": 2,
          "motion": 1,
          "rotation": 1,
          "scale": 1,
          "total": 6
        },
        "media_timing_counts": {"audio": 1, "video": 0, "total": 1},
        "has_animation_behaviors": true,
        "has_media_timing": true,
        "provenance": {
          "source": "pptx_package_xml",
          "measurement": "raw_ooxml_element_counts",
          "observed_playback": false,
          "part_name": "ppt/slides/slide1.xml"
        }
      },
      "shapes_summary": [
        {"name": "Title 1", "shape_type": "PLACEHOLDER (14)", "shape_path": ["Title 1"], "group_depth": 0, "font_name": "Bangers", "font_size": 36, "font_color": "#FFFFFF", "bold": true},
        {"name": "Cloud 2", "shape_type": "AUTO_SHAPE (1)", "shape_path": ["Cloud 2"], "group_depth": 0, "auto_shape_type": "CLOUD_CALLOUT (108)", "fill_color": "#FFFFFF", "line_color": "#000000"}
      ]
    }
  ],
  "native_timing_summary": {
    "slides_with_timing_elements": 12,
    "slides_with_transitions": 40,
    "slides_with_animation_behaviors": 10,
    "slides_with_media_timing": 2,
    "timing_element_count": 12,
    "transition_count": 40,
    "set_action_count": 18,
    "visibility_set_action_count": 9,
    "animation_behavior_counts": {
      "general": 7,
      "color": 3,
      "effect": 15,
      "motion": 4,
      "rotation": 2,
      "scale": 5,
      "total": 36
    },
    "media_timing_counts": {"audio": 2, "video": 1, "total": 3},
    "provenance": {
      "source": "pptx_package_xml",
      "measurement": "raw_ooxml_element_counts",
      "observed_playback": false
    }
  },
  "global_design": {
    "fonts_used": {"Bangers": 45, "Arial": 10},
    "background_colors": {"#5B2C6F": 12, "#C0392B": 8},
    "shape_types_used": {"CLOUD_CALLOUT (108)": 15, "EXPLOSION1 (89)": 8},
    "color_sequence": ["#5B2C6F", "#FFFFFF", "#C0392B", "..."]
  }
}
```

`schema_version` tracks this JSON field shape. Missing means legacy shape `0`;
v1 added the version/fingerprint and current v2 adds `native_timing` to every
slide plus `native_timing_summary`. `pipeline_version` tracks extraction behavior
and changes when the walk, classification, confidence, OCR, recovery, or timing
behavior changes; current is `1.1.0`.

These records are transient per-invocation output, not a persisted artifact with
an in-place migration. Regenerate old output with the current extractor. A timing
reader must treat v0/v1 as **timing unknown**, never as all-zero, and rerun; an
unknown future schema version is no usable prior output. The vault-profile layout
reader may dual-read v1/v2 because `template_layouts` is unchanged, but it also
rejects missing/unknown versions and reruns instead of guessing. This is the only
declared cross-pipeline compatibility exception.
`input_fingerprint` hashes the exact source PPTX bytes before any in-memory
media recovery; identical bytes have the same fingerprint regardless of path.

`corrupt_assets` is empty on a healthy package. A bad-CRC member under
`ppt/media/` is replaced only in an in-memory package with a transparent
placeholder, allowing healthy text and slides to survive. Structural members
(XML, relationships, content types) are never discarded; their corruption is
a hard extraction error.

`native_timing` inventories exact PresentationML element names under each slide's
`<p:timing>` tree. `general` means the exact `<p:anim>` behavior, not a total;
`effect`, `motion`, `rotation`, `scale`, and `color` likewise count only their
specific behavior elements. `visibility_set_action_count` is the subset of
`<p:set>` actions whose attribute name is `visibility` or ends in
`.visibility`. Audio/video time nodes have a separate `media_timing_counts` lane,
and slide transitions are counted separately whether or not a timing tree exists.

All counts are raw OOXML structure. Markup Compatibility `Choice` and `Fallback`
branches are both present in the package and both counted. The provenance field's
`observed_playback: false` is load-bearing: timing-container presence, media timing,
or a motion behavior element does not prove execution, concurrency, smoothness,
the perceived target, or delivered audience behavior. Adjacent static duplicate
slides can still be progressive-reveal evidence after rendered-state inspection;
they correctly carry zero native timing when the author implemented the build as
separate slides.

**`text_extraction_confidence` gates how the text fields may be read.**
`text_content_preview` aggregates native shape-frame and table-cell text for
backward compatibility. `text_channels` is authoritative for provenance:
recursive shape text, table cells, picture OCR, and background-image OCR remain
distinct. Text rendered inside pictures, SmartArt, charts, or other unsupported
containers can remain invisible. On a `"low"` slide:

- empty `text_content_preview` means *unreadable by native shape/table
  channels*, never wordless
- `ocr_text` holds the backward-compatible aggregate of picture and background
  image OCR channels when the engine ran (`text_extraction_method:
  "shapes+ocr"`). Use it for cites,
  transcript cross-checks, language policy on slide text, and pattern evidence
- `text_extraction_method` is `"shapes"` when OCR was not attempted (high
  confidence, `--no-ocr`, or no usable image blob), `"shapes+ocr"` when it ran,
  `"shapes+ocr_unavailable"` when the engine was missing
- Dimensions 8/13 **design** judgment (density, two-layer legibility, composition)
  still requires the rendered image — OCR is inventory, not layout (see
  [known-issues.md](known-issues.md) § "Shape Extraction Is Blind to Text Baked
  Into Images" and [subagent-instructions.md](subagent-instructions.md))

`has_text_frame_shapes` reports shapes carrying text frames — not whether the
slide shows text. `has_extracted_text` covers every emitted text channel,
including table cells and OCR.

Groups and tables are traversed, but they still force `low`: nested transforms,
merged cells, and embedded visual content can affect visible reading order.
SmartArt, charts, OLE/media objects, unknown graphic frames, unreadable images,
and recovered corrupt assets are listed in `unsupported_content`. Never infer
completeness when `render_required` is true; use
`render_required_reasons` to choose the fallback.

`image_area_ratio` is the **largest** PICTURE shape's area as a fraction of the
slide, rounded to 3 decimals; always present. `0.0` means no picture, unreadable
picture geometry, **or** a picture small enough to round down — it is not proof
that the slide has no picture. The confidence threshold
compares against the unrounded value, so a reported ratio equal to the
threshold is not proof of which way the slide was classified.

It measures picture **shapes** only. A slide whose image is a *background*
reports `background_type: "image"` and `text_extraction_confidence: "low"`
while `image_area_ratio` stays `0.0` — the background covers the canvas by
definition and has no picture geometry to measure. When its relationship and
blob are valid, OCR appears in a distinct `background_image_ocr` channel; a
missing blob is recorded as `status: "unavailable"`. Either way, rendering is
still required for design judgment. Read the confidence, never the ratio, to
decide whether a slide needs a visual pass.
