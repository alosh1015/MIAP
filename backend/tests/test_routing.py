from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.errors import AppError
from app.modules.routing.service import (
    capability_for,
    classify_modality,
    classify_region,
    group_mammogram_views,
    normalise_laterality,
    normalise_view,
    resolve_model_for_image,
)


@pytest.mark.parametrize(
    "tag,expected",
    [("MG", "mammogram"), ("DX", "xray"), ("CR", "xray"), ("US", "unknown")],
)
def test_modality_from_dicom_tag(tag, expected):
    assert classify_modality(tag, None, has_dicom=True)["value"] == expected


def test_manual_modality_override_wins():
    result = classify_modality("DX", "mammogram", has_dicom=True)
    assert result == {"value": "mammogram", "method": "manual", "confidence": 1.0}


def test_raster_defaults_to_xray_with_low_confidence():
    result = classify_modality(None, None, has_dicom=False)
    assert result["value"] == "xray"
    assert result["method"] == "assumed"
    assert result["confidence"] == 0.5


def test_region_chest_is_supported():
    assert classify_region("CHEST", "xray", "PA", None, None)["value"] == "chest"
    assert capability_for("chest")["supported"] is True


@pytest.mark.parametrize(
    "body_part,region,supported",
    [
        ("HAND", "bone_limb", True),
        ("FEMUR", "bone_limb", True),
        ("HIP", "bone_hip_pelvis", True),
        ("SKULL", "unsupported", False),
    ],
)
def test_region_groups(body_part, region, supported):
    result = classify_region(body_part, "xray", None, None, None)
    assert result["value"] == region
    assert capability_for(region)["supported"] is supported


def test_mammogram_bucket_needs_modality():
    assert capability_for("LCC")["supported"] is False
    assert capability_for("LCC", "mammogram")["bucket"] == "mammogram_density"
    assert capability_for("LCC", "mammogram")["supported"] is True


def test_hip_pelvis_is_experimental():
    assert capability_for("bone_hip_pelvis")["experimental"] is True
    assert capability_for("bone_limb")["experimental"] is False


@pytest.mark.parametrize(
    "typed,region",
    [
        ("knee", "bone_limb"),
        ("wrist", "bone_limb"),
        ("limb", "bone_limb"),
        ("upper arm", "bone_limb"),
        ("pelvis", "bone_hip_pelvis"),
        ("chest", "chest"),
        ("spine", "unsupported"),
        ("something else", "unrecognised"),
    ],
)
def test_manual_body_part_override_accepts_anatomy(typed, region):
    result = classify_region(None, "xray", None, None, typed)
    assert result["value"] == region
    assert result["method"] == "manual"


def _fake_image(modality: str, body_part: str | None):
    return SimpleNamespace(modality=modality, body_part=body_part)


def test_chest_resolves_to_the_stub_under_the_stub_backend():
    entry, bucket = resolve_model_for_image(None, _fake_image("xray", "chest"))
    assert entry["model_id"] == "stub_classifier"
    assert bucket == "chest"


def test_unsupported_region_is_refused_with_its_bucket():
    with pytest.raises(AppError) as caught:
        resolve_model_for_image(None, _fake_image("xray", "unsupported"))
    assert caught.value.status == 409
    assert caught.value.code == "analysis_not_supported"
    assert caught.value.detail == "capability: unsupported"


def test_mammogram_without_an_approved_model_names_the_bucket():
    with pytest.raises(AppError) as caught:
        resolve_model_for_image(None, _fake_image("mammogram", "LCC"))
    assert caught.value.status == 409
    assert caught.value.detail == "capability: mammogram_density"


def test_explicit_model_outside_the_capability_is_refused():
    with pytest.raises(AppError) as caught:
        resolve_model_for_image(None, _fake_image("xray", "bone_limb"), "stub_classifier")
    assert caught.value.status == 409
    assert caught.value.code == "model_scope_mismatch"


def test_unrecognised_region_has_no_capability():
    result = classify_region("PELVIS_LEFT", "xray", None, None, None)
    assert result["value"] == "unrecognised"
    assert capability_for("unrecognised")["supported"] is False


def test_laterality_and_view_normalisation():
    assert normalise_laterality("left") == "L"
    assert normalise_laterality("R") == "R"
    assert normalise_laterality("bilateral") is None
    assert normalise_view("CC") == "CC"
    assert normalise_view("l-mlo") == "MLO"
    assert normalise_view("XCCL") is None


def _image(image_id, laterality, view):
    return {"id": image_id, "laterality": laterality, "view": view}


def test_four_view_exam_is_complete():
    images = [
        _image("i1", "L", "CC"),
        _image("i2", "R", "CC"),
        _image("i3", "L", "MLO"),
        _image("i4", "R", "MLO"),
    ]
    group = group_mammogram_views(images)
    assert group["complete"] is True
    assert group["missing"] == []
    assert group["layout"]["top_left"]["id"] == "i1"
    assert group["layout"]["bottom_right"]["id"] == "i4"


def test_three_view_exam_reports_the_missing_view():
    images = [_image("i1", "L", "CC"), _image("i2", "R", "CC"), _image("i3", "L", "MLO")]
    group = group_mammogram_views(images)
    assert group["complete"] is False
    assert group["missing"] == ["RMLO"]
    assert group["layout"]["bottom_right"] is None


def test_duplicate_view_is_flagged_not_overwritten():
    images = [
        _image("i1", "L", "CC"),
        _image("i2", "L", "CC"),
        _image("i3", "R", "CC"),
        _image("i4", "L", "MLO"),
        _image("i5", "R", "MLO"),
    ]
    group = group_mammogram_views(images)
    assert group["duplicates"] == ["LCC"]
    assert group["layout"]["top_left"]["id"] == "i1"
    assert group["complete"] is False


def test_image_without_metadata_is_unassigned():
    group = group_mammogram_views([_image("i1", None, "CC"), _image("i2", "L", None)])
    assert group["unassigned"] == ["i1", "i2"]
    assert len(group["missing"]) == 4
