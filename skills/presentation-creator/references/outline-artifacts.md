# Outline and Derived Artifacts

`presentation-creator` owns `outline.yaml` shape and migrations. The talk block
starts in Phase 1, chapters in Phase 2, and slides/interludes in Phase 3. Keep all
of them in the same `schema_version: 2` outline. Fields and compatibility live in
[phase3-content.md](phase3-content.md) and `scripts/outline_schema.py`.

| File | Contract |
|---|---|
| `outline.yaml` | Authored source of truth, schema-validated |
| `narrative.md` | Generated TL;DR and chapter arc in partial mode; TL;DR and slide walk once slides exist |
| `script.md` | Generated rehearsal screenplay |
| `slides.md` | Generated per-slide build-sheet |
| `rhetorical-review.md` | Generated structural check report |

After each edit in Phases 1–2, regenerate the partial narrative:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/extract-narrative.py" --partial outline.yaml > narrative.md
```

Leave `argument_beats[].slide_refs` empty until slides exist. From Phase 3 onward,
validate and regenerate all four derived files after every outline edit:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/outline_schema.py" outline.yaml
"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/extract-narrative.py" outline.yaml > narrative.md
"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/extract-script.py" outline.yaml > script.md
"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/extract-slides.py" outline.yaml > slides.md
"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/check-rhetorical.py" outline.yaml > rhetorical-review.md
```

The Markdown outputs are read-only. Repair their source and regenerate them.
The validation command migrates an older outline as its owner before full
validation; non-owner consumers use `--emit-json` and never migrate.
