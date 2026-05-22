# Publish a Talk Page When the Recording Isn't Ready

## Problem/Feature Description

A speaker delivered a talk last week and the slides are uploaded, but
the conference still hasn't published the video. The speaker wants
the page live now — attendees keep asking — and wants visitors to
see that a video is coming and they should check back later.

The speaker says: "Slides are at
`https://drive.google.com/file/d/Vid-pending-12345/preview`. Get the
page up. Make sure visitors can tell the video isn't out yet — the
page should clearly indicate the recording is coming."

Compose the talk-page file. Save it at `_talks/<filename>.md`
relative to the working directory.

## Output Specification

Produce the file:

1. **`_talks/<filename>.md`** — the talk page.

## Input Files

Download the synthetic fixtures from the project repository:

```bash
BASE="https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/shownotes-publisher-omit-placeholder"
mkdir -p inputs/talk inputs/vault
curl -sL -o inputs/talk/outline.yaml          "$BASE/outline.yaml"
curl -sL -o inputs/talk/resources.json        "$BASE/resources.json"
curl -sL -o inputs/vault/speaker-profile.json "$BASE/speaker-profile.json"
```

The outline.yaml validates against `outline_schema.py`.
