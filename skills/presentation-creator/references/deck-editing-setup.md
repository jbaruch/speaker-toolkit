# Deck Editing — One-Time Setup Walkthrough

First-time setup for the PowerPoint-native deck-editing tooling
(`RunDeckOps.bas` + `run-deck-ops.sh`; see `rules/deck-editing-rules.md`).
**macOS + Microsoft PowerPoint only.**

Steps 1–4 are manual GUI actions only the user can perform; the agent presents
each and the user acts, then the agent proceeds. The Step 5 smoke test verifies
the whole setup end-to-end before any real edit — so the agent does not pause to
confirm each manual step, it confirms once via the smoke test. Steps 1–4 run once
per machine. **Step 6 is the recurring per-build flow** — read it before every
real deck build.

Heads-up for installed tiles: `tessl install` ships only `.md/.py/.json/.sh/.txt`
and STRIPS `.bas`/`.applescript`, so `RunDeckOps.bas` and the `.applescript`
drivers aren't on disk after install — Step 3 restores them from their committed
`.txt` mirrors. A dev checkout already has them.

## Step 1 — Enable VBA macros

Ask the user to open **PowerPoint → Settings → Security & Privacy** and enable
macros ("Enable all macros", or enable + trust). Proceed to Step 2.

## Step 2 — Create the macro container `DeckOps.pptm`

The macro must live in a macro-enabled file, never in a real deck. Ask the user
to:
1. **File → New Presentation** (a blank deck — this becomes the macro home).
2. **File → Save As** → set **File Format: PowerPoint Macro-Enabled
   Presentation (.pptm)** → name it `DeckOps.pptm`, and save it into the **vault**
   (a stable location reused across every talk, e.g. `<vault>/.deckops/DeckOps.pptm`)
   so it's created once and reused — not regenerated per deck.

Gotcha to warn about up front: if PowerPoint ever shows **"Visual Basic macros
will be removed if you save the file in this format"**, the user is saving a
`.pptx` — tell them to click **Cancel** and save as `.pptm` instead. A real
deck must never carry the macro.

## Step 3 — Import the macro

**First, on an installed tile, restore the stripped drivers** (a dev checkout
already has them, so this is a no-op there):

```bash
python3 skills/presentation-creator/scripts/sync-deck-drivers.py materialize
```

This recreates `RunDeckOps.bas` and the eight `.applescript` drivers from their
committed `.txt` mirrors. (The `.sh` wrappers also self-restore the `.applescript`
drivers on first run via `ensure-drivers.sh`; only the `RunDeckOps.bas` you import
by hand here needs the explicit step.)

Then ask the user to open the VBA editor (**Tools → Macro → Visual Basic Editor**,
or ⌥F11), select **DeckOps.pptm's** project in the left pane, then
**File → Import File…** and choose
`skills/presentation-creator/scripts/RunDeckOps.bas`. Save `DeckOps.pptm` (⌘S).

To UPDATE the macro later (e.g. after a tile update): re-run the materializer with
`materialize --force` to refresh the on-disk `.bas`, then in the VBA editor
right-click the `DeckOps` module → **Remove** (No to export) → **Import File…** the
refreshed `.bas` → save.

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

## Step 6 — Every build (recurring)

Steps 1–4 are one-time per machine; this is what happens on EVERY real deck build:

1. **Open `DeckOps.pptm` first and keep it open for the entire build.** Every pass
   (`BuildDeck`, `ExpandBuilds`, speaker notes, backgrounds, QR) drives a macro
   that lives in this file; the scripts call it in the running PowerPoint instance.
   If `DeckOps.pptm` is closed (or PowerPoint quits) mid-build, the next pass fails
   with a macro-not-found error — reopen it and re-run that pass.
2. The agent runs the passes in order against uniquely-named copies:
   structural build → `ExpandBuilds` → speaker notes → backgrounds → QR.
   `ExpandBuilds` renumbers later slides, so it runs before the by-index passes
   (see `rules/deck-editing-rules.md`).
3. On the FIRST run after setup, the user clicks the macOS Automation prompt
   (Step 4). After that the agent runs the passes unattended, with no
   per-illustration prompts (images are staged into PowerPoint's container — see
   the per-illustration caveat below).
4. When the build finishes, open the output in PowerPoint **and** Keynote and
   confirm it's clean (no "Repair" prompt, art present) before trusting it.

## Google Drive caveat (important)

If decks live in a **Google Drive** "My Drive" folder (the macOS Google Drive
File-Provider mount), sandboxed PowerPoint can OPEN/read them but **cannot
create a new file there via VBA** — `SaveCopyAs` fails with E_FAIL
(`-2147467259`). `run-deck-ops.sh` works around this by saving to a local
staging folder (`~/.deckops-staging/`) and then moving the result into the Drive
destination with the shell (which writes to Drive normally). Keep using
uniquely-named copies for the base/import/output so PowerPoint's
filename-keyed open-deck cache never hands back the wrong deck.

## Powerbox prompt caveat (important)

Sandboxed PowerPoint shows a Powerbox "grant access" / "select file" prompt
whenever a VBA macro touches a file OUTSIDE its container — opening a Google-Drive
base deck or template (`Presentations.Open`), reading an illustration
(`UserPicture`), or writing the output (`SaveCopyAs` to a Drive folder E_FAILs, and
to a local `~/.deckops-staging` subdir prompts every run). On a 40-slide deck that
is dozens of clicks.

Every deck-ops wrapper avoids this by routing ALL macro file I/O through
PowerPoint's own sandbox container (`~/Library/Containers/com.microsoft.Powerpoint/Data/.deckops-stage/<pid>/`),
which a sandboxed app reads and writes with no prompt:
- `container-stage.sh` (sourced by every wrapper) provides `stage_base` — it copies
  the base deck / template / QR image into the container and opens them from there.
- `stage-images-into-container.py` stages illustration backgrounds the same way.
- The OUTPUT is saved into the container (`OUT_STAGE_DIR`), then the shell (not
  sandboxed) moves it to the Drive destination.
- A single EXIT trap in `container-stage.sh` removes the per-run staging dir;
  wrappers must NOT set their own EXIT trap (it would override that one and leak
  copies).

So a full build runs with ZERO prompts and no Full Disk Access grant. If the
container is absent (PowerPoint never launched), the wrappers fall back to the
original paths and a local output dir — prompts return, but nothing breaks.

Mac PowerPoint VBA has no `Application.FileDialog`, so a "grant one folder" macro is
impossible; container-staging is the supported no-prompt path.
