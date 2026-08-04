# Processing Rules

## Language Policy — English Only

All analysis output, rhetoric summary updates, tracking DB entries, and profile data
MUST be written in English regardless of the talk's delivery language. For non-English talks:

- **Verbatim quotes**: ALWAYS write English translation FIRST, then the original in
  parentheses. Never the reverse. Format: `"English text" (оригинальный текст)`.
  Example: `"That's the whole point" (В этом весь смысл)` — NOT
  `"В этом весь смысл" (That's the whole point)`
- **Evidence-citation exception**: `evidence_citations[].quote` is the
  machine-verification field and MUST contain only the exact source-language span.
  Put its English rendering in `evidence_citations[].translation`; renderers show
  the translation first and label the original. Keep the human `evidence` summary
  in English.
- **Verbal signatures**: store separately tagged with language code (e.g.,
  `[ru] "получается что"`) — do NOT merge into the main English signature list
- **Slide text**: translate in the analysis, note original language
- **Humor/wordplay**: note when a joke is language-dependent and untranslatable
- Tag the talk entry with `delivery_language` in the tracking DB

## Pattern Taxonomy and Generation Recovery

Run `"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/queue-state.py"
<tracking-database.json> normalize` before claiming work. The command owns both legacy source-status
migration and pattern-generation recovery as one copy-on-write transaction. It
uses `partition_pattern_scoring_cohort` from
`skills/vault-ingress/scripts/adherence_baseline.py`; do not duplicate that
selection logic or approximate it with `processed_date`.

Every valid `processed`/`processed_partial` result excluded from the active
generation is moved to `needs-reprocessing`. The stored machine reason is
`pattern_scoring_generation:<reason-code>[+<reason-code>...]`, preserving the
selector's ordered codes, and the same codes and observed/expected generation
identity appear in the command's `normalizations` JSON. That gives every clean
consumer exclusion a deterministic queue path instead of leaving the current
cohort permanently empty.

Malformed or unknown generation identity, a current result with non-empty
generation reasons, incomplete current identity, and invalid or divergent
current score lanes reject the whole command with no DB write. Inflight,
pending, already-queued, and skipped records remain outside generation recovery.
Repeating normalization after a successful recovery is byte-stable. Existing
completed claim and history evidence is preserved; the next ordinary queue claim
archives the prior current claim under the normal generation transition.

## Pattern Tagging Rules

Scan observations against the pattern taxonomy index at
`skills/presentation-creator/references/patterns/_index.md` (path relative to plugin root).
Skip every pattern marked `observable: false`. These include hidden preparation,
provenance, decision, and post-event processes as well as behavior that the
available artifacts cannot establish. A polished outcome is not proof that a
named process produced it.

For every other entry, inspect `evaluable_from`, optional
`strong_evaluable_from` and `absence_evaluable_from`, the required-together
`not_applicable_when` / `applicability_evaluable_from` contract when present,
`evidence_requirements`, and `not_evaluable_when`. The allowed evidence-source values and
their limits are defined in the index's Evidence-Source Contract. A strong
detection uses `strong_evaluable_from` (defaulting to `evaluable_from`);
moderate and weak detections use `evaluable_from`. Only score an entry when an
available eligible source establishes its requirements. Every detected pattern
or antipattern must record concrete `evidence` and the qualifying
`evidence_source`. When that source is `source_comparison`, also return the
duplicate-free `evidence_sources_used` array. It must exactly equal one
qualifying all-of group, while the prose evidence names what was compared.

Return v4/v5 makes "inspected" an artifact-bound statement. Alongside the exact
`evidence_sources` set, return one closed raw `source_inspection` record per
underlying source:

- `transcript` uses one or more inclusive, ascending `line_ranges`.
- `static_slides` and `native_deck` use inclusive, ascending `page_ranges`.
- `delivery_video` uses ascending `[start, end]` second `time_ranges`, with
  `end > start`.
- Each distinct `source_comparison` group uses its duplicate-free
  `evidence_sources_used` plus `comparison_scope: "full"|"partial"`. Multiple
  comparison records are valid when their exact underlying groups differ.

Ranges may be adjacent but may not overlap. Coverage is complete only when the
verified artifact begins at line/page 1 (or video second 0), ends at its exact
verified bound, and has no gaps. A `full` comparison is complete only when all
of its members have complete coverage; a `partial` comparison never authorizes
an undetected outcome. The worker owns the raw ranges and scope. Persistence
owns the resolved counts/duration, `coverage_complete`, artifact identities,
and comparison identity bundle.

Each observable entry declares `evidence_channels`. Each detection returns a
non-empty `evidence_citations` array through one of those channels. Use the citation shapes in
[schemas-db.md](schemas-db.md) Pattern Evidence Citation Schema. The citation
must locate proof from the qualifying source: transcript evidence uses a
transcript locator, static/native slide evidence uses a slide or slide-sequence
locator, and delivery-video evidence uses a video interval. A
`source_comparison` detection supplies citations for every underlying member of
`evidence_sources_used`. Metadata may supplement a detection but cannot replace
the source/outcome gate. Timing, sequence, motion, and delivery claims use their
specific timed-transcript, slide-sequence, or video locators. Put hypotheses without allowed source-located proof in
clarification notes, not the score.

For an entry with no positive detection, use `absence_evaluable_from`
(defaulting to `evaluable_from`) to decide whether completely inspected sources
can support an undetected outcome. Return v4/v5 uses no prose waiver: every
`not_evaluable` item contains exactly `pattern_id` and `reason_code`. Use
`missing_required_source_coverage` when no effective absence group has complete
coverage. Use `absence_not_authorized_by_catalog` when an explicit
`absence_evaluable_from: null` makes the entry positive-only; this is intentional
catalog policy, not unfinished owner work. Use `source_gate_pending_owner_review`
only when the observable catalog entry has no owner-approved positive gate.
That pending entry fails closed: it cannot be detected by a v4/v5 return and
cannot be silently counted as absent. A
valid positive detection takes precedence for a gated entry; never add the same
ID to `not_evaluable`. Do not guess and do not interpret `not_evaluable` as
absence. Exclude not-evaluable entries from the score. Persistence recomputes
the exhaustive expected ID→reason map and rejects missing, extra, duplicate,
prose-bearing, or blanket waivers.

Return v5 additionally makes applicability exhaustive. For every nondetected
entry with `not_applicable_when`, first evaluate the complete
`applicability_evaluable_from` gate. Without complete canonical coverage, an
assessment is forbidden and the outcome is `not_evaluable` with
`missing_applicability_source_coverage`. With complete coverage, exactly one
`applicability_assessments` row is mandatory. It contains `pattern_id`,
`result`, `evidence_source`, nonempty `evidence`, source-located
`evidence_citations`, comparison-only `evidence_sources_used`, and a
catalog-authorized `condition_id` only for `not_applicable`. An `applicable`
assessment forbids `condition_id` and then proceeds through the ordinary
absence gate; there is no implicit applicable default.

Persistence owns the exhaustive v5 projection. It writes exactly one sorted
`pattern_outcomes` row per observable entry using precedence: detection;
validated applicability assessment; incomplete applicability/absence gate as
`not_evaluable`; applicable plus complete absence gate as `undetected`.
Outcomes are exactly `detected`, `undetected`, `not_evaluable`, or
`not_applicable`. The worker never returns this ledger. Persistence also hashes
scoring schema, catalog fingerprint, and sorted per-pattern opportunity state
into `opportunity_coverage_identity`; detected/undetected collapse to
`evaluable`, while the two unavailable states remain distinct.

This is exhaustive for source gates: every undetected observable catalog entry
for which no effective absence alternative is satisfied by complete, canonical
inspection coverage must be represented in `not_evaluable`. A singleton
alternative needs both complete ranges and absence-capable provenance. A `full`
source comparison remains positive evidence but cannot authorize absence or
applicability until a future canonical receipt proves aligned modality capture;
mere artifact coexistence is not comparison work. Artifact scope still controls
what counts as a source. In particular, an untrusted video
`full_frame_context` may support concrete `delivery_video` observations but never
creates `static_slides` or `native_deck` evidence.

A trusted schema-v3 video-extracted `slide_region` PDF is a positive-only static
source. Its identity-bound pages may support citations and detections, but the
sampling, transition filtering, and deduplication receipt does not prove that
every delivered visual state survived. Therefore even full inspection of that
PDF does not join the absence/applicability-complete source set. Bare
`native_deck` and `delivery_video` are positive-only for the same reason: page
ranges or full duration do not prove audience/screen/audio/session-boundary
capture. Native PPTX and rendered static pages are distinct too: PPTX inspection
establishes `native_deck`, never `static_slides`; a separately declared readable
PDF retains its own static identity and may be absence-complete.

Canonical inspection rows expose both facts. `coverage_complete` reports only
range coverage. Engine-owned `absence_capability_complete` separately gates
negative/applicability inference, and `absence_capability_reason` explains the
decision with a stable code such as `authorized_transcript`,
`authorized_rendered_static`, `nonexhaustive_video_extraction`,
`bare_native_deck`, `bare_delivery_video`, or
`comparison_alignment_unverified`.

`persist-results.py` validates catalog ID/type, bucket, uniqueness,
observability, source/outcome gate, channel, quote, slide range, declared
inspection coverage, and available artifact context before writing. Raw
transcript citations contain `source`, `channel`, `quote`, and optional
`translation`; raw slide citations add `slide_numbers`; raw video citations add
`start_seconds`/`end_seconds`; raw metadata citations add `field`. Workers do
not return transcript lines/timestamps, artifact roots/paths/hashes, metadata
`value`/`owner_value_after_return`, `coverage_complete`, derived counts/duration,
timing/quality receipt identities, comparison artifact identities, enriched
not-evaluable facts, or
`evidence_schema_version`. Those are engine-owned canonical fields. Catalog
dimensions are also engine-owned and should be omitted; a compatibility copy is
accepted only when it exactly matches catalog order.

## Transcript Quality and Timing Authority

Treat the readable transcript and its two receipts as three separate artifacts:

- `transcripts/<id>.txt` is the exact UTF-8 speech text.
- `transcripts/<id>.segments.json` schema v2 owns owner-bound acquisition
  source and optional timing.
- `transcripts/<id>.quality.json` owns the exact validation policy and the
  source of any duration that lowered the fixed short-artifact floor.

Both receipts carry SHA-256 of the exact `.txt` bytes. Verify against raw bytes,
not newline-normalized text: replacing CRLF with LF invalidates both even when
the decoded words are unchanged. Missing or rejected timing leaves ordinary
transcript quotation available but cannot support `timed_transcript`. Quality
is independent: a transcript with no timed segments can and must still carry a
current quality receipt before it enters v5 scoring.

The quality policy is exactly `{schema_version, min_words,
duration_seconds}`. A caller's `--min-words` may tighten the derived floor but
never lower it. With no trusted duration, the floor remains 400 words. A lower
short-talk floor derives only from `yt-dlp` provider duration for the exact
YouTube ID or `ffprobe` over exact local media, whose digest is stored in the
provenance. `--duration-seconds` is an expected value that must match that
source-owned probe; it is not authority itself. Return fields, analysis prose,
and unbound talk metadata never lower the floor.

Current v5 persistence requires a hash-current receipt with exact provenance.
For `youtube_duration`, the receipt video ID must equal the owning talk's
`youtube_id`. For `local_media_duration`, the stored media digest must equal the
exact owner-bound local media. A missing legacy receipt is unverified and must
be requeued through `fetch-transcript.py`; malformed, stale, wrong-owner, or
duration-drifted receipts fail closed. Never copy a policy or duration from a
worker return.

Timing schema v2 is closed and source-artifact-bound. YouTube captions/Whisper
require the exact owner video ID and trusted duration; local Whisper requires
the exact media digest and trusted duration; VTT requires a safe relative
regular-file path, exact artifact digest, and exact final cue extent. Joined
segment text must equal the transcript modulo Unicode whitespace layout, and
time ranges must fit the source bound. Legacy schema v1/minimal receipts are
archival: never infer missing ownership or migrate them by relabeling.

Caption timing enrichment for valid existing text is non-destructive. Pass the
owner's provenance via `--existing-source`; only known `youtube_auto` text may
acquire fetched caption segments, and only when caption text is identical after
Unicode-whitespace collapse. The script writes only the timing sidecar and never
relabels or overwrites manual, Whisper, unknown, or text-mismatched transcripts.

An existing transcript is validation-only unless `--force` explicitly
authorizes replacement. Tightening `--min-words` can reject it but never
licenses a provider overwrite. A caught bundle failure restores the prior
transcript and receipt bytes. On a fresh/forced fetch, invalid optional segment
timing degrades to unavailable and removes stale timing transactionally; valid
semantic text and its quality receipt still commit.

## Structured Field Extraction

The subagent's job is to **return** every structured field it identifies (co-presenter,
delivery language, slide counts, opening/closing types, etc.) in the `structured_data`
block per the return schema — never to leave them buried only in `rhetoric_notes` free
text. If it's in the analysis, it must be in `structured_data`.

Persisting those fields is deterministic and script-owned, not a manual per-run mapping —
SKILL.md Step 4 uses `{speaker_toolkit_root}/skills/vault-ingress/scripts/persist-results.py` for the merge. Authors do not re-derive
that logic here.

## Adherence Assessment

`adherence_assessment` measures how consistent a talk is with the speaker's
**established** rhetorical baseline — not whether the talk was good in the
abstract. Adherence is consistency with this speaker's own validated style, which
is why it can only be computed once a baseline exists.

**Authority:** for return schema v5, the claim baseline remains immutable, but
raw-score comparison also requires an exact matching canonical
`opportunity_coverage_identity`. The worker cannot author that engine-owned
identity. Therefore the exact empty adherence sentinel is always safe; any
owner-side structured comparison must prove identity equality. Workers MUST
NOT parse Section 15, infer a date cohort, or recompute an average from the live
DB. Every member of one batch carries the same snapshot.

**Worker gate:** return exact `adherence_assessment: ""` and omit
`adherence_comparison`. Canonical talk identity does not exist until owner-side
persistence, so a worker cannot prove the comparison predicate.

**Owner-side gate:** inspect baseline comparison status, identity, and counts exactly.

- `raw_score_comparison_status: unavailable`, a null identity, an identity
  mismatch, or fewer than 10 `scored_talk_count`: do not construct a comparison.
- A structured comparison is valid only when the canonical talk identity equals
  the baseline identity and the baseline contains at least 10 scored talks. It
  carries a value-for-value copy of the immutable baseline and the validated
  talk score.

`eligible_talk_count` remains the complete fresh generation cohort for
per-pattern opportunity denominators even when mixed identities suppress the
raw-score lane. `scored_talk_count` is only the exact one-identity score cohort.

This is a global, generation-bound comparison. The baseline includes only
`processed`/`processed_partial` talks stamped `current` with the exact catalog
fingerprint and pattern-scoring schema captured by the claim. An unscored talk
cannot be assessed, and a stale catalog/scoring generation requires recovery
and a fresh claim rather than reinterpretation.

**Three checks, in order:**
1. **Numeric anchor** — interpret the validated `pattern_score` against the
   claim baseline's `average_pattern_score` and `scored_talk_count`. The
   renderer generates this anchor mechanically from `adherence_comparison`; the
   worker's prose need not restate the numbers.
2. **Current-talk evidence** — interpret that difference using the patterns and
   antipatterns detected in this return. Name a detected antipattern when one
   materially explains the score; do not invent population frequency that the
   baseline schema does not carry.
3. **Departure classification** — use claim/talk context and confirmed intent,
   when present, to distinguish a deliberate mode, co-presenter, or venue choice
   from likely backsliding. Context may explain the number but cannot replace or
   modify the claim snapshot.

**Required interpretation:** the assessment explains the mechanically generated
anchor using current-talk evidence. Validators deliberately do not parse prose
for numeric agreement. If the prose happens to repeat a number, that number is
untrusted narrative; the structured comparison and renderer-generated anchor
remain authoritative.

**Bound:** 2–4 punctuation-terminated sentences of prose, not a second score. Enforcement is
deterministic: every `.`, `?`, or `!` punctuation cluster followed by whitespace
or end of text is one sentence boundary, including a period in an abbreviation;
the final sentence must be terminated. Spell out abbreviations that would create
a false boundary.

Non-empty adherence prose from a return v1–v4 artifact remains replayable only
as archival `legacy-unverified` text. It is never a verified numeric comparison,
never enters a current baseline or Section 15 aggregate, and is never profile
input.

## Rhetoric Summary — Improvement & Adherence Sections (15–16)

`rhetoric-style-summary.md` Sections 1–14 mirror the 14 analysis dimensions.
Sections 15–16 are cross-talk narratives. Rebuild Section 15 in Step 5 only
after the entire batch has persisted successfully; never update it after an
individual member merge.

### Section 15 — Improvement & Adherence Baseline

Section 15 is a human-readable account of the verified current cohort, not the
numeric authority for a worker. `persist-results.py` stdout supplies the
post-batch `current_adherence_baseline` only after every merge succeeds. That
adherence-baseline schema-v2 payload is all-inclusive (`active_batch_excluded: false`,
`excluded_filenames: []`). `eligible_talk_count` is the complete fresh-v5
candidate. `scored_talk_count`, sum, and ROUND_HALF_EVEN average describe only
one exact `opportunity_coverage_identity`; mixed identities make raw-score
comparison unavailable with zero/null score aggregates while retaining the
per-pattern opportunity cohort.

The independently versioned Section 15 current block has read-v2/write-v3
compatibility. A reader may validate an occurrence-only v2 block, but it must keep every
classification-derived claim unavailable: v2 has no policy identity and the existence
of a new default cannot retroactively classify it. Every replacement writes v3 and
embeds the complete validated schema-v5 `pattern_profile`, including the normalized
classification policy and its canonical semantic digest.

For every Section 15 current-block count, read only talks with status
`processed`/`processed_partial`, `pattern_scoring_generation_status: current`,
empty generation reasons, the exact current catalog fingerprint, and the exact
current pattern-scoring schema version. Never approximate this cohort by
`processed_date`. Exclude skipped, legacy-unbaselineable, stale-fingerprint,
stale-schema, and archival `legacy-unverified` adherence prose. The current
machine-readable block has three audit lanes:

1. **Occurrence rows** — copy the exhaustive `pattern_usage` and
   `antipattern_frequency` rows generated from v5 outcomes. Each row retains its
   own opportunity denominator; detected, evaluable, unevaluable, and not-applicable
   counts; coverage; and null-rate sentinel. The v3 writer copies these raw rows
   unchanged.
2. **Raw-score availability** — copy the global comparison status, exact
   opportunity identity, scored count, sum, and `average_pattern_score` from the
   post-batch baseline. Mixed identities or no evaluable opportunities keep this
   lane explicitly unavailable; do not calculate a trajectory or substitute the
   broader eligible count.
3. **Policy-derived history** — copy the classifier's self-contained policy stamp,
   per-domain availability, exhaustive positive and antipattern classification rows,
   trend audit, and derived projections. With no vault override, use bundled
   `speaker-toolkit-default@1` automatically; do not ask the speaker to choose
   thresholds. If `{vault_root}/pattern-classification-policy.json` exists, validate it
   strictly and abort on any error rather than falling back. Mastery/novelty,
   antipattern recurrence, underuse, combinations, trends, and modes are independently
   gated. Honor row-level bounds and absence capability: zero detections become
   `never_tried` or `confirmed_none` only when the catalog and complete-evaluation gates
   permit an absence conclusion.

Old recurring/signature/underuse/resolved prose may remain outside the delimited
block only when explicitly labeled historical or manually curated. It is
non-baseline narrative and must not be regenerated from occurrence rates or
consumed as current catalog classification.

Section 15 is the human-readable mirror of the profile's validated
`pattern_profile` occurrence, policy, classification, and audit lanes (see
[../../vault-profile/references/speaker-profile-schema.md](../../vault-profile/references/speaker-profile-schema.md));
keep the two consistent when both update. Profile generation must independently
apply the same exact current-generation filter; Section 15 prose and legacy
adherence text are not machine-readable numeric inputs.

After the complete post-batch narrative and `pattern_profile` candidate are
ready, run `"{python_path}" "{speaker_toolkit_root}/skills/vault-profile/scripts/section15_pattern_history.py" replace`
with the summary, candidate, and live `tracking-database.json`. The helper reads v2 or
v3, writes only v3, recomputes the full current cohort from the database, rejects stale
or policy-mismatched candidates, checks scoring-v5 artifact freshness against the vault
and configured source roots, and atomically replaces only the uniquely delimited
current block. Classification is a re-analysis of persisted outcomes: no talk is
reparsed, and neither tracking records nor raw opportunity rows are mutated. All prose
outside that block remains explicitly historical/non-baseline; ordinary Section 15
prose can never restore pattern-history authorization.
`section15_pattern_history.py replace` is the only supported current-block
replacement operation and must receive the live tracking database.
Recount status from the tracking database every time; never increment it
manually.

### Section 16 — Speaker-Confirmed Intent

Patterns the speaker confirmed as deliberate or accidental during a clarification
session (see vault-clarification). Read-only during ingress — populated by
clarification, consumed here as the intent-adherence input for Section 15.

## Improvement Goal Verification

Each ingress run, after the final Section 15 baseline is current, verifies the
speaker's active `improvement_goals` (set during clarification — record schema in
[../../vault-clarification/references/schemas-config.md](../../vault-clarification/references/schemas-config.md)).
This closes the loop: the system stops merely diagnosing and checks whether the
issue the speaker chose to work on actually moved.

Before calculating any metric, run
`"{python_path}" "{speaker_toolkit_root}/skills/vault-clarification/scripts/goal_generation_provenance.py"` with the complete
active-goal array and the structured post-batch full-cohort pattern baseline. The
script emits one assessment with a stable `decision` and `reason_codes` per goal;
exit 1 blocks all goal writes. Require exactly one assessment for every active
goal before constructing a mutation plan. It is the sole authority for generation
comparability—do not reproduce its fingerprint/schema predicate and never parse
Section 15 prose as its baseline.

- A `comparable` assessment authorizes the metric and outcome rubric below.
- A schema-v1 `antipattern` or `underuse` goal is historical, report-only
  `unverifiable`. Preserve the complete record and do not create a mutation for
  it.
- A schema-v1 `pacing` or `other` goal may remain comparable through its
  independent provenance lane. If comparable, patch only `current_value`,
  `last_checked`, `checked_by`, and `status`. Never add `verification_state` or
  `verification_reasons` to a schema-v1 record. A non-comparable assessment is
  report-only.
- For a schema-v2 `needs_rebaseline` or `unverifiable` assessment, copy the
  decision to `verification_state` and its codes to `verification_reasons`.
  In either case, preserve `current_value` and must not set `status` to
  `achieved`, `improving`, `stalled`, or `regressed`. A speaker-confirmed rebaseline is owned by
  vault-clarification; ingress never restamps the fixed baseline.
- Pacing and independent goals continue through their own provenance lanes and
  are not invalidated by a pattern-catalog generation change.

For each comparable goal with `status` not in (`achieved`, `retired`):
- Compute `current_value` for the goal's `metric` from the current Section 15
  cohort data — and, for `pacing` and mode-specific goals, from the freshly regenerated
  speaker profile. Freshness alone is not availability: require the matching
  `classification_availability` domain before using antipattern recurrence, underuse,
  trends, or `by_mode`; an unavailable domain yields an unverifiable/report-only result,
  not a zero. Examples by `kind`: `antipattern` → the antipattern's policy-classified
  frequency; `underuse` → the pattern's classification or available breadth trend;
  `pacing` → `pacing.adherence.over_budget_rate`.
  For schema v1, write only `current_value`, `last_checked` (today),
  `checked_by: "vault-ingress"`, and `status`. For schema v2, write those
  fields plus `verification_state: "current"` and empty
  `verification_reasons`.
- Set `status` by comparing `current_value` against `baseline_value` and `target`:
  - `achieved` — `current_value` meets or beats `target`.
  - `improving` — moved toward `target` versus `baseline_value` but not there yet.
  - `stalled` — no meaningful movement from `baseline_value`.
  - `regressed` — moved away from `target` (worse than `baseline_value`).
- Only count talks processed after `set_date` toward movement — a goal can't
  be judged on talks that predate it.
- Never overwrite `baseline_value`, `target`, `issue`, or `set_date` — those are the
  fixed yardstick; the verification writer changes only the schema-authorized
  verification and status fields above.

Use one `patch_improvement_goal_verification` mutation per writable assessment.
Each mutation's `expect` object must contain exactly the fields it sets with the
values from the latest strict read. If every assessment is report-only, do not
invoke the mutator. Otherwise dry-run the complete multi-goal plan, review it,
apply the whole plan against the reported input SHA, and re-read the database.
An assessment failure, malformed plan, stale expectation, or changed database
generation installs no partial goal update.

Report each goal's status in the run summary. A `regressed` or `stalled` goal is the
strongest signal to surface — it is the speaker's own priority, not a machine-chosen
one.
