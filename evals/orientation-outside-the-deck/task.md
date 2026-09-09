# Pattern Observations for a Demo-Heavy Delivery

## Background

You are scoring one delivery against the presentation pattern catalog.

**Talk:** "The Right 300 Tokens Beat 100k Noisy Ones", JavaZone 2026, 45 minutes.

**Sources inspected for this talk:** the rendered slide PDF (`static_slides`)
and the complete delivery video (`delivery_video`). No transcript, no native
deck.

### What the rendered PDF contains

Nine slides. A title slide, a bio slide, six content slides, and a closing
slide. No agenda slide. No progress bar. No sidebar topic list. No section
dividers. Nothing on any slide indicates position within the talk.

### What the delivery video shows

The speaker leaves the deck after slide 3, about six minutes in, and returns to
it only for the closing slide. For the remaining ~35 minutes the projector shows
a terminal session running seven live demos.

The terminal's status bar is visible along the bottom of the projected screen for
that entire span:

```
talk | 0 slides | 1 demo01 | 2 demo02 | 3 demo03 | 4 demo04 | 5 demo05 | 6 demo06 | 7 eval
```

The current window is highlighted in reverse video. Windows the speaker has
already worked through sit to its left; the ones still to come sit to its right.
The speaker moves left to right through the list over the course of the talk and
refers to it out loud twice ("we're on demo four of seven").

The talk's sections are the demo environments, not the slides: seven demo
segments plus an opening and a close.

## Output Specification

Produce a pattern observation report saved to `observations.md` covering exactly
the two catalog entries `breadcrumbs` and `context-keeper`.

For each, state:

1. The outcome — one of `strong`, `moderate`, `absent`, `not_evaluable`, or
   `not_applicable`.
2. The evidence source or sources the outcome is drawn from.
3. One sentence of justification, naming the artifact the finding rests on.

Then add a short `## Notes` section recording anything you observed that the
catalog has no entry for.

Follow the catalog's own evidence gates. Do not assert an outcome the entry's
gate does not authorize.
