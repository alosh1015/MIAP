from __future__ import annotations

import json
import uuid

from app.core.config import get_settings
from app.modules.models.router import load_registry, seed_models
from tests.conftest import API

REQUIRED_KEYS = {
    "model_id",
    "version",
    "digest",
    "state",
    "task",
    "modalities",
    "regions",
    "capabilities",
    "demo",
    "validated_locally",
    "preprocess_profile",
    "input",
    "cam",
    "licence",
    "source",
    "metrics",
    "approval",
    "card",
}


def test_every_registry_entry_has_governance_metadata_and_a_card():
    entries = load_registry()
    assert {entry["model_id"] for entry in entries} >= {
        "chest_densenet121",
        "stub_classifier",
        "monai_density",
        "siglip_bone",
        "mammoscreen",
    }
    cards_dir = get_settings().registry_path.parent / "cards"
    for entry in entries:
        assert REQUIRED_KEYS <= set(entry), entry["model_id"]
        assert entry["licence"].get("spdx")
        assert entry["licence"].get("access_date") == "2026-11-10"
        assert isinstance(entry["input"], dict) and entry["input"]
        assert entry["cam"].get("method")
        assert entry["validated_locally"] is False
        assert (cards_dir / f"{entry['model_id']}.json").exists()
        card = entry["card"]
        assert card.get("intended_use")
        assert card.get("validation")
        assert card.get("limitations")


def test_mammoscreen_is_registered_as_an_unselectable_candidate():
    entry = next(item for item in load_registry() if item["model_id"] == "mammoscreen")
    assert entry["state"] == "candidate"
    assert entry["licence"]["spdx"] == "LicenseRef-Proprietary"
    assert entry["approval"]["benchmark_path"] is None


def test_model_api_exposes_licence_source_metrics_and_approval_history(client, auth):
    listed = client.get(f"{API}/models", headers=auth("researcher"))
    assert listed.status_code == 200, listed.text
    models = {item["model_id"]: item for item in listed.json()}
    assert "mammoscreen" in models
    monai = models["monai_density"]
    assert monai["state"] in {"candidate", "approved", "rejected", "revoked"}
    assert monai["licence"]["name"].startswith("MONAI")
    assert "Project-MONAI" in monai["source"]["repo"] or "MONAI/breast_density" in monai["source"]["repo"]
    assert monai["input"]["size"] == [299, 299]
    assert monai["cam"]["target_layer"] == "Mixed_7c"
    assert monai["metrics"] == []
    assert monai["validated_locally"] is False
    assert isinstance(monai["approvals"], list)
    assert monai["card"]["intended_use"]


def test_approval_outranks_registry_and_survives_reseed(client, auth):
    models = {item["model_id"]: item for item in client.get(f"{API}/models", headers=auth("administrator")).json()}
    monai = models["monai_density"]

    approved = client.post(
        f"{API}/models/monai_density/{monai['version']}/approve",
        json={"note": "Benchmark reviewed locally.", "benchmark_digest": "a" * 64},
        headers=auth("administrator"),
    )
    assert approved.status_code == 200, approved.text

    after = {
        item["model_id"]: item
        for item in client.get(f"{API}/models", headers=auth("administrator")).json()
    }["monai_density"]
    assert after["state"] == "approved"
    assert after["state_source"] == "approval"
    assert after["approved_at"]
    assert after["approvals"][0]["decision"] == "approved"
    assert after["approvals"][0]["benchmark_digest"] == "a" * 64

    from app.core.db import SessionLocal

    assert SessionLocal is not None
    with SessionLocal() as session:
        seed_models(session)
    reseeded = {
        item["model_id"]: item
        for item in client.get(f"{API}/models", headers=auth("administrator")).json()
    }["monai_density"]
    assert reseeded["state"] == "approved"
    assert reseeded["state_source"] == "approval"

    revoked = client.post(
        f"{API}/models/monai_density/{monai['version']}/revoke",
        json={"note": "Local review found the benchmark insufficient."},
        headers=auth("administrator"),
    )
    assert revoked.status_code == 200, revoked.text
    final = {
        item["model_id"]: item
        for item in client.get(f"{API}/models", headers=auth("administrator")).json()
    }["monai_density"]
    assert final["state"] == "revoked"
    assert len(final["approvals"]) == 2


def test_candidate_model_is_refused_for_analysis(client, auth, chest_image):
    case_id, image = chest_image()
    response = client.post(
        f"{API}/analyses",
        json={
            "case_id": case_id,
            "image_id": image["id"],
            "model_id": "mammoscreen",
            "model_version": "vendor",
        },
        headers={**auth("clinician"), "Idempotency-Key": uuid.uuid4().hex},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "model_not_approved"


def test_registry_json_is_valid_json():
    payload = json.loads(get_settings().registry_path.read_text(encoding="utf-8"))
    assert payload["models"]
