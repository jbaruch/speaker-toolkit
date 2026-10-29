# Deck Editing

Content edits to an outline-backed deck first invoke `Skill(skill: "presentation-creator")` for the source change. Resume with regenerated artifacts; layout-only edits stay here.

## Iteration Loop

Free-form conversation. The author gives feedback in whatever format is natural.
Edits drive the real PowerPoint app — there is no open session to mutate. Two
mechanisms cover iteration: a global text replace via `run-deck-ops.sh`'s
`replaceStr`, and build-then-assemble — rebuild the affected slide as a
one-`SLIDE` fragment with `build-deck.sh`, then position it with
`run-deck-ops.sh`'s order string (see [deckops-spec.md](deckops-spec.md)).

### Slide-specific changes

Author says: "Slide 12 — make the title shorter"
→ global text replace (replaces every occurrence, so use distinctive text):
  `run-deck-ops.sh <deck> <out> "" "<unchanged order>" "Old long title=>Shorter"`

Author says: "Slide 5 — change to two columns"
  1. Build a one-`SLIDE` fragment on the two-column layout with `build-deck.sh`.
  2. Use `run-deck-ops.sh` to drop the old slide 5 and place the fragment in its
     position — express the FINAL slide order (see Structural changes below).

### Batch changes

Read `design_rules.slide_numbers` from the speaker profile. If "never", decline
requests to add slide numbers and explain it's a design rule.

### Content delivery

Author provides an image for a placeholder slide:
→ Rebuild that slide as a one-`SLIDE` fragment with an `IMAGE` op, then position
  it with `run-deck-ops.sh` (build-then-assemble).

### Structural changes (real PowerPoint via RunDeckOps)

Make ALL structural edits (delete / reorder / cross-deck import / global text
replace) by driving the real PowerPoint app, which serializes the file and
preserves backgrounds, fonts, masters, and Keynote-openability. python-pptx
editing strips each slide's per-slide background fill — on illustrated decks that
silently flattens full-bleed art to bare color. See `rules/deck-editing-rules.md`.

```bash
bash "{speaker_toolkit_root}/skills/presentation-creator/scripts/run-deck-ops.sh" <basePath> <outPath> <importSpec> <orderStr> <replaceStr>
```

`orderStr` is the FINAL slide sequence as space-separated `<alias>:<1-based #>`
tokens; alias `BASE` is `basePath`. Delete by OMITTING a slide; reorder by
listing tokens in the target order; import by adding an alias to `importSpec`.

```
# drop slide 3, and move slide 6 ahead of slide 4:
"BASE:1 BASE:2 BASE:6 BASE:4 BASE:5"
```

macOS + Microsoft PowerPoint only. Run
`"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/deckops-doctor.py" --vault-root "{vault_root}"`
first and act on its `status` rather than assuming a first run;
[deck-editing-setup.md](deck-editing-setup.md) covers enabling VBA macros, importing
`RunDeckOps.bas` into a `DeckOps.pptm` container, and granting Automation
consent. On EVERY build, the user must open `DeckOps.pptm` first and keep it open
for the whole sequence — each macro pass calls a macro in that running instance
(see Step 6 of the setup doc). The speaker-notes pass runs no macro.
The macro writes a COPY — the original is untouched; continue editing from the
OUTPUT deck.
