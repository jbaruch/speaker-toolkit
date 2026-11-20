# Draft and Review Toolkit Text

## Start with the speaker and the material

Read approved examples in the same medium when available. Use delivered remarks
for notes, approved decks for headlines, and approved submissions for CFPs. Pick
a few passages that show how the speaker makes a claim, tells a story, or lands
a joke. Match each speaker to their own examples in a multi-speaker talk. Use the
vault’s confirmed intent to interpret the examples. When examples are missing,
write in a plain register and leave voice calibration unresolved.

Identify the reader and what the artifact needs to convey. Write from the talk’s
claim, examples, and sequence. Preserve author-supplied wording, approved copy,
quoted material, technical meaning, and the format each consumer expects.

## Edit for the medium

- **Narrative and outline.** State what happens and why it changes the argument.
  Make each chapter beat follow from the preceding one. Replace planning shorthand
  and generic transitions with the claim, event, or example that earns the turn.
- **Speaker notes, rehearsal lines, and demos.** Read the lines aloud in sequence.
  Use phrases the assigned speaker would say. Give a demo line something concrete
  to point at. Keep stage directions and build cues in their own fields.
- **Slides and short hooks.** Read headlines in sequence and against their visuals.
  Put a claim, instruction, or punchline on screen when it has a job there. A pun
  should make the point easier to remember. Use the slide-copy examples in
  [phase3-content.md](phase3-content.md#slide-copy).
- **Build instructions, analyses, and reviews.** Name the object, action, and
  relevant evidence. Say which slide, line, or behavior needs attention. Use plain
  production language. Keep source quotes, measured data, and validation results intact.
- **CFPs, shownotes, and other public prose.** Ground the promise in what the talk
  actually delivers. A proposal tells the committee what the audience will learn.
  Shownotes acquaint readers with the actual argument and examples. A downloadable
  skill explains enough of the talk to answer questions about it.

Before presenting a draft or asking for approval, cut generic openings, repeated
claims, and transitions that add no information. Check the text beside the source
and revise the draft where it loses the speaker’s point or specificity. Fix authored
fields in the owning artifact. Regenerate and read the derived outputs as a reader
would, including the partial narrative and, when present, the full narrative,
rehearsal script, build sheet, and rhetorical review. If the boilerplate comes
from a renderer, flag it in the draft review and leave the generated file
read-only. Preserve fixed labels and machine-readable syntax.

For a demo about skill discovery, the narrative might say “Give the agent the
same request twice. Change only the skill’s description between runs.” The
speaker note can point at the cause. “See that line? That’s the only thing I
changed.” The build sheet can tell the operator what to show. “Put the
descriptions side by side. Highlight the trigger phrase after the second run.”

## Use the scoped `blog-writer` review

For a new or substantively revised draft, batch its changed prose in reading
order with enough neighboring text to judge transitions. When the installed skill
supports scoped non-blog review, invoke
`Skill(skill: "blog-writer")` for a **scoped, review-only humanization pass on
non-blog text**. Supply the reader, purpose, field or slide locations, approved
wording, and relevant voice examples. Ask for the completed manual catalog review
and sweep, with each finding’s location, phrase, suggested edit, and disposition.
For the presentation guardrail, also ask for severity (`high` or `medium`) on
confirmed findings so they can be counted. Keep the scope to the supplied prose.
Leave identifiers, syntax, raw quotes, transcripts, numerical results, and visual
prompts out of the scan.

Review suggestions in context and apply warranted edits to the authoring draft
before approval. Keep intentional phrasing when a source passage or explicit
direction supports it in this context. Check the revised passages for meaning,
voice, and continuity. Run scoped review again on passages you substantially
rewrite. Leave approval and persistence with the calling skill.

If the scoped review is unavailable, fails, or requests a full blog workflow,
continue the toolkit’s editorial pass and report the reason the scan was skipped.
For a missing or older install, point to `tessl install jbaruch/blog-writer`.
Keep the anti-pattern catalog and sweep in their owning skill.
