---
id: guess-first
name: Guess First
type: pattern
part: build
phase_relevance:
  - content
  - slides
vault_dimensions: [2, 4, 11]
detection_signals:
  - "audience asked to commit an answer before the reveal"
  - "prediction solicited ahead of a demo, result, or number"
  - "speaker withholds the answer through a deliberate pause for attempt"
  - "reveal is framed against what the audience just predicted"
related_patterns: [concrete-before-abstract, retrieval-beat, live-demo, progressive-reveal, foreshadowing, inoculation]
inverse_of: []
difficulty: intermediate
---

# Guess First

## Summary
Make the audience *commit an answer* — a prediction, a guess, a number, a show of hands — **before** you reveal the result. The attempt, including a wrong attempt, primes the reveal to land harder and stay longer than the same reveal delivered cold.

## The Pattern in Detail
The instinct of every expert speaker is to deliver the answer cleanly. You know the result; showing it is fast, and showing it well feels like generosity. Guess First deliberately spends time buying something the clean reveal cannot: the audience's own failed attempt.

The mechanism is the **generation effect**, one of the better-replicated findings in the learning literature (Slamecka & Graf, 1978, and a large subsequent literature). People remember material they *generated* — even partially, even incorrectly — better than material they merely read or heard. The unsuccessful attempt is not wasted effort that the correct answer then has to overwrite. The attempt is what makes the correct answer stick, because it creates the question in the listener's mind that the answer then resolves. An answer to a question you never asked yourself is just a fact passing by.

The move is small and structural. Before the benchmark result, ask the room to guess the number. Before running the demo, ask what they think will happen when you hit enter. Before the architecture reveal, ask how they would solve it. Before the plot twist in the incident story, ask what they think broke. The commitment can be a show of hands, a shouted answer, a poll, or — most often and most cheaply — a genuine three-second pause after a genuine question, during which every person in the room silently commits an answer whether they intended to or not. The public part is optional. The commitment is not.

**The wrong answer is the asset.** Guess First is at its most powerful when the room confidently guesses wrong, because the gap between the predicted and actual result is exactly the thing worth remembering. A room that predicts the query takes 200ms and watches it take 40 seconds has learned something that no amount of "queries can be slow" would have taught. This is why the pattern pairs naturally with counterintuitive material: the more surprising the true answer, the more the prediction earns. Conversely, a question whose answer the room will obviously get right buys nothing — there is no gap to exploit — and costs the same time.

The pattern's central risk is the **dead pause**: asking a question the room cannot attempt. If nobody has the raw material to form a guess, the silence is not productive struggle, it is confusion, and the speaker pays in energy and pace for nothing. The question must be *attemptable* — the audience needs enough to reason from, even if reasoning from it leads them astray. "How many milliseconds?" is attemptable. "What's the name of the internal service that caused it?" is not; it is a trivia question, and trivia questions punish the room for not being you.

Guess First is bounded by time. Each instance costs somewhere between three seconds and a minute, and the honest accounting is that a talk can afford a handful, not a dozen. Spend them where the reveal is worth the setup: the two or three moments that carry the thesis.

### Boundary With Concrete Before Abstract
These two patterns are neighbors and are frequently confused, so the distinction is worth stating precisely.

`concrete-before-abstract` withholds the **label**. The audience is *shown* a tangible instance and lets an intuition form, then the abstraction is named. The audience's role is receptive: they watch the car anecdote unfold, and the term "exciter" arrives as a satisfying compression of what they just felt. Nothing is demanded of them.

Guess First withholds the **answer** and demands a swing at it. The audience's role is active: they must produce something — a number, a prediction, a hypothesis — and be publicly or privately on record before the reveal. Concrete Before Abstract asks the audience to *notice*; Guess First asks the audience to *commit*.

They compose cleanly and often should. The strongest version runs the concrete instance, stops before the payoff to make the room predict where it lands, reveals, and only then names the abstraction. Instance → attempt → reveal → label. Each move buys a different thing, and the sequence buys all three.

## When to Use / When to Avoid
Use Guess First when the true answer is counterintuitive, when the audience holds a common misconception the talk exists to dislodge, ahead of any demo whose output is surprising, and at the two or three structural moments carrying the thesis. It is the natural default for demo-driven and data-heavy talks, where a predicted-versus-actual gap is available for free.

Use it especially where the talk's job is *unlearning*. A room that has never committed to the wrong model has no reason to abandon it; a room that just committed, publicly, and watched the commitment fail, has a reason.

Avoid Guess First when the answer is guessable — a correct prediction is a spent minute with no gap to trade on. Avoid it when the question is trivia rather than reasoning. Avoid stacking it: a talk that demands a prediction every four minutes turns into a pop quiz, the room learns that raising a hand is a tax, and participation collapses (see `_anti_negative-ignorance.md` for the adjacent failure — questions that punish people for what they do not know). Avoid it with hostile or high-status-anxiety rooms, where a public wrong guess costs the guesser more than it costs you; there, use the silent-pause form, which extracts the commitment without the exposure.

The honest caveat: the generation-effect literature largely studies learners across sessions, not audiences in a single 45-minute room. A conference talk is not a semester, and no one should promise that one prediction produces durable recall a month later. What the pattern reliably buys in the room is attention and a sharper reveal; durability is what `spaced-followup` is for. Claim the first; do not oversell the second.

## Detection Heuristics
The vault should look for the audience being put on the hook before a reveal:
- Interrogatives aimed at the room that precede a result — "what do you think happens when…", "how long do you think this took…", "hands up if you think…", "before I run this — guesses?"
- A pause or audience-noise gap in the transcript between the question and the reveal, rather than the speaker answering their own question in the next breath
- Reveal language that references the prediction — "and that's what almost everyone guesses", "you're all wrong, and so was I", "half the room said 200 milliseconds"
- Slide-side: a slide holding a question with no answer on it, followed by a separate answer slide — the deck is built to withhold
- Counter-signal: rhetorical questions the speaker answers immediately. "What happens when you do this? Well, it crashes." That is a rhetorical flourish, not a generation move, and it should not score. The distinguishing test is whether the room was given room to answer.

## Scoring Criteria
- Strong signal (2 pts): Multiple genuine prediction moments where the room commits before a reveal; at least one where the predicted answer and the true answer visibly diverge and the speaker exploits the gap; questions are attemptable and land at structurally important moments
- Moderate signal (1 pt): The speaker asks anticipatory questions but does not leave real room to answer, or the guesses are too easy to create a gap, or a single instance appears in an otherwise tell-only talk
- Absent (0 pts): Every result is delivered cold; questions to the room are rhetorical and self-answered; the audience is never on record before a reveal

## Relationship to Vault Dimensions
Relates to Dimension 2 (Narrative Structure) as a sequencing move — it reorders the beats of a reveal. Relates to Dimension 4 (Audience Interaction), since the commitment is usually solicited from the room. Relates to Dimension 11 (Technical Content Delivery), where its highest-value application lives: predicting demo output, benchmark numbers, and failure modes.

## Combinatorics
Guess First composes with `concrete-before-abstract` in the sequence described above (instance → attempt → reveal → label), and the two together are close to a complete inductive teaching engine. It pairs tightly with `live-demo` — "what will happen when I hit enter" is the single cheapest and highest-yield application of this pattern in a technical talk, and it converts a demo from a thing the audience watches into a thing the audience bet on. It composes with `retrieval-beat`: generation asks for an answer the audience has never been given, retrieval asks for one they were given earlier, and a talk can run both.

It shares machinery with `progressive-reveal` but differs in who is working: progressive-reveal builds a picture in front of a watching audience, while Guess First stops and makes the audience draw the next line themselves. A progressive-reveal that pauses to ask "what goes here?" has become a Guess First. It reinforces `foreshadowing` (a prediction solicited early can be paid off much later, and the audience will remember they were wrong) and `inoculation` (asking the room to voice the objection before you answer it is a Guess First applied to counterarguments).

## Related Reading
- Brown, P. C., Roediger, H. L., III, & McDaniel, M. A. (2014). *Make It Stick: The Science of Successful Learning.* Ch. 4 — "Embrace Difficulties" covers generation and the Bjorks' "desirable difficulties" framework: the argument that effortful, error-prone retrieval produces more durable learning than fluent, frictionless exposure, and that the errors themselves are productive rather than damaging. Belknap Press / Harvard University Press.
- Slamecka, N. J., & Graf, P. (1978). "The generation effect: Delineation of a phenomenon." *Journal of Experimental Psychology: Human Learning and Memory*, 4(6) — the founding demonstration.
