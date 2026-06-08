# Set Up the Illustration Style Anchor for a Talk

## Situation

A speaker is at the illustration-strategy stage for a talk. The outline has
slides with per-slide scene descriptions, but no illustration style or model has
been chosen yet — the STYLE ANCHOR header is empty. The speaker wants the style
anchor set up so deck-illustration generation can begin.

## Outline Setup

Create the talk directory and `outline.yaml`:

```bash
mkdir -p talk-dir

cat > talk-dir/outline.yaml <<'EOF'
talk:
  title: "The Cost of Coordination"
  slug: "internal-arch-coordination"
  speakers: ["Speaker"]
  duration_min: 30
  audience: "Internal engineering org"
  mode: "talklet"
  venue: "Internal Architecture Review"
  slide_budget: 32
  pacing_wpm: [135, 145]
  architecture: "talklet"

chapters:
  - id: ch1
    title: "Coordination"
    target_min: 30
    argument_beats:
      - text: "Show how coordination cost grows with team count."
        slide_refs: [3, 7]

slides:
  - n: 3
    chapter: ch1
    title: "The Coordination Tax"
    format: FULL
    visual: "A single team working in calm focus, one shared workbench."
    text_overlay: "One team, one bench"
    big_idea: true
    applied_patterns:
      - id: call-to-adventure
        big_idea_text: "Every new team is another line on the bill."

  - n: 7
    chapter: ch1
    title: "The Tangle"
    format: FULL
    visual: "Many teams, each at its own bench, connected by a snarl of wires."
    text_overlay: "Many teams, many wires"
EOF
```

## What the Speaker Asks

> "I already know I want the quality-tier model and a clean, editorial look —
> nothing too cartoonish. Just set up the style anchor for these slides so we
> can start generating the illustrations."

## Constraints

- The speaker has not committed to a specific illustration style or model yet.
- The two slides above are the ones the speaker cares about most.
