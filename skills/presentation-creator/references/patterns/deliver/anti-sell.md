---
id: anti-sell
name: Anti-Sell
type: pattern
part: deliver
phase_relevance:
  - content
vault_dimensions: [9]
evidence_channels: [transcript, video]
detection_signals:
  - "speaker downplays own product, employer, or work"
  - "self-deprecating framing of own credentials"
  - "explicit hedge against perceived sales pitch"
evaluable_from:
  - transcript
  - delivery_video
strong_evaluable_from:
  - delivery_video
absence_evaluable_from: null
evidence_requirements:
  - "A positive finding must locate an explicit deflection tied to the speaker's own product, employer, book, credentials, or other visible commercial interest; general humility or a vendor-neutral tone does not qualify."
  - "A strong finding requires delivery video showing the brief deflection, its humor or register, and the later structural choice not to pitch."
not_evaluable_when:
  - "The source does not establish a visible commercial or credential context that could create a pitch expectation."
  - "Only a neutral product mention, generic self-deprecation, or excerpted disclaimer is available without the surrounding delivery needed to establish Anti-Sell."
related_patterns: [delayed-self-introduction, the-big-why, mentor]
inverse_of: [disowning-your-topic]
difficulty: intermediate
---

# Anti-Sell

## Summary
Actively downplay your own products, employer, or credentials at the moments where the audience expects a pitch. The technique buys credibility by signaling that the talk is about ideas, not about selling, and lets the speaker make stronger product claims later by having visibly resisted weaker ones.

## The Pattern in Detail
A vendor-affiliated speaker walks into a talk carrying an automatic credibility tax: the audience suspects the talk is a pitch in disguise. Anti-Sell is the deliberate work of paying that tax up front. The speaker mentions their employer or product in a deflated, self-deprecating register — "I work at X, but this isn't a pitch," "we make Y, which is fine, you can look it up later" — and then moves on to the topic. The hedge tells the audience: I know what you were worried about, and I will not be doing that.

If the audience spends the first ten minutes wondering when the pitch will arrive, they are not absorbing the content. Anti-Sell preempts the worry. Once the audience trusts that the talk is not a sales call, they grant the speaker the same attention they would grant a vendor-neutral expert. Paradoxically, this trust makes any later product mention land harder.

A skilled Anti-Sell mention is brief, slightly humorous, and structurally tied to the topic — "I wrote a book about this, which was hard, so I guess it's good, maybe." The speaker concedes the conflict of interest, refuses to lean into it, and moves on. The pattern fails when the deflection is too long (now it sounds like the speaker is fishing for compliments) or too earnest (now it sounds like a different kind of pitch).

## When to Use / When to Avoid
Use Anti-Sell whenever the speaker has a visible commercial affiliation — works for a vendor whose product is relevant to the talk, has authored a book on the topic, leads a tool or framework being discussed. The pattern is essential for talks at conferences where the audience expects vendor talks to be pitches. Avoid Anti-Sell when there is no real conflict of interest (it sounds like fake humility), and avoid it as a substitute for not pitching — if the talk eventually does pitch the product, the Anti-Sell opening reads as a setup, which damages trust more than a clean pitch would have.

## Detection Heuristics
Look for moments where the speaker mentions their employer, product, book, or credentials in a deflated or self-deprecating register. Phrases like "this isn't a pitch," "you can ignore the bio," "we make X, which is fine" are positive signals. The deflection should appear in the opening or at the moments where a product mention is structurally unavoidable.

## Scoring Criteria
- Strong signal: explicit, brief, humor-tinged Anti-Sell mention at the talk's opening and at any product reference; visible structural choice not to pitch
- Moderate signal: one Anti-Sell mention or a generally vendor-neutral framing without explicit deflection
- Absent: In an established pitch-expectation context, a straight product or employer pitch proceeds with no visible hedge

## Evidence Gate
Use `strong_evaluable_from`, `evidence_requirements`, and `not_evaluable_when` above to evaluate positive evidence.
Current catalog artifacts may support positive detection only. Because `absence_evaluable_from` is `null`, no delivery video, transcript, rendered or native deck, comparison artifact, or claim of full coverage authorizes an absence finding; when no positive signal is established, record `not_evaluable`, not `absent`.

## Relationship to Vault Dimensions
Dimension 9 (Self-Presentation): how the speaker positions themselves relative to commercial interests. Dimension 9 (Evidence and Persuasion): a credibility move.

## Combinatorics
Pairs naturally with Delayed Self-Introduction (the bio comes late, and when it comes it includes the Anti-Sell). The Big Why benefits when Anti-Sell has cleared the suspicion that the "why" is sales-driven. Mentor framing is reinforced — the speaker who refuses to pitch reads as someone there to teach. The pattern is the inverse of Disowning Your Topic, where the speaker sounds embarrassed by their own affiliation; Anti-Sell owns the affiliation while refusing to weaponize it.

## Related Reading
- Reynolds, G. (2012). *Presentation Zen.* Ch. 5 — credibility-by-restraint: speakers who do not oversell themselves are perceived as more authoritative. New Riders.
