from __future__ import annotations

from reportlab.lib.units import mm
from reportlab.platypus import CondPageBreak, KeepTogether, Paragraph, Spacer

from app.modules.patients.service import age_from_dob

from .common import (
    BAND_TEXT,
    COARSE_NOTE,
    DECISION_TEXT,
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

REVIEW_BANDS = {"above_threshold", "borderline"}


def render(ctx: dict, report_id: str) -> list:
    style = styles()
    document = ctx["document"]
    case = ctx["case"]
    identity = ctx.get("identity") or {}
    summary = ctx.get("summary") or {}
    card = ctx.get("card") or {}
    requester = ctx.get("requester") or {}

    story = [
        Paragraph("Clinical report", style["title"]),
        Paragraph(
            f"<b>{case.pseudonym}</b> · {display_region(document['region_or_view']['value'])} · "
            f"{ctx['generated_at']}",
            style["subtitle"],
        ),
    ]

    if identity:
        who = [
            ["Patient", identity.get("name") or "—"],
            ["Hospital number", identity.get("hospital_number") or "—"],
            ["Sex", str(identity.get("sex") or "unknown").capitalize()],
        ]
        age = age_from_dob(identity.get("dob"))
        details = []
        if age is not None:
            details.append(f"{age} years")
        if identity.get("dob"):
            details.append(f"DOB {identity['dob']}")
        who.append(["Age / DOB", " · ".join(details) or "—"])
        story += [
            facts_table(who, style),
            Spacer(1, 1.5 * mm),
            Paragraph(
                "Identity is included at your request. Reading it was written to the audit "
                "chain before this report was rendered.",
                style["small"],
            ),
            Spacer(1, 3 * mm),
        ]
    else:
        note = (
            "Patient identity was requested but is not linked to this study."
            if ctx.get("identity_requested")
            else "De-identified report. Patient identity is not included."
        )
        story += [Paragraph(note, style["small"]), Spacer(1, 3 * mm)]

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

    impression = document.get("impression") or {}
    if impression.get("text"):
        story += [
            Paragraph("Impression", style["heading"]),
            Paragraph(impression["text"], style["body"]),
            Spacer(1, 3 * mm),
        ]

    flagged = [
        finding for finding in document.get("findings", []) if finding.get("band") in REVIEW_BANDS
    ]
    if flagged:
        rows = []
        for finding in flagged:
            review = (ctx.get("reviews") or {}).get(int(finding.get("index", 0))) or {}
            decision = DECISION_TEXT.get(review.get("decision"), "Not reviewed")
            note = (review.get("note") or "").strip()
            rows.append(
                [
                    Paragraph(finding.get("plain_label") or finding.get("label", ""), style["meta"]),
                    BAND_TEXT.get(finding.get("band"), "—"),
                    Paragraph(
                        decision + (f"<br/><i>{_escape(note)}</i>" if note else ""),
                        style["meta"],
                    ),
                    review.get("reviewer_name") or "—",
                    format_stamp(review.get("updated_at")) if review else "—",
                ]
            )
        block = [
            Paragraph("Findings to review", style["heading"]),
            Paragraph(
                "Bands are qualitative and uncalibrated; they prompt review and are not a "
                "probability of disease.",
                style["small"],
            ),
            Spacer(1, 1.5 * mm),
            findings_table(
                rows,
                [51, 24, 22, 34, 39],
                ["Finding", "Band", "Decision", "Reviewer", "Reviewed"],
            ),
        ]
        story += [CondPageBreak(40 * mm), KeepTogether(block), Spacer(1, 3 * mm)]
    else:
        story += [
            CondPageBreak(25 * mm),
            Paragraph("Findings to review", style["heading"]),
            Paragraph(
                "No finding reached the review band. This does not exclude disease.",
                style["body"],
            ),
            Spacer(1, 3 * mm),
        ]

    if summary.get("findings_to_review", 0):
        story.append(
            Paragraph(
                f"{summary.get('reviewed', 0)} of "
                f"{summary.get('findings_to_review', 0)} flagged findings reviewed "
                f"({summary.get('confirmed', 0)} agree, "
                f"{summary.get('dismissed', 0)} disagree).",
                style["small"],
            )
        )
        story.append(Spacer(1, 3 * mm))

    caption = (
        COARSE_NOTE
        if is_coarse_bone(document)
        else (
            "Area the model focused on, overlaid on the de-identified image. It shows where "
            "the model looked, not proof of disease."
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
        block = [Paragraph("Caveats", style["heading"])]
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


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
