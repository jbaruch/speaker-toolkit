"""TSV-to-offline-reviewer integration and executable JavaScript decisions."""

import csv
import importlib.util
import io
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

import pytest

from test_crop_frames import bundle as bundle, recording as recording


SCRIPTS = Path(__file__).parents[1] / "skills" / "vault-ingress" / "scripts"


@pytest.fixture
def reviewer():
    spec = importlib.util.spec_from_file_location(
        "crop_reviewer_builder", SCRIPTS / "build-crop-reviewer.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def proposal(reviewer, recording, bundle, **changes):
    row = dict(
        zip(
            reviewer.COLUMNS,
            [
                "dQw4w9WgXcQ",
                "A diagram worth keeping",
                "ExampleConf",
                "2025-01-01",
                str(recording),
                str(recording.parent / "extracted"),
                str(bundle / "manifest.json"),
                "crop",
                "0.1,0.1,0.8,0.9",
            ],
        )
    )
    row.update(changes)
    return row


def tsv(reviewer, rows):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=reviewer.COLUMNS, delimiter="\t")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def build(reviewer, recording, bundle, **changes):
    row = proposal(reviewer, recording, bundle, **changes)
    proposals = recording.parent / "proposals.tsv"
    proposals.write_text(tsv(reviewer, [row]), encoding="utf-8")
    output = recording.parent / "review.html"
    result = reviewer.build_reviewer(proposals, output, batch_id="test-batch")
    return row, proposals, output, result


def embedded(output):
    html = output.read_text(encoding="utf-8")
    talks = re.search(r"const TALKS = (.*);\nconst BATCH", html)
    batch = re.search(r"const BATCH = (.*);\n", html)
    assert talks and batch
    return html, json.loads(talks.group(1)), json.loads(batch.group(1))


def test_real_bundle_build_is_offline_and_idempotent(reviewer, recording, bundle):
    row, proposals, output, result = build(reviewer, recording, bundle)
    html, talks, batch = embedded(output)
    assert result["frames_per_talk"] == {row["id"]: 6}
    assert len(talks[0]["frames"]) == 6
    assert all(
        frame["image"].startswith("data:image/jpeg;base64,")
        for frame in talks[0]["frames"]
    )
    assert "fonts.googleapis" not in html
    assert 'src="http' not in html
    assert "__TALKS_JSON__" not in html
    assert talks[0]["mode"] == "crop"
    assert "verdict" not in talks[0]
    assert batch["fingerprint"] == result["batch_fingerprint"]
    assert "--expected-source-sha256" in talks[0]["command_prefix"]
    before = output.read_bytes()
    assert reviewer.build_reviewer(proposals, output, batch_id="test-batch")["reused"]
    assert output.read_bytes() == before


def test_talks_with_different_frame_counts_are_reported(reviewer, recording, bundle):
    import crop_frames

    second = recording.parent / "twelve-frames"
    crop_frames.sample_video(recording, second)
    rows = [
        proposal(reviewer, recording, bundle),
        proposal(
            reviewer,
            recording,
            second,
            id="abcdefghijk",
            title="A second delivery",
            mode="no-slides",
            region="",
        ),
    ]
    proposals = recording.parent / "two.tsv"
    proposals.write_text(tsv(reviewer, rows), encoding="utf-8")
    output = recording.parent / "two.html"
    result = reviewer.build_reviewer(proposals, output, batch_id="mixed-counts")
    assert result["frames_per_talk"] == {"dQw4w9WgXcQ": 6, "abcdefghijk": 12}
    assert embedded(output)[1][1]["mode"] == "no-slides"


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "../../escape"},
        {"id": "too-short"},
        {"mode": "approved"},
        {"region": "nan,0,1,1"},
        {"region": "0,0,inf,1"},
        {"region": "0,0,0,1"},
        {"region": "0,0,2,1"},
        {"region": "0,0,1"},
        {"mode": "full-frame", "region": "0,0,1,1"},
        {"title": "first\nsecond"},
        {"video_path": "$V/talk.mp4"},
        {"title": ""},
    ],
)
def test_bad_proposals_fail_before_media_io(reviewer, tmp_path, changes):
    row = proposal(reviewer, tmp_path / "talk.mp4", tmp_path, **changes)
    with pytest.raises(reviewer.ReviewerError):
        reviewer.parse_proposals(tsv(reviewer, [row]))


def test_duplicate_ids_empty_or_wrong_header_fail(reviewer, tmp_path):
    row = proposal(reviewer, tmp_path / "talk.mp4", tmp_path)
    for text in [
        tsv(reviewer, [row, row]),
        tsv(reviewer, []),
        "id\ttitle\nabc\ttalk\n",
    ]:
        with pytest.raises(reviewer.ReviewerError):
            reviewer.parse_proposals(text)


def test_script_embedding_and_command_arguments_cannot_inject(
    reviewer, recording, bundle
):
    attack = "</script><script>alert('x')</script> __BATCH_JSON__ __TALKS_JSON__"
    target = str(recording.parent / "output ' $(touch /tmp/injected) ; #")
    _, proposals, output, _ = build(
        reviewer, recording, bundle, title=attack, output_dir=target
    )
    html, talks, _ = embedded(output)
    assert attack not in html
    assert talks[0]["title"] == attack
    assert html.count("</script>") == 1
    args = shlex.split(talks[0]["command_prefix"])
    assert args[3] == target
    assert args[2] == str(recording)
    alternative = recording.parent / "marker-batch.html"
    reviewer.build_reviewer(proposals, alternative, batch_id="batch__TALKS_JSON__")
    assert embedded(alternative)[2]["id"] == "batch__TALKS_JSON__"


def test_changed_proposal_requires_fresh_output_and_new_approval_identity(
    reviewer, recording, bundle
):
    row, proposals, output, first = build(reviewer, recording, bundle)
    before = output.read_bytes()
    row["region"] = "0.2,0.2,0.7,0.8"
    proposals.write_text(tsv(reviewer, [row]), encoding="utf-8")
    with pytest.raises(reviewer.ReviewerError, match="output_conflict"):
        reviewer.build_reviewer(proposals, output, batch_id="test-batch")
    assert output.read_bytes() == before
    second = reviewer.build_reviewer(
        proposals, recording.parent / "changed.html", batch_id="test-batch"
    )
    assert first["batch_fingerprint"] != second["batch_fingerprint"]


def test_exported_command_runs_for_dash_prefixed_video_id(reviewer, recording, bundle):
    _, _, output, _ = build(
        reviewer, recording, bundle, id="-abcdefghij", mode="full-frame", region=""
    )
    talk = {
        key: value for key, value in embedded(output)[1][0].items() if key != "frames"
    }
    command = run_javascript(
        "const talk = "
        + json.dumps(talk)
        + "; process.stdout.write(review.commands([talk], {[talk.id]:review.approve(review.initial(talk))}));"
    )
    args = shlex.split(command)
    assert args[-2:] == ["--", "-abcdefghij"]
    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["source_video_id"] == "-abcdefghij"
    assert report["review_required"] is False
    assert (
        report["source_receipt"]["source_sha256"]
        == args[args.index("--expected-source-sha256") + 1]
    )


def test_missing_frames_never_builds_even_for_proposed_no_slides(
    reviewer, recording, bundle
):
    (bundle / "frame-001.jpg").unlink()
    with pytest.raises(reviewer.SupervisorError):
        build(reviewer, recording, bundle, mode="no-slides", region="")
    assert not (recording.parent / "review.html").exists()


def test_replaced_recording_rejects_stale_samples(reviewer, recording, bundle):
    recording.write_bytes(recording.read_bytes() + b"changed")
    with pytest.raises(reviewer.ReviewerError, match="source_mismatch"):
        build(reviewer, recording, bundle)
    assert not (recording.parent / "review.html").exists()


def test_installed_template_falls_back_to_txt_mirror(reviewer, tmp_path, monkeypatch):
    monkeypatch.setattr(reviewer, "__file__", str(tmp_path / "build-crop-reviewer.py"))
    for name in ("crop-reviewer.js", "crop-reviewer-shell.html"):
        (tmp_path / (name + ".txt")).write_text("installed mirror", encoding="utf-8")
        assert reviewer._read_template(name) == "installed mirror"


def run_javascript(script):
    node = shutil.which("node")
    assert node, "install the project's Node runtime; decision tests may not be skipped"
    result = subprocess.run(
        [
            node,
            "-e",
            "const assert = require('node:assert/strict'); const review = require("
            + json.dumps(str(SCRIPTS / "crop-reviewer.js"))
            + ");\n"
            + script,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_reviewer_ui_event_contracts():
    node = shutil.which("node")
    assert node, "install Node to run the reviewer UI event tests"
    result = subprocess.run(
        [node, "--test", str(Path(__file__).with_name("test_crop_reviewer_ui.js"))],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_executable_decisions_require_explicit_approval_and_edit_invalidates():
    run_javascript("""
const talk = {id:'dQw4w9WgXcQ', mode:'crop', region:[.1,.2,.8,.9], command_prefix:'python extract.py'};
let entry = review.initial(talk);
assert.equal(review.commands([talk], {[talk.id]:entry}), '');
entry = review.approve(entry);
assert.match(review.commands([talk], {[talk.id]:entry}), /--region 0.1,0.2,0.8,0.9 --region-verified -- dQw4w9WgXcQ$/);
entry = review.edit(entry, [.2,.2,.8,.9]);
assert.equal(entry.verdict, null);
assert.equal(review.commands([talk], {[talk.id]:entry}), '');
entry = review.edit(review.approve(entry), [0,0,1,1], 'full-frame');
assert.equal(entry.verdict, null);
assert.match(review.commands([talk], {[talk.id]:review.approve(entry)}), /--region 0,0,1,1 --region-verified -- dQw4w9WgXcQ$/);
const no = {...talk, mode:'no-slides', region:[0,0,1,1]};
entry = review.initial(no);
assert.equal(review.commands([no], {[no.id]:entry}), '');
entry = review.approve(entry);
assert.match(review.commands([no], {[no.id]:entry}), /^# dQw4w9WgXcQ: owner confirmed no slides/);
assert(!review.commands([no], {[no.id]:entry}).includes('--region-verified'));
assert.equal(review.edit(entry, [.1,.2,.8,.9]).verdict, null);
assert.equal(review.initial(talk).verdict, null);
""")


def test_saved_approvals_are_isolated_and_malformed_state_fails_closed():
    run_javascript("""
const talk = {id:'dQw4w9WgXcQ', mode:'crop', region:[.1,.2,.8,.9]};
const batch = {id:'one',fingerprint:'a'.repeat(64)};
const entry = review.approve(review.initial(talk));
const saved = {schema_version:1,fingerprint:batch.fingerprint,entries:{[talk.id]:entry}};
assert.equal(review.restore([talk], batch, JSON.stringify(saved))[talk.id].verdict, 'approved');
assert.notEqual(review.key(batch), review.key({...batch,id:'two'}));
assert.notEqual(review.key(batch), review.key({...batch,fingerprint:'b'.repeat(64)}));
assert.throws(() => review.restore([talk], {...batch,fingerprint:'b'.repeat(64)}, JSON.stringify(saved)), SyntaxError);
for (const changed of [{...saved,schema_version:2}, {...saved,entries:{unknown:entry}}, {...saved,entries:{[talk.id]:{...entry,region:[0,0,2,1]}}}, {...saved,entries:{[talk.id]:{...entry,mode:'no-slides'}}}]) {
  assert.throws(() => review.restore([talk], batch, JSON.stringify(changed)), SyntaxError);
}
for (const region of [[0,0,NaN,1],[0,0,Infinity,1],[0,0,0,1],[0,0,1,1,1],[false,0,1,1]]) {
  assert.equal(review.validRegion(region), false);
  assert.throws(() => review.edit(entry, region), RangeError);
}
assert.equal(review.commands([talk], {[talk.id]:{...entry,region:[0,0,2,1]}}), '');
""")


@pytest.mark.parametrize(
    "args,code",
    [
        ([], 2),
        (["--help"], 0),
        (["--unknown"], 2),
        (["absent.tsv", "output.html", "--batch-id", "test"], 1),
    ],
)
def test_reviewer_cli_json_contract(args, code):
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "build-crop-reviewer.py"), *args],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == code
    assert isinstance(json.loads(result.stdout), dict)
    if code:
        assert result.stderr


def test_reviewer_boundary_redacts_unexpected_failure_and_keeps_interrupts(
    reviewer, monkeypatch, capsys
):
    def fail():
        raise RuntimeError("private details")

    monkeypatch.setattr(reviewer, "main", fail)
    assert reviewer.run_cli() == 1
    output = capsys.readouterr()
    assert json.loads(output.out)["code"] == "crop_reviewer_unexpected_failure"
    assert "private details" not in output.out + output.err

    def interrupt():
        raise KeyboardInterrupt

    monkeypatch.setattr(reviewer, "main", interrupt)
    with pytest.raises(KeyboardInterrupt):
        reviewer.run_cli()
