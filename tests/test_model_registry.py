"""Tests for model_registry.py — alias resolution, shortlist ranking, freshness."""

from datetime import date

import pytest


@pytest.mark.parametrize(
    "model,canonical,family",
    [
        ("GPT-IMAGE-2.5-FLARE", "gpt-image-2.5-flare-2026-09-08", "openai"),
        ("Nano-Banana-Pro", "gemini-3-pro-image", "gemini"),
        ("nano-banana-2.1", "gemini-nano-banana-2.1", "gemini"),
        ("gpt-image-2.6-flare", "gpt-image-2.6-flare", "openai"),
        # The roster carries no Imagen model, but the family still dispatches.
        ("imagen-9.9-future", "imagen-9.9-future", "imagen"),
        ("gpt-image-ad-hoc", "gpt-image-ad-hoc", "openai"),
    ],
)
def test_lane_resolver_uses_the_registry_alias_contract(
    model_registry, model, canonical, family
):
    result = model_registry.resolve_image_lane(model)
    assert (
        result.requested_model,
        result.served_model,
        result.family,
        result.lane,
    ) == (canonical, canonical, family, "api")


@pytest.mark.parametrize("model", [None, [], "", "unsupported-vendor-model"])
def test_lane_resolver_rejects_unknown_vendor_before_dispatch(model_registry, model):
    with pytest.raises(model_registry.ImageLaneError):
        model_registry.resolve_image_lane(model)


def test_registry_native_choice_never_claims_the_snapshot(model_registry):
    probe = model_registry.CliProbe(
        "ready", "/synthetic/bin/codex", "0.153.2", auth_mode="chatgpt"
    )
    result = model_registry.resolve_image_lane(
        "gpt-image-2.5-flare", probe, allow_native_model=True
    )
    assert result.lane == "cli"
    assert result.requested_model == "gpt-image-2.5-flare-2026-09-08"
    assert result.served_model == "codex-native-image-model-unpinned"


# --- Registry shape ---


def test_registry_entries_well_formed(model_registry):
    required = {
        "id",
        "display",
        "family",
        "aliases",
        "cost",
        "speed",
        "quality",
        "edit",
    }
    for m in model_registry.MODEL_REGISTRY:
        assert required <= set(m), f"{m.get('id')} missing keys"
        assert m["family"] in {"gemini", "imagen", "openai"}
        assert m["cost"] in {"low", "medium", "high"}
        assert m["speed"] in {"fast", "medium", "slow"}
        assert m["quality"] in {"medium", "high"}
        assert m["edit"] in {"precise", "stable", "strong", "none"}


def test_compare_models_derived_from_registry(model_registry):
    assert model_registry.COMPARE_MODELS == [
        m["id"] for m in model_registry.MODEL_REGISTRY
    ]


def test_registry_ids_unique(model_registry):
    ids = [m["id"] for m in model_registry.MODEL_REGISTRY]
    assert len(ids) == len(set(ids))


def test_shut_down_imagen_4_is_not_in_the_roster(model_registry):
    # Imagen 4 was shut down 2026-08-17. Nothing may rank or --compare it, and
    # its old alias no longer maps onto a roster entry.
    assert not any(m.startswith("imagen-4") for m in model_registry.COMPARE_MODELS)
    assert model_registry.model_attributes("imagen-4-ultra") is None


# --- Alias resolution (the nano-banana fix) ---


def test_resolve_nano_banana_pro_alias(model_registry):
    assert (
        model_registry.resolve_model_id("nano-banana-pro-preview")
        == "gemini-3-pro-image"
    )
    assert model_registry.resolve_model_id("nano-banana-pro") == "gemini-3-pro-image"


def test_resolve_deprecated_preview_id_to_ga(model_registry):
    # Google deprecates the "-preview" Gemini ids 2026-06-25; the Pro preview
    # stays a roster alias so a baked outline still resolves to the GA id.
    assert (
        model_registry.resolve_model_id("gemini-3-pro-image-preview")
        == "gemini-3-pro-image"
    )


def test_resolve_nano_banana_2_1_alias(model_registry):
    assert (
        model_registry.resolve_model_id("nano-banana-2.1") == "gemini-nano-banana-2.1"
    )


# Every superseded name and the id it stays pinned to. Retiring a model adds a
# row here as well as in LEGACY_MODEL_ALIASES.
LEGACY_CASES = [
    ("gpt-image-2", "gpt-image-2-2026-04-21"),
    ("gpt-image-2.5-flare", "gpt-image-2.5-flare-2026-09-08"),
    ("gpt-image-2.5-sunburst", "gpt-image-2.5-sunburst-2026-09-08"),
    ("nano-banana", "gemini-3.1-flash-image"),
    ("gemini-flash-image", "gemini-3.1-flash-image"),
    ("gemini-3.1-flash-image-preview", "gemini-3.1-flash-image"),
]


def test_legacy_cases_match_the_alias_table(model_registry):
    assert dict(LEGACY_CASES) == model_registry.LEGACY_MODEL_ALIASES


@pytest.mark.parametrize("legacy,pinned", LEGACY_CASES)
def test_superseded_names_resolve_to_their_pinned_ids(model_registry, legacy, pinned):
    # An outline baked against a superseded name must keep rendering on the id
    # it was pinned to — never drift to whatever the vendor serves for a rolling
    # name today, and never be remapped onto the successor. The superseded
    # model stays out of the roster so nothing ranks or --compares it.
    assert model_registry.resolve_model_id(legacy) == pinned
    assert model_registry.resolve_model_id(f"  {legacy.upper()}  ") == pinned
    assert model_registry.is_supported_model(legacy)
    assert model_registry.model_attributes(legacy) is None
    # An outline that baked the pinned id itself passes through unchanged and
    # still dispatches by family.
    assert model_registry.resolve_model_id(pinned) == pinned
    assert model_registry.is_supported_model(pinned)
    assert pinned not in model_registry.COMPARE_MODELS
    assert pinned not in [m["id"] for m in model_registry.shortlist_models([])]


def test_legacy_names_never_shadowed_by_the_roster(model_registry):
    # resolve_model_id() consults the roster before LEGACY_MODEL_ALIASES, so a
    # roster id or alias equal to a legacy name or pinned id would silently
    # remap baked outlines onto the successor.
    roster_names = {
        name.lower()
        for m in model_registry.MODEL_REGISTRY
        for name in [m["id"], *m["aliases"]]
    }
    legacy = model_registry.LEGACY_MODEL_ALIASES
    assert not roster_names & set(legacy)
    assert not roster_names & {pinned.lower() for pinned in legacy.values()}


def test_resolve_is_case_insensitive(model_registry):
    assert model_registry.resolve_model_id("Nano-Banana-Pro") == "gemini-3-pro-image"
    assert (
        model_registry.resolve_model_id("  GPT-IMAGE-2.6-FLARE  ")
        == "gpt-image-2.6-flare"
    )


def test_resolve_canonical_id_unchanged(model_registry):
    assert (
        model_registry.resolve_model_id("gpt-image-2.6-sunburst")
        == "gpt-image-2.6-sunburst"
    )


def test_resolve_unknown_passthrough(model_registry):
    # Unknown / ad-hoc ids dispatch by family — returned unchanged.
    assert model_registry.resolve_model_id("imagen-9.9-future") == "imagen-9.9-future"


def test_resolve_unknown_strips_whitespace(model_registry):
    # Stray whitespace on an unknown id must not survive — it would misclassify
    # the vendor family in model_family()'s prefix check.
    assert (
        model_registry.resolve_model_id("  imagen-9.9-future  ") == "imagen-9.9-future"
    )


def test_resolve_empty(model_registry):
    assert model_registry.resolve_model_id("") == ""
    assert model_registry.resolve_model_id(None) is None


def test_is_supported_model(model_registry):
    assert model_registry.is_supported_model("gpt-image-2.5-flare")
    assert model_registry.is_supported_model("imagen-4.0-ultra-generate-001")
    assert model_registry.is_supported_model("gemini-9-future-image")
    assert model_registry.is_supported_model("nano-banana-pro")  # alias resolves
    # An unknown vendor with no adapter is NOT supported (model_family would
    # otherwise misroute it to Gemini).
    assert not model_registry.is_supported_model("midjourney-v7")
    assert not model_registry.is_supported_model("")


def test_model_attributes_via_alias(model_registry):
    attrs = model_registry.model_attributes("nano-banana-pro")
    assert attrs is not None
    assert attrs["id"] == "gemini-3-pro-image"
    assert model_registry.model_attributes("totally-unknown") is None


# --- Shortlist ranking ---


def test_shortlist_build_editability_excludes_imagen(model_registry):
    # No Imagen model is cached any more, but the family still renders and has
    # no edit endpoint: an injected one must not reach a build shortlist.
    imagen = {
        "id": "imagen-9.9-future",
        "family": "imagen",
        "cost": "low",
        "speed": "fast",
        "quality": "high",
        "edit": "none",
    }
    ranked = model_registry.shortlist_models(
        ["build-editability"], extra_models=[imagen]
    )
    families = {m["family"] for m in ranked}
    assert "imagen" not in families
    # every survivor is edit-capable (assert the property, not a fixed count)
    assert all(m["edit"] not in (None, "", "none") for m in ranked)
    assert ranked, "shortlist should retain the edit-capable models"


def test_shortlist_cost_ranks_cheapest_first(model_registry):
    ranked = model_registry.shortlist_models(["cost"])
    assert ranked[0]["cost"] == "low"
    assert ranked[-1]["cost"] == "high"


def test_gpt_image_2_6_enters_at_stable_not_precise(model_registry):
    # Vendor positioning is not evidence that a chained build holds. Both 2.6
    # models stay "stable" until a real chained build proves one of them, so
    # the roster carries no "precise" model; promoting one edits this test.
    for model_id in ("gpt-image-2.6-flare", "gpt-image-2.6-sunburst"):
        attrs = model_registry.model_attributes(model_id)
        assert attrs is not None
        assert attrs["edit"] == "stable"
    assert all(m["edit"] != "precise" for m in model_registry.MODEL_REGISTRY)


def test_shortlist_build_editability_leads_with_edit_stable_models(model_registry):
    # A talk with builds lands on GPT Image 2.6: the edit tier is the primary
    # key, so both edit-stable 2.6 models precede every drifting (strong)
    # editor.
    ranked = model_registry.shortlist_models(["build-editability"])
    ids = [m["id"] for m in ranked]
    tiers = [m["edit"] for m in ranked]
    assert tiers == sorted(tiers, key=model_registry.EDIT_RANKING.index)
    assert set(ids[:2]) == {"gpt-image-2.6-flare", "gpt-image-2.6-sunburst"}
    assert all(m["edit"] == "strong" for m in ranked[2:])


def test_shortlist_build_editability_outranks_soft_signals(model_registry):
    # The lean is heavy: the cheapest, fastest editor still ranks below every
    # GPT Image 2.6 model when builds are in play. Without builds, cost rules
    # as before.
    with_builds = model_registry.shortlist_models(
        ["cost", "speed", "build-editability"]
    )
    ids = [m["id"] for m in with_builds]
    nano = ids.index("gemini-nano-banana-2.1")
    assert nano > ids.index("gpt-image-2.6-flare")
    assert nano > ids.index("gpt-image-2.6-sunburst")
    # Within one tier the soft signals decide: Flare is the faster 2.6 model.
    assert ids[:2] == ["gpt-image-2.6-flare", "gpt-image-2.6-sunburst"]
    without_builds = model_registry.shortlist_models(["cost", "speed"])
    assert without_builds[0]["id"] == "gemini-nano-banana-2.1"


def test_shortlist_injected_unknown_edit_tier_ranks_last(model_registry):
    # An injected editor with a tier string the ranking does not know survives
    # the filter but never outranks a known tier.
    odd = {
        "id": "vendor-x-editor",
        "family": "gemini",
        "cost": "low",
        "speed": "fast",
        "quality": "high",
        "edit": "yes",
    }
    ranked = model_registry.shortlist_models(
        ["cost", "build-editability"], extra_models=[odd]
    )
    assert ranked[-1]["id"] == "vendor-x-editor"


def test_shortlist_quality_then_editability(model_registry):
    # Edit tier leads; quality breaks ties within a tier, high before medium.
    ranked = model_registry.shortlist_models(["quality", "build-editability"])
    # the medium-quality Nano Banana 2.1 ranks last among the strong editors
    assert ranked[-1]["id"] == "gemini-nano-banana-2.1"


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
        "id": "gemini-5-ultra-image",
        "family": "gemini",
        "cost": "low",
        "speed": "fast",
        "quality": "high",
        "edit": "strong",
    }
    ranked = model_registry.shortlist_models(
        ["quality", "cost"], extra_models=[breakthrough]
    )
    ids = [m["id"] for m in ranked]
    assert "gemini-5-ultra-image" in ids
    # high quality + low cost ranks it ahead of the cached high-cost model
    assert ids.index("gemini-5-ultra-image") < ids.index("gpt-image-2.6-flare")


def test_shortlist_injected_model_respects_editability_filter(model_registry):
    # An injected model that can't edit is dropped under build-editability.
    no_edit = {
        "id": "fancy-but-no-edit",
        "family": "other",
        "cost": "low",
        "speed": "fast",
        "quality": "high",
        "edit": "none",
    }
    ranked = model_registry.shortlist_models(
        ["build-editability"], extra_models=[no_edit]
    )
    assert "fancy-but-no-edit" not in [m["id"] for m in ranked]


def test_shortlist_build_editability_excludes_missing_edit(model_registry):
    # An injected model that forgets its edit field must not slip into a
    # build-required shortlist — unknown edit support counts as not-capable.
    no_edit_field = {"id": "mystery-model", "family": "gemini", "quality": "high"}
    ranked = model_registry.shortlist_models(
        ["build-editability"], extra_models=[no_edit_field]
    )
    assert "mystery-model" not in [m["id"] for m in ranked]


def test_shortlist_injected_model_without_id_raises(model_registry):
    import pytest

    with pytest.raises(ValueError) as exc:
        model_registry.shortlist_models(["cost"], extra_models=[{"family": "gemini"}])
    assert "id" in str(exc.value)


def test_shortlist_extra_none_is_noop(model_registry):
    assert model_registry.shortlist_models(
        ["cost"], extra_models=None
    ) == model_registry.shortlist_models(["cost"])


def test_shortlist_deduplicates_priorities(model_registry):
    # A repeated priority must not double its weight — repetition is meaningless.
    assert model_registry.shortlist_models(
        ["cost", "cost"]
    ) == model_registry.shortlist_models(["cost"])


# --- Freshness ---


def test_freshness_fresh_when_recent(model_registry):
    reviewed = date.fromisoformat(model_registry.REGISTRY_LAST_REVIEWED)
    result = model_registry.check_freshness(today=reviewed)
    assert result["age_days"] == 0
    assert result["stale"] is False
    assert result["last_reviewed"] == model_registry.REGISTRY_LAST_REVIEWED


def test_freshness_stale_after_thirty_days(model_registry, monkeypatch):
    monkeypatch.setattr(model_registry, "REGISTRY_LAST_REVIEWED", "2024-01-01")
    result = model_registry.check_freshness(today=date(2024, 2, 1))
    assert result["stale"] is True
    assert result["age_days"] == 31
    assert result["max_age_days"] == 30


def test_freshness_boundary_not_stale_at_thirty_days(model_registry, monkeypatch):
    monkeypatch.setattr(model_registry, "REGISTRY_LAST_REVIEWED", "2024-01-01")
    result = model_registry.check_freshness(today=date(2024, 1, 31))
    assert result["age_days"] == 30
    assert result["stale"] is False


def test_freshness_includes_full_roster(model_registry):
    result = model_registry.check_freshness()
    assert [m["id"] for m in result["models"]] == model_registry.COMPARE_MODELS
