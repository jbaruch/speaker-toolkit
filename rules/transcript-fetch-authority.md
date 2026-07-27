---
alwaysApply: false
applyTo: "skills/vault-ingress/scripts/fetch-transcript.py, pyproject.toml — when changing transcript acquisition or the mlx-whisper dependency"
description: Authority of record for the Whisper transcription layer's Platform-Bound Untestable Carve-Out
---

# Transcript Fetch Authority

## Why

- `skills/vault-ingress/scripts/fetch-transcript.py` acquires a talk transcript from a caption track, falling back to local Whisper transcription of the downloaded audio.
- The Whisper layer needs `mlx-whisper`, which requires Apple Silicon and cannot install on the project's Linux CI runners.
- `jbaruch/coding-policy: testing-standards` Platform-Bound Untestable Carve-Out permits an exempt layer under three preconditions. This rule is the authority of record satisfying precondition 3: it names the carve-out, the exempt artifact, and where the manual validation procedure lives.

## Covered Artifact

- `fetch_whisper()` in `skills/vault-ingress/scripts/fetch-transcript.py` — the audio download plus `mlx_whisper.transcribe()` call. Nothing else in the file is exempt.
- `mlx-whisper` is declared as the optional `whisper` extra in `pyproject.toml`, never a base dependency. The caption path and every validator work without it.

## Precondition 1 — CI-Runnable Pieces Are Extracted and Tested

- `validate_transcript()`, `count_words()`, `resolve_video_id()`, `segments_to_text()` and `write_atomically()` are pure and carry tests in `tests/test_fetch_transcript.py`.
- Those tests cover every validation failure mode from fixtures: empty, Python-error signature, word floor, mostly-`[Music]`, words-per-minute floor, Cyrillic word counting, both caption-segment shapes, atomic write, and caption-exception fall-through.
- Only the audio-download-and-transcribe wrapper is exempt.

## Precondition 2 — Manual Validation Procedure

Run against a talk whose caption track is disabled, on Apple Silicon with the
`whisper` extra installed:

1. `python3 skills/vault-ingress/scripts/fetch-transcript.py <youtube_id> --out /tmp/t.txt --method whisper`
2. Observe: exit 0, one JSON object on stdout with `"method": "whisper"` and a `words` count plausible for the runtime (conference delivery is 110–160 wpm).
3. Confirm `/tmp/t.txt` holds prose, not `[Music]` markers or a traceback.
4. Re-run with `yt-dlp` removed from `PATH`. Expect exit 1, a stderr line naming the install command, one JSON object with `"ok": false`, and NO file at the output path.

A pass requires all four. Step 4 is the one that matters: it proves a tool-state failure still honours the JSON contract and still leaves nothing behind.

## Scope Limits

- The carve-out covers this one wrapper. It does not extend to another script, another dependency, or the caption path.
- Adding a second exempt artifact requires naming it here AND documenting its own validation procedure. Adding one without both invalidates the precondition.
- "Hard to install in CI" does not qualify — see `jbaruch/coding-policy: ci-safety` Install, Don't Skip. `mlx-whisper` qualifies because it cannot run on the runner's architecture at all.
