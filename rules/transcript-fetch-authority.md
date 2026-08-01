---
alwaysApply: false
applyTo: "skills/vault-ingress/scripts/fetch-transcript.py, skills/vault-ingress/scripts/transcript_quality.py, skills/vault-ingress/scripts/transcript_timing.py, skills/vault-ingress/scripts/vtt-cleanup.py, pyproject.toml — when changing transcript acquisition, VTT import, quality/timing receipts, or the mlx-whisper dependency"
description: Authority of record for the Whisper transcription layer's Platform-Bound Untestable Carve-Out
---

# Transcript Fetch Authority

## Carve-Out Claimed

- `jbaruch/coding-policy: testing-standards` Platform-Bound Untestable Carve-Out.
- This rule is the authority of record satisfying precondition 3 — it names the carve-out, the exempt artifact, and where the manual validation procedure lives.
- Qualifying condition: `mlx-whisper` requires Apple Silicon and cannot install on the project's Linux CI runners.

## Covered Artifact

- `transcribe_audio()` in `skills/vault-ingress/scripts/fetch-transcript.py` — the `mlx_whisper.transcribe()` call — and `fetch_whisper()`, which downloads audio and delegates to it. Both the YouTube `--method whisper` path and the non-YouTube `--audio` path reach the exemption through `transcribe_audio()`; nothing else in the file is exempt.
- `mlx-whisper` is declared as the optional `whisper` extra in `pyproject.toml`, never a base dependency. The caption path and every validator work without it.
- Non-YouTube talks route through `--audio` on this same script. Transcription is deterministic script work per `jbaruch/coding-policy: script-delegation`, so no skill prose may call `mlx_whisper.transcribe()` directly — a hand-rolled call carries none of the validation, atomic write, or JSON contract, which is the defect class this script was written to end.

## Precondition 1 — CI-Runnable Pieces Are Extracted and Tested

- `validate_transcript()`, `build_quality_policy()`, `count_words()`,
  `resolve_video_id()`, `segments_to_text()`, receipt validation, and atomic
  writers are deterministic and carry tests in `tests/test_fetch_transcript.py`
  and `tests/test_transcript_timing.py`.
- Duration probes are subprocess wrappers with synthetic CI tests. YouTube
  duration comes from provider metadata returned by `yt-dlp`; local-media
  duration comes from `ffprobe` over the exact file and is bound to its SHA-256.
- Tests cover empty/error/VTT/non-speech artifacts, the fixed and WPM floors,
  low-`--min-words` bypass attempts, source-duration matching, Unicode word
  counting, both segment shapes, invalid UTF-8, exact provenance, no-segment
  quality receipts, CRLF/LF byte drift, transactional rollback, enumerated
  optional-library failures, malformed-timing downgrade, media
  snapshot mutation, destination symlinks, VTT path safety, and caption fall-through.
- Only the audio-download-and-transcribe wrapper is exempt.
- Caption and Whisper imports, constructors, API calls, and provider result
  objects are optional-lane boundaries. `ImportError`, `OSError`,
  `RuntimeError`, `AttributeError`, `TypeError`, `ValueError`, and `KeyError`
  make that lane unavailable; auto mode continues to its next source. Unknown
  exception classes reach the tokenized outer process boundary. Provider stdout
  routes to stderr so stdout remains one JSON object. Process-control signals
  are not swallowed.

## Transcript Quality Authority

- `transcripts/<id>.segments.json` owns timing and acquisition provenance only.
  It never owns quality policy.
- Its current closed schema is version 2 with exactly `schema_version`,
  `transcript_sha256`, `source`, `provenance`, and `segments`. YouTube caption
  and Whisper timing bind an 11-character video ID plus trusted provider
  duration; local Whisper timing binds exact media SHA-256 plus trusted probe
  duration; VTT timing binds a safe transcript-relative regular-file path,
  exact artifact SHA-256, and final cue extent.
- Every schema-v2 segment must be canonical, its joined text must equal the
  transcript modulo Unicode whitespace layout, and its time range must fit the
  source-owned duration (or exact VTT cue extent). Schema v1 is archival only:
  it cannot supply timing or relabel provenance and must be regenerated from a
  source whose owner and bounds can be proved.
- `transcripts/<id>.quality.json` owns the exact policy that validated the
  transcript. Its closed schema contains `schema_version`, the SHA-256 of exact
  `.txt` bytes, exact `policy`, and exact `provenance`.
- Policy is exactly `{schema_version: 1, min_words: int,
  duration_seconds: number|null}`. A low `--min-words` never lowers the fixed
  400-word floor or a trusted duration-derived floor; any value above the
  derived floor tightens it.
- Provenance is exactly one of `{kind: "fixed_default"}`,
  `{kind: "youtube_duration", video_id, duration_seconds}`, or
  `{kind: "local_media_duration", media_sha256, duration_seconds}`. A
  duration-bearing provenance value must equal the policy duration exactly.
- `--duration-seconds` is caller expectation, not authority. It can be used
  only when it matches provider/`yt-dlp` duration for the exact YouTube ID or
  `ffprobe` duration for the exact local-media digest. Worker-returned or talk
  analysis metadata can never lower a threshold.
- Missing timing does not invalidate a current quality receipt. Missing or
  stale quality authority does make a transcript ineligible for current v5
  scoring until the fetcher validates it and writes a receipt.
- Both receipt readers hash raw transcript bytes. Any byte replacement,
  including CRLF→LF with identical decoded words, invalidates both receipts.
- The talk's recorded `transcript_source` is canonical. A sidecar may confirm
  matching owner-bound timing, but captions cannot promote manual, Whisper, or
  unknown text, and a timing source never rewrites the talk's provenance.
- Existing transcript bytes are never replaced without explicit `--force`.
  Invalid existing text fails closed and asks for that authorization. A caught
  bundle-write failure restores the prior transcript and both receipts exactly.
  Missing, malformed, mismatched, or over-bound optional timing removes stale
  timing while valid transcript text and its quality receipt still commit.
- Local `--audio` acquisition copies one twice-verified regular source into a
  private read-only snapshot. Hashing, `ffprobe`, Whisper, quality provenance,
  and timing provenance all use that snapshot. The original pathname identity
  and open-descriptor digest are revalidated immediately before commit.
  Original-source replacement, in-place mutation, or snapshot drift fails with
  no bundle write.
- Transcript, timing, and quality final-component symlinks are forbidden,
  including dangling links. VTT imports require lexical and resolved
  containment below the transcript directory, no symlink components below that
  root, and a regular artifact before read/open.

## Precondition 2 — Manual Validation Procedure

Run against a talk whose caption track is disabled, on Apple Silicon with the
`whisper` extra installed:

1. `"{python_path}" skills/vault-ingress/scripts/fetch-transcript.py {youtube_id} --out /tmp/{youtube_id}.txt --method whisper --existing-source unknown`
2. Observe: exit 0, one JSON object on stdout with `"method": "whisper"`,
   `"timed_path": "/tmp/{youtube_id}.segments.json"`,
   `"quality_path": "/tmp/{youtube_id}.quality.json"`, and a `words` count plausible for
   the runtime (conference delivery is 110–160 wpm).
3. `jq -e --arg id "{youtube_id}" '.schema_version == 2 and .source == "whisper" and .provenance.kind == "youtube_whisper" and .provenance.video_id == $id and (.provenance.duration_seconds > 0) and (.segments | length > 0) and all(.segments[]; .start_seconds >= 0 and .end_seconds > .start_seconds and (.text | length > 0))' /tmp/{youtube_id}.segments.json` exits 0.
4. `test "$(jq -r .transcript_sha256 /tmp/{youtube_id}.segments.json)" = "$(shasum -a 256 /tmp/{youtube_id}.txt | awk '{print $1}')"` exits 0.
5. `jq -e '.schema_version == 1 and (.transcript_sha256 | length == 64) and .policy.schema_version == 1 and (.policy.min_words >= 1) and ((.policy.duration_seconds == null and .provenance == {"kind":"fixed_default"}) or (.policy.duration_seconds == .provenance.duration_seconds))' /tmp/{youtube_id}.quality.json` exits 0, and its `transcript_sha256` equals `shasum -a 256 /tmp/{youtube_id}.txt`.
6. Confirm `/tmp/{youtube_id}.txt` holds prose, not `[Music]` markers or a traceback.
7. Re-run with `yt-dlp` removed from `PATH` and a fresh output path. Expect exit 1, a stderr line naming the install command, one JSON object with `"ok": false`, and no transcript or receipt at that output path.
8. `"{python_path}" skills/vault-ingress/scripts/fetch-transcript.py local-talk-label --audio <local-file> --out /tmp/a.txt --existing-source unknown` on a non-YouTube recording: exit 0, `"method": "whisper"`, `"timed_path": "/tmp/a.segments.json"`, `"quality_path": "/tmp/a.quality.json"`, prose at the output path, timing schema v2 with `local_media_whisper` provenance, and timing plus quality provenance whose `media_sha256` equals the exact input-media digest.

A pass requires all eight checks.

## Scope Limits

- The carve-out covers this one wrapper. It does not extend to another script, another dependency, or the caption path.
- Adding a second exempt artifact requires naming it here AND documenting its own validation procedure. Adding one without both invalidates the precondition.
- "Hard to install in CI" does not qualify — see `jbaruch/coding-policy: ci-safety` Install, Don't Skip. `mlx-whisper` cannot run on the runner's architecture and qualifies for the carve-out.
