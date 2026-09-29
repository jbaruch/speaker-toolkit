# Camtasia file formats

What the scripts read and write, as observed in Camtasia 2025 for Mac.

## Project bundle

A `.cmproj` directory holding `project.tscproj` (JSON), `bookmarks.plist`,
`docPrefs` (property lists), and `media/`, `originals/`, `recordings/`. While a
project is open, Camtasia keeps a `~project.tscproj` beside it.

- Time is in ticks at the project's `editRate`. Frame snapping is `tick` in
  `skills/screencast-editor/scripts/camtasia_model.py`.
- Tracks live at `timeline.sceneTrack.scenes[0].csml.tracks`, with display
  names in `timeline.trackAttributes`. Each clip has `start`, `duration`
  (timeline ticks), `mediaStart`, `mediaDuration` (source ticks), and `scalar`
  (speed as an exact fraction such as `"57/47"`, or 1).
- A screen + camera recording opens as track 0 `ScreenVMFile` and track 1
  `UnifiedMedia` (camera `video` plus mic `audio`).
- Position is `translation0`/`translation1` in canvas pixels, center-relative,
  y up. `scale0`/`scale1` are relative to source pixels: 0.5 fits a 3840x2160
  source to a 1080-high canvas.
- An animated parameter is `{"type": "double", "defaultValue", "interp": "eioe",
  "keyframes": [{"time", "endTime", "duration", "value"}]}` with times relative
  to the clip, plus `animationTracks.visual` entries `{"endTime", "duration"}`.
- The rounded inset is the native `RoundCorners` effect followed by an
  alpha-aware `Border` (`type` 1); AI noise removal is the audio effect
  `VSTEffect-DFN3NoiseRemoval`. Definitions: `skills/screencast-editor/scripts/camtasia-effects.json`.

## Dynamic captions

- Recognition is stored once, on the source: `sourceBin[].sourceTracks[type 2]
  .parameters.transcription.keyframes`, one `{"time", "value"}` per word in
  source ticks. `%GAP` marks the start of a pause; the first keyframe is a
  `%GAP` at 0.
- The caption itself is a `Callout` clip on its own track whose
  `def.modifier` is `dynamicCaption`. Box size is `def.width`/`def.height`,
  position the clip's `translation0`/`translation1`, and text size both
  `def.font.size` and the `fontSize` entry of `def.textAttributes`.
- `def.dynamic-caption-new-paragraph-for-each-sentence` starts a caption block
  at each sentence, so punctuation in the words changes the blocks.

## Recording (`.trec`)

An MP4 with three streams: the TSCC2 screen, the H.264 camera, and AAC mic.
The pointer is not drawn into the screen stream. A top-level `TSCM` atom
(64-bit size) holds records: `<u32 count> "DATA" <u64 length> <16-byte GUID>
<payload>`, with the length spanning the record from the count field.

- GUID `2b7b6af2-7a1f-11e2-83d0-0017f200be7f` (raw bytes as listed) is the
  pointer path: `<u32 version> <u32 16>` then `<f64 seconds> <i32 x> <i32 y>`
  samples in global points.
- GUID `2b7b6af6-...` is the capture rectangle: `<u32 version> <u32 24>` then
  `<f64> <i32 x> <i32 y> <i32 width> <i32 height>`.
