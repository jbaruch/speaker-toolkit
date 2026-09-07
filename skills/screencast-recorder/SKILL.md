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
lane is issue #364 and is not implemented; the design it must satisfy is #369.

Resolve the absolute path of this loaded `SKILL.md`, then set
`speaker_toolkit_root` to the plugin root two directories above the directory
containing this file. Never derive it from the consumer working directory.
Treat `{speaker_toolkit_root}` as absolute in every toolkit-owned command;
sequence, media, and output paths remain consumer-owned.

## Step 1 — Resolve the interpreter

Every command below runs under `{python_path}`, which this skill does not invent.
Read `config.python_path` from the vault's `tracking-database.json` and set
`python_path` to that exact value — it is the interpreter authority for every
operational command here, exactly as in the other toolkit skills.

If `python_path` is absent, empty, or cannot execute, stop and repair the
configuration through its owner:

```
Skill(skill: "vault-ingress")
```

Its Step 1 owns the runtime configuration. Never fall back to whichever `python3`
happens to be on `PATH`.

Proceed immediately to Step 2.

## Step 2 — Obtain the sequence description

The recording rig emits one JSON file describing the take: delivery resolution,
narration words with real timestamps, per-clip entry/exit manifests and events,
and the storyboard rows with their machine-checkable requirements. Shape and
every field: `references/sequence-contract.md`.

The approved storyboard itself stays prose and stays human-approved. Conditions
like "leave room for the laugh" are judgments no verifier makes. This file
carries only the half a machine can decide.

Proceed immediately to Step 3.

## Step 3 — Verify

```bash
"{python_path}" "{speaker_toolkit_root}/skills/screencast-recorder/scripts/verify-storyboard.py" <sequence.json>
```

Exit 0 when every checked axis passes, 1 on any finding, 2 on usage error. The
verdict names each finding's axis, subject, and what was expected against what
was observed. Proceed immediately to Step 4.

## Step 4 — Read the unverified axes before reporting a pass

An axis reads `unverified` for either of two reasons, and neither is a pass.

`axes.pixels` is always `unverified`: this lane reads structured state and cannot
examine encoded frames, so three of the design's ten negative tests are outside
it — a click invisible in the encode, a label unreadable in the delivered pixels
rather than in the measurement, and OS chrome inside the crop.

Any other axis reads `unverified` when no row in the sequence declared a
requirement on it. A take that asserts nothing about geometry has not passed
geometry; `unverified_axes` names which case applies.

Report those as unchecked. Never restate an `unverified` axis as a pass.

If findings exist, return to the earliest invalid artifact — the storyboard row,
the clip, or the narration take. Do not accumulate local timing, cursor, or crop
patches against a take that a gate already rejected. Finish here.
