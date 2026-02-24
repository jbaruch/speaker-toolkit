# PowerPoint Deck Builder Script

## Problem/Feature Description

A speaker has a finalized presentation outline and needs to automate the creation of their PowerPoint deck. They use a custom `.pptx` template that contains their branded layouts but also includes demo/sample slides that need to be stripped out before building the actual deck. The speaker also needs their speaker notes injected into the final deck programmatically, since they have detailed notes for key slides.

Write a Python script that takes a presentation outline, a speaker profile (with template and design rules), and builds the deck end-to-end. The script should handle template preparation, slide creation with proper layout selection, footer insertion, background color management, and speaker notes injection. The speaker's profile contains their design rules — background color strategy, footer pattern, layout preferences, and other constraints.

## Output Specification

Produce the following files:

1. **`build_deck.py`** — A Python script that builds a .pptx deck from an outline and speaker profile
2. **`deck_plan.md`** — A document describing the slide-by-slide build plan: which layout to use, what content goes where, and any design decisions

The script should be runnable (with python-pptx installed) but does not need to produce an actual deck from a real template — it should demonstrate the correct workflow and API usage patterns.

Install python-pptx before starting: `pip install python-pptx`

## Input Files

The following files are provided as inputs. Extract them before beginning.

=============== FILE: inputs/speaker-profile-excerpt.json ===============
{
  "infrastructure": {
    "template_pptx_path": "/templates/speaker-template.pptx",
    "template_layouts": [
      {"index": 0, "name": "TITLE", "placeholders": [{"idx": 0, "type": "CENTER_TITLE"}], "use_for": "opening title slide, section dividers"},
      {"index": 1, "name": "TITLE_SUBTITLE", "placeholders": [{"idx": 0, "type": "TITLE"}, {"idx": 1, "type": "SUBTITLE"}], "use_for": "bio, shownotes"},
      {"index": 2, "name": "CONTENT", "placeholders": [{"idx": 0, "type": "TITLE"}, {"idx": 1, "type": "BODY"}], "use_for": "bullet lists, content slides"},
      {"index": 3, "name": "BLANK", "placeholders": [], "use_for": "full-bleed images, memes"}
    ],
    "font_pair": {"title": {"name": "Bangers"}, "body": {"name": "Arial"}},
    "slide_dimensions": {"width_inches": 10.0, "height_inches": 5.63}
  },
  "design_rules": {
    "background_color_strategy": "random_non_repeating",
    "background_color_pool": ["#5B2C6F", "#C0392B", "#F1C40F", "#27AE60", "#2980B9"],
    "white_black_reserved_for": "full-bleed image/meme slides only",
    "slide_numbers": "never",
    "footer": {
      "always_present": true,
      "pattern": "@speakerhandle | #DevOpsCon | #platform | speaker.dev",
      "font": "Arial",
      "font_size_pt": 16,
      "position": {"left": 0.01, "top": 5.22, "width": 10.0, "height": 0.37},
      "color_adapts_to_background": true
    }
  }
}
=============== END OF FILE ===============

=============== FILE: inputs/outline-excerpt.md ===============
## Opening Sequence [3 min, slides 1-5]

### Slide 1: Title Slide
- Visual: "The Talk Title" in bold
- Layout: Title only
- Speaker: (no notes)

### Slide 2: Opening Hook
- Visual: Meme — provocative image
- Layout: Full-bleed image
- Speaker: "So raise your hand if you've ever been told..."

### Slide 3: Brief Bio
- Visual: Name, role, one-liner
- Layout: Title + subtitle
- Speaker: "Quick intro — I'm [name], I do [thing]"

### Slide 4: Shownotes URL
- Visual: URL + QR code
- Layout: Title + subtitle
- Speaker: "Everything's at this URL — grab it now"

### Slide 5: Bold Statement
- Visual: "X is not a thing" in large text
- Layout: Title only
- Speaker: "Yeah I said it. And I mean it. Full stop."

## Act 1: The Problem [15 min, slides 6-20]

### Slide 6: Why It Matters
- Visual: Bullet list with data points
- Layout: Content
- Speaker: "okay so here's where it gets interesting"

### Slide 7: The Data
- Visual: Chart placeholder
- Layout: Content
- Speaker: "Look at these numbers right?"

### Slide 8: Reaction Meme
- Visual: Full-bleed meme
- Layout: Blank
- Speaker: (reaction image, no notes)
=============== END OF FILE ===============
