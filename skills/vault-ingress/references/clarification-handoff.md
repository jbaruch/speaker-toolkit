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

- `offer_clarification` — compute the candidate topics and make the offer.
- `await_disposition` — the offer was made earlier, possibly by a run that was
  interrupted, and never answered. Put the same question again using the
  recorded `topics`. Silence was not an answer.
- `complete_clarification_session` — the speaker accepted and the session did
  not finish. Invoke `Skill(skill: "vault-clarification")` now with the
  recorded topics as the seed agenda, then record the session (below).
- `deliver_end_report` or `none` — nothing to offer; proceed to Step 10.

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
  --run-id "{run_id}" --now "{iso_timestamp}" --topic "{topic}" [--topic ...]
```

Exit 2 with `invalid_transition` and a "no longer has an analyzed talk" message
means the database changed since the run opened; nothing is asked — proceed to
Step 10. Otherwise `run.clarification.offer_mode` names the strength. The
bucket boundaries behind it are the script's (`run-obligations.py`,
top-of-file constants):

- **`inline`** (a same-week talk) — hand off inline, don't just recommend.
  Memory of the delivery is sharpest right after the talk, and verbal beats
  that never reached the auto-captions (bilingual jokes in a non-primary
  language, improvised asides, fly-bys that weren't in the deck) are only
  recoverable now. Do NOT bury this as a closing recommendation. Offer an
  immediate session, showing the candidate topics so the speaker sees exactly
  what it would cover. Recommended answer: accept.
- **`recommend_full`** (a recent or undated talk) — recommend the full session
  with the topics, noting that some verbatim details may already be lost.
  Ask whether to run it now; never start it unasked.
- **`recommend_compressed`** (older talks only) — memory has decayed and
  detailed recall is unreliable; recommend the compressed session instead of
  the full one. Ask whether to run it now; never start it unasked.

Then ask exactly one question and wait for the answer. Use the host's
single-question mechanism: `AskUserQuestion` with three options — accept
(labeled "(Recommended)" for `inline`), decline, defer — where the host has it;
otherwise one plain-text question naming the same three answers, then wait
for the reply. A host without the named tool never turns the offer into a
skip. An unanswered question leaves the run `offered`; the next run resumes it
from Step 1 and asks again.

## Record the Answer

Record the speaker's explicit answer, once:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/run-obligations.py" \
  "{vault_root}/tracking-database.json" record-disposition \
  --run-id "{run_id}" --now "{iso_timestamp}" \
  --disposition accepted|declined|deferred [--return-condition "{speaker's words}"]
```

- **accepted** — invoke `Skill(skill: "vault-clarification")` immediately,
  carrying the recorded topics as the session's seed agenda. When the session
  finishes: if it recorded new confirmed intents, improvement goals, or
  rhetoric-summary changes and `{vault_root}/speaker-profile.json` exists,
  re-run Step 7 so the profile reflects the answers before the end report.
  Then record the session, with `--profile-refreshed` when Step 7 re-ran:

  ```bash
  "{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/run-obligations.py" \
    "{vault_root}/tracking-database.json" record-session \
    --run-id "{run_id}" --now "{iso_timestamp}" [--profile-refreshed]
  ```

- **declined** — note it and move on; the talks are not reprocessed.
- **deferred** — `--return-condition` carries the speaker's own words for when
  to raise it again; the talks are not reprocessed.

Proceed immediately to Step 10.
