---
name: presentation-creator
description: >
  Create new presentations from scratch using the speaker's documented rhetoric
  patterns as a constitutional style guide. Follows an interactive, spec-driven
  process: distill intent from the user's prompt, jointly select rhetorical
  instruments, architect the talk structure, develop content with speaker notes,
  and iterate with the author. Use this skill whenever the user wants to create
  a new presentation, build a talk, write a conference submission, design a slide
  deck, prepare for a speaking engagement, or mentions "presentation" or "talk"
  in the context of content creation. Also trigger when the user describes a topic
  they want to present on, asks to adapt an existing talk for a new audience, or
  wants to develop a CFP abstract.
user_invocable: true
---

# Presentation Creator

Build presentations that match the speaker's documented rhetoric and style patterns.
The rhetoric-knowledge-vault is this skill's constitution. Every presentation is a
joint effort — the skill brings rhetoric knowledge, the author brings topic expertise.

**This skill defines PROCESS. The vault provides CONTENT.** All instruments, thresholds,
voice patterns, and design rules come from the vault at runtime.

## Before You Start

### Step 0: Locate the Vault

If the vault root path is unknown, ask via `AskUserQuestion`:
"Where is your rhetoric knowledge vault?"

### Step 1: Load Vault Documents

```python
# Load order — read all three from vault root:
vault_files = {
    "summary":  f"{vault_root}/rhetoric-style-summary.md",   # Constitution: all patterns
    "design":   f"{vault_root}/slide-design-spec.md",         # Visual rules
    "profile":  f"{vault_root}/speaker-profile.json",         # Structured data
}
# Then load local references:
#   references/process.md      — Phase workflow detail
#   references/guardrails.md   — Guardrail check structure
```

**Freshness check:** If `profile.generated_date < summary."Last updated"`, warn that
new talks may have been parsed — offer to run "update speaker profile" first.

**Schema version:** This skill expects `schema_version: 1`. Warn if higher.

**If profile doesn't exist** (vault has <10 talks), run in **summary-only mode**:

| Phase | Fallback |
|-------|----------|
| 2: Architecture | Read instruments from summary prose (no structured catalog) |
| 4: Guardrails | Default thresholds: 1.5 slides/min, 45% Act 1 cap, three-part close |
| 5: Slides | Ask author for template path, discover layouts via python-pptx |
| 6: Publishing | Ask author for steps interactively (no stored workflow) |

## Workflow Overview

| Phase | What happens | Gate |
|-------|-------------|------|
| 0: Intake | Load vault, gather context | Topic and context captured |
| 1: Intent Distillation | Clarifying questions → Presentation Spec | Author confirms spec |
| 2: Rhetorical Architecture | Joint instrument selection from vault catalog | Author approves architecture |
| 3: Content Development | Section-by-section outline with speaker notes | Draft delivered |
| 4: Revision & Guardrails | Iterate on feedback, run guardrail checks | Author declares outline done |
| 5: Slide Generation | Build .pptx from template, iterate with author | Author declares slides done |
| 6: Publishing | Export, shownotes, QR per speaker's workflow | Published and ready |

Do not skip phases. Do not write content before Phase 3. Phase 2 is joint, not autonomous.

## Phase 0: Intake & Context Loading

1. Load vault documents (see above).
2. Capture what the user has shared — topic, conference, audience, time slot.
3. Read any provided CFP description, conference website, or existing talk to adapt.
4. Report what you know and what you still need.

## Phase 1: Intent Distillation

Ask about what's missing; skip what's known. See `references/process.md` for the full
question set. Produce the **Presentation Spec**:

```
PRESENTATION SPEC
=================
Title:             [working title]
Thesis:            [one sentence]
Audience:          [who]
Venue:             [conference, slot, format]
Mode:              [from profile presentation_modes — present options]
Commercial intent: [none / subtle / direct]
Must-include:      [list]
Must-avoid:        [list]
Co-presenter:      [none | name + handle + role split]
Profanity register:[from profile rhetoric_defaults]
Duration target:   [from profile rhetoric_defaults.default_duration_minutes]
Shownotes slug:    [from profile speaker.shownotes_url_pattern]
```

Gate: Author confirms or edits the spec.

## Phase 2: Rhetorical Architecture

**The instrument menu comes from the vault, not from a static file.** Read the rhetoric
summary (sections 2-13) and profile `instrument_catalog` to extract available options.

### Decisions to make together:

| # | Decision | Source |
|---|----------|--------|
| 1 | Presentation Mode | `profile → presentation_modes[]` |
| 2 | Opening Pattern | summary Section 2 + `instrument_catalog.opening_patterns` |
| 3 | Narrative Structure | `instrument_catalog.narrative_structures` |
| 4 | Humor Register | `instrument_catalog.humor_techniques` (grouped by register) |
| 5 | Audience Interaction | `instrument_catalog.audience_interactions` |
| 6 | Closing Pattern | `instrument_catalog.closing_patterns` |
| 7 | Slide Design Direction | `slide-design-spec.md` + `profile → design_rules` |
| 8 | Persuasion Toolkit | `instrument_catalog.persuasion_techniques` |
| 9 | Template Rich Patterns | `slide-design-spec.md` Section 7 template catalog |

**If co-presented**, add: Role Split, Footer Adaptation (`design_rules.footer.co_presented_extra`),
Voice Differentiation (use `[SPEAKER A]:` / `[SPEAKER B]:` prefixes in notes).
See `references/process.md` for co-presenter handling.

For each decision: present options, recommend based on spec, let author choose.

**Slide budget** (from `profile → guardrail_sources.slide_budgets`):

| Duration | Max slides | Slides/min |
|----------|-----------|------------|
| 20 min | 30 | 1.5 |
| 30 min | 45 | 1.5 |
| 45 min | 70 | 1.5 |
| 60 min | 90 | 1.5 |
| 75 min | 110 | 1.5 |

Gate: Author approves the architecture.

## Phase 3: Content Development

Write the talk as a section-by-section outline. See `references/process.md` for the full
outline format, voice calibration, callback identification, and placeholder types.

**Outline structure** (abbreviated — full format in `references/process.md`):

```markdown
# [Talk Title]
**Spec:** [mode] | [duration] | [venue]
**Slide budget:** [N slides]

## Opening Sequence [3 min, slides 1-5]
### Slide 1: Title Slide
- Visual: [description]
- Speaker: [no notes — visual only]
### Slide 2: [Opening hook]
- Visual: [description]
- Speaker: "[opening lines in the speaker's voice]"

## Act 1: [Title] [N min, slides X-Y]
...
## [CUT LINE: drop below here for short version]
...
## Closing Sequence [3 min, slides N-end]
```

**Placeholders** use typed, independent numbering:
`[AUTHOR 01]`, `[DEMO 01]`, `[DATA 01]`, `[SCREENSHOT 01]`, `[MEME 01]`

Save to: `{presentations-dir}/{conference}/{year}/{talk-slug}/presentation-outline.md`

## Phase 4: Revision & Guardrails

Run guardrail checks from `references/guardrails.md` with thresholds from the profile.

```
GUARDRAIL CHECK — {talk title}
================================================
[PASS/FAIL] Slide budget: {actual}/{max} for {duration}-min slot
[PASS/WARN] Act 1 ratio: {%} (limit: {max}% — 40% for 20-30min, 45% for 45min, 50% for 60+min)
[PASS/FAIL] Branding: footer elements for {conference}
[PASS/FAIL] Profanity: {register} applied, {N} on-slide
[PASS/FAIL] Data attribution: {N} slides checked, {M} missing sources
[PASS/FAIL] Time-sensitive: {count} items
[PASS/FAIL] Closing: summary={y/n} CTA={y/n} social={y/n}
[PASS/FAIL] Cut lines: {present/missing}
[INFO] Anti-patterns: {flags from profile recurring_issues}
================================================
```

Iterate on author feedback. Apply changes first, guardrail second. Flag but don't block
intentionally overridden guardrails. See `references/process.md` for iteration protocol.

## Phase 5: Slide Generation & Interactive Iteration

Build the .pptx deck from the finalized outline. See `references/slide-generation.md`
for the full technical reference.

**Setup:**
```python
from pptx import Presentation

# Strip demo slides from template, keep layouts only
tmpl = Presentation(profile["infrastructure"]["template_pptx_path"])
xml_slides = tmpl.slides._sldIdLst
for sldId in list(xml_slides):
    rId = sldId.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
    tmpl.part.drop_rel(rId)
    xml_slides.remove(sldId)
tmpl.save(output_path)
```

Then open with MCP `open_presentation` and walk the outline: `add_slide` → `populate_placeholder`
→ `manage_image` for each slide. Inject speaker notes via python-pptx batch after MCP generation.

**Key rules from profile:**
- `design_rules.background_color_strategy` — how to pick background colors
- `design_rules.footer` — pattern, position, font, color adaptation
- `design_rules.slide_numbers` — typically "never"
- `infrastructure.template_layouts[]` — layout index + placeholder mapping

## Phase 6: Publishing

Read `publishing_process` from `speaker-profile.json`. Each speaker's workflow differs.

If `publishing_process` is missing or empty, ask the author interactively.

Execute the steps from the profile:
1. **Export** — run `export_method` / `export_script` (see `references/slide-generation.md`)
2. **Shownotes** — if `shownotes_publishing.enabled`, follow the described method
3. **QR Code** — if `qr_code.enabled`, generate and insert per profile
4. **Additional steps** — execute each `additional_steps[]` entry

Gate: Author confirms published and ready to deliver.

---

## Adapting Existing Talks

1. Check if the talk has been ingested by the vault. If not, process it first.
2. Read the original talk's analysis from `{vault_root}/analyses/`
3. Copy the previous deck as starting point — do NOT start from fresh template.
4. Start at Phase 1 with the original spec pre-filled, modify as needed.
5. Auto-generate adaptation checklist: footer, shownotes slug, time-sensitive content,
   slide budget, profanity register, locale references, commercial intent.

## CFP Abstract Writing

1. Complete Phase 0-1 (lighter touch)
2. Skip Phase 2 (not needed for an abstract)
3. Write: title, abstract (200-300 words), key takeaways (3-5 bullets), speaker bio
4. Phase 4 revision as normal
