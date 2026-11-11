from __future__ import annotations

from reportlab.lib.units import mm
from reportlab.platypus import CondPageBreak, KeepTogether, Paragraph, Spacer

from .common import (
    BAND_TEXT,
    COARSE_NOTE,
    DISCLAIMER,
    TB_NOTICE,
    appendix,
    display_consent,
    display_modality,
    display_region,
    facts_table,
    findings_table,
    format_stamp,
    is_chest,
    is_coarse_bone,
    preview_flowables,
    relevant_limitations,
    relevant_warnings,
    styles,
)


def render(ctx: dict, report_id: str) -> list:
    style = styles()
    document = ctx["document"]
    case = ctx["case"]
    agreement = ctx.get("agreement") or {}
    card = ctx.get("card") or {}
    requester = ctx.get("requester") or {}

    story = [
        Paragraph("Research dataset report", style["title"]),
        Paragraph(
            f"<b>{case.pseudonym}</b> · {display_region(document['region_or_view']['value'])} · "
            f"{ctx['generated_at']}",
            style["subtitle"],
        ),
        Paragraph(
            "Pseudonymised research output. It contains no patient identity, no "
            "reviewer names and no clinical review notes; the pseudonym is the "
            "research key.",
            style["small"],
        ),
        Spacer(1, 4 * mm),
    ]

    facts = [
        ["Pseudonym", case.pseudonym],
        ["Consent", display_consent(case.consent)],
        ["Modality", display_modality(document["modality"]["value"])],
        ["Region / view", display_region(document["region_or_view"]["value"])],
        [
            "Requested by",
            f"{requester.get('name', 'n/a')} ({requester.get('role', 'n/a')}) · "
            f"{format_stamp(ctx['job'].created_at)}",
        ],
        ["Model", f"{document['model']['name']} {document['model']['version']}"],
    ]
    story += [facts_table(facts, style), Spacer(1, 4 * mm)]

    story.append(Paragraph("Model output", style["heading"]))
    story.append(
        Paragraph(
            "Scores are uncalibrated model outputs, not probabilities of disease. "
            "Bands are qualitative thresholds used for review triage; a row marked "
            "Not flagged is background output, not a finding.",
            style["small"],
        )
    )
    story.append(Spacer(1, 1.5 * mm))

    rows = []
    for finding in document.get("findings", []):
        score = float(finding.get("probability", 0.0))
        threshold = finding.get("threshold")
        band = finding.get("band")
        rows.append(
            [
                Paragraph(
                    str(finding.get("label", "")).replace("_", " "), style["meta"]
                ),
                f"{score:.3f}",
                f"{float(threshold):.2f}" if threshold is not None else "—",
                finding.get("band_label") or BAND_TEXT.get(band) or "—",
            ]
        )
    story.append(
        findings_table(rows, [76, 22, 24, 48], ["Finding", "Score", "Threshold", "Band"])
    )
    story.append(Spacer(1, 4 * mm))

    impression = document.get("impression") or {}
    if impression.get("text"):
        story += [
            Paragraph("Model impression", style["heading"]),
            Paragraph(impression["text"], style["body"]),
            Spacer(1, 4 * mm),
        ]

    confirmed = int(agreement.get("confirmed", 0))
    dismissed = int(agreement.get("dismissed", 0))
    unreviewed = int(agreement.get("not_reviewed", 0))
    story.append(
        Paragraph(
            f"Local clinician agreement: {confirmed} agree, {dismissed} disagree, "
            f"{unreviewed} not reviewed. This is review agreement on this dataset, "
            "not model accuracy. Reviewer names and notes are withheld from research "
            "reports.",
            style["small"],
        )
    )
    story.append(Spacer(1, 4 * mm))

    caption = (
        COARSE_NOTE
        if is_coarse_bone(document)
        else (
            "Area the model focused on, overlaid on the de-identified image. It shows "
            "where the model looked, not proof of a finding."
        )
    )
    story += preview_flowables(
        document,
        ctx.get("image"),
        style,
        caption=caption,
        annotations=ctx.get("annotations"),
    )

    notices = relevant_warnings(document)
    limitations = relevant_limitations(document, card)
    if is_chest(document):
        notices.insert(0, TB_NOTICE)
    caveats = _dedupe(notices + limitations)
    if caveats:
        block = [Paragraph("Warnings and limitations", style["heading"])]
        block += [
            Paragraph(f"- {item}", style["warn"] if item == TB_NOTICE else style["body"])
            for item in caveats
        ]
        story += [CondPageBreak(28 * mm), KeepTogether(block), Spacer(1, 3 * mm)]

    story += [Spacer(1, 4 * mm), Paragraph(DISCLAIMER, style["warn"])]
    story += appendix(ctx, style, report_id)
    return story


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = item.strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result
