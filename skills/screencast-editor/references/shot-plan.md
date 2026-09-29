# Shot plan contract

`shot-plan.json` drives `build-project.py`, `audit-framing.py`, and
`framing-stills.py`. All times are source seconds in the recording.

```json
{
  "title": "Good is better than perfect",
  "canvas": {"width": 1920, "height": 1080, "menubar": 28},
  "inset": {"height": 324, "x": 640, "y": -346, "corner_radius": 120,
            "border_color": "#A78BFA", "border_width": 4},
  "noise_removal": 0.8,
  "shots": [
    {"start": 0.70, "end": 20.10, "kind": "speaker", "label": "Intro"},
    {"start": 20.10, "end": 35.20, "kind": "screen", "label": "The roles",
     "cues": [[20.10, 1.06, 0.5, 0.5], [22.0, 1.7, 0.14, 0.72]]}
  ]
}
```

- `shots` tile the edit with no gap or overlap. The first start is the head
  trim, the last end the tail. `camtasia_model.load_plan` enforces the minimum
  shot length (`MIN_SHOT_SECONDS`).
- `kind: "speaker"` is the presenter full-frame. `kind: "screen"` is the screen
  with the presenter inset.
- A cue is `[time, zoom, x, y]`: the framing that is complete at `time`, reached
  by an ease of `MOVE_SECONDS`. `(x, y)` is the focal point in normalized source
  coordinates, top-left origin. The first cue sits at the shot start.
- `zoom` is relative to fit. `camtasia_model.min_zoom(canvas)` is the floor: the
  smallest zoom that keeps the macOS menu bar (`canvas.menubar` pixels at fit)
  off screen without exposing a canvas edge. The validator rejects anything
  below it, and every framing is clamped the same way.
- `inset` is in canvas pixels, center-relative, y up. `noise_removal` is the
  Camtasia AI Noise Removal amount on the mic; 0 disables it.

## Editorial rules

- The presenter owns the opening, all commentary, and the close. The first
  shot is the presenter saying what the viewer will get.
- The screen appears while the words point at it and leaves when they stop.
- Cut only between sentences, using the transcript's word onsets: end a shot
  after the last word of a sentence and before the first of the next.
- Enter each screen shot wide (zoom 1.06), then push in to what is named.
- Frame a text view (an issue, a doc) as its whole column, left of the inset:
  zoom 1.4 with focal x 0.517 fits a GitHub issue on a 1920x1080 canvas. Larger
  zooms cut words at the edge.
- Hold a framing while the pointer rests on something in it. Never pan away
  from where the presenter points; `audit-framing.py` checks this.
- Do not zoom back out just before a cut to the presenter: the cut does it.
