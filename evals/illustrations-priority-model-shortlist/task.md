# Choose an Image Model for a Build-Heavy Deck on a Budget

## Situation

A speaker is in the illustration-strategy stage for a talk. The outline has
slides and several progressive-reveal sequences (elements appear one at a time
across consecutive slides), but no illustration style or model has been chosen
yet. The speaker wants help picking which image-generation model to use.

## Outline Setup

Create the talk directory and `outline.yaml`:

```bash
mkdir -p talk-dir

cat > talk-dir/outline.yaml <<'EOF'
talk:
  title: "Shipping Under Pressure"
  slug: "internal-tech-talk-shipping"
  speakers: ["Speaker"]
  duration_min: 25
  audience: "Internal engineering team"
  mode: "talklet"
  venue: "Internal Tech Talk"
  slide_budget: 28
  pacing_wpm: [135, 145]
  architecture: "talklet"

chapters:
  - id: ch1
    title: "The Pipeline"
    target_min: 25
    argument_beats:
      - text: "Reveal the deploy pipeline stage by stage."
        slide_refs: [4, 9]

slides:
  - n: 4
    chapter: ch1
    title: "The Deploy Pipeline"
    format: FULL
    visual: "A horizontal pipeline diagram that fills in stage by stage."
    text_overlay: "The Pipeline"
    builds:
      - "Show only the empty pipeline track."
      - "Add the build stage."
      - "Add the test stage."
      - "Add the deploy stage."
    big_idea: true
    applied_patterns:
      - id: call-to-adventure
        big_idea_text: "Every stage earns the next."

  - n: 9
    chapter: ch1
    title: "The Rollback Path"
    format: FULL
    visual: "The same pipeline, with a rollback arrow drawn in progressively."
    text_overlay: "Rollback"
    builds:
      - "Show the full pipeline."
      - "Add the rollback arrow from deploy back to build."
EOF
```

## What the Speaker Asks

> "Help me pick an image-generation model for this deck. Money's tight this
> quarter, so I want to keep generation costs as low as possible. Which one
> should we go with?"

## Constraints

- The speaker has not yet defined an illustration style or chosen a model.
- The reveal sequences in slides 4 and 9 are core to the talk and must be
  preserved.
