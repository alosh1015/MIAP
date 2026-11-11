"""Plain-language mapping for findings.

The UI and the PDFs both read these strings from the server so a clinician never
sees raw model jargon and the two outputs cannot drift apart. Probabilities are
deliberately absent: they are uncalibrated and would imply false precision.
"""

from __future__ import annotations

PLAIN_LABELS: dict[str, str] = {
    "Atelectasis": "collapsed lung tissue",
    "Cardiomegaly": "an enlarged heart shadow",
    "Consolidation": "a dense patch in the lung",
    "Edema": "fluid in the lungs",
    "Effusion": "fluid around the lung",
    "Emphysema": "over-inflated lung tissue",
    "Fibrosis": "scarring in the lung",
    "Hernia": "bowel pushing through the diaphragm",
    "Infiltration": "cloudy lung tissue",
    "Mass": "a larger solid-looking area",
    "Nodule": "a small round shadow",
    "Pleural_Thickening": "a thickened lining around the lung",
    "Pneumonia": "an infection-like patch in the lung",
    "Pneumothorax": "air around the lung",
    "Fracture": "a bone break",
    "Lung Lesion": "an abnormal area in the lung",
    "Lung Opacity": "a cloudy patch in the lung",
    "Enlarged Cardiomediastinum": "a widened central chest shadow",
    "normal": "no standout pattern",
    "abnormal": "an unusual pattern",
    "A": "mostly fatty breast tissue",
    "B": "scattered dense breast tissue",
    "C": "dense breast tissue",
    "D": "very dense breast tissue",
}

BAND_LABELS: dict[str, str] = {
    "above_threshold": "Worth reviewing",
    "borderline": "Borderline",
    "below_threshold": "Not flagged",
}

UNCALIBRATED_NOTE = (
    "These are screening hints from a model that has not been calibrated on local "
    "patients. They are not probabilities of disease."
)


def plain_label(label: str) -> str:
    return PLAIN_LABELS.get(label, label.replace("_", " ").lower())


def plain_sentence(label: str, band: str) -> str:
    phrase = plain_label(label)
    token = label.strip().lower()
    if token == "normal":
        return "The model did not flag an abnormality in this image."
    if token == "abnormal":
        if band == "above_threshold":
            return "The model flagged an unusual pattern. A clinician should review this image."
        if band == "borderline":
            return "The model saw a weak signal for an unusual pattern. This needs clinical judgement."
        return "The model did not flag an abnormal pattern in this image."
    if band == "above_threshold":
        return f"The model marked changes that can be seen with {phrase}. A clinician should check this area."
    if band == "borderline":
        return f"The model saw a weak signal for {phrase}. This is uncertain and needs clinical judgement."
    return f"The model did not mark {phrase} in this image."
