"""CI cache identity and renewal contracts; runner execution proves the runtime."""

from fnmatch import fnmatchcase
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(
    ("name", "paths", "key"),
    [
        (
            "Cache apt package downloads and package indices",
            ["/tmp/apt-cache", "/tmp/apt-lists"],
            "apt-${{ runner.os }}-${{ steps.apt-cache-key.outputs.codename }}-"
            "${{ steps.apt-cache-key.outputs.packages }}-"
            "${{ steps.apt-cache-key.outputs.week }}",
        ),
        (
            "Cache the markdown deck renderers",
            [
                "${{ github.workspace }}/deck-renderers",
                "~/.cache/ms-playwright",
                "~/.cache/puppeteer",
            ],
            "deck-renderers-${{ runner.os }}-"
            "${{ steps.deck-renderers.outputs.digest }}",
        ),
    ],
)
def test_cache_runtime_renewal_preserves_cache_identity(name, paths, key):
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8")
    )
    matches = [
        step for step in workflow["jobs"]["test"]["steps"] if step.get("name") == name
    ]
    assert len(matches) == 1
    step = matches[0]
    assert step["uses"].startswith("actions/cache@")
    assert set(step) == {"name", "uses", "with"}
    assert set(step["with"]) == {"path", "key"}
    assert step["with"]["path"].splitlines() == paths
    assert step["with"]["key"] == key


def test_dependabot_can_renew_the_cache_action():
    config = yaml.safe_load(
        (ROOT / ".github/dependabot.yml").read_text(encoding="utf-8")
    )
    updates = [
        update
        for update in config["updates"]
        if update["package-ecosystem"] == "github-actions"
        and update["directory"] == "/"
    ]
    assert len(updates) == 1
    assert updates[0]["schedule"]["interval"] == "weekly"
    assert not any(
        fnmatchcase("actions/cache", ignored["dependency-name"])
        for ignored in updates[0].get("ignore", [])
    )
