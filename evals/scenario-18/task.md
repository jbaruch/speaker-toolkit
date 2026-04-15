# Speaker Notes Injection with Keynote Compatibility

## Problem/Feature Description

A speaker has finished building a four-slide .pptx deck with the slide content they want, and has written out speaker notes for the three content slides (the opening title slide has no notes). They now need to inject the speaker notes into the deck before presenting.

The speaker frequently presents from Keynote on macOS (their laptop lives on the conference podium and projects fine from Keynote, but PowerPoint requires a license transfer they don't have). Previously, when they ran a custom script that just called `slide.notes_slide.notes_text_frame.text = "..."` with python-pptx, the resulting `.pptx` would open fine in PowerPoint but Keynote would reject it with "The file format is invalid." They lost a morning at a conference because of this. For this talk, they need a workflow that produces a `.pptx` that opens cleanly in **both** PowerPoint and Keynote.

Using the presentation-creator skill, inject the notes from `notes.json` into `base-deck.pptx` and produce a deck that satisfies the OOXML spec requirements that strict parsers (Keynote) enforce.

## Output Specification

Produce the following files:

1. **`deck-with-notes.pptx`** — The resulting deck, with speaker notes injected on slides 1, 2, and 3 (0-indexed), and no notes on slide 0.
2. **`verification-report.md`** — A brief report describing:
   - Which script/command was used to inject the notes
   - What checks were performed to confirm Keynote compatibility
   - The findings of those checks (pass/fail per check, with the actual values observed inside the `.pptx`)

## Input Files

Download the base deck and notes map from the project repository before beginning:

```bash
BASE="https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/scenario-18"
mkdir -p inputs
curl -L -o inputs/base-deck.pptx "$BASE/base-deck.pptx"
```

=============== FILE: inputs/notes.json ===============
{
  "0": "",
  "1": "Setup: describe the problem the audience is living with today. Keep this short — one minute max.",
  "2": "Development: walk through the diagnosis. This is the meat of the talk, plan for about eight minutes here.",
  "3": "Payoff: three-point close and CTA. End on time."
}
=============== END OF FILE ===============

The base deck is a minimal four-slide `.pptx` built with python-pptx. It has no speaker notes yet and no `notesMaster` artifacts — you can confirm this by unzipping it and inspecting `ppt/presentation.xml` and `ppt/_rels/presentation.xml.rels`.

## Notes on Verification

The specific OOXML contract that Keynote enforces (and PowerPoint does not) is: when a presentation has a `notesMaster` relationship declared in `ppt/_rels/presentation.xml.rels`, `ppt/presentation.xml` MUST contain a `<p:notesMasterIdLst>` element whose child `<p:notesMasterId r:id="..."/>` references that relationship's ID. Your verification should confirm this contract holds in the output.
