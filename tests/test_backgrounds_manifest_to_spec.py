"""Tests for backgrounds-manifest-to-spec.py — manifest JSON to ApplyBackgrounds spec."""

import pytest


def test_spec_sorted_by_slide_number(backgrounds_manifest_to_spec):
    manifest = {"backgrounds": {"10": "/a/slide-10.jpg", "2": "/a/slide-02.jpg"}}
    spec = backgrounds_manifest_to_spec.manifest_to_spec(manifest)
    # Numeric (not lexical) sort: 2 before 10.
    assert spec == "2=/a/slide-02.jpg;10=/a/slide-10.jpg"


def test_spec_single_entry(backgrounds_manifest_to_spec):
    manifest = {"backgrounds": {"3": "/img/slide-03.png"}}
    assert backgrounds_manifest_to_spec.manifest_to_spec(manifest) == "3=/img/slide-03.png"


def test_empty_manifest_raises(backgrounds_manifest_to_spec):
    with pytest.raises(ValueError):
        backgrounds_manifest_to_spec.manifest_to_spec({"backgrounds": {}})
    with pytest.raises(ValueError):
        backgrounds_manifest_to_spec.manifest_to_spec({})


def test_reserved_delimiter_in_path_raises(backgrounds_manifest_to_spec):
    # A ';' or '=' in a path would corrupt the spec the VBA macro parses.
    with pytest.raises(ValueError):
        backgrounds_manifest_to_spec.manifest_to_spec({"backgrounds": {"1": "/a/b;c.jpg"}})
    with pytest.raises(ValueError):
        backgrounds_manifest_to_spec.manifest_to_spec({"backgrounds": {"1": "/a/b=c.jpg"}})
