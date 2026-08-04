# Clarification Handoff by Delivery Recency

This is the complete normative Step 9 contract for `vault-ingress`. Compute
candidate topics first, then apply the exact recency bucket and interaction rule.

If no talks were newly processed in this run, finish here without further action.

Otherwise, scan the newly-processed talks for delivery date and bucket each by how
long ago it was delivered (`today − date`). The handoff strength is tiered by recency —
clarification quality decays fast, so the freshest talks get an active handoff, not a
footnote. For every bucket, first compute that talk's **candidate clarification topics**:
- Each per-talk `areas_for_improvement` entry.
- Any `pattern_observations` the subagent flagged as **unverifiable from transcript
  alone** (low confidence, heavy reliance on visual cues, non-English dialogue without
  captions).

**≤7 days (same-week) — hand off inline, don't just recommend.** This is the
freshest-possible clarification window: memory of the delivery is sharpest right after
the talk, and verbal beats that didn't appear in auto-captions (bilingual jokes rendered
in a non-primary language, improvised asides, fly-bys that weren't in the deck) are only
recoverable now. Do NOT bury this as a closing recommendation. Use `AskUserQuestion` to
offer an immediate session through `Skill(skill: "vault-clarification")`, showing the
candidate topics you computed so the speaker sees exactly what the session would cover.
If they accept, invoke that typed call immediately, carrying those candidate topics as
the session's seed agenda. If they decline, note it and finish.

**7–30 days — recommend the full session.** Recommend running
`Skill(skill: "vault-clarification")`, listing the candidate topics, but note that some
verbatim details may already be lost. Do not auto-invoke.

**30+ days — recommend the compressed session.** Memory has decayed and detailed recall
is unreliable; recommend the compressed clarification instead of the full one. Do not
auto-invoke.
