# Generate Deck Illustrations for an Aged Outline

## Situation

A speaker is preparing a talk for an upcoming conference. The outline was drafted during the speaker's intake session several months ago and has been sitting in the talk directory since. The `style_anchor.model` field in `outline.yaml` was filled in at that time after a side-by-side comparison run; the speaker has not revisited the model choice since.

Today the speaker opens the talk directory and asks for deck illustrations to be generated from the outline. They expect this to "just work" — the outline already has style anchors, per-slide image prompts, and the chosen model baked in.

## Outline Setup

Create the talk directory and `outline.yaml`:

```bash
mkdir -p talk-dir/illustrations
cat > talk-dir/outline.yaml <<'EOF'
talk:
  title: "Detours and Reckonings"
  slug: "literary-talk-detours-reckonings"
  speakers: ["Speaker"]
  duration_min: 30
  audience: "Literary conference attendees"
  mode: "narrative"
  venue: "Literary Conference"
  slide_budget: 30
  pacing_wpm: [125, 135]
  architecture: "narrative-arc"

style_anchor:
  model: "gemini-2.0-flash-preview-image-generation"
  full: |
    A muted watercolor scene with soft edges, earthen palette, and visible
    brushstrokes. Subjects rendered loosely, backgrounds drawn from natural
    textures.
  imgtxt: |
    Same watercolor aesthetic, portrait orientation. Illustration upper 60%.
  conventions: "Consistent earthen palette; figures rendered loosely."

chapters:
  - id: ch1
    title: "Journey"
    target_min: 30
    argument_beats:
      - text: "The detour and the reckoning."
        slide_refs: [2, 5]

slides:
  - n: 2
    chapter: ch1
    title: "The Detour"
    format: FULL
    visual: "Traveler at an unmarked fork."
    text_overlay: "The Detour"
    image_prompt: |
      [STYLE ANCHOR]. A traveler standing at an unmarked fork in a country
      road, looking at a battered signpost.
    big_idea: true
    applied_patterns:
      - id: call-to-adventure
        big_idea_text: "Every detour is a chance to reckon with the route."

  - n: 5
    chapter: ch1
    title: "The Reckoning"
    format: FULL
    visual: "Hillside at dusk with one figure facing a guttered fire."
    text_overlay: "The Reckoning"
    image_prompt: |
      [STYLE ANCHOR]. A wide hillside at dusk with one figure facing a small
      fire that has just guttered out.
EOF
```

Note the timestamp: the outline file is being created fresh for the eval run, but the situation assumes the speaker drafted it several months ago. Treat the `style_anchor.model` value as a choice the speaker made then, not a current decision.

## What the Speaker Asks

> "Generate the illustrations for this deck."

## Constraints

- The talk is not booked for a hard deadline; there is no time pressure to skip preparation.
- The speaker wants a polished deck — quality of the resulting illustrations matters more than how fast they appear.
