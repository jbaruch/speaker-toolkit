### Known Pitfalls

**Wide-angle room recordings defeat perceptual hash dedup.** When the camera captures
the full stage (speaker moving + slides projected on a screen behind them), every frame
looks different because speaker position changes. The pipeline produces 800-1500
"unique" frames instead of 40-80 actual slides. Mitigation options:
1. Increase `hash_threshold` to 14-16 (loose dedup tolerates speaker movement)
2. Manually specify `slide_region` crop coordinates to isolate the projected screen
3. Accept the bloated PDF — the analysis subagent should visually SAMPLE representative
   frames at intervals rather than reading every page of a 1000+ page PDF

The pipeline works best for recordings that show slides fullscreen (Devoxx, JFokus,
most modern conference recordings). Wide-angle audience-camera recordings from meetups
and DevOpsDays are the worst case.

**Whisper hallucination on bad audio.** When conference recordings have poor audio
(distant mics, room echo, music tags), Whisper large-v3-turbo recovers ~60% of speech
but hallucinates through silent/noisy sections — generating plausible-sounding but
fabricated text. Always:
1. Set `transcript_source: "whisper"` so the analysis knows the source
2. Cross-reference Whisper output against visible slide text to catch hallucination
3. Note quality issues in the talk's DB entry (e.g., `transcript_quality: "partial"`)

**Non-speaker talks slip into playlists.** Conference playlists include ALL speakers,
not just the vault's target speaker. The subagent should verify speaker identity early
in analysis — check video frames for the expected speaker, check transcript for
self-identification. Flag `is_baruch_talk: false` and set status to `skipped` if the
speaker doesn't match.

**Step 5 timing matters.** Run the full clarification session (especially the humor
post-mortem and blind spot moments) IMMEDIATELY for talks delivered within the past
week. Memory is freshest right after delivery — room energy, audience reactions, and
spontaneous moments fade fast. For older talks (2+ years), use the compressed version:
"Any jokes you remember landing well or badly? Anything about the room context?"
