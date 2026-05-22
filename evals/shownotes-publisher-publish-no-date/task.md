# Publish a Pre-Talk Shownotes Page (No Delivery Date Yet)

## Problem/Feature Description

A speaker is heading to a conference next month and wants the talk
page on the shownotes site to go live ahead of the talk so attendees
can scan a QR pointing at it. The talk isn't delivered yet — there is
no recording, no fixed delivery date in the spec, just an accepted
slot at the conference and a finalized slide deck.

The speaker says: "Talk got accepted, here's the deck and the spec.
Get the page up before the conference — I want the QR code to point
somewhere real on the printed badge."

The slides PDF is at
`https://drive.google.com/file/d/9XyZ-mlops-pretalk-aBcDeF/preview`.

Compose the talk-page file for the `_talks/` collection. Save it at
the path the site's conventions require, relative to the working
directory. Do not run a Jekyll build.

## Output Specification

Produce the file:

1. **`_talks/<filename>.md`** — the talk page. Pick the filename per
   the site's rules.

## Input Files

Download the synthetic fixtures from the project repository:

```bash
BASE="https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/shownotes-publisher-publish-no-date"
mkdir -p inputs/talk inputs/vault
curl -sL -o inputs/talk/outline.yaml          "$BASE/outline.yaml"
curl -sL -o inputs/talk/resources.json        "$BASE/resources.json"
curl -sL -o inputs/vault/speaker-profile.json "$BASE/speaker-profile.json"
```

The outline.yaml deliberately omits `talk.delivery_date` (the talk
hasn't happened yet). The file still validates against
`outline_schema.py` — `delivery_date` is optional in the schema.
