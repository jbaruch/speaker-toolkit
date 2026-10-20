# Outline Repair Handoff

This is a bounded repair, not a new talk or ingestion run. Resolve the read-only
outline runtime from [runtime-and-context.md](runtime-and-context.md). No rhetoric
summary, design spec, pattern history, or secrets are required to migrate a file.

```bash
"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/outline_schema.py" --migrate path/to/outline.yaml
```

Input: the caller's exact outline path. Exit 0 emits `{ok, path, migrated, ...}`;
a schema-1 partial outline can migrate before slides exist. Exit 1 names the
required source repair; fix only the reported problem and re-run. Unsupported or
unparseable input is not permission to invent talk content.
For a version-only handoff, return the migrated path; the caller retries its
refused read. A successful migration does not repair unrelated validation errors.

When the caller named another defect, repair that specific source field before
returning. For a missing engine, load the relevant projected engine/mode settings,
confirm the engine/theme with the author, and write `talk.engine`, `deck_theme`,
and `engine_source` as the outline owner. For other validation errors, use the
field contract in [phase3-content.md](phase3-content.md); preserve approved content.
Ask only for missing author-owned facts rather than restarting the interview.

Validate a complete outline and regenerate its artifacts with
[outline-artifacts.md](outline-artifacts.md). For an unfinished Phase 1–2 outline,
use partial narrative validation instead. Return only when the named defect is
repaired; an unresolved defect remains an explicit blocked action, not a successful
handoff. The caller then retries the original build/read. Finish here.
