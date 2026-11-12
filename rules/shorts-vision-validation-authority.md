---
alwaysApply: false
applyTo: "skills/shorts-producer/scripts/vision.swift, skills/shorts-producer/scripts/prepare-clip.py, skills/shorts-producer/scripts/verify-short.py — when changing how the shorts producer asks Apple Vision for faces or QR payloads"
description: Authority of record for the shorts producer's Apple Vision boundary under the Platform-Bound Untestable Carve-Out
---

# Shorts Vision Validation Authority

## Carve-Out Claimed

- `jbaruch/coding-policy: testing-standards` Platform-Bound Untestable Carve-Out.
- Qualifying condition: Apple's Vision framework is a proprietary macOS runtime. The suite that tests the shorts producer runs on Ubuntu, and the macOS lane runs only the artifact-platform contracts.
- Scope: Apple Vision face and QR detection only. The word-timing layer is governed by `rules/transcript-fetch-authority.md`.

## Covered Artifact

- Exempt: `skills/shorts-producer/scripts/vision.swift` and its install mirror `vision.swift.txt`, in both modes, `faces` and `qr`. `vision_script` in `skills/shorts-producer/scripts/shorts_plan.py` copies whichever is present to a runnable name, and that copy is tested.
- Exempt: the two calls that run it, `detect_faces` in `skills/shorts-producer/scripts/prepare-clip.py` and `_scan_qr` in `skills/shorts-producer/scripts/verify-short.py`. Each returns Vision's JSON rows; `detect_faces` only turns each frame's file name into its time.
- Not exempt: everything that consumes the detections. Region filtering, crop size, smoothing, keyframes, the crop expression, caption alignment and the edit-budget refusal, caption timing, layout, rendering and the other verification checks are deterministic and tested.

## Precondition 1 — CI-Runnable Pieces Are Extracted and Tested

- `tests/test_shorts_producer.py` feeds synthetic face rows to the crop tracker and asserts region filtering, crop size, smoothing and the refusal when too few faces fall in the region.
- The same file renders a short end to end from a synthetic recording, deck page, word timings and face rows, then runs every verification check against it, with the QR scan's payloads supplied in place of Vision's.

## Precondition 2 — Manual Validation Procedure

Run on macOS against a real processed talk with a visible speaker and a shownotes link.

1. Run the skill through Step 5 for one clip. Observe: `faces.json` has a face on the speaker in most frames, and `contact.jpg` shows red boxes on the speaker's face.
2. Complete Steps 6 and 7. Observe: the rendered speaker panel keeps the speaker's face in frame for the whole clip.
3. Run Step 8. Observe: `qr_payloads` holds the plan's `qr_url` and `ok` is true.
4. Set the clip's `qr_url` to a different https link without re-rendering and rerun Step 8. Observe: it fails, naming the QR mismatch.

A pass requires all four observations.

## Scope Limits

- The carve-out covers only the Vision requests named above. It does not extend to ffmpeg, Pillow or qrcode, which CI installs and exercises.
- Adding another exempt artifact requires naming it here with its own validation procedure.
