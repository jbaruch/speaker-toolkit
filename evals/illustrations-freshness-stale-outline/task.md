# Generate Deck Illustrations for an Aged Outline

## Situation

A speaker is preparing a talk for an upcoming conference. The outline was drafted during the speaker's intake session several months ago and has been sitting in the talk directory since. The `**Model:**` line in the outline header was filled in at that time after a side-by-side comparison run; the speaker has not revisited the model choice since.

Today the speaker opens the talk directory and asks for deck illustrations to be generated from the outline. They expect this to "just work" — the outline already has style anchors, per-slide image prompts, and the chosen model baked in.

## Outline Setup

Create the talk directory and the outline file before generating:

```bash
mkdir -p talk-dir/illustrations
cat > talk-dir/presentation-outline.md <<'EOF'
# Presentation Outline

## Illustration Style Anchor

**Model:** `gemini-2.0-flash-preview-image-generation`

### STYLE ANCHOR (FULL — 16:9, 1920x1080)
> A muted watercolor scene with soft edges, earthen palette, and visible
> brushstrokes. Subjects rendered loosely, backgrounds drawn from natural
> textures.

---

### Slide 2: The Detour
- Format: **FULL**
- Image prompt: `[STYLE ANCHOR] A traveler standing at an unmarked fork in a country road, looking at a battered signpost.`
- Safe zone: upper_third
- Text: **The Detour**

### Slide 5: The Reckoning
- Format: **FULL**
- Image prompt: `[STYLE ANCHOR] A wide hillside at dusk with one figure facing a small fire that has just guttered out.`
- Safe zone: upper_third
- Text: **The Reckoning**
EOF
```

Note the timestamp: the outline file is being created fresh for the eval run, but the situation assumes the speaker drafted it several months ago. Treat the `**Model:**` line as a choice the speaker made then, not a current decision.

## What the Speaker Asks

> "Generate the illustrations for this deck."

## Constraints

- The talk is not booked for a hard deadline; there is no time pressure to skip preparation.
- The speaker wants a polished deck — quality of the resulting illustrations matters more than how fast they appear.
