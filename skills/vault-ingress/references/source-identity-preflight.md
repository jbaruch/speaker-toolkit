# Vault Source & Identity Preflight

`skills/vault-ingress/scripts/preflight-vault.py` is the read-only integrity
gate before ingress selection or re-analysis. It accepts either the vault root
or `tracking-database.json` as a native absolute locator, performs no network
access and makes no writes:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/preflight-vault.py" \
  ~/.claude/rhetoric-knowledge-vault/
```

Stdout is one JSON report. Exit `0` means there are no blocking findings (the
report may contain warnings); exit `1` means at least one integrity finding is
blocking. Invocation errors use argparse's exit `2` and still emit a blocking
JSON report. A missing, unreadable, malformed, or structurally invalid tracking
database is itself a blocking integrity finding.

## Trusted vault-root authority

Every ingress reader derives the same artifact root before it assesses,
caches, persists, or renders evidence. The native absolute parent of
`tracking-database.json` is the primary authority. When preflight is invoked
with a vault root, that CLI root must be lexically equal to the database parent.
`config.vault_storage_path` may be absent or null, in which case the database
parent is used; every other present value must be a native absolute root and
must be lexically equal to that parent.

Preflight labels a raw input by its final basename before any `Path`
materialization or filesystem access. A case-insensitive exact
`tracking-database.json` basename is a `database_path` authority; every other
input is a `cli_root` authority. The same lexical decision controls how the
validated native absolute path is interpreted, so a relative direct database
locator fails as `vault_root_database_path_invalid` rather than being relabeled
as a vault directory.

Root comparison is lexical and host-native. It does not expand `~`, rebase a
relative value from the process cwd, translate a foreign absolute flavor,
resolve symlinks, stat the filesystem, or infer that two different locators
reach the same storage. Invalid database, CLI, and config authorities fail with
closed path-neutral reasons; a disagreement names only the authority pair.
Repair the invocation/config explicitly before reprocessing. No reader silently
migrates or rewrites a stored root.

### Repair a stored root assertion

Read the database through its owner command before constructing a repair. For
example, if that read reports the exact stored value `"C:vault"`, remove the
invalid assertion and let the database parent remain authoritative with this
expectation-bound mutation plan:

```json
{
  "schema_version": 1,
  "mutations": [{
    "kind": "set_config",
    "path": ["vault_storage_path"],
    "expect": "C:vault",
    "delete": true
  }]
}
```

Use the exact decoded value from the owner read in `expect`; JSON null and an
absent key are different expectations. If the assertion should remain explicit,
replace `"delete": true` with `"value": "<native-absolute-database-parent>"`.
That value must be the lexical native parent of `tracking-database.json`, not a
symlink-resolved alias.

Run the plan as a dry run, review its `changes`, then bind apply to the dry
run's exact `input_sha256`:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/read-tracking-database.py" \
  "{vault_root}/tracking-database.json"

"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/mutate-tracking-database.py" \
  "{vault_root}/tracking-database.json" vault-root-repair-plan.json

"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/mutate-tracking-database.py" \
  "{vault_root}/tracking-database.json" vault-root-repair-plan.json \
  --apply --expected-sha256 "<input_sha256-from-dry-run>"

"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/read-tracking-database.py" \
  "{vault_root}/tracking-database.json"

"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/preflight-vault.py" \
  "{vault_root}"
```

The second owner read must show the applied generation. Preflight must then
report no trusted-root blocking finding before queue normalization, claiming,
persistence, analysis rendering, or profile generation resumes.

Use `scripts/apply-source-repairs.py` for catalog metadata fixes. Its plan
requires an exact `expect` map for every record, permits only source/queue
repair fields, supports explicit `set` and `clear` operations, and is dry-run by
default. `--apply` refuses active claims, then uses the shared owner transaction
to create an exact backup in `.backups` and replace the database. The never-
overwritten backup name includes the exact input SHA-256 and the transaction
verifies that binding under its lock. Use `{"$missing": true}` in `expect` when
absence rather than JSON null is the required precondition.

Its report schema is v2. In addition to the reviewed `changes`, it returns
`input_sha256`, `output_sha256`, `database_written`, `backup`,
`durability_state`, and `warnings`. `installed_directory_fsync_failed` and
`installed_verification_failed` mean the install syscall succeeded; inspect the
live database and exact output hash before retrying.

When fresh provider facts are needed, run the networked, read-only
`scripts/audit-source-identities.py` after this offline gate and before writing
the repair plan. Its provider metadata proposal is deliberately not an apply
plan; see [source-identity-audit.md](source-identity-audit.md).

## Severity contract

- `blocking` means stored claims disagree, identities collide, or a completed
  talk claims an artifact that is absent. Stop selection and repair the source
  record/artifact first.
- `warning` means a legacy evidence field is absent, a comparison cannot be
  made, or a pending/processable talk has not acquired an expected artifact
  yet. Warnings are reported but do not make the vault unusable.

The whole `source_identity` block is optional. Its absence on a legacy talk is
not a finding. Missing evidence *inside an existing block* is a warning. Invalid
or contradictory recorded evidence is blocking.

## Report schema (v1)

```json
{
  "schema_version": 1,
  "ok": false,
  "database": "/vault/tracking-database.json",
  "vault_root": "/vault",
  "talk_count": 2,
  "blocking_count": 1,
  "warning_count": 0,
  "summary": {
    "by_severity": {"blocking": 1, "warning": 0},
    "by_code": {"youtube_id_mismatch": 1}
  },
  "findings": [{
    "severity": "blocking",
    "code": "youtube_id_mismatch",
    "talk_index": 1,
    "filename": "talk.md",
    "field": "youtube_id",
    "message": "video_url and stored youtube_id identify different recordings",
    "expected": "IDFromTheURL",
    "actual": "StoredWrongID",
    "artifact_path": null
  }]
}
```

All finding keys are always present. Findings and `summary.by_code` are sorted,
so the same filesystem state produces byte-for-byte equivalent decoded data.
Paths are absolute. Consumers route on `severity` and `code`, never on message
text.

An unusable owner-schema finding retains the assessment's closed
`reason_codes` in structured `actual` detail. A config-version failure names
`config.schema_version`, expects readable generations `[1, 2]`, and reports the
stored config generation separately from those reasons; it is not mislabeled as
a root-schema failure.

`database` and `vault_root` are nullable authority fields. When raw database or
CLI input is rejected before admission, both are null, `talk_count` is zero,
and the report contains one path-neutral blocking finding. Once the direct
input is admitted, they remain its lexical native absolute database/root paths,
including when a later configured-root mismatch blocks the run.

Trusted-root findings use this closed reason family:

| Code | Field | Safe `actual` detail |
|---|---|---|
| `vault_root_database_path_invalid` | `database.path` | `reason_code` plus closed `locator_reason_code` |
| `vault_root_cli_invalid` | `cli.vault_root` | `reason_code` plus closed `locator_reason_code` |
| `vault_root_config_invalid` | `config.vault_storage_path` | `reason_code` plus closed `locator_reason_code` |
| `vault_root_authority_mismatch` | disagreeing CLI/config field | `reason_code` plus `authorities` (`database_path` and `cli_root` or `config_root`) |

These findings never echo a rejected locator. Empty/blank, relative,
drive-relative (`C:vault`), current-drive-rooted (`\vault`), dot-segment,
home-relative, foreign-absolute, and device-namespace config values all route
through the config-invalid family. Lexically different symlink aliases remain
different authorities even when the filesystem would resolve them to one
directory.

## Recorded source identity (v1)

Capture source metadata once, alongside the talk; the preflight never fetches
live metadata. The optional talk-level field has this shape:

```json
{
  "source_identity": {
    "schema_version": 1,
    "provider": "youtube",
    "video_id": "AbCdEfGhI_1",
    "title": "The title recorded at the source",
    "uploader": "Conference Channel",
    "uploader_id": "@conference",
    "speakers": ["Speaker One", "Speaker Two"],
    "recorded_date": "2026-07-30",
    "upload_date": "2026-07-31",
    "duration_seconds": 2700,
    "webpage_url": "https://www.youtube.com/watch?v=AbCdEfGhI_1",
    "webpage_video_id": "AbCdEfGhI_1",
    "captured_at": "2026-07-31T12:00:00Z"
  }
}
```

`video_id`, `title`, `speakers`, `duration_seconds`, and at least one of
`recorded_date`/`upload_date` are the v1 evidence fields. `captured_at` records
provenance for humans but is not used as source identity. Dates are ISO
`YYYY-MM-DD`; `duration_seconds` is positive numeric data.

`uploader`, `uploader_id`, `webpage_url`, and `webpage_video_id` are optional
provider facts. An uploader identifies the publishing account, never a speaker;
an upload date identifies publication, never recording. The live audit may
therefore propose a partial provider-fact block without `speakers` or
`recorded_date`. A human adds those delivery claims only from separate direct
evidence. The captured webpage URL is provenance and is never an automatic
`video_url` repair. When present, provider strings must be nonempty, webpage
IDs must agree with `video_id`, and `captured_at` must be a timezone-aware
ISO-8601 timestamp. Invalid or contradictory provider provenance is blocking.

Offline comparison rules are intentionally deterministic:

- `video_id` must equal the ID parsed from the catalog URL/stored ID.
- The source title must materially agree with the catalog title. A provider may
  omit an explicitly delimited subtitle when its distinctive base title remains
  intact. This never establishes delivery identity: when the provider title
  explicitly names a known event, that event must agree with the catalog
  conference. The deterministic matching contract is owned by
  `skills/vault-ingress/scripts/source_identity_matching.py`.
- At least one recorded speaker must match a talk-level `speakers`/`speaker`
  value, falling back to `config.speaker_name`. A full name and that same
  surname-only form agree; unrelated names do not.
- `recorded_date` must be in the catalog year; a different day in that year is
  a warning. `upload_date` must not precede the catalog delivery date/year. The
  catalog reading and the upload comparison are owned by `parse_catalog_date`
  and `upload_predates_catalog` in
  `skills/vault-ingress/scripts/source_identity_matching.py`, so the live audit
  reaches the same verdict this gate does.
- When the talk has numeric `duration_seconds`, `video_duration_seconds`, or
  `talk_duration_seconds` (top-level or the documented structured variants),
  source duration may differ by at most the greater of 60 seconds or 5%.
  Without a numeric catalog duration, preflight still validates that source
  duration is positive but does not guess from prose estimates.

An unsupported future `source_identity.schema_version` is a warning and known
fields are still checked. This lets old readers remain conservative without
silently accepting contradictions.

## Rejected upstream sources

When a shownotes or catalog URL is verified as a demo clip, a sibling delivery,
or an unrelated recording, remove it from the active source fields and preserve
the decision on the talk so a later scan cannot reintroduce it:

```json
{
  "source_rejections": [{
    "schema_version": 1,
    "source_type": "video",
    "url": "https://youtu.be/AbCdEfGhI_1",
    "reason": "non_delivery_clip",
    "evidence": "Provider title and 226-second duration identify the embedded demo",
    "verified_at": "2026-07-31T14:00:00-05:00"
  }]
}
```

`source_type` is `video` or `slides`. Every entry requires a nonempty URL,
reason, evidence, and timezone-aware timestamp. The preflight blocks malformed
entries and blocks an active `video_url` or `slides_url` that names the same
rejected URL or provider identity (YouTube ID, Drive file/deck ID). Scanners
compare against this ledger before importing an upstream link.

## YouTube identity and duplicate relation

The parser accepts these URL identities:

- `youtube.com/watch?v={id}`
- `youtu.be/{id}`
- `youtube.com/shorts/{id}`
- `youtube.com/embed/{id}` (including `youtube-nocookie.com`)

IDs are exactly 11 URL-safe characters and must agree with `youtube_id`.
Duplicate IDs are blocking unless all but one canonical record explicitly point
to another record in the same identity group:

```json
{
  "source_relation": {
    "type": "duplicate",
    "target_filename": "canonical-talk.md"
  }
}
```

`type` is `duplicate` or `borrowed_recording`. The target must exist, must not
be the same record, and must carry the same YouTube ID. Legacy `duplicate_of`,
`_duplicate_of`, `borrowed_recording_from`, and `_borrowed_recording_from`
aliases are recognized when they describe the same recording. A legacy
`_duplicate_of` between different recordings can continue to describe duplicate
content, but it cannot waive a duplicate-ID fault.

## Artifact contracts

Checks apply to a record with a declared transcript, slide, or video capability
(processable) or status `processed` / `processed_partial` (completed):

Config schema v2 must contain a bounded unique
`pptx_directory_exclusions` array of literal directory-name components. Missing
or malformed current state is blocking as
`pptx_directory_exclusions_invalid`; config v1 remains readable only so the
owner migration can supply or preserve the field. This offline check validates
the policy but does not scan the configured presentation root.

A missing declared PPTX is evidence about that exact locator, not proof that no
matching deck exists elsewhere. Only a strict schema-v1
`pptx_directory_batch` result with `complete: true` authorizes a full-catalog or
missing-deck conclusion. Partial results are usable for the decks they safely
return, but budget, availability, change, placeholder, probe, or extraction
reasons leave coverage incomplete. Legacy unversioned batch output has unknown
completeness and must be rerun before an absence conclusion.

- Transcript source enum: `youtube_auto`, `provider_auto`, `whisper`, `manual`,
  `none`. Absence remains valid “unknown provenance.” Unless the value is `none`, the expected
  file is `transcripts/{youtube_id}.txt`; an explicit relative
  `transcript_path` is resolved from the vault root.
- Slide source enum: `pptx`, `pdf`, `both`, `video_extracted`, `markdown`, `none`.
- `markdown` records a deck authored in Slidev, presenterm, Marp, reveal-md or
  remark. It is provenance, not evidence: nothing renders markdown here, so the
  talk supplies no slide evidence until the deck is exported to PDF and
  re-registered as `pdf`. It requires no binary artifact and is absent from
  `USABLE_SLIDE_SOURCES`.
  `transcript_only` is unsupported; represent that state as `none`.
- Persisted local-artifact locators are classified before host path
  normalization. Relative locators use canonical `/` separators beneath their
  documented trusted root; raw dot segments, `~`, backslash/mixed relative
  syntax, Windows current-drive/per-drive-relative forms, device namespaces,
  dual-flavor `//` paths, Win32-trimmed components, alternate-stream syntax,
  and reserved DOS device basenames fail closed.
- A native absolute locator is valid only on its matching host. Windows UNC
  locators use their backslash form. Foreign absolute locators are never
  translated or rebased beneath a trusted root; repair the owner locator and
  reprocess its evidence after moving a vault between operating systems.
- Relative `pptx_path` is resolved from `config.pptx_source_dir`, falling back
  to the vault root only when that setting is absent or null. A present source
  root must be a native absolute path; an invalid/relative/foreign root is a
  blocking configuration error, not a request to fall back.
- A recorded local PDF path is authoritative only after its exact generation
  passes the bounded metadata, copy/hash, strict container, and complete page-tree
  probe.
  The current field is `slides_local_path`; the legacy `slides_pdf_path` and
  `pdf_path` aliases remain readable so old, descriptively named artifacts do
  not acquire invented Drive provenance merely to pass the gate. Relative
  values resolve from the vault root.
- Without an explicit local path, `pdf`/`both` requires `google_drive_id` and
  `slides/{google_drive_id}.pdf`.
- Without an explicit local path, `video_extracted` requires a valid YouTube
  identity. `processed` also requires `slides/{youtube_id}.pdf`;
  `processed_partial` may intentionally retain only manifest-declared source and
  derivative artifacts.
- A present video-extracted PDF is not sufficient deck evidence by itself. A
  completed record also requires a complete schema-v4
  `structured_data.video_extraction` manifest, preserved source video and
  artifact paths, and internally consistent frame/page, scope, crop, and trust
  provenance. That manifest is valid only when `slide_source` is
  `video_extracted`; persisted preflight blocks it in every other slide lane
  before inspecting any of its paths. Every manifest PDF is independently
  probed and its bounded page count must match the manifest before either
  preflight or current-return persistence accepts the referential unit. Manifest
  paths reject NUL/dot ambiguity. The schema-v4 source is exactly
  `<youtube_id>.mp4`; it takes precedence over legacy top-level video path
  fields and must pass the bounded `source-video` evidence probe as a
  root-confined regular ISO-BMFF recording with a usable video stream and
  positive duration. A promoted PDF must have the
  exact bounded SHA-256 digest of the manifest's trusted `slide_region` artifact
  and additionally requires `review_required: false` and
  a manually cropped, visually verified `slide_region` artifact marked
  `trusted_for_authored_slide_analysis: true`. A valid unpromoted
  `processed_partial` manifest may be trusted or context-only; full-frame context
  can support room/stage and qualifying delivery-video observations, but never
  authored-slide evidence. Missing, legacy, invalid, or falsely promoted
  provenance is blocking for completed records and a warning for requeued/pending
  work.

Source-video artifact availability is reported separately from manifest
ownership or locator faults:

| Code | Meaning |
|---|---|
| `source_video_artifact_missing` | The exact manifest-owned source recording is absent |
| `source_video_artifact_unavailable` | The recording exists as an offline cloud placeholder and must be hydrated locally |
| `source_video_artifact_unreadable` | The recording could not complete bounded media inspection; the nested reason distinguishes container, stream, parser, dependency, generation-change, timeout, monitor, and resource causes |

These outcomes disable only source-video evidence. They do not invalidate an
independently verified transcript, rendered PDF, or native PPTX. A locator,
root-containment, symlink/reparse, manifest-ID, or exact-basename mismatch
remains `video_extraction_provenance_invalid`. For a completed record that
claims the source, an unavailable source is blocking until repaired or the
record is requeued; independent evidence remains valid. Requeue or reparse only
when a current persisted claim depends on source-video evidence that can no
longer be verified.

Source-to-derivative lineage is a separate question from source availability. A
schema-v4 manifest carries the engine-owned `source_receipt` the extraction run
captured, and preflight compares it against a fresh bounded probe of the same
path. A source that reads but disagrees is
`video_extraction_source_lineage_mismatch`, blocking: the saved PDFs describe
bytes that are no longer there. A schema-v3 record predates the receipt and
reports `video_extraction_source_receipt_missing` at the caller's severity —
archival, not corrupt, and repaired only by reacquiring the source video and
re-extracting. Preflight never stamps a receipt onto a v3 record; a digest
observed now cannot prove what produced pages saved earlier.

The thirteen stable slide-contract fault classes are:

| Code | Meaning |
|---|---|
| `slide_source_unsupported` | Explicit source is outside the enum |
| `slide_pptx_reference_missing` | `pptx`/`both` has no `pptx_path` |
| `slide_pptx_artifact_missing` | Resolved PPTX does not exist |
| `slide_pptx_artifact_unreadable` | Resolved PPTX exists but its container or structural members cannot be parsed safely |
| `slide_pptx_artifact_degraded` | Resolved PPTX required loss-reporting placeholder recovery for damaged media |
| `slide_pdf_reference_missing` | `pdf`/`both` has no Drive ID |
| `slide_pdf_artifact_missing` | Explicit or Drive-ID PDF does not exist |
| `slide_pdf_artifact_unavailable` | PDF is an offline cloud placeholder |
| `slide_pdf_artifact_unreadable` | PDF could not complete bounded evidence inspection; use the nested reason code to distinguish parse, dependency, monitor, identity, containment, and resource causes |
| `slide_video_reference_missing` | Video extraction has no valid YouTube identity |
| `slide_video_artifact_missing` | Required explicit/processed YouTube-ID PDF does not exist |
| `slide_video_artifact_unavailable` | Video-derived PDF is an offline cloud placeholder |
| `slide_video_artifact_unreadable` | Video-derived PDF could not complete bounded evidence inspection; use the nested reason code to select remediation |

`status_source_reachability_conflict` is a separate queue-state integrity
fault. It is blocking when `skipped_no_sources` or legacy `skipped_no_video`
coexists with a concrete PDF or PPTX reference. The preflight reports the
reachable source and leaves status repair to the queue workflow.

A claimed source missing from a completed record is blocking, except for a valid
manifest-backed unpromoted `processed_partial` video result. The same absence on
a pending/processable record is a warning because acquisition has not yet run.

The preflight opens declared PPTX and PDF artifacts only through their shared
bounded probes. PDF page counts validate container integrity, citation bounds,
and manifest consistency; they never derive or validate authored `slide_count`
from `structured_data.video_extraction.unique_slides_count`. A video extraction
can produce multiple captured states for one authored slide; those are different
measurements by contract.

The canonical vault locator may itself be the documented configuration symlink.
PDF admission maps that trusted locator to its storage root once, then rejects
symlinks and unsupported reparse points in every descendant artifact component.
