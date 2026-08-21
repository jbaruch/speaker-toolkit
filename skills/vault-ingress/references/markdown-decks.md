# Markdown-Authored Decks

Slidev, presenterm, Marp, and reveal-md author decks as markdown. Nothing in
this toolkit reads markdown as slide evidence, so a talk whose deck is a
`slides.md` in a git repo was analysed transcript-only — the deck was sitting
right there and no rule could see it.

`slide_source: "markdown"` records that such a deck exists. It is provenance,
not evidence: it stays out of `USABLE_SLIDE_SOURCES`, and a talk carrying it
gets the same transcript-only reading as `"none"`. This page is how to stop
that being the end of the story.

## Why it matters

Transcript-only analysis is not thinner, it is biased downward. Entries whose
`strong_evaluable_from` requires `static_slides` / `native_deck` /
`delivery_video` cap at `moderate` and take half the weight; everything else
they might have gated lands in `not_evaluable`. One talk re-analysed without
its slides lost nine previously-detected patterns — `bookends`, `breadcrumbs`,
`context-keeper`, `live-demo`, `crawling-code`, `defy-defaults`,
`display-of-high-value`, `greek-chorus`, `hiccup-words` — none of them
disproven, all of them merely ungated. A profile built from a cohort like that
understates the speaker's visual craft to the point of being misleading, and
Dimensions 8 and 13 are unmeasurable for them.

## The lane

Each renderer is its own optional lane, so a presenterm vault is not reported
as degraded for three tools it will never call. Which lane a deck needs is the
`lane` field of its own receipt (probe it below); what that lane requires is
`LANE_REQUIREMENTS` in `skills/vault-ingress/scripts/check-runtime.py`, and the
checker names the missing commands itself when a lane is unavailable.

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/check-runtime.py" \
  --lanes "core,{lane_from_the_receipt}"
```

Never `--require-lanes` a markdown-deck lane during bootstrap. Like every other
optional lane, an absent renderer degrades that one deck, not the run.

## Render, then register

`{deck_path}` below is the talk's registered `deck_source_path` when it has one,
and the file you located by hand when it does not — registering it is the last
step of this page. A registered value that is not absolute is vault-root
relative: resolve it against `{vault_root}` before passing it, because the
renderer resolves a relative path from its own working directory and would
report a missing deck for a locator that is fine.

Read the deck without touching a renderer — this reports the detected flavor,
the lane, and what is missing from it:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/render-markdown-deck.py" \
  "{deck_path}" --probe
```

Then render it into the vault's slides directory, where the existing
`static_slides` path already looks:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/render-markdown-deck.py" \
  "{deck_path}" --output "{vault_root}/slides/{talk}.pdf"
```

Both print one JSON receipt on stdout and exit 0; a deck that cannot be read,
an unavailable lane, and a failed render each exit 1 with a diagnostic on
stderr. Exit 3 is the closed failure boundary, not a verdict — see
[entrypoint-failure-contracts.md](entrypoint-failure-contracts.md). Pass `--flavor` when the deck carries no marker that names its tool, or
carries markers for two. The full receipt contract — every field, the detection
vocabularies, and the per-flavor invocation — is the script's, at the top of
`skills/vault-ingress/scripts/render-markdown-deck.py` and
`skills/vault-ingress/scripts/markdown_deck.py`.

Register the render as a normal PDF slide source and requeue the talk in one
repair plan (see [bootstrap-and-preflight.md](bootstrap-and-preflight.md) for
the `apply-source-repairs.py` dry-run/apply pair):

```json
{"schema_version": 1, "repairs": [{
  "filename": "spring-rag-jcon.md",
  "reason": "Slidev deck rendered to PDF and registered as slide evidence",
  "expect": {"slides_local_path": {"$missing": true},
             "slide_source": "markdown",
             "status": "processed_partial",
             "reprocess_reason": {"$missing": true}},
  "set": {"slides_local_path": "slides/spring-rag-jcon.pdf",
          "slide_source": "pdf",
          "status": "needs-reprocessing",
          "reprocess_reason": "source_added"}}]}
```

`expect` covers every field `set` touches, `status` and `reprocess_reason`
included — `validate_plan` refuses a repair that changes a field it did not
declare, so a plan missing those two is rejected before anything is written.
Use the talk's actual current `status`, not the one above.

The talk then binds as a normal `static_slides` artifact. Nothing about the
evidence path is special-cased for a deck that started as markdown.

## Register the deck itself

That repair is a one-way door: `slide_source` becomes `"pdf"` because the talk
now genuinely has readable slides, and after it nothing on the record says the
deck was ever markdown or where it lives. Record the deck separately, in its own
collection, so a later render — the deck gained three slides, the speaker
reworked the demo — reads its source instead of asking whoever remembers:

```json
{"schema_version": 1, "mutations": [{
  "kind": "record_markdown_deck",
  "filename": "spring-rag-jcon.md",
  "deck_source_path": "/repos/spring-rag/slides.md"}]}
```

It is an upsert keyed on the talk, so a deck repo that moves is re-pointed by
running it again; a second record for one talk is refused. It does not touch the
talk record — deliberately, because a talk's `schema_version` is its analysis
generation, and the transcript-only talks this whole page is about are legacy
records that can never advance to a shape gate. Field contract and accepted path
spellings: [schemas-db.md](schemas-db.md#owner-read-and-mutation-contract).

Nothing reaches the output path until the bounded PDF probe has accepted the
render. A renderer that exits 0 over a corrupt file leaves an earlier valid
render exactly where it was.

## Reading the receipt honestly

**`slide_count` comes from the rendered page count**, and the page count means
what it says: the renderer is invoked so that one page is one authored slide,
never one page per build state. How each tool is invoked to get that is the
script's — see `RendererSpec.argv` and the module docstring in
`skills/vault-ingress/scripts/render-markdown-deck.py`.

**`source_slide_count` is the cross-check, never the authority.** It is what
segmenting the markdown source finds. When it disagrees with the page count,
`slide_count_agrees_with_source` is `false` and the deck uses a construct the
source reader does not model. Record `slide_count` from the render, and treat
the disagreement as a reason to look at the pages rather than as a number to
reconcile.

One such construct is named outright: a Slidev `src:` key pulls slides from
another file, so one source slide renders as however many that file holds.
`source_structure.imported_files` lists them and `slide_count_is_a_floor` goes
`true`, which is why a disagreement there is expected rather than alarming.

**`source_structure.slides[].reveal_markers` is `progressive-reveal` evidence.**
It counts the staged-reveal markers the deck's own author wrote; which literals
each tool's markers are is `_REVEAL_PATTERNS` in
`skills/vault-ingress/scripts/markdown_deck.py`. A slide with markers declares
ordered cumulative content, which is exactly what `progressive-reveal` asks
for. Two things it is not:

- It is **not** `crawling-code` or repetition padding. Build states of one
  authored slide are one slide, and the one-page-per-slide export never split
  them into separate pages to be miscounted.
- It is **not** observed motion. The author asked for a staged reveal; nothing
  here watched one happen. Native-animation and delivery-video evidence stay
  separate.

When `reveal_markers_are_a_floor` is `true`, `floor_causes` names the headmatter
switch that stages content the source never marks. The count is a lower bound in
that case — a slide reporting zero may still build.

## Validating a deck by hand

CI installs all four renderers at pinned versions and renders a three-slide
deck through each on every run, so the one-page-per-slide claim is checked
there rather than asserted. What CI cannot check is YOUR deck. To do that:

1. Install what the flavor's lane requires — run the checker above and
   read the lane's `missing_commands`.
2. `render-markdown-deck.py <deck> --probe` — expect the right `flavor` and
   `lane_available: true`.
3. `render-markdown-deck.py <deck> --output /tmp/deck.pdf` — expect exit 0.
4. `pdftoppm -png -r 100 /tmp/deck.pdf /tmp/slide` and open the pages. Expect
   one image per authored slide, each showing the slide's *final* build state.
   Several near-identical images differing by one added line means a per-click
   export got through, and the renderer's invocation needs fixing rather than
   the count explaining away.
5. Compare `page_count` against the deck's own slide count in its editor.

## Two gotchas worth knowing

**presenterm needs a terminal.** Exporting it by hand from a script or a CI
step fails with `Inappropriate ioctl for device (os error 25)`, and from an
unsized pty with `render: screen is too small`. Both are handled — see
`_run_with_pty` in `skills/vault-ingress/scripts/render-markdown-deck.py`.
Recognize the messages if you export by hand; the renderer here does not hit
them. presenterm also shells out to `weasyprint`, which is why its lane wants
both.

**Browser-backed renderers need a browser.** Slidev's PDF export needs
`playwright-chromium`; Marp and reveal-md drive a Chrome/Chromium or Firefox.
Their absence surfaces as a renderer failure, not a missing command, so the
diagnostic carries the renderer's own output.
