"""Tests for generate-thumbnail.py — prompt building and image validation (no API calls)."""

from io import BytesIO

from PIL import Image


def test_build_prompt_default(generate_thumbnail):
    prompt = generate_thumbnail.build_thumbnail_prompt("JUDGMENT DAY")
    assert "JUDGMENT DAY" in prompt
    assert "slide_dominant" in prompt or "fills most of the frame" in prompt
    assert "1280x720" in prompt


def test_build_prompt_with_subtitle(generate_thumbnail):
    prompt = generate_thumbnail.build_thumbnail_prompt("Test", subtitle="DevNexus 2026")
    assert "DevNexus 2026" in prompt


def test_build_prompt_split_panel_style(generate_thumbnail):
    prompt = generate_thumbnail.build_thumbnail_prompt("Title", style="split_panel")
    assert "Left half" in prompt or "split" in prompt.lower()


def test_build_prompt_overlay_style(generate_thumbnail):
    prompt = generate_thumbnail.build_thumbnail_prompt("Title", style="overlay")
    assert "cutout" in prompt.lower() or "overlay" in prompt.lower()


def test_build_prompt_brand_colors(generate_thumbnail):
    prompt = generate_thumbnail.build_thumbnail_prompt(
        "Title", brand_colors=["#5B2C6F", "#C0392B"]
    )
    assert "#5B2C6F" in prompt
    assert "#C0392B" in prompt


def test_build_prompt_title_position(generate_thumbnail):
    prompt = generate_thumbnail.build_thumbnail_prompt("Title", title_position="bottom")
    assert "bottom third" in prompt


def test_validate_and_resize_correct_dimensions(generate_thumbnail):
    # Create a 1280x720 image
    img = Image.new("RGB", (1280, 720), (255, 0, 0))
    buf = BytesIO()
    img.save(buf, format="PNG")
    image_bytes = buf.getvalue()

    result_bytes, mime = generate_thumbnail.validate_and_resize(image_bytes, "image/png")
    result_img = Image.open(BytesIO(result_bytes))
    assert result_img.size == (1280, 720)


def test_validate_and_resize_rescales(generate_thumbnail):
    # Create a non-standard sized image
    img = Image.new("RGB", (800, 600), (0, 255, 0))
    buf = BytesIO()
    img.save(buf, format="PNG")
    image_bytes = buf.getvalue()

    result_bytes, mime = generate_thumbnail.validate_and_resize(image_bytes, "image/png")
    result_img = Image.open(BytesIO(result_bytes))
    assert result_img.size == (1280, 720)


def test_validate_and_resize_size_limit(generate_thumbnail):
    result_bytes, mime = generate_thumbnail.validate_and_resize(
        _make_large_image_bytes(), "image/png"
    )
    assert len(result_bytes) <= 2 * 1024 * 1024


def test_validate_and_resize_rgba_to_rgb(generate_thumbnail):
    img = Image.new("RGBA", (1280, 720), (255, 0, 0, 128))
    buf = BytesIO()
    img.save(buf, format="PNG")
    image_bytes = buf.getvalue()

    result_bytes, mime = generate_thumbnail.validate_and_resize(image_bytes, "image/png")
    result_img = Image.open(BytesIO(result_bytes))
    assert result_img.mode == "RGB"


def _make_large_image_bytes():
    """Create a large random-ish image that exceeds 2MB as PNG."""
    import random
    random.seed(42)
    img = Image.new("RGB", (1280, 720))
    pixels = img.load()
    for x in range(1280):
        for y in range(720):
            pixels[x, y] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
