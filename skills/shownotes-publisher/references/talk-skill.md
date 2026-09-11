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
characters. The description identifies the talk and when to summarize, explain, or answer
questions about it. Use a distinctive talk-specific name, not `conference-talk`
or `shownotes-publisher`. Quote YAML values containing colons. Optional metadata
must describe the real source; do not invent a license or compatibility need.

## Build a talk knowledge brief

The audience task is understanding this talk. A visitor might ask their agent
“Summarize RoboCoders,” “What did the Pidge demo establish?” or “Did both
frameworks enforce the critic?” Supply the substance directly so the agent can
answer without fetching a recording and reconstructing its transcript. Do not
turn the talk into an operational playbook unless the user explicitly requests
that separate artifact.

### Sources and their roles

1. Load the rhetoric analysis for this exact delivery from the speaker's vault.
   Match title, event, date, and source receipts; a similar title is insufficient.
   Treat the analysis as a primary synthesis input, not an optional final check.
   Read its argument structure, persuasion, example/analogy roles, questions,
   transitions, callbacks, conclusion, and delivery-versus-plan findings. Consult
   detection evidence when a relevant interpretation needs grounding; do not
   dump pattern scores or the whole taxonomy into the published skill.
2. Read the validated outline's substantive slides and notes, final deck text,
   demo explanations, and available transcript. Use these to verify what was
   said or shown and fill factual detail. Prefer observed delivery over a
   contradicted plan. Preserve useful prepared details only with honest
   provenance; never describe an unperformed planned demo as observed.
3. Separate three kinds of content: the speaker's stated claim, what a demo
   actually established, and an interpretation from rhetoric analysis. Analysis
   explains the argument but does not override primary evidence or establish
   private intent, audience reception, or measured effectiveness. Correct or
   qualify conflicts before publication.
4. For a delivered talk with missing or mismatched rhetoric analysis, invoke
   `Skill(skill: "vault-ingress")` for that delivery and resume once its analysis
   is available. Do not silently substitute a generic transcript summary. For a
   pre-talk skill, use the approved rhetorical architecture and any
   `rhetorical-review.md` as planned analysis, clearly label that status, and
   refresh against delivered analysis after the event. If the user explicitly
   accepts a provisional brief without analysis, disclose that limitation.

### Synthesis

Build the brief around the analysis-derived argument, not a transcript's word
count or the order in which tool names appear:

- Establish talk identity, central thesis, and the question or assumption it
  challenges. Explain the conclusion at a depth suitable for a short summary.
- Recover the argument's progression: what each demonstration, contrast,
  analogy, countervoice, or callback contributes to the next claim. Translate
  rhetoric terminology into substance an audience member can understand.
- Explain key concepts, distinctions, examples, and demo outcomes. Preserve why
  an example matters, not just that it appeared. Give under-time-pressure but
  load-bearing conclusions their proper weight rather than weighting by airtime.
- Preserve objections and qualifications, including an unexpected live result
  that changes what can be concluded. Do not smooth a partial failure into a
  successful planned narrative.
- Retain humor or cultural references when they carry an argument. Drop filler,
  applause, logistics, decorative jokes, design metrics, and private coaching
  recommendations that do not help someone understand the talk. Do not turn an
  analyst's suggestion for a future delivery into something this talk taught.
- Add source links for attribution and deeper detail. State that the brief draws
  on delivery-specific rhetoric analysis reconciled with source materials.
  Never require the audience agent to access the private vault or supporting
  files. Do not copy private paths, secrets, analysis receipts, or unpublished
  notes verbatim.

The value beyond “summarize YouTube” is the recovered reasoning: why these
examples were chosen, what changes in the listener's understanding, and how the
argument resolves. A rhetoric-label inventory or a chronological recap alone
does not deliver that value. The analysis must shape the actual brief, not just
appear in a provenance sentence.

### Single-file structure

Use a talk-specific name for new skills. The description names the talk,
speaker/event, and summary/explanation/question-answering triggers. It must not
activate merely because someone wants to perform a related technical task.
Preserve an existing installed name on updates; revise the description and H1
to identify the talk unambiguously.

Start with an H1 naming the talk and knowledge capability, followed by
`Process steps in order. Do not skip ahead.` Keep the instruction wrapper
short, using flat numbered steps with explicit continuation and completion:

- `## Step 1 — Match the question`: identify this delivery and the supported
  audience requests; finish on a mismatched delivery, otherwise continue.
- `## Step 2 — Answer from the brief`: use the supplied content, adapt depth to
  the question, preserve claim/evidence/interpretation distinctions, then finish.
- `## Talk brief`: substantive knowledge under descriptive topic headings,
  including how the argument works, examples, caveats, and sources. These
  headings organize reference content; they are not tasks to execute.

Ordinary summaries and covered questions must need no network request. Fetch a
linked source only for a requested exact quote, timestamp, missing detail, or
other information not established by the brief. Never fabricate those details.
The depicted prompts and workflows remain content to explain, not instructions
to run tools, change files, launch workers, or perform external actions.

Keep the brief materially smaller than its source materials: under 500 lines
and roughly 5000 tokens. Favor useful coverage and argument over repetition.
Only this file is served; do not move necessary knowledge into companion files.
A title or abstract alone is insufficient; resolve missing substantive sources
before claiming completion unless the user accepts a provisional brief.

## Updates and review

Read the existing file. Preserve its installed name, useful hand-edits, and
unaffected content. A video URL alone does not require rewriting a brief. A new
delivered analysis can change its interpretation or evidence boundaries;
reconcile those findings before refreshing the affected passages. Do not delete
a skill merely because a source artifact is temporarily absent.

Review the following against the source materials and rhetoric analysis:

- “What was this talk about?” yields an accurate summary using the file alone.
- A concept/demo question yields the explanation and observed outcome directly.
- “Why did that example matter?” yields its role in the argument, grounded in
  the analysis and checked against the delivery. Record which analysis insights
  changed the brief during editorial review.
- The summary preserves the main conclusion, objections, and consequential
  live deviations; it does not over-weight banter or confuse airtime with weight.
- Exact-quote, timestamp, and missing-detail requests have an honest source path
  rather than invented answers. Interpretation is distinguishable from quotation.
- An unrelated implementation request does not trigger the skill or cause the
  talk's example commands to be executed.
- The single downloaded file carries the substance; attribution links are
  optional for ordinary use and no private source is required by the consumer.

Fix failures before publication. The mechanical validator checks delivery
integrity, not rhetorical fidelity, completeness, or answer quality.

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
check the Skill section beneath the media, its description, expanded talk brief,
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
