# Sequence contract

Input and output for `scripts/verify-storyboard.py`. The verifier reads structured
state only; it never opens media.

## Why the input is structured

The approved storyboard (e.g. `SCREEN-PLAN.md` in a demo repo) is prose, on
purpose — a human approves visual intent, and conditions like "leave room for the
laugh" are judgments, not predicates. The recording rig emits the machine-checkable
half as the JSON below. Parsing prose pass-conditions is out of scope
(`rules/script-delegation.md` The Regex Trap).

## Input

```json
{
  "delivery":  { "width": 1920, "height": 1080, "min_label_px": 14, "scale": 1.0 },
  "narration": { "source": "actual_word_timestamps",
                 "words": [ { "word": " Hi,", "start": 0.0, "end": 0.62 } ] },
  "clips":     [ { "id": "a0-hook", "entry": {manifest}, "exit": {manifest},
                   "events": [ {event} ] } ],
  "rows":      [ { "id": "a0-hook-r1", "clip": "a0-hook", "phrase": "...",
                   "proof_frame_t": 3.1, "require": {…} } ],
  "seam_tolerances": { "scroll": 2, "transform": 2 }
}
```

`narration.source` must be `actual_word_timestamps`. Any other value fails the
time axis: WPM predicts whether a script is deliverable, never that a visual and
a phrase coincide.

`delivery.scale` converts a recorded label height to its delivered height. A
label readable in the browser and unreadable in the encode is the case
`min_label_px` exists to catch.

### Manifest

`route`, `data_fingerprint`, `viewport {width,height}`, `zoom`,
`scroll {x,y}`, `transform {pan_x,pan_y,zoom}`, `tabs` (ordered), `active_tab`,
`cursor [x,y]`, `labels [{text, height_px}]`.

### Events

`{"type":"pan","axis":"x","delta":-640,"t":2.0}` ·
`{"type":"click","t":3.1,"pointer":[x,y],"target_rect":[x,y,w,h]}`

### Row requirements

A phrase spoken more than once is matched at **every** occurrence; a proof
frame inside any of them passes.

`route` · `data_fingerprint` · `visible_labels` · `content_bounds [x,y,w,h]` ·
`margin_px` · `pan {axis,min_abs_delta}` · `click_on_target`

## Output

```json
{ "ok": false,
  "axes": {"semantic":"fail","geometry":"pass","motion":"pass","time":"pass",
           "pixels":"unverified"},
  "unverified_axes": {"pixels": "requires encoded frames; not checked by the manifest lane"},
  "finding_count": 1,
  "findings": [ {"code":"stale_data","axis":"semantic","subject":"a0-hook-r1",
                 "message":"...", "expected":"…","actual":"…"} ],
  "counts": {"rows":1,"clips":2,"seams":1} }
```

An axis is `unverified` for either of two reasons, and neither is a pass:

- **`pixels`, always** — this lane cannot examine encoded frames.
- **Any axis no row exercised** — a sequence that asserts nothing about geometry
  has not passed geometry.

`unverified_axes` says which case applies. An axis reported as passing without
being examined is a false assurance, which is the failure the verification
doctrine exists to prevent — and which the first draft of this script committed
by passing an empty sequence on every axis.

## Evidence is required before judgement

A requirement whose evidence the take does not carry is **refused**, never
passed: `require.content_bounds` with no `entry.viewport`, `visible_labels` with
no `entry.labels`, `click_on_target` with a click lacking `pointer`/`target_rect`,
or `proof_frame_t` with no `narration.words`. Each yields `evidence_missing`
naming the requirement and the absent field, **on the axis that requirement is
judged on** — a missing `viewport` fails `geometry`, not `semantic`, so an axis
can never read `pass` while its own evidence is absent.

A seam field absent from either manifest is refused for the same reason: two
absences compare equal, and equality between nothing and nothing is not
agreement.

A document that does not satisfy the contract exits 2 with the violation named,
rather than failing later on a missing key. Validation covers structure
(`clips`/`rows` as lists of objects with non-empty string ids), completeness
(`scroll` carries `x`/`y`, `transform` carries `pan_x`/`pan_y`/`zoom`, a
`proof_frame_t` has a `phrase`), and **finiteness of every number**.

Finiteness is not pedantry: JSON admits `NaN`, and every comparison against
`NaN` is false, so a `NaN` measurement or threshold satisfies whatever it is
tested against. A `bool` is an `int` in Python and is rejected as a coordinate.

Exit 0 when every checked axis passes, 1 on any finding, 2 on usage error.

## Finding codes

| code | axis | means |
|---|---|---|
| `route_mismatch` | semantic | clip is not on the required route |
| `stale_data` | semantic | route correct, rendered data is the wrong revision |
| `required_label_absent` | semantic | a label the phrase names is not in the frame |
| `seam_state_mismatch` | semantic | a seam does not carry a field across unchanged |
| `seam_tab_mismatch` | semantic | tab set or active tab changed across a seam |
| `content_clipped` | geometry | required content not fully inside the viewport at margin |
| `label_below_readable_size` | geometry | a required label is under `min_label_px` at delivery scale |
| `pan_not_performed` | motion | a required deliberate pan is absent |
| `click_absent` | motion | a required visible click is absent |
| `cursor_off_target` | motion | the pointer was not on the target when the click fired |
| `timing_not_from_actual_words` | time | synchronisation asserted without transcribed timestamps |
| `phrase_not_spoken` | time | the row's phrase is absent from the narration |
| `proof_outside_phrase` | time | the proof frame falls outside every spoken occurrence |
| `evidence_missing` | varies | a requirement cannot be judged; the take lacks its evidence |
| `sequence_empty` | semantic | the sequence declares no rows, so it verifies nothing |

## Coverage against the #369 negative tests

Seven of ten are checked here. Three need encoded frames and are not:

| # | negative test | here |
|---|---|---|
| 1 | correct route but wrong/stale data | `stale_data` |
| 2 | workflow present but partly clipped | `content_clipped` |
| 3 | missing horizontal pan | `pan_not_performed` |
| 4 | labels below readable size | `label_below_readable_size` (from recorded measurement; pixels must confirm) |
| 5 | cursor off the clicked target | `cursor_off_target` |
| 6 | click not visible in encoded frames | **pixel lane — not checked** |
| 7 | scroll/pan/zoom mismatch across a seam | `seam_state_mismatch` |
| 8 | different tab set or active tab across a seam | `seam_tab_mismatch` |
| 9 | menu bar / system clock in crop | **pixel lane — not checked** |
| 10 | timing from predicted WPM | `timing_not_from_actual_words` |
