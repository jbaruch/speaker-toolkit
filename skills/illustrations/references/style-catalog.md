# Reusable Style Catalog

The illustrations skill owns these schemas. The packaged public layer lives at
`skills/illustrations/catalog/styles.json`; the optional personal layer is
`{vault_root}/style-catalog.json`, separate from the tracking database and
descriptive `visual_style_history`. No tracking schema change or talk reparse is
needed. Never infer a reusable anchor from a talk title or transcript alone.

## Read and select

Resolve `{speaker_toolkit_root}` from the loaded skill. With a known vault:

```bash
python3 "{speaker_toolkit_root}/skills/illustrations/scripts/style_catalog.py" list \
  --vault "{vault_root}"
```

Omit `--vault` for public-only selection. A missing personal file means an empty
overlay. A present invalid, unavailable, or unsupported-version personal file
stops selection; it must not silently expose the shadowed public defaults.
Personal entries replace entire public entries of the same slug, not individual
fields. Distinct slugs form the union; output is sorted by slug. Neither layer is
modified by a read, and no image or remote sample is fetched.

Use the merged entries in Step 7's source/fit judgment. A catalog entry is a
candidate, not a speaker's approval or a substitute for inspecting a rendered
sample. Existing personal history still informs which entries fit. New styles
can be proposed when the selected idea sources need them; record them through
the owner tool instead of maintaining another ad hoc reusable library.

After the speaker chooses the exploration candidates, author a selection JSON:

```json
{
  "schema_version": 1,
  "slugs": ["comic-book-hero", "isometric-systems-3d"],
  "slides": {"FULL": 7},
  "models": ["gemini-3-pro-image"]
}
```

Use the live Step 6 shortlist, not the illustrative model ID above. `slides`
maps FULL and/or IMG+TXT to positive outline slide numbers. Select one to twenty
distinct slugs and one to twenty distinct model IDs. Explore a single
composition per grid; poster-theatrical requires FULL only. Selected display
names must have distinct exploration-directory slugs. Unknown fields and
unsupported selection versions are refused.

```bash
python3 "{speaker_toolkit_root}/skills/illustrations/scripts/style_catalog.py" candidates \
  --vault "{vault_root}" --selection selection.json \
  --output "{talk_dir}/style-explore/candidates.json"
```

Create the output parent directory first. An identical output is reused;
different existing bytes are preserved and require a fresh filename. The owner
emits candidate schema v2 with complete style entries and layer/digest receipts.
The generator reads v1 and v2 without rewriting either. Its v2 path applies each
style's conventions and, for posters, text treatment to the representative
slide's actual `text_overlay` and the outline's footer. A poster representative
must have text and no safe zone. Follow Step 8's normal render and Step 9's
human-choice/render-before-bake gates; copy the selected entry's anchor,
conventions, composition, and text treatment when baking. Receipts identify the
snapshot used, not a promise that a later catalog read is unchanged.

## Catalog schema v1

Root: exactly `schema_version: 1` and `styles: []`, with at most 200 entries.
Every entry has exactly the fields below; entry, sample, and provenance versions
are independently explicit integers, not booleans. Unknown fields, duplicate
JSON keys, nonfinite numbers, duplicate layer slugs, and future versions fail
closed. UTF-8 inputs and outputs are bounded to 2 MiB.

| Field | Contract |
|---|---|
| `schema_version` | Integer 1 |
| `slug` | Stable lowercase hyphenated identifier, at most 100 characters |
| `name` | Nonempty single-line display name, at most 160 characters |
| `anchors` | Exactly FULL and IMG+TXT, both nonempty style-only text |
| `text_treatment` | Text-rendering style; nonempty for poster-theatrical |
| `conventions` | Style-only continuity/color conventions; empty allowed |
| `composition` | `poster-theatrical` or `overlay` |
| `tags` | One to twenty distinct slug-shaped concept-fit hints |
| `sample` | Versioned reference described below |
| `provenance` | Versioned origin described below |

Sample has exactly `schema_version: 1`, `kind`, `location`, `description`.
Kinds: `local-image` (personal only), `remote-image` (HTTPS), or `reference`
(HTTPS source describing an unbundled sample). A reference is not an inspected
image; keep that limitation visible. Local sample paths are resolved by the
speaker relative to the vault unless absolute. Readers do not open them.

Provenance has exactly `schema_version: 1`, `kind`, `reference`, `note`.
Kinds: `exploration`, `delivered-talk`, `contribution`, or `personal`.
Public provenance must be a credential-free public HTTPS reference. Personal
provenance may refer to local evidence. Plain-text fields are bounded to 16,000
characters; do not include credentials or private source text in a public entry.
URL user information is forbidden in every sample/provenance reference, including
personal local-image fields and personal provenance.

The merged view is a read-only v1 envelope with `public_sha256`,
`personal_sha256` (or `missing`), and `styles`. Each style retains its entry fields
and adds `catalog_source`: exactly `schema_version: 1`, `layer` (`public` or
`personal`), and the source layer's `sha256`. Candidate v2 preserves these styles;
its other root fields remain `slides` and `models`. See
[skills/illustrations/references/style-explore-candidates-schema.md](style-explore-candidates-schema.md).

## Personal owner writes

Only the `put` action of
[skills/illustrations/scripts/style_catalog.py](../scripts/style_catalog.py)
writes the personal layer. Author one complete entry JSON, then preview against `personal_sha256`
from a fresh list. For an absent file, use `missing`:

```bash
python3 "{speaker_toolkit_root}/skills/illustrations/scripts/style_catalog.py" put \
  --vault "{vault_root}" --entry personal-entry.json --expected-sha256 missing
```

Review the entry and preview. To authorize the same operation, repeat with
`--apply` and the same `--expected-sha256`. The configured environment must have
the project's `filelock` dependency. All owner writers share a canonical-path
lock. A stale digest fails before mutation. Replacement backs up exact prior
bytes as `style-catalog.json.backup-<sha256>`, then atomically publishes the whole
validated catalog. Existing other entries retain their values; a semantic no-op
preserves the complete original bytes. Keep backups private with the catalog.
Use verified backups as evidence when restoring reviewed entries through `put`;
never copy a backup over live state or add a reader-side reset.

There are no legacy versions of this new artifact. Readers never migrate or
restamp unsupported records. A future shape change must increment its owner's
version and ship the relevant reader/migration work before writing that shape.
No catalog write requeues talks, changes active claims, or edits the public file.

## Discoveries and opt-in contribution

After ingress or exploration yields a genuinely new, visually evidenced style,
compare it with the merged catalog. The anchor discipline in
[rules/illustration-rules.md](../../../rules/illustration-rules.md) applies; semantic style-only review remains human/
agent judgment, not a regex classifier. Keep signature/private styles personal.

Offer one separate question: “Would you like to contribute this reusable style
to the public catalog?” Never submit automatically or bundle this with a
clarification question. A decline ends this flow without a write or upload.

On acceptance, show the exact proposed entry, sample, and provenance; remove
private paths, talk content, and identifying material the speaker has not agreed
to share. Obtain approval for that exact public payload. Use the
`style-contribution` issue form at
[New style contribution](https://github.com/jbaruch/speaker-toolkit/issues/new?template=style-contribution.yml).
The form requests the complete catalog entry, a representative image/link,
source attribution, and sharing consent. A maintainer validates and reviews it
before adding it to the public catalog. An issue is a proposal, not automatic
catalog admission, rendered-sample approval, or permission to publish a vault.

The initial three Berglund exploration entries cite their owner-supplied issue
anchors; their images are unbundled references. Seeding from delivered talks
dated April 2026 onward is a separate evidence pass after this format lands:
verify the delivery/source identity, inspect actual slides, extract style-only
features, and retain a consented sample with exact provenance. Do not label the
three exploration seeds as that completed delivered-talk pass.
