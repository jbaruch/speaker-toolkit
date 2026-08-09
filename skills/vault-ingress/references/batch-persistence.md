# Batch Persistence

This is the complete normative Step 4 contract for `vault-ingress`. Run the
validation, database merge, analysis rendering, and final feedback intake in the
declared order. A failed operation never authorizes the next one.

Runs after each batch inside Step 3's loop (not as a separate post-loop
phase). Mechanical persistence of the batch's subagent JSON returns:

Before validation, inspect only the return declarations. If any return declares
a preserved local recording through
`structured_data.video_extraction.source_video_path`, `video_local_path`, or
`video_path`, require the configured runtime once for this exact batch:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/check-runtime.py" \
  --lanes core,source-video --require-lanes core,source-video
```

That success gates validation, persistence, and analysis rendering for the
batch. Do not pre-open, hash, hydrate, or invoke `ffprobe` directly to decide
whether to run the gate.

- **Validate the whole batch before any write.** Run
  `"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/validate-returns.py" batch-returns.json`.
  The command accepts one return object, an array, a directory of JSON returns,
  or multiple such inputs. Exit 0 emits one structured JSON validation report on
  stdout and authorizes the next step; exit 1 emits concise diagnostics on stderr,
  authorizes no write, and requires repairing the named return before rerunning.
  Exit 2 means the validator itself failed and the batch is UNVALIDATED, not
  invalid — see
  [Entrypoint Failure Contracts](entrypoint-failure-contracts.md).
  The complete field, catalog, source, evidence, scoring, and artifact predicates
  are owned by `skills/vault-ingress/scripts/validate-returns.py` (top-of-file
  input/output/exit contract) and
  `skills/vault-ingress/scripts/return_validation.py` (shared validator). Both
  persistence writers import that validator; do not restate, infer, or bypass its
  internal predicates and allowlists here. Reports may surface stable machine
  reason codes such as `source_gate_pending_owner_review`; their triggering
  predicates remain script-owned.
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
  On exit 2 read the stderr document's `database_written` before retrying — it
  states whether the atomic commit landed. See
  [Entrypoint Failure Contracts](entrypoint-failure-contracts.md).
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
  On exit 2 read the stderr document's `analyses_written` before retrying — it
  states whether the batch committed. See
  [Entrypoint Failure Contracts](entrypoint-failure-contracts.md).
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
  [catalog-feedback-intake.md](catalog-feedback-intake.md); exit 3 means the
  aggregator failed and no feedback was harvested, per
  [Entrypoint Failure Contracts](entrypoint-failure-contracts.md).
