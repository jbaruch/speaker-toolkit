---
id: red-yellow-green
name: Red Yellow Green
type: pattern
part: deliver
phase_relevance:
  - publishing
vault_dimensions: [4]
detection_signals:
  - "audience feedback mechanism"
  - "exit polling"
  - "colored card voting"
related_patterns: [crucible, know-your-audience, retrieval-beat, spaced-followup]
inverse_of: []
difficulty: foundational
observable: false
---

# Red Yellow Green

## Summary
Use colored cards near the room entrance for instant audience feedback — attendees drop a card in a bucket on the way out. Green means great, yellow means okay, red means poor. Simple, immediate, and honest.

## The Pattern in Detail
Most conference feedback systems are broken. Online surveys have abysmal completion rates. Written evaluations are filled out hours later when memories have faded and the emotional response has cooled. The Red Yellow Green pattern provides an elegantly simple alternative: place three stacks of colored cards (red, yellow, green) near the room entrance and a bucket or box by the exit. As attendees leave, they drop one card — green for "great talk," yellow for "decent but room for improvement," red for "this did not work for me." No forms, no logins, no writing required.

The simplicity of the system is its greatest strength. The barrier to participation is almost zero — picking up a card and dropping it in a bucket takes less than two seconds. This means you get feedback from a much higher percentage of the audience than any other method. The physical, immediate response captures the audience's genuine in-the-moment reaction rather than a post-hoc rationalization. People vote with their gut, which is often more honest than what they would write in a considered review.

The scoring is tallied immediately after the session. Count the cards, calculate the ratios, and you have an instant, quantitative read on how the audience received your talk. Over time, tracking these ratios across venues and audiences reveals patterns: maybe your talk works better for smaller audiences, or maybe the afternoon slot hurts your numbers, or maybe a specific section consistently correlates with yellow and red cards.

The system also provides psychological safety for the audience. Dropping a red card is anonymous and takes two seconds; writing a negative review requires composing criticism and attaching your name (or at least your identity to the feedback platform). Many people who would never write a negative review will drop a red card, giving you more honest feedback. This is valuable — the criticism you do not hear is the criticism you cannot act on.

One refinement is to add a small comment card for anyone who wants to provide written feedback alongside their color card. This captures the detail that the color system lacks without requiring it of everyone. You might also experiment with a fourth color or a numbered scale, but simplicity is the pattern's core virtue — resist the temptation to complicate it.

### Smile Sheets Do Not Measure Retention
Everything above is true and the pattern is worth running. It is worth being exact about what the cards measure, because the answer is narrower than it looks and the gap has consequences.

A green card means *"I enjoyed that."* It does not mean *"I learned that,"* and the two travel together far less reliably than anyone would like — the training literature has been unhappy about the weak relationship between end-of-session satisfaction ratings and actual learning for decades, which is why "smile sheet" is a pejorative in that field. The card is cast on the way out, at the emotional peak, by someone who has not yet tried to use anything they heard. It is a review of an experience, not a measurement of an outcome.

Worse, the two can point in opposite directions. Fluent, frictionless, well-polished delivery reliably produces high satisfaction and — on its own — poor retention; that is `_anti_nodding-room.md` in one sentence. Meanwhile the moves that most improve retention are the ones that introduce friction: a `retrieval-beat` that makes someone fail to remember in front of their peers, a `guess-first` that makes the room commit to a wrong number. Those moments do not feel good. A room asked to work is a room slightly less inclined to reach for the green card.

The consequence lands on `crucible.md`. Crucible's engine is iterative refinement driven by feedback, and an engine is only as good as its input. Feed it satisfaction data across ten deliveries and it will faithfully optimize toward the smoothest, most agreeable, most nodding-friendly version of the talk — sanding off the friction that was doing the actual work, while the ratios climb the whole way. The mechanism is invisible from the inside because every signal says it is working.

So keep the cards, and calibrate what you spend them on:

- **Read them as what they are.** Ratios are an energy and fit signal — did this land with this room, in this slot, at this venue. That is genuinely useful and this pattern remains the cheapest way to get it. It is not a learning measurement, and a run of green cards is not evidence anything stuck.
- **Do not let a red-card dip veto a retrieval move.** If the ratios dropped the delivery you started asking the room to work, that is expected, and it is not a reason to revert. Effortful is supposed to feel worse.
- **Pair with an instrument that measures recall.** `retrieval-beat` gives you an in-room read on what actually landed — a room that cannot answer has told you more than a bucket of green cards can. `spaced-followup` gives you the two-week version, which is the only signal in this catalog that measures what survived rather than what pleased.

## When to Use / When to Avoid
Use this pattern whenever you want honest, high-participation feedback and have logistical control over the room setup (you need to place cards and a collection bucket). It works best at conferences and meetups where you will present the same talk multiple times and want to track improvement. Avoid it in very small settings (under ten people) where anonymity is impossible and direct conversation is better, or in venues where you cannot control the room setup.

## Detection Heuristics
- Physical feedback mechanism visible near the room exit
- Speaker mentions the feedback system at the start or end of the talk
- Evidence of systematic feedback collection and tracking
- Speaker references feedback trends across multiple deliveries

## Scoring Criteria
- Strong signal (2 pts): Structured, low-barrier feedback mechanism in place, evidence that feedback is collected and acted upon across deliveries
- Moderate signal (1 pt): Some feedback collection but using higher-barrier methods (online surveys, written forms) with lower participation rates
- Absent (0 pts): No feedback mechanism beyond whatever the conference provides by default

## Relationship to Vault Dimensions
This pattern maps to Vault Dimension 4 (Audience Engagement). While it operates at the end of the talk rather than during it, the feedback loop it creates ultimately improves engagement in future deliveries. The audience also feels valued when they see a speaker actively seeking their input.

## Combinatorics
Red Yellow Green feeds directly into Crucible (feedback drives iterative improvement), supports Know Your Audience (feedback patterns reveal audience preferences), and pairs with Seeding Satisfaction (positive pre-talk interactions often correlate with more generous post-talk feedback). It can also inform Emotional State adjustments for future deliveries at similar venues.

Its blind spot is covered by `retrieval-beat` (in-room recall) and `spaced-followup` (delayed recall), which measure what the cards cannot; see "Smile Sheets Do Not Measure Retention" above for why the pairing matters and how satisfaction-only feedback steers `crucible` toward `_anti_nodding-room.md`.

## Related Reading
- Brown, P. C., Roediger, H. L., III, & McDaniel, M. A. (2014). *Make It Stick: The Science of Successful Learning.* Ch. 5 — "Avoid Illusions of Knowing" establishes that subjective confidence and satisfaction are systematically poor proxies for learning, and that fluent delivery inflates both while doing little for retention. Belknap Press / Harvard University Press.
