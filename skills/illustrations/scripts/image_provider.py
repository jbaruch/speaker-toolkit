"""Shared per-render routing and truthful image-lane diagnostics.

API adapters stay in their existing generators. Only compatible native requests
load the supervised Codex adapter; importing this module reads no credentials.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import sys
from typing import Any, Iterator

from image_lane_contract import ImageLane, ImageLaneError
from model_registry import resolve_image_lane


@dataclass(frozen=True)
class ImageProviderOptions:
    lane: str = "auto"
    allow_cli_native: bool = False


@dataclass(frozen=True)
class ImageRender:
    """Two-value adapter outcome plus the actual selected lane, never a model guess."""

    data: bytes | None
    detail: str
    lane: ImageLane | None
    width: int | None = None
    height: int | None = None
    sha256: str | None = None
    warning_count: int = 0

    def __iter__(self) -> Iterator[Any]:
        # Preserve the existing heterogeneous two-value unpacking interface.
        yield self.data
        yield self.detail

    def provenance(self) -> dict:
        return {
            "lane": asdict(self.lane) if self.lane is not None else None,
            "width": self.width,
            "height": self.height,
            "sha256": self.sha256,
            "warning_count": self.warning_count,
        }


def add_image_lane_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--image-lane",
        choices=("auto", "api", "cli"),
        default="auto",
        help="Prefer a compatible subscription CLI, force API, or require CLI. "
        "A CLI failure never retries a paid API.",
    )
    parser.add_argument(
        "--allow-cli-native",
        action="store_true",
        help="Opt into an unpinned native image model and observed dimensions. "
        "Does not enable unverified masks or multi-reference composition.",
    )


def report_lane(lane: ImageLane) -> None:
    # JSON quoting keeps paths and all other fields on one diagnostic line.
    print("IMAGE_LANE " + json.dumps(asdict(lane), sort_keys=True), file=sys.stderr)


def select_image_lane(
    model: str,
    options: ImageProviderOptions | None = None,
    *,
    operation: str = "generate",
    requested_size: tuple[int, int] | None = None,
    reference_count: int = 0,
    masked: bool = False,
    report: bool = True,
) -> ImageLane:
    """Select before reading API credentials; only absence permits API fallback."""
    options = options or ImageProviderOptions()
    if not isinstance(options, ImageProviderOptions):
        raise ImageLaneError("invalid_image_lane", "supply ImageProviderOptions")

    def resolve(probe=None):
        return resolve_image_lane(
            model,
            probe,
            forced_lane=options.lane,
            operation=operation,
            requested_size=requested_size,
            reference_count=reference_count,
            masked=masked,
            allow_native_model=options.allow_cli_native,
            allow_native_geometry=options.allow_cli_native,
        )

    try:
        lane = resolve()
    except ImageLaneError as error:
        if error.reason_code != "cli_probe_required":
            raise
        from image_cli import probe_codex

        lane = resolve(probe_codex())
    if report:
        report_lane(lane)
    return lane


def render_cli(
    lane: ImageLane, prompt: str, reference: str | None = None
) -> ImageRender:
    """Execute once. An unsuccessful CLI has no API-dispatch path."""
    from image_cli import render_codex

    try:
        image = render_codex(lane, prompt, reference_path=reference)
    except ImageLaneError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return ImageRender(None, str(error), lane)
    if image.warning_count:
        print(
            f"WARNING: cli_item_diagnostics ({image.warning_count}); Codex completed "
            "with non-fatal item diagnostics. Inspect your CLI setup; diagnostic "
            "text is withheld and no API retry was selected.",
            file=sys.stderr,
        )
    print(
        "IMAGE_OUTPUT "
        + json.dumps(
            {
                "served_model": lane.served_model,
                "width": image.width,
                "height": image.height,
                "sha256": image.sha256,
            },
            sort_keys=True,
        ),
        file=sys.stderr,
    )
    return ImageRender(
        image.data,
        image.mime_type,
        lane,
        image.width,
        image.height,
        image.sha256,
        image.warning_count,
    )
