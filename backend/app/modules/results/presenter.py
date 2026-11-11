"""Read-time presentation of stored result documents.

Stored documents are immutable. Older documents (v1) have no index, band, or
plain-language fields, so the presenter derives them on every read. That keeps
the worker's output stable while the UI and PDFs share one mapping.
"""

from __future__ import annotations

import copy
from typing import Any

from app.modules.results.plain_language import (
    BAND_LABELS,
    UNCALIBRATED_NOTE,
    plain_label,
    plain_sentence,
)

DEFAULT_THRESHOLD = 0.5
BAND_MARGIN = 0.05
DENSITY_LABELS = {"A", "B", "C", "D"}
FLAGGED_BANDS = {"above_threshold", "borderline"}
NON_LOCALISABLE = {"normal", "no finding", "none"}
NO_FINDING_TEXT = "No finding reached the review band. This does not exclude disease."


def band_for(probability: float, threshold: float | None) -> str:
    limit = DEFAULT_THRESHOLD if threshold is None else float(threshold)
    if probability >= limit + BAND_MARGIN:
        return "above_threshold"
    if probability >= limit - BAND_MARGIN:
        return "borderline"
    return "below_threshold"


def is_localisable(label: str) -> bool:
    return label.strip().lower() not in NON_LOCALISABLE


def is_flagged(finding: dict[str, Any]) -> bool:
    return finding.get("band") in FLAGGED_BANDS and is_localisable(str(finding.get("label", "")))


def _primary_index(findings: list[dict[str, Any]]) -> int | None:
    if not findings:
        return None
    flagged = [finding for finding in findings if is_flagged(finding)]
    if not flagged:
        return None
    return max(flagged, key=lambda finding: float(finding.get("probability", 0.0)))["index"]


def present_document(
    document: dict[str, Any],
    *,
    heatmaps: dict[int, dict[str, Any]] | None = None,
    reviews: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a v2 view of a stored document without touching the stored copy."""
    payload = copy.deepcopy(document)
    presented: list[dict[str, Any]] = []
    for index, finding in enumerate(payload.get("findings", [])):
        label = str(finding.get("label", ""))
        probability = float(finding.get("probability", 0.0))
        threshold = finding.get("threshold")
        # A reference class is not an abnormality, even when its probability is high.
        band = band_for(probability, threshold) if is_localisable(label) else "below_threshold"
        entry = dict(finding)
        entry.update(
            {
                "index": index,
                "threshold": DEFAULT_THRESHOLD if threshold is None else float(threshold),
                "band": band,
                "band_label": BAND_LABELS[band],
                "plain_label": plain_label(label),
                "plain_sentence": plain_sentence(label, band),
            }
        )
        heatmap = (heatmaps or {}).get(index)
        if heatmap and is_flagged(entry):
            entry["heatmap"] = heatmap
        review = (reviews or {}).get(index)
        if review:
            entry["review"] = review
        presented.append(entry)

    payload["findings"] = presented
    payload["document_version"] = 2
    payload["primary_finding_index"] = _primary_index(presented)
    payload["impression"] = _impression(presented, payload.get("classification") or {}, payload.get("density"))
    payload["plain_language_note"] = UNCALIBRATED_NOTE
    payload["review_summary"] = _review_summary(presented, reviews or {})
    top = str((payload.get("classification") or {}).get("label") or "")
    top_finding = next((item for item in presented if item.get("label") == top), None)
    if not payload.get("heatmap") or top_finding is None or not is_flagged(top_finding):
        payload["heatmap"] = None
    elif "mapping" not in payload["heatmap"]:
        payload["heatmap"]["mapping"] = "centre"
    return payload


def _impression(
    findings: list[dict[str, Any]],
    classification: dict[str, Any],
    density: str | None,
) -> dict[str, Any]:
    """The plain answer to "what might this be", derived from the leading finding."""
    label = str(classification.get("label") or "")
    probability = float(classification.get("probability") or 0.0)
    if density or (label in DENSITY_LABELS and findings and all(item["label"] in DENSITY_LABELS for item in findings)):
        phrase = plain_label(label or str(density))
        return {
            "kind": "density",
            "label": label or str(density),
            "plain_label": phrase,
            "band": None,
            "band_label": None,
            "probability": probability,
            "text": f"Breast density category {label or density}: {phrase}.",
        }

    flagged = [item for item in findings if is_flagged(item)]
    if not flagged:
        leading = max(findings, key=lambda item: float(item.get("probability", 0.0)), default=None)
        fallback = leading.get("label") if leading else None
        return {
            "kind": "none",
            "label": label or fallback,
            "plain_label": None,
            "band": None,
            "band_label": None,
            "probability": probability or None,
            "text": NO_FINDING_TEXT,
        }

    top = max(flagged, key=lambda item: float(item.get("probability", 0.0)))
    token = str(top.get("label", "")).strip().lower()
    if token == "abnormal":
        text = (
            "The model flagged an unusual pattern in this image. A clinician should review it."
            if top["band"] == "above_threshold"
            else "The model saw a weak signal for an unusual pattern. This needs clinical judgement."
        )
        return {
            "kind": "finding",
            "label": top.get("label"),
            "plain_label": top["plain_label"],
            "band": top["band"],
            "band_label": top["band_label"],
            "probability": float(top.get("probability", 0.0)),
            "text": text,
        }

    name = str(top.get("label", "")).replace("_", " ").strip()
    phrase = top["plain_label"]
    if top["band"] == "above_threshold":
        text = f"Most likely pattern: {name} ({phrase})."
    else:
        text = f"Possible pattern: {name} ({phrase}). The signal is weak and needs clinical judgement."
    return {
        "kind": "finding",
        "label": top.get("label"),
        "plain_label": phrase,
        "band": top["band"],
        "band_label": top["band_label"],
        "probability": float(top.get("probability", 0.0)),
        "text": text,
    }


def _review_summary(findings: list[dict[str, Any]], reviews: dict[int, dict[str, Any]]) -> dict[str, Any]:
    flagged = [finding for finding in findings if is_flagged(finding)]
    decisions = [reviews[finding["index"]]["decision"] for finding in findings if finding["index"] in reviews]
    return {
        "findings_to_review": len(flagged),
        "reviewed": len(decisions),
        "confirmed": sum(1 for decision in decisions if decision == "confirmed"),
        "dismissed": sum(1 for decision in decisions if decision == "dismissed"),
    }
