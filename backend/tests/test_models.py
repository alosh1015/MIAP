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
    assert models["stub_classifier"]["demo"] is True


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
