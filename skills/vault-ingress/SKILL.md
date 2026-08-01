---
name: vault-ingress
description: >
  Parses presentation talks to catalog rhetoric patterns: opening hooks, humor style,
  pacing, transitions, audience interaction, slide design, and verbal signatures.
  Downloads YouTube transcripts and analyzes slides (from PPTX, Google Drive PDFs, or
  video extraction), examining HOW the speaker presents. Processes talks in parallel
  batches and updates the running rhetoric summary.
  Triggers: "parse my talks", "run the rhetoric analyzer", "analyze my presentation style",
  "how many talks have been processed", "update the rhetoric knowledge base",
  "check rhetoric vault status", "process remaining talks for style patterns".
user_invocable: true
---

# Vault Ingress — Incremental Talk Parser

Process the steps below in order; each step's output (tracking DB state, batch results, per-talk artifacts) feeds the next. Do not skip ahead.

Resolve the absolute path of this loaded `SKILL.md`, then set
`speaker_toolkit_root` to the plugin root two directories above the directory
containing this file. Never derive it from the consumer working directory.
Treat `{speaker_toolkit_root}` as absolute in every toolkit-owned command;
vault and source-artifact paths remain consumer-owned.

Build a rhetoric and style knowledge base by analyzing presentation talks. Each run
processes **unprocessed** talks, extracts rhetoric/style observations, and updates the
running summary. The vault lives at `~/.claude/rhetoric-knowledge-vault/` (may be a
symlink to a custom location). All paths are relative to this **vault root**.

## Key Files & References

| File / Reference | Purpose |
|------------------|---------|
| `tracking-database.json` | Source of truth — talks, status, config, confirmed intents |
| `rhetoric-style-summary.md` | Running rhetoric & style narrative |
| `slide-design-spec.md` | Visual design rules from PDF + PPTX analysis |
| `speaker-profile.json` | Machine-readable bridge to presentation-creator |
| `analyses/{talk_filename}.md` | Per-talk rhetoric analysis (one file per processed talk) |
| `transcripts/{transcript_id}.txt` | Downloaded/cleaned transcripts (`youtube_id` for YouTube talks) |
| `transcripts/{transcript_id}.segments.json` | Hash-bound acquisition source and optional timing for the matching transcript |
| `transcripts/{transcript_id}.quality.json` | Hash-bound exact quality policy and source-owned duration provenance |
| `slides/{id}.pdf` | Slide PDFs (from Google Drive, PPTX export, or video extraction) |
| [references/schemas-db.md](references/schemas-db.md) | DB + subagent schemas; extraction output schemas |
| [references/rhetoric-dimensions.md](references/rhetoric-dimensions.md) | 14 analysis dimensions |
| [references/subagent-instructions.md](references/subagent-instructions.md) | Step 3 per-talk procedure — transcript download, slide acquisition, fallback chains, return-JSON shape |
| [references/video-slide-extraction.md](references/video-slide-extraction.md) | Video-to-slides pipeline — layout heuristics, tuning, limitations |
| [references/source-identity-preflight.md](references/source-identity-preflight.md) | Offline identity, duplicate-source, enum, and artifact integrity contracts |
| [references/source-identity-audit.md](references/source-identity-audit.md) | Networked, read-only capture of live provider identity evidence and review findings |
| [references/catalog-feedback-intake.md](references/catalog-feedback-intake.md) | Five-lane catalog-feedback schema, polarity, recurrence, and review contract |
| [references/pattern-catalog-contract.md](references/pattern-catalog-contract.md) | Read-only catalog graph, polarity, source-gate, and semantic-debt contract |
| [references/processing-rules.md](references/processing-rules.md) | Language policy, pattern migration logic, structured field rules |
| [references/known-issues.md](references/known-issues.md) | Edge cases — wide-angle recordings, Whisper hallucination, non-speaker talks |
| `skills/vault-ingress/scripts/persist-results.py` | Deterministically merge batch subagent returns into the tracking DB (Step 4) |
| `skills/vault-ingress/scripts/migrate-tracking-database.py` | Owner-only tracking schema migration with hash precondition, backup, and atomic replacement (Step 1) |
| `skills/vault-ingress/scripts/check-runtime.py` | Stdlib-only configured-interpreter and lane dependency probe |
| `skills/vault-ingress/scripts/write-analysis.py` | Render per-talk `analyses/*.md` from persisted effective state authorized by the same batch returns (Step 4) |
| `skills/vault-ingress/scripts/validate-returns.py` | Reject malformed schemas, statuses, scores, and catalog observations before either Step 4 writer runs |
| `skills/vault-ingress/scripts/queue-state.py` | Normalize legacy statuses; claim versioned batches; inspect or recover queue leases without replaying returns |
| `skills/vault-ingress/scripts/pptx-extraction.py` | Extract visual design data from .pptx files |
| `skills/vault-ingress/scripts/video-slide-extraction.py` | Extract slides from video via ffmpeg + perceptual dedup |
| `skills/vault-ingress/scripts/batch-download-videos.sh` | Parallel video download for batch processing |
| `skills/vault-ingress/scripts/vtt-cleanup.py` | Clean VTT subtitles into plain transcript text |
| `skills/vault-ingress/scripts/fetch-transcript.py` | Fetch a transcript, validate it, write only if real (captions → local Whisper) |
| `skills/vault-ingress/scripts/transcript_timing.py` | Own independent timing/quality receipts, validation, and quote resolution |
| `skills/vault-ingress/scripts/preflight-vault.py` | Read-only source/identity integrity gate before selection or re-analysis |
| `skills/vault-ingress/scripts/scan-shownotes.py` | Deterministic shownotes discovery and guarded tracking-DB import |
| `skills/vault-ingress/scripts/audit-source-identities.py` | Read-only `yt-dlp` evidence capture, deduplicated by active YouTube ID |
| `skills/vault-ingress/scripts/audit-pattern-catalog.py` | Read-only pattern catalog graph and contract gate before analysis |
| `skills/vault-ingress/scripts/apply-source-repairs.py` | Guarded dry-run/apply workflow for evidence-backed source metadata repairs |
| `skills/vault-ingress/scripts/aggregate-catalog-feedback.py` | Validate and aggregate return feedback without editing the pattern catalog |
| `skills/vault-ingress/scripts/read-tracking-database.py` | Strict, hash-reporting owner read for agent workflows |
| `skills/vault-ingress/scripts/mutate-tracking-database.py` | Typed, expectation-bound owner mutations for config and catalog metadata |

Every agent-driven read of `tracking-database.json` must go through
`read-tracking-database.py`. Every agent-driven write not already owned by a
specialized toolkit script must go through `mutate-tracking-database.py`; never
parse or rewrite the file directly. Both commands and the mutation-plan contract
are documented in [references/schemas-db.md](references/schemas-db.md#owner-read-and-mutation-contract).

A talk is processable when preflight confirms at least one usable transcript,
slide, or video source. A talk may be transcript-only or slides-only and
finish `processed_partial`; `video_url` is not a queue prerequisite. Slide sources,
in order of preference:
1. `pptx_path` — richest data (exact colors, fonts, shapes via python-pptx)
2. `slides_url` — download PDF from Google Drive
3. `video_url` — extract slides from the video using ffmpeg + perceptual dedup
4. none — transcript-only analysis (`processed_partial`)

The `slide_source` field tracks which path: `"pptx"`, `"pdf"`, `"both"`,
`"video_extracted"`, or `"none"`. The `pptx_catalog` array fuzzy-matches `.pptx`
files to shownotes entries.

## Step 1 — Bootstrap Vault State

**Vault discovery** — canonical path is always `~/.claude/rhetoric-knowledge-vault/`.

1. **Path exists** — use as `vault_root`, then load the database with the strict
   owner read command in
   [references/schemas-db.md](references/schemas-db.md#owner-read-and-mutation-contract).
2. **Path missing** — first-time setup: ask preferred location via `AskUserQuestion`,
   create the directory (and symlink if a custom path was chosen), then use a sole
   `initialize_database` mutation. Include database `schema_version: 1`, config
   `schema_version: 1`, and empty `talks`, `pptx_catalog`, `qr_codes`, `resources`,
   `thumbnails`, `confirmed_intents`, and `improvement_goals` arrays. Review the
   dry-run and apply it with `--expected-sha256 missing`; never create the JSON
   file directly.

**Schema gate** — vault-ingress owns the tracking database shape and migrations.
The stdlib-only strict reader may use the host interpreter for the initial
bootstrap read only. Read `config.python_path` from an existing database, or ask
for the interpreter path without writing the database when that field is absent.
Immediately re-read the same canonical path with that configured interpreter and
require the same SHA-256; restart discovery if the generation changed. Use the
configured interpreter for migration, queue commands, and every later toolkit
command. Run the owner migration before any other database mutation:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/migrate-tracking-database.py" \
  "{vault_root}/tracking-database.json"
```

Exit 0 writes one dry-run JSON report with `input_sha256`, source and target
schema versions, `output_sha256`, `record_counts`, `changed`,
`database_written: false`, `warnings`, and the deterministic backup path. A
changed report authorizes this exact apply command:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/migrate-tracking-database.py" \
  "{vault_root}/tracking-database.json" --apply --expected-sha256 "{input_sha256}"
```

Exit 0 from apply writes one JSON report with `database_written: true`, preserves
the complete original bytes under `{vault_root}/.backups/`, and atomically
installs database schema v1. A non-empty `warnings` array means replacement
completed with a durability warning and must not be reported as a failed/no-write
run. Exit 2 writes one error object to stdout plus a diagnostic to stderr and
leaves the database unchanged. Recover or
complete every active queue claim named by the diagnostic. For an unversioned
database, use `queue-state.py ... inspect` to identify the lease and
`queue-state.py ... recover` to close it. Those two commands accept schema 0;
recovery changes only queue-lease/status state and does not stamp or migrate the
database or talk record. The existing queue transition may advance a recovered
legacy claim receipt from schema v1 to v2 while adding its release fields. Rerun
migration dry-run, then apply its new exact digest. Do not copy a digest across
runs. `queue-state.py ... normalize` and `queue-state.py ... claim` require
database schema 1.

**Config bootstrapping** — ask once per missing field and persist to the tracking
database with expectation-bound `set_config` mutations. Re-read after every
successful apply and use the new hash for the next plan. Core fields: `shownotes` (enabled, source.type, source.path_or_url,
source.talks_subdir, url.base, url.template, thumbnail_path_template,
slug_convention), `pptx_source_dir`, `python_path`, `template_skip_patterns`.
See [references/schemas-db.md](references/schemas-db.md) for the full schema
and [../vault-profile/references/schemas-config.md](../vault-profile/references/schemas-config.md)
for field-by-field semantics and migration notes.

`python_path` is the interpreter authority for every operational command below;
never fall back to whichever `python3` happens to be on `PATH`. Installed plugin
bundles do not include `pyproject.toml`, so immediately probe the configured
runtime with the shipped stdlib-only checker:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/check-runtime.py" \
  --lanes core,pdf,pptx
```

All owner-authored tracking writes below require database schema 1 after this
gate. Preserve every independent record version and validate the complete
candidate before installing it. Only `migrate-tracking-database.py` may move
schema 0 to schema 1; its hash precondition binds replacement to the exact input
bytes as documented above.

Core requires Python 3.10+ and PyYAML and is blocking. The PDF and PPTX lanes
require pypdf and python-pptx respectively; a missing optional lane is reported
as degraded and must not erase a healthy transcript or alternate slide lane.
Require a lane before using it, for example `--require-lanes core,pdf`. Remote
Drive acquisition additionally needs the `gdown` module; captions need
`youtube-transcript-api`; audio download fallback needs `yt-dlp`; rendered PDF
inspection needs `pdftoppm`; video extraction needs Pillow, `imagehash`,
`ffmpeg`, and `ffprobe`; local Whisper needs `mlx-whisper` and `ffprobe`.
Inspect those with the checker's `google-drive`, `captions`,
`youtube-download`, `pdf-render`, `video`, and `whisper` lanes as selected talks
require. Each lane is independent: a failed optional import/tool disables only
that lane. Import failure details appear under the lane's `module_failures`;
dependency absence, initializer exceptions, native crashes, timeouts, and
invalid child results degrade an optional lane or block a required lane without
breaking the one-JSON contract. The checker writes a recovery instruction to
stderr whenever a lane is unavailable.

**Scan for new talks:** run the deterministic scanner in its default read-only
mode:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/scan-shownotes.py" \
  "{vault_root}/tracking-database.json"
```

Read the structured report before any mutation. `add` and `update` entries are
safe deterministic proposals; `review_required` entries need a human decision.
The scanner uses exact filename identity, derives supported YouTube and Google
Drive IDs, and keeps every matching `source_rejections` identity inactive.
For comparison only, title equality applies Unicode NFC and maps straight/curly
single and double quote glyphs to the same narrow equivalents; it preserves
case, other punctuation, and wording. Conference equality applies NFC plus
casefold only and preserves whitespace. The scanner never writes these
comparison transforms back to the database or report. Incomplete metadata,
substantive conflicts, and normalized filename collisions remain proposals.
Disabled, `remote_url`, and `none` sources return a structured no-op.

Apply the reviewed deterministic proposals with the same command plus
`--apply`. Only `add` and `update` entries mutate the tracking database. New
records receive current `schema_version` and status `"pending"`; exact-filename
updates fill empty fields without overwriting established values. The write is
atomic and rejects a tracking-database symlink. See
[references/schemas-db.md](references/schemas-db.md#shownotes-scanimport-report)
for the complete report and mutation contract.

**Scan for .pptx files:** Recursively glob `**/*.pptx` in `pptx_source_dir`;
fuzzy-match to `talks[]` entries. Report counts, then persist each reviewed result with a
`record_pptx` mutation and `schema_version: 1`, including the exact prior catalog record and, for a match,
the talk's exact prior `pptx_path` expectation. See [references/schemas-db.md](references/schemas-db.md)
for the PPTX extraction output schema (per-slide visual data, shape types, global design stats).
Run `"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/pptx-extraction.py"` for extraction.
Consume current schema v2 for timing/build evidence. A v0/v1 record has unknown
timing, not zero timing, and must be regenerated; an unknown future schema is
unusable until this reader is updated. The vault-profile layout-only consumer is
the documented v1/v2 exception for the unchanged `template_layouts` field.

**Pattern taxonomy recovery:** See [references/processing-rules.md](references/processing-rules.md) for the queue-owned
contract. Step 2 normalization deterministically routes processed results outside
the active pattern-scoring generation back to `needs-reprocessing`; do not infer
generation currency from processing date or hand-edit those statuses.

**Pattern catalog preflight:** Before source selection or re-analysis, run:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/audit-pattern-catalog.py"
```

Stdout is stable JSON. Exit 1 means structural catalog errors: stop before
scoring. Exit 0 may include `semantic_debts`; present those for human review and
do not auto-edit names, aliases, definitions, or graph relationships. The input,
report, and no-write contracts are defined in
[references/pattern-catalog-contract.md](references/pattern-catalog-contract.md).

**Source/identity preflight:** After bootstrapping and scanning, and before talk
selection or re-analysis, run the read-only offline gate:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/preflight-vault.py" {vault_root}
```

Exit 1 means one or more blocking integrity errors (identity disagreement,
unqualified duplicate recording, invalid source claim, or a claimed completed
artifact that is missing): stop and repair those records/artifacts before
processing. Exit 0 may still carry warnings for legacy evidence gaps or pending
artifacts; report them, but they do not make the vault unusable. The stable JSON
report and evidence shape are defined in
[references/source-identity-preflight.md](references/source-identity-preflight.md).

After the offline gate, capture and compare live YouTube provider evidence:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/audit-source-identities.py" {vault_root}
```

This networked audit invokes `yt-dlp` once per distinct active YouTube ID and
prints deterministic JSON without changing the vault. Review every proposed
`source_identity` block and finding, especially `likely_non_delivery_clip` and
`same_id_cross_talk_collision`. Provider uploader is not speaker evidence,
upload date is not recorded date, and the provider webpage URL must never be
auto-applied as an active source. See
[references/source-identity-audit.md](references/source-identity-audit.md).

Only after that human review, write a source-repair plan containing supported
facts and exact old-value preconditions, then dry-run it before applying:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/apply-source-repairs.py" \
  {vault_root}/tracking-database.json source-repair-plan.json
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/apply-source-repairs.py" \
  {vault_root}/tracking-database.json source-repair-plan.json --apply
```

The apply command validates the whole plan before mutation, refuses active queue
claims, writes a byte-for-byte backup under `{vault_root}/.backups/`, and replaces
the DB atomically. Re-run the preflight after applying; do not claim work until
blocking findings reach zero.

Read `rhetoric-style-summary.md` and `slide-design-spec.md`. Report:
"X processed, Y remaining. PPTX: A cataloged, B matched, C extracted."

## Step 2 — Select Talks to Process

Fresh queue work uses claim schema v5. Before changing any talk status,
`queue-state.py claim` snapshots one immutable `adherence_baseline` for the
entire selected batch, stamps `required_return_schema_version: 5`, and copies
that exact snapshot into every member claim. The snapshot uses the current
catalog fingerprint and pattern-scoring schema, includes only current
`processed`/`processed_partial` talks, and excludes every active-batch filename
before inspecting its prior score. Its `as_of` equals the claim's canonical
`claimed_at`; do not edit or recompute it after the claim is written.

- Run `"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/queue-state.py"
  {vault_root}/tracking-database.json normalize` once. This one copy-on-write
  command migrates legacy
  `skipped_no_video`/`skipped_no_transcript` states from the talk's usable source
  capabilities. The shared root-aware assessor must actually read and validate a
  local transcript/deck/PDF before it counts; a non-empty or missing path is not a
  capability. Declared remote video/slide acquisition remains eligible for a
  claim-time download. A `transcript_source` provenance label alone
  is not capability. Only a record with no verified local source or remote
  acquisition path becomes `skipped_no_sources`. The same command uses the shared
  exact-generation selector to requeue valid `processed`/`processed_partial`
  results that cannot enter the active pattern cohort. For scoring v5, exact
  generation identity is necessary but insufficient: the shared freshness assessor
  also re-hashes every persisted source-located artifact against the database's
  vault and configured source roots. Missing, replaced, or otherwise drifted
  evidence is excluded and requeued. Transcript freshness also revalidates the
  hash-bound quality policy against current owner/provider duration; source-
  identity drift cannot leave a previously accepted partial transcript in the
  cohort. Its `normalizations` report carries ordered
  reason codes, deterministic freshness details where applicable, and the stored
  `reprocess_reason` for each changed row. Malformed current-generation identity or
  score lanes reject the complete command without writing; inflight, pending,
  already-queued, and skipped records are not generation-normalized. A repeated
  successful normalization with no new drift leaves the DB bytes unchanged.
  Completed claims remain immutable evidence on the requeued talk and move to
  history normally when a later claim is created.
- Claim each exact batch through `queue-state.py ... claim --run-id <stable-run>
  --batch-id <stable-batch> --now <timezone-aware-ISO>`. The command selects
  `pending`, `needs-reprocessing`, and retryable download failures, writes an
  atomic lease, increments `reprocess_generation`, and returns the claimed talk
  list. Every fresh claim is schema v5 and requires return schema v5. Never
  change a record to `reprocessing-inflight` by hand.
- Before claiming a non-YouTube talk whose transcript will be used as evidence,
  acquire the transcript and register its canonical vault-relative
  `transcript_path` through the guarded source-repair workflow. A worker-returned
  path cannot grant citation authority to that same return.
- Repeating the same live/completed run and batch is an idempotent replay: use
  the exact stored claims and baseline, and do not rewrite the DB. Recover an
  expired or stranded lease with `queue-state.py ... recover`; recovery keeps
  the saved snapshot in claim history. A later claim creates a new generation and
  takes a fresh pre-mutation snapshot rather than editing or reusing the old
  generation's baseline.
- Set `slide_source` per the hierarchy above. Mark `"skipped_no_sources"` only if
  preflight confirms that transcript, slide, and video sources are all unavailable.
- If `$ARGUMENTS` specifies a talk filename or title, process ONLY that one.

## Step 3 — Process Talks via Parallel Subagents (Batches of 5)

Per batch: launch 5 subagents in parallel, wait, run Step 4 (Persist Subagent
Results), then run Step 5 (Update Rhetoric Summary), then move to the next
batch. When all batches have finished, proceed to Step 6.

Each subagent receives the talk's DB entry and current
`rhetoric-style-summary.md`, runs A → B → B2 → C, and returns a JSON payload.
The summary supports qualitative rhetoric analysis, but the worker MUST NOT
parse Section 15 for numeric adherence. The immutable
`talk._queue_claim.adherence_baseline` is the sole numeric authority.

The return version matches the active claim contract. A fresh schema-v5 claim
with `required_return_schema_version: 5` requires return v5. Saved claim schemas
v1–v4 authorize only their same-numbered return schemas and remain replayable
archival artifacts; none can enter the current scoring cohort. Recover a live
legacy lease and issue a fresh v5 generation instead of mutating its claim.
A successfully persisted v5 return produces talk-record schema v5 and is the
only return generation eligible for pattern-scoring schema v5. Valid v4
source-located evidence remains intact with evidence-ledger schema v1, but it is
requeued for v5 and never receives synthesized v5 outcomes.

Return v5 uses the exact empty `adherence_assessment` sentinel and omits
`adherence_comparison` unless an owner-side second-stage comparison can prove
that the canonical talk and frozen baseline carry the same
`opportunity_coverage_identity`. Persistence never guesses or normalizes across
different identities. The schema-v2 baseline keeps `eligible_talk_count` for
per-pattern history separately from the exact-identity `scored_talk_count`; a
mixed opportunity cohort or a cohort with no evaluable pattern opportunities uses
the explicit unavailable/null comparison sentinel.
The return copies `run_id`, `batch_id`, and `reprocess_generation` from the
talk's active `_queue_claim`; persistence rejects a stale, mismatched, or
unclaimed return.
Full procedure — slide acquisition per `slide_source`, rhetoric/style analysis,
pattern-taxonomy tagging, and the return-JSON shape — lives in
[references/subagent-instructions.md](references/subagent-instructions.md).

Every v4/v5 worker also returns a closed `source_inspection` receipt. Transcript,
static-slide/native-deck, and delivery-video records carry the exact line, page,
or time ranges actually inspected. Distinct source comparisons each carry their
exact underlying group and `comparison_scope`. Workers return only those raw
ranges and citation claims; persistence derives artifact roots/paths/hashes,
line and time matches, metadata values, coverage flags, and the evidence schema
marker. Never copy engine-owned fields from an earlier analysis into a return.

Transcripts come from `skills/vault-ingress/scripts/fetch-transcript.py`, never from inline fetch
code. It tries the caption track, falls back to local Whisper, validates the
result, and writes atomically only on success. A failed fetch never replaces the
transcript with a crash report or partial speech:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/fetch-transcript.py" <video-id-or-url> \
    --out {vault_root}/transcripts/<youtube_id>.txt \
    --existing-source <youtube_auto|whisper|manual|unknown> \
    [--duration-seconds N]
```

Exit 0 wrote (or kept) a valid transcript; exit 1 means no source produced one
and the talk is `processed_partial` at best; exit 2 is an argument or tool-state
error. Validation thresholds and failure signatures are the script's own — see
its module docstring and `transcript_quality.py`. `--duration-seconds` is only an
expected value and must match a source-owned provider or local-media probe; a
worker return or unbound metadata never lowers the quality floor. Its JSON
`quality_path` names the required hash-current quality receipt on every success.
`timed_path` is non-null only when a separate schema- and hash-verified timing
receipt has usable owner-bound segments. Current timing receipts are schema v2;
v1/minimal sidecars are archival and cannot supply timing or provenance. Do not
rewrite them in place: re-fetch/re-transcribe from the proved source, or import
the original VTT artifact, so the current writer can bind owner and bounds.
Missing or rejected timing does not invalidate ordinary
transcript evidence, but missing quality does exclude it from current v5
scoring; requeue legacy transcripts through the fetcher. Reparse runs must pass
the talk's owner-recorded `transcript_source` (or `unknown` when absent), even
when the transcript already exists. For `youtube_auto` only, a missing/stale
timing receipt triggers non-destructive caption enrichment: fetched caption text
must equal the existing text exactly except for whitespace layout before a
caption timing receipt is written, and the transcript bytes are never replaced.
Edited, manual, Whisper, unknown-provenance, or mismatching text remains
timing-unavailable and is never relabeled as captions.

Without `--force`, any existing transcript is validation-only: a stricter caller
policy may reject it but cannot authorize replacement. Pass `--force` only after
inspecting the named artifact and intentionally authorizing new source bytes.
A failed fetch or caught bundle write restores the prior transcript, quality,
and timing bytes. If fetched text is valid but optional segments are malformed,
text-mismatched, or outside their source bound, the transaction writes text and
quality, removes stale timing, and reports timing unavailable.

For a supplied WebVTT artifact, choose the output identity explicitly; language
suffixes must never collide implicitly:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/vtt-cleanup.py" \
  {vault_root}/transcripts/<source>.vtt \
  {vault_root}/transcripts/<transcript_id>.txt [--force]
```

The VTT must be a non-symlink regular file inside the transcript directory.
Its schema-v2 receipt binds the safe relative path, exact VTT digest, and final
cue extent. Replacement still requires explicit `--force`.

## Step 4 — Persist Subagent Results

Runs after each batch inside Step 3's loop (not as a separate post-loop
phase). Mechanical persistence of the batch's subagent JSON returns:

- **Validate the whole batch before any write.** Run
  `"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/validate-returns.py" batch-returns.json`.
  Stop on a non-zero exit and repair the named return. The validator enforces the
  terminal status, return field types, catalog ID and polarity, observability,
  confidence and evidence, score arithmetic, co-presenter shape, language code,
  all catalog-feedback lanes, source-gated `not_evaluable` coverage, and the
  schema-v3 video-artifact trust boundary. V4/v5 `not_evaluable` entries contain
  only `pattern_id` plus the exact reason code derived by the contract. An
  observable catalog entry still awaiting an owner-approved source gate fails
  closed: it cannot be detected or silently counted as absent and must use
  `source_gate_pending_owner_review`. For `video_extracted`, the enum alone
  never creates `static_slides`: that source exists only when the complete manifest
  proves a verified manual `slide_region`. `status: "processed"` additionally
  requires its promoted `slides_local_path`. Both writers import this same validator,
  so bypassing the standalone command cannot weaken the boundary.
  For v5, an N/A-capable nondetected entry is assessed only after its complete
  `applicability_evaluable_from` gate is proven. Complete coverage requires
  exactly one source-located `applicability_assessments` row; incomplete
  coverage forbids a row and yields `not_evaluable`. Catalog-authorized
  `not_applicable`, applicable-then-undetected, positive-only absence, and
  missing-coverage states remain distinct.
  Range-complete does not mean modality-complete. Bare `native_deck`, bare
  `delivery_video`, video-extracted static pages, and current source-comparison
  receipts remain positive-only; they cannot authorize absence or force an
  applicability assessment until a canonical modality/alignment receipt exists.
  Canonical inspection rows expose this with engine-owned
  `absence_capability_complete` and `absence_capability_reason` alongside the
  independent `coverage_complete` locator receipt.
  For newly emitted work, exit 0 is necessary but not sufficient: every
  processed entry in `pattern_scoring_generations` must report
  `status: current`. `legacy_unbaselineable` exists only so saved v1–v4 artifacts remain
  replayable and must be repaired before accepting new analysis.
  A v5 analysis additionally carries one sorted engine-owned `pattern_outcomes`
  row per observable catalog entry plus `opportunity_coverage_identity`. Raw
  returns cannot supply either field.
- **Update tracking DB — deterministic merge, NOT hand-mapping.** Collect the
  batch's subagent JSON returns into an array file (`batch-returns.json`) and run
  `"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/persist-results.py" {vault_root}/tracking-database.json batch-returns.json`.
  The script first requires the return filenames to equal every live member of one
  run/batch claim; partial, extra, mixed-identity, duplicate, closed, or stranded
  batches fail before merge. The script requires database schema v1 and current
  independent record versions; Step 1 is the sole migration path. It then merges each return into its matching
  talk entry, promotes the declared queryable scalars to the talk top level, and
  rewrites the DB in place. Do NOT hand-copy fields one at a time — that is what
  dropped structured data before (it was computed and reached the analysis files
  but never landed in the DB).
  Contract, the promoted-scalar allowlist, and merge semantics live in
  `skills/vault-ingress/scripts/persist-results.py` (top-of-file docstring and the
  `PROMOTE` list); the shared snapshot structured policy registry lives in
  `skills/vault-ingress/scripts/return_validation.py` so standalone validation and
  persistence enforce the same container shapes. To make
  a new field queryable, extend the return schema and that list; never reintroduce
  manual mapping.
  The same script validates each new detection against catalog observability,
  its `evidence_source` source/outcome gate, and its evidence-channel policy; it
  resolves every `evidence_citations` source location and refuses the whole
  batch when proof is absent or unverifiable. Comparison detections must locate
  proof from every underlying member of `evidence_sources_used`.
  Version-2 through version-5 returns snapshot-replace every supplied declared
  field, including empty values where that field contract permits emptiness,
  and complete structured maps; omission preserves a field. Saved returns with
  missing/version-1 metadata retain their legacy
  additive behavior. A corrective reparse that needs to delete a field rather
  than replace it declares its analysis-owned dotted paths in `clear_fields`.
  Any video return without a promoted artifact must clear
  `slides_local_path`; an untrusted return is context-only and cannot carry
  authored-slide evidence. The script
  persists that path when a trusted artifact is promoted, replaces a complete
  video-extraction manifest atomically, and clears matching promoted scalars.
  Returns satisfying the current evidence contract receive the exact catalog
  fingerprint and scoring-schema version 5. Replayable v1–v4 returns that cannot
  prove it are retained with
  `pattern_scoring_generation_status: legacy_unbaselineable`, exact machine reasons, and no current fingerprint or
  scoring version. The DB write remains atomic.
  Only after every member has merged successfully, stdout exposes
  `current_adherence_baseline`: an all-inclusive post-batch snapshot with
  `active_batch_excluded: false` and `excluded_filenames: []`. Downstream
  Section 15/profile consumers use this complete-candidate payload; they never
  recompute a cohort after an individual member merge or mutate the immutable
  preclaim snapshot.
  Its normalized `--run-date` (or generated UTC timestamp) is authoritative for
  every processed member's `processed_date` and claim release; return-side dates
  are legacy advisory metadata and cannot override it. A return-side full
  timestamp is treated as an explicit identity assertion and must normalize to
  the same batch stamp or the entire write fails.
  A successful merge closes the matching queue lease as `completed`; it never
  deletes claim history. Claims v2 through v5 close at their own versions, and
  an active v1 lease upgrades to v2. Every completed v2–v5 claim stores a canonical
  SHA-256 receipt of the exact return payload; a receiptless completed v1 claim
  cannot authorize analysis replacement. Unknown future claim versions fail
  closed. An
  interrupted batch is recovered with
  `queue-state.py ... recover --now <ISO> --stale-after-seconds <N>`, not by
  replaying whichever old return files happen to exist.
  Future talk-record schemas are rejected before merge so this writer never
  stamps a newer record down to its current version. Pass the canonical tracking
  DB path: queue and persistence tools reject a final-component symlink before
  opening it, preventing atomic replacement from splitting the link and target.
- **Write per-talk analysis files — run the script, do NOT hand-write them.** Run
  `"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/write-analysis.py" batch-returns.json {vault_root}/analyses --talks {vault_root}/tracking-database.json`
  over the SAME `batch-returns.json` the merge consumed, so the DB and the files
  cannot diverge. The writer verifies each completed claim's payload receipt and
  persisted catalog fingerprint/scoring version, requires exact membership
  across the completed batch, validates the persisted effective snapshot analysis, and
  renders analysis-owned fields from that canonical talk state. Fields
  omitted and preserved during persistence remain in Markdown. Only the
  receipt-bound, non-persisted catalog-feedback side channel comes from the
  return. The writer also renders the persisted, writer-owned timestamp. It
  checks return targets against both one
  another and existing directory entries under normalized/case-folded identity,
  rejects directory/special-file targets, stages every body, and commits with
  reverse rollback so a late failure cannot leave a partial batch. An exact
  analysis-target symlink is replaced as a directory entry; its external target
  is never followed or modified.
  It renders `{vault_root}/analyses/{talk_filename}.md` per effective talk —
  14 dimensions, structured data, verbatim examples, "Presentation Patterns Scoring",
  and catalog feedback — creates `analyses/` if missing, prints a JSON summary, and
  exits non-zero on a return with no `filename`. Section list and field handling live
  in `skills/vault-ingress/scripts/write-analysis.py` (top-of-file docstring).
  Non-empty adherence prose from a legacy v1–v4 return is preserved only as
  archival text under an unmistakable `legacy-unverified` label. It is never a
  current numeric comparison, Section 15 aggregate, or profile input.
- **Aggregate catalog feedback — after the final batch, do not hand-harvest or
  auto-edit the catalog.** Run the read-only intake over every return file or
  return directory:
  `"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/aggregate-catalog-feedback.py" {return_paths}`.
  Review the stable JSON's invalid entries, exact-ID recurrence, normalized
  suggestions, and polarity warnings with the speaker. Recurrence is evidence
  for review, never authorization to change a catalog file. The five lanes and
  report contract live in
  [references/catalog-feedback-intake.md](references/catalog-feedback-intake.md).

Proceed immediately to Step 5.

## Step 5 — Update Rhetoric Summary

Still per-batch (continues Step 3's loop). The summary update requires a
speaker-review gate and stays separate from Step 4 persistence. Unlike DB
writes, edits to `rhetoric-style-summary.md` change the speaker's
ground-truth narrative and must not be applied silently.

1. **Speaker-review gate.** Present the subagent's proposed `summary_updates`
   and `new_patterns` as a section-by-section diff and wait for explicit
   speaker confirmation. Silent application erodes the speaker's sense of
   ownership of their own style summary; pattern-taxonomy additions in
   particular drift if applied unreviewed. Only bypass the gate if the
   speaker pre-authorized this batch ("just apply everything, don't ask").
2. **Apply approved changes.** Integrate confirmed `new_patterns` and
   `summary_updates` into `rhetoric-style-summary.md`. Sections 1–14 map to
   the 14 dimensions; Sections 15–16 are the cross-talk improvement & adherence
   narrative and speaker-confirmed intent — structure defined in
   [references/processing-rules.md](references/processing-rules.md) Rhetoric
   Summary — Improvement & Adherence Sections. Rebuild Section 15 only after the
   whole batch has persisted, using `persist-results.py` stdout's
   `current_adherence_baseline` plus talks from the exact current catalog
   fingerprint/scoring-schema cohort. Never use a processing-date cohort and
   never rebuild after member 1 of a multi-member batch. Section 15 remains
   human-readable narrative; workers do not parse it as numeric authority.
   Render its sole machine-readable current block only from the complete
   post-batch `pattern_profile` candidate and live tracking database:

   ```bash
   "{python_path}" "{speaker_toolkit_root}/skills/vault-profile/scripts/section15_pattern_history.py" replace \
     {vault_root}/rhetoric-style-summary.md pattern-profile-candidate.json \
     {vault_root}/tracking-database.json
   ```

   The helper rejects a stale same-generation cohort, validates through the
   shared profile assessor, and atomically replaces only the delimited block.
   `section15_pattern_history.py replace` is the sole supported current-block
   replacement operation and always requires the live tracking database.
   A nonzero exit guarantees no write; do not hand-edit or partially update the
   block.
   **Recount status from the DB every time** — never increment manually.
3. **Report.** Output: talks processed, new patterns, current state, skipped
   talks. Flag structural changes prominently (new presentation mode, new
   workflow pattern).

When Step 3's batch loop finishes, proceed to Step 6.

## Step 6 — Extract Remaining PPTX Visual Data

Runs once after all Step 3 batches have completed.

Process PPTX files not yet extracted during Step 3: unmatched catalog entries, talks
that used PDF as primary but have a PPTX available, or entries with
`pptx_visual_status: "pending"`. Skip if already `"extracted"`.
Run `"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/pptx-extraction.py" <path.pptx>` for each file.
Require schema v2 before using native timing fields. Regenerate v0/v1 output and
stop on an unknown future schema rather than interpreting missing fields as zero.

**PPTX matching rules:** The .pptx files are in `Conference/Year/TalkName.pptx` and
shownotes entries have `conference` and `title` fields. Fuzzy-match by: normalize
conference names (strip year, "Days", "Conference"), match by date proximity and title
substring. Skip files with "static" in name, conflict copies matching `(N).pptx`, and
files matching `config.template_skip_patterns`. Some talks have multiple .pptx files
(one per delivery) — match to the closest date.

After 3+ extractions, populate `slide-design-spec.md`; after 5+, analyze cross-talk
patterns (colors, fonts, footers).

Proceed immediately to Step 7.

## Step 7 — Regenerate Speaker Profile

If `{vault_root}/speaker-profile.json` exists, invoke `Skill(skill: "vault-profile")`
with the updated tracking database plus the resolved `{vault_root}` and exact
database-configured `{python_path}` as handoff context. The profile skill re-reads
the database and rejects a missing or mismatched interpreter; never let the handoff
fall back to `python3` on `PATH`. Report the diff of changes (added fields, changed
values) so the speaker can verify.

If the profile doesn't exist, skip this step silently.

Proceed immediately to Step 8.

## Step 8 — Verify Improvement Goals

If the tracking DB has no active `improvement_goals` (none whose `status` is
outside `achieved`/`retired`), skip this step silently. Otherwise, with the
post-batch full-cohort pattern baseline current, pass the complete active-goal
array and that structured baseline to:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-clarification/scripts/goal_generation_provenance.py" \
  < goal-generation-input.json
```

The input object contains `goals` and `current_pattern_baseline`; stdout is one
schema-v1 assessment per goal. Exit 1 is a malformed owner record or baseline:
stop before constructing a mutation plan and change no goal. Require exactly one
assessment for every active goal before calculating or writing anything. Only a
`comparable` assessment authorizes metric calculation.

Apply the assessment according to the stored goal record schema; never restamp a
legacy goal:

- A schema-v1 `antipattern` or `underuse` goal is report-only
  `unverifiable`. Preserve the complete record and create no mutation for it.
- A schema-v1 `pacing` or `other` goal may be comparable through its independent
  provenance lane. For a comparable goal, patch only `current_value`,
  `last_checked`, `checked_by`, and `status`; never add `verification_state` or
  `verification_reasons`. A non-comparable assessment is report-only.
- A schema-v2 goal uses the full verification contract. Persist
  `needs_rebaseline` or `unverifiable` in `verification_state` with the exact
  assessment reasons while preserving `current_value` and `status`. For a
  comparable goal, persist the calculated metric, check metadata, outcome status,
  `verification_state: "current"`, and empty `verification_reasons`.

For every mutation, `expect` must contain exactly the fields being set with the
values from the latest strict read. If no assessment authorizes a write, do not
invoke the mutator. Otherwise dry-run the complete multi-goal plan as one
transaction, review it, apply it against the reported input SHA, then re-read the
database; one failed assessment or mutation precondition must never leave a
partial goal update. The full write rubric is in
[references/processing-rules.md](references/processing-rules.md) Improvement
Goal Verification. Report current comparable outcomes first, then every goal that
needs rebaselining or is unverifiable.

Proceed immediately to Step 9.

## Step 9 — Same-Week Clarification Trigger

If no talks were newly processed in this run, finish here without further action.

Otherwise, scan the newly-processed talks for delivery date and bucket each by how
long ago it was delivered (`today − date`). The handoff strength is tiered by recency —
clarification quality decays fast, so the freshest talks get an active handoff, not a
footnote. For every bucket, first compute that talk's **candidate clarification topics**:
- Each per-talk `areas_for_improvement` entry.
- Any `pattern_observations` the subagent flagged as **unverifiable from transcript
  alone** (low confidence, heavy reliance on visual cues, non-English dialogue without
  captions).

**≤7 days (same-week) — hand off inline, don't just recommend.** This is the
freshest-possible clarification window: memory of the delivery is sharpest right after
the talk, and verbal beats that didn't appear in auto-captions (bilingual jokes rendered
in a non-primary language, improvised asides, fly-bys that weren't in the deck) are only
recoverable now. Do NOT bury this as a closing recommendation. Use `AskUserQuestion` to
**offer to run `vault-clarification` right now**, showing the candidate topics you
computed so the speaker sees exactly what the session would cover. If they accept, invoke
`Skill(skill: "vault-clarification")` immediately, carrying those candidate topics as the
session's seed agenda. If they decline, note it and finish.

**7–30 days — recommend the full session.** Recommend running
`Skill(skill: "vault-clarification")`, listing the candidate topics, but note that some
verbatim details may already be lost. Do not auto-invoke.

**30+ days — recommend the compressed session.** Memory has decayed and detailed recall
is unreliable; recommend the compressed clarification instead of the full one. Do not
auto-invoke.

## Error Handling

| Transcript | Slides (PPTX/PDF) | Video | Status | Action |
|-----------|-------------------|-------|--------|--------|
| OK | OK | — | `processed` | Full analysis |
| OK | FAIL | OK | `processed` | Extract slides from video, then full analysis |
| OK | FAIL | FAIL | `processed_partial` | Transcript only (no visual analysis) |
| FAIL | OK | — | `processed_partial` | Slides only |
| FAIL | FAIL | OK | `processed_partial` | Extract slides from video, visual only |
| FAIL | FAIL | FAIL | `skipped_download_failed` | Skip, move on |

Persistence mechanically rechecks terminal reasons against the claimed talk.
`skipped_no_sources` requires no live capability; `skipped_download_failed`
requires a remote acquisition path and no verified local transcript/PPTX/PDF/video
artifact; stale or unreadable local declarations are not capabilities;
`skipped_duplicate` requires a bound duplicate `source_relation` target.

## Important Notes

- Create `transcripts/`, `slides/`, `analyses/` dirs if missing.
- Re-read tracking DB before writing (single source of truth).
- Preserve all summary content — add/refine, never delete.
- Auto-score only source-located observations for `observable: true` catalog entries.
  Hidden preparation/provenance belongs in clarification, not pattern inference.
- Raw-score, breadth, and adherence comparisons are permitted only across an
  exact matching `opportunity_coverage_identity`. A mismatched or mixed cohort
  uses the explicit unavailable/empty sentinel; never normalize denominators.

For input-quality edge cases that require non-default handling — wide-angle
room recordings, Whisper hallucination on bad audio, non-speaker talks
slipping into playlists — see
[references/known-issues.md](references/known-issues.md).
