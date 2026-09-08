---
id: crowd-work
name: Crowd Work
type: pattern
part: deliver
phase_relevance:
  - content
  - publishing
vault_dimensions: [4, 12]
evidence_channels: [transcript, video]
detection_signals:
  - "live execution stalls the screen and the speaker turns to the room instead of narrating filler"
  - "audience question taken or invited during a demo wait rather than at a planned Q&A beat"
  - "the wait is named out loud rather than covered over"
  - "material generated in the gap is reused later in the talk"
evaluable_from:
  - transcript
  - delivery_video
strong_evaluable_from:
  - delivery_video
absence_evaluable_from: null
not_applicable_when:
  - condition_id: no-live-execution-waits
    description: "The delivery contains no live execution that can stall — pre-recorded demo playback, slide-only delivery, or a recorded talk with no on-stage waits — so there is no wait available to convert."
applicability_evaluable_from:
  - transcript
  - delivery_video
evidence_requirements:
  - "Evidence must establish both halves: that live execution left a wait, and that the speaker filled it by engaging the room rather than by narrating filler."
  - "A timestamped transcript must show the gap and the audience exchange inside it; a strong finding additionally requires video establishing that the screen was genuinely stalled."
not_evaluable_when:
  - "Only a deck or an untimestamped transcript is available, so waits cannot be located."
  - "The recording does not capture audience audio, so what happened in the gap cannot be established."
  - "The demo track is pre-recorded playback, so no wait exists and the applicability condition cannot be assessed from the artifacts."
related_patterns: [live-demo, brain-breaks, breathing-room, know-your-audience, greek-chorus]
inverse_of: []
difficulty: advanced
---

# Crowd Work

## Summary
Live execution stalls. An agent thinks, a build runs, a deploy churns — and the screen goes static for thirty to ninety seconds while the room watches nothing happen. Hand that time to the audience instead of narrating filler. The gap is not an interruption of the talk; it is the only unscripted room you get, and it is where the best material comes from.

## The Pattern in Detail

Every talk built on live execution has a structural problem the pre-recorded version does not: dead air. The demo is honest, the risk is real, and the price is that the speaker regularly has nothing to do for a minute at a time. The instinctive responses are all bad. Narrating the spinner ("so it's thinking about the file structure now…") teaches nothing and sounds nervous. Filling with "okay" burns credibility a syllable at a time. Reading ahead on the slides breaks the reveal the demo was set up to deliver.

Crowd Work treats the wait as a resource. The speaker turns to the room and asks something — a prediction about the run in progress, an unrelated question they were going to ask later, or simply "what do you want to know while this finishes". Questions come back. Because the exchange is unrehearsed, it produces the two things a scripted talk cannot manufacture: genuine surprise and material specific to this room.

Two properties make it work rather than merely fill.

**Name the gap; do not cover it.** Acknowledging the dead air out loud converts an awkward silence into a shared joke and buys the speaker the right to change subject. Covering it pretends the audience cannot see the screen.

**Bank what the gap produces.** The exchange is not disposable. A question asked during a wait can be answered properly two slides later; a heckle can be recycled as a callback at the close. The gap stops being a hole in the talk once its output re-enters the talk.

The pattern is only reachable in `live-demo` mode. A `lipsync` delivery of identical material never stalls, and therefore never produces any of this — which is a real, usually unacknowledged cost of choosing tape over live.

## When to Use / When to Avoid

Use it whenever the talk runs anything live whose duration you do not control: agents, builds, deploys, remote APIs, hardware. Use it especially when the wait is long enough that silence would be conspicuous but short enough that a `brain-breaks` detour would overshoot.

Plan it per demo rather than reaching for it in the moment. Speaker-confirmed
(JavaZone 2026): applied opportunistically it converts only the gaps you happen
to notice and leaves the rest as filler — the converted ones produced the
delivery's best material while others became "okay". Nominating one
audience-facing beat per demo before the stage is what makes the conversion
consistent.

Avoid it when the wait is under about ten seconds — starting an exchange you must abandon mid-answer is worse than a pause. Avoid it when the room has not warmed up enough to answer at all; an unanswered question in dead air compounds the problem rather than solving it, and `know-your-audience` has to come first. Avoid it in a slot so tight that any unplanned exchange threatens the close, since the pattern's failure mode is `shortchanged`.

## Detection Heuristics

- A timestamped transcript shows a gap in demo narration filled by a question to or from the audience.
- The speaker explicitly names the wait ("nothing is happening", "this is the most dynamic demo you've seen").
- Audience turns appear inside demo intervals rather than clustering at a planned Q&A beat.
- Content generated in a wait is referenced again later — the strongest signal, because it shows the gap was harvested rather than merely survived.

Distinguish from `brain-breaks`, which is a planned pacing device placed where the *content* needs relief. Crowd Work is unplanned and placed where the *machine* forces it.

## Scoring Criteria
- Strong signal: The speaker converts live-execution waits into audience exchange repeatedly across the delivery, and at least one exchange produces material that is reused later in the talk
- Moderate signal: Waits are filled with audience engagement, but the output stays in the gap and is never carried forward into the talk
- Weak signal: The wait is named out loud but not converted — the speaker acknowledges the dead air and then fills it alone
- Absent: Live-execution waits occur and are filled with narration, filler, or silence. Absence is never scorable from artifacts alone, because a delivery may simply have had no stalls

## Evidence Gate
Use `strong_evaluable_from`, `evidence_requirements`, and `not_evaluable_when` above to evaluate positive evidence.
Current catalog artifacts may support positive detection only. Because `absence_evaluable_from` is `null`, no delivery video, transcript, rendered or native deck, comparison artifact, or claim of full coverage authorizes an absence finding; when no positive signal is established, record `not_evaluable`, not `absent`.
Not applicable when the demo track is pre-recorded, since no wait exists to convert.

## Relationship to Vault Dimensions

Relates to Dimension 4 (Audience Interaction) as the primary axis, but arrives at interaction from an unusual direction. Most interaction patterns place engagement where the *argument* wants it. Crowd Work places it where the *runtime* forces it, which means the interaction is scheduled by a machine and the speaker's skill is in accepting that schedule gracefully.

Relates to Dimension 12 (Pacing Clues) because the pattern is fundamentally about time the speaker did not choose. A talk with live execution has a pacing profile it cannot fully author; Crowd Work is the technique for spending the unauthored parts.

## Combinatorics

Pairs naturally with `live-demo`, which is its precondition, and with `guess-first` — a prediction about the run currently executing is the most economical wait-filler available, because it is simultaneously crowd work and a primed reveal.

Pairs with `greek-chorus`: a known ally in the room shortens the latency between question and answer, which matters when the wait is short.

Tension with `shortchanged`. Unplanned exchange costs wall-clock that a scripted talk does not spend, and the cost lands at the end. A talk using Crowd Work should carry an `expansion-joints` decision made before the stage — which segment drops, and at which checkpoint the call gets made.

## Related Reading

Field-observed rather than sourced from the literature. First named from JavaZone 2026 ("The Right 300 Tokens Beat 100k Noisy Ones"), where the same talk's two previous deliveries had run the demos as tape and produced none of the improvised material the live cut generated in its waits. Speaker-confirmed in the same-week clarification as a deliberate technique he intends to apply to every wait, not improvisation that happened to work.

The term is borrowed from stand-up, where crowd work denotes the unscripted portion of a set built from direct exchange with the audience. The borrowing is deliberate: comics generally regard crowd work as harder and more valuable than prepared material, which is the right connotation here. This is not stalling.
