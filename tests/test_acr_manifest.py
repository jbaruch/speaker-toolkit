"""The ACR and Tessl manifests describe one package at one version.

Both channels publish the explicit version from these files, so a PR that
bumps or adds to one of them and not the other would split the channels.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _manifests() -> tuple[dict, dict]:
    tessl = json.loads(
        (ROOT / ".tessl-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    acr = yaml.safe_load((ROOT / "agent-plugin.yaml").read_text(encoding="utf-8"))
    return tessl, acr


def test_both_manifests_carry_the_same_name_and_version():
    tessl, acr = _manifests()
    assert acr["name"] == tessl["name"]
    assert acr["version"] == tessl["version"]


def test_both_manifests_ship_the_same_skills_and_rules():
    tessl, acr = _manifests()
    artifacts = acr["artifacts"]
    assert sorted(entry["path"] for entry in artifacts["skills"]) == sorted(
        tessl["skills"]
    )
    assert sorted(entry["path"] for entry in artifacts["rules"]) == sorted(
        tessl["rules"]
    )
