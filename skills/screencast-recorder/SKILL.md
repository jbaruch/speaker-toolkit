---
name: screencast-recorder
description: >
  Verify a recorded screen sequence against its approved storyboard: route and
  data revision, content framing and label readability, deliberate pans, the
  pointer landing on what it clicks, clip-to-clip continuity, and whether each
  visual proof occurs while its phrase is actually spoken. Use when checking a
  demo or screencast take before shipping it, when a recorded sequence must be
  proved rather than trusted, or when a clip join must be shown to be invisible.
  Verification only — this skill does not record.
user_invocable: true
---

# Screencast Recorder — Verification Lane

Process steps in order. Do not skip ahead.

This skill verifies a take. It does **not** record one.

Resolve the absolute path of this loaded `SKILL.md`, then set
`speaker_toolkit_root` to the plugin root two directories above the directory
containing this file. Never derive it from the consumer working directory.
Treat `{speaker_toolkit_root}` as absolute in every toolkit-owned command;
sequence, media, and output paths remain consumer-owned.

## Step 1 — Resolve the interpreter

```bash
python3 "{speaker_toolkit_root}/skills/screencast-recorder/scripts/resolve-interpreter.py" <vault_root>
```

Emits `{"ok": true, "python_path": ..., "vault_root": ..., "database": ...}`.
Set `python_path` from that value; it is the interpreter authority for every
command below.

Exit 1 means it could not be resolved — the diagnostic names the cause. Repair
through its owner:

```
Skill(skill: "vault-ingress")
```

Never fall back to whichever `python3` is on `PATH`.

Proceed immediately to Step 2.

## Step 2 — Obtain the sequence description

The recording rig emits one JSON file describing the take: delivery resolution,
narration words with real timestamps, per-clip entry/exit manifests and events,
and the storyboard rows with their machine-checkable requirements. Shape, every
field, and every finding code:

```text
skills/screencast-recorder/references/sequence-contract.md
```

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

`axes.pixels` is always `unverified`. Three checks are outside this lane: a click
visible in the encoded frames, OS chrome absent from the crop, and confirming in
the delivered pixels what the readability check computes from the recorded
measurement.

Any other axis reads `unverified` when no row declared a requirement on it.
`unverified_axes` names which case applies.

Report those as unchecked. Never restate an `unverified` axis as a pass.

If findings exist, return to the earliest invalid artifact — the storyboard row,
the clip, or the narration take. Do not accumulate local timing, cursor, or crop
patches against a take that a gate already rejected. Finish here.
