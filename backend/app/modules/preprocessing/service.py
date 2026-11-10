from __future__ import annotations

import io
from typing import Any

import numpy as np


def _dicom_array(data: bytes) -> tuple[np.ndarray, dict[str, Any]]:
    import pydicom

    dataset = pydicom.dcmread(io.BytesIO(data), force=False)
    array = dataset.pixel_array
    meta = {
        "photometric": str(dataset.get("PhotometricInterpretation", "")).upper(),
        "rows": int(dataset.get("Rows", 0) or 0),
        "cols": int(dataset.get("Columns", 0) or 0),
        "rescale_slope": float(dataset.get("RescaleSlope", 1) or 1),
        "rescale_intercept": float(dataset.get("RescaleIntercept", 0) or 0),
    }
    array = array.astype(np.float32) * meta["rescale_slope"] + meta["rescale_intercept"]
    return array, meta


def _raster_array(data: bytes) -> tuple[np.ndarray, dict[str, Any]]:
    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        array = np.asarray(image.convert("L"), dtype=np.float32)
        meta = {"photometric": "MONOCHROME2", "rows": image.height, "cols": image.width}
    return array, meta


def load_pixels(mime: str, data: bytes) -> tuple[np.ndarray, dict[str, Any]]:
    if mime == "application/dicom":
        return _dicom_array(data)
    return _raster_array(data)


def to_model_input(
    array: np.ndarray,
    *,
    photometric: str = "",
    size: int = 224,
) -> tuple[np.ndarray, dict[str, float]]:
    """Return a 1x1xSxS float32 tensor-ready array in TorchXRayVision's range."""
    import torchvision
    import torchxrayvision as xrv

    working = np.asarray(array, dtype=np.float32)
    if working.ndim == 3:
        working = working[..., 0]
    if photometric == "MONOCHROME1":
        working = working.max() - working

    # Stretch to 8-bit so normalisation is comparable across sources.
    low, high = np.percentile(working, [0.5, 99.5])
    if high <= low:
        high = low + 1.0
    scaled = np.clip((working - low) / (high - low), 0.0, 1.0) * 255.0

    normalised = xrv.datasets.normalize(scaled, 255)
    normalised = normalised[None, :, :]
    transforms = torchvision.transforms.Compose(
        [xrv.datasets.XRayCenterCrop(), xrv.datasets.XRayResizer(size)]
    )
    # XRay transforms take and return (1, H, W); add the batch dim last.
    tensor = transforms(normalised).astype(np.float32)[None, ...]

    stats = {
        "min": float(tensor.min()),
        "max": float(tensor.max()),
        "mean": float(tensor.mean()),
        "std": float(tensor.std()),
        "size": float(size),
    }
    return tensor, stats
