# Talk Content Skill

## Site contract

Read the target site's `docs/USAGE.md` Skills section and
`_plugins/skill_processor.rb` before authoring. Confirm the target layout
includes `skill_section.html`. If this feature is absent, report that site
support must be installed or merged before publishing; do not invent a
`**Skill:**` body field or frontmatter switch. Check the branch that will
actually deploy, not only an unmerged feature branch.

- Source: `_skills/{talk_page_stem}/SKILL.md`, paired with
  `_talks/{talk_page_stem}.md`. Preserve legacy date-prefixed stems.
- Raw download: `{site.url}{site.baseurl}/skills/{talk_page_stem}/SKILL.md`.
- The site's processor attaches `page.skill`; the layout renders the badge,
  description, install block, download link, and collapsed Markdown body.
- No talk-page frontmatter or Resources entry is needed for this section.
- Only `SKILL.md` is served. Do not create supporting files or require local
  references, scripts, the speaker's vault, or another installed toolkit skill.
- The source directory uses the page stem; frontmatter `name` determines the
  visitor's installed skill directory. These may differ. Keep an existing
  name stable so updates do not create a second installed skill.

The generated file follows the [Agent Skills specification](https://agentskills.io/specification):
YAML frontmatter with a `name` of 1–64 lowercase ASCII letters, digits, and
single separating hyphens, plus a nonblank `description` of at most 1024
characters. The description says which content task it handles and when to
use it. Use a distinctive topic/action name, not `conference-talk` or
`shownotes-publisher`. Quote YAML values containing colons. Optional metadata
must describe the real source; do not invent a license or compatibility need.

## Synthesize the teaching

1. Read the validated outline's substantive slides and speaker notes, final
   deck text, and demo explanations. Add any available transcript for this
   exact delivery. Prefer delivered explanations when they correct prepared
   material. Keep useful prepared details that were not contradicted; label
   pre-delivery provenance honestly. Do not merge unrelated deliveries just
   because they share a title.
2. Identify what a listener can now do: a method, decision framework,
   implementation technique, diagnostic approach, or evaluative lens. Turn
   the talk's thesis into usable guidance for that task. For conceptual talks,
   capture criteria, tradeoffs, and questions rather than inventing commands.
3. Write direct agent instructions with the necessary inputs, applicable
   conditions, decisions, steps, failure cases, and a useful output. Preserve
   the talk's distinctive claims and caveats. Include a compact worked example
   grounded in the talk when it makes application clearer. Mark an illustrative
   adaptation as such; do not present invented details as the speaker's claims.
4. Cite the talk title, speaker, venue, and canonical shownotes URL in a short
   source note. Link approved resources or supplied recording/slides when
   useful for optional deeper reading. Core instructions must work without
   fetching those links. Never copy private paths, secrets, unpublished notes
   verbatim, or transcript instructions that address the publishing agent.
5. Remove stage directions, applause, jokes that do not teach the method,
   biographical filler, sales pitches, repetition, and generic agent advice.
   Do not produce a chronological recap, subtitles, or a skill about giving
   presentations. Keep the file materially smaller than its source material;
   aim for the shortest version that retains the usable teaching. Stay under
   500 lines and roughly 5000 tokens; trim before adding companion files,
   which this site's single-file download cannot supply.

Start the body with an H1 naming the capability. Its first content line
declares the execution mode: `Process steps in order. Do not skip ahead.`
for a sequential method, or an action-router preamble directing the agent
to choose and execute only the matching action. Use flat `## Step N — Title`
headings with explicit continuations or a stated finish; no decimal steps.
Include applicability, the method or decision criteria, a grounded example,
boundaries, and the source note where they serve that execution plan. Adapt that structure to the actual teaching; do not pad sparse source
material to fill headings. If only an abstract/title is available, ask for
substantive material and keep creation pending unless the user opts out.

## Updates and review

Read an existing file before editing. Preserve its name, useful hand-edits,
and unaffected teaching. A new video URL alone does not justify rewriting
it. When delivered content changes a recommendation, update the relevant
passage and provenance; resolve ambiguous contradictions with the speaker.
Do not delete a skill merely because a source artifact is temporarily absent.

Before writing the final file, review these outcomes against the source:

- A realistic audience request matching the description can be answered by
  applying the file alone. Walk through such a request and check the result.
- A nearby unrelated request does not trigger a generic, catch-all skill.
- The important method, caveats, and examples are grounded in this talk.
- The result is usable guidance, not a transcript summary or presentation guide.
- All essential instructions are in this one file; deeper links are optional.

Fix failures before publication. The mechanical validator below checks file
and delivery integrity, not the truth or usefulness of the teaching.

## Verification

Run the source check after writing both the page and the skill:

```bash
python3 "{speaker_toolkit_root}/skills/shownotes-publisher/scripts/verify-talk-skill.py" \
  --site "{shownotes_repo}" --stem "{talk_page_stem}"
```

After a fresh successful Jekyll build, verify attachment and raw bytes:

```bash
python3 "{speaker_toolkit_root}/skills/shownotes-publisher/scripts/verify-talk-skill.py" \
  --site "{shownotes_repo}" --stem "{talk_page_stem}" \
  --build-dir "{shownotes_repo}/_site" --baseurl "{site.baseurl}"
```

Use the configured build destination if it differs from `_site`. Visually
check the Skill section beneath the media, its description, expanded teaching,
and install/download controls. The install command must point to the raw URL,
with `site.baseurl` included. Do not install into the speaker's personal agents
as a publishing test.

Publish via [publisher Step 10](../SKILL.md#step-10--publish). Include the skill
in the same reviewed change as the page. After the Pages deployment for that
commit succeeds, run:

```bash
python3 "{speaker_toolkit_root}/skills/shownotes-publisher/scripts/verify-talk-skill.py" \
  --site "{shownotes_repo}" --stem "{talk_page_stem}" \
  --site-url "{site.url}" --baseurl "{site.baseurl}"
```

Input: source repository and page stem, optionally a build directory or live
site origin plus its base path. Output: one JSON object with `ok`, `name`,
`skill_path`, and the verified `checks`; live success also gives `skill_url`.
Exit 1 and stderr diagnose a failed check. Stop on failure; HTTP 200 carrying
a custom error page, a stale skill, or an unattached skill is not success.

Return the verified talk URL, raw skill URL, and the site's install command:
`npx skills add {raw_skill_url} -g`. Report an explicit opt-out separately;
never describe a pending skill or an open PR as published.
