---
id: spaced-followup
name: Spaced Follow-Up
type: pattern
part: deliver
phase_relevance:
  - publishing
vault_dimensions: [6]
detection_signals:
  - "post-event re-exposure to the talk's core content"
  - "follow-up prompts audience recall rather than re-delivering material"
  - "contact channel established during the talk for later use"
related_patterns: [retrieval-beat, coda, call-to-action, live-on-tape, social-media-advertising, crucible]
inverse_of: []
difficulty: intermediate
observable: false
---

# Spaced Follow-Up

## Summary
The talk ends and the forgetting starts. Schedule one deliberate re-exposure days or weeks later — and make it **ask** rather than **tell**. Three recall questions in an email outperform the most beautiful handout ever attached to one.

## The Pattern in Detail
Every other pattern in this catalog operates inside the room. This one is the only move available after the audience has stood up, and it exists because of an unavoidable fact about how memory works: the spacing effect — the finding that learning distributed across time massively outperforms the same learning massed into one block — operates on a scale of days and weeks. It cannot be executed inside a 45-minute talk. There is no arrangement of slides that produces spacing. The only place a speaker can spend it is *after*.

Nearly every speaker already does something post-talk: slides get posted, a recording goes up, a link tree lands in the closing slide. All of that is *availability*, not spacing. Availability is passive and self-selecting — it serves the handful of people already motivated enough to go re-read, who are the people who least needed the help. Spacing is a push, and it is timed to arrive after forgetting has begun but before the material is gone entirely.

The shape is small. A week or two after the talk, the people who opted in get a short message containing **two or three questions rather than a summary**. *"Quick one: what were the three constraints we said every caching decision trades against? Reply if you want the answers — or they're at the bottom."* The questions are the payload. A summary would be a restatement, which is the same low-yield move that `retrieval-beat` displaces inside the room, merely relocated to an inbox. The follow-up is a `retrieval-beat` fired at a delay of ten days, and the delay is the entire point: recalling something ten days later, when it has begun to fade, is the version of retrieval that the literature associates with durable gains.

This requires an opt-in channel, which means the pattern's real prerequisite lands during the talk itself: a way to reach people who want to be reached. A short link, a QR code on the closing slide, a list signup framed as the thing it actually is — "I'll send you three questions in two weeks to see what stuck" — which is a markedly more honest and more interesting offer than "join my newsletter." That framing tends to attract a smaller list of considerably more engaged people, which is the correct trade.

**The pattern's cost is a real one and it is not the writing.** It is that you now owe strangers something in two weeks, when the talk is over, the conference high has worn off, and you are on to the next thing. Most speakers who set this up execute it once and abandon it, which is worse than never starting: a list that expected a follow-up and got silence has been taught that your offers are noise. If the follow-through is not there, do not collect the addresses. This is the same commitment logic `proposed` applies to abstracts — the ask is a promise.

Be clear-eyed about the ceiling. Open rates are what they are; a follow-up reaches a fraction of a list that is already a fraction of the room. The pattern will not rescue a talk nobody cared about, and its effect on any individual attendee is modest. It is worth doing because it is nearly free and it is the *only* instrument that operates on the timescale where durable memory is actually decided — not because it is powerful. A speaker who wants scale should ship a better talk; a speaker who wants retention among the people who already cared should ship the follow-up.

## When to Use / When to Avoid
Use Spaced Follow-Up for teaching-shaped talks whose value is measured in what the audience can do afterward: tutorials, workshops, internal training, conference deep dives, and any talk delivered to a group you will see again. Use it especially for internal and corporate talks, where the audience is a known, reachable list and the follow-through costs one calendar reminder.

Use it when the talk has a `call-to-action` that needs a nudge at exactly the moment enthusiasm has decayed — a two-week follow-up is a well-timed second ask, and it converts better than the in-room ask alone for the simple reason that the in-room ask arrived while everyone was thinking about lunch.

Avoid it for keynotes and one-shot inspirational talks, where the contract is emotional rather than instructional and a pop quiz two weeks later would be tonally absurd. Avoid it when you cannot commit to actually sending the thing. Avoid turning it into a drip campaign: this is one message, possibly two. A third is marketing, and the audience will correctly reclassify the whole exercise as list-building with a learning-science costume on.

## Detection Heuristics
The follow-up itself happens after the recording stops and leaves no trace. Only its **in-room prerequisite** is visible, and only when the speaker announces it:
- Closing-slide or closing-remark evidence of an opt-in channel — a short link, a QR code, a list signup — framed around later contact rather than generic self-promotion
- Explicit announcement of the follow-up and its shape: "I'll send you a few questions in two weeks", "you'll get three questions, not a newsletter"
- Counter-signal: a closing slide offering slides, a recording, or a link tree only. That is availability, and availability is not this pattern.

The execution — whether the message was ever actually sent, and whether it asked or told — is invisible to the vault and is confirmed only by the speaker.

## Scoring Criteria
Score the in-room prerequisite only; never infer the follow-up itself from the talk.
- Strong signal (2 pts): A named opt-in channel on the closing slides, explicitly framed as a later re-exposure with a stated shape and timeframe
- Moderate signal (1 pt): An opt-in channel exists but is framed generically (newsletter, "follow me"), with no stated follow-up intent
- Absent (0 pts): No opt-in channel, or post-talk provision is availability only — slides, recording, links

## Relationship to Vault Dimensions
Relates to Dimension 6 (Closing Pattern), the only dimension it can touch, and only through the in-room prerequisite that rides on the closing slides.

**This pattern is unobservable and must not appear in the speaker profile's `pattern_profile`.** The vault cannot see the follow-up; it can see, at most, that a channel was opened. The pattern surfaces in **creator Phase 6 (Publishing / Go-Live)** as a post-event checklist item, under a Post-Event heading — it is the catalog's only entry whose action lands after the talk rather than before or during it.

## Combinatorics
Spaced Follow-Up is `retrieval-beat` executed at a delay of days instead of seconds; the two are the same instrument at two timescales, and a talk that runs beats in the room and a follow-up afterward has covered the only two windows available to it. It composes with `call-to-action` (the follow-up is where the ask gets its second, better-timed attempt) and with `coda` (the coda supplies the reference material the follow-up's answers can point back to, which is exactly the division of labor: coda is availability, follow-up is push).

It is distinct from `live-on-tape` and `social-media-advertising`, both of which are also post- or peri-event but are *distribution* rather than *retention* — they reach new people rather than deepening the people already reached. It feeds `crucible`: the replies to a follow-up are the most honest data a speaker can get about what actually landed, and unlike `red-yellow-green`'s in-the-moment satisfaction read, the replies measure what survived two weeks. A follow-up whose questions nobody can answer is telling you something the applause did not.

## Related Reading
- Brown, P. C., Roediger, H. L., III, & McDaniel, M. A. (2014). *Make It Stick: The Science of Successful Learning.* Ch. 3 — "Mix Up Your Practice" covers the spacing effect and the finding that spaced retrieval, which feels harder and less productive than massed review, produces the more durable result. Ch. 2's treatment of distributed low-stakes quizzing supplies the ask-don't-tell shape of the follow-up itself. Belknap Press / Harvard University Press.
