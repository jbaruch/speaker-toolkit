# Add the Video URL to an Existing Shownotes Page

## Problem/Feature Description

A few weeks after a talk shipped, the conference uploaded the
recording to YouTube and the speaker wants the talk's shownotes page
updated so the video shows up. The talk page was already published —
slides and shownotes have been live for weeks — and the speaker has
hand-edited the file in the interim (added a couple of follow-up
resource links, fixed a typo in the abstract, added a new resource
the audience suggested afterward).

The speaker says: "The video is out — URL is in
`inputs/video-url-2026-05-22.txt`. Update the shownotes page so the
video shows. Don't touch the rest — I already cleaned up the
resources and fixed the abstract typo a couple of weeks back."

## Output Specification

Produce the updated talk page at the same path as the existing file.
Preserve the speaker's prior hand-edits.

## Input Files

Download the synthetic fixtures from the project repository. The
existing `_talks/*.md` (with the speaker's hand-edits) is the live
source of truth for the update — the outline.yaml is provided for
reference only.

```bash
BASE="https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/shownotes-publisher-update-add-video"
mkdir -p inputs/talk inputs/_talks
curl -sL -o inputs/talk/outline.yaml "$BASE/outline-2026-05-22.yaml"
curl -sL -o inputs/video-url-2026-05-22.txt "$BASE/video-url-2026-05-22.txt"
curl -sL -o inputs/_talks/2026-04-15-mlopscon-2026-decoding-ml-pipelines.md \
    "$BASE/existing-talk-2026-05-22.md"
```

The outline.yaml validates against `outline_schema.py`. The
`existing-talk-*.md` fixture is the live `_talks/` file as the
speaker last edited it.
