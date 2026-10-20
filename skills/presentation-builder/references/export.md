# Deck Export

For the requested export, use the existing deck; do not start an authoring interview. The method depends on the
speaker's `publishing_process.export_method` and platform.

Run the export script — it auto-detects PowerPoint (macOS AppleScript) or LibreOffice:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/export-pdf.py" path/to/deck.pptx [path/to/output.pdf]
```

If `output.pdf` is omitted, uses the same name with `.pdf` extension.

The script prefers PowerPoint AppleScript on macOS (if installed), falls back to
LibreOffice CLI. Read `publishing_process.export_method` from the speaker profile
to know which is expected.

---

A deck-only export does not read `outline.yaml`, the rhetoric summary, design
spec, pattern history, or `secrets.json`. Use the shared read-only core runtime.
Respect an explicit format/output and the profile's configured export instructions.
If a configured `export_script` is required, run it with the deck path substituted;
if the format is undecided, ask once. Never publish as part of export alone.

For a presenterm Markdown deck, use the existing renderer:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/render-markdown-deck.py" path/to/deck.md --output path/to/deck.pdf --flavor presenterm
```

Exit 0 emits a JSON receipt; non-zero reports the renderer/input repair on stderr.
A missing presenterm runtime is a renderer repair, not a PowerPoint fallback.
Check the requested output exists and opens as a PDF before reporting completion.
Return output and any receipt paths to the caller.
