"""The seed-agenda contract between vault-ingress Step 9 and vault-clarification.

vault-ingress records the candidate topics in the run obligations ledger and
invokes vault-clarification for an accepted session; the session must open with
those topics, and the ledger session must be closed by whichever side owns the
invocation (#456 part two).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills/vault-clarification/SKILL.md"
HANDOFF = ROOT / "skills/vault-ingress/references/clarification-handoff.md"
LEDGER_SCHEMA = ROOT / "skills/vault-ingress/references/schemas-obligations.md"
RESOURCES_RULE = ROOT / "rules/resources-gathering-rules.md"

_STEP_HEADING = re.compile(r"^## Step (\d+) — (.+)$", re.MULTILINE)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _normalized(text: str) -> str:
    return " ".join(text.split())


def _steps(text: str) -> dict[int, tuple[str, str]]:
    """Map each ``## Step N — Title`` heading to its title and body."""
    matches = list(_STEP_HEADING.finditer(text))
    steps: dict[int, tuple[str, str]] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        number = int(match.group(1))
        assert number not in steps, f"duplicate Step {number}"
        steps[number] = (match.group(2).strip(), text[match.end() : end])
    return steps


def test_steps_are_flat_contiguous_and_chained() -> None:
    steps = _steps(_read(SKILL))

    assert sorted(steps) == list(range(1, len(steps) + 1))
    last = max(steps)
    for number, (_title, body) in steps.items():
        if number == last:
            assert "Finish here." in body
        else:
            assert f"Step {number + 1}" in body, f"Step {number} never continues"


def test_seed_agenda_is_resolved_through_the_ledger_owner() -> None:
    title, body = _steps(_read(SKILL))[2]
    normalized = _normalized(body)

    assert title == "Resolve the Seed Agenda"
    assert "skills/vault-ingress/scripts/run-obligations.py" in body
    command = (
        '"{vault_root}/tracking-database.json" session-agenda [--run-id "{run_id}"]'
    )
    assert command in body
    assert "`session.topics`, in its recorded order, is the seed agenda" in normalized
    assert "`session: null` means this session is standalone" in normalized
    assert "the `pending_sessions` docstring" in normalized
    for reason in ("invalid_transition", "run_not_found", "ledger_not_adopted"):
        assert f"(`{reason}`)" in normalized
    assert "never open the ledger file directly" in normalized
    assert "never write it in this step" in normalized
    assert "never guess the topics" in normalized
    for agent_owned in (
        "earliest `opened_at`",
        "`next_action`",
        " pending\n",
        "status --run-id",
    ):
        assert agent_owned not in body


def test_rhetoric_clarification_opens_with_the_seed_agenda() -> None:
    title, body = _steps(_read(SKILL))[3]
    normalized = _normalized(body)

    assert title == "Rhetoric Clarification"
    seed = normalized.index("Open with the seed agenda when Step 2 found one")
    own = normalized.index("surprising, contradictory, or ambiguous")
    assert seed < own
    assert "in its recorded order, one topic per `AskUserQuestion`" in normalized
    assert "before anything this session finds on its own" in normalized
    assert "never dropped silently" in normalized


def test_session_completion_closes_the_ledger_session() -> None:
    title, body = _steps(_read(SKILL))[9]
    normalized = _normalized(body)

    assert title == "Mark Session Complete"
    assert "`config.clarification_sessions_completed + 1`" in body
    assert "Name `profile_inputs`" in normalized
    assert "clarification-handoff.md#record-the-answer" in body
    assert "Do not record it here" in normalized
    assert '"{vault_root}/tracking-database.json" record-session' in body
    assert "--profile-inputs changed|unchanged [--profile-refreshed]" in body
    assert "`profile_refresh_required`" in body
    assert 'Skill(skill: "vault-profile")' in body
    assert "`report_reopened: true`" in body
    assert "stays pending for the next run to record" in normalized


def test_tracking_write_window_names_the_renumbered_steps() -> None:
    skill = _read(SKILL)
    steps = _steps(skill)

    assert "Every tracking write in Steps 3–9 is current-only." in skill
    assert steps[3][0] == "Rhetoric Clarification"
    assert steps[9][0] == "Mark Session Complete"
    assert "Steps 2–8" not in skill


def _bullet(text: str, start: str, end: str) -> str:
    """The normalized text of one list item, from its opening marker to the next."""
    begin = text.index(start)
    return _normalized(text[begin : text.index(end, begin)])


def test_handoff_carries_the_run_id_and_names_the_skill_steps() -> None:
    handoff = _read(HANDOFF)
    steps = _steps(_read(SKILL))

    assert "carrying the recorded topics as the session's seed agenda" not in handoff
    resumption = _bullet(
        handoff, "- `complete_clarification_session` —", "- `deliver_end_report`"
    )
    acceptance = _bullet(handoff, "- **accepted** —", "- **declined** —")
    for branch in (resumption, acceptance):
        assert 'Skill(skill: "vault-clarification")' in branch
        assert "carrying `run_id`" in branch
    for step, title in (
        (2, "Resolve the Seed Agenda"),
        (3, "Rhetoric Clarification"),
        (9, "Mark Session Complete"),
    ):
        assert f"(its Step {step})" in handoff
        assert steps[step][0] == title
    assert "picks it up through `session-agenda` and records it itself" in handoff
    assert "record it with the `profile_inputs` it reported" in _normalized(handoff)


def test_ledger_schema_names_vault_clarification_as_a_reader() -> None:
    schema = _normalized(_read(LEDGER_SCHEMA))

    assert "vault-clarification and vault-profile never read it" not in schema
    assert "vault-clarification Step 2 (`session-agenda`)" in schema
    assert "vault-profile never reads it" in schema
    recorded = "records the session `session-agenda` selected through `record-session`"
    assert recorded in schema
    assert "the script stays the only writer" in schema
    assert "`session-agenda [--run-id]` emits" in schema


def test_resources_rule_points_at_the_infrastructure_step() -> None:
    steps = _steps(_read(SKILL))

    assert steps[6][0] == "Speaker Infrastructure (first session only)"
    assert "during vault-clarification (Step 6 infrastructure capture)" in _read(
        RESOURCES_RULE
    )
