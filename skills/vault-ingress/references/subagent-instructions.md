# Per-Talk Subagent Instructions — Detail

The Step 3 procedure each parallel subagent runs. The orchestrator passes the
talk's DB entry plus the current `rhetoric-style-summary.md`; the subagent
returns the JSON shape in [schemas-db.md](schemas-db.md). The summary supports
qualitative rhetoric analysis, but Section 15 is human narrative and MUST NOT be
parsed for numeric adherence. The active claim's immutable
`adherence_baseline` is the sole numeric authority.
A successfully persisted v7 return is the fresh return generation eligible for pattern-scoring schema v6;
saved legacy claims remain replayable only with their
same-numbered archival return generation.

## A. Acquire Transcript and Slides

### Transcript download

Before local-media acquisition or the YouTube Whisper fallback, follow
[Bounded Local-Media Acquisition](local-media-acquisition.md). Require its
runtime lanes and pass the source locator to the owner; do not pre-read media.

One command. Do NOT hand-roll a fetch — an inline `python3 -c` fetch here is
what wrote four Python tracebacks into `transcripts/` when the upstream library
renamed a method, and nothing noticed because nothing validated the output.

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/fetch-transcript.py" {youtube_id} \
  --out "{vault_root}/transcripts/{youtube_id}.txt" \
  --existing-source "{talk.transcript_source|unknown}" \
  [--duration-seconds {seconds}]
```

The script owns the whole chain — caption track first, local Whisper fallback,
validation, atomic write. It prints one JSON object and never leaves a corrupt
transcript behind on failure. Transcript, quality, and timing changes are staged
together; a caught replacement failure restores every prior byte. When verified
source-bound segment timing exists, `timed_path` names hash-bound schema-v2
`{id}.segments.json`; otherwise it is `null` and stale timing is removed. On
every success, `quality_path` names the independent hash-bound
`{id}.quality.json` receipt, including for an existing transcript and when no
timed segments exist. Exit codes and the JSON shape are the script's contract;
see its module docstring.

| exit | meaning | what to do |
|---|---|---|
| 0 | a valid transcript is at `--out` | continue; read `method` to set `transcript_source` |
| 1 | no source produced valid text, or existing text failed policy without replacement authorization | inspect the reason; `processed_partial` at best |
| 2 | argument or tool-state error | the id or the environment is wrong, not the talk |

Map the returned `method` to `transcript_source`:

| `method` | `transcript_source` |
|---|---|
| `captions` | `youtube_auto` |
| `whisper` | `whisper` |
| `existing` | leave the talk's current `transcript_source` unchanged; when the field is absent, leave it absent |

An automatic caption track imported from a non-YouTube provider records
`provider_auto`; it does not map from the fetcher's YouTube-only `captions`
method.

`existing` means a valid transcript was already on disk and no fetch ran, so the
script learned nothing about where it came from — overwriting the recorded source
would replace a known value with a guess, and inventing one where the field is
absent is the same error with no prior value to lose. `manual` in particular
means a human produced the transcript; writing it on an unknown-provenance file
asserts something false, and a downstream reader weighing transcript reliability
would trust it more than the ASR it probably is.

Set `delivery_language` from the returned `language`: the caption track's own
language code, or Whisper's detected language. It is `null` on the `existing`
path — keep whatever the talk already records, and leave the field unset rather
than guessing when there is nothing to copy.

`--duration-seconds` is an expected runtime, never authority. The script uses it
only when it matches a provider/`yt-dlp` probe for the exact YouTube ID or
`ffprobe` over the exact local-media file. Do not pass a return field, prose
estimate, or unbound talk-metadata duration. `--min-words` can tighten the safe
floor but cannot lower it; a short-talk floor comes only from the trusted probe.

Treat `timed_path: null` literally. A hash-current `quality_path` still permits
an ordinary `transcript` quote, but no opening/closing position, pause, or other
timing-dependent claim. Missing or stale quality is unverified legacy input and
cannot enter the current pattern-scoring generation; requeue it through this
script. Never invent a
timestamp, reuse an unverified receipt, or copy receipt fields into a return;
persistence owns and verifies both artifacts.

Timing schema v1/minimal receipts are archival and cannot establish ownership,
timing, or transcript provenance. Do not relabel or patch them in place. Re-run
the current fetch/transcription against a source with provable owner duration,
or re-import the original VTT artifact, to generate schema v2. If optional
segments are malformed, text-mismatched, or outside that bound, valid semantic
text plus quality still commit and timing remains unavailable.

**A transcript already on disk is not proof of a transcript.** Ten corpus files
were empty, a traceback, or a stub. Running the script without `--force` is the
check: it validates any existing file and atomically creates or reuses its exact
quality receipt without replacing transcript bytes. A stricter `--min-words`
may reject existing text but never authorizes provider replacement. Inspect the
named artifact and pass `--force` only when replacement is intentional. Invalid
UTF-8 fails explicitly; readers never hash replacement-decoded text.

`--existing-source` is mandatory context, not a provenance guess. For a valid
existing transcript, only known `youtube_auto` provenance permits caption-timing
enrichment. The fetched captions must match the existing text exactly after
collapsing Unicode whitespace; case, punctuation, words, and order may not
change. On a match the script writes only the timing sidecar and preserves the
transcript bytes. Manual, Whisper, unknown-provenance, and mismatched text stay
untimed and are never relabeled.

**Non-YouTube talks** (InfoQ, Vimeo, conference platforms): the orchestrator must
acquire the transcript and register its canonical vault-relative
`transcript_path` before claiming the talk. Pass the audio or video file to the
same script with `--audio`. Do not call
`mlx_whisper.transcribe()` yourself — the validation, the atomic write and the
JSON contract all live in the script, and a hand-rolled call has none of them.

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/fetch-transcript.py" {talk_label} \
  --audio "{path_to_audio_or_video}" \
  --existing-source "{talk.transcript_source|unknown}" \
  --out "{vault_root}/transcripts/{talk_id}.txt"
```

Set `transcript_source: whisper` on exit 0. Fall back to `processed_partial`
when no audio is obtainable at all. You may repeat the exact pre-registered
`transcript_path` (for example `transcripts/infoq-talk-id.txt`), but a new or
redirected return path cannot authorize citations in that return. Recover and
reclaim after source registration if the path was missing. YouTube talks may
omit the field because `youtube_id` remains the canonical fallback.
The local-media quality receipt binds trusted duration to SHA-256 of the exact
input media; moving a policy to another recording does not authorize it.
An acquisition failure preserves prior transcript and receipt bytes, including
stale quality. Do not weaken provenance or bypass the owner-binding preflight
gate to make an existing transcript eligible.

For an existing WebVTT artifact, provide an explicit collision-free output:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/vtt-cleanup.py" \
  "{vault_root}/transcripts/{source}.vtt" \
  "{vault_root}/transcripts/{talk_id}.txt" [--force]
```

The input must be a non-symlink regular file within the output transcript
directory. The schema-v2 timing receipt binds its safe relative path, exact
digest, and final cue extent. An existing output is preserved unless `--force`
explicitly authorizes full transcript/receipt replacement.
Record `transcript_source: provider_auto` when the imported VTT is known to be
the provider's automatic caption track. A VTT authored by a human remains
`manual`; the artifact receipt proves the file identity, not who produced its
text.

### Slide acquisition (per `slide_source`)

- **`pptx` / `both`** — run
  `"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/pptx-extraction.py" <path.pptx>`.
  Require extraction schema v4 for current analysis. Missing/v0/v1 output has
  unknown timing; v2 has the pre-build timing lanes but lacks raw build-list
  evidence, archive-recovery, and native/render audit receipts; v3 lacks required
  shape/image capability bindings. Re-extract v0-v3; an unknown future version
  is unusable until the reader contract is updated. A non-empty
  `archive_recovery` is degraded input, not permission to score the surviving
  slides: restore or re-export a required native deck before returning evidence.
- **`pdf`** — download via gdown (pass the bare Google Drive file id; gdown
  accepts a `url_or_id` argument, so no full download URL is needed):
  ```bash
  "{python_path}" -m gdown "{google_drive_id}" \
    -O "{vault_root}/slides/{google_drive_id}.pdf"
  ```
- **`video_extracted`** — download video at 720p, then extract slides. Never
  invoke `yt-dlp` directly; the downloader resolves the pinned binary, and a
  stale one answers every download with HTTP 403:
  ```bash
  "{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/batch-download-videos.py" \
    "{vault_root}" "{youtube_id}"
  ```
  Read the report before going further. The downloader takes any number of ids
  and writes one JSON report to stdout. Branch on this id's `results` entry,
  never on the process exit: exit 1 only means some id in the batch failed, and
  a sibling's failure never disqualifies this one. When the entry is `fail` — or
  when the report carries no `results` at all, which is what exits 2 and 3
  return alongside a typed `error` — treat the talk as having no video source,
  fall back per **Fallback** below, and carry that `reason` or `error` into the
  return. Never look for `results` in a report that has none, and never run the
  extractor against a video the report did not confirm. See the docstring at the
  top of `skills/vault-ingress/scripts/batch-download-videos.py` for the report
  shape, the exit codes, and the closed failure vocabulary.

  Only once this id's entry is `ok` or `skip`, extract:
  ```bash
  "{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/video-slide-extraction.py" \
    "{vault_root}/slides-rebuild/{youtube_id}/{youtube_id}.mp4" \
    "{vault_root}/slides-rebuild/{youtube_id}" "{youtube_id}"
  ```

  Store the complete JSON result in `structured_data.video_extraction`, then obey its
  artifact gate:

  1. An artifact with `artifact_scope: "full_frame_context"` is evidence about the
     room, stage, speaker, and PiP only. Never treat it as the authored deck, derive
     slide design from it, or copy it to `slides/{youtube_id}.pdf`.
  2. A `slide_region` artifact from a result with top-level `review_required: true`, or
     whose own `trusted_for_authored_slide_analysis` is false, is only a crop candidate.
     Inspect it against the context PDF and source video, then rerun with the checked
     coordinates as `--region LEFT,TOP,RIGHT,BOTTOM --region-verified`. An auto crop is
     always unverified. If the source is truly a full-frame screencast, use the verified
     manual region `0,0,1,1`.
  3. Only a `slide_region` artifact with
     `trusted_for_authored_slide_analysis: true` and `review_required: false` may be
     copied to `slides/{youtube_id}.pdf`, recorded as `slides_local_path`, and analyzed
     like an authored PDF deck.

  The return validator recomputes that trust from the complete schema-v4 manifest; it
  does not trust `slide_source: "video_extracted"` or an isolated artifact boolean.
  `status: "processed"` requires both the trusted manifest and the promoted top-level
  `slides_local_path: "slides/{youtube_id}.pdf"`. A trusted artifact may still finish
  `processed_partial` when another channel fails, and its verified `slide_region` may
  supply positive `static_slides` evidence even before promotion. It does not
  authorize an undetected or applicability outcome: extraction schema v4 proves
  crop/artifact identity, not that sampling, transition filtering, and deduplication
  preserved every delivered visual state. Any return without a promoted
  artifact must omit `slides_local_path` and put `slides_local_path` in `clear_fields`.
  If the manifest itself is untrusted, the result is context-only: return
  `processed_partial` and omit authored-slide structured claims such as `slide_count`,
  slide design, typography, per-slide visuals, and image counts.

  A `full_frame_context` artifact may support `delivery_video` observations about the
  room, speaker, PiP, or visible delivery phenomena when it was actually inspected. It
  never makes `static_slides` available. Apply each catalog entry's `evaluable_from`
  gate to the sources actually inspected. If none qualifies—or the source cannot
  establish that entry's evidence requirements—record the entry in `not_evaluable`.

  Keep the source MP4 and full-frame context artifact under
  `slides-rebuild/{youtube_id}/` for provenance and future re-extraction. The script
  deletes only its intermediate JPEG frames. `unique_frame_count` and artifact
  `page_count` are retained video samples, not authored `slide_count`; populate
  `structured_data.slide_count` only from corroborated deck numbering or an authored
  source.
- **`none`** — transcript-only, status `processed_partial`.
- **Fallback** — if primary slides fail but `video_url` exists, fall back to
  video extraction. A talk can still reach `processed` status this way.

### `transcript_source` records known provenance

Set `transcript_source` on the talk entry: `youtube_auto` (YouTube caption
track), `provider_auto` (another provider's automatic caption track), `whisper`
(local transcription), or `manual`. Downstream tools use it to gauge transcript
reliability.

**One exception, and only one:** `method: "existing"` from the fetcher. No fetch
ran, so provenance is unknown — leave the recorded value alone, and leave the
field absent when it was already absent. `manual` asserts a human produced the
transcript; writing it on an unknown file is a false claim that makes a
downstream reader trust ASR more than it should. Absent is honest; invented is
not.

## B. Analyze for Rhetoric & Style (NOT content)

Apply all 14 dimensions from
[rhetoric-dimensions.md](rhetoric-dimensions.md), including dimension 14
(Areas for Improvement). Follow language policy and verbatim-quote rules in
[processing-rules.md](processing-rules.md).

**Quote rule:** human-readable verbatim examples must be English-first —
`"English translation" (original text)`. The `evidence_citations[].quote` field
is the deliberate exception: return only the exact source-language span there so
persistence can match it. When the preclaim or validated return identifies a
non-English `delivery_language`, the adjacent `translation` field is mandatory,
non-empty English; it is optional for English delivery. The analysis renderer
displays translation first.

### Slides with `text_extraction_confidence: low` — inventory + pixels

`skills/vault-ingress/scripts/pptx-extraction.py` reads text out of PPTX
*shapes*. Text rendered inside a picture — the norm for AI-generated illustration decks, where titles, callout
labels, stamps, and annotations are all baked into the image — is invisible to
native text channels. On those slides the extractor emits
`text_extraction_confidence: "low"`, keeps `text_content_preview` as
native shape/table text (often empty), and — when PICTURE or background-image
blobs exist — fills distinct provenance-bearing OCR channels plus the
backward-compatible `ocr_text` aggregate via tesseract
(`text_extraction_method: "shapes+ocr"`).

**An empty `text_content_preview` on a low-confidence slide is not evidence of
a wordless slide.** It means shapes could not read the text. For affirmative OCR
inventory, read only each receipt's `recovered_text` when that same receipt has
`trustworthy_text: true`; inspect `text_channels` to learn which source was read.
Never authorize a word, citation, language finding, or pattern from `ocr_text` or
an OCR channel's aggregate `text` alone: both intentionally preserve untrustworthy
low-confidence recovery for human review.
If OCR is also empty (engine missing, unavailable/corrupt image blob, unsupported
SmartArt/chart/graphic frame, or genuinely blank art), still do not treat
absence as proof — look at the rendered page. Reading shape emptiness as
"wordless" inverts Dimension 8 — see
[known-issues.md](known-issues.md) § "Shape Extraction Is Blind to Text Baked
Into Images".

**Use the source classes for different jobs:**

| Job | Source |
|---|---|
| Word inventory, transcript cross-check, slide-text language policy, citational pattern evidence (`second-look` labels, buried jokes) | Native channel text plus OCR receipt `recovered_text` only where that receipt has `trustworthy_text: true`; aggregates are review/compatibility fields, not authority |
| Density / two-layer legibility / composition / Dim 8–13 design judgment | **Rendered page images** (OCR is not a layout oracle) |

When any slide in a deck reports `text_extraction_confidence: "low"`:

1. Read `text_channels`, `unsupported_content`, and
   `render_required_reasons` from the extraction JSON first. Each channel names
   its source, confidence, and status. `ocr_text` remains a convenient combined
   review field, but never affirmative evidence. For OCR channels, read
   channel-level `attempted`, engine/version,
   result confidence, reason, and every `ocr_receipts[]` record: each receipt
   binds one exact package `part_name` and asset SHA-256 to its outcome.
   Only a receipt with `trustworthy_text: true` authorizes its own
   `recovered_text`; `trustworthy_text: false`, `failed`, `unavailable`, or
   `genuine_empty` never authorizes a word or proves visible-text absence.
   `--no-ocr` and missing blobs are explicit
   `attempted: false` outcomes. `shapes+ocr_unavailable` means install tesseract
   next time; an `unsupported` or `unavailable` channel needs rendering or a
   specialized parser. Do not invent words.

2. Get a PDF to render for design judgment. Which one depends on `slide_source`
   — the `pptx` path never downloads one, so it has to be produced:

   | `slide_source` | PDF |
   |---|---|
   | `pdf`, `both` | already at `{vault_root}/slides/{google_drive_id}.pdf` |
   | `video_extracted` | trusted `slide_region` artifact promoted to `{vault_root}/slides/{youtube_id}.pdf`; if no trusted artifact exists, deck-layout judgment is not evaluable |
   | `pptx` | none exists — export it from the deck (below) |

   For `pptx`, export first (PowerPoint via AppleScript, LibreOffice fallback).
   A `pptx`-sourced talk may have no `slides_url`, so `google_drive_id` can be
   absent — render to a temp path, which needs no id and no cleanup:

   ```bash
   "{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/export-pdf.py" \
     "{pptx_path}" "{tmp}/deck.pdf"
   ```

   The temporary render is valid for visual judgment in this run, but it is not
   automatically a `static_slides` scoring source: raw inspection has no path
   field and persistence cannot identity-bind an ephemeral artifact. To use a
   rendered PPTX as static-slide evidence or authorize absence, promote it to a
   stable owner-declared PDF path before claiming and issue a fresh claim. The
   resolver will then retain both the distinct `native_deck` and `static_slides`
   identities; it never aliases the PPTX itself to static pages.

   If the export fails and no PDF exists for the talk, say so in the analysis,
   omit render-dependent Dimensions 8 and 13 structured fields/detections, and
   return the affected catalog outcomes as `not_evaluable` with missing source
   coverage. There is no confidence carrier for those structured fields, so do
   not put a guessed "low-confidence" value into them. Preserve only structural
   observations that the native audit actually supports. Still use
   `recovered_text` from healthy-picture receipts whose own
   `trustworthy_text` is true; channel/`ocr_text` aggregates and low-confidence,
   failed, unavailable, or empty OCR are not affirmative text evidence.

3. Render the pages and read them for design:

   ```bash
   pdftoppm -png -r 100 -f <first> -l <last> "{pdf_path}" "{tmp}/slide"
   ```

   Bind the rendered artifact and exact pages inspected by rerunning extraction:

   ```bash
   "{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/pptx-extraction.py" \
     "{pptx_path}" --rendered-pdf "{pdf_path}" \
     --inspected-pages <PAGE|START-END>
   ```

   Every current return that declares, inspects, or cites `native_deck` must
   carry the current `native_deck_audit`, even when it reports zero findings.
   `native_deck_audit.rendered_page_inspection.complete` must be true for
   explicit authored visual summary fields. A native citation needs rendered
   coverage only when its cited slide overlaps the audit's render-required
   pages; an unrelated clean-slide citation remains usable. The owner
   re-extracts the exact PPTX and matches the receipt to canonical
   `native_deck` and `static_slides` identities. If extraction reports
   `archive_recovery`, stop and repair/re-export the required deck.

4. Judge **Dimension 8** structure (dense vs minimal, room vs reward layer) and
   **Dimension 13** (Slide Design) from the rendered images. Cross-check the
   spoken word only against native channel text and per-receipt OCR
   `recovered_text` authorized by `trustworthy_text: true`.
5. Count `image_only_slide_count` from what the rendered slide *shows* (and
   from non-empty trustworthy OCR receipts), never from an aggregate alone or
   from empty shape text. A slide
   carrying baked-in text is not image-only.

Structural fields stay authoritative for what they actually measure —
`shape_count`, `background_color_hex`, `layout_name`, fonts, and
`has_text_frame_shapes` (which reports text-frame shapes, not on-screen text).

### Native timing is structure, not observed playback

Schema-v3 PPTX extraction introduced the fifth raw
build-list lane and keeps all five evidence lanes distinct on every slide:
exact animation behavior elements, visibility-targeting `<p:set>` actions,
slide transitions, audio/video timing nodes, and raw `<p:bldLst>` build entries.
Read the per-slide
`native_timing` record and the fixed-key `native_timing_summary`; do not derive
an `animated` verdict merely from `<p:timing>` presence.

The provenance says `observed_playback: false` deliberately. A motion element
establishes that a `<p:animMotion>` behavior exists in package XML, not that it
executed, looked smooth, or targeted the perceived object. Audio/video timing is
not shape motion. Raw counts also do not establish concurrency or effect order,
so multiple effect/scale/rotation elements alone cannot score
`composite-animation`; inspect target/timing relationships or delivery video.
Build-list records establish only that PowerPoint stored paragraph, diagram,
OLE-chart, or graphic build metadata; they do not establish reveal order or a
visible state and are never merged into visibility actions. Markup-compatibility
Choice/Fallback branches are counted as stored, not resolved for the presenter
that delivered the talk.

Conversely, zero native timing does not rule out progressive builds implemented
as adjacent duplicate slides. Ordered rendered states with controlled cumulative
changes are valid `progressive-reveal` evidence; they are not native animation
evidence and must not be relabeled as observed motion.

## B2. Tag Presentation Patterns

Scan observations against the pattern taxonomy at
`skills/presentation-creator/references/patterns/_index.md`. Skip patterns
marked `observable: false`; do not infer hidden preparation or provenance from a
polished result. For each detection, record confidence (strong/moderate/weak), a
brief evidence explanation, and at least one direct source citation through a
channel allowed by the pattern's `evidence_channels`. Timing claims require a
verified timed transcript or direct video review; sequence claims require the
actual consecutive slides. Native-deck structure can support motion/build
claims only when the entry's gate permits `native_deck`; observed playback and
delivery claims require direct video review.
Do not cite a video interval unless you inspected that interval. Compute the
per-talk score only through the `build-score-basis.py` step below. Record each
detection's confidence, but do not calculate or write `pattern_score` or
`pattern_score_basis` yourself; the script derives both through the scoring
owner.
See [processing-rules.md](processing-rules.md) for full tagging rules.

Use `evaluable_from` for moderate/weak detections,
`strong_evaluable_from` (or its base-gate default) for strong detections, and
`absence_evaluable_from` (or its base-gate default) for undetected outcomes. A
valid positive detection takes precedence over an unavailable absence gate.
Every `source_comparison` detection must include `evidence_sources_used` as the
exact qualifying underlying source group; do not include that field on any
other detection. Its citations must collectively locate proof from every named
underlying source. A `talk_metadata` citation may supplement a detection but
cannot replace its qualifying source/outcome gate.

### Record exact source inspection coverage

Return v4-v7 requires a receipt for the material you actually inspected, not just
a list of artifacts that happened to exist. `pattern_observations.evidence_sources`
must be the exact source-name set represented by `source_inspection`:

```json
[
  {"source": "transcript", "line_ranges": [[1, 180], [181, 360]]},
  {"source": "static_slides", "page_ranges": [[1, 18], [20, 42]]},
  {"source": "native_deck", "page_ranges": [[1, 42]]},
  {"source": "delivery_video", "time_ranges": [[0, 600.0], [615.0, 1800.0]]},
  {
    "source": "source_comparison",
    "evidence_sources_used": ["static_slides", "native_deck"],
    "comparison_scope": "full"
  },
  {
    "source": "source_comparison",
    "evidence_sources_used": ["transcript", "delivery_video"],
    "comparison_scope": "partial"
  }
]
```

Use inclusive positive line/page ranges and finite non-negative video seconds.
Ranges are ascending and non-overlapping; adjacent ranges are allowed. Do not
fill gaps you did not inspect. `comparison_scope: "full"` asserts that the
comparison covered every named member in full; use `partial` otherwise. More
than one comparison record is allowed only when the exact underlying groups
differ. Artifact coexistence without actual comparison gets no comparison
record.

Canonical `coverage_complete` means the declared ranges covered that artifact;
it is not a blanket negative-evidence grant. Bare `native_deck`, bare
`delivery_video`, and video-extracted static pages remain positive-only because
their receipts do not prove modality completeness. A `full` comparison likewise
supports positive comparison claims but cannot authorize absence or force a v5
applicability assessment until an alignment/modality receipt exists. Persistence
adds engine-owned `absence_capability_complete` and
`absence_capability_reason`; workers must not return either field.

The worker returns only those ranges/groups/scopes. Do not add line/page counts,
verified duration, `coverage_complete`, artifact root/path/hash fields, timing
artifact identity, or comparison `artifact_identities`; persistence derives
them from the preclaim artifacts and rejects false bounds or source claims.

## C. Return JSON

Return exactly the shape in [schemas-db.md](schemas-db.md). `status`,
`slide_source`, all five catalog-feedback lanes, and the complete pattern score
object are mandatory. Match `return_schema_version` to the active claim:
fresh claim-schema v7 with `required_return_schema_version: 7` emits return v7.
Saved claim schemas v1/v2 authorize only saved return schemas v1/v2; claim
schema v3 authorizes only return schema v3, claim schema v4 authorizes only
archival return schema v4, claim schema v5 authorizes only return schema v5,
and claim schema v6 authorizes only return schema v6. These are saved legacy
replay generations, never fresh ones.
Recover a live legacy lease and issue a fresh v7 generation; never mutate its
claim or attach a newer return to it.
Snapshot versions 2–7 require `rhetoric_notes` and `areas_for_improvement` to
contain substantive non-whitespace analysis. Empty strings remain valid for
`adherence_assessment`, `new_patterns`, and
`summary_updates` where documented; the adherence no-assessment sentinel must be
exactly `""`, never whitespace. `transcript_source` is conditional provenance:
omit the key when the fetcher reports `existing` and the DB has no known provenance;
never emit JSON `null`.
`slides_local_path` is optional for ordinary returns but mandatory for
`status: "processed"` with `slide_source: "video_extracted"`.
Omit `processed_date`; the persistence writer owns one normalized timestamp for
the complete queue batch and the analysis writer renders that stored value.

For returns v5-v7, always return `"adherence_assessment": ""` exactly and omit
`adherence_comparison`. The worker cannot know the canonical, engine-owned talk
`opportunity_coverage_identity`. Only an owner-side consumer after persistence
may compare a talk against a schema-v2 baseline, and only when the identities
match exactly, comparison status is available, and at least ten talks share the
same identity.

Never recalculate after inspecting the talk, substitute the post-batch cohort,
parse Section 15, or infer a cohort from processing dates. Legacy v1–v4
adherence prose is archival `legacy-unverified`, not a current numeric input.

When returning `per_slide_visual`, use the exact seven-key row contract and
cover slides 1 through `slide_count` once in order; legacy aliases and row-local
notes are invalid. `content_type` and `image_composition` use the closed schema
vocabularies. Keep `image_source_distribution` provenance-only and integer-valued:
visual resemblance does not prove AI, stock, or speaker authorship, so use an
`unknown` count where origin is unverified rather than adding a note string. Whenever
you return that map, also return a non-empty sibling
`image_source_distribution_basis` string. State whether the counting unit is a
slide, page, or asset; how one class wins when multiple images or sources occur;
which provenance evidence supports the classes; and how unverified origins enter
the `unknown` count.

Version-2 through version-7 supplied fields are snapshots: an empty string, array,
or declared map
replaces an older value when that field permits emptiness, while an omitted field
preserves it. Use `clear_fields`
when the re-analysis must delete a field rather than replace it. Each entry is
an analysis-owned dotted path such as `verbatim_examples.jokes` or
`structured_data.slide_count`. An untrusted or unpromoted
video-extraction result must include `slides_local_path` here so an older trusted
deck path cannot survive the corrective merge; also clear any stale authored-slide
structured fields disproved by the new evidence.

Treat every documented structured object as one complete snapshot. Do not rely on
nested dictionary union. Put genuinely additive experimental data under
`structured_data.extensions.<producer_namespace>`; an undeclared top-level object
is rejected until its replacement policy is documented and registered.

Minimal processed structure for a fresh v7 claim:

```json
{
  "filename": "2026-01-01-example.md",
  "return_schema_version": 7,
  "queue_claim": {
    "run_id": "reparse-2026-07",
    "batch_id": "25",
    "reprocess_generation": 1
  },
  "status": "processed_partial",
  "transcript_source": "youtube_auto",
  "slide_source": "none",
  "rhetoric_notes": "Dimensions 1-13 analysis...",
  "areas_for_improvement": "Dimension 14 analysis...",
  "adherence_assessment": "",
  "new_patterns": "",
  "summary_updates": "",
  "structured_data": {
    "delivery_language": "en",
    "co_presenter": false
  },
  "verbatim_examples": {},
  "pattern_observations": {
    "evidence_sources": [
      "transcript"
    ],
    "source_inspection": [
      {
        "source": "transcript",
        "line_ranges": [
          [
            1,
            360
          ]
        ]
      }
    ],
    "patterns_detected": [
      {
        "pattern_id": "narrative-arc",
        "confidence": "strong",
        "evidence_source": "transcript",
        "evidence": "Four named acts build one argument.",
        "evidence_citations": [
          {
            "source": "transcript",
            "channel": "transcript",
            "quote": "First, understand the problem before trying to fix it."
          }
        ]
      }
    ],
    "antipatterns_detected": [],
    "applicability_assessments": [],
    "not_evaluable": []
  },
  "catalog_feedback": {
    "unmatched_observations": [],
    "confusable_pairs": [],
    "definition_problems": [],
    "scoring_problems": [],
    "tensions": []
  }
}
```

This block is complete except for `pattern_observations.pattern_score` and
`pattern_observations.pattern_score_basis`, which a script fills in. Do not
write, calculate, or merge either field by hand:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/build-score-basis.py" \
  batch-returns.json > completed-returns.json
```

Input is one return object or an array of them; output is those same returns
with both fields set, ready for `validate-returns.py`. Exit `0` means the batch
is complete. Exit `2` means unreadable, malformed, or duplicate-filename input:
a diagnostic goes to stderr, stdout stays empty, and you must stop rather than
validate a partial batch. The arithmetic, weight table, and basis shape belong
to `skills/vault-ingress/scripts/return_validation.py`; nothing here restates
them.

The example claims one inspected source. Add a source only with the audit
behind it: `native_deck` requires the current
`structured_data.native_deck_audit`, `static_slides` from a video-extracted deck
requires the schema-v4 `structured_data.video_extraction` manifest, and
`delivery_video` requires its own declared local artifact. A claimed source
without its audit is rejected.

The raw worker return must not include engine-owned `evidence_schema_version`,
`pattern_outcomes`, or `opportunity_coverage_identity`. Persistence derives the
exhaustive sorted outcome ledger and its identity from the validated raw lanes.

For a comparison detection, the detection object additionally carries, for
example, `"evidence_sources_used": ["static_slides", "native_deck"]`.
The array is duplicate-free, excludes the `source_comparison` marker, and must
exactly match one qualifying catalog group.

Fresh work arrives only under a claim-v7 payload that explicitly requires return
v7. Saved claims v1/v2 remain replayable only with saved returns v1/v2; claim v3
requires return v3, claim v4 requires archival return v4, claim v5 requires
return v5, and claim v6 requires return v6. Recover a live legacy lease without
rewriting it; otherwise issue a new v7 claim. Never alter a
saved claim payload, invent a schema, or attach a newer return to a legacy claim.

In raw v4-v7 citations, return only `source`, `channel`, and the locator you
actually observed: transcript `quote` (plus optional `translation`), slide
`slide_numbers`, video `start_seconds`/`end_seconds`, or metadata `field`.
Never return transcript line/timestamp matches, artifact root/path/hash fields,
timing-artifact fields, or metadata `value`/`owner_value_after_return`; those are
engine-owned. Omit catalog-owned `dimensions`; if retained for compatibility,
it must match the exact catalog order. V4/v5 `not_evaluable` entries contain only
`pattern_id` and `reason_code`: `missing_required_source_coverage` for an
incompletely covered absence gate, `absence_not_authorized_by_catalog` for an
explicit positive-only entry, `missing_applicability_source_coverage` for a v5
conditional entry whose applicability gate is incomplete, or
`source_gate_pending_owner_review` for an observable entry still missing an
approved positive gate. V5 additionally returns one exact source-located
`applicability_assessments` row for every nondetected conditional entry whose
applicability gate is complete. An ungated entry fails closed and cannot be
returned as detected or silently absent.

Before returning, run the deterministic gate:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/validate-returns.py" batch-returns.json
```

Fix every reported error. Do not weaken a catalog ID, polarity, observability,
evidence, confidence, score, or status error into a prose caveat.
For newly emitted work, also require the validator report's matching
`pattern_scoring_generations` entry to have `status: "current"` and an empty
reasons array. `legacy_unbaselineable` is replay compatibility, not an accepted
new-work outcome.
