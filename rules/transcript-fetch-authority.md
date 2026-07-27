---
alwaysApply: false
applyTo: "skills/vault-ingress/scripts/fetch-transcript.py, pyproject.toml — when changing transcript acquisition or the mlx-whisper dependency"
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
5. `--audio <local file> --out /tmp/a.txt` on a non-YouTube recording: exit 0, `"method": "whisper"`, prose at the output path.

A pass requires all five. Step 4 is the one that matters: it proves a tool-state failure still honours the JSON contract and still leaves nothing behind.

## Scope Limits

- The carve-out covers this one wrapper. It does not extend to another script, another dependency, or the caption path.
- Adding a second exempt artifact requires naming it here AND documenting its own validation procedure. Adding one without both invalidates the precondition.
- "Hard to install in CI" does not qualify — see `jbaruch/coding-policy: ci-safety` Install, Don't Skip. `mlx-whisper` qualifies because it cannot run on the runner's architecture at all.
