# Vault Bootstrap and Preflight

This is the complete normative Step 1 contract for `vault-ingress`. Execute
each section in order; later sections assume every earlier gate succeeded.

**Vault discovery** — canonical path is always `~/.claude/rhetoric-knowledge-vault/`.

1. **Path exists** — use as `vault_root`, then load the database with the strict
   owner read command in
   [schemas-db.md](schemas-db.md#owner-read-and-mutation-contract).
2. **Path missing** — first-time setup: ask preferred location via `AskUserQuestion`,
   create the directory (and symlink if a custom path was chosen), then use a sole
   `initialize_database` mutation. Include database `schema_version: 1`, config
   `schema_version: 2`, and empty `talks`, `pptx_catalog`, `qr_codes`, `resources`,
   `thumbnails`, `confirmed_intents`, and `improvement_goals` arrays. The plan may
   omit `pptx_directory_exclusions`; the initializer supplies the canonical default
   defined by the [PPTX scan contract](#scan-for-pptx-files). Include that field
   only when the speaker explicitly requests a valid customization.
   Review the dry-run and apply it with `--expected-sha256 missing`; never create
   the JSON file directly.

**Schema gate** — vault-ingress owns the tracking database shape and migrations.
The stdlib-only strict reader may use the host interpreter for the initial
bootstrap read only. Read `config.python_path` from an existing database, or ask
for the interpreter path without writing the database when that field is absent.
Immediately re-read the same canonical path with that configured interpreter and
require the same SHA-256; restart discovery if the generation changed. Use the
configured interpreter for migration, queue commands, and every later toolkit
command. Run the owner migration before any other database mutation:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/migrate-tracking-database.py" \
  "{vault_root}/tracking-database.json"
```

Exit 0 writes one dry-run JSON report with `input_sha256`, source and target
schema versions, `output_sha256`, `record_counts`, `persisted_observations`,
`changed`,
`database_written: false`, `warnings`, and the deterministic backup path. A
changed report authorizes this exact apply command:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/migrate-tracking-database.py" \
  "{vault_root}/tracking-database.json" --apply --expected-sha256 "{input_sha256}"
```

Exit 0 from apply writes one JSON report with `database_written: true`, preserves
the complete original bytes under `{vault_root}/.backups/`, and atomically
installs database schema v1 with config schema v2. A current root with config
schema v1 is also a migration: root `from_schema_version` and
`to_schema_version` both remain `1`, while `record_counts.config` records the
config upgrade.

`persisted_observations` reports what the migration did to corrupt persisted
pattern observations: `repaired` counts talks whose exact inverse-schema field
swap was undone in place, `requeued` counts talks whose defect it refused to
guess at, which keep their original bytes and return to the queue with
`reprocess_reason: persisted_observation_invalid`. A non-zero count in either
field means the migration changed state and is a real write, not a no-op. The
decision predicate is `gate_persisted_observations` in
`skills/vault-ingress/scripts/migrate-tracking-database.py`. A non-empty `warnings` array means replacement
completed with a durability warning and must not be reported as a failed/no-write
run. Exit 2 writes one error object to stdout plus a diagnostic to stderr and
leaves the database unchanged. Recover or
complete every active queue claim named by the diagnostic. For an unversioned
database, use `queue-state.py ... inspect` to identify the lease and
`queue-state.py ... recover` to close it. Those two commands accept schema 0;
recovery changes only queue-lease/status state and does not stamp or migrate the
database or talk record. The existing queue transition may advance a recovered
legacy claim receipt from schema v1 to v2 while adding its release fields. Rerun
migration dry-run, then apply its new exact digest. Do not copy a digest across
runs. `queue-state.py ... normalize` and `queue-state.py ... claim` require
database schema 1.

**Config bootstrapping** — ask once per missing user-owned field and persist to the tracking
database with expectation-bound `set_config` mutations. Re-read after every
successful apply and use the new hash for the next plan. Core fields: `shownotes` (enabled, source.type, source.path_or_url,
source.talks_subdir, url.base, url.template, thumbnail_path_template,
slug_convention), `pptx_source_dir`, `python_path`, `template_skip_patterns`,
and `pptx_directory_exclusions`. The exclusion field is not a missing-field
question: initialization supplies the canonical default, while migration supplies
that default when absent or preserves an existing valid custom list. Ask about or
change it only when the speaker explicitly wants to customize directory pruning.
See [schemas-db.md](schemas-db.md) for the full schema and
[schemas-config.md](../../vault-profile/references/schemas-config.md) for
field-by-field semantics and migration notes.

`python_path` is the interpreter authority for every operational command below;
never fall back to whichever `python3` happens to be on `PATH`. Installed plugin
bundles do not include `pyproject.toml`, so immediately probe the configured
runtime with the shipped stdlib-only checker:

Remove obsolete config fields with `delete: true`; never pass the missing marker
as a `value`. If the owner read exposes that marker as a present legacy value,
use the expectation-bound deletion in
[schemas-db.md](schemas-db.md#owner-read-and-mutation-contract), then re-read
before another config write.

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/check-runtime.py" \
  --lanes core,pdf,pptx
```

All owner-authored tracking writes below require database schema 1 and config
schema 2 after this
gate. Preserve every independent record version and validate the complete
candidate before installing it. Only `migrate-tracking-database.py` may move
schema 0 to schema 1; its hash precondition binds replacement to the exact input
bytes as documented above.

Core requires Python 3.10+ and PyYAML and is blocking. The PDF lane requires
pypdf plus exactly `psutil==7.2.2`; the PPTX lane requires python-pptx plus the
same exact psutil version. Both parser lanes run behind bounded worker
supervision. Preserved source-video evidence has its own narrow `source-video`
lane requiring exactly `psutil==7.2.2` plus `ffprobe`; require that lane before
preflight, persistence, queue, or profile work will inspect a local recording
declared by `structured_data.video_extraction.source_video_path`,
`video_local_path`, or `video_path`.
The canonical vault locator may be the configured symlink; the PDF
boundary maps that trusted root to storage while still rejecting every
descendant symlink/reparse redirect. Trusted-root bindings retain the directory
object's stable identity and policy attributes, not mutable child-content size or
timestamps; PDF and PPTX leaf generations remain exact. The checker emits report
schema v2 and records exact pins under
each lane's `required_module_versions`; a mismatched version is unavailable. A
missing optional lane is reported as degraded and must not erase a healthy
transcript or alternate slide lane.
Require a lane before using it, for example `--require-lanes core,pdf`. Remote
Drive acquisition additionally needs the `gdown` module; captions need
`youtube-transcript-api`; audio download fallback needs `yt-dlp`; rendered PDF
inspection needs `pdftoppm`; video extraction needs exactly `Pillow==12.3.0`,
`ImageHash==4.3.2`, `numpy==2.2.6`, and `filelock==3.32.2`, plus `ffmpeg` and
`ffprobe`; local Whisper needs `mlx-whisper` and `ffprobe`.
Inspect those with the checker's `google-drive`, `captions`,
`youtube-download`, `pdf-render`, `video`, and `whisper` lanes as selected talks
require; use `source-video` for evidence over an already-preserved recording and
`video` for frame extraction. Each lane is independent: a failed optional
import/tool disables only that lane. Import failure details appear under the
lane's `module_failures`;
dependency absence, initializer exceptions, native crashes, timeouts, and
invalid child results degrade an optional lane or block a required lane without
breaking the one-JSON contract. The checker writes a recovery instruction to
stderr whenever a lane is unavailable.

**Scan for new talks:** run the deterministic scanner in its default read-only
mode:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/scan-shownotes.py" \
  "{vault_root}/tracking-database.json"
```

Read the structured report before any mutation. `add` and `update` entries are
safe deterministic proposals; `review_required` entries need a human decision.
The scanner uses exact filename identity, derives supported YouTube and Google
Drive IDs, and keeps every matching `source_rejections` identity inactive.
For comparison only, title equality applies Unicode NFC and maps straight/curly
single and double quote glyphs to the same narrow equivalents. It preserves
case, other punctuation, and wording. Conference equality applies NFC plus
casefold only and preserves whitespace. The scanner never writes these
comparison transforms back to the database or report. Incomplete metadata,
substantive conflicts, and normalized filename collisions remain proposals.
Disabled, `remote_url`, and `none` sources return a structured no-op.

For an exact-filename match, pass the stored and proposed title plus stored
conference/date context to the shared title-agreement contract documented in
[schemas-db.md](schemas-db.md#shownotes-scanimport-report). Agreement keeps the
authored title unchanged. Disagreement emits `existing_title_conflict` and
leaves the entry `review_required`.

Apply the reviewed deterministic proposals with the same command plus
`--apply`. Only `add` and `update` entries mutate the tracking database. New
records receive current `schema_version` and status `"pending"`; exact-filename
updates fill empty fields without overwriting established values. The write is
atomic and rejects a tracking-database symlink. See
[schemas-db.md](schemas-db.md#shownotes-scanimport-report)
for the complete report and mutation contract.

**Scan for .pptx files:** Do not recursively glob the source tree. Run one bounded
directory extraction, which owns deterministic discovery, symlink/reparse-point
rejection, and aggregate file/input/output/wall budgets:

Read the exact `config.template_skip_patterns` and
`config.pptx_directory_exclusions` arrays from the strict owner-read result.
Set `{template_skip_arguments}` to one separately shell-quoted
`--skip=<exact-value>` argument per array entry, preserving its order. An empty
array produces zero arguments; never add an implicit default.
Set `{directory_exclusion_arguments}` the same way, using one
`--exclude-directory=<exact-component>` argument per exclusion. These are
case-insensitive exact directory-name components at any descendant depth—not
substrings, paths, globs, or regular expressions. The sole config-v2 owner-default
source is
`skills/vault-ingress/scripts/pptx_discovery_contract.py::DEFAULT_PPTX_DIRECTORY_EXCLUSIONS`;
do not copy or reconstruct that list in workflow prose.
Do not broaden that code-owned default to plausible authored-content directory
names without an explicit speaker-specific customization.

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/pptx-extraction.py" \
  --directory "{pptx_source_dir}" {template_skip_arguments} \
  {directory_exclusion_arguments}
```

Require exit status zero before consuming the public schema-v1
`pptx_directory_batch` envelope's `results[]` or `skipped[]`. A
whole-root discovery failure exits nonzero and emits a compact top-level
`error` containing the public `reason_code` plus any closed
`details.supervisor_reason_code`; report both and stop the PPTX scan. Never
reinterpret that failure's root `skipped[]` receipt as a successful empty scan.

On exit zero, `complete` is true exactly when `incomplete_reason_codes` is
empty. A partial scan deliberately still exits zero so its safely extracted
per-deck results can be reviewed and persisted. Preserve those results and all
skip receipts, report the incomplete reasons, and rerun after remediation. Only
`complete: true` proves that all eligible descendants were considered; without
it, never claim full catalog coverage, infer that a missing deck does not exist,
or convert an empty result into an absence conclusion. Legacy unversioned
`{"results": ..., "skipped": ...}` output has unknown completeness and must be
rerun before any coverage or absence claim.

Use root-relative `results[].pptx_path` identities to fuzzy-match `talks[]` entries
and retain every `skipped[]` receipt. Treat the envelope's `complete` and
`incomplete_reason_codes` fields as authoritative; never reclassify receipts by
reason string. Configured exclusion dirents use a separate bounded
policy-enumeration allowance rather than the eligible-entry budget, so policy
pruning cannot hide an authored sibling; exhausting that allowance fails closed.
Directory intent must remain explicit:
do not omit `--directory` or
pre-probe the root with `find`, a recursive glob, or a per-file loop. The bounded
authenticated discovery worker owns root validation and enumeration. Report counts,
then persist each reviewed result with a `record_pptx`
mutation and `schema_version: 3`, including the exact prior catalog record and, for
a match, the talk's exact prior `pptx_path` expectation. A record whose deck has
had no extraction attempt carries `visual_evidence: null`; a record claiming
visual evidence carries the receipt binding extractor schema, pipeline version,
exact source fingerprint, and artifact identity.

A matched record also carries `identity_assessment`: the assessment produced by
`skills/vault-ingress/scripts/pptx_talk_identity.py` for that exact deck against
the database's talks, serialized whole. Obtain it by assessing the deck BEFORE
deciding the binding — the assessment is what decides it, not a confirmation of a
decision already made. An unmatched record carries `identity_assessment: null`.
The writer rejects an assessment that does not authorize the binding; the
predicate is `binding_refusal` in
`skills/vault-ingress/scripts/pptx_talk_identity.py`, shared with preflight. Route a rejected deck to owner review
rather than persisting it.

Rows bound before that writer existed carry no assessment, and preflight blocks
every one of them. Assess the whole catalog at once with:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/sweep-pptx-talk-identity.py" \
  "{vault_root}"
```

Read-only. Stdout is one JSON object carrying `disposition_counts`,
`unresolved_binding_count`, and a `rows[]` entry per catalog row. Exit 0 means
the catalog was assessed — contradictions included, since this reports rather
than gates; preflight is the gate. Exit 2 means the database is unusable and
writes an error object with a closed `code` to stdout plus one diagnostic line
to stderr; stop there and repair the database, never consume a failed report as
if the catalog were clean. The disposition taxonomy and the signals it observes
are in the script's module docstring.

`binding_contradicted` names a deck feeding one talk's evidence to another and
is owner-review work before any reparse; `binding_confirmed` supplies the
assessment a `record_pptx` write carries. `--dispositions` narrows the reported
rows without changing the counts.

`--emit-mutations` adds two owner plans, each built from the whole catalog and
never from the `--dispositions` view. `mutation_plan` severs every binding the
sweep could not prove, through the `sever_pptx_talk_binding` mutation, which
clears the catalog row's `talk_filename` and the talk's own `pptx_path`
together; its `unseverable[]` names every row it could not address, so a
complete-looking plan cannot hide a binding it left in place. `proof_plan`
stores the assessment behind every confirmed binding through `record_pptx`.

Apply one plan, re-run the sweep, then apply the next. Both plans carry
exact-old-value preconditions on both sides of each binding, so a plan built
before the other was applied fails loudly rather than severing a binding nobody
assessed. Review each plan before applying it: severing is how a wrong binding
stops feeding a talk, and the sweep decides nothing.
Never decide from
`visual_extracted` alone whether a deck needs extraction. Run:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/classify-pptx-evidence.py" \
  "{vault_root}"
```

It fingerprints each deck and each extraction artifact on disk, classifies
every catalog record, and prints one JSON object; extract exactly the records
whose `needs_extraction` is true. Argument, output shape, and exit codes are in
the script's module docstring. A legacy record's bare claim reads as
unknown-generation evidence, and an unreadable deck or a deleted artifact reads
as unverified — never as current (see [schemas-db.md](schemas-db.md) —
`pptx_catalog` v1 -> v2). See
[schemas-db.md](schemas-db.md) for the PPTX extraction output
schema (per-slide visual data, shape types, global design stats).
Consume current schema v4. A v0/v1 record has unknown timing, not zero timing;
v2 has the pre-build timing lanes but lacks raw build-list evidence,
archive-recovery, and exact native/render audit receipts; v3 lacks required
shape/image capability bindings. Regenerate v0-v3
output for current analysis. An unknown future
schema is unusable until this reader is updated. The vault-profile layout-only
consumer is the documented v1/v2/v3/v4 exception for the unchanged
`template_layouts` field. Non-empty `archive_recovery` is degraded evidence:
restore or re-export a required native deck before claiming or returning it.

**Pattern taxonomy recovery:** See [processing-rules.md](processing-rules.md) for the queue-owned
contract. Step 2 normalization deterministically routes processed results outside
the active pattern-scoring generation back to `needs-reprocessing`; do not infer
generation currency from processing date or hand-edit those statuses.

**Pattern catalog preflight:** Before source selection or re-analysis, run:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/audit-pattern-catalog.py"
```

Stdout is stable JSON. Exit 1 means structural catalog errors: stop before
scoring. Exit 0 may include `semantic_debts`; present those for human review and
do not auto-edit names, aliases, definitions, or graph relationships. The input,
report, and no-write contracts are defined in
[pattern-catalog-contract.md](pattern-catalog-contract.md).

**Conditional source-video runtime gate:** Use only the strict owner-read database
payload to determine whether the upcoming source preflight may inspect any
preserved local recording declared by
`structured_data.video_extraction.source_video_path`, `video_local_path`, or
`video_path`. When it may, require the configured runtime before invoking
preflight:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/check-runtime.py" \
  --lanes core,source-video --require-lanes core,source-video
```

Do not pre-open, hash, hydrate, or invoke `ffprobe` directly on the recording.
The supervised source-video assessor owns availability, exact-generation hashing,
media inspection, caching, and diagnostics. Repair a failed required lane before
allowing preflight to inspect that recording. An unavailable or unreadable video
disables only source-video evidence; it must not erase or invalidate independently
verified transcript, rendered-PDF, or native-PPTX evidence.

**Source/identity preflight:** After bootstrapping and scanning, and before talk
selection or re-analysis, run the read-only offline gate:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/preflight-vault.py" {vault_root}
```

Exit 1 means one or more blocking integrity errors (identity disagreement,
unqualified duplicate recording, invalid source claim, or a claimed completed
artifact that is missing): stop and repair those records/artifacts before
processing. Exit 0 may still carry warnings for legacy evidence gaps or pending
artifacts; report them, but they do not make the vault unusable. Exit 2 carries
a real report whose single blocking `preflight_unexpected_failure` finding means
the gate never completed — treat the vault as unverified, not clean, per
[Entrypoint Failure Contracts](entrypoint-failure-contracts.md). The stable JSON
report and evidence shape are defined in
[source-identity-preflight.md](source-identity-preflight.md).

After the offline gate, capture and compare live YouTube provider evidence:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/audit-source-identities.py" {vault_root}
```

This networked audit invokes `yt-dlp` once per distinct active YouTube ID and
prints deterministic JSON without changing the vault. Review every proposed
`source_identity` block and finding, especially `likely_non_delivery_clip` and
`same_id_cross_talk_collision`. Provider uploader is not speaker evidence,
upload date is not recorded date, and the provider webpage URL must never be
auto-applied as an active source. See
[source-identity-audit.md](source-identity-audit.md).

Only after that human review, write a source-repair plan containing supported
facts and exact old-value preconditions, then dry-run it before applying:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/apply-source-repairs.py" \
  {vault_root}/tracking-database.json source-repair-plan.json
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/apply-source-repairs.py" \
  {vault_root}/tracking-database.json source-repair-plan.json --apply
```

The apply command validates the whole plan before mutation, refuses active queue
claims, writes a byte-for-byte backup under `{vault_root}/.backups/`, and replaces
the DB atomically. Re-run the preflight after applying; do not claim work until
blocking findings reach zero.

The summary's status block is owner-generated, never hand-edited. Refresh it at
safe checkpoints — after migration or recovery, after normalization, and after a
batch persists — with:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/render-vault-status.py" \
  "{vault_root}" --generated-at "{iso_timestamp}"
```

That is a dry run: it writes nothing and prints one JSON object on stdout.
`--summary` overrides the summary path; `--generated-at` is required and is
recorded in the block, so a render is reproducible.

The report fields this workflow reads:

- `summary_sha256` — the digest to pass back as `--expected-sha256`
- `changed` — false means the installed block already matches; skip the apply
- `summary_written` — true only after an apply installed new bytes
- `status` — the derived counts, and `block` the exact text that would install

Apply with the digest the dry run reported:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/render-vault-status.py" \
  "{vault_root}" --generated-at "{iso_timestamp}" \
  --apply --expected-sha256 "{summary_sha256_from_dry_run}"
```

Exit 0 succeeded. Exit 3 is the precondition alone: the summary's bytes are no
longer the ones the digest named, so re-run the dry run and apply with the new
digest — never force it. Exit 2 is every other failure — the database or the
summary could not be read, locked, or installed — and its JSON carries a typed
`code` plus an actionable `error`; act on that, do not retry blindly.

The block carries the database SHA-256 it was derived from, so a consumer can
tell a stale block from a current one; the tracking database stays the authority
and prose counts are never trusted on their own.

Read `rhetoric-style-summary.md` and `slide-design-spec.md`. Report:
"X processed, Y remaining. PPTX: A cataloged, B matched, C extracted."
