"""Tests for the per-profile session token storage."""

import json

from Resolucion_script_rosseta.presentacion.web.session_store import SessionStore

CAPTURED = {
    "authorization": "eyJhbGciOiJIUzI1NiJ9.payloadlargo.firma1234",
    "session_token": "abcdef0123456789abcdef",
    "school_id": "555",
    "user_id": "99887",
    "lang_code": "ENG",
    "product": "foundations",
    "user_name": "Elkin",  # not a session key: must not be stored
}


def test_save_keeps_only_the_session_keys(tmp_path):
    store = SessionStore(tmp_path)
    stored = store.save("perfil1", CAPTURED)

    assert "user_name" not in stored
    assert stored["school_id"] == "555"
    assert stored["captured_at"]

    on_disk = json.loads((tmp_path / "sessions" / "perfil1.json").read_text("utf-8"))
    assert on_disk["authorization"] == CAPTURED["authorization"]


def test_each_profile_gets_its_own_file(tmp_path):
    store = SessionStore(tmp_path)
    store.save("perfil1", CAPTURED)
    store.save("perfil2", {**CAPTURED, "user_id": "11111"})

    assert store.load("perfil1")["user_id"] == "99887"
    assert store.load("perfil2")["user_id"] == "11111"


def test_masked_hides_secrets_but_keeps_identifiers(tmp_path):
    store = SessionStore(tmp_path)
    store.save("perfil1", CAPTURED)

    view = store.masked("perfil1")
    assert view["school_id"] == "555"  # identifier, in the clear
    assert view["user_id"] == "99887"
    assert CAPTURED["authorization"] not in view["authorization"]
    assert CAPTURED["session_token"] not in view["session_token"]
    assert view["authorization"].startswith("eyJhbG")
    assert "…" in view["authorization"]


def test_saving_nothing_writes_nothing(tmp_path):
    store = SessionStore(tmp_path)
    assert store.save("perfil1", {}) == {}
    assert store.load("perfil1") == {}
    assert store.masked("perfil1") == {}


def test_delete_removes_the_credentials(tmp_path):
    store = SessionStore(tmp_path)
    store.save("perfil1", CAPTURED)
    store.delete("perfil1")

    assert store.load("perfil1") == {}
    store.delete("perfil1")  # deleting twice must not raise


def test_corrupt_file_reads_as_empty(tmp_path):
    store = SessionStore(tmp_path)
    store.save("perfil1", CAPTURED)
    (tmp_path / "sessions" / "perfil1.json").write_text("{roto", encoding="utf-8")

    assert store.load("perfil1") == {}

