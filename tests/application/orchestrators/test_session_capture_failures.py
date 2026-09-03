"""A run that captured no session must fail loudly, not report success.

Before this, both orchestrators logged a warning and returned. The process
exited 0, the scheduler saw success and the web UI showed a green chip — for a
run that sent nothing at all.
"""

import asyncio

import pytest

from Resolucion_script_rosseta.aplicacion.orchestrators.complete_fluency_orchestrator import (
    CompleteFluencyOrchestrator,
)
from Resolucion_script_rosseta.aplicacion.orchestrators.complete_foundations_orchestrator import (
    CompleteFoundationsOrchestrator,
)
from Resolucion_script_rosseta.dominio.errors import SessionCaptureIncomplete

COMPLETE_SESSION = {
    "authorization": "eyJhbGciOiJIUzI1NiJ9.x.y",
    "lang_code": "ENG",
    "session_token": "tok",
    "school_id": "555",
    "user_id": "99887",
}


class _UseCaseSpy:
    def __init__(self):
        self.calls = 0

    async def execute(self, **kwargs):
        self.calls += 1
        raise AssertionError("no debería ejecutarse sin sesión completa")


class _ApiSpy:
    def __init__(self):
        self.calls = 0

    async def get_catalog(self, authorization, locale=None):
        self.calls += 1
        raise AssertionError("no debería llamarse sin authorization")


@pytest.mark.parametrize(
    "missing_key", ["authorization", "lang_code", "session_token", "school_id", "user_id"]
)
def test_foundations_raises_when_any_token_is_missing(missing_key):
    captured = {k: v for k, v in COMPLETE_SESSION.items() if k != missing_key}
    spy = _UseCaseSpy()
    orchestrator = CompleteFoundationsOrchestrator(complete_foundations_use_case=spy)

    with pytest.raises(SessionCaptureIncomplete) as exc_info:
        asyncio.run(orchestrator.execute(captured))

    assert missing_key in exc_info.value.missing
    assert spy.calls == 0  # nothing was attempted


def test_foundations_error_names_the_product_and_reads_clearly():
    orchestrator = CompleteFoundationsOrchestrator(
        complete_foundations_use_case=_UseCaseSpy()
    )

    with pytest.raises(SessionCaptureIncomplete) as exc_info:
        asyncio.run(orchestrator.execute({}))

    message = str(exc_info.value)
    assert "Foundations" in message
    assert "No se envió nada" in message


def test_an_empty_token_counts_as_missing():
    """A blank string is what a failed capture actually leaves behind."""
    captured = {**COMPLETE_SESSION, "session_token": ""}
    orchestrator = CompleteFoundationsOrchestrator(
        complete_foundations_use_case=_UseCaseSpy()
    )

    with pytest.raises(SessionCaptureIncomplete):
        asyncio.run(orchestrator.execute(captured))


def test_fluency_raises_without_the_gaia_token():
    api = _ApiSpy()
    orchestrator = CompleteFluencyOrchestrator(api_port=api)

    with pytest.raises(SessionCaptureIncomplete) as exc_info:
        asyncio.run(orchestrator.execute({"user_id": "1", "lang_code": "ENG"}))

    assert exc_info.value.missing == ["authorization"]
    assert "Fluency Builder" in str(exc_info.value)
    assert api.calls == 0

