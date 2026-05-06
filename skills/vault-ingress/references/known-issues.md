# Known Issues — Vault Ingress

Edge cases and recovery strategies that don't change the happy-path workflow
but matter when the input data is degraded. Linked from `SKILL.md`'s
Important Notes section as one-line summaries.

## Wide-Angle Room Recordings Defeat Slide Dedup

When the camera captures the full stage (speaker moving + slides on screen
behind), every frame looks different — perceptual hash dedup ends up
producing one "unique" slide per frame.

**Mitigations:**

- Increase `--threshold` to 14–16 (looser similarity tolerance).
- Manually specify `slide_region` crop coordinates so the deduper hashes
  only the slide area, not the whole frame.
- Accept the bloated PDF and have the analysis subagent sample frames at
  intervals.

**Best results:** fullscreen slide recordings (Devoxx, JFokus).
**Worst results:** meetup / DevOpsDays audience-camera recordings.

## Whisper Hallucination on Bad Audio

Whisper large-v3-turbo recovers ~60% of speech on poor recordings but
hallucinates through silent / noisy sections — generating plausible-looking
text that wasn't said.

**Mitigations:**

- Always set `transcript_source: "whisper"` so downstream tools know the
  reliability tier.
- Cross-reference suspect passages against visible slide text — if the
  transcript claims content the slide doesn't support, flag it.
- Set `transcript_quality: "partial"` on talks where whole sections are
  unreliable.

## Non-Speaker Talks Slip into Playlists

Conference playlists sometimes mix talks from multiple speakers, and a vault
that ingests "everything in the playlist" will silently absorb them.

**Mitigations:**

- Verify speaker identity early — check video frames and the transcript for
  self-introduction.
- Flag `is_baruch_talk: false` (or the equivalent for the configured speaker
  identity) and set status to `skipped` if the speaker doesn't match.
- Review the skip list manually before publishing the speaker profile —
  silent skips are the easiest way to corrupt the rhetoric summary with
  someone else's patterns.
