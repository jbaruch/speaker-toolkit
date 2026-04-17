# Resources Gathering Rules

Steering rules for Phase 6 Step 6.0 — extracting and curating resource links
from a presentation outline.

## 1. Script First

ALWAYS use `extract-resources.py` for initial resource extraction. Do not
manually scan the outline first — the script handles URL detection, repo
matching, book patterns, RFC citations, and tool mentions consistently.
Manual scanning misses items and introduces inconsistency.

```bash
python3 skills/presentation-creator/scripts/extract-resources.py \
  presentation-outline.md --spec presentation-spec.md
```

## 2. Speaker Review is Mandatory

The extracted list is **candidates**, not the final resource list. The speaker
MUST review, approve, edit, or remove items before any publishing step uses
them. Never auto-publish extracted resources without explicit speaker approval.

Present the extracted resources in a formatted, reviewable list grouped by type.
The speaker may:
- Approve items (set `approved: true`)
- Remove false positives (delete from the list)
- Add missing resources the script couldn't detect
- Edit descriptions or add URLs for tool/book entries
- Reorder by importance

## 3. Coda Pattern Items Get Priority

Resources from Coda slides (closing/further-reading sections) are the most
intentional — the speaker deliberately chose to surface them. Sort these
higher in the review list and flag them as "from Coda section."

## 4. File Location

`resources.json` lives in the talk working directory alongside
`presentation-outline.md` and `presentation-spec.md`. It is talk-specific,
not vault-level. Path:

```
{presentations-dir}/{conference}/{year}/{talk-slug}/resources.json
```

## 5. Shownotes Integration

When shownotes are enabled (Step 6.1), the shownotes generation step reads
`resources.json` for the resource links section. Only `approved: true` items
are included. If `resources.json` doesn't exist or has no approved items,
the resource links section is omitted from shownotes.

## 6. No Duplicates

The script deduplicates URLs and repos. If a GitHub repo URL appears as both
a full URL and a repo reference, keep only the URL entry. When the speaker
adds resources manually, check for duplicates before appending.

## 7. Tracking Database

After resources are approved, update `tracking-database.json` with a
`resources[]` entry:

```json
{
  "talk_slug": "...",
  "resources_json_path": "...",
  "item_count": 12,
  "categories": {"urls": 5, "repos": 1, "tools": 3, "books": 2, "rfcs": 1},
  "created_at": "..."
}
```
