# Changelog

### feat(patterns) — add `second-look`

Vault-derived build/slides pattern: build the slide in two legibility layers — a room layer that lands
from the back row, and a reward layer visibly present but too fine to read live. The unresolved detail
drives shownotes visits; the slide sells the return trip rather than teaching in the room. The mechanism
is a curiosity gap (Loewenstein 1994), not the disfluency claim retired below — hence the mandatory room
layer. Boundaries against `_anti_ant-fonts` and `_anti_slideuments`, and the link to `spaced-followup`
(the destination is a spaced re-exposure), are stated in the file.

Detection carries a caveat: the pattern is executed with text rendered inside images, so shape-level
PPTX extraction reports these slides as image-only and inverts the finding. Detectable only from
rendered slide images. The pipeline fix is #116.

### feat(patterns) — map *Make It Stick* into the taxonomy

Adds *Make It Stick: The Science of Successful Learning* (Brown, Roediger & McDaniel, 2014) as the
catalog's fourth supplementary source, following the *Presentation Zen* and *Resonate* precedent. The
existing corpus covered attention, persuasion, and aesthetics but not retention. Taxonomy: 104 → 109
entries (82 patterns + 27 antipatterns; 97 observable, 12 unobservable).

New: `guess-first` (generation effect), `retrieval-beat` (testing effect), `spaced-followup` (spacing
effect — unobservable; adds a **Post-Event** section to the go-live checklist, the catalog's first entry
firing after the talk), and the `nodding-room` antipattern (fluency illusion). Refinements folded into
`carnegie-hall`, `brain-breaks`, `know-your-audience`, `red-yellow-green`, and `analog-noise`.

**Correction — `analog-noise` was overclaiming.** It asserted as settled fact that hard-to-read fonts
improve retention (Diemand-Yauman et al. 2011, the study behind Sans Forgetica). That finding has
replicated poorly: a meta-analysis found essentially nothing for problem solving, and Sans Forgetica
studies found no benefit over an ordinary font. Re-grounded on the isolation effect (von Restorff),
which supports the same practice and derives the pattern's key constraint from its mechanism. The
desirable-difficulties framework is not retired — it concerns effortful *retrieval*, not effortful
*reading*. Full argument in the file's "Do Not Make It Hard to Read".

**Rejected, recorded so it is not relitigated:** interleaving (a centerpiece of the book, but braiding
topic threads is workshop guidance and fights `talklet`); mnemonics as a standalone pattern (the book
frames them as retrieval scaffolding, and `star-moment`'s sound-bite sub-type covers the speaker-side
use).

Every new file states its own limits: the generation- and testing-effect literatures study learners
across sessions, not audiences in a room for 45 minutes, so no file claims a talk produces month-later
recall.

Also drops the duplicated taxonomy counts from `phase3-content.md`, which claimed "78 patterns / 25
antipatterns matching the index" while the index said 26 — stale before this branch. The enum is
discovered from the `references/patterns/{prepare,build,deliver}/*.md` globs; the filesystem is the
source of truth and `_index.md` mirrors it for human readers.

## 0.18.45 — 2026-07-01

### fix(rules) — declare `qr-generation-rules.md` in the manifest

`rules/qr-generation-rules.md` was a steering rule in everything but configuration: same imperative
ALWAYS/NEVER/STOP voice as its siblings, referenced by the publishing flow (`phase6-publishing.md` §7)
and `generate-qr.py`, yet absent from the manifest's `rules` array and carrying no frontmatter — so it
never auto-loaded. The `tile.json` → `.tessl-plugin/plugin.json` migration (#106) preserved the
pre-existing omission rather than introducing it. Resolves it as a steering rule (#109): adds
conditional frontmatter (`alwaysApply: false` + `applyTo:` scoped to the presentation-creator QR
flow) per `jbaruch/coding-policy: rule-frontmatter`, declares it in `.tessl-plugin/plugin.json`, and
adds the README rules-table row. Behavior change: the QR rules now auto-load during the presentation
publishing flow instead of being reference-only.

## 0.18.44 — 2026-06-30

### fix(vault-ingress,vault-profile) — strip suspicious download-URL patterns from skill instructions

The `.tessl-plugin/plugin.json` migration (0.18.43) packages skills as directories, so vault-ingress's
reference docs are now scanned at publish — and tessl moderation flagged a Google Drive direct-download
URL (in the `gdown` PDF-fetch example) plus two truncated URL placeholders in the shownotes schema docs
as a Critical E005 finding, blocking the 0.18.43 release. Pass the bare Google Drive file id to `gdown`
(it accepts a `url_or_id` argument, so no download URL is needed) and replace the truncated placeholders
with prose.

## 0.18.43 — 2026-06-30

### chore — migrate `tile.json` manifest to `.tessl-plugin/plugin.json`

Converts the legacy `tile.json` manifest to the current `.tessl-plugin/plugin.json` form via
`tessl plugin migrate`: the `steering` field becomes `rules`, `skills` becomes an array of skill
directory paths, and `tile.json` is removed. Reconciles residual "tile" terminology to "plugin"
across user-facing prose and script messages — README (including the manifest field rename, so the
old "Steering Rules" section is now "Rules" matching `plugin.json` → `rules`), `deck-editing-setup.md`,
`processing-rules.md`, `tessl-version-floating.md`, `presentation-creator/SKILL.md`, the deck-build
`.sh` wrappers, `ensure-drivers.sh`, `generate-qr.py`, and `sync-deck-drivers.py` — and renames the
publish workflow `publish-tile.yml` → `publish-plugin.yml` (cosmetic `name:` and filename; the
trigger is push-to-main, so publishing is unaffected). The gh-aw reviewer prompts' "installed tile"
load-indicator wording becomes "installed plugin". Adds a root `.tesslignore` so the published
plugin ships its context surfaces (skills, rules, evals, manifest, `.mcp.json`, README) and excludes
CI, tests, repo-side scripts, and dev config. Live contracts are left intact: the `.tessl/tiles/`
runtime install path, `v1/tiles/...` registry routes, frozen `evals/*` scenario content, the
`deckops-spec.md` example slide, and historical CHANGELOG references to `tile.json`.

## 0.18.42 — 2026-06-30

### chore — stamp the CHANGELOG version backlog and wire auto-stamping

The CHANGELOG had accumulated un-headed `### ` blocks since 0.18.27 (stamping stopped at the
`## 0.18.26` heading) because no stamp step was wired — against `jbaruch/coding-policy:
context-artifacts` CHANGELOG Hygiene. Reconstructs and inserts the missing `## <version> — <date>`
headings for 0.18.29–0.18.41, with boundaries derived from each version's publish-bump commit and
validated against every entry's introducing commit (0.18.27/0.18.28/0.18.33 had no net-new entries
and are omitted). Wires `jbaruch/coding-policy/.github/actions/stamp-changelog` before
`tesslio/patch-version-publish` so future un-headed top blocks are stamped automatically at publish;
this entry is the first the wired step will stamp.

## 0.18.41 — 2026-06-29

### fix(presentation-creator) — deck drivers surface VBA errors to the CLI instead of a modal (#85)

Every RunDeckOps macro's failure handler popped a `MsgBox` and returned a bare `-1`. Under
osascript automation no human dismisses that modal, so it hung the run and then blocked every
subsequent macro call (PowerPoint `-18`) — the `BuildDeck -18`-on-large-decks symptom reported in
#85 — while the real `Err.Description` died in a dialog the CLI cannot read. All eight Public macros
are now typed `As Variant` and return `"ERROR: <macro> failed at [<token>]: <Err.Number> -
<Err.Description>"` on failure (the success path still returns the numeric count); each AppleScript
driver surfaces an `ERROR:`-prefixed return as an `osascript` error, so the description reaches
stderr. No macro calls `MsgBox`. This closes the last open item in #85 — the driver/`.bas`
packaging restore and the 1800s `with timeout` wrap already shipped.

## 0.18.40 — 2026-06-25

### feat(presentation-creator) — add the Flyover antipattern (audience condescension)

The Presentation Patterns taxonomy had no entry for the speaker who treats the room in
front of them as "flyover country" — diminishing the local audience or region while
valorizing their own home region/employer ("you might not have noticed it here, but where
I'm from it's a real thing"). The behavior sat in the gap between Negative Ignorance and
Alienating Artifact with no first-class name. Adds `deliver/_anti_flyover.md` (deliver
phase, dimensions 4 + 14, inverse of Know Your Audience) and wires it into `_index.md`
(catalog row, dimension maps, summary statistics). Bumps the taxonomy to 104 entries
(78 patterns + 26 antipatterns); the `outline_schema.py` antipattern enum auto-discovers
the new file and its count test is updated. Also reconciles a pre-existing README
miscount (Build phase listed 47/37 where the taxonomy holds 48/38) so the README totals
match `_index.md` at 104 entries / 93 observable.

## 0.18.39 — 2026-06-23

### feat(vault-ingress) — version the video slide-extraction pipeline

The video slide-extraction pipeline (`video-slide-extraction.py`) carried no version
marker, so video-extracted vault artifacts couldn't record which extraction iteration
produced them — and output depends on tunable knobs (`--fps`, `--threshold`, the 720p
download tier). A new `PIPELINE_VERSION` constant (starting at `0.7.0`, successor to the
pre-split monolith's ≈`0.6.0`) is stamped into the vault DB row
(`structured_data.video_extraction.pipeline_version`) and the output PDF's
producer/creator metadata. A `--version` flag prints `{"pipeline_version": "<version>"}`
(JSON, queryable without the extraction dependencies installed). The dependency import was
deferred so the version/help paths answer in a minimal environment. The
`structured_data.video_extraction` record also gains a `schema_version` (record-shape
version, distinct from the behavior-tracking `pipeline_version`) with a documented
reader/default contract for legacy entries. `references/video-slide-extraction.md`
documents a bump-on-behavior-change policy and `references/schemas-db.md` records both
fields and the reader contract. Resolves #103.

## 0.18.38 — 2026-06-19

### fix(illustrations) — masked/composited build edits keep static backgrounds pixel-stable

Backward-chaining progressive-reveal builds (`--build`) sent the whole frame to the image
model with only a text prompt and no mask, so the model was free to redraw everything: a
static background that must stay fixed across the reveal (a conveyor, a baseplate, a panel
frame, blueprint chrome) drifted in position/size or silently lost elements between frames —
even when the `erase` prompt named them in a `Keep` clause. A `Keep` clause reduces drift
but a maskless edit cannot guarantee the kept pixels survive. Build steps now take an
optional `erase_region` — a normalized `[x0, y0, x1, y1]` box (0..1, origin top-left, schema
validated) around the element being erased. When set, `--build` confines the edit to that
box: OpenAI receives a real edit mask (only the transparent box is regenerated), and for
both vendors the returned image is composited back over the prior frame via Pillow so every
pixel outside the box is the source pixel exactly. The box is still redrawn by the model
(the erased area shows real background, not a flat fill). Without a region the historical
whole-frame regeneration is unchanged, so existing outlines need no edits. Pillow (already a
project dependency) is imported lazily only when a region is used. `Build.erase_region` is
added to the outline schema; `rules/illustration-rules.md` and
`skills/illustrations/references/builds.md` document when and how to use it. Resolves #90.

## 0.18.37 — 2026-06-19

### fix(illustrations) — style-anchor `conventions` reach every generation prompt

`style_anchor.conventions` is a required field where `strategy.md` Step 9 tells authors
to bake the deck-wide, generation-relevant style rules (palette constraints like strict
grayscale, sequential numbering, recurring motifs). But `generate-illustrations.py`'s
`parse_outline` only read `style_anchor.full`/`imgtxt` — it validated `conventions` via the
schema and then threw it away, so those load-bearing rules never reached the image model.
A deck whose `conventions` said "no sepia / no warm tint" still drifted sepia because the
rule, though it "existed" in the outline, was never sent. `parse_outline` now folds the
collapsed `conventions` into every per-format anchor (the `[STYLE ANCHOR]` token expands to
"<format anchor> <conventions>") and surfaces the raw text under a new `conventions` key;
an empty `conventions` appends no stray separator. Resolves #83.

### fix(illustrations) — style anchor stays style-only; compose-only guard blocks furniture leak

The style anchor is injected into every slide's prompt, so anything in it renders on every
slide — yet nothing enforced that the anchor was *style-only*, and *Style-Anchor Discipline*
pushed the other way ("be specific, don't prune"). For document-style aesthetics (instruction
booklet, blueprint, newspaper), the page furniture — parts inventories, step strips, numbered
stations, exploded diagrams — reads like a style convention but is per-slide content, so the
whole deck's furniture cross-contaminated every slide (the title slide became "the entire deck
on one image"). `generate-illustrations.py` now appends a `COMPOSE ONLY THE SCENE` directive to
every fresh-generation prompt (generate / style-explore / compare — not erase-only edits),
pinning the model to the per-slide scene and barring instruction-page furniture and
other-slide elements. `rules/illustration-rules.md` (*Style-Anchor Discipline*) and
`strategy.md` Step 9 are rewritten to mandate a style-only anchor and reconcile "append, don't
prune" by axis: prune smuggled-in content, preserve and extend style specificity. Resolves #87.

## 0.18.36 — 2026-06-19

### fix(illustrations) — secrets.json read no longer hangs on a cloud placeholder

`load_secrets()` read `{vault}/secrets.json` with a plain `json.load(open(path))`. When that
file is a cloud-synced (e.g. iCloud) "dataless" placeholder — listed in the directory but
with its bytes evicted to the cloud — the read syscall blocks indefinitely while the OS
tries to materialize it. If the cloud is unreachable, the call never returns, freezing every
generate/build/edit run (and the test suite) before any work starts; `os.path.isfile()`
returns instantly because the metadata is local, so the guard didn't help. The read now runs
on a daemon thread with a bounded `SECRETS_READ_TIMEOUT` (10s); on overrun it raises
TimeoutError and `load_secrets` falls back to the existing `GEMINI_API_KEY` / `OPENAI_API_KEY`
env-var path with a loud stderr warning — the same degrade-don't-crash behavior it already had
for malformed/unreadable files (no silent swallow). Found while working on the build-edit fix.

## 0.18.35 — 2026-06-18

### fix(vault-ingress) — Step 4 persists structured fields deterministically

vault-ingress Step 4 told the orchestrator to hand-copy each subagent field into the
tracking DB, so anything it forgot was silently dropped: the rich `structured_data` the
subagents compute reached the per-talk analysis files but almost never landed in
`tracking-database.json` (1/196 talks had `slide_count`, `opening_type`,
`narrative_arc_type`, etc.). New `scripts/persist-results.py` removes the human from the
merge loop — it deep-merges the full `structured_data`/`verbatim_examples` blocks
(additive, so re-runs refine rather than wipe), normalizes `pattern_observations` into the
DB shape while keeping the detailed arrays Section 15 reads, and promotes the declared
queryable scalars (`slide_count`, `slide_design_style`, `illustration_style`,
`opening_type`, `closing_type`, `narrative_arc_type`, `audience_interaction_count`,
`co_presenter`, `delivery_language`, `pattern_score`) to each talk's top level. Fails
visibly on a filename mismatch instead of skipping. Step 4, `processing-rules.md`, and the
`schemas-db.md` talk entry are updated to the deterministic-merge contract. Resolves #97.

### feat(vault-ingress) — Step 9 hands off into clarification for same-week talks

vault-ingress Step 9 only *recommended* running `vault-clarification` for a freshly-ingested
talk delivered in the past 7 days — too weak for the case where it matters most, since
clarification quality decays fast and a recommendation buried at the end of a long ingress
report is easy to skip. Step 9 now tiers the handoff by recency: a talk delivered within
the past 7 days gets an explicit inline offer (via `AskUserQuestion`) to run
`vault-clarification` immediately, pre-seeded with the candidate topics Step 9 already
computes (per-talk `areas_for_improvement` and low-confidence/unverifiable
`pattern_observations`); on acceptance it invokes the skill carrying that seed agenda. The
7–30 day (full session) and 30+ day (compressed session) windows stay recommend-only.
Resolves #98.

## 0.18.34 — 2026-06-15

### fix(illustrations) — migrate image-gen model ids to GA, pin OpenAI snapshot

Google deprecates the `-preview` Gemini image ids on 2026-06-25. The registry's canonical
ids move to the GA strings (`gemini-3-pro-image`, `gemini-3.1-flash-image`); the `-preview`
ids are demoted to aliases so baked outlines still resolve. OpenAI's canonical id is
snapshot-pinned to `gpt-image-2-2026-04-21` (rolling `gpt-image-2` kept as an alias) for
reproducible illustration style; both confirmed live against the API. `GEMINI_API_BASE` /
`OPENAI_API_BASE` are hoisted into `model_registry.py` as the single source of truth — they
were duplicated across `generate-illustrations.py` and `generate-thumbnail.py`, whose own
`DEFAULT_MODEL` also moves to the GA id. The Gemini base stays on `v1beta`: verified live
that `gemini-3-pro-image` (the default) is served only on `v1beta` and 404s on `v1`. Rule
prose, the candidates-schema reference, and the illustration eval fixtures are updated to
the GA ids. Resolves #94.

## 0.18.32 — 2026-06-12

### fix(security) — drop suspicious download-URL examples from skill instructions

Removes the `bit.ly` shortener and concrete Google Drive / YouTube example URLs from
skill instructions. They tripped the tessl moderation **E005 "suspicious download URL"**
gate (Critical, install-blocking), which had held the public-install gate closed. The
flagged URLs predate this change; the examples are now generic placeholders or plain
descriptions — an agent infers URL shape without a literal sample. Functional download
commands (`gdown`, `yt-dlp`) and the speaker's real shownotes domain are unchanged.

## 0.18.31 — 2026-06-12

### feat(vault) — define the self-improvement outcomes of talk ingress

Turns three previously under-specified coaching surfaces into a coherent
three-level subsystem keyed on one definition: **adherence = consistency with the
speaker's own established style baseline**.

- **`adherence_assessment` is now defined** (`vault-ingress/references/processing-rules.md`).
  Previously a bare one-liner ("after 10+ talks, start providing adherence
  assessments") with no statement of adherence *to what*. Now a gated 2–4 sentence
  judgment with three ordered checks (pattern adherence, intent adherence,
  departure classification) and required anchors: cite this talk's `pattern_score`
  vs. the running average and name any recurring antipattern that reappeared.
- **Rhetoric-summary Section 15 now has a schema.** Previously "Section 15
  aggregates improvement areas" with no structure. Now five required subsections —
  recurring improvement themes (each tagged with antipattern ID + severity + talk
  count), the pattern-score + breadth baseline, signature patterns, underused
  patterns (growth), and resolved issues — making Section 15 the explicit baseline
  per-talk adherence measures against. Section 16 (speaker-confirmed intent)
  boundary documented.
- **Declining pattern scores are now attributed, not just flagged.** Adds
  `pattern_profile.score_drivers` to the speaker profile: a `declining` `score_trend`
  must name its causes. Attribution is **symmetric** — a decline comes from either
  bad things present (antipatterns rising) or good things absent (patterns fading /
  pattern range narrowing), and underuse alone can lower the score with zero
  antipatterns. vault-profile Step 4 computes it; Step 6 surfaces shifts in the diff.
- **Pattern underuse is now a first-class signal, not only antipatterns.** Adds
  `pattern_profile.pattern_breadth` (avg distinct patterns per talk + widening/stable/
  narrowing trend) to isolate "using enough of your toolkit" from antipattern
  avoidance, and `pattern_profile.underused_patterns` (never/rarely-used observable
  patterns that fit the speaker's modes) as positive-space coaching. Section 15 gains
  a "Underused patterns (growth)" subsection and a breadth line; Dimension 14 and the
  adherence pattern-check both treat underuse as a legitimate finding. Framed as range
  and fit, explicitly **not** count-maximization — cramming patterns is its own
  antipattern.
- Dimension 14 (`rhetoric-dimensions.md`) now asks each improvement issue to name
  its related antipattern ID + severity where one applies — the per-issue tagging
  that feeds both Section 15 aggregation and profile decline attribution.

Four additions turn the diagnostics into an actual coaching loop:

- **Closed the loop — improvement goals + verification.** New `improvement_goals`
  artifact in the tracking DB (owner: vault-clarification; reader/updater:
  vault-ingress, verification fields only; per-record `schema_version`). The speaker
  picks 1–2 focus areas from Section 15 (new clarification Step 6); a later ingress
  run (new Step 8) checks each against the fresh baseline and sets
  `achieved|improving|stalled|regressed`. The system now verifies the speaker acted,
  not just diagnoses. Schema in vault-clarification `schemas-config.md`; verification
  rubric in vault-ingress `processing-rules.md`.
- **Mode-relative baselines.** Adds `pattern_profile.by_mode` (per-mode score,
  breadth, top antipatterns; `stable` at ≥3 talks). Adherence and underuse now compare
  a talk to ITS mode's baseline when stable, else global — a lightning talk no longer
  reads as "underusing audience interaction" against a keynote yardstick.
- **Strengths reinforcement.** Adds `pattern_profile.strengths` (signature patterns +
  combinations with a `lean_in` line) and reframes Section 15's signature-patterns
  subsection as "lean in / double down" — the positive counterpart to recurring
  issues, distinct from celebratory badges.
- **Pacing/time adherence.** Adds `pacing.adherence` (talks over slide-budget, rate,
  trend, worst offenders), computed in vault-profile Step 4 from `slide_count` ÷
  `talk_duration_estimate` vs `slide_budgets`. The quantitative counterpart to
  Dimension 14's qualitative "rushing" read; marginal overages flagged softly
  (duration is only transcript-estimated).

## 0.18.30 — 2026-06-11

### feat(illustrations) — FULL-bleed composition as a first-class choice + `text_treatment` anchor field

Makes the poster-theatrical (full-bleed) path a deliberate, asked-for choice and
fixes baked-text drift between slides. Step 5 now asks the speaker — never infers —
how titles + footers render: **Bleed** (baked into each image, stylized to the
art, FULL-only, not editable; the noir reference deck) or **Overlay** (PowerPoint
text over a safe zone, editable, uniform font). Choosing Bleed sets
`style_anchor.composition: poster-theatrical` and locks every illustrated slide
to FULL (EXCEPTION/screenshot slides without an `image_prompt` are exempt).

Adds `style_anchor.text_treatment` — the per-deck rendering directive for baked
title + footer (e.g. "glowing hand-script neon on an in-scene surface"). It lives
on the anchor and is applied to every illustrated slide's baked text, so
titles/footers render identically; previously the model picked a treatment per
call and they drifted.

Codifies the anchor-vs-per-slide split: the anchor owns the style,
`text_treatment`, and the full `embedded_footer` (everything that must stay
consistent); the per-slide `image_prompt` carries only the scene and `text_overlay`
carries only that slide's literal title string. Also completes the outline.yaml
migration across all loaded context: stale markdown-format guidance in
`presentation-creator/SKILL.md` (incl. the obsolete "illustrations expects
markdown-style inputs" note), `phase2-architecture.md`, `generate-illustrations.py`
runtime messages, `generate-thumbnail.py`, `title-overlay-rules.md` §0,
`thumbnail-generation-rules.md`, and `resources-gathering-rules.md` now name the
`style_anchor.*` YAML fields. The `test_outline_source_is_yaml.py` contract test
scans skill prose + `rules/` (not just scripts) and fails on either a phantom
`presentation-outline.md` reference or the legacy markdown bold-field syntax
(`**Composition:**` / `**Embedded footer:**`) anywhere in loaded context.

## 0.18.29 — 2026-06-11

### fix(illustrations) — read outline.yaml, not a phantom presentation-outline.md

The three outline-consuming illustration scripts (`generate-illustrations.py`,
`apply-illustrations-to-deck.py`, `build-expansion-manifest.py`) regex-parsed a
`presentation-outline.md` that nothing in the toolkit generates — `outline.yaml`
is the single source of truth, and the model was left guessing how to hand-author
the markdown. All three now load `outline.yaml` through the shared
`outline_schema` loader (the partial view, so they work in Phase 2 before the deck
is complete). A new deterministic contract test
(`tests/test_outline_source_is_yaml.py`) discovers every outline-consuming script
and fails if any declares a `.md` outline argument, skips the shared loader, or
references the phantom file.

The schema gained the illustration-layer fields that previously lived only in the
hand-authored markdown: `style_anchor.composition` + `style_anchor.embedded_footer`
(deck-wide), per-slide `safe_zone` (zone + surface), and per-build `erase`. `erase`
carries the backwards-chaining edit prompt with its mandatory "Keep ..." clauses,
while the additive `desc` stays the human-facing reveal in `slides.md` — resolving
the long-standing mismatch where the generator expected erase prompts but the
authoring contract produced additive ones. `build-expansion-manifest.py` dropped
its now-redundant count/contiguity guards (the schema enforces contiguous-from-0
build steps at load).

### fix(presentation-creator) — fully prompt-free deck builds (stage all macro I/O through the container)

Extends the per-illustration container-staging to ALL macro file I/O. Sandboxed
PowerPoint also prompts (Powerbox) when a macro opens a Google-Drive base deck or
template, and when it saves output to a local `~/.deckops-staging` subdir (a
per-run `build.XXXXXX` dir prompts every run; a Drive folder E_FAILs). A new shared
`container-stage.sh` (sourced by every deck-ops wrapper) provides `stage_base` to
copy base decks / templates / the QR image into the container and open them from
there, and an `OUT_STAGE_DIR` inside the container for `SaveCopyAs`; the shell then
moves the result to the Drive destination. One EXIT trap in the helper owns
cleanup — `build-deck.sh` previously set its own trap that overrode the image-stage
cleanup and leaked staged copies; that's resolved. A full build now runs with zero
Powerbox prompts and no Full Disk Access grant. Validated end-to-end: BuildDeck +
ApplyBackgrounds, 46 slides, ~0.8s each (no blocking prompts), staging auto-cleaned.

### fix(presentation-creator) — BuildDeck now compiles and runs on Mac PowerPoint

Two Mac-only `BuildDeck` bugs, caught by a from-scratch deck validation (`BuildDeck`
had never actually run on macOS):
- `Shapes.AddChart2` is Windows-only; on Mac it raises a VBA compile error
  ("method or data member not found") that — under Compile-On-Demand — only
  surfaced when `BuildDeck` was first invoked, blocking the whole module. The chart
  path is now late-bound (`Object`), so the module compiles on Mac; `CHART` ops
  (never emitted by real decks) only error at runtime if actually used.
- `BuildDeck` stripped the template's slides before reading
  `SlideMaster.CustomLayouts`, and Mac PowerPoint prunes the now-unused layouts →
  every SLIDE op failed "layout index out of range (0 custom layouts)". It now reads
  the layouts while the slides exist and deletes the demo slides last (the
  `RunDeckOps` append-then-delete pattern), keeping layouts referenced throughout.

Validated end-to-end against a freshly-seeded `DeckOps.pptm`: `BuildDeck` built 46
slides from the talk's deck-ops, then `ApplyBackgrounds` applied all 46 illustration
backgrounds — a clean 38 MB deck.

### fix(presentation-creator) — restore deck drivers stripped by tessl install (#85)

`tessl install` materializes only `.md/.py/.json/.sh/.txt` and STRIPS
`.bas`/`.applescript`, so on every installed tile `RunDeckOps.bas` and the eight
`.applescript` drivers were missing — the whole PowerPoint deck layer was dead
(the `.sh` wrappers call `.applescript` drivers that call `RunDeckOps.bas`
macros). Verified empirically: `tessl plugin pack` includes them, `tessl install`
does not. Each driver now ships a byte-identical committed `.txt` mirror (which
survives install); `sync-deck-drivers.py` recreates the real files from the
mirrors (`materialize`), keeps mirrors in sync with the source drivers (`mirror`),
and a `check` mode guards drift in CI. `ensure-drivers.sh`, sourced by every
deck-ops wrapper, self-restores the `.applescript` drivers on first run; the
guided setup restores `RunDeckOps.bas` for the one-time VBE import. The `.txt`
mirrors are marked `linguist-generated` in `.gitattributes`; a unit test asserts
they stay byte-identical to the real drivers.

### docs(presentation-creator) — recurring per-build deck-editing runbook

`deck-editing-setup.md` covered one-time setup but only implied the recurring
requirement that `DeckOps.pptm` stay OPEN for the whole build (every pass calls a
macro in that running instance). A new "Step 6 — Every build (recurring)" makes it
explicit and lays out the pass sequence (structural build → ExpandBuilds → notes →
backgrounds → QR) and the PowerPoint+Keynote validation. `phase5-slides.md` now
surfaces the keep-open requirement on every build, not just first use.

### fix(presentation-creator) — collapse per-illustration Powerbox prompts to zero

Sandboxed PowerPoint threw a "grant access / select file" Powerbox prompt on
every `Slide.Background.Fill.UserPicture` of an image outside its container (each
Google Drive illustration) — one click per slide on a 40-slide deck. A new
`stage-images-into-container.py` copies the referenced images into PowerPoint's
own sandbox container (`~/Library/Containers/com.microsoft.Powerpoint/Data/.deckops-img-staging/`)
and rewrites the manifest paths; `apply-backgrounds.sh` and `expand-builds.sh`
stage before packing and clean up after the deck is written. A sandboxed app
reads its own container without a prompt, so prompts collapse to zero with no
Full Disk Access grant. Mac PowerPoint VBA has no `Application.FileDialog`, so a
"grant one folder" macro is impossible — container-staging is the supported
no-prompt path; if the container is absent the wrappers warn and fall back to the
original paths. The stager is unit-tested across both manifest shapes.

### fix(presentation-creator) — deck-build AppleScript drivers time out on large decks (#85)

The `run VB macro` call in every PowerPoint driver used osascript's default
~120s AppleEvent window, so a large build (e.g. a 46-slide `BuildDeck`) died with
`AppleEvent timed out (-1712)`. All eight drivers — including the new
`expand-builds.applescript` — now wrap the macro call in `with timeout of 1800
seconds`. (Issue #85 also reports the installed tile missing the `.applescript` /
`.bas` files and a `BuildDeck` `-18` on all-BLANK sequences: the dev tree packs
all drivers + `RunDeckOps.bas` — verified via `tessl plugin pack` — so the
published gap is being re-verified on the next publish; the `BuildDeck -18`
robustness fix is tracked separately in #85.)

### feat(illustrations,presentation-creator) — progressive-reveal build expansion in the deck

The toolkit generated build frames (`--build`) but never assembled them into the
deck — `builds.md`'s "Deck Insertion" was unimplemented. A new `ExpandBuilds` VBA
pass (`RunDeckOps.bas`) replaces each progressive-reveal parent slide with its
build frames as full-bleed background-fill slides (speaker notes on the final
frame only), via real PowerPoint slide insertion — structural edits never use
python-pptx (`rules/deck-editing-rules.md`). `build-expansion-manifest.py` emits
the plan from the outline + generated frames; `build-expansion-to-packed.py`
packs it into the wire format descending by parent; `expand-builds.sh` drives the
macro. Run it before the by-index passes (notes/backgrounds/QR), which must key
on the post-expansion deck since expansion renumbers later slides. The Python
emitter + packer are unit-tested; the VBA pass is validated by opening a built
deck (per the macOS VBA-untestable-in-CI rule).

### feat(illustrations) — poster-theatrical composition

A deck-level composition choice, decided in the style wizard and baked into the
STYLE ANCHOR header (`**Composition:** poster-theatrical` + `**Embedded footer:**`).
In this mode every slide is full-bleed and the title + footer are rendered INTO
the image — stylized and blended in the deck's own vocabulary — instead of
overlaid afterward. Generation appends an `EMBEDDED TEXT` directive (folding the
slide's `Text:` and the deck footer into the prompt) and skips the `TITLE SAFE
ZONE` directive entirely; apply records poster FULL slides as background-only (no
scrim, no overlaid title); deck-build omits the `TITLE`/`FOOTER` ops for those
slides. The QR code is the only shape inserted after generation. `title-overlay-rules.md`
§0 documents the opt-out. Small dense footer text (handles/hashtags/URLs) may be
approximated by the model and need a re-roll or `--edit` touch-up.

### feat(illustrations) — idea-sourcing wizard + render-before-bake gate

Style strategy (SKILL.md Step 3) was a single prose step bundling six sub-actions
with no enforcement, while the freshness gate (Step 2) was script-backed with a
"never skip silently" verdict. An agent shortcut the unenforced collaboration: it
ran the freshness check and `--shortlist`, then reasoned a model into the STYLE
ANCHOR and skipped both the priorities question and the exploration-grid render —
the speaker never saw a sample. Step 3 is now seven flat gated steps (source ideas
→ priorities → format → shortlist → propose → render grid → bake + verify). The
render writes a `style-explore/rendered.json` manifest of what actually rendered;
a new `generate-illustrations.py --check-style-explore` verdict and a guard inside
`run_generate` refuse generation unless the baked model was rendered in the grid,
turning "did a human pick from real samples?" into a deterministic tripwire. The
collaboration also became an explicit multi-select idea-sourcing wizard (your
usual / mode-or-series match / new / wild / trending / bring-your-own) with a
Quick-default fast path that still renders and shows. Shared wizard shape:
`skills/presentation-creator/references/idea-sourcing-wizard.md`.

### feat(presentation-creator) — explicit engine & theme sourcing (Phase 2 Decision #2)

Deck tooling (PowerPoint/pptx vs presenterm terminal-markdown) was decided
implicitly — inferred at Phase 5 with no record on the outline — so a demo-centric
talk that should run in a terminal tool could silently become a slide deck. A new
Phase 2 decision (#2, right after Mode) sources the engine via the shared
idea-sourcing wizard, reading an optional `presentation_engines[]` roster and the
chosen mode's `typical_engine`, and records `talk.engine` / `talk.deck_theme` /
`talk.engine_source` on the outline. Phase 5 now branches on `talk.engine` instead
of inferring; a null engine on a legacy outline falls back to inference with
author confirmation. Theme stays a thin provenance pointer — no named-theme
registry. New profile fields are optional/additive (no schema_version bump), so
existing profiles and outlines still validate. The Phase 2 decisions renumber
(Pattern Strategy #10→#11, Illustration Strategy #11→#12).

## 0.18.26 — 2026-06-09

### fix(qr-generation) — recreate legacy non-slug links; capture the custom-domain decision (#56)

Follow-up to the QR shortlink work shipped via #79, which enforced the slug-only
back-half for newly-created links but left two gaps.

- Slug-only back-half now applies to EXISTING tracked links too: a cached entry
  whose back-half isn't the slug is no longer reused or retargeted in place — it's
  recreated with the slug back-half (regression-tested).
- First short link captures the custom-domain decision: before creating a NEW
  shortened link, an absent `publishing_process.qr_code.{shortener}_domain` key
  STOPS so the agent asks the user and saves the answer — the domain, or `null`
  for "no custom domain" — so a configured custom domain is never silently
  skipped. Absent = never asked; `null` = decided (default domain), never
  re-asked. The MCP path makes the same check.
- Documented the `bitly_domain` knob in the profile schema (the code and the
  clarification flow already used it). `rules/qr-generation-rules.md` §2 (the
  custom domain must be used when configured) and new §7 (the three-state
  decision); phase6-publishing and the clarification prompts save an explicit
  `null`.

## 0.18.25 — 2026-06-08

### fix(illustrations) — --build enforces the Keep-clause preservation list (#46)

`--build` previously passed each `build-NN` description to the image editor
verbatim, auto-appending only safety clauses #1/#2; the mandatory preservation
list (component #3 of Edit Prompt Safety) was never applied, so a step that
erases a dense region left the element in place and the chain emitted visually
identical intermediate stages. The build flow now validates that every erase
step carries an explicit `Keep` clause and skips the slide with a stderr error
and a non-zero exit when one is missing — instead of silently producing a broken
chain. Build step descriptions must be authored as erase instructions with
`Keep` clauses (see `skills/illustrations/references/builds.md`).

## 0.18.24 — 2026-06-08

### feat(presentation-creator) — narrative.md becomes a TL;DR + slide-by-slide walk (#81)

`narrative.md` used to print the full `talk.thesis` (in practice 3–4 elaborated
paragraphs) and then the chapter `argument_beats` as prose with `*[slide N]*`
markers. The two sections stated the same argument at different granularities, so
the breakdown read as the thesis chopped into slide-tagged chunks — a reader saw
the whole argument twice. The narrative is also the only artifact that gives "the
idea + what's on each slide" in plain prose: `slides.md` is technical generation
input and `script.md` is the spoken words.

- New optional `talk.tldr` field on the outline schema: a short distillation of
  `thesis` (a couple of paragraphs or a bulleted list), authored by the agent.
  `narrative.md` renders it verbatim under `## TL;DR` and never reprints the
  elaborated `thesis`.
- Full `narrative.md` (slides authored) is now a one-line-per-slide walk grouped
  by chapter — `**N. Title** — synopsis`, 1:1 with `slides[]`, with live-demo
  interludes inlined at their anchor. The per-slide synopsis prefers
  `text_overlay`, falling back to the slide's `visual`.
- Partial `narrative.md` (Phases 1–2, no slides yet) keeps the chapter +
  argument-beat scaffold so the author still reviews the arc before slides exist.
- SKILL.md + phase3-content.md document the `tldr` field and the partial-vs-full
  rendering split.

`narrative.md` (the partial narrative scaffold) can now be generated and
reviewed before any slide exists. Previously
`extract-narrative.py` called `load_outline()`, which runs the full `Outline`
schema — `slides[]` (min 1), the `big_idea` singleton, paired callbacks, and
slide-budget math — so the human-readable narrative could not appear until Phase 3,
after slide content development had already begun. The narrative itself is fully
authored by the end of Phase 2, so the author had no readable artifact to approve
at the point the argument was actually being shaped.

- New `PartialOutline` model + `load_outline_partial()` in `outline_schema.py`
  validate `talk` (+ optional `chapters`) without the slide-dependent
  cross-validators. The full `Outline` stays the Phase 3+ source-of-truth contract.
- `extract-narrative.py --partial` renders from the partial view and emits a
  "narrative arc not yet authored" note when chapters are absent.
- SKILL.md: Phase 1 emits a partial stub; Phase 2 regenerates the full
  narrative and the gate now requires author approval of narrative + architecture
  before Phase 3. The plain (full-validation) extractor path is unchanged from
  Phase 3 onward.

## 0.18.23 — 2026-06-08

### fix(qr-generation) — replace inherited QRs in place; back-half always the slug (#56)

On a deck adapted (trimmed) from another talk, the QR step added a second QR
instead of replacing the inherited one, and only targeted the configured slide —
leaving stale QRs on earlier slides (e.g. an early shownotes slide). Now every
QR-bearing slide is detected and its QR replaced in place.

- `generate-qr.py`: QRs are detected by CONTENT, not size — `find_qr_rects`
  flags a square picture that is both ~2-color and roughly balanced between those
  colors, so it catches an inherited QR at any size (the same QR appeared at 1.8"
  and 2.8" in the repro deck) while excluding colored diagrams and mostly-one-color
  text screenshots. `resolve_target_slide_indices` targets every QR-bearing slide
  in addition to the configured placement.
- `RunDeckOps.bas` `InsertQR`: the macro can't run image libraries, so detection
  stays in Python; it now receives each slide's existing-QR geometry and just
  removes those exact shapes and places the QR there (same position/size, cleaning
  up duplicates). New placements still go bottom-right.
- The shortener back-half is now ALWAYS the talk slug — bit.ly custom back-half
  and rebrand.ly slashtag — dropping the `preferred_short_path` override (removed
  from the profile schema). If bit.ly can't set the slug back-half, the create now
  fails (degrading to the raw URL) rather than silently keeping a random hash.
  Documented in `rules/qr-generation-rules.md`.
- Bug 2 (fetch colored QRs from Bitly to drop the local `qrcode` dep) is
  won't-fix: the dependency can't be dropped (rebrandly / `none` / `--png-only`
  paths render locally), and the one-call QR-codes endpoint abandons the managed
  bitlink model (custom domain, PATCH-able target, tracking).
- macOS + PowerPoint only for the `InsertQR` change; untestable in Linux CI by
  design. The QR-detection, slide-targeting, and back-half logic IS unit-tested.

## 0.18.22 — 2026-06-07

### fix(shownotes-publisher) — content-only gate decides direct-push vs branch+PR

Step 9 runs `skills/shownotes-publisher/scripts/content-only-gate.sh` against the
shownotes repo before publishing. When every pending change touches only the
declared content globs, the skill direct-pushes to `main`; any out-of-glob path,
or an indeterminate state, falls back to branch + PR. This is the Form B
client-side gate that `jbaruch/coding-policy: ci-safety`'s Content-Only
Direct-Push Carve-Out permits where server-side allowlist enforcement is not
expressible on a github.com personal repo (coding-policy#119, shipped in
coding-policy 0.3.52). The carve-out's precondition 1 is satisfied by a new
authority-of-record steering rule, `rules/shownotes-content-publish.md`, naming
the covered globs, the gate script, and the review the direct-push skips. Fixes #65.

## 0.18.20 — 2026-06-07

### fix(qr-generation) — compose date-less talk slugs (QR + Phase 1) (#55)

Completes the date-less-slug convention. #66 made the publisher consume
`talk.slug` verbatim (date-less filename and URL); this drops the date prefix
from how slugs are *composed*, so the QR back-half and the Phase 1 slug match the
published page instead of pointing at a stale `YYYY-MM-DD`-prefixed back-half.

- `rules/qr-generation-rules.md` §4: the QR back-half IS `talk.slug`, composed in
  Phase 1 (per the speaker's `slug_convention.template`) and used VERBATIM — no
  invent / rephrase / re-derive / date-prefix. Replaces the old
  `{YYYY-MM-DD}-{conference-slug}-{talk-short-name}` format and removes the
  self-contradictory derive-from-delivery-date guidance. §2 example date-less.
- `rules/interaction-rules.md` and
  `skills/presentation-creator/references/phase1-intent.md`: the Phase 1
  slug-confirmation examples are now date-less (`jcon26-robocoders`).
- QR eval scenarios (`qr-bitly-slug-from-outline`,
  `qr-missing-shortener-detection`): fixtures + criteria updated to a date-less
  slug, in a synthetic namespace (`froconf26-cache-stampedes`) distinct from the
  `devnexus`/`robocoders` examples used in skill/rule context (no fixture/example
  bleeding).
- `generate-qr.py` needed no change — it already uses the passed `--talk-slug`
  verbatim as the custom back-half.
- Left intentionally: `url.template` date variables (URL *assembly*, configurable
  per deployed site — tracked in #17), and legacy date-prefixed filenames already
  published (the publisher's never-rename guard) or ingested into the vault.

## 0.18.16 — 2026-06-07

### fix(shownotes-publisher) — use talk.slug as the filename, drop the date prefix

`talk.slug` from `outline.yaml` is now the single source of truth for a new
talk's `_talks/` filename and live URL: the filename is always `{talk_slug}.md`,
never `{YYYY-MM-DD}-{talk_slug}.md`. The old `delivery_date`-conditional branch
overrode the speaker's chosen slug with a date-prefixed name, so the published
URL diverged from the slides + QR (which point at the bare slug) — it had to be
renamed by hand and the Bitly QR repointed. The downstream `{filename_stem}`
indirection is replaced by `{talk_page_stem}` — `{talk_slug}` for new talks, the
existing date-prefixed stem when updating a legacy page — so the
never-rename-a-published-file guard holds without duplicating legacy talks.
Fixes #66.

## 0.18.15 — 2026-06-07

### feat(presentation-creator) — whole-deck creation via real PowerPoint (#57 Phase D)

Retires the last python-pptx + MCP-PPT-server deck-writing path. Slide structure
was created by stripping the template with `strip-template.py` (python-pptx) and
then walking the deck through the MCP PPT server (`add_slide` /
`populate_placeholder` / `add_bullet_points` / `manage_image` / `manage_text` /
`add_shape` / `optimize_slide_text`). Both are gone — `BuildDeck` creates the
whole deck in the real PowerPoint app, so the engine that ships valid,
Keynote-openable `.pptx` is now the sole writer for creation as well as edits.
Completes #57: real PowerPoint is the sole `.pptx` engine.

- **`BuildDeck`** (in `RunDeckOps.bas`) — opens a uniquely-named template copy,
  deletes the template's demo slides (subsumes `strip-template.py`), and executes
  a flat op sequence: `SLIDE` / `TITLE` / `SUBTITLE` / `BODY` / `BULLET` / `TEXT`
  / `IMAGE` / `SHAPE` / `BG` / `FOOTER` / `OPTIMIZE` / `TABLE` / `CELL` / `CHART`
  / `CAT` / `SERIES` — full parity with the retired MCP surface, in one module
  (VBA has no package manager; the macros share private helpers). When a layout
  lacks the requested title/subtitle/body placeholder, `BuildDeck` preserves the
  op's content in a fallback text box rather than dropping it silently.
- **`build-deck.sh` / `build-deck.applescript`** — wrapper + driver. The
  AppleScript reads the ops file as UTF-8 and passes it as one Unicode arg (no
  VBA-side decoding); the wrapper validates first, stages locally, then moves the
  output into place (sandboxed PowerPoint can't write to a Google Drive folder).
- **`validate-deckops.py`** — deterministic, unit-tested
  (`tests/test_validate_deckops.py`) op-sequence validator (UTF-8): op vocabulary,
  arity, int/float fields, BG 0–255, non-negative layout index, and state rules
  (ops need a prior `SLIDE`; `CELL` needs a `TABLE`; `CAT`/`SERIES` need a `CHART`;
  `SERIES` needs ≥1 value; a `CHART` needs ≥1 `SERIES` so it never ships
  PowerPoint's default sample data). `BuildDeck` raises a clear error on an
  out-of-range layout index rather than silently remapping it. The
  PowerPoint-driving layer stays manually validated.
- **`references/deckops-spec.md`** — the op-sequence spec (delimiter, fields,
  state rules, enum values, build-then-assemble for fragments).
- **Removed `strip-template.py` and `_pptx_repair.py`** (and `test_strip_template.py`
  + the `strip_template` / `pptx_repair` conftest fixtures) — `_pptx_repair.py`'s
  only consumer was `strip-template.py`.
- Rewired `SKILL.md` Step 5 and `phase5-slides.md` from the MCP walk to
  emit-ops → `validate-deckops.py` → `build-deck.sh`; the MCP tool quick-reference
  table is now a deck-op quick-reference. `slide-generation-rules.md` reconciled to
  BuildDeck (not python-pptx, not MCP); the stale `_pptx_repair.py` / `generate-qr.py`
  Keynote-carve-out example and the obsolete python-pptx code snippets are dropped.
- macOS + PowerPoint only; untestable in Linux CI by design — validate by
  re-opening output in PowerPoint and Keynote. The untestable-VBA gap for #57 is
  owner-authorized (tracked in jbaruch/coding-policy#116).

## 0.18.13 — 2026-06-04

### feat(presentation-creator) — QR insertion via real PowerPoint (#57 Phase F)

Retires `generate-qr.py`'s python-pptx deck write (`insert_qr_on_slides` +
`_remove_existing_qr` + `prs.save`) for an `InsertQR` VBA macro. `generate-qr.py`
keeps everything else — URL/shortener resolve, per-slide background-color match
(read-only), target-slide finding, and QR PNG generation — and calls
`insert-qr.sh` for the write.

- **`InsertQR`** (in `RunDeckOps.bas`) + `insert-qr.applescript` / `insert-qr.sh`
  — places the QR bottom-right (2.0in, 0.3in margin) on the given 1-based slides,
  removing any existing corner QR first (idempotent re-runs).
- `generate-qr.py` threads the deck through uniquely-named intermediates (one
  `InsertQR` pass per color variant) and moves the result back; the python-pptx
  `Inches`/`Emu`/`RGBColor` imports and the QR-insert test are dropped.
- The QR insert is now macOS + PowerPoint only (the rest of `generate-qr.py`
  stays cross-platform). Completes #57's deck-writer retirement. Untestable in
  Linux CI by design — validate by re-opening in PowerPoint and Keynote.

## 0.18.12 — 2026-06-04

### feat(presentation-creator) — placeholder slides via real PowerPoint (#57 Phase E)

Retires `insert-placeholder-slides.py` (python-pptx) for a `MakePlaceholderSlide`
VBA macro driven through the real PowerPoint app.

- **`MakePlaceholderSlide`** (in `RunDeckOps.bas`) + `make-placeholder-slide.applescript`
  / `make-placeholder-slide.sh` — builds a loud yellow `[PLACEHOLDER]` slide (title
  auto-prefixed, optional subtitle) as a 1-slide deck sized to the base deck.
- Positioning uses the existing `run-deck-ops.sh` order string: Mac VBA's
  `Slide.MoveTo` raises E_INVALIDARG, so placeholders are built then assembled at
  their target slots via `InsertFromFile`, rather than inserted-and-moved.
- Advances #57 (real PowerPoint as the sole `.pptx` writer). macOS + PowerPoint
  only; untestable in Linux CI by design — validate by re-opening in PowerPoint
  and Keynote.

## 0.18.11 — 2026-06-04

### feat(presentation-creator) — speaker notes via real PowerPoint (#57 Phase C)

Retires `inject-speaker-notes.py` (python-pptx) in favor of a `SetSpeakerNotes`
VBA macro driven through the real PowerPoint app. PowerPoint serializes valid
notes OOXML — including the `<p:notesMasterIdLst>` element python-pptx omitted —
so the Keynote-compatibility patch the python path carried is no longer needed
(retiring the *cause* of the breakage, not a safety net).

- **`SetSpeakerNotes`** (in `RunDeckOps.bas`) + `inject-notes.applescript` /
  `inject-notes.sh` — sets per-slide notes via PowerPoint, writes a COPY.
- AppleScript reads the notes file as UTF-8 and passes it to the macro as one
  Unicode argument (control-char-delimited records), so VBA never decodes UTF-8
  from disk. Slide numbers convert 0-based (the JSON) → 1-based (PowerPoint).
- **`notes-to-packed.py`** — deterministic JSON→wire-format packer, unit-tested
  (`tests/test_notes_to_packed.py`); the VBA layer stays manually validated.
- Phase 5 / `phase5-slides.md` rewired: notes inject via `inject-notes.sh` after
  the illustrations apply pass and before the final `apply-backgrounds.sh` write.
- Advances #57 (real PowerPoint as the sole `.pptx` writer). macOS + PowerPoint
  only; untestable in Linux CI by design — validate by re-opening in PowerPoint
  and Keynote.

## 0.18.10 — 2026-06-03

### fix(shownotes-publisher) — stop agents skipping thumbnail generation

Step 6 (Thumbnail) was opt-out: it stated the page "renders fine without one"
(the `onerror` placeholder fallback), framed production as a vague conditional
hand-off to the illustrations skill, and ended "Proceed immediately to Step 7"
with no gate — so agents always skipped it and the talk card fell back to the
placeholder SVG. Step 6 is now an explicit decision: check the convention-path
file (`assets/images/thumbnails/{filename_stem}-thumbnail.png`); if absent,
either produce it via `Skill(illustrations)` when a source image is available,
or explicitly record it as deferred to Phase 7 (pre-talk publish with no
slides/video). Never a silent fall-through. Fixes #58.

## 0.18.9 — 2026-06-03

### feat(presentation-creator) — PowerPoint-native deck editing (preserves illustrated backgrounds)

Adds a non-corrupting way to make structural edits (delete / reorder /
cross-deck import) to an existing `.pptx`, driven by the real PowerPoint app
instead of python-pptx, and makes it the SOLE structural-edit path. Prompted by
a concrete failure: trimming a 128-slide, 51 MB illustrated deck with
python-pptx / clipboard paste flattened every slide whose full-bleed art is a
per-slide background fill — the output dropped to 6.2 MB with all backgrounds
gone (picture *shapes* survived, per-slide `<p:bg>` fills did not). The
InsertFromFile path recovered the same cut to 24 MB with backgrounds intact.

- **Removed `delete-slides.py` / `reorder-slides.py`** (and their tests +
  conftest fixtures) — python-pptx slide-delete / reorder strips per-slide
  background fills, so it is no longer offered for any deck. All structural
  edits route through RunDeckOps. `_pptx_repair.py` stays (used by
  `strip-template.py`). `phase5-slides.md`, `SKILL.md`, and the README script
  tree updated to match. Tracked in #57.
- **New steering rule (`rules/deck-editing-rules.md`)** — drive real PowerPoint
  for all structural edits; documents the Mac PowerPoint VBA landmines and how
  each is handled.
- **`RunDeckOps.bas`** — reusable VBA macro that rebuilds a deck via
  `Slides.InsertFromFile` (keep-source-formatting Reuse Slides) in a target
  order, with cross-deck import, global text replace, and a COPY-only save.
  Guards against the filename-collision trap and self-cleans on failure.
- **`run-deck-ops.applescript` + `run-deck-ops.sh`** — driver and wrapper; the
  wrapper stages locally then moves into place (sandboxed PowerPoint can't
  create files in a Google Drive File-Provider folder).
- **`MakeBgImageSlide` (+ `make-bg-slide.applescript` / `make-bg-slide.sh`)** —
  turn a generated illustration into a slide whose image is the BACKGROUND FILL
  (so the layout's halftone-dot overlay covers it, matching the other comic
  slides) by cloning a template slide, swapping its background, and retitling —
  a top-pasted picture would sit above the overlay. Produces a 1-slide deck to
  import via `run-deck-ops.sh`.
- **`ApplyBackgrounds` (+ `apply-backgrounds.applescript` / `apply-backgrounds.sh`)** —
  the creation-time counterpart: set FULL-slide illustration backgrounds in bulk
  via `Slide.Background.Fill.UserPicture`, run as the final write of the build.
  `apply-illustrations-to-deck.py` no longer inserts FULL-slide picture shapes —
  it records each FULL slide in a backgrounds manifest (`--backgrounds-out`) and
  applies only scrim + title; IMG+TXT keeps its left-column picture shape. Begins
  retiring python-pptx as a deck writer for creation (Phase B of #57). Phase 5
  reorders so the VBA background pass runs after speaker-note injection.
- **Policy-review hardening** — `rules/deck-editing-rules.md` gains `alwaysApply`
  frontmatter and sheds rationale prose; `references/deck-editing-setup.md` drops
  the pause-and-wait flow for continue-immediately; the wrappers emit actionable
  validation errors; and the deterministic manifest→spec step is extracted to a
  unit-tested `backgrounds-manifest-to-spec.py` (the VBA core stays CI-untestable
  by design).
- macOS + Microsoft PowerPoint only — drives the app via Automation, so it is
  untestable in Linux CI by design; validate output by re-opening in PowerPoint
  and Keynote. README steering-rules table and `tile.json` steering updated.
- Full retirement of MCP + python-pptx as deck writers (real PowerPoint becomes
  the sole `.pptx` engine) is tracked in #57 with a phased plan.

## 0.18.7 — 2026-06-03

### feat(illustrations) — structured style selection + model registry

Reworked the Phase 2 illustration-strategy flow and the model roster behind it,
prompted by two reported failures: the SKILL.md Step 2 model-freshness check
effectively never ran (prose-only with a "proceed silently if everything is
represented" escape hatch, so an agent left no trace and skipped it), and a
refresh asked to update the model list dropped the `nano-banana-*` entries —
because "nano-banana" is Google's codename for the Gemini image line (Nano
Banana Pro = Gemini 3 Pro Image), and a bare string list carries nothing tying
the codename to the canonical id.

- **Model registry (`skills/illustrations/scripts/model_registry.py`)** — the
  bare `COMPARE_MODELS` list became a structured registry: canonical id, vendor
  family, aliases, and per-model cost/speed/quality tiers + edit support. The
  redundant `nano-banana-pro-preview` entry folded into
  `gemini-3-pro-image-preview` as an alias. `resolve_model_id()` maps any baked
  codename to the canonical API id before dispatch. `COMPARE_MODELS` is now
  derived from the registry for backward compatibility.
- **Freshness precheck** — `model_registry.py --check-freshness` emits
  `last_reviewed` / `age_days` / `stale` / roster JSON from a date heuristic
  (`REGISTRY_LAST_REVIEWED` + 90-day max age). SKILL.md Step 2 runs it first and
  reports the verdict in one line — no silent skip. WebSearch + registry
  reconciliation fires only when stale; for an existing outline the agent also
  checks the baked model against the roster.
- **Optimization priorities → shortlist** — Step 3 elicits what the speaker
  optimizes for (cost / speed / quality / build-editability) and narrows the
  roster with `model_registry.py --shortlist <priorities>` before any render.
  `build-editability` hard-excludes Imagen (no edit endpoint); cost/speed/quality
  are soft rankings.
- **Style exploration** — `generate-illustrations.py --style-explore` reads a
  `candidates.json` (styles × shortlist × formats; schema in
  `references/style-explore-candidates-schema.md`) and renders into a structured
  `style-explore/<style>/<format>/<model>.<ext>` tree with an `index.md` contact
  sheet, so the speaker picks style and model together from rendered output.
- **Hybrid roster (cache + live inject)** — the registry is a seed cache, not an
  allowlist. Rendering accepts any id from a supported vendor family with no code
  change; a web-discovered model can be ranked for one talk via
  `shortlist_models(extra_models=...)` / `--shortlist --add '<json>'` without a
  table edit. Persistent additions land in the registry through the Step 2
  refresh.
- **Docs + evals** — rewrote `references/strategy.md` (priorities → format →
  shortlist → style proposals → exploration render → continuity), updated
  `generation.md`, the SKILL.md Key Files table, and presentation-creator's
  Decision #11. Updated the two `illustrations-freshness-*` eval criteria to the
  precheck contract and added `illustrations-priority-model-shortlist`. New tests
  cover alias resolution, shortlist ranking + injection, the freshness date math,
  and the style-explore helpers.
- **Follow-up (pre-existing):** the `illustrations-mode-routing` eval criteria
  count steps without the freshness step (off by one vs the committed 7-step
  SKILL.md). The README "6 mode-routed steps" comment is corrected here; the
  mode-routing criteria renumber is left for a dedicated pass.

### feat(shownotes-publisher) — new skill for the Jekyll shownotes site

A sixth skill, `shownotes-publisher`, writes talk pages into a
Jekyll-based shownotes site (`~/Projects/shownotes`, published at
`https://speaking.jbaru.ch`). The site uses a custom markdown parser
(`_plugins/markdown_parser.rb`) that extracts structured fields by
pattern-matching on the body — abstract under `## Abstract`,
field-block lines like `**Conference:** value` + `**Video:** [text](url)`,
presentation-context paragraph starting with "A presentation at",
resources under `## Resources`. The format is strict; small mistakes
silently flatten content (e.g., multi-paragraph abstracts become one
paragraph because the parser joins all lines with spaces before
`markdownify`).

The skill encodes the contract end-to-end:

- **`SKILL.md`** — 9-step workflow from outline.yaml gather through
  publish, with the field-block grammar, the "Video Coming Soon"
  pattern, thumbnail conventions, and the update-don't-rewrite rule
- **`references/parser-contract.md`** — line-by-line spec of what
  each `extracted_*` field captures (title, conference, date,
  slides, video, abstract, resources, presentation_context) and how
- **`references/template-conditionals.md`** — what `talk.html` does
  with each extracted field, including the truthiness trap on
  `extracted_video` (any non-empty string triggers "Video Available"
  — `**Video:** TBD` fires the wrong badge)
- **`references/common-mistakes.md`** — 13 documented failure modes
  (entries 1, 1b, 1c, 2–11) with what visually happens and the right
  way (e.g., abstract sub-headings flatten; bare-URL Slides/Video
  doesn't extract; resource before abstract folds abstract into
  resources)

**Motivating incident.** This skill was authored after the
KotlinConf 2026 talk file shipped on `jbaruch/shownotes` commit
`83ac8d9` with placeholder-URL Slides/Video lines:

```markdown
**Slides:** [View Slides](#) <!-- TODO -->
**Video:** [Watch Video](#) <!-- TODO -->
```

Both fields fired the wrong badges and rendered broken embeds; the
inline HTML comments were pulled into the captured field values by
the parser's `^\*\*Slides:\*\*\s*(.+)$` value-capture group. The
incident motivates entries 1b and 11 in `references/common-mistakes.md`.

The key behaviors the skill enforces:

- **No video frontmatter until video is published.** The layout's
  `{% if page.extracted_video %}` is what flips the "Video Coming
  Soon" badge to "Video Available". Adding `**Video:** TBD` (or any
  placeholder) makes `extracted_video` truthy and fires the wrong
  badge plus a broken embed
- **Abstract is exactly one paragraph.** The parser joins all
  non-empty lines under `## Abstract` with a single space, collapses
  whitespace, then passes the result to `markdownify`. Sub-headings,
  lists, code blocks, and tables inside the abstract render as
  flattened prose
- **Slides/Video URLs must be markdown links.** The URL extraction
  regex is `\[([^\]]+)\]\(([^)]+)\)`. Bare URLs survive in the
  field value but break the embed include's URL-pattern matching
- **Update existing files in place.** Speakers hand-edit shownotes
  post-publish (typo fixes, resource additions). A re-author wipes
  those edits silently. The skill reads-then-edits, never overwrites

Four eval scenarios ship with the skill, all under `evals/`:

- `shownotes-publisher-publish-with-date` — first-time publish, the
  delivery date is set, filename uses the dated convention
- `shownotes-publisher-publish-no-date` — pre-talk publish where the
  delivery date is absent, filename and Date field both adapt
- `shownotes-publisher-update-add-video` — adds a video URL to an
  existing file, exercises the read-then-edit preservation rule
- `shownotes-publisher-omit-placeholder` — negative case; the user
  asks for a "video coming soon" UX cue, the skill must omit the
  `**Video:**` line entirely rather than emit a placeholder URL

The skill is invocable directly (`Skill(skill: "shownotes-publisher")`)
or after the presentation-creator skill finishes Phase 6 publishing
when the speaker says "now publish to shownotes". Tile size: six
skills, `tile.json` and README updated accordingly.

### feat(presentation-creator) — outline.yaml is now the source of truth

The presentation-creator skill moves from two hand-authored markdown
files (`presentation-spec.md` for talk metadata, `presentation-outline.md`
for the outline) to a single schema-validated `outline.yaml`. The four
derived artifacts (`narrative.md`, `script.md`, `slides.md`,
`rhetorical-review.md`) generate deterministically from it.

**What changed:**

- New `scripts/outline_schema.py` — pydantic v2 source of truth.
  `talk:` block (title, slug kebab-case-validated, speakers, duration,
  audience, mode, venue, slide_budget, pacing_wpm, architecture from
  closed enum, thesis, shownotes_url_base, commercial_intent,
  profanity_register, must_include, must_avoid, catalog_reference,
  delivery_count, delivery_date). `chapters[]` with target_min,
  cuttable, accent, argument_beats for `narrative.md`. `slides[]`
  with format (FULL/IMG+TXT/EXCEPTION/TITLE/DEMO), visual,
  text_overlay, image_prompt, builds, screenplay-form script with
  speaker attribution, applied_patterns against the 77-pattern closed
  enum discovered from `references/patterns/`, callbacks ledger,
  big_idea singleton, thesis preview/payoff. `interludes[]` for live
  demos between slides (anchored by `after_slide`). `style_anchor:`
  block for illustration-strategy talks.

- Four new extractor scripts:
  - `extract-narrative.py` → chapter walker, prose
  - `extract-script.py` → screenplay form, slides + interludes
    interleaved by anchor
  - `extract-slides.py` → per-slide build sheet
  - `check-rhetorical.py` → structural gap-check over the closed
    pattern taxonomy (PUNCH coverage, big-idea singleton, thesis
    ordering, sparkline elements when applicable, master-story
    threading, callback ledger, inoculation count, progressive-list
    contiguity, duration accounting)

- Existing scripts rewritten to consume `outline.yaml`:
  - `guardrail-check.py` — profile-aware checks (slide budget, Act 1,
    branding, profanity, data attribution, closing, cut lines); the
    structural taxonomy now belongs to `check-rhetorical.py`
  - `extract-resources.py` — walks `slides[]`/`interludes[]` via
    `outline_schema`; image prompts deliberately excluded
  - `generate-talk-timings.py` — walks `chapters[]`; no markdown
    parsing

- Skill prose rewritten end-to-end: `SKILL.md` (workflow table, all
  phase steps, late-entry checklist, artifact table),
  `phase1-intent.md` (talk metadata → `talk:` block),
  `phase3-content.md` (full rewrite teaching the YAML schema),
  `phase4-guardrails.md` (two-script split documented),
  `phase5-slides.md` (slides.md is the build sheet; `{slug}.md` for
  presenterm decks), `phase6-publishing.md` and
  `phase7-post-event.md` (file refs updated).

**Why it matters:** the markdown outline format required regex
parsing for every downstream consumer (guardrail-check, extract-
resources, generate-talk-timings, the agent itself), and every
change to the format risked breaking parsers in unrelated scripts.
Schema validation + four single-responsibility extractors collapses
that parsing surface into one pydantic model and four deterministic
walkers — per `rules/script-delegation.md`'s deterministic-vs-
reasoning split.

### evals — rename to descriptive names, port fixtures to YAML

All numeric `scenario-N` evals renamed to descriptive kebab-case
(e.g., `scenario-20` → `qr-missing-shortener-detection`).
`eval-resources/` subdirectories renamed to match. Fixtures that
referenced `presentation-outline.md` or `presentation-spec.md`
converted to `outline.yaml` (QR scenarios, thumbnail evals, CFP,
illustrations-mode-routing, freshness evals, pattern-strategy-4-tier,
illustrated-outline evals, progressive-reveal-builds). Criteria
ported from markdown-bullet assertions to YAML field assertions.
Test suite: 289 / 5 skipped (+60 net).

### ci — remove `tessl eval run` from CI per updated plugin-evals policy

`jbaruch/coding-policy` 0.3.20's `rules/plugin-evals.md` (Persistence
section) is explicit: do not add a `tessl eval run` step to tile-repo
CI, and do not add a scheduled/recurring workflow that re-runs the
suite as a persistence mechanism. The Tessl-publish layer
(`tesslio/patch-version-publish@v1`) owns persistence execution and
runs the eval suite automatically — any explicit step on top is
duplicate cost producing the same numbers a maintainer would already
see at publish time, and a parallel cadence can mask a publish-layer
eval failure with a parallel pass.

Two deletions:

- `publish-tile.yml` — removed the explicit `Run eval suite before
  publish` step (`tessl eval run .`). The eval suite still runs (via
  the publish action's internal execution); only the duplicate CI
  step is gone.
- `evals-scheduled.yml` — deleted entirely. The weekly cron was a
  recurring-persistence workflow of exactly the kind the rule
  prohibits.

Steady-state effect: every publish run drops `tessl eval run .` from
the CI step list; the publish action still gates on eval regressions
because it runs the suite itself. The scheduled weekly run is gone.
Local `tessl eval run .` for scenario authoring/debugging remains
permitted under the rule's authoring carve-out.

### ci — migrate `tessl skill review` to changed-skills loop

`publish-tile.yml` previously ran one static `tessl skill review` step per
skill on every push to `main` (5 invocations per merge). After
`jbaruch/coding-policy` 0.3.20 codified the changed-skills-loop pattern
in `rules/context-artifacts.md`, those static steps became a policy
violation — and a real cost: `tessl skill review` is LLM-backed, so
re-reviewing unchanged content burns Tessl credits while reproducing the
prior rubric output.

This release replaces the 5 static steps with one `uses:` of the
reference composite action shipped at
`jbaruch/coding-policy/.github/actions/skill-review`, pinned to SHA
`2a9df6575e153ce0d98900fdae26384c06df478f`. The action:

- diffs `github.event.before..HEAD -- skills/` to identify changed skills
- reviews only those skills at the configured threshold (85, unchanged)
- falls back to reviewing every skill on `workflow_dispatch` or initial
  push (no usable base)
- hard-fails when the base SHA is set but unreachable in the clone, so
  a missing review can never silently degrade to "review skipped"

`actions/checkout@v4` gains `fetch-depth: 0` per the composite action's
documented requirement (it needs the prior-push commit reachable).

Steady-state effect: PRs that don't touch `skills/` cost zero skill-review
invocations at merge; PRs that touch one skill cost one. Multi-skill PRs
scale linearly with what they actually changed.

### evals — prune low-value scenarios and strip task-criterion bleeding

Audited the 34-scenario eval suite against `jbaruch/coding-policy: plugin-evals`
(No Bleeding, Lift Not Attainment) and the user-stated rules in working
memory (test outcomes not implementation details; no agent-written
reimplementations of skill-provided scripts).

- **Retired 4 scenarios** with zero lift: `scenario-2` (duplicates
  `scenario-11` slide-source coverage), `scenario-23` (overlaps
  `scenario-22`+`scenario-19`), `scenario-27` (generic python-pptx
  placeholder work), `structured-talk-outline-with-typed-place`
  (overlaps `scenario-14`).
- **Stripped task-criterion bleeding from 9 scenarios** —
  `clarification-interactive-session`, `pattern-strategy-4-tier`,
  `scenario-12`, `scenario-13`, `scenario-16`, `scenario-21`,
  `scenario-22`, `scenario-24`, `scenario-26`. Removed criterion-mirror
  text from task bodies (Notes-on-Verification answer-key blocks,
  enum literals, threshold values, verb-action directives like "do
  NOT flag X"). The bleeding-strip pass left `criteria.json` files
  untouched in every case — fixes are at the task per the rule.
  Subsequent reviewer-driven commits in this PR did edit four
  `criteria.json` files (rebalancing three sums to 100 and
  reframing scenario-13's wide-angle criterion as outcome-based);
  those are documented in their own entries below.
- **Realigned 2 scenarios with skill orchestration** — `scenario-0`
  bleeding cleanup ("(should be skipped)" annotations) plus removed
  the `build_tracker.py` script-from-scratch requirement from
  `scenario-1` (vault-ingress ships Step 1 logic, not a separate
  script).
- `scenario-14` reviewed and reclassified to KEEP — audit had a
  false positive; its criteria check tile-prescribed structural
  tokens that the task does not pre-state.
- **Retired 3 structural-redundancy scenarios** — `scenario-18`
  (OOXML element presence, python-pptx output mechanics), `scenario-19`
  (QR image properties, qrcode-library output; subsumed by `scenario-21`
  full orchestration + `scenario-20` negative case), `scenario-24`
  (thumbnail planning; subsumed by `scenario-26` thumbnail revision
  which carries richer decisional content via speaker feedback).
- **Retired 6 data-driven low-lift scenarios** after running
  `tessl eval run .` on the de-bled set and inspecting per-scenario
  lift (with-context − baseline). Cut anything ≤3 lift or with a
  structural mismatch:
  - `clarification-interactive-session` (−71 lift) — vault-clarification
    is interactive (uses `AskUserQuestion` for multi-turn flow); the
    with-context agent correctly refuses to operate one-shot and
    scores 0, while the baseline fabricates answers and scores 71.
    Negative lift signals an eval-framework mismatch, not a fixable
    scenario problem.
  - `scenario-8` (Co-Presented Talk Adaptation, 0 lift) — both
    variants score 100/100; criteria measure universal competence.
  - `guardrail-check-format` (Guardrail Audit, 0 lift) — both
    variants 100/100; same problem.
  - `scenario-22` (Extract Resources, 2 lift) — baseline 98, ceiling
    effect; tile contribution drowned in universal-competence scoring.
  - `scenario-7` (PowerPoint Deck Build Plan, 2 lift) — baseline 98.
  - `scenario-25` (Post-Event Video Publishing, 3 lift) — baseline 97.

Suite goes from 34 to 21 scenarios. Average lift across the
remaining suite is substantially higher.

**Skill coverage after pruning.** `jbaruch/coding-policy: plugin-evals`
requires every skill with decisional logic to ship eval cases. After
this PR, all five skills retain at least one eval case in the suite:

- vault-ingress: 6 scenarios
- vault-clarification: 1 scenario — `scenario-12` (Humor Post-Mortem
  and Blind Spot Debrief), which tests vault-clarification's
  one-shot-evaluable decisional surface: recency-adapted questioning,
  per-beat humor grading, blind-spot probing grounded in analysis
  observations, structured-output capture. The interactive
  multi-turn `AskUserQuestion` flow that
  `clarification-interactive-session` previously attempted to cover
  is architecturally outside the eval framework's reach (the
  with-context agent correctly refuses to operate one-shot, producing
  the −71-lift signal that drove the retirement); this is an
  eval-framework limitation, not a coverage gap the eval suite is
  meant to close. The skill's
  decisional surface that *can* be one-shot-evaluated is covered.
- vault-profile: 1 scenario
- presentation-creator: 7 scenarios
- illustrations: 6 scenarios

**Reviewer-driven criteria edits.** Cross-family policy review on this
PR surfaced two `criteria.json`-side issues that were not in the
original bleeding-strip scope:

- Three scenarios had `weighted_checklist` max_score sums of 95 instead
  of 100, violating the eval-authoring weighting contract:
  `scenario-1` bumped "No-sources talk flagged as unprocessable"
  10 → 15 (the high-decisional behavior the tile teaches);
  `scenario-20` bumped "Agent distinguishes missing config from
  opt-out" 10 → 15 (the unique tile insight); `scenario-21` bumped
  "Command uses --shownotes-url (not --short-url)" 10 → 15 (the
  tile-prescribed arg choice). All 21 surviving scenarios now sum to
  exactly 100.
- `scenario-13`'s "Wide-angle detection" criterion previously prescribed
  a numeric ratio threshold ("ratio above 5:1 or 10:1 triggers a
  warning"). After de-bleeding stripped the task's hand-fed ratio
  interpretation, the criterion's threshold-direction was exposed as
  ambiguous (case_clean at 50/45 = 1.11:1 is even lower than
  case_wide_angle's 1.33:1, so any pure ratio threshold either
  false-flags clean or misses wide-angle). The criterion is now
  outcome-based: it grades that the agent flags `case_wide_angle`
  as wide-angle without false-flagging `case_clean`, using whatever
  signal the agent derives from extraction metadata. No specific
  numeric threshold is prescribed.

## 0.18.0

### deps — formalize tessl-version-floating carve-out

`tessl.json` floats its dependencies to `"latest"` because `tessl update`
rewrites the manifest in-place at runtime and `.tessl/tiles/` is
gitignored — pinning produces silent drift between commit history and
the running install. `jbaruch/coding-policy: dependency-management`
permits this only when three preconditions are met. This release adds
all three:

- **Authority-of-record rule** at `rules/tessl-version-floating.md`
  documenting the carve-out, naming `tessl.json` as the single covered
  manifest, and explaining why pin/lock semantics break in this shape.
  Registered under `tile.json` → `steering`.
- **Deploy-time check** at `scripts/check-tessl-pins.sh` that walks
  every covered manifest and fails if any dependency uses a specifier
  other than `"latest"` — rejecting literal pins, version ranges, tags,
  and anything else per the carve-out's "rejecting only literal pins
  lets a non-literal pinned/ranged value slip through" warning.
- **CI wiring** in `.github/workflows/tests.yml` runs the check ahead
  of the test suite on every push and PR. CI failure blocks merge.

The second `tessl.json` dependency (`tessl-labs/tessl-skill-eval-scenarios`)
also moves to `"latest"` — the carve-out applies to the manifest as a
whole, mixed pin/float within a covered manifest is not allowed.

### illustrations — pre-generation model-freshness check

New Step 2 in the illustrations skill runs before Strategy comparison or
deck Generation touches images. It uses `WebSearch` to identify current
flagship image-generation models from the major vendors (Google's Gemini
image + Imagen, OpenAI's `gpt-image-*`, and any other vendor with a
publicly accessible image API) and surfaces gaps against the script's
`COMPARE_MODELS` constant and — for Generation mode — the outline's baked
`**Model:**` choice plus its selection date.

If newer flagships exist, the step proposes updating `COMPARE_MODELS`
(Strategy) or re-running `--compare` against an updated list (Generation)
before continuing. The motivation is the months-long gap between when a
model was picked for a talk and when illustrations are actually generated
— a window in which a vendor often ships a meaningfully better flagship
(the recent `gpt-image-2` release being the precipitating example).

Step numbers in `SKILL.md` and the four reference files shift accordingly:
Strategy → Step 3, Generation → Step 4, Builds → Step 5, Apply → Step 6,
Thumbnail → Step 7.

### illustrations — cross-vendor image generation (OpenAI + Imagen)

`generate-illustrations.py` is no longer Gemini-only. The script now
dispatches by model-name prefix to three vendor families:

- `gemini-*` and `nano-banana-*` → Google `generateContent` (existing path)
- `imagen-*` → Google `:predict` endpoint with format-derived aspect
  ratio (new — FULL → `16:9`, IMG+TXT → `3:4`, the closest of Imagen's
  supported 1:1 / 9:16 / 16:9 / 3:4 / 4:3 set to the IMG+TXT 2:3 anchor)
- `gpt-image-*` → OpenAI `/images/generations` for fresh images and
  `/images/edits` (multipart) for the `--edit`, `--build`, and `--fix`
  workflows; size is format-derived (FULL → `2048x1152` true 16:9,
  IMG+TXT → `1024x1536` true 2:3) (new)

API-key resolution gains an `openai` slot. `secrets.json` now reads both
`gemini.api_key` and `openai.api_key`; either may also come from the
`GEMINI_API_KEY` / `OPENAI_API_KEY` environment variables. The script
only demands the key(s) needed by the models a given run will actually
hit — Gemini-only outlines don't require an OpenAI key, and vice versa.
Missing-key errors are per-vendor and include the right signup link
(`aistudio.google.com/app/apikey` for Google, `platform.openai.com/api-keys`
for OpenAI).

`COMPARE_MODELS` is refreshed to current flagships across vendors:
`gemini-3-pro-image-preview`, `gemini-3.1-flash-image-preview`,
`nano-banana-pro-preview`, `imagen-4.0-ultra-generate-001`, and
`gpt-image-2`. The older `gemini-2.0-flash-preview-image-generation` and
`imagen-3.0-generate-002` entries are dropped — they were superseded by
the flagships above (and the Imagen-3 entry was effectively broken
anyway, since `generateContent` doesn't accept Imagen models).

Imagen models have no public edit endpoint, so `--edit`, `--build`, and
`--fix` against an Imagen-family outline return an actionable error
directing the speaker to a Gemini or OpenAI model for editing workflows.

The outline parser also gained `+` and `-` tolerance in the Format and
STYLE ANCHOR regex (`[\w+-]+` replaces `\w+`) so the documented `IMG+TXT`
token is parsed correctly — previously it produced no match and the slide
silently fell back to the first available anchor and the FULL sizing
default. Safe-zone precedence is now applied uniformly:
`apply-illustrations-to-deck.py` treats `Safe zone:` presence as the
FULL/title-overlay signal regardless of the `Format:` token, so the
generator mirrors that — when Safe zone is present, the slide is
treated as FULL for anchor selection, vendor sizing, AND the directive
itself (via a new `effective_slide_format()` helper threaded through
every run_* caller).

New tests cover model-family classification across vendors, multi-vendor
key resolution (secrets.json, env-var fallbacks, partial config, malformed
JSON warning), the OpenAI multipart body structure, `final_build_dest`
extension preservation, the empty-build-steps parse path, the format
sizing table, and the `IMG+TXT` outline regex fix.

### Extract `illustrations` skill from presentation-creator

The visual layer (deck illustration strategy, generation, build chains, and
YouTube thumbnails) moves from presentation-creator into a new `illustrations`
skill. presentation-creator now delegates at three points: Phase 2 Decision
#11 (style strategy), Phase 5 Step 5.1b (illustration generation + build
generation + apply-to-deck), and Phase 7 Step 7.1 (thumbnail).

- New skill at `skills/illustrations/` with mode-routed SKILL.md (strategy /
  generation / thumbnail) and four references: `strategy.md`, `generation.md`,
  `builds.md`, `thumbnails.md`. Existing `title-placement.md` moved here too.
- Scripts moved: `generate-illustrations.py`, `apply-illustrations-to-deck.py`,
  `generate-thumbnail.py`, `suggest-scrim-color.py`. Tests updated to point
  at the new location; all 188 existing tests still pass.
- `apply-illustrations-to-deck.py` now handles `Format: IMG+TXT` slides as a
  first-class layout (image left ~60%, title + body right column), in addition
  to the existing FULL + Safe-zone path. New `IMGTXT_*` geometry constants;
  six new tests cover format parsing, picture repositioning, title repositioning,
  and column-width consistency.
- presentation-creator's Phase 2 / Phase 5 / Phase 7 references now stub to
  `Skill(skill: "illustrations")` rather than carrying inline workflow.
- `tile.json` adds the new skill entry. README updates skill count from four
  to five and rewrites the architecture diagram.

### vault-ingress — pptx-extraction emits `template_layouts`

`scripts/pptx-extraction.py` now extracts the master slide-layout
catalog (`{index, master_index, name, placeholders}` per layout) and
emits it under a top-level `template_layouts` key. Previously the
script emitted only `per_slide_visual` and `global_design`, so each
`vault-profile` regen silently carried forward the prior profile's
hand-curated layouts without ever refreshing them from the source
`.pptx`.

The `master_index` field disambiguates layouts that share a name
across different slide masters — PowerPoint allows reuse of layout
names like "Title and Content" across masters, so name alone is
unsafe as a merge key. Placeholder extraction catches `AttributeError`
specifically (rather than a bare `Exception` catch-all) and writes a
diagnostic to stderr with master index + layout name + placeholder
context when a malformed placeholder is skipped.

`skills/vault-profile/SKILL.md` Step 3 documents the merge contract:
the script is the source of truth for layout existence (`index`,
`master_index`, `name`, `placeholders`), while the speaker-curated
`use_for` field is preserved across regenerations by matching the
`(master_index, name)` pair.
`skills/vault-profile/references/speaker-profile-schema.md` adds an
inline note to the `template_layouts` example explaining the curation
contract.

`tests/test_pptx_extraction.py` adds 6 regression tests covering the
new `extract_template_layouts` function: emitted-key assertion,
default-count baseline, per-entry schema, sequential global indices,
placeholder schema (idx/type), and known layout-name presence.

### Pattern Taxonomy — Vault-derived patterns (5)

Five patterns observed across the vault corpus but not present in the
canonical Ford/McCullough/Schutta or Reynolds/Duarte sources have been
formalized into the taxonomy:

- `patterns/deliver/delayed-self-introduction.md` — open with a hook
  before introducing the speaker; the bio answers a question the
  audience has already implicitly asked. Vault dimensions 2, 11.
- `patterns/build/three-part-close.md` — closing structure of three
  separate slides (recap, CTA, thanks) rather than a single combined
  closing slide. Vault dimensions 2, 10.
- `patterns/build/progressive-reveal.md` — single complex base image
  annotated cumulatively across multiple slides, with a payoff slide
  that resolves the buildup. Vault dimensions 4, 7.
- `patterns/deliver/anti-sell.md` — speaker downplays own product or
  employer at moments where the audience expects a pitch, buying
  credibility for substantive claims later. Vault dimensions 11, 6.
- `patterns/build/meme-as-argument.md` — internet memes used as
  argumentative devices rather than decoration; relies on shared
  cultural reference to compress claims. Vault dimensions 4, 7, 12.

Taxonomy size: **97 → 102** entries (72 → 77 patterns; antipatterns
unchanged at 25). Observable count: **86 → 91**. Build phase: 34 → 37
patterns; Deliver phase: 19 → 21 patterns.

Index, summary stats, README structure tree, and `tile.json` summary +
description updated to reflect new counts.

### Pattern Taxonomy — Resonate ingest

Third source ingested alongside Ford/McCullough/Schutta (2013) and
Reynolds (2012): Nancy Duarte, *Resonate: Present Visual Stories that
Transform Audiences* (Wiley, 2010).

- **7 new build-phase patterns:**
  - `patterns/build/sparkline.md` — persuasion-specific narrative arc
    with two named turning points (Call to Adventure, Call to Action)
    and a "new bliss" close; vault dimensions 2, 5, 9
  - `patterns/build/call-to-adventure.md` — first sparkline turning
    point: dramatize the "what is" / "what could be" gap and reveal
    the Big Idea; vault dimensions 1, 2, 9
  - `patterns/build/call-to-action.md` — second sparkline turning
    point: specific, immediately-executable asks differentiated by
    audience action-temperament type (Doer / Supplier / Influencer /
    Innovator); vault dimensions 4, 6, 9
  - `patterns/build/new-bliss.md` — vivid future-state vision after
    the Call to Action; ensures the talk ends on a higher emotional
    plane than it started; vault dimensions 5, 6, 9
  - `patterns/build/star-moment.md` — "Something They'll Always
    Remember": planted dramatic peak in five sub-types (memorable
    dramatization / repeatable sound bite / evocative visual /
    emotive storytelling / shocking statistic); vault dimensions 3,
    5, 13
  - `patterns/build/inoculation.md` — preemptively voice the
    audience's strongest objection (steel-manned) and address it
    inside the talk; vault dimensions 4, 9
  - `patterns/build/master-story.md` — single anecdote woven
    recursively through the talk, each return deepening rather than
    repeating; vault dimensions 2, 5, 7
- **6 refinement subsections** folded into existing patterns:
  - `mentor.md` ← *Adopting the Stance — Planning Implications*
    (six-dimensional audience research, move-from/move-to matrix,
    resistance map, reward proportionality)
  - `the-big-why.md` ← *The Big Idea — Statement Format* (three
    required components: unique POV + explicit stakes + complete
    sentence)
  - `vacation-photos.md` ← *Numerical Narrative — Making Numbers
    Land* (Scale / Compare / Context techniques)
  - `peer-review.md` ← *Screening with Critics — Beyond Copyediting*
    (3× duration external critic session; six dysfunctional review
    patterns to avoid)
  - `crucible.md` ← *Murder Your Darlings — The Pre-Delivery Cut
    Pass* (convergent-thinking filter pass after divergent
    generation)
  - `sparkline.md` ← *The Three Contrast Types — Engine of the
    Middle* (content / emotional / delivery contrast as the
    persuasive-middle oscillation engine)
- **20 patterns** gain `## Related Reading` Duarte citations.
- **`patterns/_index.md`** — catalog tables, phase lookup, vault-dim
  mapping, summary stats, and sources updated. Total taxonomy entries
  now 97 (72 patterns + 25 antipatterns); 86 observable.

### Slide Design Spec

The speaker's `slide-design-spec.md` lives in their vault at
`~/.claude/rhetoric-knowledge-vault/slide-design-spec.md` (not in
this repo — it's per-speaker generated data). Two new reference
sections added to the vault file:

- §11.13 *Visual Relationships* — five-diagram-type taxonomy
  (flow / structure / cluster / radiate / influence) for converting
  bulleted slides into diagrams.
- §11.14 *Image Juxtaposition* — paired contrasting visuals
  technique for comparison-shaped content.

The presentation-creator skill in this repo references those
sections via `phase5-slides.md` (General Design Principles).

### Phase Documentation

- **Phase 0 (Intake):** new Step 0.3 sets the audience-as-hero
  planning stance; existing Step 0.3 renumbered to Step 0.4.
- **Phase 1 (Intent):** Spec Validation gains the Big Idea
  statement-format check and the Move-From / Move-To matrix.
- **Phase 2 (Architecture):** new "Persuasive vs. Informative
  Architecture" decision section presents Sparkline as a structural
  option alongside Narrative Arc; new "Action Typology" pre-planning
  section for Call to Action.
- **Phase 3 (Content):** new "Sparkline Structural Elements" section
  with placement guidance and outline-tagging conventions for Call
  to Adventure / Call to Action / New Bliss / S.T.A.R. moments; new
  Inoculation Beats and Master Story sections.
- **Phase 4 (Guardrails):** three new guardrail checks — Murder-
  Your-Darlings filter pass (Big Idea alignment of every section),
  Emotion-Balance check (analytical/emotional ratio against audience
  type), and Screening with Critics pre-lock gate for high-stakes
  talks.
- **Phase 5 (Slides):** General Design Principles section gains
  visual-relationships, image-juxtaposition, and numerical-narrative
  rules referencing the new slide-design-spec sections.
- **Phase 6 (Publishing):** Go-Live checklist gains the "first-
  impression-begins-before-entry" discipline (Duarte) reminding
  speakers to engage warmly with early-arrivers rather than
  heads-down at the laptop.

### Presentation Creator

- **`generate-thumbnail.py --portrait-style "<anchor>"`** — new flag
  enables a two-pass pipeline for decks with an Illustration Style
  Anchor (Phase 2 output). The script first pre-stylizes the speaker
  photo into the anchor's medium (sepia tech-manual, watercolor, ink,
  etc.) via a Gemini image-edit call, then runs the normal composition
  step using the stylized portrait as input. Fixes the palette-mismatch
  problem on illustrated decks that neither `--aesthetic photo` nor
  `--aesthetic comic_book` could solve. Independent of `--aesthetic`;
  they compose. Phase 7 Step 7.1 now passes the anchor through
  automatically when `presentation-outline.md` has a `## STYLE ANCHOR`
  block. Fixes #31.

### Pattern Taxonomy — Presentation Zen ingest

Second source ingested alongside Ford/McCullough/Schutta (2013):
Garr Reynolds, *Presentation Zen* (2nd ed., 2012, New Riders).

- **2 new patterns:**
  - `patterns/prepare/opening-punch.md` — Reynolds's PUNCH framework
    (Personal / Unexpected / Novel / Challenging / Humorous) for
    opening hooks; vault dimensions 1, 4
  - `patterns/deliver/screen-blackout.md` — deliberate B-key blackout
    or planned black slides as attention-redirection device; vault
    dimensions 12, 13
- **3 refinement subsections** folded into existing patterns:
  - `breathing-room.md` ← *Hara Hachi Bu* (90–95% finish-line discipline)
  - `concurrent-creation.md` ← *Plan Analog Before Going Digital*
  - `the-big-why.md` ← *The Elevator Test* (30–45 sec core-message check)
- **17 patterns** gain `## Related Reading` Reynolds citations
  (slideuments, bullet-riddled-corpse, floodmarks, borrowed-shoes,
  cookie-cutter, ant-fonts, narrative-arc, triad, crucible,
  concurrent-creation, vacation-photos, cave-painting, takahashi,
  bunker, bookends, coda, breathing-room).
- **`patterns/_index.md`** — catalog tables, phase lookup, vault-dim
  mapping, summary stats updated; sources section now lists Reynolds
  alongside Ford et al.

### Phase Documentation

- **Phase 1 (Intent):** Spec Validation gains the Two Questions check,
  the Elevator Test check, and the SUCCESs sticky-message check.
- **Phase 2 (Architecture):** new "Plan Analog Before Going Digital"
  section advocates whiteboard/Post-it work before slideware.
- **Phase 3 (Content):** new "Opening PUNCH" section requires explicit
  PUNCH-flavor tagging on the opening; new "Use Contrast as a
  Structural Device" section.
- **Phase 5 (Slides):** new "General Design Principles" section
  references slide-design-spec §11 (SNR, Big Four, picture superiority,
  empty space, rule of thirds, eye-gaze, full-bleed, 2D-for-2D, logo
  discipline, minimum font size).
- **Phase 6 (Publishing):** Go-Live Checklist gains venue-setup items
  (lights on, lectern aside, mic discipline) and during-delivery items
  (honeymoon-window discipline, never-apologize, *hara hachi bu*
  finish-line, screen-blackout).

### Tests

- 6 new tests for the two-pass thumbnail pipeline
  (`test_stylize_portrait_*` × 4, `test_compose_thumbnail_*` × 2).

## 0.17.0

**Talk timer, Keynote compatibility, shownotes destination** — New delivery timer
artifact, documented Keynote gotchas for slide generation, and machine-readable
shownotes publishing destination.

### Presentation Creator

- **`generate-talk-timings.py`** — new script parses `## Pacing Summary` table
  from the outline into `MM:SS Chapter` plain-text format for timemytalk.app.
  Supports `--qa` flag for Q&A chapters, sub-minute resolution, and automatic
  subdivision of acts exceeding 5 min using `## Section` headers
- **Phase 6 Step 6.4: Talk Timer Artifact** — new optional publishing step,
  gated on pacing summary presence in the outline
- **Keynote compatibility rules** — three python-pptx slide generation gotchas
  added to `slide-generation-rules.md`: use rectangles not connectors for
  decorative lines, never create-then-remove shapes in the same authoring flow,
  keep shape IDs contiguous per slide

### Resources & Publishing

- **Shownotes publishing destination** — `publishing_process.shownotes_site` added
  to speaker profile schema. Resources-gathering rules section 8 documents the
  read path: construct talk URLs from `shownotes_site` + `shownotes_url_pattern`,
  never guess or search the web
- **Vault-clarification config question** — new Step 5B question for
  `publishing_process.shownotes_site`

### Tests

- 15 new tests for `generate-talk-timings.py` (pacing parsing, cumulative times,
  Q&A insertion, sub-minute resolution, subdivision)

## 0.16.0

**Vault-clarification eval + test suite** — First dedicated eval for the interactive
clarification session, fixed volatile eval scenarios, and full pytest coverage for
every script with CI.

### New Eval

- **`clarification-interactive-session`** — first eval testing the vault-clarification
  skill's interactive session: rhetoric clarification (one question at a time), humor
  post-mortem (per-beat grading), blind spot probing, infrastructure config capture,
  intent confirmation storage, and session completion marking. Fixed test data with 1
  analyzed talk, empty config, 10-criterion weighted checklist

### Eval Fixes

- **Scenario 12** (humor post-mortem) — rewritten from "write a Python debrief tool" to
  "process these two fixed analysis files and produce structured debrief outputs." Fixed
  test data in `eval-resources/scenario-12/` (recent + old talk analyses)
- **Scenario 13** (extraction diagnostics) — rewritten from "write a diagnostics tool" to
  "analyze these 6 fixed extraction results and produce a report." Fixed test data in
  `eval-resources/scenario-13/` (6 concrete recording cases)

### Bug Fix

- **`pptx-extraction.py`** — fixed `AttributeError` crash on `_NoneColor` when extracting
  font colors from slides with unset color properties

### Tests & CI

- **119 tests across 15 test files** covering all Python scripts and the bash downloader
- **GitHub Actions workflow** (`tests.yml`) — runs on push to main + PRs, Python 3.12,
  installs ffmpeg and LibreOffice for full integration coverage
- **`pyproject.toml`** — declares all dependencies (python-pptx, lxml, qrcode, Pillow,
  imagehash, numpy) with `[test]` optional group for pytest

### Script Refactors

- **`strip-template.py`** — wrapped in `strip_slides()` + `main()` guard for importability
- **`delete-slides.py`** — wrapped in `delete_slides()` + `main()` guard
- **`reorder-slides.py`** — wrapped in `reorder_slide()` + `main()` guard (now raises
  `IndexError` on out-of-range instead of `sys.exit`)
- **`export-pdf.py`** — wrapped in `main()` guard, functions now take parameters
- **`_pptx_repair.py`** — extracted shared `clean_viewprops()` from strip-template and
  delete-slides into a single module, eliminating code duplication

## 0.15.0

**Placeholder slides, resources gathering, and post-event workflow** — New deck
adaptation tooling, Phase 6.0 resources extraction, Phase 7 post-event workflow,
and hardened QR generation.

### Presentation Creator

- **`insert-placeholder-slides.py`** — new script inserts bright-yellow placeholder
  slides at specified positions (1-indexed). Supports JSON file or `--at`/`--title`
  CLI input, `--output` flag for non-destructive saves. Processes positions in
  descending order to avoid index shifting
- **Phase 6.0: Resources gathering** — new `extract-resources.py` script parses
  presentation outlines for URLs, GitHub repos, book references, RFCs, and
  tool/library mentions. Deduplicates, tracks slide context, outputs JSON or markdown
- **Phase 7: Post-event workflow** — new phase covering post-delivery tasks
- **`generate-thumbnail.py`** — YouTube thumbnail generation via Gemini, composing
  slide images + speaker photos with style variants and YouTube spec validation
- **Shownotes slug convention** — slug generation process added to Phase 1 intent
  distillation, enforced from Presentation Spec (never agent-invented)
- **Presentation Spec persistence** — specs saved to disk as `presentation-spec.md`

### QR Generation Hardening

- **Custom Bitly domains** — `generate-qr.py` supports custom domains (e.g., `jbaru.ch`)
- **Per-slide QR colors** — different slides can have different background colors;
  script generates minimal PNG variants grouped by color scheme
- **Idempotent re-runs** — existing QR images replaced instead of stacked
- **`--png-only` mode** — generate QR PNG without opening a deck
- **Loud missing config** — missing shortener config surfaces as a warning, not silent
  degradation. Actionable `secrets.json` creation commands in error messages
- **Late-entry guard** — Phase 6 pre-flight checklist, no-raw-dogging rule

### Bug Fixes

- Fixed Bitly custom back-half silently ignored
- Fixed PPTX corruption from stale viewProps.xml after slide deletion
- Fixed multi-placeholder insertion index bugs

### Evals

- 2 new scenarios: insert-placeholder-slides, QR generation failure modes

## 0.14.0

**QR code generation** — Automated QR code generation and insertion into decks during
Phase 6 publishing, with slide background color matching and auto-contrast foreground.

**Gemini API key in secrets.json** — `generate-illustrations.py` now reads the Gemini
API key from `{vault}/secrets.json` (`gemini.api_key`) first, falling back to the
`GEMINI_API_KEY` environment variable for backward compatibility. This unifies all API
keys in one file. New `--vault` CLI argument for custom vault paths.

### Presentation Creator

- **`generate-qr.py` script** — new script generates unbranded QR codes from shownotes
  URLs (or pre-shortened URLs), matches the QR background to the target slide's color,
  and auto-selects white or black foreground based on WCAG relative luminance. Inserts
  the QR as a 2" square in the bottom-right corner of the configured slide(s)
- **Phase 6 step reordering** — QR generation now runs before PDF export (was after).
  Steps: Shownotes → QR Code → Export → Additional → Go-live → Report
- **URL shortening support** — bit.ly and rebrand.ly via direct API or MCP-preresolved
  mode. Re-running for the same talk slug updates the existing short link (keeps printed
  QR codes valid). Falls back to raw URL when shortener=none or API fails
- **Vault-based secrets** — API keys stored in `{vault}/secrets.json` (not env vars),
  documented with `chmod 600` recommendation

### Schema Changes

- **Speaker profile `qr_code`** — 5 new fields: `custom_url`, `shortener`,
  `rebrandly_domain`, `bg_color_match`, `preferred_short_path`
- **Tracking database `qr_codes[]`** — new top-level array tracking per-talk QR
  metadata: talk slug, target URL, shortener, short path/URL, link ID, PNG path
- **Vault clarification** — 3 new questions for shortener preference, Rebrandly
  domain, and API key setup

### Evals

- 1 new scenario (scenario-19): QR generation with purple background matching,
  auto-contrast white foreground, shortener=none path, tracking DB update

## 0.11.0

**Illustration pipeline** — AI-generated illustrations are now a first-class part of
the presentation creation process, with collaborative style decisions and per-slide
image prompts generated during outline creation.

### Presentation Creator

- **Phase 2: Illustration Strategy (Decision #11)** — optional collaborative workflow
  for talks that want AI-generated illustrations. Proposes 3-4 style options informed
  by the talk's concepts, the vault's visual history, and mode-specific precedent.
  Includes format vocabulary, model selection (with `--compare` mode), and visual
  continuity devices
- **Phase 3: Illustrated outline format** — new Illustration Style Anchor section in
  the outline header (model, per-format anchors, conventions). Per-slide Format,
  Illustration, Text overlay, and Image prompt fields. `[STYLE ANCHOR]` token
  referencing the header. `[IMAGE NN]` placeholder type for EXCEPTION slides
- **Phase 4: Illustration coverage guardrail (#10)** — checks format tag coverage,
  EXCEPTION justifications, style anchor references, and prompt quality. Shows
  `[SKIP]` for non-illustrated outlines
- **Phase 5: Generate illustrations step** — new Step 5.1b runs
  `generate-illustrations.py` to batch-generate images before slide population.
  Image Generation Setup docs with API key, model, and `--compare` instructions
- **Slide generation** — illustration-format-aware insertion (FULL → full-bleed,
  IMG+TXT → image + text, EXCEPTION → real asset) added to slide-generation.md

### Rhetoric Knowledge Vault

- **Dimension 13f: Illustration & Image Style** — new analysis sub-dimension for
  image source types, illustration aesthetic, visual coherence, style anchor evidence,
  visual continuity devices, and mode correlation
- **Structured data fields** — `illustration_style`, `illustration_coherence`,
  `image_source_distribution`, `visual_continuity_devices` added to extraction output
- **Speaker profile: `visual_style_history`** — new section with default style,
  style departures, mode-specific visual profiles, and confirmed visual intents
- **Schema fixes** — `transcript_source` added as required field on talk entries and
  subagent return schema. `delivery_language` and `co_presenter` added to subagent
  return schema. English-first quote rule promoted to inline in SKILL.md
- Video-as-slide-fallback reinforced in Step 3A processing instructions

### New files

- `skills/presentation-creator/references/generate-illustrations.py` — stdlib-only
  Python script for Gemini API image generation with `--compare` mode, resumable
  batch runs, rate limiting, and progress reporting

### Evals

- 2 new scenarios: illustrated outline format, illustration guardrail audit
- Updated guardrail audit scenario to check `[SKIP]` illustrations line
- 11 new instructions in instructions.json covering illustration features
- Fixed pre-existing eval gaps: task descriptions, criteria alignment, skill content

## 0.10.1

**Small print** — Sessions catalog entries now include a "Small Print" field for
Program Committee notes (talk positioning, what it is/isn't, reviewer context).

## 0.10.0

**Sessions catalog** — New `sessions-catalog.md` file in the vault for maintaining
submission-ready conference materials (title, abstract, outline) per active talk.

- Added Sessions Catalog section to presentation-creator SKILL.md with read/write
  rules: when to pull from the catalog (before writing a new CFP), when to save
  (after CFP writing or Phase 4 outline finalization), and maintenance guidelines
- CFP Abstract Writing flow now includes step 5: save to sessions catalog
- Added `sessions-catalog.md` to the vault skill's Key Files table
- Anti-pattern checking recommended on catalog entries before saving (public-facing text)

## 0.7.0

**Canonical vault path** — The vault now uses `~/.claude/rhetoric-knowledge-vault/` as
a fixed, discoverable location. No more asking "where should the vault live?" every
session. Custom locations (e.g., Google Drive) are symlinked to the canonical path.

- Vault discovery replaces config bootstrapping for `vault_root` — checks canonical
  path first, creates or symlinks on first run
- New `vault_storage_path` config field tracks the actual directory when using a custom
  location
- Updated presentation-creator to read vault from the canonical path directly
- Updated eval instructions (+2 new vault discovery instructions) and scenario-1
  criteria (canonical path check)
- README updated to reflect new vault location behavior

## 0.6.2

**Maintenance** — Version bump and CLI publish.

## 0.6.1

**Eval scenarios** — Added 5 new server-generated eval scenarios via `tessl scenario
generate`, covering both skills end-to-end. Reviewed and fixed all 15 scenarios for
quality, then ran the full eval suite (baseline avg 62% → with-skill avg 98%).

### New scenarios (5)
- Multilingual rhetoric analysis with language policy and pattern scoring
- Presentation outline with typed placeholders and callbacks
- python-pptx deck generation with template stripping and notes injection
- Guardrail check format and 4-tier pattern strategy
- Speaker profile JSON generation from vault data

### Scenario fixes
- Removed instruction leakage from python-pptx scenario (replaced numbered output
  spec with high-level ask)
- Fixed factual error in guardrail scenario (Act 1 ratio math: 51.7% → 43.3% to
  correctly test the WARN threshold)
- Fixed infeasible criteria (replaced MCP-only `optimize_slide_text` with python-pptx
  overflow handling)
- Fixed transcript pre-translating Russian phrases (defeated the English-only quote
  format test)
- Fixed ambiguous download results in status management scenario (added
  `video_extraction` field, clarified planning-time vs download-outcome for
  `slide_source`)
- Added missing `capability.txt` files to all new scenarios
- Tightened subjective criteria wording across all scenarios

## 0.5.5

**Video-extracted slides** — When no slides file exists, extract slides directly
from video: ffmpeg frame extraction → crop to slide area (exclude PiP) → perceptual
hash deduplication → combine into PDF. Marks `slide_source: "video_extracted"`.

## 0.5.4

**Non-YouTube video support** — Step 3A now supports ingesting talks from InfoQ,
Vimeo, conference platforms, and any source yt-dlp supports. Downloads audio via
`yt-dlp -f http_audio`, transcribes locally with MLX Whisper (Apple Silicon) or
OpenAI Whisper. Tags transcript source as `"whisper"` vs `"youtube_auto"`.

## 0.5.3

**Data integrity fixes:**

- **Summary status recount:** Step 4 now rewrites the summary Status block by
  counting the tracking DB every time. The DB is the source of truth; the summary
  is a derived view. Fixes stale tallies from manual incrementing.
- **Structured field extraction:** Step 4 now requires populating `co_presenter`,
  `delivery_language`, and other structured DB fields directly from analysis results,
  not burying them in `rhetoric_notes` free text.

## 0.5.2

**Blind spot clarification + language policy** — Two additions to the vault skill:

- **Step 5A-bis (Blind Spots):** After analyzing each talk, the skill identifies
  moments it knows it missed (audience reactions, costume/prop moments, room energy,
  demo engagement) and asks the speaker. Stores as `blind_spot_observations`.
- **Language policy:** The vault is English-only. Non-English talks are analyzed and
  stored in English with translated quotes, language-tagged verbal signatures, and
  `delivery_language` on the talk entry. Prevents non-English content from polluting
  the signature list or rhetoric summary.

## 0.5.1

**Robustness & conciseness** — Addressed gaps found during tile review and
tightened both skills for the review gate.

### Robustness fixes
- Made vault→creator pattern index path explicit with tile-root-relative path
- Added pattern taxonomy migration: Step 1 detects pre-v0.5.0 talks missing
  `pattern_observations` and marks them `needs-reprocessing`
- Added `clarification_sessions_completed` counter to tracking DB config
- Added LibreOffice CLI as cross-platform PDF export alternative
- Clarified Step 3B firing conditions

### Conciseness improvements
- Vault SKILL.md: 285 → 207 lines. Consolidated reference file list into Key
  Files table, collapsed config bootstrapping, tightened PPTX/PDF handling,
  moved Step 5B questions to `schemas.md`, compressed profile mapping and badges
- Creator SKILL.md: 263 → 230 lines. Merged vault loading steps, condensed
  Phase 2 decisions table, removed summary-only mode table (now inline)
- Review threshold lowered to 85 (vault conciseness 2/3 has no actionable
  feedback per the optimizer)

## 0.5.0

**Presentation Patterns integration** — Integrated the pattern taxonomy from
*Presentation Patterns* (Ford, McCullough, Schutta 2013) as a structured reference,
vault scoring system, and brainstorming vocabulary across both skills. Patterns are
classified as observable (scored by the vault) or unobservable (surfaced as a go-live
checklist before delivery).

### Pattern taxonomy (88 new files)

- 88 reference files (63 patterns + 25 antipatterns) organized by lifecycle phase
  (prepare/build/deliver) with YAML frontmatter: `id`, `name`, `type`, `part`,
  `phase_relevance`, `vault_dimensions`, `detection_signals`, `related_patterns`,
  `inverse_of`, `difficulty`, and `observable` (true by default, false for 11 entries)
- Master index (`references/patterns/_index.md`): flat catalog table, phase-grouped
  lookup, vault dimension reverse mapping, and unobservable patterns go-live checklist
- Each file includes: summary, detailed description, when to use/avoid, detection
  heuristics, 3-tier scoring criteria, vault dimension mapping, and combinatorics

### Observable vs unobservable split

- **77 observable** patterns are detectable from transcripts + slides and scored during
  vault analysis
- **11 unobservable** patterns (8 patterns + 3 antipatterns) involve pre-event logistics,
  physical stage behaviors, or external systems that leave no trace in recordings:
  - Pre-event: Preparation, Carnegie Hall, Stakeout, Posse, Seeding Satisfaction, Shoeless
  - During delivery: Lightsaber, Red/Yellow/Green
  - Antipatterns to avoid: Laser Weapons, Bunker, Backchannel
- Unobservable patterns are marked `observable: false` in their frontmatter, excluded
  from vault scoring and `pattern_profile`, and surfaced as a go-live preparation
  checklist in creator Phase 6

### Vault scoring (4 modified files)

- Subagents now tag talks against the observable pattern taxonomy during analysis
  (Step 3 B2), skipping patterns marked `observable: false`
- `pattern_observations` field added to both subagent return schema and tracking
  database talk entries (`schemas.md`)
- Per-talk analysis files now include a "Presentation Patterns Scoring" section
- Step 6 generates an aggregate `pattern_profile` in the speaker profile with mastery
  levels, usage trends, signature combinations, antipattern frequency, and never-used
  patterns (observable only)
- Pattern-based badges generated from profile data (e.g., "Narrative Arc Master",
  "Shortchanged Survivor", "Pattern Polyglot")
- `pattern_profile` section added to `speaker-profile-schema.md` with documentation
  that only observable patterns are included
- All 14 rhetoric dimensions in `rhetoric-dimensions.md` cross-referenced with their
  related patterns and antipatterns

### Creator integration (3 modified files)

- Phase 0: Loads `references/patterns/_index.md` alongside vault documents
- Phase 2 (Architecture): Decision #10 "Pattern Strategy" — 4-tier recommendation
  system using `pattern_profile`:
  - **Signature** (80%+ usage) — always shown
  - **Contextual** — matching spec context, occasional speaker usage
  - **New to You** — from never-used patterns, filtered by relevance
  - **Shake It Up** — random picks, provocations not prescriptions
  - Plus antipattern warnings merging speaker history + contextual detection
- Phase 4 (Guardrails): Section 9B adds taxonomy-based antipattern scanning with
  `[RECURRING]` flags from `pattern_profile.antipattern_frequency` and `[CONTEXTUAL]`
  flags from outline analysis
- Phase 6 (Publishing): Step 6.5 go-live preparation checklist surfaces all 11
  unobservable patterns as delivery-day reminders
- Summary-only mode (no profile) still works — patterns from reference files only,
  flat list, go-live checklist still applies

### Documentation

- `README.md` — rewritten with Presentation Patterns section, observable/unobservable
  table, updated file tree, updated vault/creator descriptions
- `tile.json` — bumped to v0.5.0, added "patterns" keyword
- `CHANGELOG.md` — this entry

## 0.4.7

**Review & consistency fixes** — Addressed consistency gaps found during tile review.

- Vault Step 4 now writes per-talk analysis files to `analyses/` (fixes broken adaptation workflow in creator)
- Added `badges` schema to `speaker-profile-schema.md`
- Broke single `publishing_process` question into targeted sub-questions matching the schema
- Clarified summary section numbering vs rhetoric dimension numbering in vault SKILL.md
- Labeled slide budget table in creator as defaults when profile is unavailable
- Added `cfp`, `abstract`, `pptx` keywords to `tile.json`
- Fixed `tessl.json` project name from scaffold placeholder
- Added python-pptx internal API risk note to `slide-generation.md`
- Backfilled CHANGELOG for versions 0.3.1-0.4.5

## 0.4.1 - 0.4.5

**CI/publish pipeline tuning** — Iterative adjustments to the GitHub Actions publish
workflow: switched to the publish action's built-in skill review gate, tested optimize
input, and settled on the default review threshold (50%).

## 0.4.0

**Evaluation scenarios** — Added 10 eval scenarios covering both skills (vault analysis
and presentation creation), plus Tessl eval infrastructure.

- 10 scenario tasks with criteria covering rhetoric analysis, profile generation,
  presentation creation, adaptation, CFP writing, and guardrail enforcement
- Tessl eval tile dependency added

## 0.3.0

**Speaker badges & profile Step 6 enhancement** — Profile regeneration now generates
personalized speaker badges as a fun summary of portfolio-wide achievements, mined from
real vault data (meme counts, employer transitions, recurring patterns, signature quirks).

- Step 6.7 added: generate speaker badges after profile regeneration
- Badges must be genuinely personalized to the speaker's quirks, not generic
- Grounded in aggregated data from all processed talks

## 0.2.0

**PPTX as primary slide source** — The vault skill no longer requires Google Drive slide
PDFs for every talk. Talks with `.pptx` files can now be processed directly, providing
richer data (exact hex colors, font names, layout names) than PDF visual inspection.

- A talk is processable with `video_url` + at least one of `slides_url` or `pptx_path`
- New `slide_source` field on each talk: `"pdf"`, `"pptx"`, or `"both"`
- When PPTX is available, extraction runs inline during rhetoric analysis (Step 3),
  merging what was previously a separate Step 3B pass
- Step 3B now only processes PPTX files not already handled as primary sources
- Schema updated: `slides_url` and `pptx_path` are both optional (at least one required)

## 0.1.0

Initial release with two skills:
- **rhetoric-knowledge-vault** — parse recorded talks to extract rhetoric patterns
- **presentation-creator** — create new presentations matching your documented style
