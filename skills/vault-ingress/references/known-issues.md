# Known Issues — Vault Ingress

Edge cases and recovery strategies that don't change the happy-path workflow
but matter when the input data is degraded. Linked from `SKILL.md`'s
Important Notes section as one-line summaries.

## Stale Vault Artifacts Are Not Inputs

A vault may hold files left by tools that predate this skill. The known case is
a vault-root `extract_pptx_visual.py` and its `pptx-extraction-results.json`,
orphaned when per-file extraction replaced them.

Nothing in this skill reads them. `skills/vault-ingress/scripts/pptx-extraction.py`
runs per PPTX and feeds the analysis directly; no step consumes an aggregate
results file. [schemas-db.md](schemas-db.md) describes what that script emits,
which is not what the orphaned file contains.

Before treating any vault file as an input, confirm a step reads it. A
plausible filename in the vault root is not a contract, and building against
one produces code that runs clean against data nothing consumes.

## Shape Extraction Is Blind to Text Baked Into Images

`skills/vault-ingress/scripts/pptx-extraction.py` reads text out of PPTX
**shapes**. AI-generated
illustration decks render every title, callout label, stamp, and annotation
*inside the picture*, where python-pptx cannot see any of it. Such a slide
extracts as one full-bleed image with no text.

Read that way, Dimension 8 inverts: the densest decks in the corpus score as
wordless backdrops.

**Mitigations:**

- The extractor no longer asserts absence: it emits
  `text_extraction_confidence` per slide. What trips it to `"low"` is the
  script's to decide — see `skills/vault-ingress/scripts/pptx-extraction.py`,
  the `_TEXT_BEARING_IMAGE_AREA_RATIO` constant comment.
- **Read the confidence, never `image_area_ratio`.** The two are independent: a
  slide can be `"low"` with a ratio of `0.0`. Deriving your own trigger from the
  ratio reproduces the bug this entry exists to prevent.
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
