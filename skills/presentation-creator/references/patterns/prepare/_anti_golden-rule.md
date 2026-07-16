---
id: golden-rule
name: The Golden Rule
type: antipattern
part: prepare
phase_relevance:
  - guardrails
vault_dimensions: [4, 9, 14]
detection_signals:
  - "every claim defended in the speaker's single preferred register"
  - "talk mirrors the speaker's own thinking style rather than the room's spread"
  - "human-consequence or mechanism questions never answered because the speaker never asks them"
  - "speaker's stated reason for believing the claim is the only reason offered"
related_patterns: [walk-around, know-your-audience, leet-grammars, crucible]
inverse_of: [walk-around]
difficulty: intermediate
---

# The Golden Rule

## Summary
Building the talk you would want to receive. The speaker defends every claim in the register they personally find convincing, mistakes their own satisfaction for the room's, and delivers a talk that lands hard with the fraction of the audience who thinks like them and glances off everyone else.

## The Antipattern in Detail
Do unto others as you would have them do unto you is excellent ethics and poor audience analysis. Applied to a talk it produces a speaker who gives the audience what *they* would want in that seat — which is a reliable guide only if the audience is a room full of the speaker.

The mechanism is invisible from the inside, which is what makes this worth naming. A speaker does not choose their default register; it is simply the kind of reason that feels like a reason to them. The benchmark-minded speaker builds a talk of benchmarks and finds it airtight, because for them a benchmark *is* airtight. They are not neglecting the human-consequence question out of contempt. They are neglecting it because it never occurred to them to ask, and the talk feels complete without it. Every re-read confirms the feeling: the talk answers all the questions the author has.

Herrmann's counter is the Platinum Rule — treat others as *they* want to be treated — and the gap between the two rules is the whole antipattern. The Golden Rule speaker projects; the Platinum Rule speaker models.

The tell in the wild is uniformity of defense. Watch a talk and ask what *kind* of thing gets offered every time a claim needs support:

- **All numbers.** Every point lands on a benchmark, a chart, a p99. The room learns the thing is fast and never learns what it is like to operate, who it disrupts, or why it matters next year.
- **All story.** Every point lands on an anecdote. The room is charmed and cannot evaluate the claim, because no one has been given a number, and the engineers in row four have quietly filed the whole talk under marketing.
- **All architecture.** Every point lands on a diagram of how it fits together. Nobody has been told what it costs or who has to migrate.
- **All process.** Every point lands on a sequence of steps. The room knows exactly how to do a thing nobody has argued is worth doing.

Each version has a constituency that loves it, which is the trap: the Golden Rule talk gets warm feedback from the subset of the room that shares the speaker's register, and that feedback reads as success. This is the same measurement failure `red-yellow-green.md` describes — the people who fill in the green card are disproportionately the ones you were already speaking to.

**The severity scales with the stakes.** For a talk meant to be admired, one register is a stylistic limitation. For a talk meant to get something *adopted*, it is usually fatal, and it fails in a predictable direction: technical speakers cut the mechanism and human-consequence answers first, and those are precisely the two an organization needs before it will adopt anything. The idea does not die in the room. It dies three weeks later, when someone asks who has to retrain the team and nobody has an answer.

## How It Manifests
- **The confident claim.** The point the speaker considers self-evident gets the thinnest support, in exactly one register. Confidence marks the spot where the default went unexamined.
- **Projected Q&A prep.** The speaker rehearses answers to the questions *they* would ask, then gets blindsided by the question the room actually asks — usually the C question, about who this hurts.
- **The mirrored reviewer.** Feedback sought from a colleague with the same background as the speaker, who finds the talk complete. Two people sharing a blind spot confirm each other.
- **"They're all engineers."** Homogeneity asserted from job titles and never verified — see `walk-around.md`'s coverage-or-match discussion. A room of engineers still contains the person who wants to know who gets paged.
- **The one-register close.** The summary reprises the same kind of evidence the talk ran on throughout, since it never occurred to the speaker there was another kind.

## How to Avoid It
Run `walk-around.md` on the load-bearing claims — it is the direct antidote, and it is mechanical precisely so it does not depend on the judgment this antipattern has already compromised.

Start with the claim you are surest of.

Get a reviewer who does *not* share your background, and ask them for the question the talk fails to answer rather than for their opinion of it. A reviewer who finds nothing missing is either a confirmation of the work or a mirror; the way to tell is whether they think in your register.

Read the room's spread before assuming it is homogeneous. Matching a homogeneous room is legitimate and often correct — but that decision has to be made from evidence, not from the comfort of already being fluent in the register you were going to use anyway.

## Detection Heuristics
The vault detects this by register uniformity across the talk's defended claims:
- Every load-bearing claim supported by the same *kind* of evidence — all quantitative, all anecdotal, all structural, all procedural
- Entire archetypes absent: no numbers anywhere, or no human consequence anywhere, across a talk long enough that the absence is a choice
- Q&A clustering: multiple audience questions attacking the same missing register is the strongest available signal, since the room is telling the speaker directly which question the talk skipped
- Speaker language that projects rather than models — "obviously the interesting part here is…", "the thing you really care about is…" — where the stated interest matches the speaker's own register
- Counter-signal: a homogeneous room deliberately matched, with evidence the speaker considered the alternatives. That is `walk-around`'s match mode, not this antipattern. The distinguishing question is whether the single register was *chosen* or *defaulted into*

Do not flag a short talk for thin coverage — a lightning talk has room for one register and choosing it is correct. The flag needs a talk long enough that the missing archetypes are an omission rather than a budget.

## Scoring Criteria
- Strong signal (2 pts — antipattern present): Every load-bearing claim in a full-length talk defended in a single register; at least one archetype wholly absent; ideally corroborated by Q&A clustering on the gap or by projecting language
- Moderate signal (1 pt): Two registers present but heavily lopsided, with a conspicuous archetype missing on the talk's central claim
- Absent (0 pts): Claims defended across multiple registers, or a homogeneous room matched with evident deliberation

## Relationship to Vault Dimensions
Relates to Dimension 4 (Audience Interaction) — the antipattern is a failure of audience modeling, with the speaker's own preferences substituted for the room's. Relates to Dimension 9 (Persuasion Techniques), since it determines what the talk offers as proof and to whom that proof is legible. Relates to Dimension 14 (Areas for Improvement), where it belongs with `_anti_nodding-room.md` in the category of failures that draw good feedback: both are talks a subset of the room genuinely enjoys, which is exactly why neither gets corrected.

## Combinatorics
The direct inverse is `walk-around` — this antipattern is its null case, and a single walked-around claim is the minimum refutation.

It is adjacent to but distinct from `_anti_tower-of-babble.md` (incomprehensible jargon — the Golden Rule talk can be perfectly comprehensible and still answer only one of four questions) and from `_anti_flyover.md` (contempt for the audience — the Golden Rule speaker respects the room and is generous toward it, and that is the point: this failure requires no bad intent). It shares its feedback-blindness with `_anti_nodding-room.md`: both antipatterns are rewarded by the instruments speakers actually have.

`know-your-audience` is the upstream dependency — the spread read that would have exposed the projection. `crucible` fixes this only if the feedback it consumes comes from outside the speaker's register; fed mirrored feedback, it optimizes the talk deeper into the antipattern.

## Related Reading
- Herrmann, N., & Herrmann-Nehdi, A. (2015). *The Whole Brain Business Book* (2nd ed.). McGraw-Hill. Ch. 13 — the Golden Rule / Platinum Rule contrast (attributed to Tony Alessandra) and the pharmaceutical-rep story, in which seven years of clinical data failed on a physician who turned out to be moved by possibility rather than evidence. Ch. 8 — the Walter/John dialogue, a sustained worked example of two competent people failing to communicate while each defends in their own register. The catalog imports the projection failure, not the book's underlying model — see `walk-around.md` Related Reading.
