"""Tests for batch-download-videos.py — resolution, outcome reporting, and exit codes."""

import importlib.util
import json
import os
import shutil
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

# Copies a locally generated complete recording to the requested output path.
FAKE_OK = """\
#!/usr/bin/env bash
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version) echo "9999.12.31"; exit 0 ;;
        -o) shift; cp "$FAKE_VIDEO_SOURCE" "$1" ;;
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

# Present and executable, but cannot answer --version — and leaks while failing.
FAKE_NO_VERSION = """\
#!/usr/bin/env bash
echo "yt-dlp: error: unrecognized arguments token=VERSIONSECRET" >&2
exit 2
"""

# Reports the output path as already downloaded, as yt-dlp does for a non-empty
# target, without writing anything itself.
FAKE_ALREADY_DOWNLOADED = """\
#!/usr/bin/env bash
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version) echo "9999.12.31"; exit 0 ;;
        *) ;;
    esac
    shift
done
echo "[download] Destination already exists; skipping"
exit 0
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


def _video_fixture(path):
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "install ffmpeg; download integrity tests must not skip decoding"
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-nostdin",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:size=64x48:rate=10",
            "-t",
            "1",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    return path.read_bytes()


def _run(vault, ids, ytdlp=None, path_dir=None):
    env = os.environ.copy()
    source = vault.parent / "fixture-video.mp4"
    if not source.exists():
        _video_fixture(source)
    env["FAKE_VIDEO_SOURCE"] = str(source)
    env.pop("VIRTUAL_ENV", None)
    if ytdlp is not None:
        env["YT_DLP"] = str(ytdlp)
    else:
        env.pop("YT_DLP", None)
    if path_dir is not None:
        env["PATH"] = f"{path_dir}:{env['PATH']}"
    return subprocess.run(
        [sys.executable, SCRIPT, str(vault), *ids],
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
    assert target.read_bytes() == (tmp_path / "fixture-video.mp4").read_bytes()
    entry = _by_id(result)[OK_ID]
    assert entry["outcome"] == "ok"
    assert entry["path"] == str(target)
    assert entry["bytes"] == target.stat().st_size
    assert entry["integrity"]["ok"] is True
    assert (
        entry["integrity"]["source_generation"]
        == downloader.FileGeneration.from_stat(target.stat()).to_dict()
    )


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
    _video_fixture(present / f"{PRESENT_ID}.mp4")

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
    before = _video_fixture(target)

    result = _run(vault, [PRESENT_ID], ytdlp=_fake_ytdlp(tmp_path, FAKE_OK))

    assert result.returncode == 0, result.stderr
    assert target.read_bytes() == before
    assert _by_id(result)[PRESENT_ID]["outcome"] == "skip"


def test_nonempty_corrupt_existing_video_never_counts_as_verified(tmp_path):
    vault = tmp_path / "vault"
    target = vault / "slides-rebuild" / PRESENT_ID / f"{PRESENT_ID}.mp4"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"damaged prior recording")
    result = _run(vault, [PRESENT_ID], ytdlp=_fake_ytdlp(tmp_path, FAKE_OK))
    assert result.returncode == 1
    entry = _by_id(result)[PRESENT_ID]
    assert entry["outcome"] == "fail"
    assert "reason_code" in entry
    assert "move the damaged file aside" in entry["reason"]
    assert target.read_bytes() == b"damaged prior recording"


def test_zero_exit_with_corrupt_file_is_not_promoted(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    corrupt = FAKE_OK.replace('cp "$FAKE_VIDEO_SOURCE" "$1"', 'printf damaged > "$1"')
    result = _run(vault, [OK_ID], ytdlp=_fake_ytdlp(tmp_path, corrupt))
    assert result.returncode == 1
    entry = _by_id(result)[OK_ID]
    assert entry["outcome"] == "fail"
    assert entry["exit_code"] == 0
    assert "integrity verification" in entry["reason"]
    assert not (vault / "slides-rebuild" / OK_ID / f"{OK_ID}.mp4").exists()
    staging = vault / "slides-rebuild" / OK_ID / f"{OK_ID}.incomplete.mp4"
    assert staging.read_bytes() == b"damaged"
    retried = _run(vault, [OK_ID], ytdlp=_fake_ytdlp(tmp_path, FAKE_OK))
    assert _by_id(retried)[OK_ID]["outcome"] == "ok"


def test_decode_failure_cannot_promote_a_nonempty_download(tmp_path, monkeypatch):
    def reject(_path):
        raise downloader.VideoIntegrityError("integrity_decode_failed")

    monkeypatch.setattr(downloader, "_verify_download", reject)
    source = tmp_path / "source.mp4"
    _video_fixture(source)
    monkeypatch.setenv("FAKE_VIDEO_SOURCE", str(source))
    result = downloader.download_one(_fake_ytdlp(tmp_path, FAKE_OK), tmp_path, OK_ID)
    assert result["outcome"] == "fail"
    assert result["reason_code"] == "integrity_decode_failed"
    assert not (tmp_path / "slides-rebuild" / OK_ID / f"{OK_ID}.mp4").exists()


def test_changed_promoted_object_cannot_reuse_verified_receipt(tmp_path):
    source = tmp_path / "source.mp4"
    _video_fixture(source)
    receipt = downloader._verify_download(source)
    source.write_bytes(source.read_bytes() + b"changed")
    with pytest.raises(downloader.VideoIntegrityError, match="source_changed"):
        downloader._bind_promoted_integrity(source, receipt)


def test_same_size_change_with_restored_mtime_cannot_hide_as_rename(tmp_path):
    source = tmp_path / "source.mp4"
    _video_fixture(source)
    receipt = downloader._verify_download(source)
    before = source.stat()
    data = bytearray(source.read_bytes())
    data[-1] ^= 1
    source.write_bytes(data)
    os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
    with pytest.raises(downloader.VideoIntegrityError):
        downloader._bind_promoted_integrity(source, receipt)


def test_empty_existing_file_is_redownloaded(tmp_path):
    """A zero-byte leftover is not evidence of a download."""
    vault = tmp_path / "vault"
    target_dir = vault / "slides-rebuild" / STUB_ID
    target_dir.mkdir(parents=True)
    (target_dir / f"{STUB_ID}.mp4").write_text("")

    result = _run(vault, [STUB_ID], ytdlp=_fake_ytdlp(tmp_path, FAKE_OK))

    assert result.returncode == 0, result.stderr
    assert (target_dir / f"{STUB_ID}.mp4").read_bytes() == (
        tmp_path / "fixture-video.mp4"
    ).read_bytes()
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
    assert target.read_bytes() == (tmp_path / "fixture-video.mp4").read_bytes()


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


def test_the_version_probe_redacts_what_the_binary_prints(tmp_path):
    """A configured executable's own diagnostics cross the boundary redacted."""
    vault = tmp_path / "vault"
    vault.mkdir()
    result = _run(vault, [OK_ID], ytdlp=_fake_ytdlp(tmp_path, FAKE_NO_VERSION, "mute"))

    assert result.returncode == 2
    assert "VERSIONSECRET" not in result.stdout
    assert "VERSIONSECRET" not in result.stderr


def test_a_stale_staging_file_is_removed_before_yt_dlp_runs(tmp_path):
    """yt-dlp must never see a leftover partial and call it already downloaded."""
    vault = tmp_path / "vault"
    staging = vault / "slides-rebuild" / OK_ID / f"{OK_ID}.incomplete.mp4"
    staging.parent.mkdir(parents=True)
    staging.write_text("stale-partial-bytes")

    result = _run(
        vault, [OK_ID], ytdlp=_fake_ytdlp(tmp_path, FAKE_ALREADY_DOWNLOADED, "already")
    )
    target = staging.parent / f"{OK_ID}.mp4"

    assert result.returncode == 1
    assert _by_id(result)[OK_ID]["outcome"] == "fail"
    assert not target.exists()


def test_an_unremovable_stale_partial_fails_rather_than_promoting_it(tmp_path):
    """When the leftover cannot be cleared, the id fails instead of risking it."""
    vault = tmp_path / "vault"
    holder = vault / "slides-rebuild" / OK_ID
    holder.mkdir(parents=True)
    (holder / f"{OK_ID}.incomplete.mp4").write_text("stale-partial-bytes")
    holder.chmod(0o500)
    try:
        result = _run(
            vault,
            [OK_ID],
            ytdlp=_fake_ytdlp(tmp_path, FAKE_ALREADY_DOWNLOADED, "already"),
        )
        entry = _by_id(result)[OK_ID]
    finally:
        holder.chmod(0o700)

    assert result.returncode == 1
    assert entry["outcome"] == "fail"
    assert "could not be removed" in entry["reason"]
    assert not (holder / f"{OK_ID}.mp4").exists()


def test_a_log_that_cannot_be_written_is_reported_not_swallowed(tmp_path):
    """The download still stands, but losing its record is said out loud."""
    vault = tmp_path / "vault"
    target_dir = vault / "slides-rebuild" / OK_ID
    target_dir.mkdir(parents=True)
    # A directory where the log file belongs: the video writes, the log cannot.
    (target_dir / f"{OK_ID}.yt-dlp.log").mkdir()

    result = _run(vault, [OK_ID], ytdlp=_fake_ytdlp(tmp_path, FAKE_OK))
    entry = _by_id(result)[OK_ID]

    assert result.returncode == 0, result.stderr
    assert entry["outcome"] == "ok"
    assert entry["log"] is None
    assert "could not be written" in entry["log_error"]
    assert OK_ID in result.stderr
    assert "could not be written" in result.stderr
