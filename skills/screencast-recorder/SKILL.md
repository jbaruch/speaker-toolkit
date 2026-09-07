---
name: screencast-recorder
description: >
  Verify a recorded screen sequence against its approved storyboard: route and
  data revision, content framing and label readability, deliberate pans, the
  pointer landing on what it clicks, clip-to-clip continuity, and whether each
  visual proof occurs while its phrase is actually spoken. Use when checking a
  demo or screencast take before shipping it, when a recorded sequence must be
  proved rather than trusted, or when a clip join must be shown to be invisible.
  Verification only — this skill does not record; the recording lane is issue
  #364 and is not implemented.
user_invocable: true
---

# Screencast Recorder — Verification Lane

Process steps in order. Do not skip ahead.

This skill verifies a take. It does **not** record one. The unattended recording
lane is tracked in issue #364 and is not implemented; the design it must satisfy
is issue #369. What exists today is the oracle those depend on — a recorded
sequence can be judged against its storyboard instead of trusted because the
right page loaded.

Resolve the absolute path of this loaded `SKILL.md`, then set
`speaker_toolkit_root` to the plugin root two directories above the directory
containing this file.

## Step 1 — Obtain the sequence description

The recording rig emits one JSON file describing the take: delivery resolution,
narration words with real timestamps, per-clip entry/exit manifests and events,
and the storyboard rows with their machine-checkable requirements. Shape and
every field: `references/sequence-contract.md`.

The approved storyboard itself stays prose and stays human-approved. Conditions
like "leave room for the laugh" are judgments no verifier makes. This file
carries only the half a machine can decide.

Proceed immediately to Step 2.

## Step 2 — Verify

```bash
"{python_path}" "{speaker_toolkit_root}/skills/screencast-recorder/scripts/verify-storyboard.py" <sequence.json>
```

Exit 0 when every checked axis passes, 1 on any finding, 2 on usage error. The
verdict names each finding's axis, subject, and what was expected against what
was observed. Proceed immediately to Step 3.

## Step 3 — Read the unverified axes before reporting a pass

`axes.pixels` is always `unverified`, never `pass`. This lane reads structured
state; it cannot examine encoded frames, so three of the design's ten negative
tests are outside it — a click that is invisible in the encode, a label
unreadable at delivery size in the pixels rather than in the measurement, and OS
chrome inside the crop.

Report those as unchecked. An axis called passing without being examined is a
false assurance, and false assurance from a green driver log is the specific
failure this verification doctrine exists to prevent.

If findings exist, return to the earliest invalid artifact — the storyboard row,
the clip, or the narration take. Do not accumulate local timing, cursor, or crop
patches against a take that a gate already rejected. Finish here.
