from __future__ import annotations

from tests.conftest import API


def test_models_list_includes_cards(client, auth):
    response = client.get(f"{API}/models", headers=auth("clinician"))
    assert response.status_code == 200
    models = {model["model_id"]: model for model in response.json()}
    assert "chest_densenet121" in models
    chest = models["chest_densenet121"]
    assert chest["state"] == "approved"
    assert chest["digest"] and chest["digest"] != "pending"
    assert chest["card"]["limitations"]
    assert chest["demo"] is False
    assert "stub_classifier" not in models


def test_internal_router_models_are_not_listed(client, auth):
    listed = client.get(f"{API}/models", headers=auth("administrator")).json()
    assert all(model["model_id"] != "stub_classifier" for model in listed)
    assert client.get(f"{API}/models/stub_classifier", headers=auth("administrator")).status_code == 404

    health = client.get(f"{API}/system/health", headers=auth("administrator")).json()
    assert all(entry["model_id"] != "stub_classifier" for entry in health["models"]["versions"])


def test_model_detail_lists_versions(client, auth):
    response = client.get(f"{API}/models/chest_densenet121", headers=auth("researcher"))
    assert response.status_code == 200
    body = response.json()
    assert body["model_id"] == "chest_densenet121"
    assert body["versions"][0]["version"] == "xrv-0.1"


def test_unknown_model_is_404(client, auth):
    assert client.get(f"{API}/models/nope", headers=auth("clinician")).status_code == 404


def test_models_require_authentication(client):
    assert client.get(f"{API}/models").status_code == 401
