# Adding Progressive Reveals to an Illustrated Talk

## Problem/Feature Description

A speaker is building a 60-minute keynote about "Zero Trust Architecture" that uses AI-generated illustrations in a retro military technical manual style. The talk has a section that introduces five security principles one at a time — each principle is a pillar in an architectural diagram. The speaker wants the audience to see the pillars appear one by one as they're discussed, not all at once.

Similarly, there's a "Security Maturity Checklist" that appears four times across the talk, each time with more items checked off as the audience has learned new concepts.

The speaker has already drafted the base outline with style anchors and image prompts. They now need:
1. Updated outline entries for the two slides that need progressive reveals (the pillars diagram and the checklist), including the build step specifications
2. A build generation plan explaining exactly how to produce the build-step images and insert them into the deck

## Output Specification

Produce the following files:

1. **`updated-outline-excerpt.md`** — The outline entries for the two slides that need builds, including the full `- Builds: N steps` specification with every build step listed. Also include the updated slide budget accounting for the extra build slides.

2. **`build-generation-plan.md`** — A step-by-step plan for generating the build images and inserting them into the PowerPoint deck. Cover: the image generation workflow (how to produce each build step), the file naming and directory structure, and the slide insertion approach (layout, positioning, speaker notes placement).

## Input Files

The following files are provided as inputs. Extract them before beginning.

=============== FILE: inputs/outline-excerpt.md ===============
# Zero Trust Architecture — From Perimeter to Principles

**Spec:** Provocateur | 60 min | RSA Conference | Security engineers
**Slide budget:** 90 slides
**Pacing target:** 1.5 slides/min

---

## Illustration Style Anchor

All generated illustrations use the **military technical manual** style.

**Model:** `gemini-3-pro-image-preview`

### STYLE ANCHOR (FULL — Landscape 1920×1080)
> Retro U.S. Military WWII technical manual style. Pen-and-ink line art on aged parchment background with foxing. Blue-ink leader lines, decorative military document border ornaments, classification stamps, and technical manual header formatting. All people/robots/animals wear WWII uniforms with garrison caps and rank insignia. Render all callout labels in large bold font. FIG. numbering on each illustration.

### Conventions
- Sequential FIG. numbering
- Classification stamp rotates: "RESTRICTED", "CONFIDENTIAL", "TOP SECRET"
- Recurring character: a sergeant with a clipboard evaluating each principle

---

## Act 2: The Five Principles [20 min, slides 25-50]

### Slide 30: The Five Pillars of Zero Trust
- Format: **FULL**
- Illustration: Five classical pillars supporting a "ZERO TRUST" architrave, each labeled with a principle
- Image prompt: `[STYLE ANCHOR]. FIG. 15. Five classical stone pillars in architectural elevation view. Each pillar labeled: "VERIFY EXPLICITLY", "LEAST PRIVILEGE", "ASSUME BREACH", "MICRO-SEGMENTATION", "CONTINUOUS VALIDATION." Architrave reads "ZERO TRUST ARCHITECTURE." The sergeant stands beside with clipboard, checking off each pillar. Classification: TOP SECRET.`

### Slide 38: Security Maturity Checklist (First Appearance)
- Format: **FULL**
- Illustration: Military personnel evaluation form — security maturity assessment with first two items checked
- Image prompt: `[STYLE ANCHOR]. FIG. 20. PERSONNEL EVALUATION FORM: SECURITY MATURITY ASSESSMENT. Checklist with 6 items: "IDENTITY VERIFICATION" [checked], "ACCESS CONTROLS" [checked], "NETWORK SEGMENTATION" [unchecked], "CONTINUOUS MONITORING" [unchecked], "INCIDENT RESPONSE" [unchecked], "ZERO TRUST COMPLIANCE" [unchecked]. Stamp: EVALUATION IN PROGRESS.`

### Slide 45: Security Maturity Checklist (Second Appearance)
- Format: **FULL**
- Illustration: Same form, now with four items checked
- Image prompt: `[STYLE ANCHOR]. FIG. 25. Same PERSONNEL EVALUATION FORM. Now "IDENTITY VERIFICATION" [checked], "ACCESS CONTROLS" [checked], "NETWORK SEGMENTATION" [checked], "CONTINUOUS MONITORING" [checked], "INCIDENT RESPONSE" [unchecked], "ZERO TRUST COMPLIANCE" [unchecked]. Stamp: MAKING PROGRESS.`

### Slide 52: Security Maturity Checklist (Third Appearance)
- Format: **FULL**
- Illustration: Same form, now with five items checked
- Image prompt: `[STYLE ANCHOR]. FIG. 30. Same form. Five of six checked. Only "ZERO TRUST COMPLIANCE" unchecked. Stamp: NEARLY THERE.`

### Slide 58: Security Maturity Checklist (Final — All Checked)
- Format: **FULL**
- Illustration: Complete form, all items checked, approval stamp
- Image prompt: `[STYLE ANCHOR]. FIG. 35. Same form, all six items checked. Large "APPROVED" stamp. Radiating approval lines. The sergeant salutes.`
=============== END OF FILE ===============
