# Phase 1: Intent Distillation — Detail

### The Art of Asking

Don't dump all questions at once. Use `AskUserQuestion` for structured choices when
the vault provides a finite set of options, and conversational questions when the
answer is open-ended.

**Batch questions logically:**
1. First batch: Purpose & thesis (the "what" and "why")
2. Second batch: Audience & venue specifics (the "who" and "where")
3. Third batch: Constraints & preferences (the "how" and "how not")

**Use the vault to inform questions.** If the topic overlaps with existing talks in
the vault, reference them: "This overlaps with your [talk name] territory. Should
we build on that argument or take a different angle?"

### Co-Presented Talks

If the spec has a co-presenter:
- Identify who owns which expertise domain
- Determine the role split: provocateur/depth, alternating sections, or parallel tracks
- Clarify whose deck/template to use (default: the vault speaker's template)
- Determine how handoffs work (verbal cue, slide type change, both)
- Use `[SPEAKER A]:` / `[SPEAKER B]:` prefixes in all speaker notes throughout the outline

### Shownotes Slug Generation

The slug is NOT free-form — read `shownotes_slug_convention` from the speaker
profile config. Apply the convention to this talk's details. Example convention:

```
Convention: {YYYY-MM-DD}-{conference-slug}-{talk-short-name}
Input:      2026-04-16, DevNexus, "Robocoders: Judgment Day"
Result:     2026-04-16-devnexus-robocoders-judgment-day
```

Rules:
- Derive the slug mechanically from the convention + talk metadata (date,
  conference, title). NEVER invent or freestyle a slug.
- Kebab-case, lowercase, no special characters.
- Present the generated slug to the author for confirmation before finalizing
  the spec. The author may want to abbreviate or adjust.
- If `shownotes_slug_convention` is not set in the profile, ask the author
  for their convention and save it (same as any missing config field).

The confirmed slug goes into the Presentation Spec as `Shownotes slug:` and is
persisted in `presentation-spec.md`. All downstream uses (Phase 6 shownotes URL,
QR code `--talk-slug`, directory name) must use this exact slug.

### Spec Validation

Before presenting the spec, cross-check:
- Does the thesis pass the "one sentence" test?
- Does the time slot match the content ambition?
- Is the mode selection consistent with the audience?
- Are there contradictions? (e.g., "zero profanity" + "heavy meme density" — flag it)
- If co-presented: is the role split clear? Does each presenter have enough airtime?

### When Adapting Existing Talks

Pre-fill the spec from the vault's analysis of the original talk:
1. Read the original talk's entry in the tracking database
2. Read its analysis file from `{vault_root}/analyses/`
3. Pre-populate: mode, opening type, narrative arc, humor register, closing pattern
4. Present to author: "Here's the original spec. What changes for the new venue?"
