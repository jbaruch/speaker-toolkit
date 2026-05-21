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

=============== FILE: inputs/talk/outline.yaml ===============
talk:
  title: "Absolutely Right: When LLMs Agree With You"
  slug: geecon-2026-absolutely-right
  thesis: "LLMs are sycophantic by training — they agree with the user even when the user is wrong. This talk walks through three production incidents where developer prompts steered a coding agent into shipping subtly broken code, and the prompt-discipline patterns that catch the agreement reflex before it ships."
  venue: "GeeCON 2026"
  speakers:
    - "Riley Hayes"
  audience: "Backend engineers using AI coding agents in CI/CD"
  mode: "Cautionary Tale"
  duration_minutes: 40
  architecture: case_study
  shownotes_url_base: "https://speaking.example.org"
=============== END OF FILE ===============

=============== FILE: inputs/talk/resources.json ===============
{
  "schema_version": 1,
  "items": [
    {"title": "Paper: Sycophancy in LLMs", "url": "https://papers.example.org/sycophancy", "approved": true},
    {"title": "Talk follow-up post (auto-generated)", "url": "https://example.org/draft-post", "approved": false}
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
