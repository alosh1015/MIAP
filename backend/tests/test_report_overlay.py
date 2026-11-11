from __future__ import annotations

import io
from types import SimpleNamespace

import numpy as np
from PIL import Image as PILImage

from app.modules.reporting.templates.common import (
    _display_gray,
    _draw_annotations,
    overlay_preview as _overlay_preview,
)


def _png_bytes(image: PILImage.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_overlay_is_composited_onto_the_original_image(tmp_path):
    width, height = 400, 300
    ramp = np.tile(np.linspace(0, 255, width, dtype=np.uint8), (height, 1))
    source = PILImage.fromarray(ramp, "L")

    heat = PILImage.new("RGBA", (224, 224), (0, 0, 0, 0))
    for y in range(62, 162):
        for x in range(62, 162):
            heat.putpixel((x, y), (255, 0, 0, 255))
    heatmap_path = tmp_path / "heatmap.png"
    heat.save(heatmap_path)

    image = SimpleNamespace(mime="image/png")
    preview = _overlay_preview(image, _png_bytes(source), heatmap_path)

    assert preview.size == (width, height)
    assert preview.mode == "RGB"

    # The heatmap is resized to the centre square (300x300 at x=50..349) and
    # must tint the middle of the image.
    centre = preview.getpixel((200, 150))
    assert centre[0] > 200 and centre[0] > centre[1] + 100

    # Pixels outside the centre square keep their grey value.
    corner = preview.getpixel((10, 150))
    assert corner[0] == corner[1] == corner[2]
    assert abs(int(corner[0]) - int(ramp[150, 10])) <= 2


def test_reviewer_highlights_are_painted_inside_the_preview():
    preview = PILImage.new("RGB", (100, 100), (0, 0, 0))
    polygon = [(0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75)]

    assert _draw_annotations(preview, [polygon]) is True
    inside = preview.getpixel((50, 50))
    assert inside[0] > inside[2]
    assert preview.getpixel((5, 5)) == (0, 0, 0)

    assert _draw_annotations(preview, []) is False


def test_display_gray_applies_window_and_monochrome1():
    array = np.array([[0.0, 100.0]], dtype=np.float32)
    meta = {
        "photometric": "MONOCHROME1",
        "slope": 1.0,
        "intercept": 0.0,
        "window_center": 50.0,
        "window_width": 100.0,
    }
    grey = _display_gray(array, meta)
    assert grey.tolist() == [[255, 0]]
