"""Tests for the web API routes, without ever launching a browser."""

import pytest
from starlette.testclient import TestClient

from rosseta_stone_script_a.presentation.web.app import create_app
from rosseta_stone_script_a.presentation.web.profiles import ProfileStore


@pytest.fixture
def client(tmp_path):
    store = ProfileStore(tmp_path / "profiles.json")
    app = create_app(store=store, state_dir=tmp_path / "state")
    with TestClient(app) as test_client:
        yield test_client


def _create(client, **overrides):
    payload = {"name": "Usuario 1", "email": "uno@example.com", "password": "s3cret"}
    payload.update(overrides)
    response = client.post("/api/profiles", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_health_reports_profile_count(client):
    assert client.get("/api/health").json()["profiles"] == 0
    _create(client)
    assert client.get("/api/health").json()["profiles"] == 1


def test_create_and_list_never_leak_the_password(client):
    created = _create(client)
    assert "password" not in created
    assert created["has_password"] is True

    listed = client.get("/api/profiles").json()["profiles"]
    assert len(listed) == 1
    assert "password" not in listed[0]
    assert listed[0]["run"]["status"] == "idle"
    assert listed[0]["progress"]["total_done"] == 0


def test_patch_leaves_an_omitted_password_alone(client, tmp_path):
    created = _create(client)
    client.patch(f"/api/profiles/{created['id']}", json={"name": "Renombrado"})

    stored = ProfileStore(tmp_path / "profiles.json").get(created["id"])
    assert stored.name == "Renombrado"
    assert stored.password == "s3cret"


def test_patch_with_empty_password_clears_it(client, tmp_path):
    created = _create(client)
    client.patch(f"/api/profiles/{created['id']}", json={"password": ""})

    stored = ProfileStore(tmp_path / "profiles.json").get(created["id"])
    assert stored.password is None


def test_run_without_any_password_is_rejected(client):
    created = _create(client, password=None)
    response = client.post(f"/api/profiles/{created['id']}/run", json={})
    assert response.status_code == 400
    assert "contrasena" in response.json()["detail"]


def test_unknown_profile_is_404(client):
    assert client.get("/api/profiles/nope/logs").status_code == 404
    assert client.post("/api/profiles/nope/run", json={}).status_code == 404
    assert client.delete("/api/profiles/nope").status_code == 404


def test_stop_without_a_run_is_409(client):
    created = _create(client)
    response = client.post(f"/api/profiles/{created['id']}/stop")
    assert response.status_code == 409


def test_logs_start_empty(client):
    created = _create(client)
    body = client.get(f"/api/profiles/{created['id']}/logs").json()
    assert body == {"lines": [], "cursor": 0, "status": "idle", "error": None}


def test_invalid_score_is_rejected(client):
    response = client.post(
        "/api/profiles",
        json={"name": "U", "email": "u@e.com", "target_score_percent": 300},
    )
    assert response.status_code == 422


def test_token_guards_the_api_when_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("ROSETTA_WEB_TOKEN", "clave-secreta")
    app = create_app(
        store=ProfileStore(tmp_path / "profiles.json"), state_dir=tmp_path / "state"
    )
    with TestClient(app) as client:
        assert client.get("/api/profiles").status_code == 401
        assert client.get("/api/profiles", headers={"X-Auth-Token": "mala"}).status_code == 401
        ok = client.get("/api/profiles", headers={"X-Auth-Token": "clave-secreta"})
        assert ok.status_code == 200
        # Health stays open so a container healthcheck needs no credentials.
        assert client.get("/api/health").status_code == 200
