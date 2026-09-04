# Queue Selection and Claim Lifecycle

This is the complete normative Step 2 contract for `vault-ingress`. Execute
normalization before claiming, and preserve every generation, freshness, replay,
and recovery rule below.

Fresh queue work uses claim schema v7. Before changing any talk status,
`queue-state.py claim` snapshots one immutable `adherence_baseline` for the
entire selected batch, stamps `required_return_schema_version: 7`, and copies
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
  list. Every fresh claim is schema v7 and requires return schema v7. Never
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
- Set `slide_source` per the PPTX → PDF → video extraction → none hierarchy in `SKILL.md`. Mark `"skipped_no_sources"` only if
  preflight confirms that transcript, slide, and video sources are all unavailable.
- If `$ARGUMENTS` specifies a talk filename or title, process ONLY that one.
