# Adapt an Existing Talk for a New Venue

## Problem/Feature Description

A speaker is adapting their 6-slide talk "Scaling Microservices" for a new venue. The original deck covers: Title, Introduction, Problem Statement, Current Architecture, Performance Results, Conclusion. For the new venue, the speaker needs to add 3 new slides:

1. A new slide at position 3 about "Cloud Cost Analysis" (subtitle: "AWS vs GCP pricing comparison for the audience")
2. A new slide at position 5 about "Migration Strategy" (subtitle: "Step-by-step migration path from monolith")
3. A new slide at position 8 about "Q&A Prep" (subtitle: "Anticipated questions from enterprise architects")

These are content placeholders — the speaker wants to mark WHERE the new slides go before actually building them, so they can see the deck flow in thumbnail view and iterate on the structure.

Using the presentation-creator skill, insert placeholder slides into the deck at the specified positions. The placeholders should be visually obvious so they stand out when reviewing the deck.

## Output Specification

Produce the following files:

1. **`adapted-deck.pptx`** — The deck with 9 slides total (6 original + 3 placeholders). Original slides must be in their original relative order. The placeholder slides must be at the specified positions.
2. **`adaptation-log.md`** — Document:
   - Which tool/script was used
   - The command that was run
   - How many slides before and after
   - The final slide order (all 9 slides listed with their position)

## Input Files

Download the base deck from the project repository:

```bash
BASE="https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/scenario-27"
mkdir -p inputs
curl -L -o inputs/base-deck.pptx "$BASE/base-deck.pptx"
```

## Key Parameters

- **Original deck:** 6 slides
- **Placeholders to insert:** 3 (at positions 3, 5, 8 in the final 9-slide deck)
- **Expected final slide count:** 9
- **Positions are 1-indexed** (final position after all insertions)
