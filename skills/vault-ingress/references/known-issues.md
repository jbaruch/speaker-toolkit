# Known Issues — Vault Ingress

Edge cases and recovery strategies that don't change the happy-path workflow
but matter when the input data is degraded. Linked from `SKILL.md`'s
Important Notes section as one-line summaries.

## Shape Extraction Is Blind to Text Baked Into Images

`pptx-extraction.py` reads text out of PPTX **shapes**. AI-generated
illustration decks render every title, callout label, stamp, and annotation
*inside the picture*, where python-pptx cannot see any of it. Such a slide
extracts as one full-bleed image with no text.

**The failure it caused (issue #116):** the Arc of AI 2026 deck — 58 pages of
densely annotated technical-manual illustrations, the wordiest slides in the
corpus — was analyzed as *"overwhelmingly image-based … only about 10 slides
have any text overlay at all … the speakers carry nearly 100% of the
information verbally."* Dimension 8 came out exactly backwards, and the deck
scored as `vacation-photos` / `cave-painting`, patterns that mean the
opposite of what it is. The tell was the analysis quoting `10x5.62 inches`, a
python-pptx shape measurement: the analyst had read the JSON, not the slides.

**Mitigations:**

- The extractor no longer asserts absence. A slide whose picture is large
  enough to be carrying text reports `text_extraction_confidence: "low"` and
  an `image_area_ratio`; the threshold is the script's (`pptx-extraction.py`,
  `_TEXT_BEARING_IMAGE_AREA_RATIO`).
- On any low-confidence slide, judge Dimensions 8 and 13 from the **rendered
  image**, never the JSON — see `subagent-instructions.md` § "Slides with
  `text_extraction_confidence: low`". An empty `text_content_preview` there
  means unreadable, not wordless.
- `has_text_frame_shapes` (formerly `has_text_placeholder`) names what it
  measures: shapes with text frames. It is not a claim about on-screen text.

**Applies to:** any deck with full-bleed or near-full-bleed imagery —
increasingly the norm as illustration generation gets cheaper. Never conclude
"the slides are wordless" from extraction output alone.

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
