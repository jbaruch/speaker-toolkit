# Live Source Identity Capture & Audit

`skills/vault-ingress/scripts/audit-source-identities.py` is the networked,
read-only companion to the offline vault preflight. It asks `yt-dlp` for stable
provider metadata, compares that evidence with active talk records, and emits
review proposals. It never changes the tracking database or any vault artifact.

Run it after the offline structural preflight and before writing a source-repair
plan:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/preflight-vault.py" {vault_root}
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/audit-source-identities.py" {vault_root}
```

The audit requires the `yt-dlp` executable and network access. An **active talk**
for this helper is a record with a nonempty `video_url`. Only supported YouTube
URL forms are fetched. The helper parses their 11-character IDs, groups every
record naming the same ID, and makes exactly one metadata request per group.
Records with a stored `youtube_id` but no active URL are not resurrected or
fetched; a rejected/cleared source stays inactive.

Stdout is the only output. The helper accepts a vault root or the database path:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/audit-source-identities.py" \
  {vault_root}/tracking-database.json
```

Use `--captured-at <timezone-aware-ISO>` only for a reproducible evidence run or
fixture. Normal runs stamp the current UTC time. Exit `0` means every requested
identity returned internally consistent metadata. Review findings such as title
mismatches, likely clips, and cross-talk collisions do not change that exit code.
Exit `1` means capture was incomplete or provider identity contradicted the
requested ID. Invocation errors exit `2`.

## Captured provider facts

The helper deliberately selects a small metadata subset:

```json
{
  "schema_version": 1,
  "provider": "youtube",
  "video_id": "AbCdEfGhI_1",
  "title": "Title reported by YouTube",
  "uploader": "Conference Channel",
  "uploader_id": "@conference",
  "upload_date": "2026-07-31",
  "duration_seconds": 2700,
  "webpage_url": "https://www.youtube.com/watch?v=AbCdEfGhI_1",
  "webpage_video_id": "AbCdEfGhI_1",
  "captured_at": "2026-07-31T19:00:00Z"
}
```

These are provider facts, not delivery facts:

- `uploader`/`uploader_id` identify the publishing account. They are never
  copied to `speakers` and are not proof that the uploader spoke.
- `upload_date` is publication time. It is never copied to `recorded_date` and
  does not establish when the talk was delivered.
- `webpage_url` is captured evidence of the fetched page. The audit never emits
  a `video_url` repair or applies that URL to a record.
- The provider does not reliably expose speakers or recording date through this
  metadata path, so the proposal omits both. A human may add them only from
  direct evidence such as the recording, event program, or authoritative page.

Every successful talk audit carries this subset under
`proposed_evidence.source_identity`. It is evidence for review, not an apply
plan. Missing fields remain absent/null; the helper does not synthesize them.

## Candidate mode (#230)

A `scan-shownotes.py` conflict names a competing source for a talk that already
has one. Pass that report back to compare both sides through this auditor's
bounded fetching, stable evidence shape, redaction, and no-write guarantee,
instead of an ad hoc provider lookup outside the ingress workflow:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/audit-source-identities.py" \
  "{vault_root}" --candidates-from "{scan_report_path}"
```

Candidate identities never enter the active-source assignment: the cross-talk
collision analysis reads that map, so a candidate shared by two talks would
otherwise fabricate a collision between active identities that share nothing.
`sources[].lanes` names which lane claimed each fetched identity.

The report is validated whole before anything is bound, and the verdict is
all-or-nothing: only `schema_version: 3` with `ok: true` is accepted, and one
malformed entry, malformed issue, or unbindable candidate discards **every**
candidate binding. A partly malformed report is not a complete conflict set, so
auditing its well-formed remainder would report an unknown subset as "these are
the conflicts". The active lane still audits, so the cost is coverage of the
conflicts, never of the sources already in the database.

An entry whose `disposition` falls outside the scan report's closed set
(`add`, `update`, `unchanged`, `review_required`) is malformed, not a row to
pass over — skipping an unrecognized value would let a typo hide a conflict
behind an apparently clean audit. A report file containing JSON `null` is a
supplied-but-invalid report, never "no report given".

An unsupported lane is not a malformed report: a `slides_url` candidate leaves
the report intact and simply names a source with no auditable provider
identity, so it stays a lane-local finding and the other candidates proceed.

Every binding resolves before any provider request — a report naming an unknown
or ambiguous talk is refused without spending a fetch. Candidate identities
share the active lane's dedupe, so a candidate repeated across conflicts, or one
equal to an active source, is fetched once. `candidates[]` carries
`provider_evidence` and `active_provider_evidence` in the same shape for
field-for-field comparison, plus `same_source_as_active`. A candidate lane with
no auditable provider identity (`slides_url`), a malformed YouTube URL, and an
unavailable or rate-limited fetch each stay lane-local structured findings.

The audit still writes nothing. A candidate is never promoted or persisted here
— reviewing this evidence and applying a decision are separate steps.

## Report contract (v2)

```json
{
  "schema_version": 2,
  "captured_at": "2026-07-31T19:00:00Z",
  "database": "/vault/tracking-database.json",
  "complete": true,
  "review_required": true,
  "active_talk_count": 2,
  "unique_youtube_id_count": 1,
  "metadata_fetch_count": 1,
  "metadata_fetch_error_count": 0,
  "candidate_count": 1,
  "summary": {
    "finding_count": 1,
    "by_code": {"same_id_cross_talk_collision": 1}
  },
  "sources": [],
  "talks": [],
  "findings": []
}
```

`sources` contains one record per fetched ID, with the sorted talk indexes and
filenames that caused the fetch, `fetch_status`, provider evidence, and any
error. `talks` contains one record per active URL, its catalog comparison, and
the proposed evidence. `findings` and `summary.by_code` are sorted; with the same
database, provider responses, and `captured_at`, the decoded JSON is identical.

Stable finding codes:

| Code | Meaning |
|---|---|
| `active_youtube_url_invalid` | An active YouTube-looking URL has no valid ID |
| `active_video_provider_unsupported` | Active URL is not a supported YouTube source; no fetch occurred |
| `stored_youtube_id_mismatch` | URL identity disagrees with stored `youtube_id` |
| `metadata_fetch_failed` | `yt-dlp` was missing, timed out, failed, or returned unusable JSON |
| `provider_video_id_mismatch` | Returned provider ID differs from the requested ID; no proposal is emitted |
| `provider_webpage_identity_mismatch` | Returned webpage names another ID; no proposal is emitted |
| `provider_metadata_incomplete` | A stable capture field is absent/invalid |
| `provider_title_mismatch` | Provider title lacks material full-title or explicit base-title agreement |
| `provider_event_mismatch` | Provider title explicitly names a known event different from the catalog conference |
| `provider_duration_mismatch` | Provider duration exceeds the audit's deterministic catalog tolerance |
| `provider_upload_predates_catalog` | Upload date predates the cataloged delivery date |
| `stored_source_identity_differs` | Fresh stable facts differ from an existing evidence block |
| `likely_non_delivery_clip` | Conservative title/duration signals suggest a demo, teaser, excerpt, or other non-delivery artifact |
| `same_id_cross_talk_collision` | One ID is active on records with materially different titles or delivery dates |

Title and explicit-event comparison are separate: an abbreviated title cannot
waive a delivery's event identity. Their matching contract is owned by
`skills/vault-ingress/scripts/source_identity_matching.py`. The non-delivery
finding is a review signal, never an automatic rejection. Its conservative
signal combination is owned by
`skills/vault-ingress/scripts/audit-source-identities.py` in
`_non_delivery_signals`. Cross-talk collision findings include existing
`source_relation` values for human review.

## Human review and repair order

1. Review the provider page/recording, every audit finding, and the proposal.
2. Add speaker or recorded-date claims only when separate direct evidence supports
   them. Do not reinterpret uploader/upload date.
3. If the active URL is a non-delivery clip or wrong recording, prepare a
   `source_rejections` entry and explicit source clears. If it is correct, prepare
   only the supported `source_identity` update.
4. Express approved changes as an `apply-source-repairs.py` plan with exact old-value
   preconditions. Dry-run first, then use `--apply` only after review.
5. Re-run the offline preflight. Never make the capture helper an automatic writer,
   and never translate its provider `webpage_url` into an unreviewed active URL.

See [source-identity-preflight.md](source-identity-preflight.md) for the persisted
evidence contract, rejection ledger, duplicate relations, and guarded repair flow.
