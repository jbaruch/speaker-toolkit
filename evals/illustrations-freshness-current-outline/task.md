# Generate Deck Illustrations Right After Picking a Model

## Situation

A speaker has just finished the illustration strategy collaboration in their talk directory. They ran the comparison helper this morning, looked at the side-by-side outputs, and picked one of the candidates. The outline's `**Model:**` line carries that fresh choice. Now they want to generate the deck illustrations from the outline.

This is the immediate handoff between strategy and generation, not a return to an outline that has been sitting around.

## Outline Setup

Create the talk directory and the outline file before generating. Set the outline file's modification time to "right now" before invoking the skill, so the freshness signal reads as fresh:

```bash
mkdir -p talk-dir/illustrations

cat > talk-dir/presentation-outline.md <<'EOF'
# Presentation Outline

## Illustration Style Anchor

**Model:** `gpt-image-2`

### STYLE ANCHOR (FULL — 16:9, 1920x1080)
> A clean technical-manual aesthetic: aged ivory paper, black ink line
> drawings with halftone shading, period-correct typography, no painterly
> gradients.

---

### Slide 3: The Routing Diagram
- Format: **FULL**
- Image prompt: `[STYLE ANCHOR] An isometric cutaway technical drawing of a small mechanical unit with four input pins on the left feeding a central dispatch element.`
- Safe zone: upper_third
- Text: **The Routing Diagram**

### Slide 8: The Caution Note
- Format: **FULL**
- Image prompt: `[STYLE ANCHOR] A technical manual page corner showing a CAUTION callout box with stenciled body text.`
- Safe zone: upper_third
- Text: **The Caution Note**
EOF

touch -m talk-dir/presentation-outline.md
```

The model picked in the outline (`gpt-image-2`) is one of the entries the comparison helper produced for the speaker this morning.

## What the Speaker Asks

> "Generate the illustrations for this deck."

## Constraints

- The speaker has an hour set aside for slide rendering work; they expect that time to be spent generating images, not on additional planning.
