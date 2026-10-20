# Presentation Runtime and Task Context

Use this shared bootstrap for authoring, building, publishing coordination, and
CFP work. Select the action before opening vault documents. A forwarded task uses
its destination skill's bootstrap; forwarding alone needs no vault load.

## Resolve the runtime

Set `host_python` to the host's explicit absolute Python interpreter. The resolver
is stdlib-only; it is the only toolkit command run under the host interpreter.

```bash
"{host_python}" "{speaker_toolkit_root}/skills/shownotes-publisher/scripts/resolve-runtime.py" --read-only --lane outline
```

Use `--lane core` for CFP/catalog work and standalone deck export. Omit
`--read-only` immediately before publishing/tracking side effects: that requires
the owner-current database. Local authoring, deck builds/edits/exports and resource
extraction use the read-only compatibility mode; it grants no tracking-write
permission. A catalog Markdown edit does not mutate the tracking database.

Input: optional `--database <path>`; otherwise the documented vault locator
`~/.claude/rhetoric-knowledge-vault/tracking-database.json`.
On exit 0, take `python_path`, `vault_root`, `database`, `database_sha256`,
`database_state`, and `lane` from the emitted JSON. Every later toolkit Python
command uses that configured interpreter. Do not derive the root from stale
`config.vault_root`, the working directory, or a PATH interpreter.

The resolver composes strict owner reads under the host and configured
interpreters and requires matching bytes/generation. Its module docstring owns
the status, runtime-probe and failure contracts. It never migrates the database.

On `database_generation_conflict` or `database_mismatch`, repeat discovery once.
For other failures, invoke `Skill(skill: "vault-ingress")` with repair-only
`runtime_repair: {reason_code, lane, database}` from the refusal, using the selected
lane. Read [the repair contract](../../vault-ingress/references/runtime-repair.md).
Re-run against the same database after repair. A second refusal ends the task
with the actionable diagnostic; never start an ingest or choose another Python.

## Load only the selected context

All paths below are under the resolved vault root except talk-owned files.
A missing required input blocks that action; an unrelated missing file does not.
Project the profile before loading it into agent context:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/read-task-profile.py" "{vault_root}/speaker-profile.json" --task "{profile_task}"
```

Choose `profile_task` from the selected action below. Exit 0 emits
`{task, profile_available, profile}` with selected configuration only. The script's
`TASK_FIELDS` owns the field selection. It neither validates the owner profile nor
authorizes historical claims; it never emits the history/badge branches. Owner
validators and guardrail/history scripts still receive the original profile path.
Read only the returned projection as context unless a later phase explicitly
requires an authorized history source. Add `--allow-missing` for summary-only
CFP/authoring or an export whose format is already supplied; a present invalid
profile always refuses. For catalog-only reads, no profile projection is needed.

Use tasks `authoring`, `cfp`, `catalog`, `build-pptx`, `build-presenterm`, `edit`,
`export`, `resources`, `qr`, `delivery`, or `publishing` as appropriate. During
architecture's visual decisions, also select `build-pptx` for its visual/template
configuration. Do not project publishing data for an isolated CFP or export.

| Action | Additional context to read |
|---|---|
| Author/adapt a talk | `rhetoric-style-summary.md`, `speaker-profile.json` when present; design spec only for visual decisions; existing talk analysis for adaptation |
| CFP | Available speaker profile, voice/confirmed-intent portions of the summary, relevant `sessions-catalog.md` entry, supplied CFP requirements |
| Catalog read/update | Relevant catalog entry; profile/voice only when composing prose |
| PowerPoint build/visual edit | Profile infrastructure/design rules, `slide-design-spec.md`; approved outline and `slides.md` for a build |
| Presenterm build | Approved outline, `slides.md`, profile engine/theme settings; visual rules when relevant |
| Standalone deck export | Existing deck, output path/format, profile export settings; no outline required |
| Resource extraction | Current outline through the non-owner reader; publishing profile when persisting or publishing |
| QR | Current outline, profile QR/URL settings, final deck if inserting; only selected-provider credentials for direct API use |
| Delivery preparation | Outline timing, profile additional steps, requested go-live patterns |
| Shownotes/recording or thumbnail | Invoke the existing owner skill with supplied paths/URLs; it loads its own context |

For a first catalog, an absent `sessions-catalog.md` means no saved entries yet.
Create it only when an approved catalog update is requested. Authoring/CFP work
can use summary-only mode when a speaker profile has not been generated; do not
invent structured history or configuration. Ask for missing task-specific choices.
The prose summary is
voice/nuance; the profile is structured configuration. Before making historical
pattern claims, read [pattern-history-authorization.md](pattern-history-authorization.md)
and run its status command. CFPs, exports and QR codes do not need that lane.
Compare profile `generated_date` with summary `Last updated` only when both are
loaded; warn on a stale profile without disabling independent configuration.

## Read an outline as a non-owner

```bash
"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/outline_schema.py" --emit-json path/to/outline.yaml
```

Exit 0 emits the validated current outline JSON. Non-zero refuses without editing
or migrating it. Invoke `Skill(skill: "presentation-creator")` with the exact
outline path and diagnostic, then retry the original action after repair.
Do not re-parse YAML to bypass a refusal.

## Persist through the owner

The [owner compatibility contract](../../vault-ingress/references/schemas-db.md#schema-versioning)
defines readable and writable generations.

Read [the owner mutation contract](../../vault-ingress/references/schemas-db.md#owner-read-and-mutation-contract)
before tracking writes. Re-resolve without `--read-only` before paired effects,
re-read their current inputs, dry-run the typed mutation, inspect its changes,
apply against the reported SHA, and strictly re-read. A successful read-only
bootstrap or a previous run's hash is not write authority.
