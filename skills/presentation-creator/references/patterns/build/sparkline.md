---
id: sparkline
name: Sparkline
type: pattern
part: build
phase_relevance:
  - architecture
  - content
vault_dimensions: [2, 5, 9]
detection_signals:
  - "establishes 'what is' baseline before introducing thesis"
  - "explicit gap-revelation moment (call to adventure)"
  - "middle oscillates between current reality and proposed future"
  - "explicit call-to-action with concrete asks"
  - "closes on a 'new bliss' future-state vision higher than the opening"
related_patterns: [narrative-arc, bookends, audience-as-hero, big-idea, call-to-adventure, call-to-action, new-bliss, foreshadowing]
inverse_of: []
difficulty: intermediate
---

# Sparkline

## Summary
Structure a persuasive presentation as an oscillation between "what is" (current reality) and "what could be" (proposed future), bracketed by two named turning points — the Call to Adventure and the Call to Action — and ending on a "new bliss" vision higher than the opening.

## The Pattern in Detail
Sparkline is a persuasion-specific structural pattern named by Nancy Duarte in *Resonate* (2010). It is a sibling of, not a replacement for, `narrative-arc` — where narrative-arc is generic three-act story structure suited to virtually any presentation, sparkline is purpose-built for talks whose central job is to *move an audience to action*. The shape was derived from Duarte's analysis of game-changing presentations including Steve Jobs's 2007 iPhone launch and Martin Luther King Jr.'s "I Have a Dream" speech — both of which mapped exactly onto the form.

The sparkline has three sections and two turning points. The **beginning** (≤10% of the talk's time) describes "what is" — the audience's current reality, the agreed baseline of the world. This is where the speaker establishes common ground and demonstrates that they understand the audience's perspective. Skipping this and jumping straight into the proposed change loses the audience because they have no contrast against which to measure the proposal.

The **first turning point — the Call to Adventure** — dramatizes the gap between "what is" and "what could be." This is the inciting incident, equivalent to the moment in a movie where the protagonist's life is thrown out of balance. The Big Idea is revealed at this turning point. After this, the audience cannot be neutral; they either start engaging with the proposed change or actively resist it.

The **middle** is where the persuasion does its work. Rather than progressing linearly from setup to conclusion, the middle oscillates between "what is" and "what could be" through multiple peaks. Each peak is a content beat that moves the audience a little further from the current world toward the proposed future. The oscillation matters: a presentation that just describes the future without continually re-anchoring against current reality leaves the audience floating; a presentation that just dwells on current reality never persuades. Three types of contrast can drive the oscillation — content (what is vs. what could be), emotional (analytical vs. emotional sections), and delivery (traditional vs. nontraditional methods). Strong sparklines stack all three.

The **second turning point — the Call to Action** — concretely defines what the audience must do. This is not a soft "thanks for listening" or a generic "I hope you'll consider." The call to action gives the audience specific, immediately-executable tasks matched to the four action-temperament types (Doer, Supplier, Influencer, Innovator). Every audience contains all four types; providing at least one ask per type ensures everyone has a way to participate.

The **end — the New Bliss** — is the speaker's vivid description of the world after the audience adopts the proposed change. This is non-negotiable in a sparkline: the talk must end on a higher plane than it started. Ending on a to-do list (the call to action alone) leaves the audience burdened rather than inspired. The new bliss restores motivation by showing what the sacrifice will produce.

The sparkline is **a form, not a formula.** Following the form does not produce identical talks; every sparkline-shaped presentation has its own unique contour driven by the specific oscillations the speaker chooses. The form constrains shape; it leaves content, voice, and pace fully variable.

### The Three Contrast Types — Engine of the Middle
The sparkline's middle works because of contrast. A flat middle, even with strong opening and closing turning points, fails to persuade because the audience experiences it as monotonic information delivery. Duarte names three orthogonal contrast axes that drive the oscillation, and the strongest sparklines deliberately stack all three rather than relying on any one in isolation.

**1. Content contrast — "what is" vs "what could be."** The default contrast axis: every content beat in the middle either reinforces current reality (extending the "what is" baseline established in the opening) or sketches the proposed future (deepening the "what could be" picture from the call to adventure). The middle oscillates between the two — a beat about the broken current state, then a beat about the promising future, then back. This rhythm produces the sparkline's literal up-and-down shape on a timeline.

**2. Emotional contrast — analytical sections alternating with emotional sections.** Borrowed from Hollywood's "beats" terminology — the smallest structural element in a movie scene, where each beat shifts the emotional polarity (hope → fear, certainty → doubt, joy → grief). Applied to presentations: a section of analytical content (data, logic, argument) is followed by a section of emotional content (story, image, anecdote). Together, these track Aristotle's *logos* and *pathos* with the speaker's *ethos* underneath both. John Heritage and David Greatbatch's 1986 study of 476 political speeches found that **half** of all bursts of applause followed a contrast moment — applause is a physical signal that emotional contrast just landed.

The emotional-contrast axis is the most-skipped of the three. Most presentations stay in analytical mode the entire middle and produce talks that audiences agree with but don't feel. The reverse failure — pure emotional content with no analytical scaffolding — produces talks that move audiences in the moment but don't survive scrutiny. The sparkline requires both, deliberately alternating. Practical rule: when scoping a content section, identify whether it leans analytical or emotional and place it adjacent to a section of the opposite polarity. If two analytical sections sit back-to-back without an emotional section between them, the audience disengages.

The emotional contrast must be calibrated to audience type. Highly analytical audiences (scientists, engineers, accountants) tolerate less emotional content per unit time but still need *some* — the reason most analytical professionals chose their fields contains an emotional core, and zero emotional appeal collapses the talk's persuasive value. Broad audiences accept higher emotional ratios. The wrong calibration in either direction (too emotional for analytics; too dry for general) damages credibility — Duarte names this the "rhetorical triangle" of ethos / pathos / logos that must be sized to context, with *karios* (timing) governing when each appeal is appropriate.

**3. Delivery contrast — traditional vs. nontraditional methods.** Stage stance changes (front-and-center vs. moving into the audience), speaking style shifts (serious tone vs. enthusiasm), visual mode changes (slides vs. demo vs. video vs. blank screen vs. physical prop), interaction shifts (one-way delivery vs. polling/shouting/writing/drawing/singing/question-asking). The audience's brain registers a delivery-mode change as "something new is happening," which interrupts the cognitive habituation that builds during a long monotone delivery. Hans Rosling's TED talks land partly because the data is rich, but more because Rosling is *running* on stage during the data visualization rather than narrating from a podium — the delivery contrast against typical academic presentation produces alertness.

Strong sparklines stack all three contrast axes simultaneously. A canonical pattern: an analytical "what is" section delivered at the podium with data slides → emotional "what could be" section delivered front-of-stage with a single full-bleed image → analytical "what is" section returning to data with a live demo → emotional "what could be" section delivered as a personal story with the screen blacked out. The three axes are orthogonal and each one re-engages the audience independently; together they keep the middle from ever feeling like a single mode.

## When to Use / When to Avoid
Use the sparkline when the presentation's central goal is **persuasion**: a sales pitch, a strategic-direction announcement, a call for organizational change, a fundraising talk, a social-cause keynote, an investor pitch. The sparkline shines when the audience is being asked to *do something different after the talk*.

Use `narrative-arc` instead when the talk is primarily *informative* (tutorial, technical deep-dive, scientific explanation, status update) where there is no specific behavior change being requested. Narrative-arc's three-act structure suits content that needs to be *understood*; sparkline suits content that needs to be *acted on*.

The two patterns can coexist within a single talk: a narrative-arc tutorial can have a small sparkline-shaped closing argument. But for a primarily persuasive talk, sparkline is the better default top-level structure.

## Detection Heuristics
Look for the named structural elements:
- **"What is" baseline** in the opening — does the talk acknowledge the audience's current reality before proposing change?
- **Gap revelation** — is there an identifiable moment where the speaker explicitly contrasts current reality with the proposed future? (Often signaled with phrases like "But what if…", "Imagine instead…", "This is the opportunity we're missing.")
- **Mid-talk oscillation** — does the middle keep returning to "what is" / "what could be" contrasts, or does it progress monotonically?
- **Concrete call to action** — does the closing zone include specific, executable asks (vs. generic "thanks" or "any questions")?
- **New bliss vision** — does the talk end on a future-state description, or does it end on the to-do list / a credentials slide / "questions"?

The strongest signal is the explicit call-to-adventure moment. Its presence indicates the speaker thought structurally about the persuasion arc.

## Scoring Criteria
- Strong signal (2 pts): All five elements present and intentional — "what is" baseline, named call-to-adventure gap reveal, oscillating middle with multiple contrast peaks, concrete call-to-action with specific asks, new-bliss closing vision higher than opening
- Moderate signal (1 pt): 3–4 of the five elements present; structure is recognizably persuasion-shaped but missing one or two elements (often the new-bliss close, which is the most-skipped element)
- Absent (0 pts): Generic three-act or topical structure; no identifiable gap-reveal moment; closing is a to-do list or "thanks"; no future-state vision

## Relationship to Vault Dimensions
Relates to Dimension 2 (Narrative Structure) as a top-level structural choice alongside `narrative-arc`. Relates to Dimension 5 (Storytelling/Narrative) because the sparkline encodes a story-shape onto content that might otherwise read as report-style information. Relates to Dimension 9 (Persuasion Techniques) because the sparkline IS the persuasion architecture — its purpose is to move the audience from one stance to another, and every element serves that purpose.

## Combinatorics
Sparkline is composed of several other patterns acting in concert: it begins with `know-your-audience` and `audience-as-hero` (the speaker has researched the hero); the gap-revelation is `call-to-adventure`; the closing zone is `call-to-action` followed by `new-bliss`. It pairs with `bookends` (the structural opening and closing slides mark the sparkline's three sections), with `foreshadowing` (early plants get paid off at later peaks), and with `star-moment` (a planted memorable beat usually lands at one of the high points in the oscillation).

It is **not the inverse** of `narrative-arc`; the two are siblings. A speaker should choose between them based on whether the talk is primarily persuasive (sparkline) or primarily informative (narrative-arc), not treat them as opposites.

## Related Reading
- Duarte, N. (2010). *Resonate: Present Visual Stories that Transform Audiences.* Ch. 2, 6 — the sparkline is the central contribution of the book; Ch. 2 derives the form from Aristotle, Syd Field, Vogler, and Campbell; Ch. 6 walks through structural application. Wiley.
