---
id: abstract-attorney
name: Abstract Attorney
type: antipattern
part: prepare
phase_relevance:
  - intent
  - guardrails
vault_dimensions: [2, 14]
detection_signals:
  - "abstract doesn't match delivery"
  - "significant deviation from published description"
related_patterns: [preroll, narrative-arc, fourthought, triad, crucible, carnegie-hall]
inverse_of: []
difficulty: foundational
---

# Abstract Attorney

## Summary
An audience member who obsessively catalogs deviations between your abstract and actual talk, rather than focusing on learning.

## The Pattern in Detail
The Abstract Attorney is not a behavior you adopt but a hazard you must defend against. This is the audience member who arrives with your published abstract printed out (mentally or literally) and spends the entire presentation comparing what you said you would cover with what you actually cover. Every deviation, no matter how minor or well-justified, is cataloged as a failure. The Abstract Attorney is not interested in learning from your presentation — they are interested in auditing it.

This antipattern appears whenever you pre-publicize what you will talk about, which is to say, virtually always. Conference abstracts, event descriptions, blog post announcements, even casual social media mentions of your upcoming talk create a contract — implicit or explicit — between you and the audience. When the delivered talk diverges from the described talk, some percentage of attendees will notice and be bothered. The Abstract Attorney is simply the extreme version of a universal tendency.

The root cause of the Abstract Attorney problem is that material takes on a life of its own. You write an abstract months before the event. During preparation, you discover that one of the promised topics does not work as well as you expected, or that a different approach better serves the narrative. You make the right creative decision to deviate from the abstract, but the abstract is already published, printed in the program, and embedded in attendees' expectations. The better your presentation becomes through iteration, the more it may diverge from the original description.

Defenses against the Abstract Attorney are multiple and should be layered. First, produce comprehensive outlines when you have a clear vision — the more specific your abstract, the more you are bound by it, but also the more the audience trusts that they will get what they came for. Second, when you can afford to, be vague — "We'll explore approaches to X" is harder to litigate than "I will demonstrate approaches A, B, and C to solving X." Third, display your abstract on a Preroll slide (the slide visible before the talk officially begins) so attendees can self-select out if the description does not match their needs. Fourth, acknowledge changes explicitly: "The abstract mentions Y, but I've found Z is more useful — let me explain why" disarms the Attorney by showing that the deviation was deliberate and reasoned.

The deeper lesson of the Abstract Attorney antipattern is that your abstract is a promise. Take promises seriously. Do not submit abstracts for talks you have not yet designed in at least broad strokes. Do not promise specific demos or tools you have not yet built. And when you must deviate, do so openly and with explanation rather than hoping nobody will notice.

## When to Use / When to Avoid
Be aware of this antipattern whenever you have pre-published a description of your talk. The defenses are most critical for conference presentations where the abstract was reviewed and approved by a program committee, as these carry the strongest implicit contract. Less critical for internal presentations where expectations are more fluid.

## Detection Heuristics
The vault should look for signs of disconnect between the apparent description of the talk and the delivered content. Significant structural deviations from what the talk claims to cover, missing promised topics, or unexpected diversions all trigger this antipattern.

## Scoring Criteria
- Strong signal (2 pts): Content closely matches what was promised; any deviations are explicitly acknowledged and justified
- Moderate signal (1 pt): Generally follows the described topics but some promised elements are missing or replaced without explanation
- Absent (0 pts): Significant disconnect between described and delivered content; audience likely feels misled about what the talk would cover

## Relationship to Vault Dimensions
Relates to Dimension 2 (Structure/Organization) because the mismatch between abstract and delivery is fundamentally a structural planning issue. Relates to Dimension 14 (Overall Impression/Polish) because abstract-delivery alignment affects the audience's overall trust and satisfaction.

## Combinatorics
Relates to Preroll (displaying the abstract), Narrative Arc (the arc may evolve away from the abstract), Fourthought (thorough pre-planning reduces divergence), Triad (structural commitments in abstracts), Crucible (iterative refinement that may cause divergence), and Carnegie Hall (extensive practice reveals when material diverges from the abstract).
