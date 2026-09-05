# Sampled Word Evidence

Owner: `vault-ingress`. `local_media_transcription.transcribe_local_words()`
returns established source-probe facts and a schema-v2 word receipt. It writes
no transcript, timing/quality sidecar, speech profile or catalog record. This
lane is separate from the existing transcript acquisition contract.

## Acquisition and Native Boundary

The caller supplies a local locator, `sample_start_seconds`,
`sample_duration_seconds`, optional trusted root and optional current in-memory
media/video probe. Missing probe facts are acquired by `probe_local_media`.
Never supply a serialized or manufactured probe. The original source's open
descriptor and pathname generation must remain unchanged throughout sampling
and transcription. The caller receives no usable result after a failed final
generation check or failed workspace cleanup.

The parent creates an owner-private workspace; the authenticated Whisper worker
decodes only the requested interval with FFmpeg. Streamed PCM has a strict byte
ceiling, a measured duration from frame count and a private WAV wrapper. The
sample has its own digest and generation. The original source is not copied or
hashed again when a current owner probe is reused. Parent-owned cleanup removes
sample files even when the worker times out or is killed.

`MEDIA_WHISPER_LIMITS` owns wall, memory, process and protocol/diagnostic limits.
`local_media_sampling.py` owns PCM format, clip bounds and decoder refusals.
All parsing, normalization, protocol framing, generation checks and cleanup
run in CI with real synthetic workers. Only native MLX calls use the documented
platform-bound carve-out in the [transcription authority](../../../rules/transcript-fetch-authority.md).

The supported model ID and immutable Hugging Face revision live in
`local_media_words.DEFAULT_WORD_MODEL`. Renew quarterly with native validation.
The optional `whisper` manifest extra pins mlx-whisper and huggingface-hub;
weekly Dependabot tracks their versions. The SDK resolves only the pinned
model's configuration and weights into its normal reusable cache; it does not
download remote Python code, use stored access tokens, or receive audio.
Model acquisition shares the worker's timeout/resource bounds. SDK cache state
is separate from per-recording scratch and is not deleted after each sample.

The native call requests real word timestamps, deterministic temperature and no
previous-text conditioning. The same model separately measures language
probability from the first 30 seconds of the decoded sample. A language label
alone, a word probability, or the expected language does not supply that value.
This probe does not prove language homogeneity across the complete sample.

## Closed Receipt Schema

All listed keys are required; unknown keys and future versions refuse:

```text
{schema_version: 2, pipeline_version: "sampled-words-v2",
 source_sha256, sample_sha256, source_duration_seconds,
 sample_start_seconds, sample_duration_seconds,
 provider: "mlx-whisper", provider_version,
 model: {id, revision}, language, language_probability, language_probe_seconds,
 words: [{text, start_seconds, end_seconds, probability, segment_index}, ...],
 segments: [{start_seconds, end_seconds, compression_ratio,
             average_log_probability, no_speech_probability}, ...],
 token_exclusions: [{token_index, reason: "punctuation_only"}, ...]}
```

The root receipt version owns the fixed nested model, word, segment and token
exclusion shapes. Words carry one lexical token each; the model's tokenization
convention is preserved. Only punctuation-only tokens are omitted, with an
explicit original token index. Invalid lexical timestamps, overlaps, missing
word alignment, invalid Unicode and segment membership failures refuse the
sample. No timestamps are interpolated, repaired, stretched or clipped.

Word and segment times are relative to the sample, not the full recording.
Each word retains its zero-based provider `segment_index`. Indices are ordered;
each word must overlap its declared segment by a positive duration. Native MLX
boundary adjustments can retain a segment timestamp inside its boundary word;
strict containment is not a provider guarantee. Neither timestamp is changed.
All word and segment spans remain positive, ordered, non-overlapping and inside
the sample. Source and sample SHA-256 values
bind different byte artifacts. `sample_start_seconds` maps the decoded interval
back to the original source, and its actual PCM duration must fit that source.
Confidence/probability fields are measurements, not quality verdicts. The
separate profile owner records the versioned policy that accepts or excludes
each sample.

`normalize_word_result()` projects bounded provider data into this receipt;
`validate_word_sample()` is the non-mutating reader. Both raise the path-neutral
`LocalMediaError` contract. Neither pure helper authenticates arbitrary supplied
digests. Consumers obtain receipts from `transcribe_local_words`, preserve them
unchanged and recheck live source freshness through ingress before reuse.
Missing receipts mean no word evidence. Segment-only timing sidecars are not
migrated into words; obtain fresh alignment through this owner. The experimental
v1 receipt omitted explicit membership; it is not accepted or auto-migrated.
Run fresh owner acquisition to obtain v2 evidence.

`WordSampleError` adds closed numeric failure details: `schema_version: 1`,
`word_index`, `word_count`, `word_start_seconds`, `word_end_seconds`,
`segment_index`, `segment_count`, `segment_start_seconds` and
`segment_end_seconds`. Indices/counts are bounded integers and times are finite
sample-relative seconds. A missing segment uses null index/start/end together.
Unknown keys, words and source paths are forbidden. Worker transport revalidates
these details before exposing them to a caller.

## Native Manual Validation

Run on Apple Silicon with the configured interpreter and optional `whisper`
extra. Use an authorized recording whose solo-speaker identity and language
are independently known. This procedure covers only the MLX import, native
transcription, spectrogram/model access and language-detection call named in
the [transcription authority](../../../rules/transcript-fetch-authority.md); it does not exempt orchestration tests.

1. Resolve the vault root, speaker name and exact interpreter through the strict
   owner bootstrap in vault-profile. Record the owner's catalog digest and
   preserve any existing speech profile and transcript artifacts.
2. Require native capability:

   ```bash
   "{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/check-runtime.py" \
     --lanes core,source-media,speech-calibration --require-lanes core,source-media,speech-calibration
   ```

   Include `youtube-download` in both lists if downloads are authorized.
3. Run a metadata plan through `calibrate-speech.py` with the explicit speaker,
   language and `--maximum-recordings 1`. Inspect the selected source identity;
   no recording is opened by the plan. Use `--allow-download` only for authorized
   YouTube acquisition and retain that same option for the measured run.
4. Repeat with `--run`, capturing stdout into a **fresh** private report. Require
   exit 0, `ok: true`, one admitted recording and `status: "low_confidence"` for
   this intentionally single-recording test. An acquisition or quality exclusion
   is not a pass. It requires source/provider investigation, not lowered gates.
5. Inspect `data.profile.calibration.samples[0].words`: current provider version,
   pinned model ID/revision, exact source/sample digests, actual interval bounds,
   lexical word start/end times and real language probability are present.
   Listen to the authorized source at the recorded sample interval and check
   several word boundaries near the beginning, middle and end. Require plausible
   word alignment and correct language; evenly spaced invented timestamps fail.
   A high reported probability does not excuse a wrong detected language.
6. Require all four metric names with their owner thresholds, the recording's
   actual word count and interval, explicit low confidence and null conservative
   planning rates. The single-family confidence interval remains null.
7. Repeat the strict catalog read and require the starting digest. Confirm no
   transcript, timing/quality receipt or prior profile changed and no private
   sample workspace survives. Model weights may remain in the SDK cache.

A native pass requires all seven checks. A single-recording validation does not
establish a representative speaker profile or recorder acceptance. Run the full
cohort separately and keep its sparse/missing-mode uncertainty explicit.
