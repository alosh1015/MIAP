from __future__ import annotations

from typing import Any

from app.core.errors import AppError
from app.modules.deid.service import read_metadata

MAMMOGRAM_MODALITIES = {"MG"}
XRAY_MODALITIES = {"DX", "CR", "RG", "PX"}

CHEST = {"CHEST", "THORAX", "RIBCAGE", "STERNUM", "LUNG"}
UPPER_LIMB = {
    "HAND",
    "WRIST",
    "FINGER",
    "FINGERS",
    "FOREARM",
    "ARM",
    "UPPER ARM",
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
    "TOES",
    "HEEL",
    "KNEE",
    "KNEE JOINT",
    "PATELLA",
    "LEG",
    "THIGH",
    "CALF",
    "SHIN",
    "LOWER EXTREMITY",
}
HIP_PELVIS = {"HIP", "PELVIS", "ACETABULUM", "FEMORAL NECK"}
UNSUPPORTED = {"SKULL", "HEAD", "SPINE", "CERVICAL", "THORACIC", "LUMBAR", "ABDOMEN", "RIB"}

BONE_LIMB = UPPER_LIMB | FRACTURE_LONG_BONE | {"LIMB", "EXTREMITY", "BONE", "LONG BONE"}

CAPABILITY = {
    "chest": {
        "area": "A",
        "task": "multi_finding_classification",
        "supported": True,
        "experimental": False,
    },
    "bone_limb": {
        "area": "B",
        "task": "normal_vs_abnormal",
        "supported": True,
        "experimental": False,
    },
    "bone_hip_pelvis": {
        "area": "C",
        "task": "fracture_detection",
        "supported": True,
        "experimental": True,
    },
    "mammogram_density": {
        "area": "D",
        "task": "breast_density_classification",
        "supported": True,
        "experimental": False,
    },
    "unsupported": {"area": None, "task": None, "supported": False, "experimental": False},
    "unrecognised": {"area": None, "task": None, "supported": False, "experimental": False},
}

LEGACY_REGIONS = {"upper_limb": "bone_limb", "fracture": "bone_limb"}
MODEL_PREFERENCE = {
    "chest": ["chest_densenet121", "stub_classifier"],
    "bone_limb": ["siglip_bone"],
    "bone_hip_pelvis": ["siglip_bone"],
    "mammogram_density": ["monai_density"],
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
        return {
            "value": override or "xray",
            "method": "manual" if override else "assumed",
            "confidence": 1.0 if override else 0.5,
        }
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
        area = LEGACY_REGIONS.get(area, area)
        if area in CAPABILITY:
            return {"value": area, "method": "manual", "confidence": 1.0}
        token = override.strip().upper()
        if token in CHEST:
            return {"value": "chest", "method": "manual", "confidence": 1.0}
        if token in BONE_LIMB:
            return {"value": "bone_limb", "method": "manual", "confidence": 1.0}
        if token in HIP_PELVIS:
            return {"value": "bone_hip_pelvis", "method": "manual", "confidence": 1.0}
        if token in UNSUPPORTED:
            return {"value": "unsupported", "method": "manual", "confidence": 1.0}
        return {"value": "unrecognised", "method": "manual", "confidence": 1.0}

    if not body_part:
        return {"value": "unrecognised", "method": "unresolved", "confidence": 0.0}

    token = body_part.strip().upper()
    if token in CHEST:
        return {"value": "chest", "method": "dicom_metadata", "confidence": 0.95}
    if token in BONE_LIMB:
        return {"value": "bone_limb", "method": "dicom_metadata", "confidence": 0.95}
    if token in HIP_PELVIS:
        return {"value": "bone_hip_pelvis", "method": "dicom_metadata", "confidence": 0.9}
    if token in UNSUPPORTED:
        return {"value": "unsupported", "method": "dicom_metadata", "confidence": 0.9}
    return {"value": "unrecognised", "method": "dicom_metadata", "confidence": 0.4}


def bucket_for(region: str | None, modality: str | None) -> str:
    if modality == "mammogram":
        return "mammogram_density"
    token = (region or "unrecognised").strip().lower().replace(" ", "_")
    token = LEGACY_REGIONS.get(token, token)
    return token if token in CAPABILITY else "unrecognised"


def capability_for(region: str | None, modality: str | None = None) -> dict[str, Any]:
    bucket = bucket_for(region, modality)
    return {**CAPABILITY[bucket], "bucket": bucket}


def resolve_model_for_image(
    session: Any,
    image: Any,
    model_id: str | None = None,
    model_version: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Pick an approved model for one image, or refuse with the missing capability."""
    from app.core.config import get_settings
    from app.modules.inference.service import select_model

    bucket = bucket_for(image.body_part, image.modality)
    if not CAPABILITY[bucket]["supported"]:
        raise AppError(
            409,
            "analysis_not_supported",
            "Analysis is not available for this study",
            f"capability: {bucket}",
        )

    if model_id:
        entry = select_model(model_id, model_version, session)
        if not entry_covers(entry, image, bucket):
            raise AppError(
                409,
                "model_scope_mismatch",
                "This model does not cover the study",
                f"capability: {bucket}",
            )
        return entry, bucket

    preference = list(MODEL_PREFERENCE.get(bucket, []))
    if bucket == "chest" and get_settings().model_backend == "stub":
        preference = ["stub_classifier", "chest_densenet121"]
    for candidate in preference:
        try:
            entry = select_model(candidate, None, session)
        except AppError:
            continue
        if entry_covers(entry, image, bucket):
            return entry, bucket

    raise AppError(
        409,
        "analysis_not_supported",
        "No approved model covers this study",
        f"capability: {bucket}",
    )


def entry_covers(entry: dict[str, Any], image: Any, bucket: str) -> bool:
    if image.modality not in entry.get("modalities", []):
        return False
    return bucket in entry.get("capabilities", entry.get("regions", []))


def is_degraded(entry: dict[str, Any], bucket: str) -> bool:
    return bucket in entry.get("degraded_capabilities", [])


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
