---
id: concrete-before-abstract
name: Concrete Before Abstract
type: pattern
part: build
phase_relevance:
  - content
vault_dimensions: [11, 9, 2]
detection_signals:
  - "a tangible example, object, story, or live demo precedes the named concept it illustrates"
  - "the framework/term is introduced only after the audience has experienced an instance of it"
  - "the abstract label arrives as a summary of concrete material already shown, not as a preamble"
  - "inductive sequencing across a section: instances -> pattern -> name, rather than definition -> examples"
related_patterns: [live-demo, master-story, vacation-photos, mentor, the-big-why, sparkline]
inverse_of: []
difficulty: intermediate
---

# Concrete Before Abstract

## Summary
Make the audience *experience* a concept through a tangible instance — an everyday object, a personal story, a live demo, a piece of data — **before** naming or defining the abstraction it illustrates. The label arrives as the payoff of concrete material the audience has already felt, not as a preamble they have to take on faith.

## The Pattern in Detail
Most speakers default to the deductive order they learned in school: state the definition, then give examples. Concrete Before Abstract inverts it. The speaker leads with the instance — *"this happens to be the car I drive; when I bought it I never told my friends about the brakes…"* — lets the audience build an intuition from the lived detail, and only *then* names the framework that organizes it (*"so it turns out every feature falls into three categories… basic expectations, satisfiers, and exciters"*). By the time the abstraction is named, the audience has already half-derived it; the name lands as a satisfying compression of something they now understand, rather than a piece of jargon they must hold in suspension until an example rescues it.

A definition delivered cold ("an exciter is a delighter whose absence is not penalized but whose presence is disproportionately rewarded") forces the audience to attach a symbol to no referent. The same idea delivered concrete-first ("the car refused to lock with my keys still inside it — I didn't know I needed that, and now I won't buy a car without it") supplies the referent first. The label then lands as recognition, not memorization. This is the mechanism behind the Heath brothers' "Concrete" principle in *Made to Stick* (the SUCCESs framework) and inductive teaching generally.

Concrete Before Abstract is a *sequencing* pattern, not a content pattern — it governs the order in which an existing concrete element and its abstraction are presented. It composes with the vehicles that supply the concrete element: a `live-demo` that proves a claim before the claim is generalized; a `master-story` whose first telling lands as pure narrative before its thesis is extracted; a `vacation-photos` image that evokes the idea while the speaker narrates toward the name. The distinguishing move is always the *withheld label* — the speaker resists the urge to announce the concept up front and trusts the instance to carry the audience to the threshold of it.

A strong application chains the move: each section opens on a fresh concrete anchor (cars → a Japanese super-fan → a toothbrush redesign → a milkshake) and only names its principle (exciters → otaku/early adopters → design-as-research → jobs-to-be-done) once the anchor has done its work. The cumulative effect is that the audience experiences a *series of small derivations* rather than a lecture of definitions. The audience feels it arrived at each idea partly on its own — more memorable, and more flattering.

The pattern fails in two directions. Withhold the label too long and the audience feels adrift, unsure why they are hearing a car anecdote ("get to the point"). Announce the label too early — even once — and the section collapses back into definition-first, the instance demoted to mere illustration. The skill is in the timing: the concrete element should run just long enough to build intuition and just short enough that the name feels *earned, not delayed*.

## When to Use / When to Avoid
Use Concrete Before Abstract whenever the audience is unlikely to already hold the abstraction, or holds it as inert jargon that needs re-grounding — teaching audiences, mixed-seniority rooms, cross-domain talks, and any frameworks-heavy content. It is especially powerful for talks that introduce multiple named concepts in sequence, where each can get its own concrete anchor. It is the natural default for the object-anchored and demo-driven modes.

Avoid it when the audience already shares the abstraction fluently and wants to get to the nuance fast (expert-to-expert talks, where leading with a basic example reads as condescension), when time is severely constrained and the concrete setup would crowd out the payload, or when no honest concrete instance exists for the concept (a manufactured example is worse than an honest definition). Note the failure mode: stacking concrete anchors with the labels *never* arriving tips into a related weakness — the audience enjoys the stories but cannot name what they learned.

## Detection Heuristics
The vault should look for inductive ordering at the section level, not the talk level:
- A tangible anchor (object, anecdote, demo, datum) is introduced and developed, and the governing term or framework is named *after* it, often with an explicit hinge — "so it turns out…", "what's going on here is…", "there's actually a name for this…", "people have studied this…".
- The abstraction, when it arrives, summarizes material the audience has already heard rather than previewing material to come.
- The move repeats across multiple sections (each concept gets its own concrete-first treatment), which distinguishes a deliberate signature from a one-off illustration.
- Counter-signal: sections that open with a definition or a named framework and *then* descend into examples are the deductive (definition-first) order — the absence of the pattern.

In transcript-only analysis the hinge phrases are the most reliable marker. The concrete-then-named ordering survives auto-captioning even when slide order does not.

## Scoring Criteria
- Strong signal (2 pts): The talk repeatedly grounds concepts in a tangible instance before naming them; multiple sections show the instance → intuition → named-label ordering with clean hinge moments; labels read as earned compressions of concrete material already delivered.
- Moderate signal (1 pt): The pattern appears for the talk's central concept (or a few sections) but is mixed with definition-first ordering elsewhere; OR the concrete anchors are present but the label is announced slightly too early to fully earn the payoff.
- Absent (0 pts): Concepts are introduced definition-first with examples used only as after-the-fact illustration; no inductive instance → name sequencing; or the talk is purely concrete with no abstractions named at all.

## Relationship to Vault Dimensions
Relates most directly to Dimension 11 (Technical Content Delivery) — concrete-before-abstract is a core complexity-handling and simplification strategy, the sequencing discipline behind "make abstract claims concrete." Relates to Dimension 9 (Persuasion Techniques) as a grounding move: leading with a felt instance lets the audience supply its own evidence before the generalization is named. Relates to Dimension 2 (Narrative Structure) as a structural choice about ordering (inductive vs. deductive) that operates within sections and shapes the rhythm of a frameworks-heavy talk.

## Combinatorics
Concrete Before Abstract is the sequencing layer on top of several content vehicles. It composes with `live-demo` (show the system working, then name the principle the demo proved — "transforms abstract claims into concrete proof"), with `master-story` (the master story's first telling lands as narrative before its thesis is extracted, and each recursive return re-applies the same concrete anchor to a new abstraction), with `vacation-photos` (a full-bleed image carries the concept while the speaker narrates toward its name), and with `mentor` / `the-big-why` (the concrete anchor often doubles as the answer to "why should the audience care" before the formal framing arrives). It frequently chains with `triad` (three concrete anchors, three named categories). It is mutually reinforcing with the speaker's broader anti-jargon, audience-as-derivation stance.

## Related Reading
- Heath, C., & Heath, D. (2007). *Made to Stick: Why Some Ideas Survive and Others Die.* Random House. The "Concrete" principle of the SUCCESs framework — abstract ideas are made memorable by grounding them in sensory, tangible specifics; the book argues that the "curse of knowledge" pushes experts toward abstraction and that concreteness is the antidote.
- Vault-derived pattern: formalized from the speaker corpus (esp. the object-anchored product talk, where every framework — Kano exciters, otaku, jobs-to-be-done, SUCCESs — is introduced through a physical object or personal anecdote *before* it is named), where the instance → name ordering recurs across effectively every talk and mode. Not present as a discrete pattern in the canonical Ford/McCullough/Schutta, Reynolds, or Duarte sources, though it underlies several of their patterns.
