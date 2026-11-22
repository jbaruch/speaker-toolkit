"""CI cache identity and renewal contracts; runner execution proves the runtime."""

from fnmatch import fnmatchcase
import json
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


def test_renovate_can_renew_actions_in_the_test_workflow():
    config = json.loads((ROOT / "renovate.json").read_text(encoding="utf-8"))
    assert "github-actions" in config["enabledManagers"]
    assert "schedule:weekly" in config["extends"]
    assert not any(
        fnmatchcase(".github/workflows/tests.yml", pattern)
        for pattern in config["ignorePaths"]
    )
