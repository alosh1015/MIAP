from __future__ import annotations

import io

import numpy as np
from PIL import Image as PILImage

from app.core.schema import Image


def _normalise(array: np.ndarray) -> np.ndarray:
    array = array.astype(np.float32)
    low, high = np.percentile(array, [1, 99])
    if high <= low:
        high = low + 1.0
    scaled = np.clip((array - low) / (high - low), 0.0, 1.0)
    return (scaled * 255).astype(np.uint8)


def _dicom_preview(data: bytes, max_side: int) -> bytes:
    import pydicom

    dataset = pydicom.dcmread(io.BytesIO(data), force=False)
    array = dataset.pixel_array
    if array.ndim == 3:
        array = array[..., 0]
    if str(dataset.get("PhotometricInterpretation", "")).upper() == "MONOCHROME1":
        array = array.max() - array
    image = PILImage.fromarray(_normalise(array), mode="L")
    image.thumbnail((max_side, max_side))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _raster_preview(data: bytes, max_side: int) -> bytes:
    with PILImage.open(io.BytesIO(data)) as image:
        working = image.convert("RGB") if image.mode not in ("L", "RGB") else image.copy()
        working.thumbnail((max_side, max_side))
        buffer = io.BytesIO()
        working.save(buffer, format="PNG")
        return buffer.getvalue()


def render_preview(image: Image, data: bytes, max_side: int = 1024) -> bytes:
    if image.mime == "application/dicom":
        return _dicom_preview(data, max_side)
    return _raster_preview(data, max_side)
