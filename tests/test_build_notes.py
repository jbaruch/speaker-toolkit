"""Tests for build_notes.py — a build parent's notes, split across its frames.

The owner's bug: every word of a build slide's notes landed on its LAST frame,
so the infinite-monkeys setup sat on the GPU reveal it leads up to. Each frame
must carry the words spoken while it is on screen.
"""

import pytest

# The owner's slide 6, as rendered from its outline script: one line per script
# item, the `cue: "BUILD 01"` item as the line [BUILD 01].
MONKEY_NOTE = (
    'Now those two differences start to matter. "Describes itself to a model" '
    "means your consumer is a model.\n"
    "(beat)\n"
    "You know the infinite monkeys theorem.\n"
    "(beat)\n"
    "This one I WILL explain. Infinite monkeys, with infinite typewriters, given "
    "infinite time, will eventually type the works of Shakespeare.\n"
    "What we have with LLMs are monkeys.\n"
    "[BUILD 01]\n"
    "We just gave them GPUs, and the randomness is skewed towards Shakespeare. "
    "Sometimes it gets it right, sometimes almost right, and sometimes completely "
    "wrong."
)
MONKEY_FRAME_00 = MONKEY_NOTE.split("\n[BUILD 01]\n")[0]
MONKEY_FRAME_01 = MONKEY_NOTE.split("\n[BUILD 01]\n")[1]


def test_the_monkey_setup_lands_on_the_first_frame(build_notes):
    segments, warnings = build_notes.split_note(MONKEY_NOTE, 2, "6", [1])
    assert segments == [MONKEY_FRAME_00, MONKEY_FRAME_01]
    assert segments[0].endswith("What we have with LLMs are monkeys.")
    assert segments[1].startswith("We just gave them GPUs")
    assert warnings == []


def test_the_cue_line_never_reaches_a_frame(build_notes):
    segments, _ = build_notes.split_note(MONKEY_NOTE, 2, "6", [1])
    assert not any("[BUILD" in segment for segment in segments)


def test_a_note_opening_on_a_cue_leaves_frame_00_silent(build_notes):
    # The owner's slide 8: an empty plate, then one specimen per cue.
    note = "[BUILD 01]\nSpecimen one.\n[BUILD 02]\nSpecimen two.\n[BUILD 03]\nThree."
    segments, warnings = build_notes.split_note(note, 4, "8", [1, 2, 3])
    assert segments == ["", "Specimen one.", "Specimen two.", "Three."]
    assert warnings == []


def test_an_explicit_build_00_cue_keeps_its_text_on_frame_00(build_notes):
    note = "Before.\n[BUILD 00]\nStill frame zero.\n[BUILD 01]\nReveal."
    segments, _ = build_notes.split_note(note, 2, "2", [0, 1])
    assert segments == ["Before.\nStill frame zero.", "Reveal."]


def test_a_skipped_step_is_a_silent_frame(build_notes):
    note = "Setup.\n[BUILD 02]\nPayoff."
    segments, _ = build_notes.split_note(note, 3, "4", [2])
    assert segments == ["Setup.", "", "Payoff."]


def test_crlf_notes_split_on_the_same_cue(build_notes):
    note = MONKEY_NOTE.replace("\n", "\r\n")
    segments, _ = build_notes.split_note(note, 2, "6", [1])
    assert segments[1] == MONKEY_FRAME_01
    assert segments[0].endswith("What we have with LLMs are monkeys.")


def test_an_empty_note_gives_every_frame_an_empty_note(build_notes):
    assert build_notes.split_note("  \n", 3, "5", [1]) == (["", "", ""], [])


def test_a_cue_past_the_last_frame_is_refused(build_notes):
    with pytest.raises(build_notes.BuildNotesError) as exc:
        build_notes.split_note("A.\n[BUILD 02]\nB.", 2, "6")
    message = str(exc.value)
    assert "[BUILD 02]" in message
    assert "2 build frame(s), [BUILD 00] to [BUILD 01]" in message


@pytest.mark.parametrize(
    "note, named",
    [
        ("A.\n[BUILD 02]\nB.\n[BUILD 01]\nC.", "[BUILD 01] after [BUILD 02]"),
        ("A.\n[BUILD 01]\nB.\n[BUILD 01]\nC.", "[BUILD 01] after [BUILD 01]"),
    ],
    ids=["out-of-order", "repeated"],
)
def test_cues_out_of_order_are_refused(build_notes, note, named):
    with pytest.raises(build_notes.BuildNotesError) as exc:
        build_notes.split_note(note, 3, "6")
    assert named in str(exc.value)
    assert "increasing order" in str(exc.value)


def test_an_unpadded_cue_is_refused_with_its_canonical_spelling(build_notes):
    with pytest.raises(build_notes.BuildNotesError) as exc:
        build_notes.split_note("A.\n[BUILD 1]\nB.", 2, "6")
    assert "write it as [BUILD 01]" in str(exc.value)


def test_a_note_rendered_without_its_outline_cues_is_refused(build_notes):
    # The outline cues BUILD 01, but the notes map lost the marker line: without
    # this check the whole note would quietly sit on frame 00.
    note = MONKEY_NOTE.replace("\n[BUILD 01]\n", "\n")
    with pytest.raises(build_notes.BuildNotesError) as exc:
        build_notes.split_note(note, 2, "6", [1])
    message = str(exc.value)
    assert "outline script cues [BUILD 01]" in message
    assert "note marks no cue" in message


def test_a_cueless_note_goes_whole_on_frame_00_with_a_warning(build_notes):
    segments, warnings = build_notes.split_note("All of it.", 3, "7", [])
    assert segments == ["All of it.", "", ""]
    assert len(warnings) == 1
    assert warnings[0].startswith("WARN: slide 7 has 3 build frames")
    assert "frame 00" in warnings[0]


def test_a_single_frame_build_takes_its_note_without_a_warning(build_notes):
    assert build_notes.split_note("Only frame.", 1, "7", []) == (["Only frame."], [])


@pytest.mark.parametrize(
    "line", ["[SLIDE 2 UP — BUILD 00]", "**[BUILD 01]**"], ids=["compound", "bold"]
)
def test_a_near_miss_cue_stays_in_the_text_and_warns(build_notes, line):
    segments, warnings = build_notes.split_note(f"{line}\nSetup.", 2, "2", [])
    assert segments[0] == f"{line}\nSetup."
    assert any(line in w and "moves nothing" in w for w in warnings)


def test_outline_cues_take_only_bare_build_cues(build_notes):
    cues = [None, "SLIDE 2 UP — BUILD 00", "BUILD 01", None, " BUILD 02 ", "BEAT"]
    assert build_notes.outline_cues(cues) == [1, 2]


def test_the_expanded_map_rekeys_every_slide_past_the_frames_before_it(build_notes):
    # Pre-expansion deck: slides 1..6, build parents at 2 (two frames) and 4
    # (three frames). Post-expansion: 1, 2a, 2b, 3, 4a, 4b, 4c, 5, 6.
    notes = {0: "one", 1: "parent two", 2: "three", 3: "parent four", 5: "six"}
    frames = {2: ["2a", "2b"], 4: ["4a", "", "4c"]}
    assert build_notes.expanded_notes_map(notes, frames) == {
        "0": "one",
        "1": "2a",
        "2": "2b",
        "3": "three",
        "4": "4a",
        "5": "",
        "6": "4c",
        "8": "six",
    }


def test_the_expanded_map_carries_the_monkey_frames(build_notes):
    segments, _ = build_notes.split_note(MONKEY_NOTE, 2, "6", [1])
    notes = {4: "slide five", 5: MONKEY_NOTE, 6: "You would never hire this."}
    expanded = build_notes.expanded_notes_map(notes, {6: segments})
    assert expanded == {
        "4": "slide five",
        "5": MONKEY_FRAME_00,
        "6": MONKEY_FRAME_01,
        "7": "You would never hire this.",
    }


def test_a_parent_without_frames_is_refused(build_notes):
    with pytest.raises(build_notes.BuildNotesError):
        build_notes.expanded_notes_map({}, {3: []})


def test_normalize_turns_keys_into_indices_and_null_into_empty(build_notes):
    assert build_notes.normalize_notes_map({"0": "a", "2": None}) == {0: "a", 2: ""}


@pytest.mark.parametrize(
    "notes_map, named",
    [
        ([], "must be an object"),
        ({"-1": "x"}, "not a 0-based slide number"),
        ({"two": "x"}, "not a 0-based slide number"),
        ({"²": "x"}, "not a 0-based slide number"),
        ({"6": "a", "06": "b"}, "twice"),
        ({"6": 12}, "must be a string"),
    ],
    ids=["not-object", "negative", "word", "unicode-digit", "duplicate", "number"],
)
def test_normalize_refuses_a_malformed_map(build_notes, notes_map, named):
    with pytest.raises(build_notes.BuildNotesError) as exc:
        build_notes.normalize_notes_map(notes_map)
    assert named in str(exc.value)
