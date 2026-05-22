# Publish a Delivered Talk to the Shownotes Site

## Problem/Feature Description

A speaker has just delivered a conference talk and wants the talk page
to go live on their Jekyll-based shownotes site (a static site whose
`_talks/` collection drives the published pages). The talk's spec
(`outline.yaml`), gathered resources (`resources.json`), and the
freshly uploaded slides PDF are all available. The recording is not
yet published; only the slides URL is in hand.

The speaker says: "I delivered the talk yesterday. Slides are at
`https://drive.google.com/file/d/1aBcDe-fGhIjKlMnOpQrStUvWx/preview`.
Publish the shownotes page — no video yet, that comes later."

Compose the talk-page file for the `_talks/` collection. Save it at
the path the site's conventions require, relative to the working
directory (e.g., `_talks/<filename>.md`). Do not run a Jekyll build
and do not invoke any external service.

## Output Specification

Produce the file:

1. **`_talks/<filename>.md`** — the talk page in the format the site's
   markdown parser plugin expects. The filename is the one the site's
   convention dictates given the artifacts provided.

## Input Files

Download the synthetic fixtures from the project repository:

```bash
BASE="https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/shownotes-publisher-publish-with-date"
mkdir -p inputs/talk inputs/vault
curl -sL -o inputs/talk/outline.yaml          "$BASE/outline.yaml"
curl -sL -o inputs/talk/resources.json        "$BASE/resources.json"
curl -sL -o inputs/vault/speaker-profile.json "$BASE/speaker-profile.json"
```

All three are synthetic — speaker "Riley Hayes", conference
"MLOpsCon 2026". The outline.yaml validates against the
`outline_schema.py` pydantic schema.
