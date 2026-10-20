# QR Publication

Read `publishing_process.qr_code`. Before provider or deck effects, resolve the
shared runtime without `--read-only` and require the owner-current database.
Read the confirmed slug and URL from the non-owner outline JSON. Verify the
configured target is live before encoding it. Require only the selected direct
API provider token, not Gemini/image-provider keys. MCP-preresolved and explicit
`shortener: none` do not require direct API credentials.

For the configured workflow, skip when disabled; a direct QR request selects
this action explicitly. Follow the provider/domain choices below:

1. Determine the URL to encode:
   - If `target` is `shownotes_url`, use the shownotes URL from the verified shownotes result
   - If `target` is `custom_url`, use the `custom_url` field

2. Resolve URL shortening using one of these paths:

| Path | Short URL resolution | QR image |
|---|---|---|
| MCP (preferred when configured) | Agent calls Bitly/Rebrandly MCP tool, passes `--short-url` **and** `--shownotes-url` to script | Script generates locally from the resolved URL |
| Direct API | Script calls bit.ly/rebrand.ly REST API via `secrets.json` | Script generates locally |
| None (explicit `"shortener": "none"` only) | Script uses the raw shownotes URL | Script generates locally |

**MCP path (preferred when Bitly or Rebrandly MCP server is installed):**
- Bitly MCP: `npx @bitly/mcp` — covers link creation, update, QR, and analytics
- Rebrandly MCP: see rebrandly.com MCP documentation
- Agent creates or updates the short link via MCP tools, then passes the resolved
  URL to `generate-qr.py` via `--short-url`
- `--shownotes-url` is ALWAYS required — it is the canonical redirect target the
  catalog records. Passing only the short URL would make the record claim the
  short link redirects to itself
- Pass `--short-provider` and `--short-link-id` so the catalog keeps the real
  provider identity instead of the generic `mcp_preresolved` marker

**Direct API path (when MCP is not available):**
- API keys must be stored in `{vault_root}/secrets.json` with `chmod 600`:
  ```json
  {
    "bitly": {"api_token": "..."}
  }
  ```
- The example is for Bitly; Rebrandly uses `rebrandly.api_key` instead.
- Script reads `secrets.json` and calls the chosen shortener's REST API directly
- The `shortener` field in the profile controls which service to use

**None path (no shortening):**
- Requires an explicit `"shortener": "none"` in the profile
- Script encodes the raw shownotes URL directly into the QR code
- Any other resolution failure exits non-zero without generating a QR
  (`rules/qr-generation-rules.md` §2, §6, §7)

**First short link — confirm the custom domain:** before a short link is created
for the first time, ensure `publishing_process.qr_code.{shortener}_domain` is
recorded in the profile. If the key is absent, ASK the user whether they have a
custom domain (e.g. `jbaru.ch`) and SAVE the answer — the domain, or `null` for
"no custom domain" — then proceed. See `rules/qr-generation-rules.md` §8. The
Direct API path enforces this (the script STOPS if the key is absent); on the MCP
path make the check before resolving the link.

3. Run the QR generation script:
   ```bash
   # MCP-preresolved mode (--shownotes-url is the canonical redirect target):
   "{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/generate-qr.py" deck.pptx \
     --talk-slug SLUG --shownotes-url SHOWNOTES_URL --short-url SHORT_URL \
     --short-provider bitly --short-link-id LINK_ID

   # Direct API mode:
   "{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/generate-qr.py" deck.pptx \
     --talk-slug SLUG --shownotes-url SHOWNOTES_URL \
     --vault /path/to/vault

   # No shortening:
   "{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/generate-qr.py" deck.pptx \
     --talk-slug SLUG --shownotes-url SHOWNOTES_URL

   # PNG-only (no deck — for presenterm, PDF, or standalone use):
   "{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/generate-qr.py" --png-only \
     --talk-slug SLUG --shownotes-url SHOWNOTES_URL \
     --output /path/to/qr.png --bg-color 128,0,128
   ```

   The script is a non-owner dual reader and a current-schema writer. Dry-run
   accepts every readable database generation without changing it; the generations
   are defined by the [owner schema](../../vault-ingress/references/schemas-db.md).
   A real run requires the current database schema before URL-shortener calls, deck edits,
   or tracking persistence. Route a legacy database through vault-ingress Step 1.
   An unsupported future database or record version is no usable prior state.

4. The script will:
   - Match the QR background color to the target slide (walks slide → layout → master
     for solid fill; falls back to white with a warning for theme-colored fills)
   - Auto-select foreground color (black on light backgrounds, white on dark) using
     WCAG relative luminance
   - Insert the QR as a 2" square in the bottom-right corner
   - Serialize concurrent publication of the same talk and hold that
     serialization across the external effects — see
     `skills/presentation-creator/scripts/generate-qr.py` (`qr_publication_lock`
     docstring) for the lock's scope and placement
   - Commit the QR record against the current database generation — see the
     `commit_qr_record` docstring in the same script for what it rebases and
     what it refuses
   - On a rejected commit: exit non-zero having written one JSON document to
     stderr — `{"error": "qr_publication_unfinalized", ...}` with `retry`,
     `atomic_rollback`, and an `effects[]` entry per landed effect, each
     carrying its own `rollback` action. Render it for the operator; do not
     restate its fields here. See `unfinalized_effects_payload` in
     `skills/presentation-creator/scripts/generate-qr.py`. The run makes no
     tracking-database change in that case
   - Persist schema-v2 QR metadata in `qr_codes[]` — including one
     `artifacts[]` receipt per generated PNG — through the shared
     tracking-database transaction used by `generate-qr.py`
   - Refuse to write when the database moved underneath the run — the exact
     generation and same-talk conditions live in `commit_qr_record`

5. Re-running for the same `talk_slug` with a different target URL is safe:
   printed QR codes stay valid. Which link a run reuses, retargets, or creates is
   decided by `resolve_short_url` in
   `skills/presentation-creator/scripts/generate-qr.py` — see its docstring.

**No raw-dogging:** NEVER bypass `generate-qr.py` with hand-rolled python-pptx or
direct `qrcode` library calls. If the script targets the wrong slides, uses the wrong
shortener, or produces the wrong colors — fix the inputs (profile config, secrets,
arguments), don't patch the outputs with ad-hoc code. The script is the single source
of truth for QR generation; working around it silently drops shortening, tracking,
and color matching.

Dependencies and failure behavior belong to `generate-qr.py`; use the configured interpreter and runtime repair flow when a dependency is unavailable.
