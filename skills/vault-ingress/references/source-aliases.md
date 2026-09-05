# Reviewed Inactive Source Aliases

An accepted alias is a second verified upload of the same delivery. Keep it
separate from wrong-delivery `source_rejections` and from the active source used
for acquisition, queueing, artifact lineage, and profile freshness.

## Read and review

Use the owner read/bootstrap procedure in
[schemas-db.md](schemas-db.md#owner-read-and-mutation-contract). The optional
top-level `source_aliases` collection belongs to root schema v3; its records
have their own schema version. Migration creates no alias and infers no
equivalence. Older roots remain read-only until owner migration; root v2 keeps
its existing strict child-version checks. Normal migration still refuses
active claims. The explicit QR-only repair continues to support root v2
without advancing it or cancelling claims.

For an unresolved shownotes recording, run the
[candidate identity audit](source-identity-audit.md#candidate-mode-230). Read
both provider-fact blocks and all findings. Verify the delivery independently
against an event program or authoritative event page, including speakers and
delivery date. Upload dates and uploader accounts are not delivery facts.
Compare recording content, transcripts, or artifacts when available; retain
the compared artifact hashes. Title similarity alone is not equivalence.

The current record accepts the YouTube video lane. Unsupported providers or
lanes fail closed; do not relabel them as YouTube. The auditor supplies provider
facts, not an automatic alias decision or transcript comparison. An owner must
review and approve the independent evidence before writing the plan.

## Persisted shape

`skills/vault-ingress/scripts/source_alias_contract.py` owns the closed record
shape, provider identity checks, relationship/comparison enums, and lineage
validation. Every record contains:

- `schema_version`, `talk_filename`, and the reviewed `catalog_title`.
- `source_type`, `alias`, and `canonical`. Each provider block carries
  `provider`, `video_id`, `url`, `title`, `uploader`, `upload_date`,
  `duration_seconds`, and timezone-aware `captured_at`.
- `relationship` and nullable `canonical_choice_reason`; the reason explains
  the canonical choice without calling the alternate invalid.
- `event`: independent `url`, `conference`, delivery `date`, and `speakers`.
- `comparison`: `method`, `summary`, `canonical_sha256`, `alias_sha256`, and
  nullable integer `agreement_basis_points`. Recording review may leave hashes
  null; transcript/artifact comparisons require both reviewed byte identities.
- `reviewer` and timezone-aware `verified_at`.

Provider facts and comparison hashes are recorded evidence, not independently
authenticated by the offline writer. Review the actual sources; never invent
missing values to satisfy the schema. A record does not grant its artifacts
analysis trust.

The ledger rejects canonical/alias overlap, duplicate alias ownership, overlap
with the owning talk's rejection ledger, dangling canonical targets, and cycles.
Historical edges may terminate through another same-talk alias at the current
canonical source. Unknown record versions are unusable owner state. Existing
canonical duplicate-talk relationships retain their separate preflight contract.

## Hash-bound owner append

Construct a strict JSON mutation plan using the reviewed record:

```json
{
  "schema_version": 1,
  "mutations": [{
    "kind": "record_source_alias",
    "record": "replace this placeholder with the complete reviewed record",
    "expect": {
      "video_url": "exact current canonical URL",
      "youtube_id": "exact current stored ID or the missing marker",
      "source_rejections": {"$missing": true},
      "source_aliases": {"$missing": true}
    }
  }]
}
```

The placeholders are not executable values. Replace every expectation with the
exact owner-read value, preserving absence versus null; existing ledgers require
their complete arrays. The writer binds the reviewed catalog/event identity and
canonical ID, refuses an active claim on the target talk, and changes only the
top-level alias collection. An exact already-recorded entry with current
expectations is a no-op. A stale plan is refused, not silently rebased.

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/mutate-tracking-database.py" \
  "{vault_root}/tracking-database.json" alias-plan.json
```

Review `changes`, `input_sha256`, and `output_sha256`. Both hashes are mandatory
for alias apply; a modified candidate requires a fresh dry run and review:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/mutate-tracking-database.py" \
  "{vault_root}/tracking-database.json" alias-plan.json --apply \
  --expected-sha256 "{input_sha256}" --expected-output-sha256 "{output_sha256}"
```

The shared locked transaction rejects competing database generations. Re-read
through the owner and verify the reported output digest, then repeat the scan
and preflight. `scan-shownotes.py` reports a reviewed alternate as `unchanged`
when no independent metadata conflict remains. It preserves the canonical URL
and stored ID, including an absent ID, and never promotes the alias.

## Atomic official-upload promotion

Appending an alias does not change acquisition. For an owner-approved switch to
a verified official upload, use `promote_source_alias` as the plan's sole
mutation. Review independent event identity and recording comparison again;
an existing alias decision alone does not authorize changing the canonical.

Supply a complete **v1** decision with the old current upload in `alias`, the
new official upload in `canonical`, relationship
`superseded_by_official_upload`, and a non-null `canonical_choice_reason` that
records the owner's official-source judgment. The writer does not infer an
official channel from its name, title, or upload date. `expect` names exactly:

- `talk`: the complete owner-read talk record, including any completed lease,
  artifact declarations, analysis, and absent-versus-null fields.
- `source_aliases`: the complete current top-level array, or the missing marker.

Use the same dry-run command and review both hashes before apply. The writer
refuses active claims, competing ownership, stale talk/ledger values, rejected
identities, or a composed multi-operation plan. The locked commit installs the
source switch and its history together; do not substitute separate repair and
append writes.

The writer sets `video_url` and `youtube_id` to the reviewed new identity,
removes the old upload's top-level `source_identity`, and sets status
`needs-reprocessing` with reason `source_added`. It leaves all other talk fields,
analysis, transcript/video declarations, receipts, and external artifacts
untouched. The source switch performs no acquisition or reparsing. Old receipts
do not become proof for the new upload: existing owner/provenance checks still
apply, and preflight may remain blocking until separately authorized evidence
repair or reprocessing. Never clear or relabel those receipts to bypass a gate.

The resulting alias is **v2**, with the v1 decision fields plus:

- `prior_state`: closed schema-v1 snapshot of the exact overwritten or removed
  `video_url`, `youtube_id`, `source_identity`, `status`, and `reprocess_reason`.
  An absent field uses `{"$missing": true}`. Historical provider evidence is
  preserved as an inactive object, never interpreted as current evidence.
- `retired_alias`: null, or the complete earlier same-talk alias record for the
  identity that is now canonical. It retains its original version, reviewer,
  comparison, and any prior history. Only this edge moves into history; other
  edges retain their compared targets and resolve through the superseded source.

Readers accept v1 and v2 without restamping old judgments. Only the promotion
writer constructs v2 history; caller-supplied history is refused. Historical
records must name the promoted identity and same talk. The contract's bounded
history limit fails closed without dropping old decisions. Retired records are
neither live aliases nor acquisition capabilities. Root schema remains v3.

Re-read the committed database and verify its output digest. Repeat shownotes
scan and preflight; shownotes for the superseded recording now resolves as an
accepted alias, while independent metadata conflicts stay visible.

Unrelated source repair, scan/import, queue, persistence, and profile operations
must preserve the ledger. A mutation that would make its ownership inconsistent
fails the owner-schema gate; removing the ledger is not a repair.
