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

The following files are provided as inputs. Extract them before
beginning.

=============== FILE: inputs/talk/outline.yaml ===============
talk:
  title: "Decoding ML Pipelines: From CI to GPU"
  slug: mlopscon-2026-decoding-ml-pipelines
  thesis: "Most ML pipelines fail not in training but at the boring edges — data validation, CI gates, GPU scheduling. This talk walks through three production failures and the dull infrastructure choices that would have prevented them. The argument: ship the boring stuff first, then the model."
  venue: "MLOpsCon 2026"
  delivery_date: 2026-04-15
  speakers:
    - "Riley Hayes"
  audience: "ML platform engineers, infrastructure leads"
  mode: "Lessons from Production"
  duration_minutes: 45
  architecture: problem_solution
  shownotes_url_base: "https://speaking.example.org"
=============== END OF FILE ===============

=============== FILE: inputs/talk/resources.json ===============
{
  "schema_version": 1,
  "items": [
    {"title": "Paper: Hidden Technical Debt in ML Systems", "url": "https://papers.example.org/hidden-debt", "approved": true},
    {"title": "Guide: GPU Scheduling Patterns at Scale", "url": "https://blog.example.org/gpu-scheduling", "approved": true},
    {"title": "Repository: pipeline-test-harness reference impl", "url": "https://example.org/pipeline-test-harness", "approved": true},
    {"title": "Draft post — not ready", "url": "https://example.org/draft", "approved": false}
  ]
}
=============== END OF FILE ===============

=============== FILE: inputs/speaker-profile.json ===============
{
  "schema_version": 1,
  "speaker": {
    "name": "Riley Hayes",
    "display_name": "Riley Hayes",
    "handle": "@rileyhayes",
    "website": "rileyhayes.example.org"
  }
}
=============== END OF FILE ===============
