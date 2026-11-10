"""Decoded pixel access for the viewer.

The viewer needs raw samples, not a re-encoded preview: window/level, zoom and
measurement all operate on the original values. Decoding server-side keeps one
decoder (pydicom) for every transfer syntax accepted at upload, instead of a
second one in the browser that cannot read JPEG/J2K-compressed DICOM.
"""

from __future__ import annotations

import io

import numpy as np

from app.core.schema import Image

MIME_TYPES = {
    "int16": "application/x-miap-int16",
    "uint16": "application/x-miap-uint16",
    "uint8": "application/x-miap-uint8",
    "float32": "application/x-miap-float32",
}


def _first(value, default=None):
    if value is None:
        return default
    if isinstance(value, (list, tuple)):
        return value[0] if value else default
    try:
        if len(value) > 1 and not isinstance(value, str):
            return value[0]
    except TypeError:
        pass
    return value


def _dicom_meta(dataset, rows: int, cols: int) -> dict:
    import pydicom

    pixel = dataset.get("PixelSpacing")
    row_spacing = float(pixel[0]) if pixel else 1.0
    col_spacing = float(pixel[1]) if pixel else 1.0
    return {
        "rows": rows,
        "cols": cols,
        "samples_per_pixel": int(dataset.get("SamplesPerPixel", 1) or 1),
        "photometric": str(dataset.get("PhotometricInterpretation", "MONOCHROME2")).upper(),
        "slope": float(_first(dataset.get("RescaleSlope"), 1.0) or 1.0),
        "intercept": float(_first(dataset.get("RescaleIntercept"), 0.0) or 0.0),
        "window_center": _as_float(_first(dataset.get("WindowCenter"))),
        "window_width": _as_float(_first(dataset.get("WindowWidth"))),
        "column_pixel_spacing": col_spacing,
        "row_pixel_spacing": row_spacing,
        "frames": int(dataset.get("NumberOfFrames", 1) or 1),
        "voi_lut_function": str(dataset.get("VOILUTFunction", "LINEAR")).upper(),
    }


def _as_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dicom_pixels(dataset) -> tuple[np.ndarray, dict]:
    photometric = str(dataset.get("PhotometricInterpretation", "MONOCHROME2")).upper()
    array = dataset.pixel_array

    if array.ndim == 4:
        array = array[0]
    elif array.ndim == 3 and photometric in {"MONOCHROME1", "MONOCHROME2"}:
        array = array[0]

    rows, cols = int(dataset.get("Rows", array.shape[0])), int(dataset.get("Columns", array.shape[1]))
    return array, _dicom_meta(dataset, rows, cols)


def _raster_pixels(data: bytes) -> tuple[np.ndarray, dict]:
    from PIL import Image as PILImage

    with PILImage.open(io.BytesIO(data)) as opened:
        # Radiology pixels are monochrome; converting keeps one code path in the
        # viewer and avoids colour-management differences between browsers.
        array = np.array(opened.convert("L"))
        return array, {
            "rows": int(array.shape[0]),
            "cols": int(array.shape[1]),
            "samples_per_pixel": 1,
            "photometric": "MONOCHROME2",
            "slope": 1.0,
            "intercept": 0.0,
            "window_center": None,
            "window_width": None,
            "column_pixel_spacing": 1.0,
            "row_pixel_spacing": 1.0,
            "frames": 1,
            "voi_lut_function": "LINEAR",
        }


def read_pixel_data(image: Image, data: bytes) -> tuple[np.ndarray, dict]:
    if image.mime == "application/dicom":
        import pydicom

        dataset = pydicom.dcmread(io.BytesIO(data), force=False)
        array, meta = _dicom_pixels(dataset)
    else:
        array, meta = _raster_pixels(data)

    if array.dtype not in (np.dtype("uint8"), np.dtype("uint16"), np.dtype("int16"), np.dtype("float32")):
        array = array.astype(np.float32)

    if array.dtype.byteorder == ">" or (array.dtype.byteorder == "=" and not np.little_endian):
        array = array.astype(array.dtype.newbyteorder("<"), copy=False)

    array = np.ascontiguousarray(array)
    meta["dtype"] = array.dtype.name
    meta["min"] = float(array.min())
    meta["max"] = float(array.max())
    return array, meta


def pixel_payload(image: Image, data: bytes) -> tuple[bytes, str, dict]:
    array, meta = read_pixel_data(image, data)
    return array.tobytes(order="C"), MIME_TYPES[meta["dtype"]], meta
