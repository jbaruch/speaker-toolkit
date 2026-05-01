---
id: call-to-action
name: Call to Action
type: pattern
part: build
phase_relevance:
  - content
  - publishing
vault_dimensions: [4, 6, 9]
detection_signals:
  - "explicit imperative ask in the closing zone"
  - "asks are specific and immediately executable, not generic"
  - "asks are differentiated by audience action type (doer/supplier/influencer/innovator)"
  - "the ask is named, not implied"
related_patterns: [sparkline, coda, mentor, the-big-why, foreshadowing]
inverse_of: []
difficulty: foundational
---

# Call to Action

## Summary
The second structural turning point of a persuasive presentation — the moment the speaker delivers explicit, specific, immediately-executable asks differentiated by audience action type, transitioning the talk from middle to close.

## The Pattern in Detail
Call to Action is the named second turning point in Nancy Duarte's sparkline. It sits at the boundary between the talk's middle section (the persuasive oscillation between current and proposed states) and the closing section (the new-bliss future-state vision). Its job is to convert the audience's accumulated agreement into specific behavior. Without a Call to Action, even an audience that fully bought into the Big Idea has nothing concrete to do, and the persuasion fails to land.

Most presentations fail at this moment in one of three ways. The most common is **vagueness** — generic asks like "I hope you'll consider this" or "let's all do better" or "any questions?" These do not convert agreement into action; they evaporate the moment the audience leaves the room. The second failure is **omission** — the talk ends with a thank-you or a credentials slide, with no ask at all. The audience leaves feeling moved but with nowhere to direct that motion. The third failure is **homogeneity** — a single ask delivered as if every audience member could execute it. Real audiences contain people with different roles, resources, and authorities; a single ask leaves most of them unable to participate.

The pattern requires two specific construction rules:

**Specificity rule.** Asks must be concrete enough that a willing audience member can begin executing them tomorrow. "Support sustainability" is not an ask — it is a value statement. "Sign up to volunteer 4 hours per month at sustainabilityorg.example by the end of next week" is an ask. "Buy our product" is borderline — it depends on whether the audience has direct purchase authority. Test: can the audience member reach for a phone or laptop within five minutes and start the action? If not, the ask is too abstract.

**Action-typology rule.** Every audience contains four action-temperament types, each capable of contributing differently:

- **Doers** instigate activities. Asks: assemble, decide, gather, respond, try.
- **Suppliers** provide resources (financial, human, material). Asks: acquire, fund, provide resources, provide support.
- **Influencers** change perceptions. Asks: activate, adopt, empower, promote.
- **Innovators** generate ideas. Asks: create, discover, invent, pioneer.

Provide at least one ask per type — every audience contains all four. A truly engaged audience member may be able to execute multiple types, but the typology ensures *no* audience member is left with "this isn't for me." A practical implementation: structure the Call to Action as a short list of differentiated asks ("If you have budget authority, do X. If you have a team to influence, do Y. If you can spend a Saturday building, do Z."). The list does not need to be balanced — the proportion can match the speaker's expectation of audience composition — but all four types should be represented.

The Call to Action is **not** the end of the talk. After delivering the asks, the speaker must follow up with the new-bliss vision (`new-bliss` pattern, when added) — the picture of the world after adoption. Ending on a to-do list leaves the audience feeling burdened; ending on a vivid future restores motivation and gives the asks their purpose. The structural sequence is: middle → Call to Action → New Bliss → close.

## When to Use / When to Avoid
Use Call to Action in any presentation whose central goal is to move the audience to a position or behavior they don't currently hold. Mandatory for sales pitches, organizational-change announcements, fundraising talks, advocacy keynotes, and investor presentations.

For informative talks (tutorials, technical deep-dives, status updates), the pattern can be softened: the "ask" might be "go try this technique on a real codebase this week" or "next time you face this scenario, try this approach." The action-typology rule still applies but with lower stakes. A pure educational talk that ends with no ask at all leaves learning ungrounded — even tutorials benefit from a small executable ask.

Avoid hard Call to Action moments only when the presentation is purely ceremonial (a eulogy, a celebration, an announcement of a fait accompli) where action is not the point.

## Detection Heuristics
The vault should look for the imperative-ask cluster in the closing 15–25% of the talk:
- Explicit imperative phrasing ("do this", "go to", "sign up", "tomorrow, try…")
- Multiple distinct asks rather than a single homogeneous ask
- Differentiation by audience role or resource type
- Specificity that could be executed within hours of leaving the room
- Pivot language that signals the talk has entered the ask phase ("So here's what I need from you…", "Here's what to do next…", "Three things you can do tomorrow…")

The clearest absence-signal is a closing zone consisting only of "thanks", "questions", or a generic value-statement summary.

## Scoring Criteria
- Strong signal (2 pts): Multiple specific, immediately-executable asks differentiated by action-temperament type; pivot language clearly marks the structural transition; followed by a new-bliss future-state vision (not the talk's literal end)
- Moderate signal (1 pt): A clear ask is present but not differentiated by action type, OR multiple asks but all addressed to a single audience type, OR specific ask but no new-bliss follow-up (talk ends on the to-do list)
- Absent (0 pts): No identifiable ask in the closing zone; talk ends on a thank-you, a credentials slide, a Q&A invite, or a generic value statement

## Relationship to Vault Dimensions
Relates to Dimension 4 (Audience Interaction) because the Call to Action is the most explicit moment of speaker-to-audience direction in the entire talk. Relates to Dimension 6 (Closing Pattern) as one of two named structural elements in the closing zone (alongside `coda` and `new-bliss`). Relates to Dimension 9 (Persuasion Techniques) because the Call to Action is the moment persuasion converts to behavior — without it, persuasion remains abstract.

## Combinatorics
Call to Action pairs with `sparkline` (where it is the second of two turning points), with `the-big-why` (the asks must serve the Big Idea — every ask should make the Big Idea more real; the Big Idea construction rules live in the "Big Idea — Statement Format" subsection of `the-big-why.md`), and with `mentor` (the audience-as-hero stance dictates that the asks empower the audience's own journey rather than serve the speaker's agenda). It composes immediately with `new-bliss` (which must follow it for the closing to land) and with `coda` (which provides the reference materials supporting the asks — links, resources, contact information).

It is the inverse of the unnamed antipattern of the "thanks-and-questions" close — a closing zone that delivers no ask, leaves the audience without a path forward, and hopes that motivation alone will produce action.

## Related Reading
- Duarte, N. (2010). *Resonate: Present Visual Stories that Transform Audiences.* Ch. 4 — the Call to Action as the second sparkline turning point; the action-temperament typology (Doer/Supplier/Influencer/Innovator) with sample asks per type; the rule that the Call to Action must be followed by a new-bliss vision rather than ending the talk. Wiley.
