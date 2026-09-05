# Family-Balanced Speech Calibration

Owner: `vault-profile`. `speech_cohort.py` selects catalog declarations;
`speech_calibration.py` owns the separate schema-v2 calibration profile. It
does not restamp schema-v1 equal-sample profiles, change `speaker-profile.json`
schema v5, or reparse talks. Fresh sampled word evidence comes exclusively from
the ingress media owner; captions and segment-only receipts are not inputs.

## Repeatable Command

Use the parent skill's strict-owner bootstrap and exact configured interpreter.
Pass its resolved vault root and explicit speaker identity and language:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-profile/scripts/calibrate-speech.py" \
  "{vault_root}" --speaker "{speaker_name}" --language en
```

This defaults to metadata-only planning, including a core-runtime check. It does
not open recordings or call providers. To acquire and measure, add `--run`;
add `--allow-download` only when YouTube downloads are authorized. Local declared
recordings remain preferred and a failed declared local source is not silently
replaced by captions or another recording. `--maximum-recordings` bounds the
selected cohort. Repeat `--demo-mode` for explicitly confirmed catalog mode IDs.
`--as-of` accepts an explicit timezone-aware observation timestamp for replay.

The script requires `core,source-media,speech-calibration` for `--run`, plus
`youtube-download` when enabled. `check-runtime.py` owns the lane requirements.
Missing configured runtime is a global refusal, never a fallback interpreter or
automatic installation. Global model/dependency and scratch-cleanup failures
abort without a candidate; source-specific acquisition failures remain exclusions.

Stdout is one `{schema_version: 1, ok, data|error}` envelope. Successful `data`
has `schema_version: 1`, `status`, `catalog_sha256`, `cohort`, `runtime`, and
`profile`. Plan status is `plan_only` with null profile. A completed measured
run has `calibrated` or `low_confidence` and a schema-v2 profile. `ok: true`
means the command completed, not that its evidence supports confident planning.
Retain the complete private report, including cohort exclusions and source
locators, alongside any profile candidate. Progress diagnostics identify counts
and closed reason codes, not transcript words or source paths. A segment/word
membership refusal also emits one stderr JSON record with `schema_version: 1`,
`code` and the ingress owner's closed numeric `word_timing` diagnostic. Exit codes and
resource bounds belong to the command's module contract.

The owner rereads the strict catalog before emitting a result. Any byte change
invalidates the run. The command writes no vault artifacts; capture output only
to a fresh private candidate and never redirect over a prior profile. Preserve
existing transcripts, catalog state, queues and profiles throughout calibration.

## Selection and Scope

`plan_cohort(database, speaker, *, language, maximum_recordings=12,
allow_download=False, demo_modes=())` accepts an ingress-owner-read database
snapshot. The speaker must match `config.speaker_name`. Structured family,
delivery mode, language and explicit solo-presenter declarations determine
eligibility. Missing declarations remain exclusions, not inferred facts.
Presentation-family IDs normalize whitespace and case, not title semantics.

The schema-v1 plan retains its method version, speaker, language, options,
ordered selected recording IDs and every catalog recording. Each recording
has `schema_version: 1`, `recording_id`, `family`, `family_label`, `mode`,
`language`, `year`, `youtube_id`, `source`, `status`, and `reasons`.
Source is null or `{kind: "local_media", locator}` / `{kind: "youtube", video_id}`.
Its shape belongs to the enclosing recording's version. A selected local
locator is a declaration, not proof that the file is available. Source probing,
duration, exact-byte identity and source-generation freshness belong to ingress.

Explicit same-recording relationships prevent repeated selection. Conflicting
families, unresolved duplicate identities, and multi-speaker declarations in
otherwise excluded duplicates block that identity. Selection balances families,
then prefers local sources and less-represented years and modes. Downloads
require explicit opt-in. Budget exclusions remain visible. A cohort is not a
random population sample; broad coverage does not remove catalog-selection bias.

`sample_window()` chooses a substantial interior interval from the media owner's
measured duration. Its constants own interval and source bounds. Unknown or
short durations refuse. Interior placement avoids recording edges; it does
not prove absence of audience Q&A, music or another voice. No diarization is
performed. Explicit multi-speaker talks are excluded as whole recordings.
Unverified mixed-speaker samples must not be promoted to speaker-only evidence.
Demo/tutorial subsets require explicit catalog mode IDs; no mode is guessed
from a title or assumed to mean demo.

## Schema-v2 Request and Profile

`speech_calibration.calibrate(request)` is pure arithmetic with no I/O. The
closed request has exactly:

```text
{schema_version: 2, speaker, language, catalog_sha256, generated_at,
 demo_modes: [mode_id, ...], samples: [sample, ...], exclusions: [exclusion, ...]}
sample = {schema_version: 1, recording_id, family, mode, year: integer|null,
          words: <ingress sampled-word receipt v2>}
exclusion = {schema_version: 1, recording_id, reasons: [closed_reason_code, ...]}
```

`catalog_sha256` identifies the exact strict-reader snapshot; `generated_at`
is an explicit timezone-aware observation time. Recording IDs occur once across
samples and acquisition/selection exclusions. Bounds are code-owned. Malformed
receipts fail the request rather than being repaired. Family IDs must already
be normalized by the cohort owner. The input is retained unchanged apart from
canonical ordering of samples, exclusions and demo IDs.

The closed profile has exactly:

```text
{schema_version: 2, method_version, calibration, calibration_sha256,
 quality_policy, confidence_policy, bootstrap, recordings, exclusions,
 summary, by_mode, demo_subset, scope}
```

`calibration` is the complete request, including rejected transcription evidence.
`calibration_sha256` is the owner's canonical JSON digest, not an authentication
claim. Each admitted `recordings` row has `schema_version: 1`, `recording_id`,
`family`, `year`, `mode`, `language`, `source_sha256`, `sample_sha256`,
`sample_start_seconds`, `sample_duration_seconds`, `evidence_sha256`, `word_count`,
`values`, and `denominators`. The last two maps retain all four named metrics.
Acquisition and quality exclusions share the explicit exclusion shape above.

`summary` has `schema_version: 1`, recording/family counts, analyzed and narration
durations, year/mode coverage, confidence, families and metrics. Each family row
has `schema_version: 1`, `family`, `recording_ids`, and four equally weighted
recording `means`. Each metric has `schema_version: 1`, unit, pause threshold,
family-balanced mean, family median, family standard deviation, family-mean
range, observed-recording range, 95% mean confidence interval and conservative
planning WPM. `speech_calibration.py` owns their exact key names and recomputation.
`by_mode` maps mode IDs to the same summary shape. `demo_subset` retains explicit
classification, mode IDs and a summary; an unclassified subset is not evidence
that there are no demos. The enclosing profile version covers these fixed maps.

## Quality and Uncertainty

The versioned `quality_policy` rejects insufficient lexical evidence, short
samples, low language/word confidence, excessive provider compression, poor log
probability, non-speech hallucination indicators, impossible local word rates
and repeated token blocks. Policy constants are not speaker-rate defaults.
Genuine slow delivery is retained, not removed as a statistical outlier.
The source-byte deduplication pass accepts at most one quality-passing sample
per source; conflicting source durations refuse, and conflicting families
exclude all samples for that digest.

All metrics reuse the word-gap definitions from [speech-rates.md](speech-rates.md).
The overall estimate weights each presentation family equally. Repeated
deliveries affect their family's estimate, not its weight. Both mean and median
are retained. `bootstrap` records schema, method, family-mean resampling unit,
fixed seed, replicate count and interpretation. Its percentile interval is
conditional uncertainty of the selected-family mean, **not** a future-recording
prediction interval. It does not account for alignment errors or selection bias.

The versioned confidence policy checks independent recordings, families,
analyzed duration, actual narration duration, years and modes. Unknown years
remain explicit. A homogeneous per-mode subset does not require multiple modes.
Empty/sparse evidence reports low confidence; missing point estimates or
intervals are null. Conservative planning rates remain null under low confidence.
The result never substitutes research averages, articulation, or a generic WPM.

## Persistence and Reader Contract

Only vault-profile may write a calibration profile. Keep retained words and
source locators private with the vault; never publish them in a plugin or issue.
Validate a fresh candidate with `speech_calibration.validate_profile()` before
publishing it. That reader recomputes every derived field and rejects tampering,
unknown fields and unsupported versions. Preserve the old profile on failure.
The shared `speech_rates.py calibrate` command also accepts the explicit v2
request above, enabling owner recomputation from retained word receipts. Supply
the request, not an old profile with edited derived fields. This arithmetic-only
command does not acquire media or establish freshness. Its output envelope has
the v2 profile in `data`; keep any replacement as a fresh private candidate.
Before acting on stored evidence, revalidate source and catalog freshness
through their owners; a matching internal digest alone is insufficient.

Schema-v1 equal-sample profiles cannot be automatically upgraded: they lack
family, speaker and quality evidence required by this method. Regenerate through
the owner from fresh word samples. Non-owner readers never migrate or rewrite.
The shared speech-rate reader, narration planner and creator outline/script
readers support both v1 and v2 read-only. The v2 selector refuses low-confidence
profiles and emits separate narration and conservative-planning fields; see
[speech-rates.md](speech-rates.md) for the closed planning shapes. Deploy these
readers before replacing a prior v1 profile. Recorder integration and human
acceptance remain separate from calibration: an outline planning adapter is not
an end-to-end screencast recorder. Recording verification remains based on actual full-recording
word timestamps and duration, never on any planning-rate field.
