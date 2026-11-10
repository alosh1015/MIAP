from __future__ import annotations

import io
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import append_audit
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.ids import new_id, utcnow_iso
from app.core.schema import Case, Image, Job, Report, Result, User
from app.core.storage import read_blob, resolve_relative
from app.modules.cases.service import can_access_case
from app.modules.models.router import load_registry

DISCLAIMER = (
    "Decision support only. This report is not a diagnosis and must not replace "
    "review by a qualified clinician."
)


def _model_card(document: dict) -> dict:
    name = document.get("model", {}).get("name")
    version = document.get("model", {}).get("version")
    for entry in load_registry():
        if entry.get("model_id") == name and entry.get("version") == version:
            return entry.get("card", {})
    return {}


def _display_gray(array: np.ndarray, meta: dict) -> np.ndarray:
    """Map stored pixel values to 8-bit display values, mirroring to_model_input."""
    working = np.asarray(array, dtype=np.float32)
    if working.ndim == 3:
        if working.shape[-1] in (3, 4):
            working = working[..., :3].mean(axis=-1)
        else:
            working = working[0]

    slope = float(meta.get("slope") or 1.0)
    intercept = float(meta.get("intercept") or 0.0)
    working = working * slope + intercept

    if meta.get("photometric") == "MONOCHROME1":
        working = working.max() + working.min() - working

    center = meta.get("window_center")
    width = meta.get("window_width")
    if center is not None and width and width > 1:
        low, high = center - width / 2.0, center + width / 2.0
    else:
        low, high = np.percentile(working, [0.5, 99.5])
        if high <= low:
            high = low + 1.0

    scaled = np.clip((working - low) / (high - low), 0.0, 1.0)
    return (scaled * 255.0).astype(np.uint8)


def _overlay_preview(image: Image, data: bytes, heatmap_path: Path):
    """Composite the heatmap over the centre square of the original image.

    The model input is a centre crop resized to 224x224, so the heatmap maps to
    the central square of the stored image. This is the same mapping the viewer
    overlay uses; without it the report shows a floating heatmap on white.
    """
    from PIL import Image as PILImage

    from app.modules.ingestion.pixels import read_pixel_data

    array, meta = read_pixel_data(image, data)
    grey = _display_gray(array, meta)
    height, width = grey.shape
    side = min(height, width)
    top = (height - side) // 2
    left = (width - side) // 2

    with PILImage.open(heatmap_path) as opened:
        heat = opened.convert("RGBA").resize((side, side), PILImage.Resampling.BILINEAR)

    base = PILImage.fromarray(np.repeat(grey[..., None], 3, axis=2), "RGB")
    base.paste(heat, (left, top), heat)
    return base


def _stylesheet():
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm

    base = getSampleStyleSheet()
    return {
        "title": base["Title"],
        "heading": base["Heading2"],
        "body": base["BodyText"],
        "small": ParagraphStyle("small", parent=base["BodyText"], fontSize=8, leading=10),
        "warn": ParagraphStyle(
            "warn",
            parent=base["BodyText"],
            fontSize=9,
            leading=11,
            textColor=colors.HexColor("#8a1c1c"),
        ),
        "mm": mm,
    }


def _latest_result(session: Session, case_id: str, job_id: str | None) -> tuple[Result, Job]:
    if job_id:
        job = session.get(Job, job_id)
        if job is None or job.case_id != case_id:
            raise AppError(404, "job_not_found", "Analysis job not found for this case")
        result = session.execute(select(Result).where(Result.job_id == job.id)).scalar_one_or_none()
        if result is None or job.state != "completed":
            raise AppError(409, "job_not_complete", "The analysis has not completed")
        return result, job

    row = session.execute(
        select(Result).where(Result.case_id == case_id).order_by(Result.created_at.desc())
    ).scalars().first()
    if row is None:
        raise AppError(409, "no_results", "This case has no completed analysis to report")
    job = session.get(Job, row.job_id)
    return row, job


def render_report(session: Session, user: User, case_id: str, job_id: str | None = None) -> Report:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Image as PdfImage,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    case = session.get(Case, case_id)
    if case is None or not can_access_case(user, case):
        raise AppError(404, "case_not_found", "Case not found")

    result, job = _latest_result(session, case_id, job_id)
    document = json.loads(result.document_json)
    card = _model_card(document)
    image = session.get(Image, result.image_id)

    report_id = new_id("report")
    directory = get_settings().report_dir
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{report_id}.pdf"

    styles = _stylesheet()
    story = [
        Paragraph("MIAP imaging decision-support report", styles["title"]),
        Paragraph(
            f"Case {case.pseudonym} - generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            styles["body"],
        ),
        Spacer(1, 4 * mm),
        Paragraph(DISCLAIMER, styles["warn"]),
        Spacer(1, 4 * mm),
    ]

    facts = [
        ["Case pseudonym", case.pseudonym],
        ["Consent", case.consent],
        ["Image", f"{image.id if image else 'unknown'} ({image.mime if image else ''})"],
        ["Modality", document["modality"]["value"]],
        ["Region / view", document["region_or_view"]["value"]],
        ["Model", f"{document['model']['name']} {document['model']['version']}"],
        ["Model digest", (document["model"].get("digest") or "n/a")[:32]],
        ["Provenance", document.get("provenance_id", "")],
        ["Analysis job", job.id],
    ]
    facts_table = Table(facts, colWidths=[42 * mm, 118 * mm])
    facts_table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#444444")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story += [facts_table, Spacer(1, 5 * mm), Paragraph("Findings", styles["heading"])]

    rows = [["Finding", "Probability"]]
    for finding in document.get("findings", []):
        rows.append([finding["label"], f"{finding['probability'] * 100:.1f}%"])
    findings_table = Table(rows, colWidths=[110 * mm, 40 * mm], hAlign="LEFT")
    findings_table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
                ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.grey),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story += [findings_table, Spacer(1, 4 * mm)]

    if document.get("heatmap"):
        heatmap_png = resolve_relative(document["heatmap"]["overlay_png"]) if document["heatmap"].get("overlay_png") else None
        if heatmap_png is not None and Path(heatmap_png).exists():
            preview = None
            if image is not None:
                try:
                    preview = _overlay_preview(image, read_blob(image.blob_digest), Path(heatmap_png))
                except Exception:  # noqa: BLE001 - the report must still render
                    traceback.print_exc()
            if preview is not None:
                buffer = io.BytesIO()
                preview.save(buffer, format="PNG")
                buffer.seek(0)
                ratio = preview.height / preview.width
                width_mm, height_mm = 100.0, 100.0 * ratio
                if height_mm > 120.0:
                    height_mm, width_mm = 120.0, 120.0 / ratio
                story += [
                    PdfImage(buffer, width=width_mm * mm, height=height_mm * mm),
                    Paragraph(
                        "Heatmap overlaid on the de-identified image: where the model "
                        "looked, not proof of a finding. The model input is the centre "
                        "square, so the overlay covers that region.",
                        styles["small"],
                    ),
                    Spacer(1, 3 * mm),
                ]
            else:
                story += [
                    PdfImage(str(heatmap_png), width=70 * mm, height=70 * mm),
                    Paragraph(
                        "Heatmap only, original image could not be rendered: where the "
                        "model looked, not proof of a finding.",
                        styles["small"],
                    ),
                    Spacer(1, 3 * mm),
                ]

    story += [Paragraph("Warnings", styles["heading"])]
    for warning in document.get("warnings", []):
        story.append(Paragraph(f"- {warning}", styles["body"]))

    if card.get("limitations"):
        story += [Spacer(1, 3 * mm), Paragraph("Model limitations", styles["heading"])]
        for limitation in card["limitations"]:
            story.append(Paragraph(f"- {limitation}", styles["body"]))
        story += [
            Spacer(1, 2 * mm),
            Paragraph(f"Intended use: {card.get('intended_use', '')}", styles["small"]),
            Paragraph(f"Validation: {card.get('validation', '')}", styles["small"]),
        ]

    story += [
        Spacer(1, 6 * mm),
        Paragraph(DISCLAIMER, styles["warn"]),
        Paragraph(
            f"Report {report_id} - generated from the stored JSON result; the JSON is canonical.",
            styles["small"],
        ),
    ]

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"MIAP report {case.pseudonym}",
        author="MIAP",
        subject="Decision-support report",
    )
    doc.build(story)

    record = Report(id=report_id, case_id=case.id, path=str(path), created_by=user.id, created_at=utcnow_iso())
    session.add(record)
    append_audit(
        session,
        actor_id=user.id,
        action="report.created",
        resource_type="report",
        resource_id=report_id,
        detail={"case_id": case.id, "job_id": job.id, "result_id": result.id},
    )
    session.commit()
    return record


def get_report(session: Session, user: User, report_id: str) -> Report:
    record = session.get(Report, report_id)
    if record is None:
        raise AppError(404, "report_not_found", "Report not found")
    case = session.get(Case, record.case_id)
    if case is None or not can_access_case(user, case):
        raise AppError(404, "report_not_found", "Report not found")
    return record
