---
name: presentation-creator
description: >
  Creates presentations grounded in the speaker's documented rhetoric patterns,
  using a personal rhetoric-knowledge-vault as a constitutional style guide.
  Interactive and spec-driven: distill intent, jointly select rhetorical
  instruments from the vault catalog, architect the talk, develop content with
  speaker notes, run guardrail checks, generate a .pptx deck, publish per the
  speaker's workflow. Use whenever the user wants to create a presentation, build
  a talk, write a conference submission, design a slide deck, prepare for a
  speaking engagement, describe a topic to present on, or adapt an existing talk
  for a new audience. Also handles CFP abstracts; the sessions catalog of submission-ready
  titles, abstracts, and outlines; and single post-authoring tasks on an existing
  talk — QR code, deck export, shownotes page, YouTube thumbnail, linking a
  recording. Not a generic slide-deck tool — requires a populated
  rhetoric-knowledge-vault and follows the speaker's established style.
user_invocable: true
---

# Presentation Creator

Process steps in order. Do not skip ahead.

Steps 0–7 are one sequential workflow — Step 0 before Step 1, Step 1 before
Step 2, and so on. Do not parallelize. A request may enter the workflow at a
later step (see "Where to enter" below), but from that point it still runs in
order, and every entry requires the vault-loading gate and the documented
pre-flight checklist before any action.

Resolve the absolute path of this loaded `SKILL.md`, then set
`speaker_toolkit_root` to the plugin root two directories above the directory
containing this file. Never derive it from the consumer working directory.
Treat `{speaker_toolkit_root}` as absolute in every toolkit-owned command;
talk, vault, and output paths remain consumer-owned.

Build presentations that match the speaker's documented rhetoric and style patterns.
The rhetoric-knowledge-vault is this skill's constitution. Every presentation is a
joint effort — the skill brings rhetoric knowledge, the author brings topic expertise.

## Before You Start: Load the Vault

The vault lives at `~/.claude/rhetoric-knowledge-vault/` (may be a symlink to a custom
location). Load `tracking-database.json` with the strict owner reader at
`{speaker_toolkit_root}/skills/vault-ingress/scripts/read-tracking-database.py` to
get `config.vault_root`; never parse it directly. The stdlib-only reader may use
the host interpreter for this one bootstrap read. It accepts legacy database
schema 0 and current schema 1 without rewriting either. Stop on unsupported root
or owner-record generations and route migration to `Skill(skill: "vault-ingress")`.

Discover the exact non-empty `config.python_path`, then immediately re-read the
same canonical database path with that interpreter and require the same SHA-256;
restart discovery if the generation changed. Use only that configured interpreter
for every later toolkit command. Missing or unusable configuration stops this flow
and invokes `Skill(skill: "vault-ingress")` with Step 1 as the handoff context.
Read-only phases may continue on schema 0, but publishing and post-event writes
require schema 1 before their paired network, deck, image, or tracking side
effects. For schema 0, invoke `Skill(skill: "vault-ingress")` with a Step 1
migration handoff before continuing.

Load from vault root: `rhetoric-style-summary.md` (constitution — all patterns),
`slide-design-spec.md` (visual rules), `speaker-profile.json` (structured data).
The `interaction-rules` steering rule (one-question-at-a-time, applies to all phases)
is loaded automatically via plugin steering — do not treat it as a vault-root document.

Then load the reference for the phase you are entering — each Step below names its
own file. Pattern selection additionally reads
[references/patterns/_index.md](references/patterns/_index.md).

**Checks:** Warn if `profile.generated_date < summary."Last updated"` (stale profile).
Then run:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/pattern_history_status.py" \
  path/to/speaker-profile.json path/to/rhetoric-style-summary.md
```

Read [references/pattern-history-authorization.md](references/pattern-history-authorization.md)
before consuming any catalog-derived historical field. It owns the emitted payload
shape, the six domain contracts, source selection, profile schema tiers, Section 15
eligibility, summary-only mode, and the cross-generation comparison rules.
`history_enabled` is not blanket permission — require the specific domain per use.

## Workflow Overview

| Phase | What happens | Gate |
|-------|-------------|------|
| 0: Intake | Load vault, gather context | Topic and context captured |
| 1: Intent Distillation | Clarifying questions → `talk:` block of `outline.yaml`; generate TL;DR-only `narrative.md` (partial) | Author confirms metadata |
| 2: Rhetorical Architecture | Joint instrument selection → `architecture`, `applied_patterns`, `chapters[]` in `outline.yaml`; regenerate `narrative.md` (partial) for review | Author approves narrative + architecture |
| 3: Content Development | Fill `slides[]` + `interludes[]` in `outline.yaml`; finalize `narrative.md` (full) + generate `script.md`, `slides.md`, `rhetorical-review.md` | Draft delivered |
| 4: Revision & Guardrails | Iterate on feedback, run guardrail checks against `outline.yaml` | Author declares outline done |
| 5: Slide Generation | Build .pptx from template (or presenterm `{slug}.md`) using `slides.md` build-sheet | Author declares slides done |
| 6: Publishing | Export, shownotes, QR per speaker's workflow | Published and ready |
| 7: Post-Event | YouTube thumbnail, video to shownotes | Thumbnail approved, video linked |

Do not skip phases. Do not write content before Phase 3. Phase 2 is joint, not autonomous.

**Where to enter.** A fresh talk starts at Step 0. Four requests enter later
instead: a single post-authoring task (QR code, export, shownotes, thumbnail,
linking a recording), adapting an existing talk, writing a CFP abstract, and
sessions-catalog work. Read
[references/alternate-entry-flows.md](references/alternate-entry-flows.md) for
the matching one — it names the step to enter at and the only sanctioned skip
(the CFP flow omits Phase 2, which an abstract does not need). Vault loading
stays mandatory for all of them.

**Talk-directory artifacts.**

By end of Phase 3, the talk directory contains:

| File | Role | Authored or generated? |
|------|------|------------------------|
| `outline.yaml` | Source of truth — talk metadata, chapters, slides, interludes, patterns, callbacks | Authored (agent-edited, schema-validated) |
| `narrative.md` | TL;DR of the idea + one-line-per-slide deck walk | Generated by `extract-narrative.py` |
| `script.md` | Screenplay-form rehearsal artifact | Generated by `extract-script.py` |
| `slides.md` | Per-slide build-sheet (format, visual, image prompts, builds, callbacks) | Generated by `extract-slides.py` |
| `rhetorical-review.md` | Structural gap-check report | Generated by `check-rhetorical.py` |
| `{slug}.md` | Renderable deck (presenterm-format talks only) | Authored/built in Phase 5 |
| `*.pptx` | Renderable deck (pptx talks) | Built in Phase 5 |

Regenerate the four derived artifacts after every edit to `outline.yaml`:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/extract-narrative.py" outline.yaml > narrative.md
"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/extract-script.py"    outline.yaml > script.md
"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/extract-slides.py"    outline.yaml > slides.md
"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/check-rhetorical.py"  outline.yaml > rhetorical-review.md
```

Validate the YAML with `"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/outline_schema.py" outline.yaml` — exits non-zero with a typed error if any validator fails.

`narrative.md` is the exception to "by end of Phase 3" — it is generated earlier
in partial form during Phases 1–2 with `--partial`, which validates `talk` +
`chapters` without requiring `slides[]`. The plain (full-validation) commands
above apply from Phase 3 onward, once `slides[]` exists.

The four `.md` files are read-only — never edit them directly; they regenerate
deterministically from `outline.yaml`.

## Step 0 — Intake & Context Loading

Read [references/phase0-intake.md](references/phase0-intake.md).

1. Load vault documents (see above).
2. Capture what the user has shared — topic, conference, audience, time slot.
3. Read any provided CFP description, conference website, or existing talk to adapt.
4. Report what you know and what you still need.

Proceed immediately to Step 1.

## Step 1 — Intent Distillation

Read [references/phase1-intent.md](references/phase1-intent.md) for the full
question set. Ask about what's missing; skip what's known.

Author the **talk metadata block** of `outline.yaml`. The field-by-field
reference is the `## The talk: block` table in
[references/phase3-content.md](references/phase3-content.md); `outline_schema.py:TalkMetadata`
is the authoritative list. Leave `architecture`, `engine`, `deck_theme`, and
`engine_source` as placeholders — Phase 2 fills them.

Generate the slug per `publishing_process.shownotes.slug_convention` in the profile.
Slug validation is kebab-case (lowercase alphanumeric + single hyphens).

Gate: Author confirms or edits the metadata.

Save the partial outline to `{presentations-dir}/{conference}/{year}/{talk-slug}/outline.yaml`,
then generate the narrative stub so the author can read the TL;DR early:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/extract-narrative.py" --partial outline.yaml > narrative.md
```

At this phase `narrative.md` carries the TL;DR only — the chapter body fills in
at Phase 2 and the per-slide walk replaces it once slides exist in Phase 3.
Surface it to the author for an early read.

The talk block is the source of truth for the slug, duration, mode, and other
metadata. Later phases extend the SAME file with `chapters[]`, `slides[]`,
`interludes[]`, etc. — do not create a separate spec or outline file.

Proceed immediately to Step 2.

## Step 2 — Rhetorical Architecture

Read [references/phase2-architecture.md](references/phase2-architecture.md); it
also owns the slide-budget calculation from `guardrail_sources.slide_budgets[]`.

**The instrument menu comes from the vault, not from a static file.** Read the summary
(sections 2-13) and profile `instrument_catalog` for options.

**12 decisions to make together:** Mode, Engine & Theme Sourcing, Opening,
Narrative, Humor, Audience Interaction, Closing, Slide Design, Persuasion,
Template Patterns, Pattern Strategy, Illustration Strategy. Each reads from the
matching `instrument_catalog` entry + summary section. For each: present options,
recommend based on spec, let author choose. If co-presented, add role split and
voice differentiation — see [references/phase1-intent.md](references/phase1-intent.md).

- **Decision #2 (Engine & Theme Sourcing)** picks the deck tooling (pptx vs
  presenterm) and theme via the idea-sourcing wizard; it reads `profile →
  presentation_engines` and the chosen mode's `typical_engine`, and writes
  `talk.engine` / `talk.deck_theme` / `talk.engine_source`.
- **Decision #11 (Pattern Strategy)** uses
  [references/patterns/_index.md](references/patterns/_index.md). Use the full
  4-tier history view only when the Phase 0 pattern-history status is enabled;
  otherwise use a flat current-taxonomy menu without usage, novelty, strength,
  underuse, or mode-history claims.
- **Decision #12 (Illustration Strategy)** is optional — only when the author
  wants AI-generated illustrations. Delegate to `Skill(skill: "illustrations")`
  for the full collaboration (style proposals grounded in vault
  `visual_style_history`, format vocabulary, model choice, visual continuity
  devices). The skill writes the approved `style_anchor` block into
  `outline.yaml`.

Once the architecture is set, author `chapters[]` (section headings, `target_min`,
`argument_beats[]`) into `outline.yaml`, then regenerate the narrative — now with
its chapter body — for human review:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/extract-narrative.py" --partial outline.yaml > narrative.md
```

Present `narrative.md` to the author. This is the narrative-approval point: the
author reads the TL;DR and the chapter arc and approves or revises the argument
before any per-slide content is written in Phase 3. Leave `argument_beats[].slide_refs`
empty here — slides do not exist yet, so `--partial` validation rejects any ref;
wire them to real slides in Phase 3.

Gate: Author approves the narrative (`narrative.md`) and the architecture.

Proceed immediately to Step 3.

## Step 3 — Content Development

Read [references/phase3-content.md](references/phase3-content.md) for the full
outline schema, field-by-field guidance, pattern application, callback ledger,
voice calibration, placeholder definitions, and meme-brief format.

Fill `slides[]` and `interludes[]` in `outline.yaml`.

Placeholders use typed, independent numbering (each type starts at 01):
`AUTHOR-01`, `DEMO-01`, `DATA-01`, `SCREENSHOT-01`, `IMAGE-01`, `MEME-01`. Every
placeholder requiring author input MUST use one of these typed tags — never
generic `TODO` or `TBD`.

After saving `outline.yaml`, validate and regenerate the derived artifacts using
the commands in "Talk-directory artifacts" above, starting with `outline_schema.py`.

Gate: Draft delivered.

Proceed immediately to Step 4.

## Step 4 — Revision & Guardrails

Read [references/phase4-guardrails.md](references/phase4-guardrails.md) for the
full check list, report format, and iteration protocol.

Run two checkers — they cover different surfaces:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/check-rhetorical.py" outline.yaml > rhetorical-review.md
"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/guardrail-check.py"   outline.yaml path/to/speaker-profile.json
```

`check-rhetorical.py` enforces the closed pattern taxonomy and writes the
`rhetorical-review.md` artifact — PASS / FLAG / N/A per check.

`guardrail-check.py` enforces speaker-profile-aware rules and emits one schema-v1
JSON object on stdout. Render its `recurring_antipatterns` records unchanged; do
not inspect profile rows to recreate them. Exit 0 means the report was produced —
FAIL remains a check status. Input failures exit non-zero, write diagnostics to
stderr, and leave stdout empty.

The script reports the 7 independent non-pattern checks plus pattern-history
status; the agent adds these categories manually:

- Current-taxonomy contextual antipattern scan of the new outline — runs even when
  history is disabled and uses `[CONTEXTUAL]`, never `[RECURRING]`
- Speaker-specific recurring issues from `profile.guardrail_sources.recurring_issues[]`
  — schema-v4/v5 entries with `source_lane: "non_pattern"` remain usable
  independently; legacy or ambiguous entries are suppressed, while catalog
  warnings come from authorized `pattern_profile` history
- Illustration coverage when `style_anchor` is present
- Time-sensitive content scan
- Murder-Your-Darlings filter pass
- Emotion-balance and screening-with-critics where applicable
- AI writing patterns across every prose surface, delegated with
  `Skill(skill: "blog-writer")` — it owns the pattern catalog, so never
  reimplement the scan here; report SKIP and point the author at
  `tessl install jbaruch/blog-writer` when it is absent

Iterate on author feedback. Apply changes first, guardrail second. Flag but don't
block intentionally overridden guardrails.

Gate: Author declares the outline done.

Proceed immediately to Step 5.

## Step 5 — Slide Generation

Read [references/phase5-slides.md](references/phase5-slides.md) for the full
technical reference: the engine branch, deck-op emission, which ops to omit on
illustrated slides, the post-build pass order, and the presenterm build.
Op vocabulary and state rules live in
[references/deckops-spec.md](references/deckops-spec.md).

Build the deck from the finalized `outline.yaml`, using `slides.md` (the
build-sheet extracted by `extract-slides.py`) as the per-slide instruction list.
Branch on `talk.engine`, read via `outline_schema.py` — never re-parse YAML by hand.

**For pptx talks**, emit a deck op sequence from `slides.md` + the profile layout
map, validate it, then build with the real PowerPoint app:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/validate-deckops.py" ops.txt
bash "{speaker_toolkit_root}/skills/presentation-creator/scripts/build-deck.sh" "{template_copy_pptx_path}" "{output_path}" ops.txt
```

After the build completes, if `outline.yaml` declares `style_anchor`, delegate to
`Skill(skill: "illustrations")` to generate illustrations, generate any
progressive-reveal builds, and apply them to the deck.

Then run the post-build passes in the order phase5-slides.md prescribes —
`expand-builds.sh`, then `inject-notes.sh`, then `apply-backgrounds.sh` last.
Never reorder them. See `rules/deck-editing-rules.md`.

**For presenterm talks**, hand-author `{slug}.md` from the `slides.md`
build-sheet per phase5-slides.md — Presenterm Talks.

Every layout, background, footer, and slide-number decision reads from
`speaker-profile.json` (`design_rules.*`, `infrastructure.template_layouts[]`) at
runtime — phase5-slides.md names the exact field per decision. Never hardcode them.

Gate: Author declares slides done.

Proceed immediately to Step 6.

## Step 6 — Publishing

Read [references/phase6-publishing.md](references/phase6-publishing.md); export
detail lives in [references/phase5-slides.md](references/phase5-slides.md).

Read `publishing_process` from `speaker-profile.json`. Each speaker's workflow differs.
If `publishing_process` is missing or empty, ask the author interactively.

Execute the steps from the profile:
0. **Resources** — extract and curate resource list from outline (`extract-resources.py`)
1. **Export** — run `export_method` / `export_script`
2. **Shownotes** — if `publishing_process.shownotes.enabled`, use curated resources from Step 6.0
3. **QR Code** — if `qr_code.enabled`, generate and insert per profile
4. **Additional steps** — execute each `additional_steps[]` entry
5. **Go-live checklist** — surface unobservable patterns from
   [references/patterns/_index.md](references/patterns/_index.md) as a delivery
   preparation reminder (see phase6-publishing.md Step 6.5)

Gate: Author confirms published and ready to deliver.

Finish here. Step 7 is triggered separately, days or weeks after delivery.

## Step 7 — Post-Event

Triggered separately — days or weeks after delivery. Not part of the linear
Phase 0-6 flow. The talk has been given and recorded.

Read [references/phase7-post-event.md](references/phase7-post-event.md) for the
pre-flight checklist and Step 7.2. Step 7.1 detail lives in
`skills/illustrations/references/thumbnails.md`.

1. **YouTube Thumbnail** — delegate to `Skill(skill: "illustrations")` (the
   skill handles slide selection, speaker-photo resolution, aesthetic precedence,
   composition via Gemini, and speaker iteration).
2. **Video to Shownotes** — add video embed/link to existing shownotes page.

Gate: Thumbnail approved, video linked. Finish here.
