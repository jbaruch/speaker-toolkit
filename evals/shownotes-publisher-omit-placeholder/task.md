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

=============== FILE: inputs/talk/outline.yaml ===============
talk:
  title: "The Quiet Failures of Distributed Caches"
  slug: kafka-eu-2026-quiet-cache-failures
  thesis: "Distributed cache layers fail quietly — a 0.3% miss-rate climb that nobody sees until the upstream database starts paging at 03:00. This talk walks through three real cache failures, the metrics that would have caught them, and the dashboards every cache deployment should ship with on day one."
  venue: "KafkaEU 2026"
  delivery_date: 2026-05-04
  speakers:
    - "Riley Hayes"
  audience: "Infrastructure and platform engineers"
  mode: "War Stories"
  duration_minutes: 35
=============== END OF FILE ===============

=============== FILE: inputs/talk/resources.json ===============
{
  "schema_version": 1,
  "items": [
    {"title": "Postmortem: cache-tier paging incident", "url": "https://example.org/postmortem-2025-12", "approved": true},
    {"title": "Dashboard pack: redis-observability", "url": "https://example.org/dashboards/redis-obs", "approved": true}
  ]
}
=============== END OF FILE ===============

=============== FILE: inputs/speaker-profile.json ===============
{
  "schema_version": 1,
  "speaker": {
    "name": "Riley Hayes",
    "display_name": "Riley Hayes"
  }
}
=============== END OF FILE ===============
