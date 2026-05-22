# Publish a Delivered Talk to the Shownotes Site

## Problem/Feature Description

A speaker has just delivered a conference talk and wants the talk
page to go live on their Jekyll-based shownotes site. The talk's
spec (`outline.yaml`), gathered resources (`resources.json`), and
the freshly uploaded slides PDF are all available. The recording is
not yet published; only the slides URL is in hand — provided in the
single-line fixture `inputs/talk/slides-url-2026-05-22.txt`.

The speaker says: "I delivered the talk yesterday. Slides URL is in
the file I dropped in `inputs/talk/`. Publish the shownotes page — no
video yet, that comes later."

Compose the talk-page file at the path the site's conventions
require, relative to the working directory. Do not run a Jekyll
build and do not invoke any external service.

## Output Specification

Produce the talk page in the format the site's markdown parser
plugin expects. The filename and directory are the ones the site's
convention dictates given the artifacts provided.

## Input Files

Download the synthetic fixtures from the project repository:

```bash
BASE="https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/shownotes-publisher-publish-with-date"
mkdir -p inputs/talk inputs/vault
curl -sL -o inputs/talk/outline.yaml          "$BASE/outline-2026-05-22.yaml"
curl -sL -o inputs/talk/resources.json        "$BASE/resources-2026-05-22.json"
curl -sL -o inputs/talk/slides-url-2026-05-22.txt "$BASE/slides-url-2026-05-22.txt"
curl -sL -o inputs/vault/speaker-profile.json "$BASE/speaker-profile-2026-05-22.json"
```

All four fixtures are synthetic. The outline.yaml validates against
the `outline_schema.py` pydantic schema. The slides URL fixture
contains exactly one line.
