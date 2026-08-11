"""Tests for the per-user profile store."""

import json

from rosseta_stone_script_a.presentation.web.profiles import Profile, ProfileStore


def _store(tmp_path):
    return ProfileStore(tmp_path / "profiles.json")


def test_create_assigns_id_and_persists(tmp_path):
    store = _store(tmp_path)
    profile = store.create(name="Usuario 1", email="uno@example.com", password="s3cret")

    assert profile.id
    reloaded = ProfileStore(tmp_path / "profiles.json")
    assert [p.email for p in reloaded.list()] == ["uno@example.com"]
    assert reloaded.get(profile.id).password == "s3cret"


def test_public_dict_hides_the_password(tmp_path):
    store = _store(tmp_path)
    profile = store.create(name="Usuario 1", email="uno@example.com", password="s3cret")

    view = profile.public_dict()
    assert "password" not in view
    assert view["has_password"] is True

    without = store.create(name="Usuario 2", email="dos@example.com")
    assert without.public_dict()["has_password"] is False


def test_update_ignores_unknown_fields_and_id(tmp_path):
    store = _store(tmp_path)
    profile = store.create(name="Usuario 1", email="uno@example.com")

    store.update(profile.id, name="Renombrado", id="hackeado", bogus="x")

    updated = store.get(profile.id)
    assert updated.name == "Renombrado"
    assert updated.id == profile.id
    assert not hasattr(updated, "bogus")


def test_delete_removes_from_disk(tmp_path):
    store = _store(tmp_path)
    profile = store.create(name="Usuario 1", email="uno@example.com")

    assert store.delete(profile.id) is True
    assert store.delete(profile.id) is False
    assert ProfileStore(tmp_path / "profiles.json").list() == []


def test_corrupt_file_starts_empty_instead_of_crashing(tmp_path):
    path = tmp_path / "profiles.json"
    path.write_text("{no es json", encoding="utf-8")

    assert ProfileStore(path).list() == []


def test_unknown_keys_in_file_are_dropped(tmp_path):
    """A profile written by a newer version must not break an older one."""
    path = tmp_path / "profiles.json"
    path.write_text(
        json.dumps(
            {
                "profiles": [
                    {"id": "abc", "name": "U", "email": "u@e.com", "futuro": 1}
                ]
            }
        ),
        encoding="utf-8",
    )

    loaded = ProfileStore(path).get("abc")
    assert isinstance(loaded, Profile)
    assert loaded.name == "U"
