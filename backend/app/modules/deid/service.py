from __future__ import annotations

import hashlib
import hmac
import io
from typing import Any

import pydicom
from pydicom.dataset import Dataset

from app.core.config import get_settings
from app.core.errors import AppError
from app.modules.deid.tags import REMOVE, REPLACE, RETAIN, is_remappable_uid

PIPELINE = "ps3.15-basic-subset/1.0"


def _uid_map(uid: str) -> str:
    secret = get_settings().secret_key.encode("utf-8")
    digest = hmac.new(secret, uid.encode("utf-8"), hashlib.sha256).digest()
    value = int.from_bytes(digest[:16], "big")
    return f"2.25.{value}"


def _is_uid_element(elem: Any) -> bool:
    return bool(getattr(elem, "VR", None) == "UI" and getattr(elem, "keyword", ""))


def deidentify_dicom(data: bytes) -> tuple[bytes, dict[str, Any]]:
    try:
        dataset = pydicom.dcmread(io.BytesIO(data), force=False)
    except Exception as exc:  # pydicom raises several unrelated types
        raise AppError(422, "dicom_unreadable", "DICOM file could not be read", str(exc)[:300]) from exc

    removed: list[str] = []
    replaced: list[str] = []
    retained: list[str] = [tag for tag in RETAIN if tag in dataset]
    warnings: list[str] = []

    if str(dataset.get("BurnedInAnnotation", "")).upper() == "YES":
        warnings.append(
            "DICOM declares burned-in annotation. Pixel-embedded text cannot be removed; "
            "review the image before sharing."
        )

    for keyword, value in REPLACE.items():
        if keyword in dataset:
            try:
                setattr(dataset, keyword, value)
                replaced.append(keyword)
            except Exception:
                warnings.append(f"Could not rewrite {keyword}")

    for keyword in REMOVE:
        if keyword in dataset:
            try:
                delattr(dataset, keyword)
                removed.append(keyword)
            except Exception:
                warnings.append(f"Could not remove {keyword}")

    dataset.remove_private_tags()

    remapped = 0
    for elem in dataset.iterall():
        if not _is_uid_element(elem):
            continue
        if not is_remappable_uid(elem.keyword):
            continue
        if elem.value:
            elem.value = _uid_map(str(elem.value))
            remapped += 1

    if dataset.file_meta:
        if getattr(dataset.file_meta, "MediaStorageSOPInstanceUID", None):
            dataset.file_meta.MediaStorageSOPInstanceUID = _uid_map(
                str(dataset.file_meta.MediaStorageSOPInstanceUID)
            )
            remapped += 1
        dataset.file_meta.ImplementationClassUID = "2.25.307244391909861228508812345700171783585"
        dataset.file_meta.ImplementationVersionName = "MIAP_010"

    dataset.PatientIdentityRemoved = "YES"
    dataset.DeidentificationMethod = PIPELINE
    dataset.SeriesDescription = "MIAP de-identified"
    dataset.Manufacturer = getattr(dataset, "Manufacturer", "") or "MIAP"

    buffer = io.BytesIO()
    try:
        dataset.save_as(buffer, enforce_file_format=True)
    except Exception as exc:
        raise AppError(422, "dicom_reencode_failed", "DICOM could not be written back", str(exc)[:300]) from exc

    output = buffer.getvalue()
    receipt = {
        "pipeline": PIPELINE,
        "sha256_in": hashlib.sha256(data).hexdigest(),
        "sha256_out": hashlib.sha256(output).hexdigest(),
        "removed": sorted(set(removed)),
        "replaced": sorted(set(replaced)),
        "retained": sorted(set(retained)),
        "uids_remapped": remapped,
        "reidentification_key_retained": False,
        "warnings": warnings,
    }
    return output, receipt


def deidentify_raster(data: bytes, mime: str) -> tuple[bytes, dict[str, Any]]:
    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as image:
            had_exif = bool(image.getexif())
            format_name = "PNG" if mime == "image/png" else "JPEG"
            working = image.convert("RGB") if image.mode not in ("L", "RGB") else image.copy()
            buffer = io.BytesIO()
            if format_name == "PNG":
                working.save(buffer, format="PNG", optimize=True)
            else:
                working.save(buffer, format="JPEG", quality=95, optimize=True)
    except Exception as exc:
        raise AppError(422, "image_unreadable", "Image file could not be read", str(exc)[:300]) from exc

    output = buffer.getvalue()
    warnings = [
        "No DICOM metadata. Modality and body region must be chosen manually or guessed by the fallback classifier."
    ]
    if had_exif:
        warnings.append("Embedded EXIF metadata was discarded.")
    receipt = {
        "pipeline": "exif-strip-raster/1.0",
        "sha256_in": hashlib.sha256(data).hexdigest(),
        "sha256_out": hashlib.sha256(output).hexdigest(),
        "removed": ["exif", "xmp", "icc-profile"] if had_exif else ["xmp"],
        "replaced": [],
        "retained": [],
        "uids_remapped": 0,
        "reidentification_key_retained": False,
        "warnings": warnings,
    }
    return output, receipt


def read_metadata(dataset: Dataset) -> dict[str, Any]:
    def text(keyword: str) -> str | None:
        value = dataset.get(keyword)
        if value is None or value == "":
            return None
        return str(value).strip()

    return {
        "modality_tag": text("Modality"),
        "body_part": text("BodyPartExamined"),
        "laterality": text("Laterality") or text("ImageLaterality"),
        "view": text("ViewPosition"),
        "rows": int(dataset.get("Rows", 0) or 0),
        "cols": int(dataset.get("Columns", 0) or 0),
        "photometric": text("PhotometricInterpretation"),
    }
