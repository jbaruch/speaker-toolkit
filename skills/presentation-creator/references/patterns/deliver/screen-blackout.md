---
id: screen-blackout
name: Screen Blackout
type: pattern
part: deliver
phase_relevance:
  - content
  - slides
vault_dimensions: [12, 13]
detection_signals:
  - "deliberate blank or black slide between sections"
  - "B-key blackout during digression or audience question"
  - "speaker holds attention without screen support"
related_patterns: [breathing-room, intermezzi, brain-breaks, mentor]
inverse_of: []
difficulty: intermediate
---

# Screen Blackout

## Summary
Deliberately blank the screen — by inserting a black slide or pressing the B key — to redirect all audience attention onto the speaker for moments that do not need visual support.

## The Pattern in Detail
A live talk has two channels of attention competing for the audience: the speaker and the screen. Most of the time these channels reinforce each other — the slide amplifies what the speaker is saying. But there are moments when the screen actively *competes* with the speaker, draining attention from the human in the room. Screen Blackout is the deliberate technique of turning the screen off at those moments so the audience has nowhere to look but at the speaker.

The two implementations are functionally equivalent. The first is to **build black slides into the deck** at planned points — section boundaries, the start of a personal story, the moment before a punchline, the answer to an audience question. These slides require no design work; they are simply black canvases with no content. They appear in the speaker's flow as deliberate visual rests, the same way a composer writes rests into music.

The second implementation is the **B key** in PowerPoint or Keynote (the W key produces a white screen for venues where the projector cannot dim to true black). Hitting B during delivery instantly blanks the screen until pressed again. Most decent presentation remotes have a dedicated blackout button for the same purpose. The B key is the in-the-moment tool for unplanned blackouts: an audience question that triggers a digression, a story that ran longer than expected, a moment when the speaker realizes the slide behind them has become a distraction. Press B, finish the moment, press B again to bring the slide back.

The principle behind both implementations is the same: visual silence is a tool, equivalent to verbal silence (`breathing-room`). When you want the audience to absorb a personal story, look you in the eye, or hear a single key sentence without their attention split, blank the screen. Steve Jobs used this technique constantly — long stretches of his keynotes had a black background behind him while he spoke, with the screen brought back only when there was something worth showing. The audience-attention default flips from "screen is on, look at the screen" to "screen is on only when relevant."

The pattern composes naturally with `mentor` (when the speaker pulls up a stool to have a conversation with the audience, the screen should not be competing), with `breathing-room` (a verbal pause and a screen blackout together signal "this matters"), and with `intermezzi` (themed transitions and blackouts can alternate — a blackout is the minimalist version of an intermezzo). It is the deliberate inverse of the failure mode where every moment of the talk is forced to have a slide behind it, which over-couples the speaker to the visual track and removes the speaker's ability to hold the room with voice and presence alone.

## When to Use / When to Avoid
Use this pattern at section boundaries, during personal stories, at audience-question moments, before punchlines, and any time the slide behind you is not actively reinforcing what you are saying. Build planned blackouts into the deck during the prepare phase; rehearse the B key for unplanned ones during `carnegie-hall`.

Avoid blackouts during demo-driven sections where the screen *is* the content (`live-demo`, `lipsync`). Avoid mechanical blackouts at fixed intervals — the technique works because it is deliberate; randomizing it makes it feel like a mistake. Also avoid blackouts in webinar contexts where the screen is the primary channel and there is no physical speaker for the audience to redirect attention to — in webinars, blanking the screen leaves the audience with nothing.

## Detection Heuristics
The vault should look for: (a) explicit black or blank slides in the deck file, especially between major sections or before known personal-story moments; (b) video evidence of the speaker holding the room while the screen behind them is dark; (c) the B-key behavior on platforms where remote keystrokes are observable. The clearest signal is a deck with intentional black slides at section boundaries — this is unmistakably deliberate, not a missing-slide bug.

## Scoring Criteria
- Strong signal (2 pts): Deliberate blackouts (planned black slides or visible B-key use) at meaningful moments — section boundaries, personal stories, audience-question handling — used as a tool for attention redirection
- Moderate signal (1 pt): Occasional blackouts present but inconsistent — speaker uses the technique once or twice but does not integrate it as a regular part of the delivery toolkit
- Absent (0 pts): Every moment of the talk has a slide behind the speaker; no blackouts, no rests; the screen is on continuously regardless of whether it is relevant

## Relationship to Vault Dimensions
Relates to Dimension 12 (Pacing Clues) because deliberate blackouts function as pacing rests, equivalent to verbal pauses. Relates to Dimension 13 (Slide Design Patterns) because building black slides into the deck is a visible design choice — the deliberately empty slide is a slide-design decision.

## Combinatorics
Pairs with `breathing-room` (the verbal and visual silences reinforce each other), `intermezzi` (a blackout is the minimalist intermezzo — same structural function with no decoration), `brain-breaks` (a blackout can punctuate a brain break), and `mentor` (the stool-and-conversation moment works best with the screen out of the way). It is independent from but compatible with `cave-painting` and `vacation-photos` — the styles those patterns produce alternate naturally with blackout rests.

## Related Reading
- Reynolds, G. (2012). *Presentation Zen: Simple Ideas on Presentation Design and Delivery* (2nd ed.). Ch. 10 — describes the B-key blackout technique and Steve Jobs's use of black screens between high-impact visuals as deliberate attention-redirection moments. New Riders.
