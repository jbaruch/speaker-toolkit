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

Every path below is absolute. `{speaker_toolkit_root}` is resolved in
`SKILL.md`; `{vault_root}` is `config.vault_root` from the tracking database.
Expand both before showing a command or a path to the user — they cannot resolve
a placeholder, and Step 3 in particular hands them a path to type.

## Step 0 — Ask what is actually missing

Never assume this is a first run, and never assume it isn't:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/deckops-doctor.py" \
  --vault-root "{vault_root}"
```

Read-only: it opens nothing, saves nothing, and never launches PowerPoint. It
prints a JSON report whose `status` says what to do — `next_step` carries the
same thing as one sentence:

| `status` | What it means | Go to |
|---|---|---|
| `ok` | Set up and current | Step 6 |
| `setup_required` | No macro container on this machine | Step 1 |
| `macro_unreachable` | Container missing from the running PowerPoint, macros off, or module never imported | Steps 1–3 |
| `powerpoint_not_running` | Set up; PowerPoint just isn't open | Step 6 |
| `macro_stale` | Container holds an OLD build of the macro | Step 3 (Updating) |
| `driver_drift` | Shipped drivers don't match their mirrors | Reinstall the plugin |
| `unsupported_platform` | Not macOS | No deck build is possible here |

Pass `--offline` to skip the live PowerPoint probe; you then get `setup_required`
versus everything-else, and no reading on whether the macro is current.

Heads-up for installed plugins: `tessl install` ships only `.md/.py/.json/.sh/.txt`
and STRIPS `.bas`/`.applescript`, so `RunDeckOps.bas` and the `.applescript`
drivers aren't on disk after install. The doctor and the `.sh` wrappers restore
them automatically from their committed `.txt` mirrors; a dev checkout already
has them. Nothing here requires a manual restore.

## Step 1 — Enable VBA macros

Ask the user to open **PowerPoint → Settings → Security & Privacy** and enable
macros ("Enable all macros", or enable + trust). Proceed to Step 2.

## Step 2 — Create the macro container `DeckOps.pptm`

The macro must live in a macro-enabled file, never in a real deck. The container
goes at ONE canonical path, reused across every talk — the doctor and every
error message look for it there:

```
{vault_root}/.deckops/DeckOps.pptm
```

Create the directory yourself first, so the Save dialog has somewhere to land:

```bash
mkdir -p "{vault_root}/.deckops"
```

Then ask the user to:
1. **File → New Presentation** (a blank deck — this becomes the macro home).
2. **File → Save As** → set **File Format: PowerPoint Macro-Enabled
   Presentation (.pptm)** → name it `DeckOps.pptm` and save it to the path above.
   In the Save dialog, ⇧⌘G opens "Go to Folder" — paste the expanded directory
   there. A dot-directory does not appear in the file list; ⇧⌘. toggles hidden
   files if they need to see it.

Gotcha to warn about up front: if PowerPoint ever shows **"Visual Basic macros
will be removed if you save the file in this format"**, the user is saving a
`.pptx` — tell them to click **Cancel** and save as `.pptm` instead. A real
deck must never carry the macro.

## Step 3 — Import the macro

**First, put the `.bas` somewhere the user can actually reach it.** On an
installed plugin the module lives under a hidden `.tessl/` directory, which
PowerPoint's Import panel does not show — so export a copy next to the container:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/sync-deck-drivers.py" \
  export --to "{vault_root}/.deckops"
```

It prints the exported path as JSON (`{"exported": "..."}`). Materializes the
`.bas` from its mirror first if the install stripped it, and refreshes a stale
earlier export. Give the user that exact absolute path.

Then ask the user to open the VBA editor (**Tools → Macro → Visual Basic Editor**,
or ⌥F11), select **DeckOps.pptm's** project in the left pane, then
**File → Import File…** and choose the exported `RunDeckOps.bas`. In that panel
⇧⌘G opens "Go to Folder" and ⇧⌘. toggles hidden files — the `.deckops` directory
starts with a dot, so one of the two is needed. Save `DeckOps.pptm` (⌘S).

**Updating the macro later.** A plugin update ships a new macro; the copy already
imported into `DeckOps.pptm` keeps running the OLD code, silently, because nothing
can read VBA source back out of a saved `.pptm`. That is what `macro_stale`
detects — the module carries a content stamp and the doctor asks the running
PowerPoint for it. On `macro_stale`: re-run the `export` command above, then in
the VBA editor right-click the `DeckOps` module → **Remove** (No to export) →
**Import File…** the refreshed `.bas` → save. Re-run Step 0 to confirm `ok`.

## Step 4 — Grant Automation consent (first run only)

The first time a script drives PowerPoint, macOS shows an **Automation** consent
prompt. Tell the user it is GUI-only — it cannot be approved headless — so they
should run the first invocation themselves (or be at the machine to click
**OK**): System Settings → Privacy & Security → Automation → allow the terminal
to control PowerPoint. After consent is granted once, the agent may run
`run-deck-ops.sh` itself.

## Step 5 — Smoke-test before any real edit

Given the history of lost work with other tools, always test before touching a
real deck. One script does the whole thing — it copies the template to a
uniquely-named base, builds the shipped 3-slide op sequence (layout 0 and a free
text box only, so it runs against any template), and prints where the output
landed:

```bash
bash "{speaker_toolkit_root}/skills/presentation-creator/scripts/deckops-smoke-test.sh" \
  "{template_pptx_path}"
```

`{template_pptx_path}` is `infrastructure.template_pptx_path` from the speaker
profile; the template is read-only. An optional second argument sets the output
directory. It prints `{"ok":true,"output":"<path>","slides":3,"base":"<path>"}`
and exits non-zero when no deck was produced. `DeckOps.pptm` must be open
(Step 6).

It passes when all four hold:
1. The script exits 0 and prints `{"ok":true,...}`.
2. The output has exactly 3 slides, titled "DeckOps smoke test", "Slide 2 of 3",
   "Slide 3 of 3".
3. It opens in **PowerPoint** with no "Repair" prompt.
4. It opens in **Keynote** with no "Repair" prompt.

Anything else: re-run Step 0 and follow `next_step`. Only after a clean pass run
the real edit. Delete the throwaway files.

## Step 6 — Every build (recurring)

Steps 1–4 are one-time per machine; this is what happens on EVERY real deck build:

1. **Open `DeckOps.pptm` first and keep it open for the entire build.** Every pass
   (`BuildDeck`, `ExpandBuilds`, speaker notes, backgrounds, QR) drives a macro
   that lives in this file; the scripts call it in the running PowerPoint instance.
   If `DeckOps.pptm` is closed (or PowerPoint quits) mid-build, the next pass fails
   with a macro-not-found error — reopen it and re-run that pass.
2. Run Step 0 once before the first pass and require `ok`. It is the cheap way to
   catch a closed container or a stale import before a 40-slide build half-finishes.
3. The agent runs the passes in order against uniquely-named copies:
   structural build → `ExpandBuilds` → speaker notes → backgrounds → QR.
   `ExpandBuilds` renumbers later slides, so it runs before the by-index passes
   (see `rules/deck-editing-rules.md`).
4. On the FIRST run after setup, the user clicks the macOS Automation prompt
   (Step 4). After that the agent runs the passes unattended, with no
   per-illustration prompts (images are staged into PowerPoint's container — see
   the per-illustration caveat below).
5. When the build finishes, open the output in PowerPoint **and** Keynote and
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

This applies to `DeckOps.pptm` itself only for creation: saving it into a Drive
vault in Step 2 is a normal GUI save, which Drive accepts. The macro never writes
to its own container.

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
