# Speaking-Rate Contracts

Owner: `vault-profile`. Executable owner:
`skills/vault-profile/scripts/speech_rates.py`. This is an independent
versioned artifact lane, not a change to `speaker-profile.json` schema v5 or
the tracking database. No operation here acquires media, runs Whisper, or
reparses talks. Acquisition and source-generation verification remain the
ingress owner's responsibility.

The separate [family-balanced calibration contract](speech-calibration.md)
defines schema v2, catalog cohort selection, sampled-transcription quality and
bootstrap uncertainty. Schema v1 below remains the equal-sample arithmetic
contract; it cannot be relabeled as schema-v2 evidence. `calibrate()`, `validate_profile()`,
`validate_rate()` and `plan_duration()` accept both supported shapes read-only.

## Four Different Metrics

Every rate uses `unit: "words_per_minute"` and a named `metric`. Each emitted
record preserves its applied `pause_threshold_seconds`; measurement records
also expose `denominator_seconds`. The complete timeline/pause definitions
for `word-gaps-v1` are documented in the owner's module docstring and implemented
by `THRESHOLDS` and `_denominators` in
`skills/vault-profile/scripts/speech_rates.py`. Execute the owner rather than
recreating those calculations in prose or reader code.

| Metric label | Reporting and planning role |
|---|---|
| `timeline` | Describe the finished recording's complete timeline |
| `narration` | Plan long-form narration |
| `short_phrase` | Describe phrase/beat pace |
| `articulation` | Describe thresholded articulation, not end-to-end duration |

Articulation is an operational word-alignment metric, not a phonetic
voice-activity detector. Do not relabel it as narration. Preserve the method
version and applied threshold with every copied rate.

## Recorded Word Evidence

`measure` consumes this exact schema-v1 record. Every key is required:

```json
{
  "schema_version": 1,
  "timing_kind": "recorded_words",
  "source_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "source_duration_seconds": 50,
  "sample_start_seconds": 0,
  "sample_duration_seconds": 50,
  "aligner": "synthetic-example-v1",
  "words": [["Example", 1.0, 1.4], ["words", 1.6, 2.0]]
}
```

The example is synthetic, not a speaker calibration. Word times are relative
to the sample. Each tuple contains one nonempty whitespace-free lexical token
and its actual start/end seconds. Spans must be positive, ordered,
non-overlapping, and inside the sample; the sample must fit inside the
source's actual duration. A punctuation-only tuple is not a word. Preserve
the aligner's word-tokenization convention and record its name/version.

Use word timestamps and duration from the same unchanged recording generation.
The source digest must come from the acquisition owner's receipt. This tool
validates and carries that binding; it does not open the media or authenticate
a supplied digest. Recheck freshness through the acquisition owner before
acting on a stored snapshot. Do not substitute evenly divided segment times,
script estimates, or a predicted duration. Existing transcript timing sidecar
v2 contains segments, not word evidence, and is not accepted by this contract.

Bounds and diagnostic codes belong to the script's header and validators.
Missing/unknown fields, future or type-confused versions, duplicate JSON keys,
non-finite numbers, and invalid timing fail closed without echoing input data.

## Measured Profile and Persistence

`calibrate` consumes `{schema_version: 1, cohort: string, samples: [evidence, ...]}`.
Choose a cohort deliberately: speaker, delivery mode, language, and sample
selection should match the intended use. A sample count is not a count of
independent talks. Duplicate or overlapping windows from one source digest are
rejected; disjoint windows remain distinct samples. Do not present them as
independent deliveries. One source digest cannot declare two source durations.

The result is a closed profile:

```text
{schema_version: 1, calibration: <exact calibration request>, rates: [<rate>, ...]}
```

All four rates are retained. Each rate has exactly:

```text
{schema_version: 1, metric, unit, pause_threshold_seconds, value,
 range: [low, high], basis: "measured", provenance}
```

`value` is the equally weighted sample mean. `range` is the observed minimum
and maximum across sample rates, not a population interval. Provenance has:

```text
{schema_version: 1, sample_count, analyzed_duration_seconds, cohort,
 method_version: "word-gaps-v1", evidence_sha256: [digest, ...],
 range_kind: "observed_sample_range_not_confidence_interval"}
```

The evidence digest is SHA-256 of the owner's canonical JSON for the complete
word-evidence record. Consumers treat it as opaque, not an algorithm to
reimplement. The profile retains the source evidence for reproducibility;
keep it private with the vault, not in the public plugin or a public issue.
Small or biased cohorts remain small or biased even when validation succeeds.

Vault-profile alone creates or replaces `speech-rate-profile.json`. Run
`calibrate`, require exit 0 and `ok: true`, then store only its `data` object
unchanged in a fresh candidate file. Preserve the prior file until the new
candidate has validated; do not redirect a failing command over the prior
profile. Repeated identical calibration produces identical bytes with
`encode()`. No automatic migration is performed: regenerate legacy or unknown
profiles through this owner from recorded word evidence. Non-owner readers
call `validate_profile()`, which recomputes all derived rates/provenance from
the retained evidence and rejects any inconsistent present profile. They
never repair, restamp, or silently replace invalid state with a default.

## Planning and Verification

`plan_duration(word_count, *, intended_metric, profile=None, assumption=None)`
requires `intended_metric: "narration"`. Other named metrics and unqualified
numeric WPM are rejected. If a valid measured profile is supplied, its
narration rate wins over an assumption. A present invalid profile fails
instead of falling back. If no profile exists, explicitly supply an assumption;
there is no hidden universal speaker-rate default.

An assumed rate has the same rate keys, with `basis: "assumption"` and
`provenance: {schema_version: 1, reason: string}`. Its positive ordered range
must contain its point value. Library callers can construct one through
`assumed_narration(low, high, reason=...)`. Never attach measured provenance
to an assumption. With a v1 rate, `plan_duration` emits a schema-v1 prediction containing the
selected complete rate, intended metric, word count, point duration, and
inverted duration range, labeled `kind: "prediction_not_verification"`.

With a v2 family-balanced profile, the owner validates the complete retained
evidence and requires conditional confidence before selecting narration. A
present sparse profile is rejected with `pace_confidence_insufficient`, even
when an assumption is also supplied. No mean from a single recording becomes
a planning default. The v2 output adds `conservative_estimated_seconds` and
`range_kind: "observed_recording_range_not_prediction_interval"` to the same
prediction fields and carries `schema_version: 2`. The point duration uses
the family-balanced mean; the conservative duration uses the lower mean-CI
rate. The duration range inverts historical recording rates, not the mean CI.
Neither duration is a fit guarantee or substitutes for actual recording checks.

`speech_calibration.narration_rate(profile)` returns this closed copied rate:

```text
{schema_version: 2, metric: "narration", unit: "words_per_minute",
 pause_threshold_seconds: 2.0, value: <family-balanced mean>,
 range: <observed recording range>, basis: "measured",
 mean_confidence_interval_95: [low, high], conservative_planning_wpm: <CI low>,
 provenance: {schema_version: 2, sample_count, presentation_family_count,
   analyzed_duration_seconds, cohort: <speaker>, language, method_version,
   evidence_sha256: [digest, ...], calibration_sha256,
   range_kind: "observed_recording_range_not_prediction_interval",
   confidence_level: "conditional",
   interval_kind: "mean_uncertainty_conditional_on_selected_families_not_a_prediction_interval"}}
```

The rate retains distinct mean, observed range and conditional mean uncertainty.
The method version is `family-balanced-word-gaps-v2`. Its calibration digest
binds the complete owner request; evidence digests identify admitted recordings.
This selector uses the overall cohort, not an implicitly inferred demo subset.
An embedded rate is structurally checked but cannot independently authenticate
the raw evidence: obtain it from a freshly owner-validated full profile.

`verify_recording(evidence, *, maximum_duration_seconds)` has no planning-rate
input. It requires word evidence covering the complete recording, not an
interior calibration window. Its schema-v1 result carries
`kind: "recorded_duration_check"`, the explicit maximum duration,
`fits_duration`, and the actual measurement with all four rates. The comparison
uses actual recording duration, including pauses; changing a planning WPM
cannot change the verdict. This is a duration check, not proof of script
completeness, alignment accuracy, or delivery quality.

`measure` returns a schema-v1 record with `method_version`, `evidence_sha256`,
`source_sha256`, `word_count`, `actual_duration_seconds`, and four rate records.
Each measurement rate has `schema_version`, `metric`, `unit`,
`pause_threshold_seconds`, `denominator_seconds`, and `value`.

## Command Contract

Use the configured vault interpreter resolved by the parent skill. Each action
reads one JSON document from stdin and emits one JSON envelope. The executable
does not write files or mutate the vault.

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-profile/scripts/speech_rates.py" measure < word-evidence.json
"{python_path}" "{speaker_toolkit_root}/skills/vault-profile/scripts/speech_rates.py" calibrate < calibration-request.json
"{python_path}" "{speaker_toolkit_root}/skills/vault-profile/scripts/speech_rates.py" plan < planning-request.json
"{python_path}" "{speaker_toolkit_root}/skills/vault-profile/scripts/speech_rates.py" verify < verification-request.json
```

Plan request: `{schema_version: 1, word_count, intended_metric: "narration",
profile: <complete validated profile or null>, assumption: <assumed rate or null>}`.
Verification request: `{schema_version: 1, evidence: <complete recording word
evidence>, maximum_duration_seconds}`. Extra fields, including a planning WPM
in a verification request, are rejected. Success is
`{schema_version: 1, ok: true, data: <action result>}` with exit 0. Failures
have `ok: false` and `error: {code, message}` plus a redacted stderr diagnostic;
exit 1 rejects input and exit 2 reports usage/tool failure. `--help` emits a
JSON help envelope without reading stdin. Interrupts propagate.

## Creator and Legacy Compatibility

New outlines carry root `schema_version: 1` and exactly one
`talk.pacing_rate`: the complete typed narration rate from planning output.
Both complete and partial outline readers reject unsupported explicit root
versions and validate v1/v2 embedded rates without migration. The creator never recalculates or
edits measured provenance. Use a fresh owner-validated measured profile when
available. A stale or invalid present profile requires owner attention.

Previously unversioned outlines remain read-only-compatible. The loader does
not rewrite them; the next creator authoring pass adds the v1 root stamp.
Legacy `talk.pacing_wpm: [low, high]` has one compatibility meaning: an
unverified narration planning assumption with the v1 2-second gap definition.
It cannot coexist with `pacing_rate`; the owner replaces it with a typed
record on the next authoring pass. `extract-script.py` explicitly reports the
metric, threshold, assumption/measured basis, and measured provenance/range.
For a v2 rate, it also reports family count, family-balanced mean, conservative
planning rate and conditional mean interval, explicitly not a prediction interval.
It never labels predicted timing as verification.

Legacy `speaker-profile.json.pacing.wpm_range` has the same unverified
narration-assumption meaning; it is not a measured profile and cannot be fed
directly into the typed planning API. Its `comfortable` value is not an
independent observation. Leave schema-v5 slide-budget `pacing.adherence`
unchanged: slides per minute is a different quantity. Keep calibrated speech
data in this separate owner artifact and preserve all four metric labels.
