---
name: presentation-creator
description: >
  Creates new presentations grounded in the speaker's documented rhetoric patterns,
  using a personal rhetoric-knowledge-vault as a constitutional style guide. Follows
  an interactive, spec-driven process: distill intent from the user's prompt, jointly
  select rhetorical instruments from the vault catalog, architect the talk structure,
  develop content with speaker notes, run guardrail checks, generate a .pptx deck,
  and publish per the speaker's workflow. Use this skill whenever the user wants to
  create a new presentation, build a talk, write a conference submission, design a
  slide deck, prepare for a speaking engagement, or mentions "presentation" or "talk"
  in the context of content creation. Also trigger when the user describes a topic
  they want to present on, asks to adapt an existing talk for a new audience, or
  wants to develop a CFP abstract. Not a generic slide-deck tool — requires a
  populated rhetoric-knowledge-vault and follows the speaker's established style.
user_invocable: true
---

# Presentation Creator

Build presentations that match the speaker's documented rhetoric and style patterns.
The rhetoric-knowledge-vault is this skill's constitution. Every presentation is a
joint effort — the skill brings rhetoric knowledge, the author brings topic expertise.

## Before You Start: Load the Vault

The vault lives at `~/.claude/rhetoric-knowledge-vault/` (may be a symlink to a custom
location). Read `tracking-database.json` from there to get `config.vault_root`.

Load from vault root: `rhetoric-style-summary.md` (constitution — all patterns),
`slide-design-spec.md` (visual rules), `speaker-profile.json` (structured data).
Then load local references: `references/process.md`, `references/guardrails.md`,
`references/patterns/_index.md`.

**Checks:** Warn if `profile.generated_date < summary."Last updated"` (stale profile).
Warn if `schema_version > 1`. If profile doesn't exist (<10 talks), run in
**summary-only mode** — read instruments from summary prose, use default guardrail
thresholds (1.5 slides/min, 45% Act 1 cap), ask for template/publishing interactively.

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

**The instrument menu comes from the vault, not from a static file.** Read the summary
(sections 2-13) and profile `instrument_catalog` for options.

### 11 Decisions to make together:

Mode, Opening, Narrative, Humor, Audience Interaction, Closing, Slide Design,
Persuasion, Template Patterns, Pattern Strategy, Illustration Strategy. Each reads
from the matching `instrument_catalog` entry + summary section. Decision #10 uses the
4-tier Pattern Strategy from `references/patterns/_index.md` + `profile → pattern_profile`.
Decision #11 (Illustration Strategy) is optional — only when the author wants
AI-generated illustrations. Walks through style proposals informed by the talk's
concepts and the vault's visual history, format vocabulary, model choice, and visual
continuity devices (see `references/process.md` for the full workflow).

For each: present options, recommend based on spec, let author choose.
If co-presented, add role split and voice differentiation — see `references/process.md`.

**Slide budget** — read from `profile → guardrail_sources.slide_budgets` at runtime.
If the profile is unavailable (summary-only mode), use these defaults:

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

## Illustration Style Anchor  ← only when illustration strategy is defined
**Model:** `model-name`
### STYLE ANCHOR (FULL — Landscape 1920×1080)
> [anchor paragraph]

## Opening Sequence [3 min, slides 1-5]
### Slide 1: Title Slide
- Format: **FULL**            ← only when illustration strategy is defined
- Illustration: [visual concept]
- Image prompt: `[STYLE ANCHOR]. [generation prompt]`
- Visual: [description]
- Speaker: [no notes — visual only]
### Slide 2: [Opening hook]
...

## Act 1: [Title] [N min, slides X-Y]
...
## [CUT LINE: drop below here for short version]
...
## Closing Sequence [3 min, slides N-end]
```

When an illustration strategy is defined, each slide gets Format, Illustration, and
Image prompt fields. The `[STYLE ANCHOR]` token in prompts references the header
anchors. Talks without illustration strategy use the standard `- Visual:` field only.

**Placeholders** use typed, independent numbering:
`[AUTHOR 01]`, `[DEMO 01]`, `[DATA 01]`, `[SCREENSHOT 01]`, `[IMAGE 01]`, `[MEME 01]`

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
[INFO] Pattern score projection: {estimated score based on architecture decisions}
[RECURRING/CONTEXTUAL] Presentation Patterns: {taxonomy-based antipattern flags}
[PASS/FAIL/SKIP] Illustrations: {coverage} | {format tags} | {prompt quality}
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
→ `manage_image` for each slide. When the outline has an Illustration Style Anchor,
generate illustrations first (`generate-illustrations.py`) and use illustration-format-aware
insertion (FULL → full-bleed, IMG+TXT → image + text, EXCEPTION → real asset).
Inject speaker notes via python-pptx batch after MCP generation.

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
5. **Go-live checklist** — surface unobservable patterns from `references/patterns/_index.md`
   as a delivery preparation reminder (see `references/process.md` Step 6.5)

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
5. Save approved materials to the Sessions Catalog (see below)

## Sessions Catalog

The sessions catalog (`{vault_root}/sessions-catalog.md`) is the single source of
submission-ready materials for active talks. It stores the latest approved title,
abstract, and outline for each talk the speaker is actively submitting to conferences.

### What goes in the catalog

Each entry contains:
- **Title** (including subtitle if any)
- **Abstract** (submission-ready, anti-pattern-checked)
- **Outline** (with section descriptions and time allocations)
- **Small Print** (notes for the Program Committee — positioning the talk relative to
  other sessions, clarifying what the talk IS and ISN'T, or flagging anything the PC
  should know. Internal, not public-facing)

### When to read / write the catalog

- **Phase 0:** Load alongside vault documents to know the active rotation and flag overlapping territory.
- **Before a new CFP:** Pull existing entry if present; adapt rather than rewrite.
- **After CFP abstract writing (step 5):** Save approved title, abstract, and outline as new or updated entry.
- **After Phase 4:** Create entry if none exists; update outline to latest.
- **Talk retired:** Remove entry or move to archive section at bottom of file.

### Catalog maintenance rules

- The catalog is a **living document** — each entry reflects the LATEST approved version. Full history lives in the vault's tracking database and analysis files.
- Run an anti-pattern check on catalog entries before saving (use the blog-writer skill's `ai-anti-patterns.md` if installed). Conference abstracts are public-facing — they should read like the speaker wrote them.
- Keep the "Last updated" date at the top of the file current.
- Entries are separated by `---` horizontal rules for easy scanning.
