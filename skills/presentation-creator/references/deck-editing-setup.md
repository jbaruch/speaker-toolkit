# Deck Editing — One-Time Setup Walkthrough

First-time setup for the PowerPoint-native deck-editing tooling
(`RunDeckOps.bas` + `run-deck-ops.sh`; see `rules/deck-editing-rules.md`).
**macOS + Microsoft PowerPoint only.**

The agent runs this interactively: do ONE step at a time, wait for the user to
confirm, then continue (per `rules/interaction-rules.md`). Most of these are
manual GUI actions only the user can do. Run it once per machine; afterwards
the agent can invoke `run-deck-ops.sh` directly with no further prompts.

## Step 1 — Enable VBA macros

Ask the user to open **PowerPoint → Settings → Security & Privacy** and enable
macros ("Enable all macros", or enable + trust). Wait for confirmation.

## Step 2 — Create the macro container `DeckOps.pptm`

The macro must live in a macro-enabled file, never in a real deck. Ask the user
to:
1. **File → New Presentation** (a blank deck — this becomes the macro home).
2. **File → Save As** → set **File Format: PowerPoint Macro-Enabled
   Presentation (.pptm)** → name it `DeckOps.pptm`, save it somewhere stable
   (e.g. alongside the tooling).

Gotcha to warn about up front: if PowerPoint ever shows **"Visual Basic macros
will be removed if you save the file in this format"**, the user is saving a
`.pptx` — tell them to click **Cancel** and save as `.pptm` instead. A real
deck must never carry the macro.

## Step 3 — Import the macro

Ask the user to open the VBA editor (**Tools → Macro → Visual Basic Editor**,
or ⌥F11), select **DeckOps.pptm's** project in the left pane, then
**File → Import File…** and choose
`skills/presentation-creator/scripts/RunDeckOps.bas`. Save `DeckOps.pptm` (⌘S).

To UPDATE the macro later: right-click the `DeckOps` module → **Remove** (No to
export) → **Import File…** the new `.bas` → save.

## Step 4 — Grant Automation consent (first run only)

The first time a script drives PowerPoint, macOS shows an **Automation** consent
prompt. Tell the user it is GUI-only — it cannot be approved headless — so they
should run the first invocation themselves (or be at the machine to click
**OK**): System Settings → Privacy & Security → Automation → allow the terminal
to control PowerPoint. After consent is granted once, the agent may run
`run-deck-ops.sh` itself.

## Step 5 — Smoke-test before any real edit

With `DeckOps.pptm` open, run a 3-slide throwaway against a UNIQUELY-NAMED copy
of a deck and confirm it opens clean in PowerPoint **and** Keynote (no "Repair"
prompt). Only then run the real edit. Given the history of lost work with other
tools, always test first.

## Google Drive caveat (important)

If decks live in a **Google Drive** "My Drive" folder (the macOS Google Drive
File-Provider mount), sandboxed PowerPoint can OPEN/read them but **cannot
create a new file there via VBA** — `SaveCopyAs` fails with E_FAIL
(`-2147467259`). `run-deck-ops.sh` works around this by saving to a local
staging folder (`~/.deckops-staging/`) and then moving the result into the Drive
destination with the shell (which writes to Drive normally). Keep using
uniquely-named copies for the base/import/output so PowerPoint's
filename-keyed open-deck cache never hands back the wrong deck.
