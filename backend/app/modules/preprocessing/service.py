from __future__ import annotations

import io
from typing import Any

import numpy as np

from app.modules.preprocessing.profiles import Profile, profile_for


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


def _stretch(array: np.ndarray, photometric: str) -> np.ndarray:
    working = np.asarray(array, dtype=np.float32)
    if working.ndim == 3:
        working = working[..., 0]
    if photometric == "MONOCHROME1":
        working = working.max() - working
    low, high = np.percentile(working, [0.5, 99.5])
    if high <= low:
        high = low + 1.0
    return np.clip((working - low) / (high - low), 0.0, 1.0)


def _resize(unit: np.ndarray, spec: Profile) -> np.ndarray:
    from PIL import Image

    height, width = spec.size
    image = Image.fromarray(np.rint(unit * 255.0).astype(np.uint8), mode="L")
    resized = image.resize((width, height), Image.BILINEAR)
    return np.asarray(resized, dtype=np.float32) / 255.0


def _tensor_for(unit: np.ndarray, spec: Profile) -> np.ndarray:
    if spec.scale == "xrv":
        import torchvision
        import torchxrayvision as xrv

        normalised = xrv.datasets.normalize(unit * 255.0, 255)
        transforms = torchvision.transforms.Compose(
            [xrv.datasets.XRayCenterCrop(), xrv.datasets.XRayResizer(spec.size[0])]
        )
        return transforms(normalised[None, :, :]).astype(np.float32)[None, ...]

    resized = _resize(unit, spec)
    if spec.scale == "unit":
        planes = np.repeat(resized[None, :, :], spec.channels, axis=0)
    elif spec.scale == "half":
        planes = np.repeat(((resized - 0.5) / 0.5)[None, :, :], spec.channels, axis=0)
    else:
        raise ValueError(f"Unknown scale: {spec.scale}")
    return planes[None, ...].astype(np.float32)


def to_model_input(
    array: np.ndarray,
    *,
    photometric: str = "",
    profile: str | Profile = "xrv_chest_224",
    size: int | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Return a 1xCxHxW float32 array prepared for the named profile."""
    spec = profile if isinstance(profile, Profile) else profile_for(profile)
    if size is not None and spec.name == "xrv_chest_224" and size != spec.size[0]:
        spec = Profile(
            name=spec.name,
            size=(size, size),
            channels=spec.channels,
            crop=spec.crop,
            scale=spec.scale,
            normalisation=spec.normalisation,
        )
    tensor = _tensor_for(_stretch(array, photometric), spec)
    stats = {
        "min": float(tensor.min()),
        "max": float(tensor.max()),
        "mean": float(tensor.mean()),
        "std": float(tensor.std()),
        "size": float(spec.size[0]),
        "channels": int(spec.channels),
        "profile": spec.name,
    }
    return tensor, stats
