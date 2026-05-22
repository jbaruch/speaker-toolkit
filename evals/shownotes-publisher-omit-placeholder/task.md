# Publish a Talk Page When the Recording Isn't Ready

## Problem/Feature Description

A speaker delivered a talk last week and the slides are uploaded, but
the conference still hasn't published the video. The speaker wants
the page live now — attendees keep asking — and wants visitors to
see that a video is coming and they should check back later.

The speaker says: "Slides URL is in
`inputs/talk/slides-url-2026-05-22.txt`. Get the page up. Make sure
visitors can tell the video isn't out yet — the page should clearly
indicate the recording is coming."

Compose the talk-page file at the path the site's conventions
require, relative to the working directory.

## Output Specification

Produce the talk page. Pick the filename and directory per the
site's rules.

## Input Files

Download the synthetic fixtures from the project repository:

```bash
BASE="https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/shownotes-publisher-omit-placeholder"
mkdir -p inputs/talk inputs/vault
curl -sL -o inputs/talk/outline.yaml              "$BASE/outline-2026-05-22.yaml"
curl -sL -o inputs/talk/resources.json            "$BASE/resources-2026-05-22.json"
curl -sL -o inputs/talk/slides-url-2026-05-22.txt "$BASE/slides-url-2026-05-22.txt"
curl -sL -o inputs/vault/speaker-profile.json     "$BASE/speaker-profile-2026-05-22.json"
```

The outline.yaml validates against `outline_schema.py`.
