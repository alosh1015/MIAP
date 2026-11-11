from __future__ import annotations

import copy

from app.modules.results.plain_language import UNCALIBRATED_NOTE
from app.modules.results.presenter import band_for, present_document


def _v1_document():
    return {
        "image_id": "img_test",
        "model": {"name": "stub_classifier", "version": "0.1", "demo": True},
        "findings": [
            {"label": "normal", "probability": 0.12},
            {"label": "Effusion", "probability": 0.71, "threshold": 0.6},
            {"label": "Nodule", "probability": 0.52},
        ],
        "heatmap": {"path": "heatmap.npy", "shape": [224, 224]},
        "warnings": ["not a diagnosis"],
    }


def test_v1_document_is_upgraded_on_read_without_mutating_the_source():
    stored = _v1_document()
    snapshot = copy.deepcopy(stored)

    presented = present_document(stored)

    assert stored == snapshot
    assert presented is not stored
    assert presented["document_version"] == 2
    assert presented["plain_language_note"] == UNCALIBRATED_NOTE
    assert [finding["index"] for finding in presented["findings"]] == [0, 1, 2]
    assert [finding["band"] for finding in presented["findings"]] == [
        "below_threshold",
        "above_threshold",
        "borderline",
    ]
    assert presented["findings"][1]["band_label"] == "Worth reviewing"
    assert presented["findings"][1]["plain_label"] == "fluid around the lung"
    assert "fluid around the lung" in presented["findings"][1]["plain_sentence"]
    assert presented["primary_finding_index"] == 1
    assert presented["review_summary"]["findings_to_review"] == 2


def test_bands_are_qualitative_and_use_a_margin():
    assert band_for(0.56, 0.5) == "above_threshold"
    assert band_for(0.55, 0.5) == "above_threshold"
    assert band_for(0.5, 0.5) == "borderline"
    assert band_for(0.45, 0.5) == "borderline"
    assert band_for(0.44, 0.5) == "below_threshold"
    assert band_for(0.8, None) == "above_threshold"


def test_heatmaps_and_reviews_are_attached_per_finding():
    presented = present_document(
        _v1_document(),
        heatmaps={1: {"format": "npy", "path": "heatmap_1.npy", "shape": [224, 224]}},
        reviews={
            1: {
                "finding_index": 1,
                "decision": "confirmed",
                "has_note": True,
                "note": "Correlate.",
                "reviewer_id": "user_x",
                "revision": 1,
                "updated_at": "2026-01-01T00:00:00Z",
            }
        },
    )
    assert "heatmap" not in presented["findings"][0]
    assert presented["findings"][1]["heatmap"]["path"] == "heatmap_1.npy"
    assert presented["findings"][1]["review"]["decision"] == "confirmed"
    assert presented["review_summary"]["confirmed"] == 1


def test_unknown_labels_get_a_readable_fallback():
    presented = present_document(
        {
            "findings": [{"label": "Rare_Pattern", "probability": 0.9}],
            "model": {"name": "stub_classifier", "version": "0.1"},
        }
    )
    assert presented["findings"][0]["plain_label"] == "rare pattern"


def test_impression_names_the_leading_condition():
    presented = present_document(_v1_document())
    impression = presented["impression"]
    assert impression["kind"] == "finding"
    assert impression["label"] == "Effusion"
    assert impression["band"] == "above_threshold"
    assert impression["text"] == (
        "Most likely pattern: Effusion (fluid around the lung)."
    )


def test_impression_admits_uncertainty_for_borderline_and_absence():
    borderline = present_document(
        {"findings": [{"label": "Nodule", "probability": 0.47}], "model": {"name": "m", "version": "1"}}
    )["impression"]
    assert borderline["kind"] == "finding"
    assert borderline["band"] == "borderline"
    assert borderline["text"].startswith("Possible pattern: Nodule")

    clear = present_document(
        {"findings": [{"label": "Nodule", "probability": 0.1}], "model": {"name": "m", "version": "1"}}
    )["impression"]
    assert clear["kind"] == "none"
    assert clear["label"] == "Nodule"
    assert clear["text"] == "No finding reached the review band. This does not exclude disease."


def test_impression_reports_breast_density_as_a_category():
    presented = present_document(
        {
            "classification": {"label": "C", "probability": 0.81},
            "density": "C",
            "findings": [{"label": label, "probability": 0.25} for label in "ABCD"],
            "model": {"name": "monai_density", "version": "0.1"},
        }
    )
    impression = presented["impression"]
    assert impression["kind"] == "density"
    assert impression["band"] is None
    assert impression["text"] == "Breast density category C: dense breast tissue."
