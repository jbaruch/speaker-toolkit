"""Tests for suggest-scrim-color.py — dark pixel sampling, luminance clamping, alpha."""

import numpy as np
from PIL import Image


def test_sample_dark_pixels_uniform(suggest_scrim_color, tmp_path):
    """A uniform dark image samples to approximately that color."""
    img = Image.new("RGB", (100, 100), (20, 10, 5))
    path = tmp_path / "slide-01.jpg"
    img.save(str(path))
    result = suggest_scrim_color.sample_dark_pixels([path])
    # Should be close to (20/255, 10/255, 5/255)
    assert abs(result[0] - 20 / 255) < 0.02
    assert abs(result[1] - 10 / 255) < 0.02
    assert abs(result[2] - 5 / 255) < 0.02


def test_sample_dark_pixels_multiple_images(suggest_scrim_color, tmp_path):
    """Sampling across multiple images averages the darkest pixels."""
    for i, color in enumerate([(10, 0, 0), (0, 10, 0), (0, 0, 10)]):
        img = Image.new("RGB", (50, 50), color)
        img.save(str(tmp_path / f"slide-{i:02d}.jpg"))
    paths = sorted(tmp_path.glob("slide-*.jpg"))
    result = suggest_scrim_color.sample_dark_pixels(paths)
    assert result.shape == (3,)
    assert all(0 <= v <= 1.0 for v in result)


def test_clamp_to_scrim_darkens(suggest_scrim_color):
    """Clamping reduces luminance to the target."""
    bright = np.array([0.5, 0.4, 0.3])
    clamped = suggest_scrim_color.clamp_to_scrim(bright, target_lum=0.10)
    lum = float(clamped @ suggest_scrim_color.REC709)
    assert lum <= 0.11  # approximately at target


def test_clamp_to_scrim_preserves_dark(suggest_scrim_color):
    """Already-dark values are not changed."""
    dark = np.array([0.02, 0.01, 0.005])
    clamped = suggest_scrim_color.clamp_to_scrim(dark, target_lum=0.10)
    np.testing.assert_array_almost_equal(clamped, dark)


def test_to_hex(suggest_scrim_color):
    assert suggest_scrim_color.to_hex(np.array([0.0, 0.0, 0.0])) == "000000"
    assert suggest_scrim_color.to_hex(np.array([1.0, 1.0, 1.0])) == "FFFFFF"
    result = suggest_scrim_color.to_hex(np.array([0.5, 0.25, 0.0]))
    assert len(result) == 6


def test_recommend_alpha_black(suggest_scrim_color):
    """Pure black (no chroma) gets base alpha ~45%."""
    alpha = suggest_scrim_color.recommend_alpha(np.array([0.05, 0.05, 0.05]))
    assert 44000 <= alpha <= 46000


def test_recommend_alpha_chromatic_higher(suggest_scrim_color):
    """Chromatic samples get bumped alpha above 45%."""
    alpha = suggest_scrim_color.recommend_alpha(np.array([0.15, 0.05, 0.01]))
    assert alpha > 45000
