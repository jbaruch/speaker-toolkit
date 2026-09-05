# Speaking-Rate Contracts

Owner: `vault-profile`. Executable owner:
`skills/vault-profile/scripts/speech_rates.py`. This is an independent
schema-v1 artifact lane, not a change to `speaker-profile.json` schema v5 or
the tracking database. No operation here acquires media, runs Whisper, or
reparses talks. Acquisition and source-generation verification remain the
ingress owner's responsibility.

## Four Different Metrics

Every rate uses `unit: "words_per_minute"` and a named `metric`. Method
`word-gaps-v1` has these closed definitions:

| Metric | Denominator | `pause_threshold_seconds` | Use |
|---|---|---|---|
| `timeline` | Complete sample duration, including leading/trailing silence and all interruptions | `null` | Describe the finished recording |
| `narration` | Word spans plus complete internal gaps of at most 2 seconds | `2.0` | Long-form narration planning |
| `short_phrase` | Word spans plus complete internal gaps of at most 1 second | `1.0` | Describe phrase/beat pace |
| `articulation` | Word spans plus complete internal gaps of at most 250 milliseconds | `0.25` | Describe thresholded articulation, not end-to-end duration |

Gaps above a threshold contribute nothing; they are not clipped to the
threshold. Articulation is an operational word-alignment metric, not a
phonetic voice-activity detector. Do not relabel it as narration or use it
to size a long-form script. A threshold change requires a new method version.

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
to an assumption. `plan_duration` emits a schema-v1 prediction containing the
selected complete rate, intended metric, word count, point duration, and
inverted duration range, labeled `kind: "prediction_not_verification"`.

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
versions and validate the embedded rate. The creator never recalculates or
edits measured provenance. Use a fresh owner-validated measured profile when
available. A stale or invalid present profile requires owner attention.

Previously unversioned outlines remain read-only-compatible. The loader does
not rewrite them; the next creator authoring pass adds the v1 root stamp.
Legacy `talk.pacing_wpm: [low, high]` has one compatibility meaning: an
unverified narration planning assumption with the v1 2-second gap definition.
It cannot coexist with `pacing_rate`; the owner replaces it with a typed
record on the next authoring pass. `extract-script.py` explicitly reports the
metric, threshold, assumption/measured basis, and measured provenance/range.
It never labels predicted timing as verification.

Legacy `speaker-profile.json.pacing.wpm_range` has the same unverified
narration-assumption meaning; it is not a measured profile and cannot be fed
directly into the typed planning API. Its `comfortable` value is not an
independent observation. Leave schema-v5 slide-budget `pacing.adherence`
unchanged: slides per minute is a different quantity. Keep calibrated speech
data in this separate owner artifact and preserve all four metric labels.
