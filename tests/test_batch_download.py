"""Tests for batch-download-videos.py — resolution, outcome reporting, and exit codes."""

import importlib.util
import json
import os
import stat
import subprocess
import sys

import pytest

SCRIPT = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        os.pardir,
        "skills",
        "vault-ingress",
        "scripts",
        "batch-download-videos.py",
    )
)

# Ids must match the shared ingress grammar, so the fixtures are real-shaped.
OK_ID = "AbCdEfGhIj1"
OTHER_ID = "KlMnOpQrSt2"
BLOCKED_ID = "UvWxYzAbCd3"
PRESENT_ID = "EfGhIjKlMn4"
STUB_ID = "OpQrStUvWx5"
DASH_ID = "-YzAbCdEfG6"

# Writes a non-empty file at the -o path, so the script sees a usable download.
FAKE_OK = """\
#!/usr/bin/env bash
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version) echo "9999.12.31"; exit 0 ;;
        -o) shift; printf 'video-bytes' > "$1" ;;
        *) ;;
    esac
    shift
done
"""

# Exits non-zero after an ERROR line, like a 403 from a stale binary.
FAKE_403 = """\
#!/usr/bin/env bash
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version) echo "9999.12.31"; exit 0 ;;
        *) ;;
    esac
    shift
done
echo "ERROR: unable to download video data: HTTP Error 403: Forbidden" >&2
exit 1
"""

# Exits zero having produced nothing — the failed-merge shape.
FAKE_EMPTY_SUCCESS = """\
#!/usr/bin/env bash
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version) echo "9999.12.31"; exit 0 ;;
        *) ;;
    esac
    shift
done
exit 0
"""

# Writes a partial file, then fails — the truncated-merge shape.
FAKE_PARTIAL_THEN_FAIL = """\
#!/usr/bin/env bash
out=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version) echo "9999.12.31"; exit 0 ;;
        -o) shift; out="$1"; printf 'trunc' > "$1" ;;
        *) ;;
    esac
    shift
done
echo "ERROR: Postprocessing: ffmpeg exited with code 1" >&2
exit 1
"""

# Fails quoting the signed media URL it was handed, as yt-dlp does on a 403.
FAKE_SIGNED_URL_ERROR = """\
#!/usr/bin/env bash
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version) echo "9999.12.31"; exit 0 ;;
        *) ;;
    esac
    shift
done
echo "ERROR: unable to download https://rr3.googlevideo.com/videoplayback?expire=1&signature=DEADBEEFCAFE&ip=1.2.3.4: HTTP Error 403: Forbidden" >&2
echo "token=SUPERSECRETVALUE" >&2
echo "Authorization: Bearer SPACED SECRET VALUE" >&2
echo "Cookie: sid=COOKIESECRET; theme=dark" >&2
exit 1
"""

# Present and executable, but cannot answer --version.
FAKE_NO_VERSION = """\
#!/usr/bin/env bash
echo "yt-dlp: error: unrecognized arguments" >&2
exit 2
"""


def _load_downloader():
    """Import the script as a module, so the failure boundary is unit-testable."""
    if "batch_download_videos" in sys.modules:
        return sys.modules["batch_download_videos"]
    script_dir = os.path.dirname(SCRIPT)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    spec = importlib.util.spec_from_file_location("batch_download_videos", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["batch_download_videos"] = module
    spec.loader.exec_module(module)
    return module


downloader = _load_downloader()


def _fake_ytdlp(tmp_path, body, name="yt-dlp"):
    bin_dir = tmp_path / f"bin-{name}"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "yt-dlp"
    fake.write_text(body)
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    return fake


def _run(vault, ids, ytdlp=None, path_dir=None):
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    if ytdlp is not None:
        env["YT_DLP"] = str(ytdlp)
    else:
        env.pop("YT_DLP", None)
    if path_dir is not None:
        env["PATH"] = f"{path_dir}:{env['PATH']}"
    return subprocess.run(
        [SCRIPT, str(vault), *ids],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def _report(result):
    return json.loads(result.stdout)


def _by_id(result):
    return {entry["youtube_id"]: entry for entry in _report(result)["results"]}


def test_downloads_to_correct_path(tmp_path):
    """Output file lands at <vault>/slides-rebuild/<id>/<id>.mp4 and reports ok."""
    vault = tmp_path / "vault"
    vault.mkdir()
    result = _run(vault, [OK_ID], ytdlp=_fake_ytdlp(tmp_path, FAKE_OK))

    assert result.returncode == 0, result.stderr
    target = vault / "slides-rebuild" / OK_ID / f"{OK_ID}.mp4"
    assert target.read_text() == "video-bytes"
    entry = _by_id(result)[OK_ID]
    assert entry["outcome"] == "ok"
    assert entry["path"] == str(target)
    assert entry["bytes"] == len("video-bytes")


def test_creates_directory_structure(tmp_path):
    """Script creates <vault>/slides-rebuild/<id>/ directories for every id."""
    vault = tmp_path / "vault"
    vault.mkdir()
    result = _run(vault, [OK_ID, OTHER_ID], ytdlp=_fake_ytdlp(tmp_path, FAKE_OK))

    assert result.returncode == 0, result.stderr
    assert (vault / "slides-rebuild" / OK_ID).is_dir()
    assert (vault / "slides-rebuild" / OTHER_ID).is_dir()


def test_report_holds_one_entry_per_id_in_order(tmp_path):
    """Every id gets exactly one result entry, in the order it was given."""
    vault = tmp_path / "vault"
    vault.mkdir()
    ids = [OK_ID, OTHER_ID, PRESENT_ID, STUB_ID]
    result = _run(vault, ids, ytdlp=_fake_ytdlp(tmp_path, FAKE_OK))

    report = _report(result)
    assert [entry["youtube_id"] for entry in report["results"]] == ids
    assert report["counts"] == {"ok": 4, "skip": 0, "fail": 0}
    assert report["ok"] is True
    assert report["schema_version"] == 1


def test_failed_download_is_reported_and_fails_the_run(tmp_path):
    """A 403 surfaces as a fail entry with the yt-dlp reason, and the script exits 1."""
    vault = tmp_path / "vault"
    vault.mkdir()
    result = _run(vault, [BLOCKED_ID], ytdlp=_fake_ytdlp(tmp_path, FAKE_403, "403"))

    assert result.returncode == 1
    entry = _by_id(result)[BLOCKED_ID]
    assert entry["outcome"] == "fail"
    assert entry["exit_code"] == 1
    assert "403" in entry["reason"]
    assert entry["log"].endswith(f"{BLOCKED_ID}.yt-dlp.log")
    assert _report(result)["ok"] is False
    assert BLOCKED_ID in result.stderr


def test_zero_exit_with_no_output_file_is_a_failure(tmp_path):
    """yt-dlp exiting zero having produced nothing is a failure, not a success."""
    vault = tmp_path / "vault"
    vault.mkdir()
    result = _run(
        vault, [OK_ID], ytdlp=_fake_ytdlp(tmp_path, FAKE_EMPTY_SUCCESS, "empty")
    )

    assert result.returncode == 1
    entry = _by_id(result)[OK_ID]
    assert entry["outcome"] == "fail"
    assert entry["exit_code"] == 0


def test_one_failure_does_not_stop_the_others(tmp_path):
    """A failing id is reported without aborting the ids beside it."""
    vault = tmp_path / "vault"
    present = vault / "slides-rebuild" / PRESENT_ID
    present.mkdir(parents=True)
    (present / f"{PRESENT_ID}.mp4").write_text("prior-bytes")

    result = _run(
        vault, [PRESENT_ID, BLOCKED_ID], ytdlp=_fake_ytdlp(tmp_path, FAKE_403, "403")
    )

    assert result.returncode == 1
    entries = _by_id(result)
    assert entries[PRESENT_ID]["outcome"] == "skip"
    assert entries[BLOCKED_ID]["outcome"] == "fail"
    assert _report(result)["counts"] == {"ok": 0, "skip": 1, "fail": 1}


def test_existing_video_is_skipped_not_redownloaded(tmp_path):
    """A non-empty video already on disk is left alone."""
    vault = tmp_path / "vault"
    target_dir = vault / "slides-rebuild" / PRESENT_ID
    target_dir.mkdir(parents=True)
    target = target_dir / f"{PRESENT_ID}.mp4"
    target.write_text("prior-bytes")

    result = _run(vault, [PRESENT_ID], ytdlp=_fake_ytdlp(tmp_path, FAKE_OK))

    assert result.returncode == 0, result.stderr
    assert target.read_text() == "prior-bytes"
    assert _by_id(result)[PRESENT_ID]["outcome"] == "skip"


def test_empty_existing_file_is_redownloaded(tmp_path):
    """A zero-byte leftover is not evidence of a download."""
    vault = tmp_path / "vault"
    target_dir = vault / "slides-rebuild" / STUB_ID
    target_dir.mkdir(parents=True)
    (target_dir / f"{STUB_ID}.mp4").write_text("")

    result = _run(vault, [STUB_ID], ytdlp=_fake_ytdlp(tmp_path, FAKE_OK))

    assert result.returncode == 0, result.stderr
    assert (target_dir / f"{STUB_ID}.mp4").read_text() == "video-bytes"
    assert _by_id(result)[STUB_ID]["outcome"] == "ok"


def test_yt_dlp_override_is_used_over_path(tmp_path):
    """YT_DLP wins over a yt-dlp sitting on PATH."""
    vault = tmp_path / "vault"
    vault.mkdir()
    pinned = _fake_ytdlp(tmp_path, FAKE_OK, "pinned")
    stale = _fake_ytdlp(tmp_path, FAKE_403, "stale")

    result = _run(vault, [OK_ID], ytdlp=pinned, path_dir=stale.parent)

    assert result.returncode == 0, result.stderr
    assert _report(result)["yt_dlp"]["path"] == str(pinned)
    assert _by_id(result)[OK_ID]["outcome"] == "ok"


def test_reports_the_resolved_binary_and_version(tmp_path):
    """The resolved path and version are announced, so a stale binary is visible."""
    vault = tmp_path / "vault"
    vault.mkdir()
    pinned = _fake_ytdlp(tmp_path, FAKE_OK)

    result = _run(vault, [OK_ID], ytdlp=pinned)

    assert _report(result)["yt_dlp"] == {"path": str(pinned), "version": "9999.12.31"}
    assert f"yt-dlp: {pinned} (9999.12.31)" in result.stderr


def test_unusable_override_fails_before_downloading(tmp_path):
    """A YT_DLP that is not executable is a usage error, not a silent PATH fallback."""
    vault = tmp_path / "vault"
    vault.mkdir()
    result = _run(vault, [OK_ID], ytdlp=tmp_path / "nonexistent")

    assert result.returncode == 2
    assert _report(result)["code"] == "ytdlp_override_invalid"
    assert "YT_DLP" in result.stderr
    assert not (vault / "slides-rebuild").exists()


def test_binary_that_cannot_report_a_version_is_rejected(tmp_path):
    """A non-zero --version is a resolution failure, not an unnamed version."""
    vault = tmp_path / "vault"
    vault.mkdir()
    result = _run(vault, [OK_ID], ytdlp=_fake_ytdlp(tmp_path, FAKE_NO_VERSION, "mute"))

    assert result.returncode == 2
    assert _report(result)["code"] == "ytdlp_version_unavailable"
    assert "did not report a version" in result.stderr
    assert not (vault / "slides-rebuild").exists()


def test_missing_ids_is_a_usage_error(tmp_path):
    """A vault root with no ids exits 2 with usage."""
    vault = tmp_path / "vault"
    vault.mkdir()
    result = _run(vault, [], ytdlp=_fake_ytdlp(tmp_path, FAKE_OK))

    assert result.returncode == 2
    assert _report(result)["code"] == "usage"
    assert "usage:" in result.stderr


def test_malformed_id_is_rejected_before_any_download(tmp_path):
    """An id outside the ingress grammar never becomes a directory or a URL."""
    vault = tmp_path / "vault"
    vault.mkdir()
    result = _run(vault, [OK_ID, "../escape"], ytdlp=_fake_ytdlp(tmp_path, FAKE_OK))

    assert result.returncode == 2
    assert _report(result)["code"] == "youtube_id_invalid"
    assert "../escape" in result.stderr
    assert not (vault / "slides-rebuild").exists()


def test_leading_dash_id_is_accepted_after_a_separator(tmp_path):
    """A YouTube id may begin with `-`, so `--` reaches it as an id."""
    vault = tmp_path / "vault"
    vault.mkdir()
    result = _run(vault, ["--", DASH_ID], ytdlp=_fake_ytdlp(tmp_path, FAKE_OK))

    assert result.returncode == 0, result.stderr
    assert _by_id(result)[DASH_ID]["outcome"] == "ok"


def test_every_exit_path_emits_a_json_report(tmp_path):
    """Success, download failure, and typed failure all produce a parseable report."""
    vault = tmp_path / "vault"
    vault.mkdir()
    runs = [
        _run(vault, [OK_ID], ytdlp=_fake_ytdlp(tmp_path, FAKE_OK)),
        _run(vault, [BLOCKED_ID], ytdlp=_fake_ytdlp(tmp_path, FAKE_403, "403")),
        _run(vault, [], ytdlp=_fake_ytdlp(tmp_path, FAKE_OK)),
    ]

    assert [run.returncode for run in runs] == [0, 1, 2]
    for run in runs:
        report = _report(run)
        assert report["schema_version"] == 1
        assert isinstance(report["ok"], bool)


def test_help_flag_yields_a_typed_failure_not_prose(tmp_path):
    """There is no prose help path: stdout is a JSON object on every exit."""
    vault = tmp_path / "vault"
    vault.mkdir()
    result = _run(vault, [], ytdlp=_fake_ytdlp(tmp_path, FAKE_OK))
    flagged = subprocess.run(
        [SCRIPT, "--help"], capture_output=True, text=True, timeout=30
    )

    assert _report(result)["code"] == "usage"
    assert flagged.returncode == 2
    assert json.loads(flagged.stdout)["code"] == "usage"


def test_nonzero_exit_with_a_partial_file_is_a_failure(tmp_path):
    """A truncated file plus a non-zero exit is a failure, not a usable download."""
    vault = tmp_path / "vault"
    vault.mkdir()
    result = _run(
        vault, [OK_ID], ytdlp=_fake_ytdlp(tmp_path, FAKE_PARTIAL_THEN_FAIL, "partial")
    )

    assert result.returncode == 1
    entry = _by_id(result)[OK_ID]
    assert entry["outcome"] == "fail"
    assert entry["exit_code"] == 1


def test_a_repeated_id_is_rejected_before_any_download(tmp_path):
    """Two workers must never write the same file, so a repeat is a usage error."""
    vault = tmp_path / "vault"
    vault.mkdir()
    result = _run(vault, [OK_ID, OTHER_ID, OK_ID], ytdlp=_fake_ytdlp(tmp_path, FAKE_OK))

    assert result.returncode == 2
    assert _report(result)["code"] == "youtube_id_duplicated"
    assert OK_ID in result.stderr
    assert not (vault / "slides-rebuild").exists()


def test_an_unexpected_failure_still_writes_a_json_report(
    tmp_path, capsys, monkeypatch
):
    """A crash inside the run reports typed JSON rather than a bare traceback."""

    def explode(*_args, **_kwargs):
        raise RuntimeError("the disk went away")

    monkeypatch.setattr(downloader, "execute", explode)

    code = downloader.run_cli([str(tmp_path), OK_ID])
    captured = capsys.readouterr()

    assert code == 3
    report = json.loads(captured.out)
    assert report["code"] == "unexpected_failure"
    assert report["ok"] is False
    assert "rerun once the cause is fixed" in report["error"]
    assert report["error_type"] == "RuntimeError"
    assert report["origin"]
    # `no-secrets`: the exception message never crosses the boundary.
    assert "the disk went away" not in captured.out
    assert "the disk went away" not in captured.err
    assert "Traceback" not in captured.err


def test_the_failure_boundary_lets_an_interrupt_through(tmp_path, monkeypatch):
    """KeyboardInterrupt stays killable rather than being reported as a failure."""

    def interrupt(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(downloader, "execute", interrupt)

    with pytest.raises(KeyboardInterrupt):
        downloader.run_cli([str(tmp_path), OK_ID])


def test_a_partial_download_never_lands_on_the_target_path(tmp_path):
    """The staged file is promoted only on success, so a retry cannot skip it."""
    vault = tmp_path / "vault"
    vault.mkdir()
    result = _run(
        vault, [OK_ID], ytdlp=_fake_ytdlp(tmp_path, FAKE_PARTIAL_THEN_FAIL, "partial")
    )
    target = vault / "slides-rebuild" / OK_ID / f"{OK_ID}.mp4"

    assert result.returncode == 1
    assert not target.exists()
    assert list(target.parent.glob("*.mp4")) == []

    retried = _run(vault, [OK_ID], ytdlp=_fake_ytdlp(tmp_path, FAKE_OK))
    assert _by_id(retried)[OK_ID]["outcome"] == "ok"
    assert target.read_text() == "video-bytes"


def test_a_signed_url_never_reaches_the_report_or_the_log(tmp_path):
    """yt-dlp quotes the signed media URL it was handed; the signature is redacted."""
    vault = tmp_path / "vault"
    vault.mkdir()
    result = _run(
        vault, [OK_ID], ytdlp=_fake_ytdlp(tmp_path, FAKE_SIGNED_URL_ERROR, "signed")
    )
    log = (vault / "slides-rebuild" / OK_ID / f"{OK_ID}.yt-dlp.log").read_text()
    reason = _by_id(result)[OK_ID]["reason"]

    secrets = (
        "DEADBEEFCAFE",
        "SUPERSECRETVALUE",
        "SPACED SECRET VALUE",
        "COOKIESECRET",
    )
    for secret in secrets:
        assert secret not in reason
        assert secret not in result.stdout
        assert secret not in result.stderr
        assert secret not in log
    # The diagnostic still says what happened and which URL it was.
    assert "403" in reason
    assert "rr3.googlevideo.com/videoplayback" in reason


def test_redaction_keeps_the_diagnostic_readable(tmp_path):
    """Redaction stops at a parameter delimiter, so what follows still reads."""
    line = (
        "ERROR: unable to download "
        "https://host/videoplayback?expire=1&signature=SECRET: HTTP Error 403"
    )

    cleaned = downloader.redact(line)

    assert "SECRET" not in cleaned
    assert "HTTP Error 403" in cleaned
    assert "https://host/videoplayback" in cleaned


def test_redaction_covers_a_header_value_containing_spaces(tmp_path):
    """A header value runs to end of line, so `\\S+` would leave the secret behind."""
    cleaned = downloader.redact("Authorization: Bearer TOKEN WITH SPACES")

    assert "TOKEN" not in cleaned
    assert "SPACES" not in cleaned
    assert cleaned.startswith("Authorization: <redacted>")
