# Illustration Fix Triage and Quality Audit

## Problem/Feature Description

A speaker has generated 40 illustrations for a conference keynote using the retro military technical manual style. After reviewing them with a co-presenter, they have a list of fixes needed. Some images need content removed, some need content added, some are nearly perfect with minor issues, and one has a completely wrong composition.

The speaker also noticed that during a previous rush to fix images, some edit prompts were written hastily. They want a quality audit of the planned edits before executing them.

Given the fix request list and the original prompts, produce:
1. A triage plan categorizing each fix as regenerate, edit, or targeted fix — with the reasoning
2. Draft edit/fix commands with proper prompt engineering
3. A guardrail audit of the planned and existing prompts flagging quality anti-patterns

## Output Specification

Produce the following files:

1. **`triage-plan.md`** — For each fix request: the recommended approach (regenerate / edit / fix), the reasoning, and the draft command or prompt to use. Include safety suffixes and preservation instructions. For each command, specify the output file path and naming convention (how iterations should be saved to avoid losing previous versions).

2. **`prompt-audit.md`** — A guardrail audit of the edit prompts in the fix log below, flagging prompt quality anti-patterns: missing preservation instructions, missing safety suffixes, problematic prompt construction, and any other issues. Also note any approaches in the log that should have used a different technique (wrong tool for the job).

## Input Files

The following files are provided as inputs. Extract them before beginning.

=============== FILE: inputs/style-anchor.txt ===============
STYLE ANCHOR (FULL):
Retro U.S. Military WWII technical manual style. Pen-and-ink line art on aged parchment background with foxing and tea-staining. Blue-ink leader lines, decorative military document border ornaments, classification stamps, and technical manual header formatting. All people/robots/animals wear WWII uniforms with garrison caps and rank insignia. Render all callout labels in large bold font. FIG. numbering on each illustration.
=============== END OF FILE ===============

=============== FILE: inputs/fix-requests.md ===============
# Illustration Fix Requests

## Slide 12 — Remove the bottom-right label
The "SPECIMEN CLASSIFIED" label in the bottom-right corner overlaps with the border ornament. Need to erase it cleanly.
Current image: illustrations/slide-12.jpg (looks great otherwise)

## Slide 19 — Add a third soldier to the formation
The image shows two soldiers reviewing a document but the slide discusses a three-person review board. Need a third soldier added.
Current image: illustrations/slide-19.jpg

## Slide 25 — Road needs to be more prominent
The winding road in the background is too faint — it should be the dominant visual element. The soldiers in the foreground are fine.
Current image: illustrations/slide-25.jpg (90% correct, just the road visibility)

## Slide 33 — Completely wrong composition
The image shows a naval scene but this slide is about aerial reconnaissance. Need to regenerate entirely with the correct subject.
Current image: illustrations/slide-33.jpg

## Slide 40 — Remove the extra frame border
Gemini added a double picture-frame border that wasn't in the original. Need to remove just the outer frame while keeping the military document border ornaments.
Current image: illustrations/slide-40.jpg

## Slide 47 — Build steps look patchy
Someone tried to create progressive reveal builds for this slide by using Python PIL to paste parchment-colored rectangles over parts of the image. The texture doesn't match and it looks terrible. Need to redo the builds properly.
Current image: illustrations/slide-47.jpg, illustrations/builds/slide-47-build-*.jpg
=============== END OF FILE ===============

=============== FILE: inputs/previous-edit-log.md ===============
# Previous Edit Session — Quick Fixes (done in a rush)

These edits were applied in a previous session. Review them for quality issues.

## Edit 1 (slide 8):
Prompt: "Remove the tank from the background"

## Edit 2 (slide 15):
Prompt: "Military manual style. Pen and ink. Show a supply chain diagram."

## Edit 3 (slide 22):
Prompt: "Erase the watermark text. DO NOT add any new elements. Let background continue naturally -- no parchment patch. Keep the soldiers. Keep the border ornaments. Keep the classification stamp."

## Edit 4 (slide 29):
Prompt: "Change the hat on the left figure from a beret to a garrison cap"

## Edit 5 (slide 35):
Prompt: "Make the text on the sign bigger"
=============== END OF FILE ===============
