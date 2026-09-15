# Clarification Handoff by Delivery Recency

This is the complete normative Step 9 contract for `vault-ingress`. The offer,
the speaker's answer, and the session are obligations recorded in the run's
ledger ([schemas-obligations.md](schemas-obligations.md)). Delivery recency is
computed by `run-obligations.py` when Step 4 opens the run; never recompute
`today − date` by hand. Clarification quality decays fast, so the freshest
talks get an active handoff, not a footnote.

## Read the Obligation

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/run-obligations.py" \
  "{vault_root}/tracking-database.json" status --run-id "{run_id}"
```

`summary.next_action` decides what this step does. The summary's `offer_mode`
is a snapshot dated `recency_as_of`; the mode that counts is the one
`record-offer` returns below.

- `complete_downstream_steps` — the run's rendering, summary, profile, and
  goal steps were never recorded: go back to Step 4's rendering (when the
  batch returns are still on disk) and Steps 5–8, run `record-downstream`,
  then return here. `record-offer` refuses until then.
- `offer_clarification` — compute the candidate topics and make the offer.
- `await_disposition` — the offer was made earlier, possibly by a run that was
  interrupted, and never answered. Put the same question again using the
  recorded `topics`. Silence was not an answer.
- `complete_clarification_session` — the speaker accepted and the session did
  not finish. Invoke `Skill(skill: "vault-clarification")` now, carrying
  `run_id`; the skill reads the recorded `topics` from the run as its seed
  agenda. Then record the session (below).
- `deliver_end_report` or `none` — nothing to offer; proceed to Step 10.

A run listed under `pending`'s `deferred_offers` whose `return_condition` the
speaker has now met is raised again the same way: put the recorded offer with
its `topics` and record the new answer below — `record-disposition` accepts an
answer from `deferred`.

## Candidate Topics

For every analyzed talk in the run, collect:

- each per-talk `areas_for_improvement` entry;
- any `pattern_observations` the subagent flagged as **unverifiable from
  transcript alone** (low confidence, heavy reliance on visual cues,
  non-English dialogue without captions).

## Make the Offer

Record the offer first. The command refreshes each talk's recency against the
current database and this moment's `--now`, freezes it, and returns the run
with the `offer_mode` the offer must use:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/run-obligations.py" \
  "{vault_root}/tracking-database.json" record-offer \
  --run-id "{run_id}" --now "{iso_timestamp}" --topics-from "{topics_file}"
```

Write the candidate topics to `{topics_file}` first, one per line: a topic is
analysis-derived text and never goes through a shell string.

`offered: false` in the output means the database changed since the run
opened and no analyzed talk is left; the run is recorded as not applicable and
nothing is asked — proceed to Step 10. Otherwise
`run.clarification.offer_mode` names the strength; which talks earn which mode
is the script's rule (`run-obligations.py`, top-of-file constants):

- **`inline`** — hand off inline, don't just recommend.
  Memory of the delivery is sharpest right after the talk, and verbal beats
  that never reached the auto-captions (bilingual jokes in a non-primary
  language, improvised asides, fly-bys that weren't in the deck) are only
  recoverable now. Do NOT bury this as a closing recommendation. Offer an
  immediate session, showing the candidate topics so the speaker sees exactly
  what it would cover. Recommended answer: accept.
- **`recommend_full`** — recommend the full session with the topics, noting
  that some verbatim details may already be lost. Ask whether to run it now;
  never start it unasked.
- **`recommend_compressed`** — memory has decayed and detailed recall is
  unreliable; recommend the compressed session instead of the full one. Ask
  whether to run it now; never start it unasked.

Then ask exactly one question and wait for the answer. Use the host's
single-question mechanism: `AskUserQuestion` with three options — accept
(labeled "(Recommended)" for `inline`), decline, defer — where the host has it;
otherwise one plain-text question naming the same three answers, then wait
for the reply. A host without the named tool never turns the offer into a
skip. When the speaker chooses defer, ask one follow-up in plain text — "When
should I raise this again?" — and pass the answer, in the speaker's words, as
`--return-condition`. An unanswered question leaves the run `offered`; the next
run resumes it from Step 1 and asks again.

## Record the Answer

Record the speaker's explicit answer, once:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/run-obligations.py" \
  "{vault_root}/tracking-database.json" record-disposition \
  --run-id "{run_id}" --now "{iso_timestamp}" \
  --disposition accepted|declined|deferred [--return-condition "{speaker's words}"]
```

- **accepted** — invoke `Skill(skill: "vault-clarification")` immediately,
  carrying `run_id`. The skill resolves the recorded `topics` from the run as
  its seed agenda (its Step 2), opens the session with them (its Step 3), and
  returns `profile_inputs` with the covered topics (its Step 9). That typed
  call is the only way the session runs. A host that cannot make it leaves the
  session `pending` in the ledger — never skipped, never simulated — and the
  next run on a capable host resumes it through
  `complete_clarification_session`, or a standalone vault-clarification
  session picks it up through `session-agenda` and records it itself. When the session
  returns, record it with the `profile_inputs` it reported (`changed` for new
  confirmed intents, config fields, improvement goals, or rhetoric-summary
  changes):

  ```bash
  "{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/run-obligations.py" \
    "{vault_root}/tracking-database.json" record-session \
    --run-id "{run_id}" --now "{iso_timestamp}" \
    --profile-inputs changed|unchanged [--profile-refreshed]
  ```

  With `changed` and an existing `{vault_root}/speaker-profile.json`, the
  command refuses (`profile_refresh_required`) until Step 7 has re-run: do
  that (and Step 8 again when the session created, retired, or changed an
  improvement goal), then record the session with `--profile-refreshed`, so
  the end report reflects the answers. When the session followed a deferred offer answered
  after the report was delivered, `changed` inputs reopen the report
  (`report_reopened: true`): proceed through Step 10 to Step 11 again.

- **declined** — note it and move on; the talks are not reprocessed.
- **deferred** — `--return-condition` carries the speaker's own words for when
  to raise it again; the talks are not reprocessed.

Proceed immediately to Step 10.
