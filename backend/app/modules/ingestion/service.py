from __future__ import annotations

import io
from typing import Any

import numpy as np
import pydicom
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import append_audit
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.ids import new_id, utcnow_iso
from app.core.schema import Case, Image
from app.core.storage import sha256_bytes, write_blob
from app.modules.deid.service import deidentify_dicom, deidentify_raster, read_metadata
from app.modules.ingestion.sniff import sniff
from app.modules.routing.service import (
    capability_for,
    classify_modality,
    classify_region,
    normalise_laterality,
    normalise_view,
)

MIN_SIDE = 128
WARN_SIDE = 256


def _check(code: str, status: str, detail: str) -> dict[str, str]:
    return {"code": code, "status": status, "detail": detail}


def _validate_dicom(dataset: pydicom.Dataset) -> tuple[list[dict[str, str]], dict[str, Any]]:
    checks: list[dict[str, str]] = []
    rows = int(dataset.get("Rows", 0) or 0)
    cols = int(dataset.get("Columns", 0) or 0)

    if "PixelData" not in dataset:
        checks.append(_check("pixel_data", "fail", "No PixelData element"))
        return checks, {}
    checks.append(_check("pixel_data", "pass", "PixelData present"))

    try:
        pixels = dataset.pixel_array
    except Exception as exc:
        checks.append(_check("decode", "fail", f"Pixel data could not be decoded: {exc}"))
        return checks, {}

    if pixels.size == 0:
        checks.append(_check("decode", "fail", "Pixel array is empty"))
        return checks, {}

    sample = pixels[::4, ::4] if pixels.ndim >= 2 else pixels
    sample = np.asarray(sample, dtype=np.float32)
    std = float(sample.std())
    p1, p99 = np.percentile(sample, [1, 99])
    checks.append(_check("decode", "pass", f"Decoded {rows}x{cols}, {dataset.get('PhotometricInterpretation', 'unknown')}"))

    if min(rows, cols) < MIN_SIDE:
        checks.append(_check("dimensions", "fail", f"Image is {cols}x{rows}; minimum side is {MIN_SIDE}px"))
    elif min(rows, cols) < WARN_SIDE:
        checks.append(_check("dimensions", "warn", f"Low resolution: {cols}x{rows}px"))
    else:
        checks.append(_check("dimensions", "pass", f"{cols}x{rows}px"))

    if std == 0:
        checks.append(_check("content", "fail", "Image is a single flat value (blank)"))
    elif std < 1.0:
        checks.append(_check("content", "warn", "Very low pixel variance; image may be blank"))
    else:
        checks.append(_check("content", "pass", f"Pixel std {std:.1f}"))

    if (p99 - p1) < 10:
        checks.append(_check("contrast", "warn", "Very low dynamic range"))
    else:
        checks.append(_check("contrast", "pass", "Dynamic range looks usable"))

    photometric = str(dataset.get("PhotometricInterpretation", "")).upper()
    if photometric and photometric not in {"MONOCHROME1", "MONOCHROME2", "RGB", "YBR_FULL", "YBR_FULL_422"}:
        checks.append(_check("photometric", "warn", f"Unusual photometric interpretation: {photometric}"))

    return checks, {"std": std}


def _validate_raster(data: bytes) -> tuple[list[dict[str, str]], dict[str, Any]]:
    from PIL import Image

    checks: list[dict[str, str]] = []
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            width, height = image.size
            mode = image.mode
            array = np.asarray(image.convert("L"), dtype=np.float32)
    except Exception as exc:
        return [_check("decode", "fail", f"Image could not be decoded: {exc}")], {}

    checks.append(_check("decode", "pass", f"Decoded {width}x{height} {mode}"))
    if min(width, height) < MIN_SIDE:
        checks.append(_check("dimensions", "fail", f"Image is {width}x{height}; minimum side is {MIN_SIDE}px"))
    elif min(width, height) < WARN_SIDE:
        checks.append(_check("dimensions", "warn", f"Low resolution: {width}x{height}px"))
    else:
        checks.append(_check("dimensions", "pass", f"{width}x{height}px"))

    std = float(array.std())
    if std == 0:
        checks.append(_check("content", "fail", "Image is a single flat value (blank)"))
    elif std < 1.0:
        checks.append(_check("content", "warn", "Very low pixel variance; image may be blank"))
    else:
        checks.append(_check("content", "pass", f"Pixel std {std:.1f}"))

    checks.append(
        _check(
            "metadata",
            "warn",
            "No DICOM metadata. Choose modality and body region manually, or accept the assumed X-ray route.",
        )
    )
    return checks, {"std": std}


def ingest_upload(
    session: Session,
    *,
    actor_id: str,
    case: Case,
    filename: str | None,
    data: bytes,
    overrides: dict[str, str | None],
) -> tuple[Image, list[dict[str, str]], dict[str, Any]]:
    settings = get_settings()
    if not data:
        raise AppError(422, "empty_file", "Uploaded file is empty")
    if len(data) > settings.upload_max_bytes:
        raise AppError(
            413,
            "file_too_large",
            "Uploaded file is larger than the configured limit",
            f"Limit is {settings.upload_max_bytes} bytes",
        )

    found = sniff(data, filename)
    if found is None:
        raise AppError(
            415,
            "unsupported_media_type",
            "Only DICOM, PNG and JPEG images are accepted",
        )

    original_digest = sha256_bytes(data)
    warnings: list[str] = []

    if found.kind == "dicom":
        try:
            dataset = pydicom.dcmread(io.BytesIO(data), force=False)
        except Exception as exc:
            raise AppError(422, "dicom_unreadable", "DICOM file could not be read", str(exc)[:300]) from exc

        checks, _stats = _validate_dicom(dataset)
        metadata = read_metadata(dataset)
        deidentified, receipt = deidentify_dicom(data)
    else:
        checks, _stats = _validate_raster(data)
        metadata = {
            "modality_tag": None,
            "body_part": None,
            "laterality": None,
            "view": None,
            "rows": 0,
            "cols": 0,
            "photometric": None,
        }
        deidentified, receipt = deidentify_raster(data, found.mime)

    warnings.extend(receipt.get("warnings", []))
    failed = [check for check in checks if check["status"] == "fail"]
    if failed:
        detail = "; ".join(f"{item['code']}: {item['detail']}" for item in failed)
        raise AppError(422, "image_validation_failed", "Image failed validation", detail)

    modality = classify_modality(
        metadata.get("modality_tag"),
        overrides.get("modality"),
        has_dicom=found.kind == "dicom",
    )
    laterality = normalise_laterality(overrides.get("laterality") or metadata.get("laterality"))
    view = normalise_view(overrides.get("view") or metadata.get("view"))
    region = classify_region(
        metadata.get("body_part"),
        str(modality["value"]),
        view,
        laterality,
        overrides.get("body_part"),
    )

    if modality["value"] == "unknown":
        checks.append(_check("modality", "warn", "Modality could not be determined from metadata"))
    else:
        checks.append(_check("modality", "pass", f"Modality: {modality['value']} ({modality['method']})"))

    if region["value"] in {"unrecognised", "unknown"}:
        checks.append(_check("region", "warn", "Body region needs confirmation"))
    else:
        checks.append(_check("region", "pass", f"Region/view: {region['value']}"))

    storage_digest = write_blob(deidentified)
    now = utcnow_iso()

    image = Image(
        id=new_id("image"),
        case_id=case.id,
        blob_digest=storage_digest,
        original_digest=original_digest,
        mime="application/dicom" if found.kind == "dicom" else found.mime,
        modality=str(modality["value"]),
        laterality=laterality,
        view=view,
        body_part=str(region["value"]),
        body_part_raw=metadata.get("body_part"),
        rows=int(metadata.get("rows") or 0) or None,
        cols=int(metadata.get("cols") or 0) or None,
        photometric=metadata.get("photometric"),
        validation_json="{}",
        deid_receipt_json="{}",
        created_at=now,
    )
    import json

    validation = {
        "status": "warn" if any(c["status"] == "warn" for c in checks) else "pass",
        "passed": True,
        "checks": checks,
        "modality": modality,
        "region_or_view": region,
        "capability": capability_for(str(region["value"])),
        "warnings": warnings,
    }
    image.validation_json = json.dumps(validation, sort_keys=True)
    image.deid_receipt_json = json.dumps(receipt, sort_keys=True)
    session.add(image)

    case.modality = "mammogram" if modality["value"] == "mammogram" else (case.modality or "xray")
    case.status = "ready"

    append_audit(
        session,
        actor_id=actor_id,
        action="image.ingested",
        resource_type="image",
        resource_id=image.id,
        detail={
            "case_id": case.id,
            "sha256_in": original_digest,
            "sha256_out": storage_digest,
            "mime": image.mime,
            "modality": modality,
            "region_or_view": region,
        },
    )
    return image, checks, receipt


def case_images(session: Session, case_id: str) -> list[Image]:
    return list(
        session.execute(select(Image).where(Image.case_id == case_id).order_by(Image.created_at))
        .scalars()
        .all()
    )
