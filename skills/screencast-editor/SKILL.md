---
name: screencast-editor
description: >
  Edit a talk-to-camera or demo screencast recorded in Camtasia for Mac
  (screen, camera and mic in one take) into a speaker-first video: plan cuts on sentence
  boundaries from Camtasia's own word timings, frame and zoom the screen
  evidence, audit the framing against the recorded pointer, generate the
  Camtasia project, correct the dynamic captions, time the YouTube chapters,
  and compose the thumbnail from frames of the take. Use when the user has a new Camtasia recording to edit, wants
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
[skills/screencast-editor/references/production-lessons.md](references/production-lessons.md).
Read it before the first edit of a session. File formats:
[skills/screencast-editor/references/camtasia-format.md](references/camtasia-format.md).

Camtasia owns any project it has open. Never write a project file until the
user has saved and closed it. Never screenshot the whole screen. Look at pixels
only through the stills this skill renders.

Every script prints its diagnostics on stderr and exits 2 on a usage error
(bad or missing arguments); each step lists its other outcomes.

Steps 2, 8, 9, 10, 11, 12, 13, and 14 hand work to the user and end the turn. When the user
reports back, resume at the step each one names.

## Step 1 — Resolve the interpreter

```bash
python3 "{speaker_toolkit_root}/skills/screencast-recorder/scripts/resolve-interpreter.py" <vault_root>
```

Stdout: `{"ok": true, "python_path", "vault_root", "database"}`. Set
`python_path` from it; it is the interpreter for every command below. On exit
1, repair through `Skill(skill: "vault-ingress")`. Never fall
back to whichever `python3` is on `PATH`. Proceed immediately to Step 2.

## Step 2 — Request the transcript

Ask the user to open the recording's project in Camtasia, add dynamic captions
to it (this makes Camtasia transcribe the take), save it outside Camtasia's
Temporary Projects folder, and close it. Camtasia deletes temporary projects
and recordings on its own schedule. Finish here; resume at Step 3 when the user
confirms.

## Step 3 — Export the transcript

```bash
"{python_path}" "{speaker_toolkit_root}/skills/screencast-editor/scripts/transcript.py" <raw.cmproj> > transcript.json
```

Output: `{"words": [[seconds, word]], "sentences": [{"start", "end", "text"}]}`
in source seconds; the last sentence has no `end`. Exit 1 means the project has
no transcript: return to Step 2. Word onsets are the only clock for cuts.
Proceed immediately to Step 4.

## Step 4 — Map what the screen shows

A screen + camera take whose edit uses no screen footage skips Steps 4, 6, and
7: its plan has only speaker shots, and the unused screen track stays in the
recording. Proceed immediately to Step 5 for such a take. A camera-only
recording is out of scope: `build-project.py` requires Camtasia's screen +
camera layout.

```bash
"{python_path}" "{speaker_toolkit_root}/skills/screencast-editor/scripts/screen-changes.py" <recording.trec> > changes.json
"{python_path}" "{speaker_toolkit_root}/skills/screencast-editor/scripts/trec-pointer.py" <recording.trec> --out pointer.json
```

`changes.json` is `{"changes": [seconds]}`: page switches and scrolls.
`pointer.json` is `{"capture": {"x", "y", "width", "height"}, "samples":
[[seconds, x, y]]}` with x and y normalized to the captured display. Exit 1
from either names what failed (ffmpeg, or no pointer data in the recording). Proceed immediately to Step 5.

## Step 5 — Write the shot plan

Write `shot-plan.json` per
[skills/screencast-editor/references/shot-plan.md](references/shot-plan.md):
the presenter full-frame for the opening, commentary, and close; the screen
only while the words point at it; every cut between sentences. Proceed
immediately to Step 6, or to Step 8 when the plan has no screen shots.

## Step 6 — Audit the framing

```bash
"{python_path}" "{speaker_toolkit_root}/skills/screencast-editor/scripts/audit-framing.py" shot-plan.json pointer.json
```

Stdout lists each screen shot with its `pointing` misses. Exit 1 names each
shot whose framing cuts off what the presenter points at; exit 2 is an invalid
plan or pointer file. Fix the plan and rerun until exit 0. Proceed immediately to Step 7.

## Step 7 — Look at every framing

```bash
"{python_path}" "{speaker_toolkit_root}/skills/screencast-editor/scripts/framing-stills.py" <recording.trec> shot-plan.json --out stills
```

Stdout: `{"stills": [paths], "sheet": path}`; exit 1 names an ffmpeg or write
failure. Read `stills/sheet.png` and any still in doubt. The red box is the inset's
footprint: it must never cover text being read. Fix the plan and return to
Step 6 for any still that fails. Proceed immediately to Step 8.

## Step 8 — Build the project

```bash
"{python_path}" "{speaker_toolkit_root}/skills/screencast-editor/scripts/build-project.py" <raw.cmproj> shot-plan.json --out "<title>.cmproj"
```

Stdout: `{"project", "screen_shots", "speaker_shots"}`, plus `"unchanged": true`
on a no-op rerun. Exit 1 is an invalid template or plan; exit 2 means `--out`
already holds a different edit and is never overwritten. Read
[rules/camtasia-validation-authority.md](../../rules/camtasia-validation-authority.md)
and ask the user to open the bundle and confirm its observations 1 to 4.
Finish here;
resume at Step 9 when the user approves the cut, or at Step 5 with their
changes, building into a new bundle name.

## Step 9 — Request the captions

Ask the user to add dynamic captions to the approved project, save, and close.
Finish here; resume at Step 10 when the user confirms.

## Step 10 — Correct the captions

Write `captions.txt` as corrected English: names spelled right, sentence
punctuation, false starts dropped, grammar fixed. The words the speaker meant,
not a verbatim record. Then:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/screencast-editor/scripts/apply-captions.py" "<title>.cmproj" captions.txt
```

For a word whose measured onset differs, pass `--override WORD=SECONDS` when the
word occurs once in the captions, or `--override WORD#N=SECONDS` for its Nth
occurrence; a repeated word without `#N` is refused. Pass the size and position
flags for a different inset. Stdout: `{"words", "matched", "interpolated",
"pauses", "backup"}`; exit 1 names the problem (project open, no transcript or
caption callout, bad override, unrelated text) and leaves the project unchanged.
Ask the user to confirm
observations 5 and 6 of the Camtasia validation rule. Finish here; resume at
Step 10 with their corrections, or at Step 11 when they approve.

## Step 11 — Time the chapters

Write `chapters.json` (first entry's phrase null), then:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/screencast-editor/scripts/chapters.py" "<title>.cmproj" chapters.json
```

Stdout: `{"chapters": [{"seconds", "clock", "title"}], "lines"}`. Exit 1 names
what YouTube would reject, or a malformed chapters file: a missing phrase, or a chapter list
that breaks the length and count limits in `chapters.py`. Fix and rerun. Write
the description around its `lines`, linking only public sources you have
verified. Ask the user to export and upload the video. Finish here; resume at
Step 12 when they have.

## Step 12 — Offer thumbnail backgrounds

Pick three to five engaged moments and extract exact screen frames:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/screencast-editor/scripts/extract-frames.py" <recording.trec> --stream 0:0 --at <seconds> --out thumb --prefix screen
```

Stdout: `{"frames": [paths]}`; exit 1 means a time lies outside the recording
or ffmpeg failed. Ask the user which background to use, per the `thumbnail-generation-rules`
rule. Finish here; resume at Step 13 when the user picks.

## Step 13 — Resolve the speaker photo

Use `publishing_process.thumbnail.speaker_photo_path` from the speaker profile
when it is set, and proceed immediately to Step 14. Otherwise extract candidate
camera frames:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/screencast-editor/scripts/extract-frames.py" <recording.trec> --stream 0:1 --at <seconds> --out thumb --prefix camera
```

Ask the user for a photo path or URL, offering these frames as the
alternative. Finish here; resume at Step 14 with their choice.

## Step 14 — Confirm the thumbnail title

Propose a hook title within the `thumbnail-generation-rules` word limit and
ask the user to confirm it. Finish here; resume at Step 15 when confirmed.

## Step 15 — Compose the thumbnail

```bash
"{python_path}" "{speaker_toolkit_root}/skills/screencast-editor/scripts/compose-thumbnail.py" --slide-image thumb/<screen-frame>.png --speaker-photo <photo> --title "<TITLE>" --aesthetic <photo|comic_book> --vault <vault_root> --output thumbnail.png
```

It runs the illustrations thumbnail generator and writes `thumbnail.png`.
Stdout: `{"thumbnail", "format", "width", "height", "bytes"}`; a JPEG fallback
is renamed to `.jpg`, and the generator's progress goes to stderr. Exit 1 means
the generator failed or wrote no image; exit 2 includes a title over the word
limit. Choose the
aesthetic by the rule's precedence, read the result, and iterate one change at
a time on request. Finish here.
