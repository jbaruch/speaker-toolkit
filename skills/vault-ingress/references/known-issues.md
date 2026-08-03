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

## Native Timing Metadata Is Not Playback Evidence

PPTX schema v3 introduced a distinct raw build-list
lane. Timing containers, exact animation behavior elements, visibility set
actions, transitions, audio/video timing nodes, and build entries come directly
from slide-part XML. The lanes are
separate because `<p:timing>` can contain media
playback or other time nodes without any shape motion, and a stored behavior can
exist without executing in the delivered talk.

Read `native_timing.provenance`: `measurement: raw_ooxml_element_counts` and
`observed_playback: false` are interpretation constraints. Counts do not resolve
Markup Compatibility branches, targets, ordering, concurrency, smoothness, or
what an audience saw. Use delivery video or deeper target/timing-tree inspection
when a pattern requires those facts. Adjacent duplicate slides can establish a
static progressive reveal after rendered inspection even when every native count
is zero.

Missing/v0/v1 extraction output has **unknown** timing, not zero timing. Regenerate
it with the current extractor. Unknown future schemas are unusable until the
reader contract is updated; do not guess from field presence.

## Shape Extraction Is Blind to Text Baked Into Images

`skills/vault-ingress/scripts/pptx-extraction.py` reads text out of PPTX
**shapes**. AI-generated
illustration decks render every title, callout label, stamp, and annotation
*inside the picture*, where python-pptx cannot see any of it. Such a slide
extracts as one full-bleed image with empty shape text.

Read that way, Dimension 8 used to invert: the densest decks in the corpus
scored as wordless backdrops (#116).

**Mitigations:**

- The extractor no longer asserts absence: it emits
  `text_extraction_confidence` per slide. What trips it to `"low"` is the
  script's to decide — see `skills/vault-ingress/scripts/pptx-extraction.py`,
  the `_TEXT_BEARING_IMAGE_AREA_RATIO` constant comment.
- **OCR inventory (#129).** On low-confidence slides with usable PICTURE or
  background-image blobs, the same script emits provenance-bearing
  `picture_ocr` / `background_image_ocr` channels, aggregates their text into
  `ocr_text`, and sets `text_extraction_method` to `shapes+ocr` (or
  `shapes+ocr_unavailable` if tesseract is missing). OCR channels record whether
  an attempt occurred, engine/version, numeric result confidence, and one
  package-part/SHA-bound receipt per readable asset. `--no-ocr`, missing blobs,
  unavailable engines, genuine empty results, and failures are distinct. Use
  only `trustworthy_text: true` receipts as affirmative evidence; preserved
  low-confidence text is review inventory, not a native-text claim. Empty
  `text_content_preview` still means *native channels could not read it*, not
  *the slide is blank*, and empty/failed/unavailable OCR remains render-required.
- **Read the confidence, never `image_area_ratio`.** The two are independent: a
  slide can be `"low"` with a ratio of `0.0`. Deriving your own trigger from the
  ratio reproduces the bug this entry exists to prevent.
- On any low-confidence slide, judge Dimensions 8 and 13 **design** (density,
  two-layer structure, composition) from the **rendered image** — OCR is not a
  layout oracle. See `subagent-instructions.md` § "Slides with
  `text_extraction_confidence: low`".
- Image *backgrounds* without a PICTURE shape are still low-confidence. When
  their background relationship resolves, the extractor OCRs the actual blob
  into a distinct `background_image_ocr` channel; missing relationships/blobs
  are explicit `status: unavailable`. In both cases, use the rendered-page pass
  for design judgment.
- Grouped shapes and native table cells are now traversed, but remain
  low-confidence because nested transforms, merged cells, and embedded visuals
  can change what is visibly readable. SmartArt, charts, OLE/media, and unknown
  graphic frames are listed under `unsupported_content`; they always require a
  rendered-page or specialized-parser pass.
- Bad-CRC members under `ppt/media/` are replaced in memory with a transparent
  placeholder so healthy slides and text survive extraction. Read
  `archive_recovery`, the compatibility `corrupt_assets` projection, and
  `render_required_reasons`; the source PPTX is never rewritten, and corrupt
  structural members remain hard errors. Placeholder recovery is degraded
  evidence and blocks a fresh claim/return when the native deck is required.
- `has_text_frame_shapes` (formerly `has_text_placeholder`) names what it
  measures: shapes with text frames. It is not a claim about on-screen text.

**Applies to:** any deck with full-bleed or near-full-bleed imagery —
increasingly the norm as illustration generation gets cheaper. Never conclude
"the slides are wordless" from empty shape text alone.

## Wide-Angle Room Recordings Defeat Slide Dedup

When the camera captures the full stage (speaker moving + slides on screen
behind), every frame looks different — perceptual hash dedup ends up
producing one "unique" slide per frame.

**Mitigations:**

- Increase `--threshold` to 14–16 to merge more aggressively and keep fewer
  motion variants. Higher thresholds can also merge real reveals or distinct
  slides, so inspect the result for under-counting.
- Prefer a visually checked manual crop so the deduper hashes only the slide
  area, not the whole frame: `--region LEFT,TOP,RIGHT,BOTTOM --region-verified`.
- Treat any auto-cropped `slide_region` artifact as a review candidate only. It
  remains `review_required` and cannot support authored-slide evidence until the
  checked coordinates are rerun as a verified manual crop.
- Use the `full_frame_context` PDF to inspect the room/PiP and sample frames at
  intervals, but never describe that broadcast artifact as the authored deck.
- Preserve the source video and context PDF so a failed crop can be reviewed and
  re-extracted rather than silently replacing the only visual evidence.

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

## Timed Sidecars Can Be Missing or Stale

Legacy transcripts have no `{id}.segments.json`, and a manually edited `.txt`
can no longer match the timing file that was generated with it. This does not
make the transcript unusable, but applying those timestamps would attach
evidence to the wrong moment.

**Mitigations:**

- `transcript_timing.py` binds every sidecar to the exact transcript text with
  `transcript_sha256`; readers reject a missing, malformed, unsupported, empty,
  or hash-mismatched sidecar.
- Use ordinary `transcript` citations when exact timing is irrelevant.
- When a pattern requires position or timing, regenerate the transcript bundle
  from captions/Whisper/VTT or review the video directly. Do not silently
  downgrade it to an unlocated quote.

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
