#!/usr/bin/env python3
"""Suggest a deck-appropriate scrim color by sampling the illustrations.

A pure-black scrim desaturates warm/cool decks uniformly. Sampling the
natural shadow tone of the deck's own illustrations gives a scrim that
reads as "deeper shadow in the same style" rather than a flat black film.

Algorithm:
  1. For each illustration, resize to 200px longest edge (speed).
  2. Compute luminance per pixel (Rec. 709).
  3. Take the darkest 5% of pixels across the whole deck.
  4. Average their sRGB values.
  5. Clamp the result: push luminance down to ~8-12% so the sample is
     usable as a scrim (otherwise mid-shadow averages come out too light).

Output: suggested hex color + a recommended alpha (OOXML thousandths).
"""
import argparse
from pathlib import Path

from PIL import Image
import numpy as np

REC709 = np.array([0.2126, 0.7152, 0.0722])


def sample_dark_pixels(img_paths, percentile=5.0, resize_to=200):
    buckets = []
    for p in img_paths:
        img = Image.open(p).convert("RGB")
        img.thumbnail((resize_to, resize_to), Image.LANCZOS)
        arr = np.asarray(img, dtype=np.float32) / 255.0  # (H, W, 3)
        lum = arr @ REC709                                # (H, W)
        flat_px = arr.reshape(-1, 3)
        flat_lum = lum.reshape(-1)
        cutoff = np.percentile(flat_lum, percentile)
        mask = flat_lum <= cutoff
        if mask.sum() == 0:
            continue
        buckets.append(flat_px[mask])
    if not buckets:
        raise SystemExit("No pixels sampled — check image directory.")
    all_dark = np.concatenate(buckets, axis=0)
    return all_dark.mean(axis=0)  # (3,) in 0..1


def clamp_to_scrim(rgb01, target_lum=0.10):
    """Darken the sample so it's usable as a scrim base color.

    Preserves hue/chroma by scaling RGB uniformly to hit a target luminance.
    """
    lum = float(rgb01 @ REC709)
    if lum <= 1e-4:
        return rgb01
    scale = min(1.0, target_lum / lum)
    return rgb01 * scale


def to_hex(rgb01):
    rgb = np.clip(rgb01 * 255.0, 0, 255).astype(int)
    return "{:02X}{:02X}{:02X}".format(*rgb)


def recommend_alpha(sample_rgb01):
    """Warmer, more saturated samples need a touch more opacity.

    Black scrims need only 45% to read; tinted scrims lose some darkening
    power to the tint, so bump alpha a little when chroma is nonzero.
    """
    chroma = float(np.max(sample_rgb01) - np.min(sample_rgb01))
    base = 0.45
    bump = min(0.10, chroma * 0.5)
    alpha = base + bump
    return int(round(alpha * 100000))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("illustrations_dir", type=Path)
    ap.add_argument("--percentile", type=float, default=5.0,
                    help="Sample the darkest N%% of pixels (default 5)")
    ap.add_argument("--target-luminance", type=float, default=0.10,
                    help="Clamp sample to this Rec. 709 luminance (default 0.10)")
    ap.add_argument("--glob", default="slide-*.jpg")
    args = ap.parse_args()

    paths = sorted(args.illustrations_dir.glob(args.glob))
    if not paths:
        raise SystemExit(f"No files matching {args.glob} in {args.illustrations_dir}")

    raw = sample_dark_pixels(paths, percentile=args.percentile)
    scrim = clamp_to_scrim(raw, target_lum=args.target_luminance)
    alpha = recommend_alpha(raw)

    print(f"Sampled {len(paths)} illustrations, darkest {args.percentile:.0f}% of pixels")
    print(f"  raw dark-pixel mean : #{to_hex(raw)} (lum={float(raw @ REC709):.3f})")
    print(f"  scrim base color    : #{to_hex(scrim)} (lum={float(scrim @ REC709):.3f})")
    print(f"  recommended alpha   : {alpha} / 100000 ({alpha/1000:.1f}% opaque)")
    print()
    print("OOXML:")
    print(f'  <a:solidFill><a:srgbClr val="{to_hex(scrim)}">'
          f'<a:alpha val="{alpha}"/></a:srgbClr></a:solidFill>')


if __name__ == "__main__":
    main()
