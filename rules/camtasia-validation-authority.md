---
alwaysApply: false
applyTo: "skills/screencast-editor/scripts/build-project.py, skills/screencast-editor/scripts/apply-captions.py, skills/screencast-editor/scripts/camtasia_model.py, skills/screencast-editor/scripts/camtasia-effects.json — when changing what the screencast editor writes into a Camtasia project"
description: Authority of record for the Camtasia rendering boundary's Platform-Bound Untestable Carve-Out
---

# Camtasia Validation Authority

## Carve-Out Claimed

- `jbaruch/coding-policy: testing-standards` Platform-Bound Untestable Carve-Out.
- This rule is the authority of record satisfying precondition 3: it names the carve-out, the exempt artifact, and the manual validation procedure.
- Qualifying condition: Camtasia is a licensed macOS and Windows GUI application with no headless mode, so no CI runner can open a project and render it.

## Covered Artifact

- Exempt: Camtasia's acceptance and rendering of a project written by `skills/screencast-editor/scripts/build-project.py` or modified by `skills/screencast-editor/scripts/apply-captions.py`. That is whether the app opens the bundle, draws the planned framing and inset, and shows the corrected dynamic captions.
- Not exempt: every byte those scripts write. Timing, framing geometry, clamping, effect ownership, caption alignment, staging, and refusal paths are deterministic and tested.

## Precondition 1 — CI-Runnable Pieces Are Extracted and Tested

- `tests/test_screencast_editor.py` builds projects from a synthetic template shaped like Camtasia's screen + camera recording layout. It asserts clip placement, keyframes, inset scale, effect preservation, noise-removal disablement, staging, rerun behaviour, and caption rebuilding against synthetic transcript keyframes.
- Framing geometry is tested at the menu-bar boundary and across a zoom and focal-point sweep.

## Precondition 2 — Manual Validation Procedure

Run on macOS with Camtasia installed, against a real screen + camera recording.

1. Run the skill through Step 8, then open the generated bundle in Camtasia. Observe: it opens without a missing-media prompt, and the timeline shows three tracks named Screen, Presenter inset + audio, and Speaker full frame.
2. Scrub every screen shot. Observe: each zoom ends on its cue, no canvas edge or menu bar shows, and the rounded inset sits bottom right with its border.
3. Scrub every speaker shot. Observe: the presenter fills the frame and no inset shows.
4. Play across three cuts. Observe: the audio is continuous with no doubled voice.
5. Add dynamic captions, save, close, run the skill's Step 10 (`apply-captions.py`), and reopen. Observe: the corrected words show with the new size and position, a new caption block starts at each sentence, and the highlight tracks the speech.
6. Close the project and rerun Step 10. Observe: it succeeds and writes a second backup. With the project open, observe: it refuses and leaves the file unchanged.

A pass requires all six observations. The skill's Step 10 is not complete until steps 5 and 6 pass.

## Scope Limits

- The carve-out covers only Camtasia's acceptance and rendering of the files named above. It does not extend to another script or to ffmpeg, which CI installs and exercises.
- Adding a second exempt artifact requires naming it here with its own validation procedure.
