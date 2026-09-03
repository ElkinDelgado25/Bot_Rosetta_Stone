"""Tests for the web API routes, without ever launching a browser."""

import pytest
from starlette.testclient import TestClient

from Resolucion_script_rosseta.presentacion.web.app import create_app
from Resolucion_script_rosseta.presentacion.web.profiles import ProfileStore


@pytest.fixture
def client(tmp_path, backend):
    store = ProfileStore(tmp_path / "profiles.json")
    app = create_app(store=store, state_dir=tmp_path / "state", backend=backend)
    with TestClient(app) as test_client:
        yield test_client


def _create(client, **overrides):
    """Create a profile the way the UI does: email and password only."""
    payload = {"email": "uno@example.com", "password": "s3cret"}
    payload.update(overrides)
    response = client.post("/api/profiles", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_creating_with_only_email_and_password_fills_the_defaults(client):
    created = _create(client)

    assert created["name"] == "uno"  # derived from the mailbox
    assert created["units_to_complete"] == []  # empty means "all"
    assert created["lessons_to_complete"] == []
    assert created["path_types_to_complete"] == []
    assert created["target_score_percent"] == 100
    assert created["display_name"] is None  # not known until a run reports it
    assert created["product"] is None


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
    client.patch(f"/api/profiles/{created['id']}", json={"email": "otro@example.com"})

    stored = ProfileStore(tmp_path / "profiles.json").get(created["id"])
    assert stored.email == "otro@example.com"
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


def test_run_endpoint_actually_launches(client):
    """Cubre el camino feliz por HTTP.

    Sin este test, un endpoint síncrono que programa una asyncio.Task pasa
    todos los tests de error (400/404/409) y solo falla en producción, donde
    FastAPI lo ejecuta en un hilo sin event loop. Se comprueba el efecto
    inmediato del lanzamiento, no la ejecución: la task aún no ha corrido.
    """
    created = _create(client)
    response = client.post(f"/api/profiles/{created['id']}/run", json={})

    assert response.status_code == 200
    run = response.json()["run"]
    assert run["mode"] == "run"
    assert run["status"] in ("queued", "running")


def test_verify_endpoint_launches_in_verify_mode(client):
    created = _create(client)
    response = client.post(f"/api/profiles/{created['id']}/verify", json={})

    assert response.status_code == 200
    run = response.json()["run"]
    assert run["mode"] == "verify"
    assert run["status"] in ("queued", "running")


def test_verify_without_a_password_is_rejected(client):
    created = _create(client, password=None)
    response = client.post(f"/api/profiles/{created['id']}/verify", json={})
    assert response.status_code == 400


def test_verify_on_an_unknown_profile_is_404(client):
    assert client.post("/api/profiles/nope/verify", json={}).status_code == 404


def test_pending_endpoint_launches_a_read_only_reconciliation(client):
    created = _create(client)
    response = client.post(f"/api/profiles/{created['id']}/pending", json={})

    assert response.status_code == 200
    run = response.json()["run"]
    assert run["mode"] == "pending"
    assert run["status"] in ("queued", "running")


def test_stories_endpoint_launches_an_hour_report(client):
    created = _create(client)
    response = client.post(f"/api/profiles/{created['id']}/stories", json={})

    assert response.status_code == 200
    run = response.json()["run"]
    assert run["mode"] == "stories"
    assert run["status"] in ("queued", "running")


def test_stories_without_a_password_is_rejected(client):
    created = _create(client, password=None)
    assert client.post(f"/api/profiles/{created['id']}/stories", json={}).status_code == 400


def test_stories_on_an_unknown_profile_is_404(client):
    assert client.post("/api/profiles/nope/stories", json={}).status_code == 404


def test_a_new_profile_starts_unverified(client):
    created = _create(client)
    assert created["product"] is None
    assert created["institution_selected"] is None


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
        json={"email": "u@e.com", "target_score_percent": 300},
    )
    assert response.status_code == 422


def test_email_is_still_required(client):
    assert client.post("/api/profiles", json={"password": "x"}).status_code == 422


def test_the_api_never_serves_a_raw_token(client, tmp_path):
    """Identifiers are public; the JWT and session token are not."""
    created = _create(client)
    jwt = "eyJhbGciOiJIUzI1NiJ9.cuerpo.firma98765"
    app_manager = client.app.state.manager
    app_manager.sessions.save(
        created["id"],
        {"authorization": jwt, "session_token": "tok-secreto-123", "school_id": "555"},
    )

    view = client.get("/api/profiles").json()["profiles"][0]["session"]
    assert view["school_id"] == "555"
    assert jwt not in view["authorization"]
    assert "tok-secreto-123" not in view["session_token"]


def test_deleting_a_profile_deletes_its_tokens(client):
    created = _create(client)
    manager = client.app.state.manager
    manager.sessions.save(created["id"], {"session_token": "tok", "user_id": "1"})

    client.delete(f"/api/profiles/{created['id']}")

    assert manager.sessions.load(created["id"]) == {}


def test_token_guards_the_api_when_configured(tmp_path, monkeypatch, backend):
    monkeypatch.setenv("ROSETTA_WEB_TOKEN", "clave-secreta")
    app = create_app(
        store=ProfileStore(tmp_path / "profiles.json"),
        state_dir=tmp_path / "state",
        backend=backend,
    )
    with TestClient(app) as client:
        assert client.get("/api/profiles").status_code == 401
        assert client.get("/api/profiles", headers={"X-Auth-Token": "mala"}).status_code == 401
        ok = client.get("/api/profiles", headers={"X-Auth-Token": "clave-secreta"})
        assert ok.status_code == 200
        # Health stays open so a container healthcheck needs no credentials.
        assert client.get("/api/health").status_code == 200

