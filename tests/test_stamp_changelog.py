"""Tests for stamp-changelog.py — version computation and CHANGELOG stamping."""

import pytest


# ── compute_version: mirrors tesslio/patch-version-publish ──────────────


def test_compute_version_first_publish_uses_local(stamp_changelog):
    assert stamp_changelog.compute_version("0.1.0", None) == "0.1.0"


def test_compute_version_bumps_registry_patch(stamp_changelog):
    assert stamp_changelog.compute_version("0.18.7", "0.18.7") == "0.18.8"


def test_compute_version_bumps_registry_when_local_behind(stamp_changelog):
    # Local manifest stale vs registry — still bump the registry patch.
    assert stamp_changelog.compute_version("0.18.0", "0.18.7") == "0.18.8"


def test_compute_version_respects_manual_ahead_bump(stamp_changelog):
    # Local manifest deliberately ahead of registry — publish as-is.
    assert stamp_changelog.compute_version("0.19.0", "0.18.7") == "0.19.0"


def test_compute_version_rejects_malformed(stamp_changelog):
    with pytest.raises(ValueError):
        stamp_changelog.compute_version("0.18", "0.18.7")
    with pytest.raises(ValueError):
        stamp_changelog.compute_version("0.18.7", "vNext")


# ── stamp_changelog: insert heading above un-headed entries ─────────────


_UNHEADED = """\
# Changelog

### feat(x) — new thing

Body of x.

### fix(y) — a bug

## 0.18.7 — 2026-06-03

### feat(prior) — already released
"""


def test_stamp_inserts_heading_above_unheaded_entries(stamp_changelog):
    out, changed = stamp_changelog.stamp_changelog(_UNHEADED, "0.18.8", "2026-06-04")
    assert changed is True
    lines = out.splitlines()
    # Heading inserted directly above the first un-headed entry…
    h_idx = lines.index("## 0.18.8 — 2026-06-04")
    assert lines[h_idx + 2] == "### feat(x) — new thing"
    # …and above the prior released section, which is left intact.
    assert lines.index("## 0.18.8 — 2026-06-04") < lines.index("## 0.18.7 — 2026-06-03")
    assert "### feat(prior) — already released" in out


def test_stamp_is_noop_when_top_already_headed(stamp_changelog):
    already = (
        "# Changelog\n\n## 0.18.7 — 2026-06-03\n\n### feat(x) — released\n"
    )
    out, changed = stamp_changelog.stamp_changelog(already, "0.18.8", "2026-06-04")
    assert changed is False
    assert out == already


def test_stamp_is_noop_when_no_entries(stamp_changelog):
    empty = "# Changelog\n"
    out, changed = stamp_changelog.stamp_changelog(empty, "0.18.8", "2026-06-04")
    assert changed is False
    assert out == empty


def test_stamp_preserves_trailing_newline(stamp_changelog):
    out, changed = stamp_changelog.stamp_changelog(_UNHEADED, "0.18.8", "2026-06-04")
    assert changed is True
    assert out.endswith("\n")


def test_stamp_idempotent(stamp_changelog):
    once, _ = stamp_changelog.stamp_changelog(_UNHEADED, "0.18.8", "2026-06-04")
    twice, changed = stamp_changelog.stamp_changelog(once, "0.18.9", "2026-06-05")
    # Second run sees the heading already on top — no double stamp.
    assert changed is False
    assert twice == once
