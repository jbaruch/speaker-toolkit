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
| `transcripts/{youtube_id}.txt` | Downloaded/cleaned transcripts |
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
| `skills/vault-ingress/scripts/write-analysis.py` | Render per-talk `analyses/*.md` from persisted effective state authorized by the same batch returns (Step 4) |
| `skills/vault-ingress/scripts/validate-returns.py` | Reject malformed schemas, statuses, scores, and catalog observations before either Step 4 writer runs |
| `skills/vault-ingress/scripts/queue-state.py` | Normalize legacy statuses; claim versioned batches; inspect or recover queue leases without replaying returns |
| `skills/vault-ingress/scripts/pptx-extraction.py` | Extract visual design data from .pptx files |
| `skills/vault-ingress/scripts/video-slide-extraction.py` | Extract slides from video via ffmpeg + perceptual dedup |
| `skills/vault-ingress/scripts/batch-download-videos.sh` | Parallel video download for batch processing |
| `skills/vault-ingress/scripts/vtt-cleanup.py` | Clean VTT subtitles into plain transcript text |
| `skills/vault-ingress/scripts/fetch-transcript.py` | Fetch a transcript, validate it, write only if real (captions → local Whisper) |
| `skills/vault-ingress/scripts/preflight-vault.py` | Read-only source/identity integrity gate before selection or re-analysis |
| `skills/vault-ingress/scripts/audit-source-identities.py` | Read-only `yt-dlp` evidence capture, deduplicated by active YouTube ID |
| `skills/vault-ingress/scripts/audit-pattern-catalog.py` | Read-only pattern catalog graph and contract gate before analysis |
| `skills/vault-ingress/scripts/apply-source-repairs.py` | Guarded dry-run/apply workflow for evidence-backed source metadata repairs |
| `skills/vault-ingress/scripts/aggregate-catalog-feedback.py` | Validate and aggregate return feedback without editing the pattern catalog |

A talk is processable when preflight confirms at least one usable transcript,
slide, or video source. A talk may therefore be transcript-only or slides-only and
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

1. **Path exists** — use as `vault_root`, read `tracking-database.json`.
2. **Path missing** — first-time setup: ask preferred location via `AskUserQuestion`,
   create directory (and symlink if custom path chosen), initialize empty
   `tracking-database.json` with empty `config`, `talks`, `pptx_catalog`.

**Config bootstrapping** — ask once per missing field and persist to the tracking
database. Core fields: `shownotes` (enabled, source.type, source.path_or_url,
source.talks_subdir, url.base, url.template, thumbnail_path_template,
slug_convention), `pptx_source_dir`, `python_path`, `template_skip_patterns`.
See [references/schemas-db.md](references/schemas-db.md) for the full schema
and [../vault-profile/references/schemas-config.md](../vault-profile/references/schemas-config.md)
for field-by-field semantics and migration notes.

**Scan for new talks:** Build the talks directory path as
`{shownotes.source.path_or_url}/{shownotes.source.talks_subdir}`; glob `*.md`
there; parse and add any file not yet in `talks[]` (title, conference, date,
URLs, status `"pending"`). For `remote_url` or `none` source types, skip the
scan — the vault ingests only the talks the speaker has already registered
elsewhere. Extract
`video_url`, `slides_url` from frontmatter/links. Parse IDs from URLs:
- `youtube_id`: accept `youtube.com/watch?v=`, `youtu.be/`,
  `youtube.com/shorts/`, and `youtube.com/embed/`; require the resulting
  11-character ID to agree with any stored value
- `google_drive_id`: extract the file ID from the Google Drive URL

Before accepting a scanned source, compare it with the talk's
`source_rejections`. Never reactivate a URL (or the same YouTube ID in another
URL form) that was previously verified as a non-delivery clip, wrong delivery,
unrelated recording, or wrong event's deck. Report the upstream drift and leave
the rejected source inactive until a human supplies replacement evidence.

Default status is always `"pending"` for new entries.

**Scan for .pptx files:** Recursively glob `**/*.pptx` in `pptx_source_dir`; fuzzy-match
to `talks[]` entries. Report counts. See [references/schemas-db.md](references/schemas-db.md)
for the PPTX extraction output schema (per-slide visual data, shape types, global design stats).
Run `python3 skills/vault-ingress/scripts/pptx-extraction.py` for extraction.
Consume current schema v2 for timing/build evidence. A v0/v1 record has unknown
timing, not zero timing, and must be regenerated; an unknown future schema is
unusable until this reader is updated. The vault-profile layout-only consumer is
the documented v1/v2 exception because `template_layouts` did not change.

**Pattern taxonomy recovery:** See [references/processing-rules.md](references/processing-rules.md) for the queue-owned
contract. Step 2 normalization deterministically routes processed results outside
the active pattern-scoring generation back to `needs-reprocessing`; do not infer
generation currency from processing date or hand-edit those statuses.

**Pattern catalog preflight:** Before source selection or re-analysis, run:

```bash
python3 skills/vault-ingress/scripts/audit-pattern-catalog.py
```

Stdout is stable JSON. Exit 1 means structural catalog errors: stop before
scoring. Exit 0 may include `semantic_debts`; present those for human review and
do not auto-edit names, aliases, definitions, or graph relationships. The input,
report, and no-write contracts are defined in
[references/pattern-catalog-contract.md](references/pattern-catalog-contract.md).

**Source/identity preflight:** After bootstrapping and scanning, and before talk
selection or re-analysis, run the read-only offline gate:

```bash
python3 skills/vault-ingress/scripts/preflight-vault.py {vault_root}
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
python3 skills/vault-ingress/scripts/audit-source-identities.py {vault_root}
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
python3 skills/vault-ingress/scripts/apply-source-repairs.py \
  {vault_root}/tracking-database.json source-repair-plan.json
python3 skills/vault-ingress/scripts/apply-source-repairs.py \
  {vault_root}/tracking-database.json source-repair-plan.json --apply
```

The apply command validates the whole plan before mutation, refuses active queue
claims, writes a byte-for-byte backup under `{vault_root}/.backups/`, and replaces
the DB atomically. Re-run the preflight after applying; do not claim work until
blocking findings reach zero.

Read `rhetoric-style-summary.md` and `slide-design-spec.md`. Report:
"X processed, Y remaining. PPTX: A cataloged, B matched, C extracted."

## Step 2 — Select Talks to Process

Fresh queue work uses claim schema v3. Before changing any talk status,
`queue-state.py claim` snapshots one immutable `adherence_baseline` for the
entire selected batch, stamps `required_return_schema_version: 3`, and copies
that exact snapshot into every member claim. The snapshot uses the current
catalog fingerprint and pattern-scoring schema, includes only current
`processed`/`processed_partial` talks, and excludes every active-batch filename
before inspecting its prior score. Its `as_of` equals the claim's canonical
`claimed_at`; do not edit or recompute it after the claim is written.

- Run `python3 skills/vault-ingress/scripts/queue-state.py
  {vault_root}/tracking-database.json normalize` once. This one copy-on-write
  command migrates legacy
  `skipped_no_video`/`skipped_no_transcript` states from the talk's usable source
  capabilities. A record with a transcript artifact or slide source re-enters the
  queue even without video; a `transcript_source` provenance label alone is not
  capability. Only a record with no transcript artifact/acquisition path, slide,
  or video source becomes `skipped_no_sources`. The same command uses the shared
  exact-generation selector to requeue valid `processed`/`processed_partial`
  results that cannot enter the active pattern cohort. Its `normalizations` report
  carries ordered reason codes and the stored `reprocess_reason` for each changed
  row. Malformed current-generation identity or score lanes reject the complete
  command without writing; inflight, pending, already-queued, and skipped records
  are not generation-normalized. A repeated successful normalization with no new
  drift leaves the DB bytes unchanged. Completed claims remain immutable evidence
  on the requeued talk and move to history normally when a later claim is created.
- Claim each exact batch through `queue-state.py ... claim --run-id <stable-run>
  --batch-id <stable-batch> --now <timezone-aware-ISO>`. The command selects
  `pending`, `needs-reprocessing`, and retryable download failures, writes an
  atomic lease, increments `reprocess_generation`, and returns the claimed talk
  list. Every fresh claim is schema v3 and requires return schema v3. Never
  change a record to `reprocessing-inflight` by hand.
- Repeating the same live/completed run and batch is an idempotent replay: use
  the exact stored claims and baseline, and do not rewrite the DB. Recover an
  expired or stranded lease with `queue-state.py ... recover`; recovery keeps
  the v3 snapshot in claim history. A later claim creates a new generation and
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

The return version matches the active claim contract. A fresh schema-v3 claim
with `required_return_schema_version: 3` requires return v3. Compatibility work
under a legacy claim schema v1/v2 may use only return v1/v2; use v2 for newly
authored compatibility work, while v1 remains saved-artifact replay support.
Never attach return v3 to a legacy claim.

For a v3 claim whose baseline has fewer than 10 scored talks, return the exact
empty `adherence_assessment` string and omit `adherence_comparison`. At 10 or
more, copy the claim baseline exactly into the structured comparison, bind the
validated talk score, and write 2–4 punctuation-terminated assessment
sentences. Never regenerate the baseline after analyzing the talk.
The return copies `run_id`, `batch_id`, and `reprocess_generation` from the
talk's active `_queue_claim`; persistence rejects a stale, mismatched, or
unclaimed return.
Full procedure — slide acquisition per `slide_source`, rhetoric/style analysis,
pattern-taxonomy tagging, and the return-JSON shape — lives in
[references/subagent-instructions.md](references/subagent-instructions.md).

Transcripts come from `skills/vault-ingress/scripts/fetch-transcript.py`, never from inline fetch
code. It tries the caption track, falls back to local Whisper, validates the
result, and writes atomically only on success — so a failed fetch leaves no file
rather than leaving a crash report where speech belongs:

```bash
python3 skills/vault-ingress/scripts/fetch-transcript.py <video-id-or-url> \
    --out {vault_root}/transcripts/<youtube_id>.txt [--duration-seconds N]
```

Exit 0 wrote (or kept) a valid transcript; exit 1 means no source produced one
and the talk is `processed_partial` at best; exit 2 is an argument or tool-state
error. Validation thresholds and failure signatures are the script's own — see
its module docstring and the constants above `validate_transcript`.

## Step 4 — Persist Subagent Results

Runs after each batch inside Step 3's loop (not as a separate post-loop
phase). Mechanical persistence of the batch's subagent JSON returns:

- **Validate the whole batch before any write.** Run
  `python3 skills/vault-ingress/scripts/validate-returns.py batch-returns.json`.
  Stop on a non-zero exit and repair the named return. The validator enforces the
  terminal status, return field types, catalog ID and polarity, observability,
  confidence and evidence, score arithmetic, co-presenter shape, language code,
  all catalog-feedback lanes, source-gated `not_evaluable` coverage, and the
  schema-v3 video-artifact trust boundary. For `video_extracted`, the enum alone
  never creates `static_slides`: that source exists only when the complete manifest
  proves a verified manual `slide_region`. `status: "processed"` additionally
  requires its promoted `slides_local_path`. Both writers import this same validator,
  so bypassing the standalone command cannot weaken the boundary.
  For newly emitted work, exit 0 is necessary but not sufficient: every
  processed entry in `pattern_scoring_generations` must report
  `status: current`. `legacy_unbaselineable` exists only so saved v1/v2 artifacts remain
  replayable and must be repaired before accepting new analysis.
  A v3 analysis additionally obeys its claim-bound adherence gate: below 10
  baseline talks means exact empty prose and no comparison; at 10+ it means one
  exact structured comparison against the immutable claim snapshot.
- **Update tracking DB — deterministic merge, NOT hand-mapping.** Collect the
  batch's subagent JSON returns into an array file (`batch-returns.json`) and run
  `python3 skills/vault-ingress/scripts/persist-results.py {vault_root}/tracking-database.json batch-returns.json`.
  The script first requires the return filenames to equal every live member of one
  run/batch claim; partial, extra, mixed-identity, duplicate, closed, or stranded
  batches fail before migration or merge. It then merges each return into its matching
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
  Version-2 and version-3 returns snapshot-replace every supplied declared
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
  fingerprint and scoring-schema version. Replayable v1/v2 returns that cannot
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
  deletes claim history. Claim v3 closes as v3, claim v2 closes as v2, and an
  active v1 lease upgrades to v2. Every completed v2/v3 claim stores a canonical
  SHA-256 receipt of the exact return payload; a receiptless completed v1 claim
  cannot authorize analysis replacement. Unknown future claim versions fail
  closed. An
  interrupted batch is recovered with
  `queue-state.py ... recover --now <ISO> --stale-after-seconds <N>`, not by
  replaying whichever old return files happen to exist.
  Future talk-record schemas are rejected before migration so this writer never
  stamps a newer record down to its current version. Pass the canonical tracking
  DB path: queue and persistence tools reject a final-component symlink before
  opening it, preventing atomic replacement from splitting the link and target.
- **Write per-talk analysis files — run the script, do NOT hand-write them.** Run
  `python3 skills/vault-ingress/scripts/write-analysis.py batch-returns.json {vault_root}/analyses --talks {vault_root}/tracking-database.json`
  over the SAME `batch-returns.json` the merge consumed, so the DB and the files
  cannot diverge. The writer verifies each completed claim's payload receipt and
  persisted catalog fingerprint/scoring version, requires exact membership
  across the completed batch, validates the persisted effective v2 analysis, and
  renders analysis-owned fields from that canonical talk state. Thus fields
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
  Non-empty adherence prose from a legacy v1/v2 return is preserved only as
  archival text under an unmistakable `legacy-unverified` label. It is never a
  current numeric comparison, Section 15 aggregate, or profile input.
- **Aggregate catalog feedback — after the final batch, do not hand-harvest or
  auto-edit the catalog.** Run the read-only intake over every return file or
  return directory:
  `python3 skills/vault-ingress/scripts/aggregate-catalog-feedback.py {return_paths}`.
  Review the stable JSON's invalid entries, exact-ID recurrence, normalized
  suggestions, and polarity warnings with the speaker. Recurrence is evidence
  for review, never authorization to change a catalog file. The five lanes and
  report contract live in
  [references/catalog-feedback-intake.md](references/catalog-feedback-intake.md).

Proceed immediately to Step 5.

## Step 5 — Update Rhetoric Summary

Still per-batch (continues Step 3's loop). The summary update is a separate
step from Step 4's persistence because it requires a speaker-review gate —
unlike DB writes, edits to `rhetoric-style-summary.md` change the speaker's
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
Run `python3 skills/vault-ingress/scripts/pptx-extraction.py <path.pptx>` for each file.
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
with the updated tracking database. Report the diff of changes (added fields,
changed values) so the speaker can verify.

If the profile doesn't exist, skip this step silently.

Proceed immediately to Step 8.

## Step 8 — Verify Improvement Goals

If the tracking DB has no `improvement_goals` in a verifiable state (none whose
`status` is outside `achieved`/`retired`), skip this step silently. Otherwise, with the
post-batch full-cohort pattern baseline current, pass the complete active-goal array
and that structured baseline to:

```bash
python3 skills/vault-clarification/scripts/goal_generation_provenance.py \
  < goal-generation-input.json
```

The input object contains `goals` and `current_pattern_baseline`; stdout is one
schema-v1 assessment per goal. Exit 1 is a malformed owner record or baseline:
stop without changing any goal. Only a `comparable` assessment authorizes metric
calculation. Record `needs_rebaseline` for a pattern-generation mismatch and
`unverifiable` for a missing current baseline or legacy pattern goal; preserve its
`current_value` and do not assign an outcome status. Pacing and independent goals
remain comparable through their separate provenance lanes. The full write rubric
is in [references/processing-rules.md](references/processing-rules.md) Improvement
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
requires a remote acquisition path and no local transcript/PPTX/PDF reference;
`skipped_duplicate` requires a bound duplicate `source_relation` target.

## Important Notes

- Create `transcripts/`, `slides/`, `analyses/` dirs if missing.
- Re-read tracking DB before writing (single source of truth).
- Preserve all summary content — add/refine, never delete.
- After 10+ talks in the claim's immutable scored cohort, a v3 worker produces
  a structured comparison and 2–4 sentence assessment against that claim
  baseline — never against a reparsed Section 15 narrative. Definition in
  [references/processing-rules.md](references/processing-rules.md) Adherence Assessment.

For input-quality edge cases that require non-default handling — wide-angle
room recordings, Whisper hallucination on bad audio, non-speaker talks
slipping into playlists — see
[references/known-issues.md](references/known-issues.md).
