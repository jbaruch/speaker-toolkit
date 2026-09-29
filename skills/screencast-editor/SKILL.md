---
name: screencast-editor
description: >
  Edit a talk-to-camera or demo screencast recorded in Camtasia (screen, camera
  and mic in one take) into a speaker-first video: plan cuts on sentence
  boundaries from Camtasia's own word timings, frame and zoom the screen
  evidence, audit the framing against the recorded pointer, generate the
  Camtasia project, correct the dynamic captions, and time the YouTube
  chapters. Use when the user has a new Camtasia recording to edit, wants
  captions fixed, zooms adjusted, chapters or a description with time marks,
  or asks how to produce a screencast like a previous one.
user_invocable: true
---

# Screencast Editor

Process steps in order. Do not skip ahead.

Resolve the absolute path of this loaded `SKILL.md`, then set
`speaker_toolkit_root` to the plugin root two directories above the directory
containing this file. Never derive it from the consumer working directory.
Treat `{speaker_toolkit_root}` as absolute in every toolkit-owned command;
recording, project, and output paths remain consumer-owned.

The lessons behind every step, and the incidents that taught them:
[references/production-lessons.md](references/production-lessons.md). Read it
before the first edit of a session. File formats:
[references/camtasia-format.md](references/camtasia-format.md).

Camtasia owns any project it has open. Never write a project file until the
user has saved and closed it. Never screenshot the whole screen: other apps and
private conversations are on it. Look at pixels only through the stills this
skill renders.

## Step 1 — Resolve the interpreter

```bash
python3 "{speaker_toolkit_root}/skills/screencast-recorder/scripts/resolve-interpreter.py" <vault_root>
```

Set `python_path` from its output; it is the interpreter for every command
below. On exit 1, repair through `Skill(skill: "vault-ingress")`. Never fall
back to whichever `python3` is on `PATH`. Proceed immediately to Step 2.

## Step 2 — Secure the take

Ask the user to open the recording's project in Camtasia, add dynamic captions
to it (this makes Camtasia transcribe the take), save it outside Camtasia's
Temporary Projects folder, and close it. Camtasia deletes temporary projects
and recordings on its own schedule. Wait for confirmation. Proceed immediately
to Step 3.

## Step 3 — Export the transcript

```bash
"{python_path}" "{speaker_toolkit_root}/skills/screencast-editor/scripts/transcript.py" <raw.cmproj> > transcript.json
```

Word onsets are source seconds and are the only clock for cuts. Proceed
immediately to Step 4.

## Step 4 — Map what the screen shows

```bash
"{python_path}" "{speaker_toolkit_root}/skills/screencast-editor/scripts/screen-changes.py" <recording.trec> > changes.json
"{python_path}" "{speaker_toolkit_root}/skills/screencast-editor/scripts/trec-pointer.py" <recording.trec> --out pointer.json
```

Screen changes are page switches and scrolls. The pointer path comes from the
recording's metadata, not the pixels. Proceed immediately to Step 5.

## Step 5 — Write the shot plan

Write `shot-plan.json` per
[references/shot-plan.md](references/shot-plan.md): the presenter full-frame
for the opening, commentary, and close; the screen only while the words point
at it; every cut between sentences. Proceed immediately to Step 6.

## Step 6 — Audit the framing

```bash
"{python_path}" "{speaker_toolkit_root}/skills/screencast-editor/scripts/audit-framing.py" shot-plan.json pointer.json
```

Exit 1 names each shot whose framing cuts off what the presenter points at.
Fix the plan and rerun until exit 0. Proceed immediately to Step 7.

## Step 7 — Look at every framing

```bash
"{python_path}" "{speaker_toolkit_root}/skills/screencast-editor/scripts/framing-stills.py" <recording.trec> shot-plan.json --out stills
```

Read `stills/sheet.png` and any still in doubt. The red box is the inset's
footprint: it must never cover text being read. Fix the plan and return to
Step 6 for any still that fails. Proceed immediately to Step 8.

## Step 8 — Build the project

```bash
"{python_path}" "{speaker_toolkit_root}/skills/screencast-editor/scripts/build-project.py" <raw.cmproj> shot-plan.json --out "<title>.cmproj"
```

It writes a new bundle with the recording cloned inside; a rerun with the same
inputs is a no-op, and a different existing bundle is never overwritten. Ask the
user to open it and review the cut, following the observations in the
`camtasia-validation-authority` rule. For changes, edit the
plan, rerun Steps 6 to 8 into a new bundle name. Proceed immediately to Step 9
once the user approves the cut.

## Step 9 — Correct the captions

Ask the user to add dynamic captions to the approved project, save, and close.
Write `captions.txt` as corrected English: names spelled right, sentence
punctuation, false starts dropped, grammar fixed. The words the speaker meant,
not a verbatim record. Then:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/screencast-editor/scripts/apply-captions.py" "<title>.cmproj" captions.txt
```

Pass `--override WORD=SECONDS` for a word whose measured onset differs, and the
size and position flags for a different inset. Ask the user to review. Repeat
after any correction. Proceed immediately to Step 10.

## Step 10 — Time the chapters

Write `chapters.json` (first entry's phrase null), then:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/screencast-editor/scripts/chapters.py" "<title>.cmproj" chapters.json
```

Exit 1 names a missing phrase, a chapter under ten seconds, or fewer than
three chapters; fix and rerun. Write the description around its `lines`, linking only public sources
you have verified. Proceed immediately to Step 11.

## Step 11 — Make the thumbnail

```
Skill(skill: "illustrations")
```

Enter its thumbnail step. With no speaker photo configured, extract a frame
from the recording's camera track where the speaker is engaged and looking at
the lens: it is a real photograph. Finish here.
