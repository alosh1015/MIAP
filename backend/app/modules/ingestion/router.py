from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.core.deps import require_image_reader, require_roles
from app.core.errors import AppError
from app.core.schema import Case, Image, User
from app.core.storage import blob_path, read_blob
from app.modules.cases.schemas import ImageSummary
from app.modules.cases.service import assert_case_access
from app.modules.ingestion.pixels import pixel_payload
from app.modules.ingestion.preview import render_preview
from app.modules.ingestion.service import ingest_upload

router = APIRouter(tags=["ingestion"])


async def _read_limited(upload: UploadFile, limit: int) -> bytes:
    allowed = limit + 1
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > allowed:
            raise AppError(
                413,
                "file_too_large",
                "Uploaded file is larger than the configured limit",
                f"Limit is {limit} bytes",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/cases/{case_id}/images", status_code=201)
async def upload_image(
    case_id: str,
    file: UploadFile = File(...),
    modality: str | None = Form(default=None),
    body_part: str | None = Form(default=None),
    laterality: str | None = Form(default=None),
    view: str | None = Form(default=None),
    session: Session = Depends(get_session),
    user: User = Depends(require_roles("clinician", "researcher")),
) -> dict:
    case = session.get(Case, case_id)
    assert_case_access(user, case)
    assert case is not None

    if case.created_by != user.id and user.role != "researcher":
        raise AppError(403, "forbidden", "Only the case owner can upload images")

    data = await _read_limited(file, get_settings().upload_max_bytes)
    overrides = {
        "modality": modality,
        "body_part": body_part,
        "laterality": laterality,
        "view": view,
    }
    image, checks, receipt = ingest_upload(
        session,
        actor_id=user.id,
        case=case,
        filename=file.filename,
        data=data,
        overrides=overrides,
    )
    session.commit()

    validation = json.loads(image.validation_json)
    summary = ImageSummary(
        id=image.id,
        modality=image.modality,
        laterality=image.laterality,
        view=image.view,
        body_part=image.body_part,
        mime=image.mime,
        rows=image.rows,
        cols=image.cols,
        created_at=image.created_at,
        validation=validation,
        deid_receipt=receipt,
    )
    return {"image": summary.model_dump(), "validation": validation, "deid_receipt": receipt}


@router.get("/images/{image_id}")
def get_image(
    image_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(require_image_reader),
) -> dict:
    image = session.get(Image, image_id)
    if image is None:
        raise AppError(404, "image_not_found", "Image not found")
    assert_case_access(user, session.get(Case, image.case_id))
    return {
        "id": image.id,
        "case_id": image.case_id,
        "modality": image.modality,
        "laterality": image.laterality,
        "view": image.view,
        "body_part": image.body_part,
        "mime": image.mime,
        "rows": image.rows,
        "cols": image.cols,
        "created_at": image.created_at,
        "validation": json.loads(image.validation_json or "{}"),
        "deid_receipt": json.loads(image.deid_receipt_json or "{}"),
    }


@router.get("/images/{image_id}/file")
def download_image(
    image_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(require_image_reader),
) -> FileResponse:
    image = session.get(Image, image_id)
    if image is None:
        raise AppError(404, "image_not_found", "Image not found")
    assert_case_access(user, session.get(Case, image.case_id))

    extension = {"application/dicom": "dcm", "image/png": "png", "image/jpeg": "jpg"}.get(image.mime, "bin")
    return FileResponse(
        blob_path(image.blob_digest),
        media_type=image.mime,
        headers={
            "Content-Disposition": f'inline; filename="{image.id}.{extension}"',
            "Cache-Control": "private, max-age=300",
        },
    )


@router.get("/images/{image_id}/pixels")
def image_pixels(
    image_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(require_image_reader),
) -> Response:
    image = session.get(Image, image_id)
    if image is None:
        raise AppError(404, "image_not_found", "Image not found")
    assert_case_access(user, session.get(Case, image.case_id))
    payload, media_type, meta = pixel_payload(image, read_blob(image.blob_digest))
    return Response(
        content=payload,
        media_type=media_type,
        headers={
            "X-MIAP-Meta": json.dumps(meta, ensure_ascii=True, separators=(",", ":")),
            "Cache-Control": "private, max-age=300",
        },
    )


@router.get("/images/{image_id}/preview.png")
def image_preview(
    image_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(require_image_reader),
) -> Response:
    image = session.get(Image, image_id)
    if image is None:
        raise AppError(404, "image_not_found", "Image not found")
    assert_case_access(user, session.get(Case, image.case_id))
    png = render_preview(image, read_blob(image.blob_digest))
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "private, max-age=300"})
