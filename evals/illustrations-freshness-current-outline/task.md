# Generate Deck Illustrations Right After Picking a Model

## Situation

A speaker has just finished the illustration strategy collaboration in their talk directory. They ran the comparison helper this morning, looked at the side-by-side outputs, and picked one of the candidates. `outline.yaml`'s `style_anchor.model` field carries that fresh choice. Now they want to generate the deck illustrations from the outline.

This is the immediate handoff between strategy and generation, not a return to an outline that has been sitting around.

## Outline Setup

Create the talk directory and `outline.yaml` before generating. Set the outline file's modification time to "right now" before invoking the skill, so the freshness signal reads as fresh:

```bash
mkdir -p talk-dir/illustrations

cat > talk-dir/outline.yaml <<'EOF'
talk:
  title: "Routing in Practice"
  slug: "internal-tech-talk-routing"
  speakers: ["Speaker"]
  duration_min: 25
  audience: "Internal engineering team"
  mode: "talklet"
  venue: "Internal Tech Talk"
  slide_budget: 30
  pacing_wpm: [135, 145]
  architecture: "talklet"

style_anchor:
  model: "gpt-image-2"
  full: |
    A clean technical-manual aesthetic: aged ivory paper, black ink line
    drawings with halftone shading, period-correct typography, no painterly
    gradients.
  imgtxt: |
    Same aesthetic, portrait orientation. Illustration in upper 60%.
  conventions: "Sequential figure numbering; consistent stenciled labels."

chapters:
  - id: ch1
    title: "Routing Walk-Through"
    target_min: 25
    argument_beats:
      - text: "Walk through the routing diagram, surface the caution case."
        slide_refs: [3, 8]

slides:
  - n: 3
    chapter: ch1
    title: "The Routing Diagram"
    format: FULL
    visual: "Isometric cutaway technical drawing of a routing element."
    text_overlay: "The Routing Diagram"
    image_prompt: |
      [STYLE ANCHOR]. An isometric cutaway technical drawing of a small
      mechanical unit with four input pins on the left feeding a central
      dispatch element.
    big_idea: true
    applied_patterns:
      - id: call-to-adventure
        big_idea_text: "Routing is mechanical, not magical."

  - n: 8
    chapter: ch1
    title: "The Caution Note"
    format: FULL
    visual: "Technical manual page corner showing a CAUTION callout box."
    text_overlay: "The Caution Note"
    image_prompt: |
      [STYLE ANCHOR]. A technical manual page corner showing a CAUTION
      callout box with stenciled body text.
EOF

touch -m talk-dir/outline.yaml
```

The model picked in `style_anchor.model` (`gpt-image-2`) is one of the entries the comparison helper produced for the speaker this morning.

## What the Speaker Asks

> "Generate the illustrations for this deck."

## Constraints

- The speaker has an hour set aside for slide rendering work; they expect that time to be spent generating images, not on additional planning.
