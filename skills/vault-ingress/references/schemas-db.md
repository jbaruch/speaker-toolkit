# Vault DB & Subagent Schemas

## Tracking Database Schema

The tracking database (`tracking-database.json`) is the single source of truth.
Canonical path: `~/.claude/rhetoric-knowledge-vault/tracking-database.json`.

**Owner:** vault-ingress owns the artifact shape, every independent record
shape, and all migrations. vault-clarification may write current config,
confirmed-intent, and improvement-goal records. presentation-creator may write
current QR records. vault-profile and the remaining presentation consumers are
read-only. Non-owner readers accept every readable database generation during
rollout — legacy 0, pre-`markdown_decks` 1, and current 2. They never rewrite
legacy state. An unsupported future database or record version is no usable
prior state.

The independently versioned records are the database root, `config`, each
`talks[]`, `pptx_catalog[]`, `qr_codes[]`, `resources[]`, `thumbnails[]`,
`confirmed_intents[]`, `improvement_goals[]`, and
`talks[].source_rejections[]`. Queue claims, source identities, adherence
baselines, and evidence ledgers retain their existing domain schema fields.
Objects embedded inside a versioned record are part of that containing record
unless this reference declares a separate schema.

Current constants live in
`skills/vault-ingress/scripts/tracking_database.py`. Database schema 0 is the
implicit unversioned corpus. Within that root, a missing talk version is the
historical talk schema v1, not a request to synthesize v5 evidence; missing
config, PPTX, QR, resource, thumbnail, confirmed-intent, source-rejection, and
goal versions likewise map only to their validated historical v1 shapes. Config
v2 adds the owner-controlled `pptx_directory_exclusions` discovery boundary.
Run the owner migration in vault-ingress Step 1.
Dry-run emits the exact input SHA-256. Apply requires that digest, refuses active
queue claims, stores the complete original bytes under `.backups/`, and replaces
the verified generation atomically. Backup directory and file opens do not
follow symbolic links. The target input comparison remains exact across bytes
and every `FileGeneration` field, including `mtime_ns` and `ctime_ns`, after
staging and immediately before replacement. The unique staged candidate keeps
its original descriptor/name device and inode, regular-file type, single link,
size, exact bytes, and SHA-256 throughout verification. Staged `mtime_ns` and
`ctime_ns` may rebaseline after fsync only when the descriptor view and name view
are each stable across one byte-read window within the writer-owned bounded
attempts. Exhaustion and every hard staged mismatch raise
`StagedCandidateConflictError` carrying the failed invariant. The class is
defined in `skills/vault-ingress/scripts/tracking_database_io.py`.

### `pptx_catalog` v1 -> v2 -> v3

Writer: the `record_pptx` mutation in
`skills/vault-ingress/scripts/mutate-tracking-database.py`. Readers accept v1,
v2, and v3.

- v1 records a bare `visual_extracted` boolean and nothing about which extractor
  produced it, so a stored `true` may refer to extractor schema v0, v1, v2, v3,
  or current v4. A v1 record with a `visual_evidence` key is rejected as an
  unknown field.
- v2 requires `visual_evidence`: either `null` for a deck no extraction has been
  attempted on, or a receipt binding `outcome`, `extractor_schema_version`,
  `pipeline_version`, the exact `source_fingerprint` of the PPTX bytes, and the
  `artifact` identity/digest the run produced.
- `artifact` is required when `outcome` is `succeeded` and must be null when it
  is `failed`. A success naming no artifact cannot be proven to still exist,
  which is the ambiguity this schema removes.
- v3 requires `identity_assessment`: `null` on an unmatched record, and on a
  matched one the assessment from
  `skills/vault-ingress/scripts/pptx_talk_identity.py` that proves the deck
  belongs to the talk the record names. v2 bound a visual claim to the bytes it
  came from but said nothing about whose deck those bytes were, so a deck could
  carry a perfectly-attested extraction receipt for the wrong talk.
- One predicate decides whether an assessment authorizes a binding —
  `binding_refusal` in `skills/vault-ingress/scripts/pptx_talk_identity.py`.
  The owner writer raises on it so an unproven binding is never persisted, and
  preflight reports it so a binding persisted before this contract existed
  cannot pass as proven. Verdicts, artifact roles, and reason
  codes are the assessor's closed taxonomies, in
  `skills/vault-ingress/scripts/pptx_talk_identity.py` top-of-file constants.
- A matched assessment carries a non-empty `candidates` table, and each entry's
  `signals` map is the evidence its `agreeing` / `conflicting` arrays summarize.
  The gate recomputes those arrays from the map rather than trusting them, so a
  candidate cannot assert a standing its own readings do not support. Only
  selecting signals reach `agreeing` — the example's agreeing `delivery_year`
  and `filename_similarity` report without electing, which is why they appear in
  `signals` and not in `agreeing`.
- v2 of the assessment adds `source_identity`: the deck generation the verdict
  was reached against, in the same `{algorithm, digest, size_bytes}` shape as
  `visual_evidence.source_fingerprint`. v1 pinned an assessment to `pptx_path`
  alone, so replacing the file at that path left the `matched` verdict standing
  and the new deck's contents became that talk's evidence. A v1 assessment
  cannot be upgraded — nothing recorded which bytes it read — so it refuses as
  `identity_assessment_schema_unsupported` and reads as unproven.
- `binding_refusal` takes the caller's own observation as a required argument,
  and the two callers supply different things. `preflight-vault.py` digests the
  live deck, so a deck swapped at the same path is caught. The writer never
  touches the vault, so it supplies the record's own
  `visual_evidence.source_fingerprint` when the record has one and `None` when
  it does not — see `_record_source_fingerprint` and the
  `_require_bound_identity_assessment` docstring in
  `skills/vault-ingress/scripts/mutate-tracking-database.py` for which case
  applies. `None` never means "accepted": the assessment must still carry a
  valid `source_identity`, which is what refuses every v1 assessment. A caller
  that COULD look must not pass `None` to skip the comparison, so preflight
  reports an unreadable deck as its own blocking finding
  (`pptx_talk_binding_source_unobservable`) instead.
- A `source_identity` is held to the same contract as
  `visual_evidence.source_fingerprint`: algorithm `sha256`, a 64-character
  lowercase hex digest, and a positive integer `size_bytes`. The two are
  compared to each other, so a looser reading would let an assessment claim a
  generation the database itself would refuse.
- Readers validate v3 shape only — that the field is null exactly when
  `talk_filename` is null, and an object otherwise. The binding's semantics are
  the writer's gate, matching how `visual_evidence` is handled.
- The receipt's shape is fatal at the writer and at the classifier, never at
  the database assessment. A malformed receipt is per-record evidence trouble:
  `record_pptx` refuses to persist it and the classifier refuses to trust it,
  but the database stays usable, so preflight reports one warning instead of
  refusing the whole vault.
- `visual_extracted` mirrors whether `visual_evidence` records a success, so
  schema-v1 readers keep resolving one boolean.
- Migration stamps an unversioned record at **v1**, not the current constant: a
  legacy record has no binding and cannot satisfy the v2 shape. Migration never
  invents a generation for it.
- `artifact.path` is vault-root-relative; `pptx_path` is relative to
  `config.pptx_source_dir`.
- Selection is derived from this record, never stored in it. The classes, the
  regeneration predicate, and the live observations a caller must supply are
  owned by `classify_pptx_visual_evidence` in
  `skills/vault-ingress/scripts/tracking_database.py` — see the constants above
  that function and its docstring. Running the selection is
  [bootstrap-and-preflight.md](bootstrap-and-preflight.md)'s Step; this
  reference defines the persisted shape only.

### `qr_codes` v1 -> v2

Writer: `skills/presentation-creator/scripts/generate-qr.py`. Readers dual-accept
v1 and v2 for the rollout window.

- v1 records `qr_png_rel_path` alone and carries no `artifacts` key. A v1 record
  with an `artifacts` key is rejected as an unknown field.
- v2 requires a non-empty `artifacts` array — one entry per generated PNG, so a
  multi-colour deck run records every variant rather than only the first.
- `path` is the exact path written, never a default filename. `path_root`
  states what `path` is relative to: `deck_dir`, `cwd`, or `absolute`. A reader
  never infers the root.
- `sha256` is the artifact's digest, so catalog validation distinguishes the
  intended PNG from a stale replacement. `bg_hex` names the colour variant, or
  is null for a single-variant run.
- `qr_png_rel_path` mirrors `artifacts[0].path` so schema-v1 readers keep
  resolving one artifact.
- `target_url` is the canonical redirect target in every mode, including
  MCP-preresolved. The short URL never stands in for it.
- Migration stamps an unversioned record at **v1**, not the current constant: a
  legacy record has no `artifacts` and cannot satisfy the v2 shape. Only the QR
  writer produces v2 records, and it writes them complete.

A schema-v1 database with config v2 is an idempotent no-op. A schema-v1 database
with config v1 receives only the config-v2 migration; the root generation and
every other record remain unchanged. Before migration, queue `inspect` may read
schema 0 and queue `recover` may close an active schema-0 lease in place.
Recovery changes only queue lease/status state and never stamps database or talk
schema fields; the established queue transition may advance a recovered claim
receipt from v1 to v2 while adding its release fields.

The owner migration is a preservation migration. Its only allowed semantic
changes are advancing the root to schema v2, adding the validated historical
version to an
unversioned owner record, creating absent owned arrays as empty arrays, and
upgrading config v1 to v2. A missing exclusion list receives the canonical
defaults; a valid owner-supplied list is preserved exactly. It
preserves every other JSON value and missing-vs-present distinction, including
legacy-v1 `pattern_observations` objects, arrays, or nulls and every historical
citation/source-inspection field. Explicit version 0 sentinels, future owner
versions, ambiguous or malformed historical records, and active claims fail
before backup or write. An exact current database is a byte-and-inode-preserving
no-op.

| Independent record | Current schema |
|---|---:|
| database root | 2 (schema 1, the generation before `markdown_decks`, remains readable) |
| config | 2 (schema 1 remains readable owner-migration input) |
| talk | 7 (schemas 1-6 remain readable historical state; v5 and v6 restamp) |
| PPTX catalog | 3 (schemas 1 and 2 remain readable legacy state) |
| QR code | 2 (schema 1 remains readable legacy state) |
| resource summary | 1 |
| thumbnail | 1 |
| confirmed intent | 1 |
| source rejection | 1 |
| source title equivalence | 2 (own top-level collection; v1 nested entries are migrated) |
| improvement goal | 2 (schema 1 remains readable historical state) |

| Component | Access | Contract |
|---|---|---|
| vault-ingress migration | owner read/write | Accept root schema 0/1/2 and config schema 1/2; migrate to root v2/config v2; never downgrade future state |
| vault-ingress queue inspection/recovery | owner compatibility transition | Inspect schema 0/1/2; recover active leases in schema 0/1/2; never stamp artifact or talk schema versions |
| vault-ingress queue normalization/claim, persistence, shownotes apply, source repair | current read/write | Require database schema 2, config schema 2, and supported explicit owner-record versions; targeted writers emit their current record generation and never migrate the root implicitly |
| vault-ingress preflight, source audit, analysis rendering, shownotes dry-run | dual reader | Parse schemas 0, 1, and 2; gate through existing finding/error channels; never rewrite |
| vault-clarification | current read/write | Route schema migration to vault-ingress; preserve config v2 and stamp confirmed intent v1/improvement goal v2 |
| presentation-creator QR writer | dual reader/current writer | Read schemas 0, 1, and 2; require schema 2 before URL creation or QR metadata persistence; stamp QR v2 |
| presentation-creator publishing/post-event | authorized current writer | Require schema 2 before tracking writes; stamp resource v1 and preserve talk v7 |
| illustrations thumbnail workflow | authorized current writer | Require schema 2 before tracking writes; stamp thumbnail v1 and preserve talk v7 |
| vault-profile | dual reader | Parse schemas 0, 1, and 2; treat unsupported generations as unavailable; never migrate |

Current database schema 2 with config schema 2 requires all eight top-level
state fields shown below. `markdown_decks` is the ninth key and is optional:
absent means no talk has a registered markdown deck, which is what every
database written before root v2 says.
Missing legacy arrays become empty during owner migration. Current writers do
not create them opportunistically. A schema-v1 improvement goal remains valid
historical state; migration never fabricates the schema-v2 baseline provenance
needed for current pattern-goal verification. Talks v1-v5 remain readable under
the current root and are promoted only when the talk-domain writer legitimately
persists that exact talk.

`config.vault_storage_path` is a root assertion, not a redirect. When present
and non-null it must be a native absolute locator lexically equal to the parent
of `tracking-database.json`; absent/null uses that database parent. Readers do
not expand `~`, rebase relative values, translate foreign path flavors, resolve
symlinks to establish equivalence, or silently repair a mismatch. Empty/blank,
drive-relative forms such as `C:vault`, current-drive-rooted forms such as
`\vault`, dot-segment roots, device namespaces, and every other non-native or
non-absolute value fail closed. Repair an invalid stored assertion with the
expectation-bound `set_config` dry-run/apply/re-read/preflight sequence in
[source-identity-preflight.md](source-identity-preflight.md#repair-a-stored-root-assertion).

The exclusion value in the structural example below is one illustrative valid
customization, not the owner default. See the
[config field semantics](../../vault-profile/references/schemas-config.md#pptx-directory-exclusions).

```json
{
  "schema_version": 2,
  "config": {
    "schema_version": 2,
    "vault_root": "~/.claude/rhetoric-knowledge-vault",
    "vault_storage_path": "/native/absolute/vault/root (optional; must match the tracking-database parent; null/absent uses that parent)",
    "pptx_source_dir": "/native/absolute/path/to/Presentations (optional; null/absent falls back to the vault root)",
    "python_path": "/path/to/python3",
    "template_skip_patterns": ["template"],
    "pptx_directory_exclusions": ["example-tool-cache"],
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
      "schema_version": 1,
      "source_type": "video|slides", "url": "known-bad upstream URL",
      "reason": "non_delivery_clip|wrong_delivery|unrelated_recording",
      "evidence": "how the rejection was verified",
      "verified_at": "timezone-aware ISO-8601 timestamp"
    }],
    "pptx_path": "Conference/Year/Talk Name.pptx  (optional — highest quality slide source when available)",
    "schema_version": 7,
    "transcript_source": "youtube_auto|whisper|manual|none  (how the transcript was obtained; MAY BE ABSENT — see below)",
    "transcript_path": "transcripts/{id}.txt  (optional vault-relative path; required for non-YouTube transcript evidence)",
    "slide_source": "pptx|pdf|both|video_extracted|markdown|none  (set in Step 2 per slide source hierarchy)",
    "slides_local_path": "slides/<artifact>.pdf  (optional explicit local PDF; legacy readers also accept slides_pdf_path/pdf_path)",
    "pptx_visual_status": "pending|extracted|no_pptx",
    "status": "pending|needs-reprocessing|reprocessing-inflight|processed|processed_partial|skipped_no_sources|skipped_download_failed|skipped_duplicate",
    "reprocess_reason": "machine-readable reason for needs-reprocessing, or null (owner-set values: DELIBERATE_REPROCESS_REASONS in queue_claim_contract.py)",
    "reprocess_generation": 1,
    "_queue_claim": {
      "schema_version": 5,
      "run_id": "reparse-2026-07",
      "batch_id": "25",
      "claimed_at": "2026-07-31T18:00:00+00:00",
      "previous_status": "needs-reprocessing",
      "reprocess_generation": 1,
      "required_return_schema_version": 6,
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
  "_comment_schema_version": "Database root schema v2 is owner-migrated by vault-ingress; root v1 is the generation before the top-level `markdown_decks` collection, and migration moves a v0 or v1 database to v2 without touching any record it already carries. A missing talk record version is the historical implicit-v1 lineage. v2 makes transcript_source optional. Two incompatible v3 lineages were emitted; v4 is their source-located union and remains archival with evidence ledger v1. V5 adds applicability assessments, exhaustive outcomes, opportunity-coverage identity, and evidence ledger v2. V6 adds `pattern_score_basis` and a possibly-fractional `pattern_score` at the weighted scoring generation; migration restamps a v5 record to v6 without rescoring it, because recomputing a score under arithmetic its worker never used would restate what the worker meant. V7 was introduced for the owner-reviewed title-equivalence ledger, which now lives in the top-level `source_title_equivalences` collection at record v2, so v7 adds no field a v6 record lacks; migration restamps a v5 or v6 record to v7 untouched and lifts a nested v1 ledger out of the talk into that collection. Root migration preserves all historical evidence and never synthesizes v5 outcomes.",
  "_comment_absent_transcript_source": "Absent transcript_source: the key may be MISSING on a talk, and missing is meaningful — it means provenance is unknown, not that no transcript exists (that is the explicit value `none`). It arises on one path: fetch-transcript.py returning method `existing`, where a valid transcript was already on disk and no fetch ran, so nothing was learned about where it came from. Writers MUST NOT backfill a guess; `manual` in particular asserts a human produced it. Readers gauging transcript reliability MUST treat absent as unknown and MUST NOT default it to any value.",
  "pptx_catalog": [{
    "schema_version": 3,
    "pptx_path": "Conference/Year/Talk Name.pptx",
    "talk_filename": "2024-04-10-talk-slug.md or null",
    "matched": true,
    "slide_count": 60,
    "visual_extracted": true,
    "visual_evidence": {
      "outcome": "succeeded",
      "extractor_schema_version": 4,
      "pipeline_version": "1.5.0",
      "source_fingerprint": {
        "algorithm": "sha256",
        "digest": "64 lowercase hex characters",
        "size_bytes": 123456
      },
      "artifact": {
        "path": "vault-root-relative extraction artifact path",
        "sha256": "64 lowercase hex characters"
      }
    },
    "identity_assessment": {
      "schema_version": 2,
      "pptx_path": "Conference/Year/Talk Name.pptx",
      "verdict": "matched",
      "artifact_role": "delivery",
      "selected_talk_filename": "2024-04-10-talk-slug.md",
      "reason_codes": ["identity_matched"],
      "source_identity": {
        "algorithm": "sha256",
        "digest": "3b1f8c2d4e6a90b7c5d3e1f2a4b6c8d0e2f4a6b8c0d2e4f6a8b0c2d4e6f80a1b",
        "size_bytes": 4096
      },
      "candidates": [
        {
          "talk_filename": "2024-04-10-talk-slug.md",
          "signals": {
            "title": "agree",
            "venue": "agree",
            "delivery_year": "agree",
            "hashtag": "unknown",
            "published_pdf": "unknown",
            "filename_similarity": "agree"
          },
          "agreeing": ["title", "venue"],
          "conflicting": []
        }
      ]
    }
  }],
  "_comment_pptx_catalog_failed": {
    "schema_version": 3,
    "identity_assessment": null,
    "pptx_path": "Conference/Year/Broken.pptx",
    "talk_filename": null,
    "matched": false,
    "slide_count": 0,
    "visual_extracted": false,
    "visual_evidence": {
      "outcome": "failed",
      "extractor_schema_version": 4,
      "pipeline_version": "1.5.0",
      "source_fingerprint": {
        "algorithm": "sha256",
        "digest": "64 lowercase hex characters",
        "size_bytes": 123456
      },
      "artifact": null
    }
  },
  "qr_codes": [{
    "schema_version": 2,
    "talk_slug": "arc-of-ai",
    "target_url": "canonical shownotes URL — the short link's redirect target",
    "shortener": "bitly|rebrandly|none|mcp_preresolved",
    "short_path": "shortener's back-half/slashtag; always equals talk_slug, null for none",
    "short_url": "shortened URL, equal to target_url when shortener=none",
    "shortener_link_id": "API-side ID needed for updates; null for none",
    "qr_png_rel_path": "mirrors artifacts[0].path for schema-v1 readers",
    "artifacts": [{
      "path": "arc-of-ai-qr-ffffff.png",
      "path_root": "deck_dir|cwd|absolute",
      "sha256": "64 lowercase hex characters",
      "bg_hex": "ffffff, or null for a single-variant run"
    }],
    "created_at": "2026-04-15",
    "updated_at": "2026-04-15"
  }],
  "resources": [{
    "schema_version": 1,
    "talk_slug": "arc-of-ai",
    "item_count": 12,
    "category_breakdown": {"urls": 7, "repos": 3, "books_papers": 2}
  }],
  "thumbnails": [{
    "schema_version": 1,
    "talk_slug": "arc-of-ai",
    "youtube_url": "https://youtube.com/watch?v=dQw4w9WgXcQ",
    "source_slide_num": 15,
    "speaker_photo_used": "photos/speaker-headshot.png",
    "thumbnail_path": "illustrations/thumbnail.png",
    "shownotes_thumbnail_path": "assets/images/thumbnails/arc-of-ai-thumbnail.png",
    "dimensions": "1280x720",
    "file_size_kb": 185,
    "created_at": "2026-04-20",
    "approved": true
  }],
  "confirmed_intents": [{
    "schema_version": 1,
    "pattern": "delayed_self_introduction",
    "intent": "deliberate",
    "rule": "Use two-phase introduction",
    "note": "Speaker-confirmed intent"
  }],
  "improvement_goals": []
}
```

## Owner Read and Mutation Contract

Agent workflows never open or rewrite the tracking database directly. Read it
through the owner command:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/read-tracking-database.py" \
  "{vault_root}/tracking-database.json"
```

The command accepts only a no-follow regular file and strictly decodes one UTF-8
JSON object. Duplicate keys at any depth, non-finite numbers, finite numbers that
cannot round-trip through the toolkit without changing mathematical value,
nesting deeper than 200 JSON containers, unpaired UTF-16 surrogate escapes,
invalid JSON, and non-object roots fail closed. After decoding, owner schema
assessment is the first semantic operation: an unsupported root, record,
queue-claim, or adherence-baseline generation returns no database payload and is
never interpreted with an older identity or nested shape. Success returns report schema v1 with
`database_path`, the exact-byte `sha256`, and `database`; failure exits `2` with
`ok: false` and no database value. The host Python may run only this stdlib-only
bootstrap read until `config.python_path` is discovered or supplied by the user.
Immediately repeat the read against the same canonical path with that configured
interpreter and require the same SHA-256; restart if the generation changed. Use
the configured interpreter for initialization, migration, queue recovery, typed
mutation, and every later toolkit command.

Agent-owned config and catalog changes use a typed plan:

```json
{
  "schema_version": 1,
  "mutations": [{
    "kind": "set_config",
    "path": ["shownotes", "enabled"],
    "expect": {"$missing": true},
    "value": true
  }]
}
```

Delete a config field with `delete: true`; never pass the missing marker as a
`value`:

```json
{
  "schema_version": 1,
  "mutations": [{
    "kind": "set_config",
    "path": ["talks_source_dir"],
    "expect": "/prior/path",
    "delete": true
  }]
}
```

Every plan is strict JSON with exactly `schema_version` and a non-empty
`mutations` array. Every expectation is either the exact decoded value/record
seen by the owner reader or the exact missing marker `{"$missing": true}`. JSON
`null` is a present value and is never interchangeable with that marker.
The exact missing marker is reserved and invalid as a `set_config` value. A
legacy writer may already have persisted that marker literally. A deletion with
the missing-marker expectation is idempotent across both recoverable states: an
absent field stays unchanged, while the exact present marker is removed. Any
other present value fails the precondition. A recovery change receipt adds
`before_exists: true` and `after_exists: false` to distinguish the literal old
marker from the absent `after` marker. Run the usual dry-run, hash-bound apply,
and owner re-read sequence.
The plan decoder applies the same finite-number round-trip, 200-container depth,
and Unicode-scalar gates as the database decoder, so a reviewed value cannot
silently change or fail later during rendering.
Equality is recursive JSON equality: object key order is irrelevant, array order
is significant, and booleans, integers, and decimals are distinct types. Thus
`true`, `1`, and `1.0` never satisfy one another, and `{"$missing": 1}` is an
ordinary object rather than the missing marker. Schema versions use the same
exact-type rule. The supported mutation kinds are:

| Kind | Typed purpose |
|---|---|
| `initialize_database` | Sole mutation for a missing database; carries initial `config` |
| `set_config` | Set or delete one nested config path against its exact prior value |
| `record_pptx` | Replace/add one complete schema-v3 PPTX catalog record — generation binding included, plus the identity assessment proving the deck belongs to the talk it names — and, when matched, bind the talk's expected `pptx_path` |
| `upsert_confirmed_intent` | Replace/add one complete schema-v1 record identified by `pattern` |
| `upsert_improvement_goal` | Replace/add one complete record identified by `id` |
| `patch_improvement_goal_verification` | Set only verification fields, with `expect` covering exactly the same fields |
| `retire_improvement_goal` | Expect one complete current goal record and change only its `status` to `retired`, preserving legacy fields |
| `upsert_resource` | Replace/add one complete schema-v1 record identified by `talk_slug` |
| `upsert_thumbnail` | Replace/add one complete schema-v1 record identified by `talk_slug` |
| `apply_reviewed_metadata` | Install one human-reviewed shownotes catalog-conflict decision on one exact talk filename, over a closed identity field set, with `expect` covering exactly the same fields |
| `record_source_title_equivalence` | Append one owner-reviewed provider-title equivalence to one exact talk filename; append-only and refuses a duplicate |
| `record_markdown_deck` | Register (or re-point) the markdown file one exact talk's deck was authored in, with `expect` naming the currently registered `deck_source_path` or the missing marker; upsert, one deck per talk |
| `update_talk_publishing` | Set supported publishing fields on one exact talk filename, with `expect` covering exactly the same fields |
| `update_talk_clarification` | Set complete object/array `blind_spot_observations` or `humor_postmortem` values on one exact talk, with matching field expectations |

`source_title_equivalences` is a top-level collection, not a talk field:

```json
"source_title_equivalences": [{
  "schema_version": 2,
  "talk_filename": "playlist-QS-_4k7o7A4.md",
  "video_id": "provider video the equivalence covers",
  "catalog_title": "the exact reviewed catalog title",
  "provider_title": "the exact reviewed provider title",
  "reason": "cross_language_title|provider_retitled",
  "evidence": "how the equivalence was reviewed",
  "verified_at": "timezone-aware ISO-8601 timestamp"
}]
```

It sits outside the talk record because a talk's `schema_version` tracks its
analysis generation, which a legacy record cannot advance without fabricating
analysis. Binding an owner judgment to that generation made the ledger
unreachable for the records that needed it. The collection is optional: absent
means no equivalences.

The ledger records that an owner read one provider title and
accepted it as naming the cataloged talk. The title comparator is deterministic
and cannot cross languages or follow a provider rename, and the only alternative
was rewriting the catalog title to whatever the provider published. Its closed
reason set and matching contract live in
`skills/vault-ingress/scripts/tracking_database.py::validate_source_title_equivalence`
and `source_identity_matching.py::title_equivalence_recorded`. An equivalence
covers one video and one exact title PAIR, so either side changing re-gates
rather than inheriting the approval — a later provider rename, and a catalog
title edited after the review. Consulted only after the deterministic comparison
fails; when it applies, the check passes silently and the record is the audit
trail.

`markdown_decks` is a top-level collection for the same reason, and it is the
newer half of the same lesson:

```json
"markdown_decks": [{
  "schema_version": 1,
  "talk_filename": "spring-rag-jcon.md",
  "deck_source_path": "/repos/spring-rag/slides.md"
}]
```

It names the markdown file a talk's deck was authored in — Slidev, presenterm,
Marp, reveal-md. It is kept because registering a render destroys the only other
trace: the repair that binds `slides/<talk>.pdf` moves `slide_source` from
`"markdown"` to `"pdf"`, correctly, since the talk now has readable slides, and
after that nothing says the deck was ever markdown. The next render, after the
deck gained three slides, would begin by hunting for the file.

`deck_source_path` is a native absolute path in the ordinary case — these decks
live one git repo per talk, so no configured directory locates them the way
`config.pptx_source_dir` locates a deck library — or a vault-root-relative one
like `pptx_path`. **A relative value is resolved by the caller against the vault
root before it reaches a renderer**, which resolves a relative CLI path from its
own working directory and would otherwise report a missing deck for a perfectly
good locator. Its shape goes through `classify_artifact_locator`
(`skills/vault-ingress/scripts/artifact_locator.py`), the same lexical contract
every other persisted artifact path uses, plus a markdown-suffix check; the
accepted and refused spellings are
`skills/vault-ingress/scripts/tracking_database.py::validate_markdown_deck`.

The collection is the root v2 shape, so it cannot ride an older root: a database
at root 0 or 1 carrying a `markdown_decks` key is refused, naming the migration
that stamps the root before the collection is usable. Otherwise the root version
would stop describing the bytes, which is what the generation exists to record.

Existence is never checked. The deck's repo need not be on this machine, so an
absent file is the renderer's loud failure at render time rather than a silent
reason to refuse the whole database. The collection is optional — absent means
no registered deck, which is the correct reading of every database written
before it existed — and no migration owns it: a deck is registered by an owner
who knows where the file is, never inferred.

`apply_reviewed_metadata` exists because `scan-shownotes.py --apply` refuses
review-required entries by design: an approved catalog correction otherwise had
no owner writer at all. The same writer carries an owner-reviewed delivery-date
repair, so a cataloged date the source evidence disproves has a path that is not
a hand edit. It is also the one talk writer that accepts any readable talk
generation rather than the current one: a catalog-identity repair reads no
analysis field, and a legacy record cannot be migrated forward to earn one — see
`_require_readable_talk_record` in
`skills/vault-ingress/scripts/mutate-tracking-database.py`. It stays narrow — the writable field set, the
metadata-only versus analysis-invalidating classification, and the reprocessing
transition it demands are named at the top of
`skills/vault-ingress/scripts/mutate-tracking-database.py`. Deterministic scan
updates and human-approved conflict decisions stay separate paths; source lanes
stay with `apply-source-repairs.py`.

The command owns each operation's closed fields and record validation; do not
reimplement those allowlists in skill prose. PPTX catalog records require exact
integer `schema_version: 2`, since only v2 carries the visual-evidence
generation binding; resource, thumbnail, and confirmed-intent records require
exact integer `schema_version: 1`. A boolean or future version is
not equivalent. Complete resource category counts must sum to `item_count`, and
publishing scalar/identifier types are checked before patching. Run the plan without `--apply`,
review its `changes`, then bind apply to that report's exact input hash:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/mutate-tracking-database.py" \
  "{vault_root}/tracking-database.json" mutation-plan.json

"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/mutate-tracking-database.py" \
  "{vault_root}/tracking-database.json" mutation-plan.json \
  --apply --expected-sha256 <input-sha256-from-dry-run>
```

Initialization uses a sole `initialize_database` mutation, stamps database
schema version 2 and config schema version 2, supplies the canonical
`pptx_directory_exclusions` when the plan omits that field, defaults to dry-run,
and applies with the literal
`--expected-sha256 missing`. All other applies
require the dry-run SHA. The complete plan is one transaction: one failed type,
record, semantic expectation, or file-generation precondition installs nothing.
Re-read after apply rather than assuming the candidate is still current.

All toolkit writers share a persistent sibling lock, stage and `fsync` complete
bytes through a retained no-follow descriptor, and retain the opened parent
directory. Immediately before installation they recheck exact input bytes/file
generation plus the staged descriptor's bytes, hash, generation, type, link count,
and directory-relative visible identity. Replacement/link and cleanup use names
anchored to that same directory descriptor. A substituted staged name fails closed
and is deliberately left untouched rather than unlinking an attacker's path.
Cooperative writers therefore serialize; a same-bytes inode replacement still
conflicts.

Filesystem editors that ignore the sibling lock are outside that exclusion
guarantee. The final pre-install check is defense in depth, and an immediate
post-install inode/byte verification reports an observed last-moment edit as
`installed_verification_failed`. There remains an irreducible last-instruction race:
a non-cooperating process can change the path during the install instruction or
immediately after verification. No userspace lock protocol can make that actor
cooperate, so every caller must re-read the live database after an installed result.
No-op transactions preserve the original bytes and inode. Reports distinguish
`durable`, `unchanged`, `installed_directory_fsync_failed`, and
`installed_verification_failed`. Once the install syscall succeeds, verification,
directory-fsync, staged-name cleanup, directory close, and lock unlock/close
failures return `database_written: true` with warnings; they never masquerade as
a pre-install exception. Inspect the live database and reported output SHA before
any retry. Backup-using writers bind a never-overwritten backup to the exact input
SHA under the same transaction.

## Shownotes Scan/Import Report

Run `scan-shownotes.py` against the canonical tracking database. The scanner
reads `config.shownotes.source` for local sources and resolves
`path_or_url/talks_subdir` inside the configured root. A null or absent
`config.shownotes` may use the legacy absolute `config.talks_source_dir` during
migration. `remote_url`, `none`, and disabled sources return a structured no-op
without reading Markdown or writing the database.

On an exact-filename match, the title-agreement call receives the stored title,
the proposed shownotes title, the stored conference, and the stored date. Its
closed boolean decision contract lives in
`skills/vault-ingress/scripts/source_identity_matching.py::shownotes_titles_agree`.
Agreement is comparison-only and keeps the stored title unchanged. Disagreement
emits `existing_title_conflict` and leaves the entry `review_required`. An exact
title can still fill empty non-title metadata through the existing update
contract.

The command emits report schema v3:

```json
{
  "schema_version": 3,
  "ok": true,
  "mode": "dry-run|apply",
  "operation": "scan|skipped_disabled|skipped_nonlocal",
  "apply_requested": false,
  "database_written": false,
  "input_sha256": "64 lowercase hex characters",
  "output_sha256": "64 lowercase hex characters",
  "durability_state": "dry_run|unchanged|durable|installed_directory_fsync_failed|installed_verification_failed",
  "warnings": [],
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

A `rejected_source_reappeared` issue carries the exact ledger record that
produced the match, so a reviewer decides from the report alone:

```json
{
  "code": "rejected_source_reappeared",
  "field": "video_url",
  "message": "shownotes proposes a known-bad video_url; ...",
  "matched_rejection": {
    "source_type": "video|slides",
    "url": "the stored known-bad URL",
    "provider_id": "parsed provider ID, or null when the URL has none",
    "reason": "non_delivery_clip|wrong_delivery|unrelated_recording",
    "evidence": "how the rejection was verified",
    "verified_at": "timezone-aware ISO-8601 timestamp"
  },
  "match": {
    "method": "exact_url|provider_id",
    "candidate_url": "the URL the shownotes page proposes",
    "candidate_provider_id": "its parsed provider ID, or null"
  }
}
```

Only the matched record appears; unrelated `source_rejections` entries stay
private to the talk. A malformed ledger record never reaches this shape — the
scanner refuses to load a database whose `source_rejections` fail
`tracking_database._validate_source_rejection`.

Dry-run is the default and never writes. `--apply` adds complete new records
with current talk schema and status `pending`, or fills empty fields on an exact
filename match. Established values are not overwritten. Conflicting,
incomplete, and normalized-collision entries stay `review_required` and never
mutate. `mutation_count` counts deterministic `add` and `update` candidates;
`database_written` records whether an atomic replacement occurred. Input and
output SHA-256 values bind the report to exact database generations. An
`installed_directory_fsync_failed` or `installed_verification_failed` result
means the install syscall succeeded; inspect the live database and reported
output hash before retrying.

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

A fresh v6 worker uses the exact empty adherence sentinel and does not author a
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

Every fresh queue claim is schema v6 and carries exactly the
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
| v5 | v5 only | v5 | never current v6 |
| v6 | v6 only | v6 | v6 when canonical evidence/outcomes are fresh |

Claim/return compatibility authorizes replay; it does not grant current scoring
status. Only a v6 return canonicalized from current source artifacts can produce
talk schema v6 with `pattern_scoring_schema_version: 6`, evidence ledger v2,
exhaustive outcomes, `pattern_score_basis`, and
`pattern_scoring_generation_status: "current"`. A v5 return still validates and
still persists, at the flat scoring generation; weighted and flat scores are not
comparable and never share a cohort.
V1–v3 detections retain the explicit empty-citation legacy sentinel. V4 keeps
its source locations and evidence ledger v1 but migration never fabricates v5
applicability assessments, outcomes, or opportunity identity.

`improvement_goals` is the coaching-loop artifact — speaker-chosen focus areas that
a later ingress run verifies. vault-ingress owns the record shape and migrations;
vault-clarification creates and retires current records. Ingress verification writes
only the verification fields. Record schema, lifecycle, and writer/reader contract:
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
  "slide_source": "pptx|pdf|both|video_extracted|markdown|none",
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

The worker matches the active claim contract. Every fresh claim is schema v6
with `required_return_schema_version: 6`, and only that exact claim authorizes a
v6 return. Saved claim schemas v1/v2 authorize only return schemas v1/v2;
schema v3 authorizes only v3; schema v4 authorizes only archival v4; schema v5
authorizes only v5. Recover a live legacy lease and issue a new v6 generation;
never mutate its claim to make a newer return appear compatible.

For newly emitted work, `validate-returns.py` must report the processed talk's
scoring-generation status as `current`; a valid but
`legacy_unbaselineable` result is replay-only and must be repaired.

### Return schema v6 — the weighted aggregate

v6 keeps every v5 semantic and changes one thing: `pattern_score` is weighted by
detection confidence rather than counted flat. It therefore joins every version
set v5 belongs to — snapshot merge, outcome gate, source-located evidence, and
exhaustive outcomes.

| | v5 | v6 |
|---|---|---|
| `pattern_score` | `patterns_detected - antipatterns_detected`, each detection ±1 | weighted sum, `strong` 1.0 / `moderate` 0.5 / `weak` 0.25, rounded to two places |
| `pattern_score_basis` | forbidden | **required** alongside the score |
| exhaustive `pattern_outcomes` | required | required |

Each version is validated against the arithmetic in force when it was written. A
v5 return was produced by a worker counting ±1, so rescoring it under the weight
table would restate what that worker meant rather than validate what it said. A
v5 return carrying `pattern_score_basis` is rejected outright — the field cannot
exist under its contract.

**Writer.** Every fresh claim is schema v6 with
`required_return_schema_version: 6`, so a worker is issued a v6 return.
`PATTERN_SCORING_SCHEMA_VERSION` is 6; `FLAT_PATTERN_SCORING_SCHEMA_VERSION`
names the flat generation, and `scoring_schema_version_for_return` maps a return
to the generation its score belongs to. Weighted and flat scores are not
comparable and never share a cohort.

**Persisted shape.** A canonicalized v6 block carries
`pattern_score_basis` and its `pattern_score` may be fractional. The accepted
field sets are distinct, not v5-plus-an-optional-field: a v5 record carrying a
basis and a v6 record missing one are both malformed. The basis is recomputed
from the persisted detection lanes on the way out of the database as well as on
the way in — a stored basis that agrees with a stored score proves only that
whoever wrote them agreed with themselves.

**Migration.** `_restamp_talk_records` moves a v5 talk record to v6 and leaves
`pattern_scoring_schema_version` alone. It restamps; it never rescores.
Computing a basis from stored detections would recompute a score under
arithmetic its worker never used, which is the reinterpretation validation
refuses on the way in. The record's shape advances, its score does not, and the
cohort selector then excludes it as a generation mismatch and requeues it.
Without the restamp the schema bump alone would leave every stored talk
unmutatable, since the owner writer requires the exact current talk schema.

Weights are part of the scoring schema version, so changing one is a
scoring-generation bump, never a tuning knob.

The basis a v6 return carries has this shape:

```json
{
  "pattern_score": 1.5,
  "pattern_score_basis": {
    "schema_version": 6,
    "weights": {"moderate": 0.5, "strong": 1.0, "weak": 0.25},
    "patterns": {"moderate": 1, "strong": 1, "weak": 0},
    "antipatterns": {"moderate": 0, "strong": 0, "weak": 0},
    "not_evaluable_count": 12
  }
}
```

`weights` is the complete table, not the subset this talk used, so a reader can
recompute the score without consulting the engine. The per-lane counts cover every
confidence level the catalog admits; a level added without a weight fails the
table's own exhaustiveness test rather than silently scoring as zero.

Versions 2–6 share the complete-snapshot merge contract: supplied declared
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
Versions 2–6 require `rhetoric_notes` and `areas_for_improvement` to contain
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
requires that path plus a complete schema-v4 manifest whose top-level crop provenance
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
Native-deck freshness likewise requires a current `native_deck_audit`, binds its
PPTX digest, size, and slide count to the current bounded probe and canonical
inspection, and binds any rendered-page receipt to the current bounded PDF plus
the exact persisted static-slide inspection ranges. Missing, obsolete,
wrong-lane, or artifact-disconnected audits requeue the talk.

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

Historical v1–v3 records may contain `evidence_citations: []`. That is a deliberate
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
  "schema_version": 4,
  "pipeline_version": "0.13.0",
  "source_video_id": "AbCdEfGhI_1",
  "source_video_path": "/vault/slides-rebuild/AbCdEfGhI_1/AbCdEfGhI_1.mp4",
  "source_receipt": {
    "schema_version": 1,
    "probe_schema_version": 1,
    "probe_pipeline_version": "1.0.0",
    "source_sha256": "3b2f...c91a",
    "source_size_bytes": 734003200,
    "duration_seconds": 2998.4,
    "duration_source": "format",
    "container_family": "iso_bmff",
    "stream_count": 2,
    "video_stream_count": 1,
    "audio_stream_count": 1,
    "attached_picture_count": 0,
    "other_stream_count": 0,
    "source_generation": {
      "size": 734003200,
      "mtime_ns": 1767225600000000000,
      "ctime_ns": 1767225600000000000,
      "device": 16777232,
      "inode": 84215045,
      "mode": 33188,
      "flags": 0,
      "file_attributes": null
    }
  },
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
      "path": "/vault/slides-rebuild/AbCdEfGhI_1/AbCdEfGhI_1.slide-region.pdf",
      "artifact_scope": "slide_region",
      "page_count": 85,
      "source_video_id": "AbCdEfGhI_1",
      "source_video_path": "/vault/slides-rebuild/AbCdEfGhI_1/AbCdEfGhI_1.mp4",
      "source_receipt": { "...": "byte-identical to the manifest source_receipt" },
      "crop_method": "manual",
      "crop_verified": true,
      "trusted_for_authored_slide_analysis": true
    },
    {
      "path": "/vault/slides-rebuild/AbCdEfGhI_1/AbCdEfGhI_1.context.pdf",
      "artifact_scope": "full_frame_context",
      "page_count": 85,
      "source_video_id": "AbCdEfGhI_1",
      "source_video_path": "/vault/slides-rebuild/AbCdEfGhI_1/AbCdEfGhI_1.mp4",
      "source_receipt": { "...": "byte-identical to the manifest source_receipt" },
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

- `schema_version` (integer) — the record's **field shape**. Current value: `4`. The
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

Version 4 binds every derivative to the exact source-video content it came from.
`source_receipt` is engine-owned: the extractor captures it from the bounded
`video_evidence` probe (`skills/vault-ingress/scripts/video_evidence.py` —
`build_video_source_receipt`) before sampling frames, re-probes after the last PDF
lands, and fails the run without writing a record when anything drifted. The same
receipt is stamped on the manifest head and byte-identically on every
`artifacts[]` entry, so each derivative's own record names the source bytes it
came from and two derivatives from two different runs cannot be merged under one
manifest. The receipt lives in the record, not in the PDF: a PDF file separated
from the manifest carries only the scope and pipeline version its metadata
already recorded. The receipt is path-neutral and bounded — a digest, duration/container/
stream evidence, the bound file generation, and the probe contract version. Raw
ffprobe output and parser stderr never reach it.

Readers compare the receipt's content fields against a fresh probe of the same
path: `probe_schema_version`, `probe_pipeline_version`, `source_sha256`,
`source_size_bytes`, `duration_seconds`, `duration_source`, `container_family`,
and the four stream counts (the authoritative list is
`VIDEO_SOURCE_RECEIPT_LINEAGE_FIELDS` in `video_evidence.py`). `source_generation`
is deliberately excluded from that comparison: device, inode, and mtime are
host-local and change on a byte-identical vault move, while the digest already
proves the bytes. The generation is what the extractor holds stable inside one
run.

A schema-3 record stays readable as an archival/reprocessing input and is never
upgraded in place — a digest observed today cannot prove which bytes produced
yesterday's pages. Preflight reports it as `video_extraction_source_receipt_missing`,
naming the repair: reacquire the source video and re-extract. A source that reads
but disagrees with the receipt is `video_extraction_source_lineage_mismatch`,
blocking. A dataless or offline placeholder fails the bounded probe outright and
stays unavailable until it is hydrated.

Version 3 separates derived artifacts by provenance and scope. `artifacts[].path` and
`source_video_path` are native absolute, symlink-resolved paths at extraction
time. They must remain within the configured vault storage root, contain no NUL,
raw dot segments, `~`, device/current-drive syntax, foreign absolute flavor, or
dual-flavor `//` form, and name non-symlink descendants. Persisted relative
artifact locators elsewhere in the database use canonical `/` separators and
exclude Win32-trimmed components, alternate-stream syntax, and reserved DOS
device basenames. They are joined as logical root-relative components, never
reinterpreted through the host's alternate separator or namespace rules. Before
a current return is
persisted, every manifest PDF—not only the trusted `slide_region`—must pass the
bounded exact-generation PDF probe and match its recorded page count. A
configured canonical vault symlink is admitted as the trusted root locator and
mapped to its storage target; descendant symlinks remain forbidden.
`artifact_scope` is one of:

- `slide_region` — pages are physically cropped to the selected region. This is trusted
  for authored-slide analysis only when `crop_method` is `manual`, `crop_verified` is
  true, `trusted_for_authored_slide_analysis` is true, and top-level
  `review_required` is false.
- `full_frame_context` — uncropped broadcast frames for room, stage, speaker, or PiP
  analysis. This is never an authored deck and is never a source for slide design,
  authored slide count, or slide-pattern claims.

Ingress validates the manifest as one referential unit before trusting it: schema and
pipeline versions are present; the source receipt is complete and every artifact
carries the same one; source and artifact identities agree; normalized region
geometry agrees with `slide_region_method`, `slide_region_applied`,
`slide_region_detected`, and `slide_region_verified`; retained-frame and artifact page
counts agree with `unique_frame_count`; and artifact scope, crop method, verification,
and trust flags are mutually consistent. `review_required: false` is accepted only for
a verified manual `slide_region`; setting one optimistic flag cannot turn a context PDF
into a deck. Persistence replaces this complete owner-versioned manifest rather than
deep-merging it, so obsolete v1/v2/v3 fields cannot survive inside a schema-v4 record.

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
| Native timing/build structure | Raw timing containers, behavior elements, visibility sets, transitions, media timing, and build-list entries | `native_timing`, `native_timing_summary` |

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
  "schema_version": 4,
  "pipeline_version": "1.5.0",
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
  "archive_recovery": [
    {
      "schema_version": 1,
      "part_name": "ppt/media/image7.png",
      "member_kind": "embedded_media",
      "error_type": "crc_mismatch",
      "status": "recovered_with_placeholder_asset",
      "content_replaced": true,
      "replacement_sha256": "64 lowercase hex characters"
    }
  ],
  "template_layouts": [
    {
      "index": 0,
      "master_index": 0,
      "name": "Title Slide",
      "placeholders": [{"idx": 0, "type": "CENTER_TITLE"}]
    }
  ],
  "per_slide_visual": [
    {
      "slide_number": 1,
      "slide_part_name": "ppt/slides/slide1.xml",
      "background_color_hex": "#5B2C6F",
      "background_type": "solid|pattern|image|gradient|solid_from_layout|solid_from_master|unknown",
      "background_asset_status": "not_applicable|available|corrupt|unavailable",
      "background_part_name": null,
      "background_asset_sha256": null,
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
          "status": "extracted|empty|partial|failed|skipped|unavailable|unsupported|requires_render",
          "provenance": {
            "source": "pptx_shape_text_frame",
            "shape_path": ["Group 1", "Title 2"]
          }
        },
        {
          "channel": "picture_ocr",
          "text": "Recovered label",
          "confidence": "low",
          "result_confidence": 91.25,
          "status": "extracted",
          "attempted": true,
          "engine": "tesseract",
          "engine_version": "5.5.1",
          "reason": null,
          "provenance": {
            "source": "embedded_picture_blobs",
            "shape_paths": [["Picture 3"]]
          },
          "ocr_receipts": [
            {
              "attempted": true,
              "engine": "tesseract",
              "engine_version": "5.5.1",
              "result_status": "text_recovered|low_confidence_text|genuine_empty|failed|unavailable|skipped",
              "result_confidence": 91.25,
              "error": null,
              "part_name": "ppt/media/image3.png",
              "asset_sha256": "64 lowercase hex characters",
              "shape_path": ["Picture 3"],
              "recovered_text": "Recovered label",
              "trustworthy_text": true
            }
          ]
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
        "build_list_present": true,
        "build_list_count": 1,
        "build_entry_counts": {
          "paragraph": 1,
          "diagram": 1,
          "ole_chart": 0,
          "graphic": 0,
          "total": 2
        },
        "has_animation_behaviors": true,
        "has_media_timing": true,
        "has_build_entries": true,
        "provenance": {
          "source": "pptx_package_xml",
          "measurement": "raw_ooxml_element_counts",
          "observed_playback": false,
          "part_name": "ppt/slides/slide1.xml"
        }
      },
      "shapes_summary": [
        {"name": "Title 1", "shape_type": "PLACEHOLDER (14)", "has_text_frame": true, "is_picture": false, "is_graphic_frame": false, "graphic_frame_type": null, "graphic_data_uri": null, "left": 1.0, "top": 0.5, "width": 10.0, "height": 1.0, "shape_path": ["Title 1"], "group_depth": 0, "text_preview": "Talk Title", "font_name": "Bangers", "font_size": 36, "font_color": "#FFFFFF", "bold": true, "italic": false},
        {"name": "Cloud 2", "shape_type": "AUTO_SHAPE (1)", "has_text_frame": true, "is_picture": false, "is_graphic_frame": false, "graphic_frame_type": null, "graphic_data_uri": null, "left": 2.0, "top": 2.0, "width": 3.0, "height": 2.0, "shape_path": ["Cloud 2"], "group_depth": 0, "text_preview": "", "auto_shape_type": "CLOUD_CALLOUT (108)", "fill_color": "#FFFFFF", "line_color": "#000000"},
        {"name": "Picture 3", "shape_type": "PICTURE (13)", "has_text_frame": false, "is_picture": true, "is_graphic_frame": false, "graphic_frame_type": null, "graphic_data_uri": null, "left": 6.0, "top": 2.0, "width": 4.0, "height": 3.0, "shape_path": ["Picture 3"], "group_depth": 0, "picture_asset_status": "available", "picture_part_name": "ppt/media/image3.png", "picture_asset_sha256": "64 lowercase hex characters"}
      ]
    }
  ],
  "native_timing_summary": {
    "slides_with_timing_elements": 12,
    "slides_with_transitions": 40,
    "slides_with_animation_behaviors": 10,
    "slides_with_media_timing": 2,
    "slides_with_build_lists": 1,
    "slides_with_build_entries": 1,
    "timing_element_count": 12,
    "transition_count": 40,
    "set_action_count": 18,
    "visibility_set_action_count": 9,
    "build_list_count": 1,
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
    "build_entry_counts": {
      "paragraph": 1,
      "diagram": 1,
      "ole_chart": 0,
      "graphic": 0,
      "total": 2
    },
    "provenance": {
      "source": "pptx_package_xml",
      "measurement": "raw_ooxml_element_counts",
      "observed_playback": false
    }
  },
  "native_deck_audit": {
    "schema_version": 1,
    "extraction_schema_version": 4,
    "extraction_pipeline_version": "1.5.0",
    "source_pptx_sha256": "64 lowercase hex characters",
    "source_pptx_size_bytes": 123456,
    "slide_count": 60,
    "render_required_slide_numbers": [1],
    "render_required_reasons": {"1": ["smartart"]},
    "extraction_receipt_sha256": "64 lowercase hex characters",
    "rendered_page_inspection": {
      "schema_version": 1,
      "source_pptx_sha256": "64 lowercase hex characters",
      "rendered_pdf_sha256": "64 lowercase hex characters",
      "rendered_pdf_size_bytes": 98765,
      "rendered_page_count": 60,
      "inspected_page_ranges": [[1, 60]],
      "inspected_required_slide_numbers": [1],
      "complete": true,
      "binding_sha256": "64 lowercase hex characters"
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
v1 added the version/fingerprint, v2 added `native_timing` to every slide plus
`native_timing_summary`; v3 added the raw build-list timing lane plus closed
`archive_recovery` and `native_deck_audit` records; and current v4 makes shape,
picture, and background capability/asset bindings required. `pipeline_version`
tracks extraction behavior and
changes when the walk, classification, confidence, OCR, recovery, timing, or
receipt behavior changes; current is `1.5.0`. Pipeline 1.5 applies the shared
bounded PDF ceiling, complete page-tree walk, and repair-diagnostic rejection to
render receipts produced inside the already-contained PPTX extraction worker.

Extractor schema v4 is independent of persisted pattern-evidence schema v2,
return schema v5, queue-claim schema v5, and tracking-database schema v2. Those
downstream generations do not advance here; their current readers bind or
validate the new nested records inside their existing contracts.

These records are transient per-invocation output, not a persisted artifact with
an in-place migration. Regenerate old output with the current extractor. A timing
reader must treat v0/v1 as **timing unknown**, never as all-zero. Schema v2 has
the pre-build timing shape but lacks raw build-list evidence and cannot satisfy
archive-recovery or audit-receipt requirements. Schema v3 lacks the required
capability/asset bindings, so current analysis reruns it too. An unknown future schema version
is no usable prior output. The vault-profile layout reader may read v1/v2/v3/v4
because `template_layouts` is unchanged, but it also
rejects missing/unknown versions and reruns instead of guessing. This is the only
declared cross-pipeline compatibility exception.
`input_fingerprint` hashes the exact source PPTX bytes before any in-memory
media recovery; identical bytes have the same fingerprint regardless of path.

Every slide binds its ordinal to the canonical python-pptx part name
`ppt/slides/slide{slide_number}.xml`; native-timing provenance must name that
same part. Every shape carries explicit `has_text_frame`, `is_picture`, and
`is_graphic_frame` capabilities. Text preview and its five-field font bundle
exist only for a text frame; table dimensions/text/fonts exist only for a table
graphic frame; and picture asset status/part/digest exist only when
`is_picture: true`. Graphic type is derived from and cross-bound to the exact
DrawingML URI when present; a graphic frame with a missing/empty URI is retained
as generic `graphic_frame` unsupported evidence with a null URI. Available
picture and background OCR receipts must exactly match
their part name and digest, while corrupt asset bindings must match the closed
archive-recovery record.

Every public PPTX probe, native-audit recomputation, and extraction is executed
in a separate authenticated worker. The request and response bind the exact
file generation (including platform availability flags), operation, fixed limit
profile, and extractor schema/pipeline. POSIX process groups and Windows Job
Objects provide process-tree cleanup for the trusted worker boundary; on POSIX,
cleanup covers the worker process group plus sampled descendants and is not an
adversarial session-containment claim. Sampled aggregate RSS monitoring requires
exactly `psutil==7.2.2` and is fail-closed, but is not described as a kernel
hard-allocation limit on macOS.
Raw worker diagnostics are discarded after producing a bounded count/hash/
truncation receipt. Source-artifact and operation resource limits are script-owned;
see `skills/vault-ingress/scripts/pptx_evidence.py` — `PPTX_MAX_INPUT_BYTES` and
the top-level `SupervisorLimits` profiles. Exceeding a configured limit fails
closed.

Directory extraction is selected only with `--directory`. Its public result is
the strict schema-v1 completeness envelope below; this generation is independent
of the per-deck extractor schema v4 and pipeline 1.5.0:

```json
{
  "schema_version": 1,
  "kind": "pptx_directory_batch",
  "complete": false,
  "incomplete_reason_codes": ["pptx_batch_file_limit"],
  "results": [],
  "skipped": [{"path": ".", "reason": "pptx_batch_file_limit"}]
}
```

`complete` is true exactly when `incomplete_reason_codes` is empty, and both are
recomputed from the closed `skipped[]` taxonomy. Exit zero admits either complete
or partial output: safe per-deck results remain usable, but only `complete: true`
authorizes full-catalog coverage or an absence conclusion. Whole-root and
protocol failures exit nonzero and add the existing top-level `error`, bound to
one root receipt and no results. Whole-root-only reason codes are invalid as
ordinary partial receipts, and per-deck failures cannot be promoted into the
top-level error. Its `details` object is path-neutral and may contain only one
optional closed `supervisor_reason_code`. Each public `skipped[].path` is either
`.` or one bounded canonical root-relative path; absolute, drive-qualified,
backslash, traversal, empty-component, and control/format-bearing paths are
rejected during decode. A legacy unversioned `results`/`skipped` object has
unknown completeness and must be rerun before a coverage or absence claim.

The owner performs no root stat, type probe, or recursive enumeration: an
authenticated worker with fixed input, output, memory, process, and wall limits
validates and scans the root, then returns a private schema-v2 root-relative
manifest. Its authenticated request carries the validated exact-component
directory-exclusion list; the response echoes that exact ordered list and
carries `complete` and `incomplete_reason_codes`. The owner rejects a response
whose policy differs, fabricates an exclusion receipt, returns evidence below
an excluded component, or nests any skip below another non-root skip, then
independently recomputes completeness from `skipped[]`. For every encountered real directory, symlink and
reparse-point rejection runs before the case-insensitive exact-component
exclusion check. An excluded directory produces one
`pptx_batch_directory_excluded` receipt, consumes no descendant scan budget, and
is not traversed. The excluded dirent is charged to a separate finite policy
enumeration ceiling rather than the eligible-entry ceiling, so excluded
environment/cache directories cannot starve authored siblings. Exhausting
either ceiling emits `pptx_batch_entry_limit`; enumeration remains bounded.

The envelope's `complete` and `incomplete_reason_codes` fields are the sole
consumer authority; never recreate the per-receipt classification. Its closed
taxonomy lives only in
`skills/vault-ingress/scripts/pptx_discovery_contract.py::{PPTX_DIRECTORY_POLICY_SKIP_REASON_CODES,PPTX_DIRECTORY_INCOMPLETE_REASON_CODES}`.
The worker rejects unusable or colliding directory identities and unknown
redirecting Windows reparse tags; supported hydrated Cloud Files leaves remain
eligible. Discovery and extraction share one enclosing deadline, and final
compact-JSON accounting includes its wrapper and newline. Stronger root/leaf
handle binding and handle-relative traversal remain tracked by #176; until then
all recursive filesystem contact is at least confined to the termination-safe
discovery worker rather than occurring in the owner.

`archive_recovery` is empty on a healthy package. A bad-CRC member under
`ppt/media/` is replaced only in an in-memory package with a transparent
placeholder, allowing healthy text and slides to survive while recording the
lost part and exact replacement digest. `corrupt_assets` remains the legacy
three-field projection. Structural members (XML, relationships, content types,
layouts, masters, and presentation topology) are never discarded; their
corruption makes the deck unavailable. The source file is never rewritten.

`native_timing` inventories exact PresentationML element names under each slide's
`<p:timing>` tree. `general` means the exact `<p:anim>` behavior, not a total;
`effect`, `motion`, `rotation`, `scale`, and `color` likewise count only their
specific behavior elements. `visibility_set_action_count` is the subset of
`<p:set>` actions whose attribute name is `visibility` or ends in
`.visibility`. Audio/video time nodes have a separate `media_timing_counts` lane,
and slide transitions are counted separately whether or not a timing tree exists.
The build lane counts only exact `p:bldP`, `p:bldDgm`, `p:bldOleChart`, and
`p:bldGraphic` entries beneath `p:bldLst`, with fixed zero-valued keys and an
explicit `build_list_present` flag. A build entry is raw package structure: it
does not prove reveal order, visible state, execution, or delivered playback,
and it is never merged into visibility-set counts.

All counts are raw OOXML structure. Markup Compatibility `Choice` and `Fallback`
branches are both present in the package and both counted. The provenance field's
`observed_playback: false` is load-bearing: timing-container presence, media timing,
or a motion/build element does not prove execution, concurrency, smoothness,
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
  "shapes+ocr"`). Use only receipt records with `trustworthy_text: true` for
  affirmative cites, transcript cross-checks, language policy on slide text,
  and pattern evidence; lower-confidence recovered text remains available for
  spelling review but is not trustworthy evidence
- OCR channels add `attempted`, configured engine/version, aggregate numeric
  `result_confidence` (finite 0..100 or null), a closed reason, and
  `ocr_receipts[]`. Each per-asset receipt binds the exact package `part_name`,
  asset SHA-256, and shape path to one result. `recovered_text` is capped at
  8,000 characters per receipt. With no readable blob the channel has
  `attempted: false`, `status: "unavailable"`, reason `no_readable_asset`, and
  an empty receipt array. With `--no-ocr`, every readable asset gets an explicit
  `attempted: false` / `result_status: "skipped"` receipt and reason
  `ocr_disabled`. A missing engine records `ocr_engine_unavailable`; processing
  failures record `ocr_failed` or `partial_ocr_results`
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

`native_deck_audit` binds the exact PPTX digest and size, extractor schema and
pipeline, slide count, and every derived render-required slide/reason. Its
optional `rendered_page_inspection` binds an equal-page-count PDF plus the exact
inspected ranges. Hash, byte size, and page count come from one stable copied PDF
generation; persistence snapshots the current canonical PDF again and compares
all three, so a same-size replacement cannot inherit an old receipt. Every
current return that declares, inspects, or cites `native_deck` must carry the
current audit even when it reports zero findings. Native citations—including
applicability citations—need rendered evidence only when their cited slide
numbers overlap the audit's render-required slides; explicit authored visual
summary fields require complete coverage of every render-required slide.
Persistence recomputes the audit in a bounded worker and matches the receipt to
owner-canonical native-deck and static-slide identities.

Current PDF and PPTX supervisor receipts preserve request, result, dependency,
monitor, identity, containment, and resource-limit causes through the mappings
owned by `pdf_evidence.py` and `pptx_evidence.py`. Successful evidence is
unchanged, so this does not advance either extraction schema or pipeline.
Previously persisted ambiguous failure/skip receipts remain readable and must
not be relabeled: their closed details do not prove a narrower historical cause.
Rerun ingress to regenerate them under the current mappings before relying on
remediation advice.

`image_area_ratio` is the **largest** `is_picture: true` shape's area as a
fraction of the slide as emitted by `pptx-extraction.py` and validated by
`pptx_evidence.py`; it is always present. Script-owned normalization can make
an extremely small picture report `0.0`, so that value is not proof that the
slide has no picture. `PPTX_TEXT_BEARING_IMAGE_AREA_RATIO` in
`pptx_evidence.py` is the sole authority for when the reported value adds
`large_picture`; prose and downstream consumers must not reproduce its
predicate.

It measures picture **shapes** only, including an inserted picture placeholder
whose OOXML element is a picture; media poster frames are not picture evidence.
A slide whose image is a *background*
reports `background_type: "image"` and `text_extraction_confidence: "low"`
while `image_area_ratio` stays `0.0` — the background covers the canvas by
definition and has no picture geometry to measure. When its relationship and
blob are valid, OCR appears in a distinct `background_image_ocr` channel; a
missing blob is recorded as `status: "unavailable"`. Either way, rendering is
still required for design judgment. Read the confidence, never the ratio, to
decide whether a slide needs a visual pass.
