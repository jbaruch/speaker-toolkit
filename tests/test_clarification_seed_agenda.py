"""The seed-agenda contract between vault-ingress Step 9 and vault-clarification.

vault-ingress records the candidate topics in the run obligations ledger and
invokes vault-clarification for an accepted session; the session opens with
those topics, and the ledger session is closed by whichever side owns the
invocation (#456 part two). The behavior itself, topics handed over in recorded
order until the session is recorded, runs against the owner script in
``tests/test_run_obligations.py`` (``session-agenda``). These checks cover the
syntax the prose must carry: the commands it runs, the typed calls it makes,
the fields and reason codes it reads, and the step numbers it cross-references.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills/vault-clarification/SKILL.md"
HANDOFF = ROOT / "skills/vault-ingress/references/clarification-handoff.md"
LEDGER_SCHEMA = ROOT / "skills/vault-ingress/references/schemas-obligations.md"
RESOURCES_RULE = ROOT / "rules/resources-gathering-rules.md"
CONFIG_SCHEMA = ROOT / "skills/vault-clarification/references/schemas-config.md"

_STEP_HEADING = re.compile(r"^## Step (\d+) — (.+)$", re.MULTILINE)
_BASH_FENCE = re.compile(r"```bash\n(.*?)```", re.DOTALL)
OWNER_SCRIPT = (
    '"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/'
    'run-obligations.py"'
)


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


def _commands(body: str) -> list[str]:
    """Each fenced bash block as one command line, continuations joined."""
    return [
        _normalized(block.replace("\\\n", " ")) for block in _BASH_FENCE.findall(body)
    ]


def _bullet(text: str, start: str, end: str) -> str:
    """The normalized text of one list item, from its opening marker to the next."""
    begin = text.index(start)
    return _normalized(text[begin : text.index(end, begin)])


def _step_number(pattern: str, text: str) -> int:
    match = re.search(pattern, _normalized(text))
    assert match, pattern
    return int(match.group(1))


def test_steps_are_flat_contiguous_and_chained() -> None:
    steps = _steps(_read(SKILL))

    assert sorted(steps) == list(range(1, len(steps) + 1))
    last = max(steps)
    for number, (_title, body) in steps.items():
        if number == last:
            assert "Finish here." in body
        else:
            assert f"Step {number + 1}" in body, f"Step {number} never continues"


def test_seed_agenda_step_runs_the_owner_command() -> None:
    title, body = _steps(_read(SKILL))[2]

    assert title == "Resolve the Seed Agenda"
    commands = _commands(body)
    assert len(commands) == 1
    assert commands[0].startswith(OWNER_SCRIPT)
    assert commands[0].endswith(
        '"{vault_root}/tracking-database.json" session-agenda [--run-id "{run_id}"]'
    )
    for read_field in ("`session.run_id`", "`session.topics`", "`session: null`"):
        assert read_field in body
    for reason in ("`invalid_transition`", "`run_not_found`", "`ledger_not_adopted`"):
        assert reason in body
    # The selection rule is the script's: named by its anchor, never restated.
    assert "`pending_sessions`" in body
    for restated in ("`opened_at`", "`next_action`", " pending\n", "status --run-id"):
        assert restated not in body


def test_rhetoric_clarification_reads_the_seed_agenda_and_asks_one_at_a_time() -> None:
    title, body = _steps(_read(SKILL))[3]

    assert title == "Rhetoric Clarification"
    assert "seed agenda" in body
    assert _step_number(r"seed agenda when Step (\d+)", body) == 2
    assert "`AskUserQuestion`" in body
    assert "AskUserQuestion(" in body


def test_session_completion_runs_the_owner_command_and_typed_calls() -> None:
    title, body = _steps(_read(SKILL))[9]

    assert title == "Mark Session Complete"
    assert "`config.clarification_sessions_completed + 1`" in body
    assert "`set_config`" in body
    commands = _commands(body)
    assert len(commands) == 1
    assert commands[0].startswith(OWNER_SCRIPT)
    assert commands[0].endswith(
        '"{vault_root}/tracking-database.json" record-session '
        '--run-id "{run_id}" --now "{iso_timestamp}" '
        "--profile-inputs changed|unchanged [--profile-refreshed]"
    )
    assert "clarification-handoff.md#record-the-answer" in body
    assert 'Skill(skill: "vault-profile")' in body
    for read_field in (
        "`profile_inputs`",
        "`profile_refresh_required`",
        "`--profile-refreshed`",
        "`report_reopened: true`",
    ):
        assert read_field in body
    assert _step_number(r"ledger session Step (\d+) resolved", body) == 2


def test_tracking_write_window_spans_the_mutating_steps() -> None:
    skill = _read(SKILL)
    steps = _steps(skill)

    match = re.search(
        r"Every tracking write in Steps (\d+)–(\d+) is current-only", skill
    )
    assert match
    first, last = int(match.group(1)), int(match.group(2))
    assert steps[first][0] == "Rhetoric Clarification"
    assert last == max(steps)


def test_handoff_invokes_the_skill_with_run_id_in_both_branches() -> None:
    handoff = _read(HANDOFF)
    steps = _steps(_read(SKILL))

    resumption = _bullet(
        handoff, "- `complete_clarification_session` —", "- `deliver_end_report`"
    )
    acceptance = _bullet(handoff, "- **accepted** —", "- **declined** —")
    for branch in (resumption, acceptance):
        assert 'Skill(skill: "vault-clarification")' in branch
        assert "`run_id`" in branch
        assert "`topics`" in branch
    for number, title in (
        (2, "Resolve the Seed Agenda"),
        (3, "Rhetoric Clarification"),
        (9, "Mark Session Complete"),
    ):
        assert f"(its Step {number})" in acceptance
        assert steps[number][0] == title
    assert "`session-agenda`" in acceptance
    assert "`profile_inputs`" in acceptance
    assert '"{vault_root}/tracking-database.json" record-session' in acceptance


def test_ledger_schema_lists_the_reader_and_the_command() -> None:
    schema = _read(LEDGER_SCHEMA)
    steps = _steps(_read(SKILL))

    access = schema[schema.index("## Ownership and Access") : schema.index("## Root")]
    readers = _bullet(access, "- Readers:", "\n- ")
    assert "vault-clarification" in readers
    assert "`session-agenda`" in readers
    assert steps[_step_number(r"vault-clarification Step (\d+)", readers)][0] == (
        "Resolve the Seed Agenda"
    )
    assert "never read it" not in readers
    assert "`record-session`" in _normalized(access)
    assert re.search(r"^\| `session-agenda \[--run-id\]` \|", schema, re.MULTILINE)
    contract = schema[schema.index("## Reader Contract") : schema.index("## Migration")]
    assert "`session-agenda [--run-id]`" in contract
    for output_field in ("`session`", "`pending_sessions`", "`adopt_required`"):
        assert output_field in contract
    assert "`pending_sessions` docstring" in contract
    for reason in ("`ledger_not_adopted`", "`run_not_found`", "`invalid_transition`"):
        assert reason in contract


def test_infrastructure_step_references_follow_the_numbering() -> None:
    skill = _read(SKILL)
    steps = _steps(skill)
    intro = skill[: skill.index("## Step 1")]

    infrastructure = 6
    assert steps[infrastructure][0] == "Speaker Infrastructure (first session only)"
    assert (
        _step_number(r"infrastructure capture in Step (\d+)", intro) == infrastructure
    )
    assert _step_number(r"asked during Step (\d+)", _read(CONFIG_SCHEMA)) == (
        infrastructure
    )
    assert (
        _step_number(
            r"vault-clarification \(Step (\d+) infrastructure capture\)",
            _read(RESOURCES_RULE),
        )
        == infrastructure
    )


def test_changed_profile_inputs_name_config_fields_on_both_sides() -> None:
    step_nine = _normalized(_steps(_read(SKILL))[9][1])
    acceptance = _bullet(_read(HANDOFF), "- **accepted** —", "- **declined** —")

    skill_definition = step_nine[
        step_nine.index("`profile_inputs`") : step_nine.index("`unchanged`")
    ]
    assert "config field" in skill_definition
    assert _step_number(r"config field \(Step (\d+)\)", skill_definition) == 6
    handoff_definition = acceptance[
        acceptance.index("`changed`") : acceptance.index("record-session")
    ]
    assert "config fields" in handoff_definition
