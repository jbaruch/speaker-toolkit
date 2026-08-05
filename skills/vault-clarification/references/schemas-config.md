# Vault Config & Intent Schemas

## Config Fields — Clarification Session Questions

Fields below `template_skip_patterns` are asked during Step 5 (first session
only) when empty. The question column shows what to ask the speaker.

| Config field | Question |
|-------------|----------|
| `speaker_name` | "Name as it appears on slides?" |
| `speaker_handle` | "Social handle for footers?" |
| `speaker_website` | "Website for talk resources?" |
| `shownotes.source.type` | "Where do your shownotes live? Local Jekyll, Hugo, Eleventy, Astro, a remote URL, or no shownotes site?" |
| `shownotes.source.path_or_url` | "Path (or base URL) to the shownotes site root?" |
| `shownotes.source.talks_subdir` | "Subdirectory under the site root where talk entries live? (e.g., `_talks`, `content/talks`)" |
| `shownotes.url.base` | "Base URL where the shownotes site is deployed?" |
| `shownotes.url.template` | "Permalink template for a single talk? (e.g., `/talks/{slug}/`, `/{yyyy}-{mm}-{dd}-{slug}/`). Verify against your deployed URLs before confirming." |
| `shownotes.thumbnail_path_template` | "Where in the site repo does the SSG template expect the talk thumbnail? (e.g., `assets/images/thumbnails/{slug}-thumbnail.png`)" |
| `shownotes.slug_convention.template` | "Convention for talk slugs? (e.g., `{venue-compact}{yy}-{short-id}` → `devnexus26-robocoders`). What components and format?" |
| `shownotes.ssg_template_pointer` | "Which SSG template file encodes the URL/thumbnail conventions (so they can be re-derived after a redesign)? e.g., `_layouts/default.html` for Jekyll." |
| `template_pptx_path` | "PowerPoint template path?" |
| `presentation_file_convention` | "File organization? (default: `{conference}/{year}/{talk-slug}/`)" |
| `publishing_process.export_format` | "How do you export final decks — PDF, keep .pptx only, or both?" |
| `publishing_process.export_method` | "How do you produce the PDF? (e.g., PowerPoint AppleScript, LibreOffice CLI, manual)" |
| `publishing_process.qr_code` | "Do you put QR codes in your decks? If yes, what do they link to?" |
| `publishing_process.qr_code.shortener` | "Do you use a URL shortener for QR links? Options: `bitly`, `rebrandly`, or `none`." |
| `publishing_process.qr_code.bitly_domain` | _(Only if shortener=bitly)_ "Do you have a custom Bitly domain? (e.g., `jbaru.ch`) — save the domain, or `null` to record no custom domain (default `bit.ly`)." |
| `publishing_process.qr_code.rebrandly_domain` | _(Only if shortener=rebrandly)_ "What custom domain do you use with Rebrandly? (e.g., `jbaru.ch`) — save the domain, or `null` to record no custom domain (default)." |
| `publishing_process.qr_code.shortener_setup` | _(Only if shortener=bitly or rebrandly)_ "Add your API key to `{vault_root}/secrets.json` (`chmod 600`). Format: `{\"bitly\": {\"api_token\": \"...\"}}` or `{\"rebrandly\": {\"api_key\": \"...\"}}`. Alternatively, install the Bitly or Rebrandly MCP server for agent-driven shortening." |
| `gemini_api_key` | "Add your Gemini API key to `{vault_root}/secrets.json` under `gemini.api_key` (`chmod 600`). Format: `{\"gemini\": {\"api_key\": \"...\"}}`. Get a key from https://aistudio.google.com/app/apikey. The `GEMINI_API_KEY` env var also works as a fallback." |
| `publishing_process.additional_steps` | "Any other distribution steps after exporting?" |

## Full Config Schema

See the canonical schema and field reference in
[../../vault-profile/references/schemas-config.md](../../vault-profile/references/schemas-config.md).
Current writes preserve config schema v2, including the owner-validated
`pptx_directory_exclusions`; config v1 is owner-migration input, not writable
session state. That file also documents the migration path for the exclusion
field and for vaults created before the unified `shownotes` block.

## Confirmed Intents Schema

Stored in the `confirmed_intents` array of the tracking database. Populated during
clarification sessions when the speaker confirms a pattern is intentional. Persist
records only with the ingress owner's `upsert_confirmed_intent` mutation; see the
[owner mutation contract](../../vault-ingress/references/schemas-db.md#owner-read-and-mutation-contract).

```json
{
  "confirmed_intents": [{
    "schema_version": 1,
    "pattern": "delayed_self_introduction",
    "intent": "deliberate",
    "rule": "Use two-phase intro: brief bio at slide 3, full re-intro mid-talk",
    "note": "Speaker confirmed this is an intentional rhetorical device",
    "confirmed_date": "2026-08-01",
    "source_talk": "2026-08-01-example.md"
  }]
}
```

The complete record has required exact integer `schema_version: 1` and string
fields `pattern`, `intent`, `rule`, and `note`, plus optional
speaker-confirmation provenance. Provenance may use one of singular `source_talk`
or legacy alias `talk`, or the non-empty unique string array `source_talks`;
`confirmed_date` is canonical `YYYY-MM-DD`, and `retrofit_targets` is an optional
non-empty unique string array. Existing speaker-owned intent labels outside the
three recommended labels remain valid non-empty classifications and must not be
discarded during an exact-record update. Unknown fields are rejected.

## Improvement Goals Schema

Stored in the `improvement_goals` array of the tracking database. This is the
artifact that closes the coaching loop: the speaker picks 1–2 focus areas, and a
later ingress run checks whether the targeted issue actually moved. Without it the
system diagnoses but never verifies that the speaker acted.

**Artifact owner:** vault-ingress owns the tracking database, record shapes, and
migrations. **Authorized writer:** vault-clarification creates and retires goals
during a session through `upsert_improvement_goal`. **Reader/updater:**
vault-ingress reads active goals and changes only the verification fields through
`patch_improvement_goal_verification` (`status`, `current_value`,
`last_checked`, `checked_by`, `verification_state`, `verification_reasons`) — never
the owner shape or fixed baseline. Both operations use the
[owner mutation contract](../../vault-ingress/references/schemas-db.md#owner-read-and-mutation-contract).
On a record whose `schema_version` it does not
recognize, vault-ingress treats it as read-only and skips verification.

Schema v2 binds every catalog-derived goal to the exact pattern-scoring generation
accepted by the speaker. The full baseline snapshot is copied from a validated
schema-v4 or schema-v5 `speaker-profile.json`; Section 15 is narrative context, never
the machine source. Schema-v5 derived labels may inform the offered goals only when
their exact classification domain is available; schema v4 remains occurrence-only.
The helper at `scripts/goal_generation_provenance.py` makes the mechanical
comparability decision for both the owner and reader.

```json
{
  "improvement_goals": [{
    "id": "reduce-shortchanged",
    "schema_version": 2,
    "issue": "Shortchanged — rushing the final third under time pressure",
    "kind": "antipattern|underuse|pacing|other",
    "antipattern_id": "shortchanged (null unless kind=antipattern)",
    "metric": "fraction of recent talks exhibiting Shortchanged",
    "baseline_value": "4 of last 6 (0.67)",
    "target": "at or below 1 of 3 (0.33)",
    "set_date": "2026-06-11",
    "set_by": "vault-clarification",
    "status": "active|improving|achieved|stalled|regressed|retired",
    "current_value": "",
    "last_checked": null,
    "checked_by": null,
    "verification_state": "pending|current|needs_rebaseline|unverifiable",
    "verification_reasons": [],
    "supersedes_goal_id": null,
    "baseline_provenance": {
      "lane": "pattern_scoring",
      "pattern_baseline": {
        "schema_version": 2,
        "as_of": "2026-06-11T12:00:00+00:00",
        "scope": "global",
        "active_batch_excluded": false,
        "excluded_filenames": [],
        "eligible_statuses": ["processed", "processed_partial"],
        "pattern_scoring_generation_status": "current",
        "pattern_scoring_generation_reasons": [],
        "pattern_catalog_fingerprint": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "pattern_scoring_schema_version": 5,
        "scored_talk_count": 12,
        "pattern_score_sum": 72,
        "average_pattern_score": 6.0,
        "eligible_talk_count": 12,
        "opportunity_coverage_identity": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "raw_score_comparison_status": "available",
        "raw_score_comparison_reason": null
      }
    }
  }]
}
```

- `kind` ties the goal to a coaching surface: `antipattern` (a speaker-selected
  antipattern occurrence to reduce), `underuse` (a speaker-selected pattern occurrence
  to increase), `pacing` (hit the time/slide budget), `other` (free-form). Raw
  occurrence rows do not classify recurrence, signature status, or underuse.
- `antipattern_id` is set only when `kind` is `antipattern`; it is `null` for
  `underuse`, `pacing`, and `other` goals (no antipattern exists to reference).
- `baseline_value` is the human-readable metric value accepted by the speaker. For
  a pattern goal, compute it from the same validated profile cohort carried in
  `baseline_provenance.pattern_baseline`; never parse it from Section 15.
- `target` is the speaker's own stated aim, not a generic standard.
- `baseline_provenance.lane` is `pattern_scoring` for `antipattern` and `underuse`,
  `pacing` for pacing, and `independent` for `other`. Pacing/independent records omit
  `pattern_baseline`. An `other` goal cannot be used to evade pattern provenance.
- Pattern baselines must be non-empty post-batch full-cohort snapshots
  (`active_batch_excluded: false`, `excluded_filenames: []`). A fingerprint or scoring
  schema mismatch produces `needs_rebaseline`; scoring-v5 also requires one available
  `opportunity_coverage_identity` for raw-score comparability. A missing current
  baseline or legacy schema-v1 pattern goal is `unverifiable`. Neither state permits
  an outcome status.
- Rebaselining is an explicit speaker decision: preserve the old record, retire it,
  and create a new schema-v2 record with `supersedes_goal_id`. Never overwrite or
  restamp the old baseline.
- Existing schema-v1 `antipattern`/`underuse` goals remain read-only and
  unverifiable. Existing schema-v1 `pacing` and truly non-pattern `other` goals remain
  independent of catalog releases.
- Verification rubric (how vault-ingress sets `status`) lives in
  [../../vault-ingress/references/processing-rules.md](../../vault-ingress/references/processing-rules.md)
  Improvement Goal Verification.
