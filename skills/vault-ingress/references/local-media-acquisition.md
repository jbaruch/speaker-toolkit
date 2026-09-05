# Bounded Local-Media Acquisition

Read before using local audio/video or the YouTube Whisper fallback. The public
entrypoint remains `fetch-transcript.py`; its module docstring owns arguments,
JSON output, exit codes, and transcript-replacement authorization.

## Runtime Gate

Require the database-configured interpreter's lanes before using them:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/check-runtime.py" \
  --lanes core,source-media,whisper --require-lanes core,source-media,whisper
```

For the YouTube download fallback, include `youtube-download` in both lists.
For probe-only library work, require `core,source-media` without Whisper.
`check-runtime.py`'s `LANE_REQUIREMENTS` and version maps own dependencies and
pins. A failed optional lane does not invalidate independent captions or slides.

## Acquisition Ownership

- Pass the original local locator to `fetch-transcript.py --audio`; never
  pre-open, hash, hydrate, copy, or invoke `ffprobe` on the source yourself.
- `local_media_evidence.py`'s `probe_local_media` owns availability, generation
  binding, snapshot hashing, probe facts, and private-workspace cleanup.
- `local_media_contract.py`'s named `MEDIA_*` constants, admission helpers, and
  `bounded_whisper_result` own supported containers and resource ceilings.
- `local_media_transcription.py`'s `transcribe_local_media` accepts a current
  in-memory media/video probe from its owner. It reuses those facts and rechecks
  source generation. A serialized or hand-constructed receipt is not authority
  to skip acquisition.
- `transcribe_local_words` uses the same acquisition owner for bounded interior
  samples. Read [sampled-word-evidence.md](sampled-word-evidence.md) before using
  this independent word-evidence lane; it does not write catalog transcripts.
- `local_media_download.py`'s `download_youtube_audio` yields a private local
  artifact plus provider duration and removes the workspace when its consumer
  exits. It does not register or preserve a recording in the vault.
- Worker arguments contain no source locator or model path. Authenticated
  private request payloads carry them; diagnostics remain bounded and redacted.

## Refusal and Recovery

The fetcher reports worker refusal through its existing failure JSON and stderr.
Use `LocalMediaError.reason_code` for library callers. Repair unavailable runtime
lanes, restore a locally available supported source, or retry after source edits
finish. Never bypass worker admission or increase a threshold from skill prose.

A failed local probe, transcription, resource check, cleanup, or precommit
generation check leaves prior transcript, quality, and timing artifacts intact.
This includes a stale quality receipt: failure does not authorize weakening its
provenance. `--force` authorizes transcript replacement, not bypassing validation.

Acquisition proves source bytes and duration, not that a recording belongs to a
catalog talk. Keep the separate owner-binding preflight gate; do not patch a
receipt, infer a missing recording, or relabel old analysis to clear it.
