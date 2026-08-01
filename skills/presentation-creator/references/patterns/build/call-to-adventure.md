---
id: call-to-adventure
name: Call to Adventure
type: pattern
part: build
phase_relevance:
  - architecture
  - content
vault_dimensions: [1, 2, 9]
evidence_channels: [timed_transcript, video]
detection_signals:
  - "explicit gap-reveal moment between current reality and proposed future"
  - "Big Idea stated at the structural transition from setup to body"
  - "audience cannot remain neutral after this moment — they engage or resist"
  - "transition language signaling structural shift (e.g., 'But what if…', 'Imagine instead…', 'This is what we're missing.')"
evaluable_from:
  - transcript
  - delivery_video
strong_evaluable_from:
  - transcript
  - delivery_video
absence_evaluable_from: null
not_applicable_when:
  - condition_id: non-persuasive-talk
    description: "A complete transcript or delivery video establishes a primarily informative talk with no requested change in audience position or behavior."
applicability_evaluable_from:
  - transcript
  - delivery_video
evidence_requirements:
  - "The spoken source must cover the opening 25 percent and the transition into the body so the current-reality baseline, gap pivot, and Big Idea can be ordered."
  - "A thesis statement alone is insufficient; evidence must locate the current-versus-future gap and its structural transition language."
not_evaluable_when:
  - "The transcript or video omits part of the opening or the opening-to-body transition."
  - "The transcript lacks verified ordering or timing needed to place the candidate pivot in the opening zone."
  - "The complete presentation purpose is unavailable, so the non-persuasive applicability condition cannot be assessed."
related_patterns: [sparkline, the-big-why, opening-punch, narrative-arc, foreshadowing, know-your-audience, mentor]
inverse_of: []
difficulty: intermediate
---

# Call to Adventure

## Summary
The first structural turning point of a persuasive presentation — the moment the speaker dramatizes the gap between "what is" and "what could be," reveals the Big Idea, and ends the audience's option to remain neutral.

## The Pattern in Detail
Call to Adventure is the named first turning point in Nancy Duarte's sparkline. It borrows the term from Joseph Campbell's Hero's Journey, where the call to adventure is the moment the hero is summoned to leave the ordinary world and enter the special world. In a presentation, the audience is the hero; the call to adventure is the moment the speaker forces a confrontation between the audience's current reality and the proposed future.

Structurally, Call to Adventure sits at the boundary between the talk's opening section ("what is" — the agreed baseline of the world) and the middle section (the persuasive oscillation between current and proposed states). The opening section establishes common ground and demonstrates that the speaker understands the audience's perspective; the call to adventure ends that consensus by introducing tension — a problem to solve, an opportunity being missed, a contradiction in the current state, a gap between aspiration and reality.

This is a different pattern from `opening-punch` (which classifies the *flavor* of the opening hook — Personal, Unexpected, Novel, Challenging, Humorous). Opening-punch describes how the talk begins; Call to Adventure describes the structural transition out of the beginning. A talk often opens with a PUNCH-flavored hook, then continues to establish "what is," then delivers the Call to Adventure several minutes in. The two patterns operate at different levels and frequently coexist.

The Call to Adventure has three components:

1. **A clear "what is" baseline immediately before it.** The audience must recognize the current reality being described. Without that recognition, the gap that follows has nothing to contrast against.

2. **An explicit gap revelation.** The speaker names the contrast. Often this is signaled with structural language: *"But here's what we've been missing…"*, *"Imagine instead a world where…"*, *"What if I told you…"*, *"The truth is…"*, *"This is the opportunity we keep walking past."* The phrasing is varied; the structural function is constant — pivot from current reality to proposed alternative.

3. **The Big Idea, stated.** The Call to Adventure is the moment the audience first encounters the talk's central thesis in its complete form. Not a topic ("today we'll talk about climate"), not a teaser, but the full single-sentence Big Idea with stakes: *"Worldwide pollution is killing the ocean and us — and we have less than a decade to reverse it."*

After the Call to Adventure, the audience cannot stay neutral. They are now actively engaging with the proposed change (working through how it affects them, what it would require, whether they accept the framing) or actively resisting (looking for holes, defending the current state, dismissing the speaker). Either response is preferable to passive consumption — a Call to Adventure that doesn't move anyone hasn't worked.

## When to Use / When to Avoid
Use Call to Adventure in any presentation built on the `sparkline` structure or any presentation whose central job is to move an audience to a position they don't currently hold. The pattern is essentially mandatory for sales pitches, organizational change announcements, fundraising talks, advocacy keynotes, and investor presentations.

Avoid the pattern (or de-emphasize it) in presentations whose job is informative rather than persuasive — tutorials, technical deep-dives, status updates, scientific explanations. In an informative talk, forcing a Call to Adventure can feel manipulative because there is no genuine action being requested.

The pattern is also weakened when the gap is too small. If "what is" and "what could be" are too close together, the dramatic tension collapses and the audience experiences the moment as ordinary content. A useful test: would a thoughtful audience member take a different action tomorrow as a result of accepting your Big Idea? If yes, the gap is real; if no, you don't have a Call to Adventure, you have a comparison.

## Detection Heuristics
The vault should look for the structural transition specifically:
- An identifiable moment in the opening 10–25% of the talk where the speaker pivots from describing current reality to introducing tension
- Transition phrasing that signals the pivot ("But…", "Imagine…", "What if…", "Here's the problem…", "The opportunity we're missing…")
- A complete-sentence Big Idea statement at or immediately after the pivot
- Audience response indicators in the transcript — laughter, applause, or audible shift in attention often follow a well-executed Call to Adventure

The clearest absence-signal is a talk that progresses smoothly from setup to conclusion without any structural pivot — pure information delivery with no called-out moment of tension.

## Scoring Criteria
- Strong signal: Clear "what is" baseline; explicit gap-reveal moment with structural transition language; complete Big Idea stated at the pivot; audience response evident in transcript
- Moderate signal: Some gap-reveal happens but is muted — Big Idea is implied rather than stated, or the transition is gradual rather than pivot-shaped, or "what is" baseline is too thin to provide contrast
- Absent: Talk progresses linearly from setup to conclusion with no identifiable structural pivot; thesis is never stated as a single complete sentence; no moment after which the audience cannot remain neutral

## Evidence Gate
Use `strong_evaluable_from`, `evidence_requirements`, and `not_evaluable_when` above to evaluate positive evidence.
Current catalog artifacts may support positive detection only. Because `absence_evaluable_from` is `null`, no delivery video, transcript, rendered or native deck, comparison artifact, or claim of full coverage authorizes an absence finding; when no positive signal is established, record `not_evaluable`, not `absent`.

## Relationship to Vault Dimensions
Relates to Dimension 1 (Opening Pattern). Relates to Dimension 2 (Narrative Structure) as one of two named turning points in the sparkline form. Relates to Dimension 9 (Persuasion Techniques).

## Combinatorics
Call to Adventure pairs with `sparkline` (where it is the first of two turning points), with `the-big-why` (which is the content delivered at the pivot — the Big Idea construction rules live in the "Big Idea — Statement Format" subsection of `the-big-why.md`), with `opening-punch` (which sets up the room before the Call to Adventure lands), and with `foreshadowing` (early plants from the opening section often pay off at the Call to Adventure). It is reinforced by `know-your-audience` and the audience-as-hero stance from `mentor` — the speaker who has truly researched their audience produces a Call to Adventure that lands precisely on the audience's actual gap rather than a generic gap.

## Related Reading
- Duarte, N. (2010). *Resonate: Present Visual Stories that Transform Audiences.* Ch. 2, 4 — Call to Adventure as the first sparkline turning point; explicit treatment of the "create dramatic tension by contrasting the commonplace with the lofty" rule, with case-study examples (Steve Jobs's iPhone launch, Beth Comstock's "Growth in a Downturn") that demonstrate the move. Wiley.
