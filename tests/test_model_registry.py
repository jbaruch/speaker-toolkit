"""Tests for model_registry.py — alias resolution, shortlist ranking, freshness."""

from datetime import date


# --- Registry shape ---

def test_registry_entries_well_formed(model_registry):
    required = {"id", "display", "family", "aliases", "cost", "speed", "quality", "edit"}
    for m in model_registry.MODEL_REGISTRY:
        assert required <= set(m), f"{m.get('id')} missing keys"
        assert m["family"] in {"gemini", "imagen", "openai"}
        assert m["cost"] in {"low", "medium", "high"}
        assert m["speed"] in {"fast", "medium", "slow"}
        assert m["quality"] in {"medium", "high"}
        assert m["edit"] in {"strong", "none"}


def test_compare_models_derived_from_registry(model_registry):
    assert model_registry.COMPARE_MODELS == [m["id"] for m in model_registry.MODEL_REGISTRY]


def test_registry_ids_unique(model_registry):
    ids = [m["id"] for m in model_registry.MODEL_REGISTRY]
    assert len(ids) == len(set(ids))


def test_imagen_has_no_edit_support(model_registry):
    # Build-editability filter depends on this: Imagen has no edit endpoint.
    imagen = next(m for m in model_registry.MODEL_REGISTRY if m["family"] == "imagen")
    assert imagen["edit"] == "none"


# --- Alias resolution (the nano-banana fix) ---

def test_resolve_nano_banana_pro_alias(model_registry):
    assert model_registry.resolve_model_id("nano-banana-pro-preview") == "gemini-3-pro-image-preview"
    assert model_registry.resolve_model_id("nano-banana-pro") == "gemini-3-pro-image-preview"
    assert model_registry.resolve_model_id("gemini-3-pro-image") == "gemini-3-pro-image-preview"


def test_resolve_is_case_insensitive(model_registry):
    assert model_registry.resolve_model_id("Nano-Banana-Pro") == "gemini-3-pro-image-preview"
    assert model_registry.resolve_model_id("  GPT-IMAGE-2  ") == "gpt-image-2"


def test_resolve_canonical_id_unchanged(model_registry):
    assert model_registry.resolve_model_id("gpt-image-2") == "gpt-image-2"


def test_resolve_unknown_passthrough(model_registry):
    # Unknown / ad-hoc ids dispatch by family — returned unchanged.
    assert model_registry.resolve_model_id("imagen-9.9-future") == "imagen-9.9-future"


def test_resolve_empty(model_registry):
    assert model_registry.resolve_model_id("") == ""
    assert model_registry.resolve_model_id(None) is None


def test_model_attributes_via_alias(model_registry):
    attrs = model_registry.model_attributes("nano-banana-pro")
    assert attrs is not None
    assert attrs["id"] == "gemini-3-pro-image-preview"
    assert model_registry.model_attributes("totally-unknown") is None


# --- Shortlist ranking ---

def test_shortlist_build_editability_excludes_imagen(model_registry):
    ranked = model_registry.shortlist_models(["build-editability"])
    families = {m["family"] for m in ranked}
    assert "imagen" not in families
    # the three edit-capable models survive
    assert len(ranked) == 3


def test_shortlist_cost_ranks_cheapest_first(model_registry):
    ranked = model_registry.shortlist_models(["cost"])
    assert ranked[0]["cost"] == "low"
    assert ranked[-1]["cost"] == "high"


def test_shortlist_quality_then_editability(model_registry):
    # build-editability drops Imagen; quality ranks the rest, high before medium.
    ranked = model_registry.shortlist_models(["quality", "build-editability"])
    ids = [m["id"] for m in ranked]
    assert "imagen-4.0-ultra-generate-001" not in ids
    # medium-quality flash model ranks last among the survivors
    assert ranked[-1]["quality"] == "medium"


def test_shortlist_empty_returns_full_registry_in_order(model_registry):
    ranked = model_registry.shortlist_models([])
    assert [m["id"] for m in ranked] == model_registry.COMPARE_MODELS


def test_shortlist_unknown_priority_raises(model_registry):
    import pytest
    with pytest.raises(ValueError) as exc:
        model_registry.shortlist_models(["cost", "bogus"])
    assert "bogus" in str(exc.value)


def test_shortlist_does_not_mutate_registry(model_registry):
    before = [m["id"] for m in model_registry.MODEL_REGISTRY]
    model_registry.shortlist_models(["cost"])
    after = [m["id"] for m in model_registry.MODEL_REGISTRY]
    assert before == after


# --- Live injection (hybrid: cache + inject) ---

def test_shortlist_injects_web_discovered_model(model_registry):
    # A brand-new flagship not in the cache, injected with its attributes.
    breakthrough = {
        "id": "gemini-5-ultra-image", "family": "gemini",
        "cost": "low", "speed": "fast", "quality": "high", "edit": "strong",
    }
    ranked = model_registry.shortlist_models(
        ["quality", "cost"], extra_models=[breakthrough]
    )
    ids = [m["id"] for m in ranked]
    assert "gemini-5-ultra-image" in ids
    # high quality + low cost ranks it ahead of the cached high-cost model
    assert ids.index("gemini-5-ultra-image") < ids.index("gpt-image-2")


def test_shortlist_injected_model_respects_editability_filter(model_registry):
    # An injected model that can't edit is dropped under build-editability.
    no_edit = {
        "id": "fancy-but-no-edit", "family": "other",
        "cost": "low", "speed": "fast", "quality": "high", "edit": "none",
    }
    ranked = model_registry.shortlist_models(
        ["build-editability"], extra_models=[no_edit]
    )
    assert "fancy-but-no-edit" not in [m["id"] for m in ranked]


def test_shortlist_injected_model_without_id_raises(model_registry):
    import pytest
    with pytest.raises(ValueError) as exc:
        model_registry.shortlist_models(["cost"], extra_models=[{"family": "gemini"}])
    assert "id" in str(exc.value)


def test_shortlist_extra_none_is_noop(model_registry):
    assert model_registry.shortlist_models(["cost"], extra_models=None) == \
        model_registry.shortlist_models(["cost"])


# --- Freshness ---

def test_freshness_fresh_when_recent(model_registry):
    reviewed = date.fromisoformat(model_registry.REGISTRY_LAST_REVIEWED)
    result = model_registry.check_freshness(today=reviewed)
    assert result["age_days"] == 0
    assert result["stale"] is False
    assert result["last_reviewed"] == model_registry.REGISTRY_LAST_REVIEWED


def test_freshness_stale_past_max_age(model_registry):
    reviewed = date.fromisoformat(model_registry.REGISTRY_LAST_REVIEWED)
    past_cutoff = date.fromordinal(
        reviewed.toordinal() + model_registry.REGISTRY_FRESHNESS_MAX_AGE_DAYS + 1
    )
    result = model_registry.check_freshness(today=past_cutoff)
    assert result["stale"] is True
    assert result["age_days"] == model_registry.REGISTRY_FRESHNESS_MAX_AGE_DAYS + 1


def test_freshness_boundary_not_stale_at_exactly_max_age(model_registry):
    reviewed = date.fromisoformat(model_registry.REGISTRY_LAST_REVIEWED)
    at_cutoff = date.fromordinal(
        reviewed.toordinal() + model_registry.REGISTRY_FRESHNESS_MAX_AGE_DAYS
    )
    result = model_registry.check_freshness(today=at_cutoff)
    assert result["stale"] is False


def test_freshness_includes_full_roster(model_registry):
    result = model_registry.check_freshness()
    assert [m["id"] for m in result["models"]] == model_registry.COMPARE_MODELS
