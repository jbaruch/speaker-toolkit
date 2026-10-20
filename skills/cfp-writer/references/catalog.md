# Sessions Catalog

`{vault_root}/sessions-catalog.md` is the single source of submission-ready
materials for active talks. `cfp-writer` owns its edits. Other skills read entries
or hand approved updates here. Catalog reads do not start a submission interview.
An absent catalog is an empty first-run catalog; create it on the first approved
write. Preserve unrelated entries.

Each entry contains title/subtitle, submission-ready abstract, prose outline with
section descriptions and time allocations, and optional Small Print for the
Program Committee. Mark Small Print as internal. Separate entries with `---`.

Adapt an existing entry before creating another version of the same talk. Save
the latest approved title, abstract, and outline after a CFP revision or an
approved-outline handoff. Archive or remove an entry only when requested. Full
history remains in the tracking database and analysis files; this Markdown edit
does not authorize a tracking write.

Before saving new prose, invoke `Skill(skill: "blog-writer")` with the abstract
for an anti-pattern check; apply its flagged-phrasing corrections here. If that
skill is unavailable, report the skipped check and the installation command
`tessl install jbaruch/blog-writer`. Never approximate its scanner inline.
Keep the catalog's `Last updated` date current. Return the saved entry and path
to the caller without starting slide work or publication.
