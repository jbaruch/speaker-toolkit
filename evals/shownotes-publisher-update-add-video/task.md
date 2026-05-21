# Add the Video URL to an Existing Shownotes Page

## Problem/Feature Description

A few weeks after a talk shipped, the conference uploaded the
recording to YouTube and the speaker wants the talk's shownotes page
updated so the video shows up. The talk page was already published —
slides and shownotes have been live for weeks — and the speaker has
hand-edited the file in the interim (added a couple of follow-up
resource links, fixed a typo in the abstract, added a new resource
the audience suggested afterward).

The speaker says: "The video for the MLOpsCon talk is out:
`https://youtu.be/Mlops26-VideoIdABC`. Update the shownotes page so
the video shows. Don't touch the rest — I already cleaned up the
resources and fixed the abstract typo a couple of weeks back."

## Output Specification

Produce the file:

1. **`_talks/2026-04-15-mlopscon-2026-decoding-ml-pipelines.md`** —
   the updated talk page. Preserve the speaker's prior hand-edits.

## Input Files

The existing talk page on the site, before this update, is provided
below. The outline.yaml is included for reference but the live file
is the source of truth — speakers edit `_talks/*.md` directly post-
publish.

=============== FILE: inputs/_talks/2026-04-15-mlopscon-2026-decoding-ml-pipelines.md ===============
---
layout: talk
---

# Decoding ML Pipelines: From CI to GPU

**Conference:** MLOpsCon 2026
**Date:** 2026-04-15
**Slides:** [View Slides](https://drive.google.com/file/d/1aBcDe-fGhIjKlMnOpQrStUvWx/preview)

A presentation at MLOpsCon 2026 in April 2026 in Berlin, Germany by {{ site.speaker.display_name | default: site.speaker.name }}

## Abstract

Most ML pipelines fail not in training but at the boring edges — data validation, CI gates, GPU scheduling. This talk walks through three production failures and the dull infrastructure choices that would have prevented them. The argument: ship the boring stuff first, then the model.

## Resources

- [Paper: Hidden Technical Debt in ML Systems](https://papers.example.org/hidden-debt)
- [Guide: GPU Scheduling Patterns at Scale](https://blog.example.org/gpu-scheduling)
- [Repository: pipeline-test-harness reference impl](https://example.org/pipeline-test-harness)
- [Audience-suggested: Tecton feature-store cookbook](https://example.org/tecton-cookbook)
- [Audience-suggested: KServe inference autoscaler write-up](https://example.org/kserve-autoscaler)
=============== END OF FILE ===============

=============== FILE: inputs/talk/outline.yaml ===============
talk:
  title: "Decoding ML Pipelines: From CI to GPU"
  slug: mlopscon-2026-decoding-ml-pipelines
  thesis: "Most ML pipelines fail not in training but at the boring edges — data validation, CI gates, GPU scheduling. This talk walks through three production failures."
  venue: "MLOpsCon 2026"
  delivery_date: 2026-04-15
  speakers:
    - "Riley Hayes"
=============== END OF FILE ===============
