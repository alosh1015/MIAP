from __future__ import annotations

from typing import Any

from app.modules.deid.service import read_metadata

MAMMOGRAM_MODALITIES = {"MG"}
XRAY_MODALITIES = {"DX", "CR", "RG", "PX"}

CHEST = {"CHEST", "THORAX", "RIBCAGE", "STERNUM", "LUNG"}
UPPER_LIMB = {
    "HAND",
    "WRIST",
    "FINGER",
    "FOREARM",
    "HUMERUS",
    "ELBOW",
    "SHOULDER",
    "CLAVICLE",
    "UPPER EXTREMITY",
}
FRACTURE_LONG_BONE = {
    "FEMUR",
    "TIBIA",
    "FIBULA",
    "ANKLE",
    "FOOT",
    "TOE",
    "KNEE",
    "LEG",
    "LOWER EXTREMITY",
}
UNSUPPORTED = {"SKULL", "HEAD", "SPINE", "CERVICAL", "THORACIC", "LUMBAR", "PELVIS", "ABDOMEN", "RIB"}

CAPABILITY = {
    "chest": {"area": "A", "task": "multi_finding_classification", "supported": True},
    "upper_limb": {"area": "B", "task": "normal_vs_abnormal", "supported": False},
    "fracture": {"area": "C", "task": "fracture_detection", "supported": False},
    "unsupported": {"area": None, "task": None, "supported": False},
    "unrecognised": {"area": None, "task": None, "supported": False},
}

VIEWS = ("LCC", "LMLO", "RCC", "RMLO")


def normalise_laterality(value: str | None) -> str | None:
    if not value:
        return None
    token = value.strip().upper()
    if token in {"L", "LEFT"}:
        return "L"
    if token in {"R", "RIGHT"}:
        return "R"
    return None


def normalise_view(value: str | None) -> str | None:
    if not value:
        return None
    token = value.strip().upper().replace("-", "").replace(" ", "")
    if token in {"CC", "LCC", "RCC"}:
        return "CC"
    if token in {"MLO", "LMLO", "RMLO"}:
        return "MLO"
    return None


def classify_modality(
    modality_tag: str | None,
    override: str | None,
    *,
    has_dicom: bool,
) -> dict[str, Any]:
    if override in {"xray", "mammogram"}:
        return {"value": override, "method": "manual", "confidence": 1.0}
    if modality_tag:
        token = modality_tag.strip().upper()
        if token in MAMMOGRAM_MODALITIES:
            return {"value": "mammogram", "method": "dicom_metadata", "confidence": 0.99}
        if token in XRAY_MODALITIES:
            return {"value": "xray", "method": "dicom_metadata", "confidence": 0.99}
    if not has_dicom:
        return {"value": override or "xray", "method": "manual" if override else "assumed", "confidence": 0.5 if not override else 1.0}
    return {"value": "unknown", "method": "unresolved", "confidence": 0.0}


def classify_region(
    body_part: str | None,
    modality: str,
    view: str | None,
    laterality: str | None,
    override: str | None,
) -> dict[str, Any]:
    if modality == "mammogram":
        if laterality and view:
            return {
                "value": f"{laterality}{view}",
                "method": "dicom_metadata",
                "confidence": 0.98,
            }
        return {"value": "unknown", "method": "unresolved", "confidence": 0.0}

    if override:
        area = override.strip().lower().replace(" ", "_")
        if area in CAPABILITY:
            return {"value": area, "method": "manual", "confidence": 1.0}
        return {"value": "unrecognised", "method": "manual", "confidence": 1.0}

    if not body_part:
        return {"value": "unrecognised", "method": "unresolved", "confidence": 0.0}

    token = body_part.strip().upper()
    if token in CHEST:
        return {"value": "chest", "method": "dicom_metadata", "confidence": 0.95}
    if token in UPPER_LIMB:
        return {"value": "upper_limb", "method": "dicom_metadata", "confidence": 0.95}
    if token in FRACTURE_LONG_BONE:
        return {"value": "fracture", "method": "dicom_metadata", "confidence": 0.95}
    if token in UNSUPPORTED:
        return {"value": "unsupported", "method": "dicom_metadata", "confidence": 0.9}
    return {"value": "unrecognised", "method": "dicom_metadata", "confidence": 0.4}


def capability_for(region: str) -> dict[str, Any]:
    return CAPABILITY.get(region, CAPABILITY["unrecognised"])


def group_mammogram_views(images: list[dict[str, Any]]) -> dict[str, Any]:
    """Group a case's mammogram images into the four standard views."""
    slots: dict[str, dict[str, Any] | None] = {view: None for view in VIEWS}
    duplicates: list[str] = []
    unassigned: list[str] = []

    for image in images:
        laterality = normalise_laterality(image.get("laterality"))
        view = normalise_view(image.get("view"))
        if not laterality or not view:
            unassigned.append(image["id"])
            continue
        key = f"{laterality}{view}"
        if slots[key] is not None:
            duplicates.append(key)
        else:
            slots[key] = image

    missing = [view for view, slot in slots.items() if slot is None]
    complete = not missing and not duplicates
    return {
        "layout": {
            "top_left": slots["LCC"],
            "top_right": slots["RCC"],
            "bottom_left": slots["LMLO"],
            "bottom_right": slots["RMLO"],
        },
        "by_view": {view: slots[view] for view in VIEWS},
        "missing": missing,
        "duplicates": sorted(set(duplicates)),
        "unassigned": unassigned,
        "complete": complete,
    }


def metadata_from_dicom(dataset: Any) -> dict[str, Any]:
    return read_metadata(dataset)
