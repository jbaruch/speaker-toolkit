"""Tests for batch-download-videos.sh — resolution, outcome reporting, and exit codes."""

import os
import stat
import subprocess

SCRIPT = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        os.pardir,
        "skills",
        "vault-ingress",
        "scripts",
        "batch-download-videos.sh",
    )
)

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
        ["bash", SCRIPT, str(vault), *ids],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def _outcomes(stdout):
    return {
        line.split("\t")[1]: line.split("\t")
        for line in stdout.splitlines()
        if line.strip()
    }


def test_downloads_to_correct_path(tmp_path):
    """Output file lands at <vault>/slides-rebuild/<id>/<id>.mp4 and reports OK."""
    vault = tmp_path / "vault"
    vault.mkdir()
    result = _run(vault, ["xyz789"], ytdlp=_fake_ytdlp(tmp_path, FAKE_OK))

    assert result.returncode == 0, result.stderr
    assert (
        vault / "slides-rebuild" / "xyz789" / "xyz789.mp4"
    ).read_text() == "video-bytes"
    assert _outcomes(result.stdout)["xyz789"][0] == "OK"


def test_creates_directory_structure(tmp_path):
    """Script creates <vault>/slides-rebuild/<id>/ directories for every id."""
    vault = tmp_path / "vault"
    vault.mkdir()
    result = _run(vault, ["abc123", "def456"], ytdlp=_fake_ytdlp(tmp_path, FAKE_OK))

    assert result.returncode == 0, result.stderr
    assert (vault / "slides-rebuild" / "abc123").is_dir()
    assert (vault / "slides-rebuild" / "def456").is_dir()


def test_reports_one_outcome_line_per_id(tmp_path):
    """Every id gets exactly one outcome line, whatever happened to it."""
    vault = tmp_path / "vault"
    vault.mkdir()
    ids = ["one", "two", "three", "four"]
    result = _run(vault, ids, ytdlp=_fake_ytdlp(tmp_path, FAKE_OK))

    assert sorted(_outcomes(result.stdout)) == sorted(ids)


def test_failed_download_is_reported_and_fails_the_run(tmp_path):
    """A 403 surfaces as FAIL with the yt-dlp reason, and the script exits 1."""
    vault = tmp_path / "vault"
    vault.mkdir()
    result = _run(vault, ["blocked"], ytdlp=_fake_ytdlp(tmp_path, FAKE_403, "403"))

    assert result.returncode == 1
    outcome = _outcomes(result.stdout)["blocked"]
    assert outcome[0] == "FAIL"
    assert "403" in outcome[2]
    assert "blocked" in result.stderr


def test_zero_exit_with_no_output_file_is_a_failure(tmp_path):
    """yt-dlp exiting zero having produced nothing is FAIL, not OK."""
    vault = tmp_path / "vault"
    vault.mkdir()
    result = _run(
        vault, ["merged-away"], ytdlp=_fake_ytdlp(tmp_path, FAKE_EMPTY_SUCCESS, "empty")
    )

    assert result.returncode == 1
    assert _outcomes(result.stdout)["merged-away"][0] == "FAIL"


def test_one_failure_does_not_stop_the_others(tmp_path):
    """A failing id is reported without aborting the ids beside it."""
    vault = tmp_path / "vault"
    vault.mkdir()
    good = vault / "slides-rebuild" / "already"
    good.mkdir(parents=True)
    (good / "already.mp4").write_text("prior-bytes")

    result = _run(
        vault, ["already", "blocked"], ytdlp=_fake_ytdlp(tmp_path, FAKE_403, "403")
    )

    assert result.returncode == 1
    outcomes = _outcomes(result.stdout)
    assert outcomes["already"][0] == "SKIP"
    assert outcomes["blocked"][0] == "FAIL"


def test_existing_video_is_skipped_not_redownloaded(tmp_path):
    """A non-empty video already on disk is left alone."""
    vault = tmp_path / "vault"
    target_dir = vault / "slides-rebuild" / "present"
    target_dir.mkdir(parents=True)
    target = target_dir / "present.mp4"
    target.write_text("prior-bytes")

    result = _run(vault, ["present"], ytdlp=_fake_ytdlp(tmp_path, FAKE_OK))

    assert result.returncode == 0, result.stderr
    assert target.read_text() == "prior-bytes"
    assert _outcomes(result.stdout)["present"][0] == "SKIP"


def test_empty_existing_file_is_redownloaded(tmp_path):
    """A zero-byte leftover is not evidence of a download."""
    vault = tmp_path / "vault"
    target_dir = vault / "slides-rebuild" / "stub"
    target_dir.mkdir(parents=True)
    (target_dir / "stub.mp4").write_text("")

    result = _run(vault, ["stub"], ytdlp=_fake_ytdlp(tmp_path, FAKE_OK))

    assert result.returncode == 0, result.stderr
    assert (target_dir / "stub.mp4").read_text() == "video-bytes"
    assert _outcomes(result.stdout)["stub"][0] == "OK"


def test_yt_dlp_override_is_used_over_path(tmp_path):
    """YT_DLP wins over a yt-dlp sitting on PATH."""
    vault = tmp_path / "vault"
    vault.mkdir()
    pinned = _fake_ytdlp(tmp_path, FAKE_OK, "pinned")
    stale = _fake_ytdlp(tmp_path, FAKE_403, "stale")

    result = _run(vault, ["ok-id"], ytdlp=pinned, path_dir=stale.parent)

    assert result.returncode == 0, result.stderr
    assert str(pinned) in result.stderr
    assert _outcomes(result.stdout)["ok-id"][0] == "OK"


def test_reports_the_resolved_binary_and_version(tmp_path):
    """The resolved path and version are announced, so a stale binary is visible."""
    vault = tmp_path / "vault"
    vault.mkdir()
    pinned = _fake_ytdlp(tmp_path, FAKE_OK)

    result = _run(vault, ["ok-id"], ytdlp=pinned)

    assert f"yt-dlp: {pinned} (9999.12.31)" in result.stderr


def test_unusable_override_fails_before_downloading(tmp_path):
    """A YT_DLP that is not executable is a usage error, not a silent PATH fallback."""
    vault = tmp_path / "vault"
    vault.mkdir()
    result = _run(vault, ["any-id"], ytdlp=tmp_path / "nonexistent")

    assert result.returncode == 2
    assert "YT_DLP" in result.stderr
    assert not (vault / "slides-rebuild").exists()


def test_missing_ids_is_a_usage_error(tmp_path):
    """A vault root with no ids exits 2 with usage."""
    vault = tmp_path / "vault"
    vault.mkdir()
    result = _run(vault, [], ytdlp=_fake_ytdlp(tmp_path, FAKE_OK))

    assert result.returncode == 2
    assert "usage:" in result.stderr
