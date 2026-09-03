"""Tests for the read-only Foundations pending checker."""

import asyncio

from Resolucion_script_rosseta.aplicacion.orchestrators.foundations_pending_orchestrator import (
    FoundationsPendingOrchestrator,
)
from Resolucion_script_rosseta.dominio.entities.course_menu import CourseMenu
from Resolucion_script_rosseta.dominio.entities.lesson import Lesson
from Resolucion_script_rosseta.dominio.entities.path import Path
from Resolucion_script_rosseta.dominio.entities.unit import Unit
from Resolucion_script_rosseta.infraestructura.state import StateStore, make_path_key


class _MenuApi:
    async def get_course_menu(self, authorization, language_code):
        done = Path(0, 0, 0, "vocabulary", "course-1", 1, 1, True, 100)
        pending = Path(0, 0, 0, "grammar", "course-1", 1, 1, False, 0)
        return CourseMenu("course-1", [Unit("u", 0, 1, [Lesson("l", 0, 1, [done, pending])])])


def test_reconciles_remote_foundations_paths_without_sending(tmp_path):
    menu = asyncio.run(
        FoundationsPendingOrchestrator(_MenuApi(), tmp_path).execute(
            {"authorization": "Bearer x", "lang_code": "en", "user_id": "user-1"}
        )
    )

    assert menu["recovered"] == 1
    assert menu["completed"][0]["activity_id"] == "vocabulary"
    assert menu["pending"][0]["activity_id"] == "grammar"

    done = Path(0, 0, 0, "vocabulary", "course-1", 1, 1, True, 100)
    assert StateStore(tmp_path).load("user-1").is_done(make_path_key(done))

