from __future__ import annotations

from dataclasses import dataclass

import filetype

ALLOWED = {
    "image/png": "png",
    "image/jpeg": "jpeg",
}


@dataclass(frozen=True)
class SniffResult:
    kind: str  # dicom | png | jpeg
    mime: str
    has_dicom_preamble: bool


def sniff(data: bytes, filename: str | None = None) -> SniffResult | None:
    if len(data) >= 132 and data[128:132] == b"DICM":
        return SniffResult("dicom", "application/dicom", True)

    guess = filetype.guess(data)
    if guess is not None and guess.mime in ALLOWED:
        return SniffResult(ALLOWED[guess.mime], guess.mime, False)

    if guess is not None and guess.mime == "application/dicom":
        return SniffResult("dicom", "application/dicom", False)

    if filename and filename.lower().endswith(".dcm"):
        try:
            import io

            import pydicom

            pydicom.dcmread(io.BytesIO(data), force=False, stop_before_pixels=True)
            return SniffResult("dicom", "application/dicom", False)
        except Exception:
            return None
    return None
