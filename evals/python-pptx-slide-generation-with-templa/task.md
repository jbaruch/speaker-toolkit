# Generate a Conference Deck from a Finalized Outline

## Background

Jordan Chen is a conference speaker who uses a custom PowerPoint template for all their talks. Jordan has finalized the outline for an upcoming talk and needs a Python script to programmatically build the `.pptx` deck from that outline.

The script will be part of Jordan's repeatable workflow: every time an outline is ready, they run a script to generate the initial deck from the template, then iterate from there. Jordan's existing setup uses python-pptx for any structural operations and the speaker profile specifies how notes, footers, and backgrounds should be handled.

Jordan's template is at `./template.pptx` and the output should go to `./output/cloud-native-testing.pptx`.

## Output Specification

Write a Python script named `generate_deck.py` that takes Jordan's PowerPoint template and the outline below and produces a finished `.pptx` deck at `./output/cloud-native-testing.pptx`. The script should use python-pptx to build the deck programmatically.

The finished deck should be a complete, presentation-ready file with all slides from the outline, proper visual formatting, and speaker guidance preserved. Use the speaker profile below for all design decisions.

Also document any required dependencies in a requirements comment at the top of the script.

The speaker profile specifying Jordan's design rules and infrastructure is provided below.

## Input Files

The following files are provided as inputs. Extract them before beginning.

=============== FILE: inputs/speaker-profile.json ===============
{
  "schema_version": 1,
  "speaker": {
    "name": "Jordan Chen",
    "handle": "@jchen",
    "shownotes_url_pattern": "speaking.jordanchen.dev/{slug}"
  },
  "infrastructure": {
    "template_pptx_path": "./template.pptx",
    "template_layouts": [
      {"index": 0, "name": "TITLE_ONLY", "placeholders": ["TITLE"], "use_for": "title slide, section dividers"},
      {"index": 1, "name": "TITLE_AND_BODY", "placeholders": ["TITLE", "BODY"], "use_for": "content slides"},
      {"index": 2, "name": "BLANK", "placeholders": [], "use_for": "full-bleed images, memes"},
      {"index": 3, "name": "TWO_COLUMN", "placeholders": ["TITLE", "BODY_LEFT", "BODY_RIGHT"], "use_for": "comparisons"}
    ]
  },
  "design_rules": {
    "background_color_strategy": "dark_saturated_per_section",
    "section_colors": {
      "opening": [30, 30, 60],
      "problem": [80, 20, 20],
      "solution": [20, 60, 30],
      "closing": [30, 30, 60]
    },
    "white_black_reserved_for": "full-bleed image slides only",
    "footer": {
      "pattern": "@jchen | #{conference_hashtag} | speaking.jordanchen.dev/{slug}",
      "position_left_inches": 0.5,
      "position_bottom_inches": 0.15,
      "width_inches": 8.5,
      "height_inches": 0.25,
      "font": "Arial",
      "font_size": 9,
      "color": [255, 255, 255]
    },
    "slide_numbers": "never"
  }
}

=============== FILE: inputs/outline.md ===============
# Cloud-Native Testing: Stop Mocking Everything

**Spec:** practitioner | 30 min | CloudNativeCon EU 2025 | senior engineers
**Slide budget:** 45 slides

## Opening Sequence [3 min, slides 1-4]

### Slide 1: Title Slide
- Layout: TITLE_ONLY
- Visual: "Cloud-Native Testing: Stop Mocking Everything"
- Speaker: [no notes — title slide]

### Slide 2: Opening Provocation
- Layout: TITLE_AND_BODY
- Visual: Title: "Your test suite is a lie detector. And it's broken."
- Speaker: "Raise your hand if your CI passes and your prod still breaks. Yeah. That's most of us. Today we fix that."

### Slide 3: Brief Bio
- Layout: TITLE_AND_BODY
- Visual: Title: "Jordan Chen", Body: "Platform engineer @ Acme Corp. I break prod so you don't have to."
- Speaker: "Quick bio — I'll keep it short."

### Slide 4: Shownotes URL
- Layout: TITLE_AND_BODY
- Visual: Title: "All the links", Body: "speaking.jordanchen.dev/cloud-native-testing" + QR code placeholder
- Speaker: "Everything is at this URL. Slides, links, code samples."

## Act 1: The Problem With Mocks [8 min, slides 5-14]

### Slide 5: What We Do
- Layout: TITLE_AND_BODY
- Visual: Title: "The standard approach"
  Body: → Mock your dependencies\n→ Unit test everything in isolation\n→ 90% coverage\n→ Ship with confidence
- Speaker: "Here's the playbook most teams follow. Looks solid, right?"

### Slide 6: What Actually Happens
- Layout: TITLE_AND_BODY
- Visual: Title: "Reality"
  Body: → Mocks diverge from the real service\n→ Tests pass, integration fails\n→ You find out in prod
- Speaker: "Here's the thing nobody tells you: your mock is a snapshot of what you thought the API did in 2022."

[CUT LINE: drop slides 7-9 for 20-min version]

### Slide 7: The Drift Problem
- Layout: TITLE_AND_BODY
- Visual: Title: "Mock drift"
  Body: Study shows 62% of mocks in enterprise projects are out of sync with the actual service within 6 months.
- Speaker: "This number is from a 2024 study — reference in shownotes. Sixty-two percent. That's not a corner case."

### Slide 8: War Story
- Layout: TITLE_ONLY
- Visual: "The incident you don't want to have"
- Speaker: "Let me tell you about a payments service at a company I won't name. Their test coverage was 94%. Their prod incident rate was... also high."

## Act 2: Contract Testing [10 min, slides 15-24]

### Slide 15: The Alternative
- Layout: TITLE_AND_BODY
- Visual: Title: "Consumer-driven contract testing"
  Body: → Consumer defines what it needs\n→ Provider verifies it can deliver\n→ Contracts live in source control
- Speaker: "Instead of mocking what you think an API does, you write down what you need and verify it against the real thing."

## Closing Sequence [3 min, slides 42-45]

### Slide 42: Summary
- Layout: TITLE_AND_BODY
- Visual: Title: "Three things to take home"
  Body: → Replace mocks with contract tests at integration boundaries\n→ Use Testcontainers for infrastructure dependencies\n→ Keep unit tests for pure logic only
- Speaker: "Three things. If you do only one, do the first one."

### Slide 43: Call to Action
- Layout: TITLE_AND_BODY
- Visual: Title: "This week: one contract test"
  Body: Pick your most brittle mock. Replace it. Measure the flakiness delta.
- Speaker: "Don't boil the ocean. One mock. This week."

### Slide 44: Shownotes + QR
- Layout: TITLE_AND_BODY
- Visual: Title: "Resources", Body: "speaking.jordanchen.dev/cloud-native-testing"
- Speaker: "Everything is here. The Pact tutorial, the Testcontainers guide, and the incident post-mortem I referenced."

### Slide 45: Thanks
- Layout: TITLE_ONLY
- Visual: "Thank you — @jchen"
- Speaker: [no notes]
