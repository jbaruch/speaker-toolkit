---
id: walk-around
name: Walk-Around
type: pattern
part: prepare
phase_relevance:
  - architecture
  - content
  - guardrails
vault_dimensions: [4, 9]
detection_signals:
  - "each major claim answers precision, process, impact, and implication questions"
  - "talk supplies numbers, mechanism, human consequence, and long-range framing for the same point"
  - "evidence register matched to a homogeneous room rather than spread across four"
  - "counter-signal: every claim defended in one register only"
related_patterns: [know-your-audience, inoculation, leet-grammars, crucible, peer-review, concrete-before-abstract]
inverse_of: [golden-rule]
difficulty: intermediate
---

# Walk-Around

## Summary
Take each load-bearing claim and walk it around four standing questions — *what exactly?*, *how does it work?*, *who does it hit?*, *where does it lead?* — then revise until the talk answers all four. Any room large enough to be interesting contains all four questions, and a claim defended in one register only lands with the fraction of the room that speaks it.

## The Pattern in Detail
Every speaker has a default register. Ask a data-minded engineer why their approach is right and you get a benchmark; ask a designer and you get a story about a user; ask an architect and you get a diagram of where it all leads. Each answer is correct and each is *partial*, and the speaker rarely notices the partiality — the register they reach for is the one they find convincing, so a talk built entirely in it feels complete from the inside.

It is not complete from the outside. A conference room holds people who want to know the number, people who want to know the sequence, people who want to know who gets hurt, and people who want to know what it means in five years. Give them one of the four and three-quarters of the room is politely waiting for their question to be answered. They will not raise a hand about it. They will conclude the talk was fine and forget it.

The Walk-Around is a preparation audit borrowed from Ned Herrmann's Whole Brain Communication Walk-Around. Herrmann labels the four as quadrants — **A** (Analyzer), **B** (Organizer), **C** (Personalizer), **D** (Strategizer) — and the labels are worth keeping because a chunk of any business audience has met them. What this catalog imports is the *procedure*, not the psychology:

- **A — "What exactly, and how do you know?"** Precision and evidence. The number, its units, its source, its error bars. The claim "we made it faster" fails here; "p99 dropped from 800ms to 120ms across three months of production traffic" passes.
- **B — "How does it work, in what order?"** Mechanism and sequence. What happens first, what depends on what, what the steps actually are. The room that asks this is not slow; it is the room that will have to implement the thing on Monday.
- **C — "Who does this affect, and how will it land?"** Human consequence. Whose job changes, who has to be retrained, who is going to hate this, what it feels like to be on the receiving end. Technical talks skip this question almost universally, and it is the one that decides whether the idea survives contact with an organization.
- **D — "Where does this lead, and what does it connect to?"** Implication and frame. Why this matters beyond the immediate case, what it composes with, what it means in three years.

Herrmann's own worked example is a one-sentence corporate statement — *"it is our strategic intent to double this business in the next five years"* — walked around four ways. **A** asks *double what — revenue, headcount, profit?* **B** asks *with what reorganization?* **C** asks *does this mean doubling everyone's workload?* **D** asks *and then what, is there a plan past year five?* Four questions, one sentence, and the sentence was ambiguous on all four. The revised version answers each. The procedure is mechanical and that is its whole value: it does not depend on the author's judgment about which questions matter, which is precisely the judgment their default register has already corrupted.

**The vocabulary is a handle, not a theory.** Nobody *is* a quadrant. This catalog does not import Herrmann's brain model, his physiological grounding, or the HBDI instrument — and `know-your-audience.md`'s "Learning Styles Are a Myth" applies here with full force. The Walk-Around is not the meshing hypothesis and must not be mistaken for it: meshing says *identify a person's style and tailor delivery to it*, which has no evidential support. The Walk-Around says *assume the room is heterogeneous and cover everything*, which identifies nobody and tailors to no one. Coverage and matching are opposite moves, and only the second one was ever debunked. What the pattern needs to be true is that audiences differ in what evidence persuades them — which is uncontroversial, well-supported, and old enough that Aristotle divided it into ethos, pathos, and logos.

### Coverage or Match — Read the Room's Spread First
Herrmann's book contains a contradiction worth resolving before applying it, because the two halves prescribe opposite things.

Ch. 8 says cover all four quadrants for every significant point. Ch. 13 tells the story of a Whole Brain leadership program taught to engineering faculty at MIT, CMU, and Berkeley, where the model was introduced as a colorful, metaphor-driven visual — and the audience rejected it. As the facilitator put it, the walls went up: they read a metaphor literally, analyzed it as a claim, and found it wanting. Re-introducing the identical model as *"a first-order engineering approximation to mental diversity"* changed the response dramatically. That is not coverage. That is *matching* — same content, re-registered.

Both are right, and the discriminator is the room's spread:

- **Heterogeneous room** — a conference keynote, an all-hands, a mixed-seniority audience. Cover. You cannot know who is out there, so answer all four questions and let each person find theirs.
- **Homogeneous room** — one engineering team, a board, a room of clinicians. Match. Spending airtime on registers nobody in the room uses is airtime stolen from the register everyone uses. A room of engineers does not need the metaphor softened for them; it needs the claim stated as an approximation with stated error.

The failure mode of matching is the more dangerous of the two, since homogeneity is usually assumed rather than verified. "They're all engineers" is a statement about job titles, not about what persuades them, and the engineer who asks *who does this affect* exists in quantity. Verify the spread through `know-your-audience` before betting the talk on it; when in doubt, cover.

Note what the MIT move is *not*. It is not `leet-grammars` — the facilitators did not change their vocabulary, they changed the epistemic form of the argument, from metaphor to approximation. A speaker can deploy flawless insider jargon and still lose a room by offering the wrong *kind* of justification.

## When to Use / When to Avoid
Run the Walk-Around during architecture and again during content, on the talk's load-bearing claims only. It is an audit, not a template: a talk that answers all four questions about all twenty of its claims is a talk nobody has time to sit through. Three or four claims carry a talk; walk those around.

Use it hardest on the claim you are most confident about, since confidence is the tell for default-register blindness — the claim that needs no defense is the one you have only ever defended one way.

Use it in any talk aimed at getting something adopted rather than admired. Adoption requires the B and C answers (how does it work, who does it disrupt), and those are the two that technical speakers cut first.

Avoid mechanical application to every sentence; the Walk-Around is a filter for the claims that matter. Avoid it as an audience-typing exercise — the moment it turns into "the C-quadrant people in the back need a story," it has become the meshing hypothesis with extra steps and should be stopped. Avoid the coverage form in a genuinely homogeneous room, where it dilutes.

## Detection Heuristics
The vault should look for register spread across a claim's defense, not for the vocabulary:
- A load-bearing claim supported by a number *and* a mechanism *and* a human consequence *and* a forward implication, rather than by one of the four repeated
- Explicit answers to the unasked questions: "you're probably wondering what this costs" (A), "here's the order you'd actually do this in" (B), "this means your on-call rotation changes" (C), "and in three years this is table stakes" (D)
- Q&A evidence: questions from the floor that the talk already answered indicate coverage; a cluster of questions all attacking the same missing register indicates a gap the speaker did not see
- Register matching: a homogeneous room addressed in its own dominant register throughout, with the other three deliberately thin
- Counter-signal: every claim in the talk defended the same way. A talk that is all benchmarks, or all anecdote, or all architecture diagram, is running one register and has not been walked around — score it under `_anti_golden-rule.md`

## Scoring Criteria
- Strong signal (2 pts): The talk's major claims are each defended across multiple registers; at least one claim visibly answers all four; the human-consequence and mechanism questions are answered without being asked, which is the rarest evidence of a real audit
- Moderate signal (1 pt): Claims are defended in two or three registers, or the coverage is uneven — one claim walked around, the rest single-register; or a homogeneous room is matched well without evidence the alternatives were considered
- Absent (0 pts): Every claim defended in the speaker's single default register; the unasked questions stay unasked and unanswered

## Relationship to Vault Dimensions
Relates to Dimension 9 (Persuasion Techniques) as the primary axis — the pattern is about what counts as proof to whom, which is a persuasion question rather than a structural one. Relates to Dimension 4 (Audience Interaction) through audience modeling, the same pairing `know-your-audience` carries.

## Combinatorics
Walk-Around is the systematic counterpart to `inoculation`, and the two are worth holding apart. Inoculation voices *one* objection — the strongest, steel-manned — and answers it on stage as a persuasion move. Walk-Around answers *four standing questions* nobody has voiced yet, and it operates in preparation: it changes what gets built rather than what gets said about opposition. A claim that survives the Walk-Around often needs no inoculation, since the objection inoculation would have addressed was usually a register the talk had simply omitted.

It depends on `know-your-audience` for the spread read that decides coverage-versus-match, and the two compose directly: know-your-audience supplies who is in the room, Walk-Around decides what each of them needs to hear. It is distinct from `leet-grammars` (vocabulary and belonging) — Walk-Around governs the *form of the justification*, not the words.

It pairs with `concrete-before-abstract`, which is frequently the vehicle for the C answer — a human consequence lands as a story, not as a bullet. It feeds `crucible` and `peer-review`: both are review passes, and the Walk-Around gives a reviewer four specific things to look for rather than a general request to find problems. Its direct inverse is `_anti_golden-rule.md` — a talk built entirely in the speaker's own preferred register is the null case of this pattern.

## Related Reading
- Herrmann, N., & Herrmann-Nehdi, A. (2015). *The Whole Brain Business Book* (2nd ed.). McGraw-Hill. Ch. 8 — "Communicating Across Thinking Styles" contains the Walk-Around procedure and the doubled-revenue worked example; Ch. 13 — "Influencing, Getting Buy-In, and Connecting with Your Customers" contains the MIT/CMU re-registering story. The catalog imports the procedure and the quadrant vocabulary as a recognizable handle. It does not import the Whole Brain Model's physiological claims, the HBDI instrument, or the book's Ch. 8 section on gender-based communication differences, which rests on popular rather than empirical sources.
- Petty, R. E., & Cacioppo, J. T. — the Elaboration Likelihood Model and the need-for-cognition literature supply the defensible version of the premise this pattern needs: audiences differ in what evidence moves them, and argument quality persuades some listeners where peripheral cues persuade others. No brain-dominance claim is required to justify covering more than one register.
