from __future__ import annotations

import io
import traceback
from pathlib import Path

import numpy as np

DISCLAIMER = (
    "Decision support only. This report is not a diagnosis and must not replace "
    "review by a qualified clinician."
)
TB_NOTICE = (
    "MIAP does not screen for tuberculosis. A low or negative AI result does not "
    "exclude TB; use the local TB pathway."
)
COARSE_NOTE = (
    "This is coarse attention at a 14 by 14 patch level, not a fracture location. "
    "The model was trained on image-level captions, so treat the map as a hint."
)
TEMPLATE_VERSION = "4.0"
BAND_TEXT = {
    "above_threshold": "Worth reviewing",
    "borderline": "Borderline",
    "below_threshold": "Not flagged",
}
DECISION_TEXT = {
    "confirmed": "Agree",
    "dismissed": "Disagree",
}
PETROL = "#234f53"
MUTED = "#5a686b"
RULE = "#c9d3d2"
SIGNAL = "#b57b32"
INK = "#20292b"


def _palette():
    from reportlab.lib import colors

    return {
        "petrol": colors.HexColor(PETROL),
        "petrol_soft": colors.HexColor("#e8f0ef"),
        "muted": colors.HexColor(MUTED),
        "rule": colors.HexColor(RULE),
        "signal": colors.HexColor(SIGNAL),
        "ink": colors.HexColor(INK),
        "bad": colors.HexColor("#8a1c1c"),
        "white": colors.white,
    }


def styles():
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm

    base = getSampleStyleSheet()
    colour = _palette()
    return {
        "title": ParagraphStyle(
            "miapTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=colour["ink"],
            alignment=0,
            spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "miapSubtitle",
            parent=base["BodyText"],
            fontSize=9.5,
            leading=13,
            textColor=colour["muted"],
            spaceAfter=4,
        ),
        "heading": ParagraphStyle(
            "miapHeading",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11.5,
            leading=14,
            textColor=colour["petrol"],
            spaceBefore=7,
            spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "miapBody",
            parent=base["BodyText"],
            fontSize=9.5,
            leading=13,
            textColor=colour["ink"],
        ),
        "small": ParagraphStyle(
            "miapSmall",
            parent=base["BodyText"],
            fontSize=8.2,
            leading=10.5,
            textColor=colour["muted"],
        ),
        "meta": ParagraphStyle(
            "miapMeta",
            parent=base["BodyText"],
            fontSize=8.6,
            leading=10.8,
            textColor=colour["ink"],
        ),
        "warn": ParagraphStyle(
            "miapWarn",
            parent=base["BodyText"],
            fontSize=8.8,
            leading=11.5,
            textColor=colour["bad"],
        ),
        "mm": mm,
    }


def is_chest(document: dict) -> bool:
    region = str((document.get("region_or_view") or {}).get("value") or "").lower()
    modality = str((document.get("modality") or {}).get("value") or "").lower()
    return any(token in f"{region} {modality}" for token in ("chest", "thorax", "lung"))


def is_hip_pelvis(document: dict) -> bool:
    region = str((document.get("region_or_view") or {}).get("value") or "").lower()
    return any(token in region for token in ("hip", "pelvis", "pelvic", "femur", "femoral"))


def is_coarse_bone(document: dict) -> bool:
    model = str((document.get("model") or {}).get("name") or "").lower()
    region = str((document.get("region_or_view") or {}).get("value") or "").lower()
    return "siglip" in model or (not is_chest(document) and "bone" in region)


REGION_TEXT = {
    "bone_limb": "Limb bone",
    "bone_hip_pelvis": "Hip or pelvis",
    "mammogram_density": "Mammogram — breast density",
    "chest": "Chest",
    "hand": "Hand",
    "wrist": "Wrist",
    "knee": "Knee",
    "hip": "Hip",
    "pelvis": "Pelvis",
    "skull": "Skull",
}
MODALITY_TEXT = {
    "xray": "X-ray",
    "x-ray": "X-ray",
    "mammogram": "Mammogram",
    "ct": "CT",
    "mri": "MRI",
    "ultrasound": "Ultrasound",
}
CONSENT_TEXT = {
    "clinical": "Clinical use",
    "research": "Research use",
}


def display_region(value: str | None) -> str:
    text = str(value or "n/a")
    return REGION_TEXT.get(text.lower(), text.replace("_", " ").capitalize())


def display_modality(value: str | None) -> str:
    text = str(value or "n/a")
    return MODALITY_TEXT.get(text.lower(), text.replace("_", " ").capitalize())


def display_consent(value: str | None) -> str:
    text = str(value or "n/a")
    return CONSENT_TEXT.get(text.lower(), text.capitalize())


def relevant_warnings(document: dict) -> list[str]:
    """Drop generic warnings the report states once, and out-of-scope caveats."""
    keep: list[str] = []
    for warning in document.get("warnings", []):
        low = warning.lower()
        if low.startswith(("decision support only", "the heatmap shows", "model:")):
            continue
        if "hip and pelvis" in low and not is_hip_pelvis(document):
            continue
        keep.append(warning)
    return keep


def relevant_limitations(document: dict, card: dict) -> list[str]:
    keep: list[str] = []
    for limitation in card.get("limitations", []):
        low = limitation.lower()
        if low.startswith(("the heatmap shows", "decision support only", "model:")):
            continue
        if "hip" in low and "pelvis" in low and not is_hip_pelvis(document):
            continue
        keep.append(limitation)
    return keep


def format_stamp(value: str | None) -> str:
    if not value:
        return "—"
    from datetime import datetime

    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    local = moment.astimezone()
    return f"{local:%Y-%m-%d %H:%M} {local.tzname() or 'local'} · {moment:%H:%M} UTC"


def facts_table(rows: list[list[str]], styles, widths_mm: tuple[float, float] = (40, 130)) -> "object":
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Table, TableStyle

    colour = _palette()
    body = [
        [label, value if not isinstance(value, str) else Paragraph(value, styles["meta"])]
        for label, value in rows
    ]
    table = Table(body, colWidths=[width * mm for width in widths_mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 8.6),
                ("FONT", (1, 0), (1, -1), "Helvetica", 9.2),
                ("TEXTCOLOR", (0, 0), (0, -1), colour["muted"]),
                ("TEXTCOLOR", (1, 0), (1, -1), colour["ink"]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -2), 0.25, colour["rule"]),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def findings_table(rows: list[list[str]], widths_mm: list[float], head: list[str]) -> "object":
    from reportlab.lib.units import mm
    from reportlab.platypus import Table, TableStyle

    colour = _palette()
    table = Table(
        [head] + rows,
        colWidths=[width * mm for width in widths_mm],
        hAlign="LEFT",
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.4),
                ("FONT", (0, 1), (-1, -1), "Helvetica", 8.8),
                ("TEXTCOLOR", (0, 0), (-1, 0), colour["petrol"]),
                ("BACKGROUND", (0, 0), (-1, 0), colour["petrol_soft"]),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, colour["petrol"]),
                ("LINEBELOW", (0, 1), (-1, -1), 0.25, colour["rule"]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


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


def overlay_preview(image, data: bytes, heatmap_path: Path | None, mapping: str = "centre"):
    """Composite the CAM where the model input actually sits on the stored image."""
    from PIL import Image as PILImage

    from app.modules.ingestion.pixels import read_pixel_data

    array, meta = read_pixel_data(image, data)
    grey = _display_gray(array, meta)
    height, width = grey.shape
    base = PILImage.fromarray(np.repeat(grey[..., None], 3, axis=2), "RGB")
    if heatmap_path is None:
        return base

    if mapping == "full":
        left, top, span_x, span_y = 0, 0, width, height
    else:
        span_x = span_y = min(height, width)
        top = (height - span_y) // 2
        left = (width - span_x) // 2

    with PILImage.open(heatmap_path) as opened:
        heat = opened.convert("RGBA").resize((span_x, span_y), PILImage.Resampling.BILINEAR)

    base.paste(heat, (left, top), heat)
    return base


def _draw_annotations(image, annotations) -> bool:
    """Paint reviewer lasso polygons onto the preview; returns True if any drawn."""
    from PIL import Image as PILImage
    from PIL import ImageDraw

    width, height = image.size
    drew = False
    for polygon in annotations or []:
        points = [
            (float(x) * (width - 1), float(y) * (height - 1))
            for x, y in polygon
            if 0.0 <= float(x) <= 1.0 and 0.0 <= float(y) <= 1.0
        ]
        if len(points) < 3:
            continue
        layer = PILImage.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        draw.polygon(points, fill=(226, 169, 79, 60), outline=(181, 123, 50, 255), width=3)
        image.paste(layer, (0, 0), layer)
        drew = True
    return drew


def preview_flowables(
    document: dict,
    image,
    styles,
    *,
    caption: str,
    annotations=None,
) -> list:
    """Return the image preview plus caption, or nothing when neither is available."""
    from pathlib import Path

    from app.core.storage import read_blob, resolve_relative
    from reportlab.lib.units import mm
    from reportlab.platypus import Image as PdfImage
    from reportlab.platypus import Paragraph, Spacer

    heatmap = document.get("heatmap") or {}
    png = heatmap.get("overlay_png")
    path = resolve_relative(png) if png else None
    has_cam = path is not None and Path(path).exists()
    if not has_cam and not annotations:
        return []

    mapping = document.get("heatmap_mapping") or heatmap.get("mapping") or "centre"
    story = []
    preview = None
    if image is not None:
        try:
            preview = overlay_preview(
                image,
                read_blob(image.blob_digest),
                Path(path) if has_cam else None,
                mapping,
            )
        except Exception:  # noqa: BLE001 - the report must still render
            traceback.print_exc()

    if preview is not None:
        note = caption if has_cam else "Original image; no heatmap is stored for this result."
        if _draw_annotations(preview, annotations):
            note += (
                " Amber outlines were added by the reviewer to mark areas of interest;"
                " they are not model findings."
            )
        buffer = io.BytesIO()
        preview.save(buffer, format="PNG")
        buffer.seek(0)
        ratio = preview.height / preview.width
        width_mm, height_mm = 95.0, 95.0 * ratio
        if height_mm > 115.0:
            height_mm, width_mm = 115.0, 115.0 / ratio
        story.append(PdfImage(buffer, width=width_mm * mm, height=height_mm * mm))
        story.append(Paragraph(note, styles["small"]))
        story.append(Spacer(1, 2 * mm))
    elif has_cam:
        story.append(PdfImage(str(path), width=65 * mm, height=65 * mm))
        story.append(
            Paragraph(
                "Heatmap only, original image could not be rendered. " + caption,
                styles["small"],
            )
        )
        story.append(Spacer(1, 2 * mm))
    return story


def appendix(ctx: dict, style, report_id: str) -> list:
    """Technical and benchmark detail, kept out of the clinical body."""
    from reportlab.lib.units import mm
    from reportlab.platypus import CondPageBreak, Paragraph, Spacer

    document = ctx["document"]
    provenance = ctx.get("provenance") or {}
    parameters = provenance.get("parameters") or {}
    runtime = provenance.get("runtime") or {}
    card = ctx.get("card") or {}
    job = ctx["job"]
    model = document.get("model") or {}

    story = [
        CondPageBreak(100 * mm),
        Paragraph("Appendix — technical record", style["heading"]),
        Paragraph(
            "This appendix records how the result was produced. The stored JSON result "
            "is canonical; the report is a rendering of it.",
            style["small"],
        ),
        Spacer(1, 2 * mm),
    ]

    attention = " · ".join(
        str(value)
        for value in (parameters.get("cam_method"), parameters.get("gradcam_layer"))
        if value
    )
    rows = [
        ["Model", f"{model.get('name', 'n/a')} {model.get('version', '')}"],
        ["Model digest", (model.get("digest") or "n/a")[:32]],
        [
            "Capability",
            str(parameters.get("capability") or document.get("region_or_view", {}).get("value", "n/a")),
        ],
        ["Input size", str(parameters.get("input_size", "n/a"))],
        ["Preprocessing", str(parameters.get("normalisation", "n/a"))],
        ["Attention", attention or "n/a"],
        ["Seed", str(provenance.get("seed", "n/a"))],
        ["Runtime", f"{runtime.get('backend', 'n/a')} · Python {runtime.get('python', 'n/a')}"],
        ["Platform", str(runtime.get("platform", "n/a"))],
        ["Code commit", str(provenance.get("code_commit", "n/a"))],
        [
            "Analysis job",
            f"{job.id} · {job.state} · requested {format_stamp(job.created_at)}",
        ],
        ["Result", str(ctx["result"].id)],
        ["Provenance", str(document.get("provenance_id", "n/a"))],
        ["Requester", str(ctx.get("requester", {}).get("name", "n/a"))],
        ["Template", f"{TEMPLATE_VERSION} · report {report_id}"],
    ]
    story += [facts_table(rows, style), Spacer(1, 3 * mm)]

    prompts = parameters.get("prompts") or []
    if prompts:
        story.append(Paragraph("Model prompts", style["heading"]))
        story.append(
            findings_table(
                [[Paragraph(str(prompt), style["meta"])] for prompt in prompts],
                [170],
                ["Prompt"],
            )
        )
        story.append(Spacer(1, 3 * mm))

    if card.get("validation") or card.get("intended_use"):
        story.append(Paragraph("Model validation and intended use", style["heading"]))
        if card.get("intended_use"):
            story.append(Paragraph(str(card["intended_use"]), style["small"]))
        if card.get("validation"):
            story.append(Paragraph(str(card["validation"]), style["small"]))
    return story


def brand_page(canvas, doc, *, report_id: str, audience: str, generated: str) -> None:
    """Draw the MIAP mark, report identity and page footer on every page."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm

    colour = _palette()
    page_width, page_height = A4
    canvas.saveState()

    x, y = 25 * mm, page_height - 16 * mm
    canvas.setStrokeColor(colour["petrol"])
    canvas.setFillColor(colour["signal"])
    canvas.setLineWidth(1.4)
    canvas.circle(x, y, 4.1 * mm, stroke=1, fill=0)
    path = canvas.beginPath()
    path.moveTo(x - 2.6 * mm, y - 2.3 * mm)
    path.lineTo(x - 2.6 * mm, y + 2.2 * mm)
    path.lineTo(x, y - 0.8 * mm)
    path.lineTo(x + 2.6 * mm, y + 2.2 * mm)
    path.lineTo(x + 2.6 * mm, y - 2.3 * mm)
    canvas.drawPath(path, stroke=1, fill=0)
    canvas.circle(x, y - 1.0 * mm, 0.9 * mm, stroke=0, fill=1)

    canvas.setFillColor(colour["ink"])
    canvas.setFont("Helvetica-Bold", 12)
    canvas.drawString(33 * mm, page_height - 15 * mm, "MIAP")
    canvas.setFillColor(colour["muted"])
    canvas.setFont("Helvetica", 7)
    canvas.drawString(33 * mm, page_height - 18.6 * mm, "Medical imaging decision support")

    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colour["muted"])
    canvas.drawRightString(page_width - 20 * mm, page_height - 14.5 * mm, audience)
    canvas.drawRightString(page_width - 20 * mm, page_height - 18.2 * mm, generated)
    canvas.drawRightString(page_width - 20 * mm, page_height - 21.9 * mm, f"Report {report_id}")

    canvas.setStrokeColor(colour["rule"])
    canvas.setLineWidth(0.5)
    canvas.line(20 * mm, page_height - 24 * mm, page_width - 20 * mm, page_height - 24 * mm)

    canvas.line(20 * mm, 14 * mm, page_width - 20 * mm, 14 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colour["muted"])
    canvas.drawString(20 * mm, 9.5 * mm, "De-identified by default · Decision support only")
    canvas.drawRightString(page_width - 20 * mm, 9.5 * mm, f"Page {doc.page}")
    canvas.restoreState()
