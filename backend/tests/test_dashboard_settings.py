from __future__ import annotations

from tests.conftest import API


def test_each_role_gets_a_distinct_dashboard(client, auth, new_case):
    new_case("clinician")
    clinician = client.get(f"{API}/dashboard", headers=auth("clinician"))
    assert clinician.status_code == 200
    body = clinician.json()
    assert body["role"] == "clinician"
    assert "patients" in body and "recent_cases" in body
    assert body["notices"] and "tuberculosis" in body["notices"][0].lower()

    researcher = client.get(f"{API}/dashboard", headers=auth("researcher")).json()
    assert researcher["role"] == "researcher"
    assert "datasets" in researcher and "recent_cases" not in researcher
    assert researcher["compute_warning"]

    admin = client.get(f"{API}/dashboard", headers=auth("administrator")).json()
    assert admin["role"] == "administrator"
    assert admin["audit"]["ok"] is True
    assert "recent_cases" not in admin
    assert "patients" not in admin


def test_dashboard_requires_authentication(client):
    assert client.get(f"{API}/dashboard").status_code == 401


def test_settings_expose_server_side_capabilities(client, auth):
    clinician = client.get(f"{API}/settings/me", headers=auth("clinician")).json()
    assert clinician["capabilities"]["can_see_identity"] is True
    assert clinician["capabilities"]["can_manage_users"] is False

    researcher = client.get(f"{API}/settings/me", headers=auth("researcher")).json()
    assert researcher["capabilities"]["can_see_identity"] is False
    assert researcher["capabilities"]["can_export_dataset"] is True

    admin = client.get(f"{API}/settings/me", headers=auth("administrator")).json()
    assert admin["capabilities"]["can_view_images"] is False
    assert admin["capabilities"]["can_manage_retention"] is True


def test_theme_preference_round_trips(client, auth):
    updated = client.patch(
        f"{API}/settings/me", json={"theme": "dark", "viewer_overlay_opacity": 0.6}, headers=auth("researcher")
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["preferences"]["theme"] == "dark"
    fetched = client.get(f"{API}/settings/me", headers=auth("researcher")).json()
    assert fetched["preferences"]["theme"] == "dark"
    assert fetched["viewer_defaults"]["overlay_opacity"] == 0.6


def test_only_administrators_change_system_settings(client, auth):
    forbidden = client.patch(
        f"{API}/settings/system", json={"export_row_cap": 10}, headers=auth("clinician")
    )
    assert forbidden.status_code == 403

    updated = client.patch(
        f"{API}/settings/system", json={"export_row_cap": 1234}, headers=auth("administrator")
    )
    assert updated.status_code == 200
    assert updated.json()["export_row_cap"] == 1234
