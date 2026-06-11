# Idea-Sourcing Wizard — Shared Shape

A reusable interaction shape for visual-design decisions: ask where the ideas
come from *before* proposing, present the options, render or describe them, and
let the speaker pick. Two decision sites use it — the engine/theme decision in
`phase2-architecture.md` and the illustration-style strategy in
[../../illustrations/references/strategy.md](../../illustrations/references/strategy.md).
This file documents the generic flow once; each site binds its own sources.

The shape generalizes the Pattern-Strategy 4-tier menu (`phase2-architecture.md`
Decision #11) — that menu is the origin; this is the same idea applied to other
design choices.

## The Flow

1. **Source menu first.** Present an `AskUserQuestion` **multi-select** of idea
   sources, even when the speaker has history. The checked sources decide which
   buckets the proposals span.
2. **Always-on grounding.** The talk's own concepts, audience, and venue ground
   every proposal — state them above the menu, never as a checkbox.
3. **Proposals span the checked sources.** Synthesize 3-4 options drawn across
   the checked sources for variety, each labeled with its source.
4. **Pick.** A single-select (or a rendered grid, where the decision is visual)
   chooses the final option. The speaker picks; the agent recommends.

## The Source Vocabulary

Each site maps these to its own data. The generic buckets:

- **Your Usual** — the speaker's most-common choice for this kind of artifact.
- **Mode / Series Match** — what this talk's mode or series has used before.
- **New To You** — a fit-relevant option the speaker hasn't used.
- **Wild Card** — a deliberately provocative option, NOT filtered for fit.
  Provocation, not prescription.
- **What's Trending** — a `WebSearch`-sourced current option; no vault data.
- **I'll Drive** — the speaker supplies direction + reference examples.

Plus `AskUserQuestion`'s built-in "enter your own".

## Quick-Default Fast Path

Offer a menu entry that resolves a sensible default immediately and shows it,
deferring deeper refinement — the "ship something now, ask later" path. It is the
sanctioned way to go fast: it still produces a concrete, shown result and records
its provenance; it never silently commits an unshown choice. For the illustration
site this means rendering one default style+model and showing it (it flows through
the same render-before-bake gate); for the engine site it means resolving the
default engine by precedence and recording `engine_source: "quick-default"`.

## Summary-Only / No-Profile Degradation

When the profile (or the relevant history field) is absent, the data-backed
sources — Your Usual, Mode/Series Match — have nothing to offer. Present them as
"no history yet" or omit them; the fit-based and external sources (New To You,
Wild Card, What's Trending, I'll Drive) still work from the talk alone. The
quick-default falls back to a hard-coded sensible default. The wizard degrades;
any downstream enforcement (e.g. the illustration render-before-bake gate) does
not.

## One Question Per Turn

Per the `interaction-rules` steering rule, ask each question individually and wait
for the answer before the next. The source menu is one question; the final pick is
another.
