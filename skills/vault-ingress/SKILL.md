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
user-invocable: true
---

# Vault Ingress — Incremental Talk Parser

Process steps in order. Do not skip ahead.

Each step's output (tracking DB state, batch results, per-talk artifacts) feeds the next.

Resolve the absolute path of this loaded `SKILL.md`, then set
`speaker_toolkit_root` to the plugin root two directories above the directory
containing this file. Never derive it from the consumer working directory.
Treat `{speaker_toolkit_root}` as absolute in every toolkit-owned command;
vault and source-artifact paths remain consumer-owned.

Build a rhetoric and style knowledge base by analyzing presentation talks. Each run
processes **unprocessed** talks, extracts rhetoric/style observations, and updates the
running summary. The vault lives at `~/.claude/rhetoric-knowledge-vault/` (may be a
symlink to a custom location). All paths are relative to this **vault root**.

## Quick Reference

| Step | Required outcome |
|---:|---|
| 1 | Bootstrap/migrate, discover sources, and clear catalog/source preflight gates |
| 2 | Normalize the queue and claim one exact versioned batch |
| 3 | Run up to five per-talk workers in parallel |
| 4 | Validate, persist, render, and aggregate feedback transactionally |
| 5 | Apply speaker-approved narrative updates and write policy-bound Section 15 v3 |
| 6 | Finish pending PPTX visual evidence |
| 7 | Regenerate an existing speaker profile |
| 8 | Verify active improvement goals against current provenance |
| 9 | Hand fresh findings to clarification using the delivery-recency policy |
| 10 | Offer opt-in contribution of new visually evidenced styles |

## Key Files & References

| File / Reference | Purpose |
|------------------|---------|
| `tracking-database.json` | Source of truth — talks, status, config, confirmed intents |
| `rhetoric-style-summary.md` | Running rhetoric & style narrative |
| `slide-design-spec.md` | Visual design rules from PDF + PPTX analysis |
| [references/schemas-db.md](references/schemas-db.md) | DB + subagent schemas; extraction output schemas |
| [references/bootstrap-and-preflight.md](references/bootstrap-and-preflight.md) | Step 1 vault bootstrap, runtime, discovery, and preflight workflow |
| [references/batch-persistence.md](references/batch-persistence.md) | Step 4 validation, persistence, rendering, and feedback sequence |
| [references/queue-selection.md](references/queue-selection.md) | Step 2 normalization, claims, freshness, replay, and recovery contract |
| [references/pptx-followup.md](references/pptx-followup.md) | Step 6 bounded PPTX follow-up and visual-evidence contract |
| [references/clarification-handoff.md](references/clarification-handoff.md) | Step 9 topic selection and recency-bucket handoff contract |
| [references/rhetoric-dimensions.md](references/rhetoric-dimensions.md) | 14 analysis dimensions |
| [references/subagent-instructions.md](references/subagent-instructions.md) | Step 3 per-talk procedure — transcript download, slide acquisition, fallback chains, return-JSON shape |
| [references/video-slide-extraction.md](references/video-slide-extraction.md) | Video-to-slides pipeline — layout heuristics, tuning, limitations |
| [references/crop-review.md](references/crop-review.md) | Reproducible contact sheets, individual-frame proposals, and owner crop approval |
| [references/markdown-decks.md](references/markdown-decks.md) | Slidev/presenterm/Marp/reveal-md decks — render lanes, register-and-requeue, reveal structure |
| [references/source-identity-preflight.md](references/source-identity-preflight.md) | Offline identity, duplicate-source, enum, and artifact integrity contracts |
| [references/source-identity-audit.md](references/source-identity-audit.md) | Networked, read-only capture of live provider identity evidence and review findings |
| [references/catalog-feedback-intake.md](references/catalog-feedback-intake.md) | Five-lane catalog-feedback schema, polarity, recurrence, and review contract |
| [references/pattern-catalog-contract.md](references/pattern-catalog-contract.md) | Read-only catalog graph, polarity, source-gate, and semantic-debt contract |
| [references/processing-rules.md](references/processing-rules.md) | Language policy, pattern migration logic, structured field rules |
| [references/known-issues.md](references/known-issues.md) | Edge cases — wide-angle recordings, Whisper hallucination, non-speaker talks |
| [references/entrypoint-failure-contracts.md](references/entrypoint-failure-contracts.md) | Per-script stdout, stderr, exit-code, and commit-position contract on failure |

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
3. a markdown deck (Slidev, presenterm, Marp, reveal-md) — render it to
   `slides/{talk}.pdf` and register it as a normal PDF source, per
   [references/markdown-decks.md](references/markdown-decks.md)
4. `video_url` — extract slides from the video using ffmpeg + perceptual dedup
5. none — transcript-only analysis (`processed_partial`)

The `slide_source` field tracks which path: `"pptx"`, `"pdf"`, `"both"`,
`"video_extracted"`, `"markdown"` (a Slidev/presenterm/Marp deck — provenance
only, it yields no slide evidence until rendered to PDF and re-registered as
`"pdf"`), or `"none"`. The top-level `markdown_decks` collection names the file
that deck was authored in and outlives the re-registration, so a changed deck
re-renders without being located again. The `pptx_catalog` array fuzzy-matches
`.pptx` files to shownotes entries.

## Step 1 — Bootstrap Vault State

Execute [Bootstrap and Preflight](references/bootstrap-and-preflight.md) in full.
Do not select work until migration succeeds, the catalog is structurally valid,
and offline preflight has no blocking finding. Before preflight may inspect any
preserved local recording declared by
`structured_data.video_extraction.source_video_path`, `video_local_path`, or
`video_path`, require:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/check-runtime.py" \
  --lanes core,source-video --require-lanes core,source-video
```

Never pre-open, hash, hydrate, or call `ffprobe` directly. Video failure disables
only video evidence; retain independent transcript/PDF/PPTX evidence. Then read
the summary/spec and report processed, remaining, cataloged, matched, and
extracted counts.

## Step 2 — Select Talks to Process

Follow [Queue Selection](references/queue-selection.md) in full. Normalize once:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/queue-state.py" \
  "{vault_root}/tracking-database.json" normalize
```

Then claim each exact batch:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/queue-state.py" \
  "{vault_root}/tracking-database.json" claim --run-id <stable-run> \
  --batch-id <stable-batch> --now <timezone-aware-ISO>
```

Fresh claims are schema v7 and require return v7. A v7 return carries the v6
weighted score contract plus `provider_auto` transcript provenance. Use the stored claim on replay;
recover a stranded lease and issue a new generation. Set the best verified slide
source, use `skipped_no_sources` only when every source is unavailable, and honor
an explicit filename/title argument as a one-talk selection.

## Step 3 — Process Talks via Parallel Subagents (Batches of 5)

Launch up to five claimed talks in parallel, then complete Steps 4 and 5 before
the next batch. Each worker must execute
[Per-Talk Subagent Instructions](references/subagent-instructions.md), A → B →
B2 → C, against its claim and current summary.

The claim fixes the return schema and immutable numeric baseline. Workers must
not parse Section 15 for numeric adherence or return engine-owned enrichment;
they return only observed analysis, raw inspection coverage, and citations.

## Step 4 — Persist Subagent Results

If any batch return declares a preserved local recording through
`structured_data.video_extraction.source_video_path`, `video_local_path`, or
`video_path`, first require the same `core,source-video` runtime gate from Step
1. One successful check gates validation, persistence, and analysis rendering
for that exact batch.

Then execute [Batch Persistence](references/batch-persistence.md) in order:

1. Validate the complete claimed batch.
2. Persist it atomically; never hand-map fields.
3. Render analyses from the same returns and persisted effective state.
4. After the final batch, aggregate catalog feedback without editing the catalog.

Any failure stops the sequence. A successful merge closes the lease and emits
the complete post-batch baseline. Proceed immediately to Step 5.

## Step 5 — Update Rhetoric Summary

Present `summary_updates` and `new_patterns` as a section-by-section diff and
apply only speaker-approved changes (unless this batch was pre-authorized).
Follow the [Rhetoric Summary contract](references/processing-rules.md): rebuild
Section 15 only after the complete batch persists, never from a date cohort or
partial merge, and recount the database rather than incrementing totals. Its reader
accepts legacy occurrence-only v2 blocks, but every replacement writes v3 with the
schema-v5 profile's self-contained policy stamp and deterministic classifications.

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-profile/scripts/section15_pattern_history.py" replace \
  {vault_root}/rhetoric-style-summary.md pattern-profile-candidate.json \
  {vault_root}/tracking-database.json
```

A stale candidate, invalid optional policy override, or nonzero exit makes no write;
absence of an override automatically selects bundled `speaker-toolkit-default@1`.
This step re-analyzes persisted outcomes without reparsing talks or changing raw
tracking/opportunity rows. Report the batch outcome, then continue the loop or proceed
to Step 6.

## Step 6 — Extract Remaining PPTX Visual Data

Follow [PPTX Follow-up](references/pptx-followup.md). Run one bounded directory
extraction — that invocation walks every eligible deck and takes no include
list. `classify-pptx-evidence.py` decides what to do with the results: persist a
new receipt only for the records it reports `needs_extraction`, and leave a
`current` record's receipt untouched. Never decide from `visual_extracted`
alone; a stale, legacy, or unverifiable record can carry `visual_extracted:
true` and still need one. See
[Bootstrap and Preflight](references/bootstrap-and-preflight.md).

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/pptx-extraction.py" \
  --directory "{pptx_source_dir}" {template_skip_arguments} \
  {directory_exclusion_arguments}
```

Reuse both exact config-derived argument sets from Step 1. Safely extracted deck
results in a partial schema-v1 directory envelope remain usable, but only
`complete: true` authorizes a full-catalog or missing-deck conclusion. Use only
current schema-v4, artifact-bound deck evidence and the reference's matching,
rendered-page, OCR, and cross-talk rules. Proceed to Step 7.

## Step 7 — Regenerate Speaker Profile

If `{vault_root}/speaker-profile.json` exists, invoke `Skill(skill: "vault-profile")`
with the updated tracking database plus the resolved `{vault_root}` and exact
database-configured `{python_path}` as handoff context. The profile skill re-reads
the database and rejects a missing or mismatched interpreter; never let the handoff
fall back to `python3` on `PATH`. It writes speaker-profile schema v5 by classifying the existing raw
outcomes; this does not reparse talks. Speaker-profile schema versions are independent of the return, claim, and talk schema versions. Report the diff of changes (added fields,
changed values) so the speaker can verify.

If the profile doesn't exist, skip this step silently.

Proceed immediately to Step 8.

## Step 8 — Verify Improvement Goals

Skip when no goal is active. Otherwise follow
[Improvement Goal Verification](references/processing-rules.md#improvement-goal-verification)
using every active goal and the current full-cohort baseline:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-clarification/scripts/goal_generation_provenance.py" \
  < goal-generation-input.json
```

Require one valid assessment per goal before one expectation-bound transaction,
then re-read and report comparable, rebaseline, and unverifiable outcomes.
Proceed to Step 9.

## Step 9 — Same-Week Clarification Trigger

If no talk was processed, finish. Otherwise compute candidate topics and follow
[Clarification Handoff](references/clarification-handoff.md).

- **≤7 days:** offer to run `Skill(skill: "vault-clarification")` inline; on
  acceptance, invoke it with the candidate topics as handoff context.
- **7–30 days:** recommend the full session with topics; do not auto-invoke.
- **30+ days:** recommend the compressed session; do not auto-invoke.

After any clarification interaction finishes, proceed immediately to Step 10.

## Step 10 — Offer Style Contribution

For a newly discovered, visually evidenced reusable style, follow
[skills/illustrations/references/style-catalog.md](../illustrations/references/style-catalog.md#discoveries-and-opt-in-contribution).
Offer contribution as one separate question; never upload automatically.
If no new reusable style was observed, finish silently. Otherwise finish after
the contribution decision and any explicitly approved submission.

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
- Classification availability is per domain. Use each domain and row's explicit
  status/reasons; never let an unavailable trend or mode erase available mastery,
  recurrence, underuse, or combination classifications.

For input-quality edge cases that require non-default handling — wide-angle
room recordings, Whisper hallucination on bad audio, non-speaker talks
slipping into playlists — see
[references/known-issues.md](references/known-issues.md).
