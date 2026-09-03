"""Fluency progress must be per account, not shared.

The activity keys are ``fluency|course|sequence|activity`` — no account in them.
With a single shared state file, the second user's run skipped every activity
the first user had completed and finished "successfully" having sent nothing.
"""

import asyncio
import json

from Resolucion_script_rosseta.aplicacion.orchestrators.complete_fluency_orchestrator import (
    CompleteFluencyOrchestrator,
)


def _orchestrator(tmp_path):
    return CompleteFluencyOrchestrator(api_port=object(), state_dir=tmp_path)


def _captured(user_id=None, email=None):
    data = {"user_id": user_id, "credentials": {"email": email} if email else {}}
    return data


def test_each_account_gets_its_own_state_file(tmp_path):
    orchestrator = _orchestrator(tmp_path)

    uno = orchestrator._state_for("111", _captured("111"))
    dos = orchestrator._state_for("222", _captured("222"))

    uno.mark_done("fluency|curso|sec|actividad-A")
    uno.save()
    dos.mark_done("fluency|curso|sec|actividad-B")
    dos.save()

    assert (tmp_path / "fluency_111.json").exists()
    assert (tmp_path / "fluency_222.json").exists()

    # The decisive check: one account's work must not read as the other's.
    assert dos.is_done("fluency|curso|sec|actividad-A") is False
    assert uno.is_done("fluency|curso|sec|actividad-B") is False


def test_the_second_user_does_not_inherit_the_first_users_progress(tmp_path):
    """Reproduces the bug: same activity key, two accounts, both pending."""
    orchestrator = _orchestrator(tmp_path)
    key = "fluency|c11c7c39|17ba3cc1|f34a8dd7"

    primero = orchestrator._state_for("111", _captured("111"))
    primero.mark_done(key)
    primero.save()

    segundo = orchestrator._state_for("222", _captured("222"))
    assert segundo.is_done(key) is False  # would be True with a shared file


def test_falls_back_to_the_email_before_the_first_run(tmp_path):
    """user_id is unknown until a run captures it."""
    orchestrator = _orchestrator(tmp_path)

    state = orchestrator._state_for(None, _captured(email="uno@example.com"))
    state.mark_done("k")
    state.save()

    assert (tmp_path / "fluency_uno_example.com.json").exists()


def test_unsafe_characters_do_not_escape_the_state_directory(tmp_path):
    orchestrator = _orchestrator(tmp_path)

    state = orchestrator._state_for("../../etc/passwd", _captured())
    state.mark_done("k")
    state.save()

    written = list(tmp_path.glob("fluency_*.json"))
    assert len(written) == 1
    assert written[0].parent == tmp_path  # stayed put
    assert "/" not in written[0].name and "\\" not in written[0].name


def test_without_a_state_dir_there_is_no_state(tmp_path):
    orchestrator = CompleteFluencyOrchestrator(api_port=object(), state_dir=None)
    assert orchestrator._state_for("111", _captured("111")) is None


def test_state_survives_a_reload(tmp_path):
    orchestrator = _orchestrator(tmp_path)
    state = orchestrator._state_for("111", _captured("111"))
    state.mark_done("k1")
    state.save()

    reloaded = _orchestrator(tmp_path)._state_for("111", _captured("111"))
    assert reloaded.is_done("k1") is True
    assert reloaded.total_done() == 1

    on_disk = json.loads((tmp_path / "fluency_111.json").read_text(encoding="utf-8"))
    assert on_disk["completed_path_keys"] == ["k1"]


def test_the_engine_default_is_one_lesson_but_all_is_selectable(monkeypatch):
    """Documenta el tope que dejaba a medias las corridas desde la UI.

    DependencyFactory lee FLUENCY_MAX_LESSONS y su default es 1: completaba una
    lección y paraba. La capa web pasa "all" explícitamente.
    """
    from Resolucion_script_rosseta.presentacion.dependency_factory import DependencyFactory

    class _Session:
        _page = type("P", (), {"request": object()})()

    factory = DependencyFactory(web_session=_Session(), rosseta_login_url="http://x")

    monkeypatch.delenv("FLUENCY_MAX_LESSONS", raising=False)
    assert factory.create_complete_fluency_orchestrator().max_lessons == 1

    monkeypatch.setenv("FLUENCY_MAX_LESSONS", "all")
    assert factory.create_complete_fluency_orchestrator().max_lessons is None

    monkeypatch.setenv("FLUENCY_MAX_LESSONS", "5")
    assert factory.create_complete_fluency_orchestrator().max_lessons == 5

