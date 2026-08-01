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
extracts as one full-bleed image with empty shape text.

Read that way, Dimension 8 used to invert: the densest decks in the corpus
scored as wordless backdrops (#116).

**Mitigations:**

- The extractor no longer asserts absence: it emits
  `text_extraction_confidence` per slide. What trips it to `"low"` is the
  script's to decide — see `skills/vault-ingress/scripts/pptx-extraction.py`,
  the `_TEXT_BEARING_IMAGE_AREA_RATIO` constant comment.
- **OCR inventory (#129).** On low-confidence slides that have PICTURE shapes,
  the same script OCRs the picture blobs into `ocr_text` and sets
  `text_extraction_method` to `shapes+ocr` (or `shapes+ocr_unavailable` if
  tesseract is missing). Use `ocr_text` for word lists, transcript cross-checks,
  language policy on slide text, and citational pattern evidence (`second-look`,
  etc.). Empty `text_content_preview` still means *shapes could not read it*,
  not *the slide is blank*.
- **Read the confidence, never `image_area_ratio`.** The two are independent: a
  slide can be `"low"` with a ratio of `0.0`. Deriving your own trigger from the
  ratio reproduces the bug this entry exists to prevent.
- On any low-confidence slide, judge Dimensions 8 and 13 **design** (density,
  two-layer structure, composition) from the **rendered image** — OCR is not a
  layout oracle. See `subagent-instructions.md` § "Slides with
  `text_extraction_confidence: low`".
- Image *backgrounds* without a PICTURE shape are still low-confidence but have
  no blob to OCR in this path — fall back to the rendered-page pass.
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
