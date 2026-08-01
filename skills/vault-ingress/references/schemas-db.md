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
    "schema_version": 5,
    "transcript_source": "youtube_auto|whisper|manual|none  (how the transcript was obtained; MAY BE ABSENT — see below)",
    "transcript_path": "transcripts/{id}.txt  (optional vault-relative path; required for non-YouTube transcript evidence)",
    "slide_source": "pptx|pdf|both|video_extracted|none  (set in Step 2 per slide source hierarchy)",
    "slides_local_path": "slides/<artifact>.pdf  (optional explicit local PDF; legacy readers also accept slides_pdf_path/pdf_path)",
    "pptx_visual_status": "pending|extracted|no_pptx",
    "status": "pending|needs-reprocessing|reprocessing-inflight|processed|processed_partial|skipped_no_sources|skipped_download_failed|skipped_duplicate",
    "reprocess_reason": "machine-readable reason for needs-reprocessing, or null",
    "reprocess_generation": 1,
    "_queue_claim": {
      "schema_version": 5,
      "run_id": "reparse-2026-07",
      "batch_id": "25",
      "claimed_at": "2026-07-31T18:00:00+00:00",
      "previous_status": "needs-reprocessing",
      "reprocess_generation": 1,
      "required_return_schema_version": 5,
      "adherence_baseline": {
        "schema_version": 2,
        "as_of": "2026-07-31T18:00:00+00:00",
        "scope": "global",
        "active_batch_excluded": true,
        "excluded_filenames": ["2024-04-10-talk-slug.md"],
        "eligible_statuses": ["processed", "processed_partial"],
        "pattern_scoring_generation_status": "current",
        "pattern_scoring_generation_reasons": [],
        "pattern_catalog_fingerprint": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "pattern_scoring_schema_version": 5,
        "eligible_talk_count": 25,
        "opportunity_coverage_identity": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
        "raw_score_comparison_status": "available",
        "raw_score_comparison_reason": null,
        "scored_talk_count": 25,
        "pattern_score_sum": 170,
        "average_pattern_score": 6.8
      },
      "state": "claimed"
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
    "pattern_scoring_generation_status": "current",
    "pattern_scoring_generation_reasons": [],
    "pattern_scoring_schema_version": 5,
    "pattern_catalog_fingerprint": "sha256 of the exact catalog files used",
    "pattern_observations": {
      "evidence_schema_version": 2,
      "evidence_sources": ["transcript"],
      "source_inspection": [{
        "source": "transcript",
        "line_ranges": [[1, 240]],
        "line_count": 240,
        "coverage_complete": true,
        "artifact_root": "vault",
        "artifact_path": "transcripts/dQw4w9WgXcQ.txt",
        "artifact_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
      }],
      "pattern_ids": [],
      "antipattern_ids": [],
      "not_evaluable_ids": [],
      "pattern_score": 0,
      "patterns_detected": [],
      "antipatterns_detected": [],
      "applicability_assessments": [],
      "pattern_outcomes": [
        {"pattern_id": "another-catalog-id", "outcome": "not_evaluable"},
        {"pattern_id": "one-catalog-id", "outcome": "undetected"}
      ],
      "opportunity_coverage_identity": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
      "not_evaluable": []
    }
  }],
  "_comment_schema_version": "Talk-record schema version, stamped by persist-results.py. v1 is the implicit unversioned shape. v2 makes transcript_source optional. Two incompatible v3 lineages were emitted; v4 is their source-located union and remains archival with evidence ledger v1. V5 adds applicability assessments, exhaustive outcomes, opportunity-coverage identity, evidence ledger v2, and current scoring schema v5. Migration preserves v1-v4 evidence and never synthesizes v5 outcomes.",
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

## Shownotes Scan/Import Report

Run `scan-shownotes.py` against the canonical tracking database. The scanner
reads `config.shownotes.source` for local sources and resolves
`path_or_url/talks_subdir` inside the configured root. A null or absent
`config.shownotes` may use the legacy absolute `config.talks_source_dir` during
migration. `remote_url`, `none`, and disabled sources return a structured no-op
without reading Markdown or writing the database.

The command emits report schema v1:

```json
{
  "schema_version": 1,
  "ok": true,
  "mode": "dry-run|apply",
  "operation": "scan|skipped_disabled|skipped_nonlocal",
  "apply_requested": false,
  "database_written": false,
  "mutation_count": 1,
  "scanned_file_count": 1,
  "existing_talk_count": 10,
  "counts": {
    "add": 1,
    "update": 0,
    "unchanged": 0,
    "review_required": 0
  },
  "shownotes": {
    "enabled": true,
    "source_type": "local_jekyll",
    "config_origin": "shownotes|talks_source_dir",
    "root": "/absolute/shownotes/root",
    "talks_subdir": "_talks",
    "talks_directory": "/absolute/shownotes/root/_talks"
  },
  "entries": [{
    "filename": "2026-08-01-talk.md",
    "disposition": "add|update|unchanged|review_required",
    "proposal": {"filename": "2026-08-01-talk.md"},
    "changes": {},
    "issues": [],
    "applied": false
  }]
}
```

Dry-run is the default and never writes. `--apply` adds complete new records
with current talk schema and status `pending`, or fills empty fields on an exact
filename match. Established values are not overwritten. Conflicting,
incomplete, and normalized-collision entries stay `review_required` and never
mutate. `mutation_count` counts deterministic `add` and `update` candidates;
`database_written` records whether an atomic replacement occurred.

Supported Markdown metadata includes YAML, TOML, and JSON frontmatter plus a
body H1 and labeled `Conference`, `Event`, `Venue`, `Date`, `Video`, `Recording`,
`Slides`, or `Deck` links. YouTube and Google Drive identities use the shared
ingress URL parsers. A proposed source matches a rejection when its URL is exact
or its parsed provider ID equals the rejected URL's ID. Such a proposal remains
inactive with `rejected_source_reappeared` until human review supplies a valid
replacement.

The two persisted `pattern_outcomes` rows in the tracking-DB example are
illustrative only; a real v5 persisted talk contains exactly one sorted row for
every observable catalog entry. The raw v5 worker return below includes
`applicability_assessments` but must omit engine-owned
`evidence_schema_version`, `pattern_outcomes`, and
`opportunity_coverage_identity`; persistence derives all three.

The copyable talk above is a current scoring generation. A replayable legacy
return that cannot prove the current evidence contract instead stores this
mutually exclusive shape and omits both `pattern_scoring_schema_version` and
`pattern_catalog_fingerprint`:

```json
{
  "pattern_scoring_generation_status": "legacy_unbaselineable",
  "pattern_scoring_generation_reasons": [
    "comparison_group_ambiguous:gradual-consistency"
  ]
}
```

A fresh v5 worker uses the exact empty adherence sentinel and does not author a
raw-score comparison. Only an owner-side consumer that sees the canonical talk
outcomes may compare against a baseline carrying the same
`opportunity_coverage_identity`. Baseline schema v2 keeps all fresh-v5 talks in
`eligible_talk_count`; `scored_talk_count` is only the exact-identity raw-score
cohort. Mixed identities use zero/null score aggregates plus explicit
`raw_score_comparison_status: "unavailable"` and reason
`mixed_opportunity_coverage` rather than normalizing unlike denominators. A
non-empty cohort whose exhaustive outcome matrix contains no `detected` or
`undetected` row also uses zero/null aggregates with reason
`no_evaluable_pattern_opportunities`; missing opportunities must never publish
an available zero average.

`source_identity` and `source_relation` are optional. Their owned shape,
offline comparison rules, duplicate semantics, and compatibility policy are in
[source-identity-preflight.md](source-identity-preflight.md). Do not fetch live
metadata during validation. Capture provider evidence separately with the
read-only flow in [source-identity-audit.md](source-identity-audit.md), review it,
then run the preflight. Uploader/upload date never establish speaker/recorded
date, and a captured webpage URL is never an automatic active-source repair.

Queue eligibility is not encoded by `video_url` alone. One shared resolver derives
auditable `source_capabilities` for queueing, return provenance, and terminal
status checks. A local capability requires an artifact that the source-specific
quality checker/parser/probe can actually read under the vault or configured source
root; a non-empty, escaped, symlinked, missing, or malformed local path is not a
capability. Active remote video/slide acquisition paths remain separate eligible
capabilities because processing performs that acquisition. `transcript_source:
manual` is provenance only and does not prove an artifact exists. Legacy
no-video/no-transcript statuses normalize to `skipped_no_sources` only when the
shared verified-local plus remote-acquisition capability list is empty.

Every fresh queue claim is schema v5 and carries exactly the
`required_return_schema_version` and `adherence_baseline` fields shown above.
The queue owner builds one baseline before mutating any selected talk, copies it
unchanged to every batch member, and requires `adherence_baseline.as_of` to equal
the canonical `claimed_at`. `excluded_filenames` is the sorted exact batch;
exclusion happens before generation identity or score inspection so a talk's
prior result cannot compare with itself. Only eligible talks stamped `current`
with empty reasons and the baseline's exact catalog fingerprint/scoring schema
contribute to `eligible_talk_count`. Exact opportunity identity additionally
controls the raw-score cohort. Promoted and nested pattern scores must agree.
Count and sum are integers; an available average uses decimal
`ROUND_HALF_EVEN` to two places.

A closed claim adds `released_at` and `release_reason`; a completed claim also
adds terminal `result_status` and the canonical `result_payload_sha256` receipt.
Those suffix fields are forbidden while `state` is `claimed`.

Claim records are immutable generation evidence. Idempotent replay returns the
stored claim and leaves DB bytes unchanged. Recovery closes but preserves the
same v5 snapshot; a later claim increments `reprocess_generation` and captures a
fresh snapshot. Historical retry epochs may span `_queue_claim_history` and
current `_queue_claim` locations, but their combined members must still match
the baseline's exact excluded filenames and share one snapshot.

The four version axes are deliberately explicit:

| Claim | Authorized return | Persisted talk | Pattern scoring |
|---|---|---|---|
| v1 or v2 | saved v1 or v2 only | migrated legacy record | never current v5 |
| v3 | v3 only | migrated union-safe record | never current v5 |
| v4 | v4 only | archival source-located v4 | never current v5 |
| v5 | v5 only | v5 | v5 when canonical evidence/outcomes are fresh |

Claim/return compatibility authorizes replay; it does not grant current scoring
status. Only a v5 return canonicalized from current source artifacts can produce
talk schema v5 with `pattern_scoring_schema_version: 5`, evidence ledger v2,
exhaustive outcomes, and `pattern_scoring_generation_status: "current"`.
V1–v3 detections retain the explicit empty-citation legacy sentinel. V4 keeps
its source locations and evidence ledger v1 but migration never fabricates v5
applicability assessments, outcomes, or opportunity identity.

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
  "return_schema_version": 5,
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
  "transcript_path": "transcripts/{id}.txt  (optional exact repeat of a pre-registered non-YouTube path; cannot introduce citation authority)",
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
    "image_source_distribution": {"ai_generated": 0, "speaker_created": 7, "stock_photo": 0, "unknown": 28, "none": 12},
    "image_source_distribution_basis": "Unit: slide; classify each slide by its dominant image source using asset manifests; origins without provenance count as unknown.",
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
    },
    "key_data_points": {},
    "named_authorities": {},
    "time_bound_promotion": {},
    "native_deck_audit": {},
    "native_timing_audit": {},
    "source_comparison": {},
    "source_identity": {},
    "animation_observations": {},
    "pptx_pdf_reconciliation": {},
    "extensions": {
      "producer_namespace": {"additive extension data": true}
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
  "adherence_assessment": "",
  "new_patterns": "100-300 words on NEW patterns not in summary, or ''",
  "summary_updates": "50-200 words: additions for rhetoric-style-summary.md by section #, or ''",
  "pattern_observations": {
    "evidence_sources": [
      "every source actually inspected: static_slides|native_deck|delivery_video|transcript|source_comparison"
    ],
    "source_inspection": [
      {"source": "transcript", "line_ranges": [[1, 240]]},
      {"source": "static_slides", "page_ranges": [[1, 60]]},
      {"source": "native_deck", "page_ranges": [[1, 60]]},
      {"source": "delivery_video", "time_ranges": [[0, 1800.0]]},
      {
        "source": "source_comparison",
        "evidence_sources_used": ["static_slides", "native_deck"],
        "comparison_scope": "full"
      },
      {
        "source": "source_comparison",
        "evidence_sources_used": ["transcript", "delivery_video"],
        "comparison_scope": "partial"
      }
    ],
    "patterns_detected": [
      {
        "pattern_id": "progressive-reveal",
        "confidence": "strong|moderate|weak",
        "evidence_source": "static_slides|native_deck|delivery_video|transcript|source_comparison",
        "evidence": "Three consecutive slides add one element at a time.",
        "evidence_citations": [
          {"source": "native_deck", "channel": "slide_sequence", "slide_numbers": [21, 22, 23]}
        ]
      }
    ],
    "antipatterns_detected": [
      {
        "pattern_id": "shortchanged",
        "confidence": "strong|moderate|weak",
        "evidence_source": "static_slides|native_deck|delivery_video|transcript|source_comparison",
        "evidence": "The talk announces the close before beginning a new topic.",
        "evidence_citations": [
          {"source": "transcript", "channel": "timed_transcript", "quote": "Before I finish, there is one more architecture topic."}
        ]
      }
    ],
    "applicability_assessments": [
      {
        "pattern_id": "pattern-with-applicability-contract",
        "result": "not_applicable",
        "condition_id": "catalog-owned-condition-id",
        "evidence_source": "transcript",
        "evidence": "The complete transcript establishes the catalog-owned condition.",
        "evidence_citations": [
          {"source": "transcript", "channel": "transcript", "quote": "A unique source-language span of at least four words"}
        ]
      }
    ],
    "not_evaluable": [
      {
        "pattern_id": "composite-animation",
        "reason_code": "missing_required_source_coverage"
      },
      {
        "pattern_id": "catalog-entry-awaiting-owner-gate",
        "reason_code": "source_gate_pending_owner_review"
      },
      {
        "pattern_id": "positive-only-pattern",
        "reason_code": "absence_not_authorized_by_catalog"
      },
      {
        "pattern_id": "conditional-pattern-with-incomplete-coverage",
        "reason_code": "missing_applicability_source_coverage"
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

A `source_comparison` detection or applicability assessment adds
`"evidence_sources_used": ["static_slides", "native_deck"]` (or another
exact qualifying catalog group). Return v5 enforces this proof structurally.
The field is forbidden on non-comparison records. Only replayed v1–v3 artifacts may omit it, and persistence infers
the proof only when exactly one pair qualifies.

`per_slide_visual`, when present, is a closed, complete slide ledger. It requires
a positive integer `slide_count` and exactly that many rows in ascending order,
with `slide_number` covering every integer from 1 through `slide_count` once.
Every row has exactly the seven keys shown above; aliases and extra keys are
rejected. `background_color_name` is an open non-empty label so a newly observed
palette can be named. `content_type` and `image_composition` use the closed
vocabularies shown above, and the three `has_*` values are booleans.
`background_color_sequence`, when supplied, must reproduce the row background
labels in order. `meme_count`, when supplied with the ledger, must equal the
number of `meme_only` plus `meme_with_text` rows. No equivalent row-derived
check exists for `image_only_slide_count`: visible text baked into an image
distinguishes that measure from image composition and meme classification.

`image_source_distribution` is strictly a count map: each non-empty string key
names a source/provenance class and each value is a non-negative integer. Visual
appearance does not establish authorship. Do not infer `ai_generated`,
`stock_photo`, or another origin from style alone; count unverified origins as
`unknown`. Content/format labels such as “meme” and “screenshot” are not
authorship provenance, and free-form entries such as `classification_note` do
not belong in this map. If observable visual categories need their own map,
introduce a distinct schema field rather than mixing notes or category metadata
into source counts. Whenever the map is present, its sibling
`image_source_distribution_basis` is required and must be a non-empty string.
The basis states the counting unit (`slide`, `page`, or `asset`), the
classification rule including how a dominant class is selected, the provenance
evidence used, and how unverified origins are counted as `unknown`. Both fields
are authored-slide evidence and cannot be supplied from untrusted video context.

The worker matches the active claim contract. Every fresh claim is schema v5
with `required_return_schema_version: 5`, and only that exact claim authorizes a
v5 return. Saved claim schemas v1/v2 authorize only return schemas v1/v2;
schema v3 authorizes only v3; schema v4 authorizes only archival v4. Recover a
live legacy lease and issue a new v5 generation; never mutate its claim to make
a newer return appear compatible.

For newly emitted work, `validate-returns.py` must report the processed talk's
scoring-generation status as `current`; a valid but
`legacy_unbaselineable` result is replay-only and must be repaired.

Versions 2–5 share the complete-snapshot merge contract: supplied declared
scalar and list fields replace prior values, including empties only where the
field contract permits emptiness; complete structured maps and each verbatim
lane replace their prior snapshots; omitted fields remain untouched. The
image-source distribution and its basis form one dependent group. Unregistered
incoming structured objects fail closed instead of acquiring accidental
recursive-merge semantics. Historical returns with no version field, or with
explicit version 1, retain the legacy additive merge contract so saved
artifacts remain replayable. Unknown future versions are rejected.

The structured snapshot objects currently registered for atomic replacement are
`image_source_distribution`, `color_coded_backgrounds`,
`typography_observations`, `footer_observations`, `shape_observations`,
`video_extraction`, `key_data_points`, `named_authorities`,
`time_bound_promotion`, `native_deck_audit`, `native_timing_audit`,
`source_comparison`, `source_identity`, `animation_observations`, and
`pptx_pdf_reconciliation`; `per_slide_visual` is the corresponding atomic array.
Their complete nested contents come from the current analysis, so no child from an
older run survives. Experimental recursively additive data must live under the
explicit `structured_data.extensions` object. A new top-level object needs a named
policy here and in `STRUCTURED_FIELD_POLICIES` before a snapshot return may use it.
The six documented `verbatim_examples` lanes are exact: a stale undeclared lane makes
the effective snapshot candidate invalid until `clear_fields` removes it. A
valid snapshot verbatim object may still repair a legacy non-object container
atomically.

Every processed return carries the required top-level analysis blocks and the
complete required `pattern_observations` fields. Individual `structured_data`
fields and `verbatim_examples` lanes remain optional for partial-return and legacy
compatibility: omission preserves the prior field, while a supplied empty value
records that the current analysis found none. Required prose fields use an empty
string only for `adherence_assessment`, `new_patterns`, and `summary_updates`.
For `adherence_assessment`, the no-assessment sentinel is exactly `""`; whitespace-only
text is invalid.
Fresh return v5 uses exact `adherence_assessment: ""` and omits
`adherence_comparison`. The worker cannot know the engine-owned canonical talk
`opportunity_coverage_identity`. An owner-side consumer may construct a numeric
comparison only after persistence, only when the talk identity exactly equals a
schema-v2 baseline identity, `raw_score_comparison_status` is `available`, and
the baseline has at least ten exact-identity scored talks. Comparisons from
return v1–v4 are archival only and never verified current numeric evidence.
Versions 2–5 require `rhetoric_notes` and `areas_for_improvement` to contain
substantive non-whitespace analysis. An unknown `transcript_source` is omitted; a present value
must be one of the declared enums and must never be JSON `null`. Missing/version-1
returns retain their historical type-only and empty-value no-op behavior. A skipped
terminal return may contain only `filename`, `return_schema_version`, `queue_claim`,
and `status`. Both
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
For claim v3–v5, every live batch member must also share one canonical
`claimed_at`, one identical baseline, and an `excluded_filenames` array equal to
the exact sorted batch. Persistence validates all of those conditions before
the first candidate merge; one mismatch leaves both DB and analysis artifacts
unchanged.

Queue-claim schema v2 adds `result_payload_sha256` to completed claims; schema
v3 adds the required-return version and immutable adherence snapshot. Schema v4
freezes those fields to the source-located return-v4/scoring-v4 contract. Schema
v5 carries the v5 return/scoring contract and schema-v2 baseline. The
receipt hashes the exact return payload after stable JSON key/whitespace
canonicalization. `persist-results.py` closes v1 as v2 and closes v2–v5 at
their own versions, storing the receipt for every completed v2–v5 claim. The analysis writer
recomputes it and rejects a substituted payload. `queue-state.py` reads v1–v5
without mutating `inspect` or idempotent replay. An already completed v1 claim
has no reconstructable receipt and therefore cannot authorize an analysis
replacement until a fresh generation is processed. Unknown future claim
versions fail closed.

Recovery never rewrites a claim snapshot. It marks the generation closed and
restores its prior claimable status; reclaiming creates a new generation with a
fresh pre-mutation baseline. A historical v3/v4/v5 batch may therefore be split across
current and history storage locations, but the combined `(run_id, batch_id,
claimed_at)` epoch must still have exact membership and one baseline.

Terminal skip reasons are state-bound too. `skipped_no_sources` requires an
empty capability list. `skipped_download_failed` requires a remote video/slide
acquisition path and no remaining verified local transcript, PPTX, PDF, or video
artifact; a stale local declaration does not block that terminal result.
`skipped_duplicate` requires `source_relation.type: duplicate` plus a non-empty
`target_filename`.

Before rendering a processed result, `write-analysis.py` recomputes the scoring
generation from the receipt-bound return and current catalog. A current result
must carry `pattern_scoring_generation_status: current`, an empty reasons array,
scoring schema 5, and the exact catalog fingerprint. A replayable v1–v4 result
that cannot prove the current evidence contract carries
`legacy_unbaselineable` plus exact sorted machine reasons and must not retain a
current scoring version or fingerprint. Its Markdown visibly labels adherence
prose `legacy-unverified` and states that it is excluded from current numeric
baselines, Section 15 aggregates, and speaker profiles. A v2–v4 snapshot replay
also clears any stale authenticated `adherence_comparison` from a prior
generation. Skipped results are `not_applicable` in validator and
persistence reports and do not render or restamp prior analysis-generation
metadata.

After all members merge successfully, `persist-results.py` emits
`current_adherence_baseline` on stdout. It uses baseline schema version 2 and is
explicitly all-inclusive: `active_batch_excluded: false` and
`excluded_filenames: []`. Its `as_of` is the authoritative completion stamp.
`eligible_talk_count` describes every fresh-v5 candidate; score count/sum/average
describe only one exact opportunity-identity cohort. Mixed identities make the
raw-score comparison unavailable with zero/null score aggregates while retaining
the full per-pattern opportunity cohort. A shared identity with no evaluable
outcome uses the same zero/null sentinel with
`no_evaluable_pattern_opportunities` rather than publishing an available `0.0`.
Section 15 and profile generation consume exact current-generation talk data and
this post-batch aggregate; they must not recompute after member 1, use a
processing-date cohort, or mutate a preclaim baseline.

The completed return receipt authorizes rendering, but snapshot analysis-owned
content comes from the validated persisted effective talk, not the partial raw
return. This is the single canonical merged payload: a structured field or verbatim
lane omitted by the return and preserved by persistence remains present in Markdown.
`catalog_feedback` is the sole receipt-bound rendering side channel read directly
from the return because it is intentionally not stored on the talk.

Analysis replacement is batch-transactional. The writer preflights every target,
including normalized/case-fold collisions with existing output-directory
entries and exact directory/special-file targets, then stages every body before
the first replacement. Existing targets move to same-directory recovery backups
during commit; a later failure restores them in reverse order. Exact target
symlinks are moved/replaced as directory entries, so their external targets are
never followed.

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

`clear_fields` explicitly deletes prior analysis before the return is applied. Allowed paths
are top-level analysis prose/provenance scalars or leaves under
`structured_data`, `verbatim_examples`, and `pattern_observations`. It cannot
clear queue identity, source URLs, catalog metadata, or the talk record itself.
Clearing a promoted structured scalar clears its top-level copy too. A supplied
v2–v5 replacement wins after a clear; permitted empty values are real snapshots,
not no-ops. Legacy v1 empty values retain their historical additive no-op behavior.

`evidence_source` uses the enum defined by the pattern index's Evidence-Source Contract.
Detected entries must name a qualifying source. Strong detections use
`strong_evaluable_from` (defaulting to `evaluable_from`); moderate/weak
detections use the base gate. A `source_comparison` detection must name both
sources in its evidence. Every v4/v5 return carries a
duplicate-free `evidence_sources_used` array exactly equal to one qualifying
underlying group. Saved v1–v3 replay may omit that array; persistence infers it
only when exactly one pair qualifies. Zero or multiple qualifying groups remain
replayable but are excluded from current baselines. The `source_comparison`
marker does not count as an underlying source and is forbidden as a catalog
gate member or singleton.

For an undetected entry, `absence_evaluable_from` defaults to the base gate. V4
absence remains archival and is never current. In v5, complete canonical
inspection coverage is necessary but never sufficient to authorize absence:
the persistence engine must also derive `absence_capability_complete: true` for
the current source role, and the entry's `absence_evaluable_from` singleton gate
must match that complete source. An unsatisfied gate requires exactly
`{"pattern_id": "...", "reason_code": "missing_required_source_coverage"}`.
An explicit null absence gate requires `absence_not_authorized_by_catalog` and
keeps the entry positive-only. In v5, incomplete applicability coverage requires
`missing_applicability_source_coverage`; complete applicability coverage requires
exactly one source-located assessment for every nondetected conditional entry.
An observable entry with no owner-approved gate requires
`source_gate_pending_owner_review`; it cannot be detected or silently counted
as absent. This is fail-closed catalog debt, not a model waiver. A valid positive
detection takes precedence for a gated entry. Not-evaluable entries are excluded
from `pattern_ids`, `antipattern_ids`, and every `pattern_score` count. Never put
an unavailable entry in a detected array or treat it as an absent pattern.

`catalog_feedback` is mandatory on current processed returns and uses only the
five lanes shown above (empty arrays are valid). Exact IDs and
pattern/antipattern polarity are validated against catalog YAML; new suggested
names occupy a separate namespace and carry `proposed_polarity`. The read-only
aggregator also audits historical returns, reports legacy compatibility issues
without silently repairing them, and preserves per-entry provenance. Its owned
schema and aggregation contract are in
[catalog-feedback-intake.md](catalog-feedback-intake.md).

### Source Inspection Receipt Schema

Every return v4/v5 carries `pattern_observations.source_inspection`. Its source-name
set exactly equals `evidence_sources`; comparison records may repeat the
`source_comparison` name only for distinct underlying groups. Worker-authored
records are closed objects:

```json
{"source": "transcript", "line_ranges": [[1, 120], [121, 240]]}
{"source": "static_slides", "page_ranges": [[1, 20], [25, 60]]}
{"source": "native_deck", "page_ranges": [[1, 60]]}
{"source": "delivery_video", "time_ranges": [[0, 900.0], [905.0, 1800.0]]}
{"source": "source_comparison", "evidence_sources_used": ["static_slides", "native_deck"], "comparison_scope": "full"}
{"source": "source_comparison", "evidence_sources_used": ["transcript", "delivery_video"], "comparison_scope": "partial"}
```

Line/page ranges are inclusive positive integers. Time ranges are finite
non-negative seconds with `end > start`. In all three lanes, ranges are ordered,
non-overlapping, and may be adjacent. Persistence reads the exact artifacts to
derive their line/page count or video duration. Coverage is complete only when
the ranges start at 1 (or time 0), reach the verified final bound, and contain no
gap. A comparison's range receipt is complete only when `comparison_scope` is
`full` and every named underlying source has complete range coverage. That
remains positive evidence; neither `full` nor `partial` comparison proves an
undetected or applicability outcome until a future canonical receipt establishes
aligned modality capture.

`native_deck` and `static_slides` are distinct evidence sources. Reading or
extracting a `.pptx` establishes only `native_deck`; it never silently creates a
rendered-page receipt or authorizes static-slide absence. A real PDF, a trusted
video-extracted slide artifact, or a stable PDF exported from the exact PPTX may
establish positive `static_slides` evidence only when the concrete artifact is
actually inspected and identity-bound in canonical persistence. Video-extracted
static pages, bare `native_deck`, and bare `delivery_video` are positive-only;
their current receipts do not prove exhaustive modality capture. A genuine
authored/rendered PDF may be absence-capable when its catalog gate permits it.

Canonical rows make the distinction auditable. `coverage_complete` is locator
range completeness. `absence_capability_complete` is the independent engine-owned
negative/applicability gate, and `absence_capability_reason` carries its stable
reason (`authorized_transcript`, `authorized_rendered_static`,
`nonexhaustive_video_extraction`, `bare_native_deck`, `bare_delivery_video`,
`comparison_alignment_unverified`, or `incomplete_range_coverage`). Workers
must not return either absence-capability field.

Workers never return canonical receipt enrichment. Persistence adds
`artifact_root`, vault/root-relative `artifact_path`, `artifact_sha256`, optional
timing-artifact identity, required quality-artifact identity for current v4/v5
transcript evidence, derived `line_count`/`page_count`/`duration_seconds`, and
`coverage_complete`; comparison records add `artifact_identities`. Current
cohort readers re-hash these identities and fail stale, missing, symlinked,
relocated, or owner-path-drifted evidence closed. Transcript freshness also
re-runs the hash-bound quality policy against the current owner/provider duration;
a material identity-duration change yields `transcript_quality_context_drift`
even when the transcript and sidecar bytes themselves did not change.

### Pattern Evidence Citation Schema

`evidence` remains the concise human explanation. `evidence_citations` is the
auditable proof. Every newly returned detection requires one or more citations;
`persist-results.py` rejects missing citations, unknown or duplicate pattern IDs,
pattern/antipattern bucket swaps, `observable: false` patterns, and citation
channels not permitted by that pattern's required `evidence_channels`
frontmatter. An observable catalog entry without that field is itself invalid
and stops persistence.

A permitted citation channel is necessary but not sufficient. Every citation's
`source` names the underlying member it locates or supplements, and its `channel`
must be compatible with that source. The detection's `evidence_source` must
independently satisfy its effective source/outcome gate,
and at least one citation must locate proof from that source: transcript evidence
uses `transcript` or `timed_transcript`, static/native deck evidence uses `slides`
or `slide_sequence`, and delivery evidence uses `video`. A `source_comparison`
detection must cite every member named by `evidence_sources_used`.
`talk_metadata` may supplement those citations but cannot replace the qualifying
gate source.

Allowed citation shapes:

```json
{"source": "transcript", "channel": "transcript", "quote": "A unique source-language span of at least four words", "translation": "Required English translation for non-English delivery; otherwise optional"}
{"source": "transcript", "channel": "timed_transcript", "quote": "A unique source-language span of at least four words", "translation": "Required English translation for non-English delivery; otherwise optional"}
{"source": "static_slides", "channel": "slides", "slide_numbers": [4, 17]}
{"source": "native_deck", "channel": "slide_sequence", "slide_numbers": [21, 22, 23]}
{"source": "delivery_video", "channel": "video", "start_seconds": 42.5, "end_seconds": 48.0}
{"source": "delivery_video", "channel": "talk_metadata", "field": "slide_count"}
```

Those are the complete worker-side shapes. A worker supplies the source/channel
and the smallest source locator it can actually claim: quote, slide numbers,
video interval, or metadata field. It must not copy `line_start`, `line_end`,
transcript `start_seconds`/`end_seconds`, artifact root/path/hash fields,
timing/quality-artifact fields, metadata `value`/`owner_value_after_return`, or
any other canonical enrichment from an earlier analysis. Unknown raw citation fields are
rejected. Catalog dimensions are likewise engine-owned; workers should omit
them, although a supplied v4/v5 `dimensions` array is accepted only when it exactly
matches catalog order.

For transcript citations, `quote` is always the exact source-language text needed
for matching. When either preclaim metadata or the validated return's
`structured_data.delivery_language` identifies non-English delivery, a non-empty
English `translation` is required so readers still see English first. It remains
optional for English delivery. The model never supplies a translated composite
string as `quote`, because that string does not occur in the source transcript.
`persist-results.py` verifies that the normalized quote occurs exactly once in
the local transcript and stamps `line_start`/`line_end`; for
`timed_transcript`, it also stamps `start_seconds`/`end_seconds` from a verified
timing sidecar. Model-supplied locations are discarded. A `slide_sequence` must
contain at least two consecutive ascending slide numbers. Slide numbers are
checked against an independently resolved slide artifact/count. A video citation
is valid only when the video was directly reviewed at that interval; the writer
binds its range to an identity-bound local or timed artifact and checks the
verified duration bound. A video URL alone cannot verify a timestamp.
`talk_metadata.value` and `owner_value_after_return` are likewise writer-owned:
the former records the pre-return source value and the latter binds freshness to
the persisted owner value after the return is applied. Citation objects use these
closed field sets; unknown model-supplied fields are rejected.
`talk_metadata.field` is restricted to source/provenance fields declared by `persist-results.py`'s
`TALK_METADATA_FIELDS` and then to the pattern's narrower
`evidence_metadata_fields`; generated prose such as `rhetoric_notes` cannot cite
itself, and an irrelevant metadata field cannot stand in for pattern evidence.

Migrated v1–v3 records may contain `evidence_citations: []`. That is a deliberate
legacy marker: readers may render the old `evidence` prose, but must not present
it as source-verified. The v4/v5 writer never accepts an empty array for a new
detection. `evidence_schema_version` is writer-owned persisted state; workers
must not return it, and legacy detections never acquire it by migration.

The same boundary applies to `not_evaluable`. Workers return only `pattern_id`
and one exact current reason code. Persistence derives
`required_source_groups`, `available_source_groups`, and `capability_fact` from
the catalog and canonical inspection receipt. It also injects catalog dimensions
and canonical slide count where applicable. The raw-return receipt remains the
hash of exactly what the worker sent; canonical enrichment is deterministic and
does not alter that receipt.

## Transcript Timing and Quality Receipt Schemas

`fetch-transcript.py` and `vtt-cleanup.py` keep the readable transcript at
`transcripts/{id}.txt`. When timing is trustworthy they also write
`transcripts/{id}.segments.json`; otherwise a fresh/forced bundle removes any
older timing sidecar. This closed receipt owns acquisition identity and timing
only:

```json
{
  "schema_version": 2,
  "transcript_sha256": "SHA-256 of the exact on-disk transcript bytes",
  "source": "captions|whisper|vtt",
  "provenance": {
    "kind": "youtube_captions",
    "video_id": "dQw4w9WgXcQ",
    "duration_seconds": 212.125
  },
  "segments": [
    {"text": "Timed source text", "start_seconds": 1.2, "end_seconds": 3.4}
  ]
}
```

The top-level keys are exact. `provenance` is exactly one compatible shape:

```json
{"kind": "youtube_captions", "video_id": "dQw4w9WgXcQ", "duration_seconds": 212.125}
{"kind": "youtube_whisper", "video_id": "dQw4w9WgXcQ", "duration_seconds": 212.125}
{"kind": "local_media_whisper", "media_sha256": "64 lowercase hex characters", "duration_seconds": 212.125}
{"kind": "vtt_artifact", "artifact_path": "source.en.vtt", "artifact_sha256": "64 lowercase hex characters", "cue_extent_seconds": 212.125}
```

YouTube and local-media timing require a positive trusted duration. The VTT
path is a safe transcript-directory-relative POSIX path to a non-symlink
regular file; the digest binds its exact bytes and cue extent equals the final
segment boundary. Every segment is canonical, joined segment text equals the
transcript modulo Unicode whitespace layout, and no segment extends past its
source-owned duration beyond the reader's one-second measurement tolerance.
`vtt-cleanup.py` therefore requires both input and explicit output paths; an
existing output bundle is preserved unless `--force` authorizes replacement.

`fetch-transcript.py` separately writes `transcripts/{id}.quality.json`. This
closed receipt owns quality authority even when no timed segments exist:

```json
{
  "schema_version": 1,
  "transcript_sha256": "SHA-256 of the exact on-disk transcript bytes",
  "policy": {
    "schema_version": 1,
    "min_words": 400,
    "duration_seconds": null
  },
  "provenance": {"kind": "fixed_default"}
}
```

The only other provenance forms are exact duration-bound objects:

```json
{"kind": "youtube_duration", "video_id": "dQw4w9WgXcQ", "duration_seconds": 212.125}
{"kind": "local_media_duration", "media_sha256": "64 lowercase hex characters", "duration_seconds": 212.125}
```

The policy keys are exactly `schema_version`, `min_words`, and
`duration_seconds`; policy schema is `1`. `min_words` is the canonical floor
actually applied. With `duration_seconds: null`, it is at least 400. A trusted
short duration may derive a lower floor at 30 words per minute; an invocation
value below that derived floor cannot lower it, while any value above the
derived floor tightens it. A duration-bearing provenance object must repeat the policy
duration exactly. `youtube_duration.video_id` binds to the owning YouTube talk;
`local_media_duration.media_sha256` binds to exact local-media bytes.

The owner of both receipt shapes is
`skills/vault-ingress/scripts/transcript_timing.py`; current timing schema is `2`
and quality-receipt/policy schema remains `1`. Readers hash raw `.txt` bytes,
never decoded/newline-normalized text. Any byte replacement, including CRLF→LF,
invalidates both receipts.

Missing, malformed, owner-mismatched, text-incomplete, over-bound, or hash-stale
timing leaves the plain transcript
readable but makes `timed_transcript` evidence unavailable. Never copy
timestamps from a stale timing receipt or silently downgrade a pattern whose
semantics require timing. Writers do not emit empty timing receipts: a fresh or
forced semantic bundle with no usable timing removes the old sidecar and keeps
`timed_path: null`.

Timing schema v1 and minimal sidecars are archival only. Their missing owner
artifact and duration bounds cannot be inferred safely, so they cannot supply
timing or promote transcript provenance. There is no automatic in-place
migration. Re-fetch/re-transcribe from the proved owner source, or re-import the
original VTT file, to regenerate schema v2. Missing timing remains optional for
ordinary transcript evidence; the independent schema-v1 quality receipt stays
valid when its exact transcript bytes and owner context remain current.

Quality availability is independent. A successful fetch or existing-artifact
validation returns `quality_path` for a current receipt even when `timed_path`
is null. Missing legacy quality is unverified and must be revalidated before v5
scoring; malformed, hash-stale, wrong-owner, wrong-media, or duration-drifted
quality fails closed. Worker-returned duration or talk analysis metadata is
never quality authority. A stored policy is revalidated against its owner;
tightening a caller's `--min-words` can reject existing text but cannot authorize
replacement. Bundle writers stage transcript, timing deletion/replacement, and
quality together. A caught failure rolls every attempted path back to its exact
prior bytes.

For an already-valid transcript, caption timing enrichment is deliberately
non-destructive. Pass the owner's known provenance to `fetch-transcript.py` via
`--existing-source`. Only a known `youtube_auto` transcript may acquire a new
caption timing receipt, and only when the fetched caption text differs from the
existing UTF-8 text by Unicode whitespace alone. The script then writes only
the hash-bound timing sidecar and preserves the transcript bytes exactly.
Manual, Whisper, unknown-provenance, or text-mismatched transcripts remain
untimed; they are never relabeled or overwritten by the enrichment path. The
talk's recorded `transcript_source` remains canonical even when a sidecar is
valid; timing receipts can confirm matching ownership but cannot rewrite it.

Fresh provider text may still be valid when optional segment timing is not. The
fetcher prevalidates timing and, on malformed segments, transcript-text
mismatch, or a source-bound violation, writes the semantic transcript and
quality receipt while removing stale timing in the same transaction. Direct
`write_timing_receipt` calls remain strict and reject those payloads.

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
