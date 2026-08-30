"""Tests for the read-only Foundations pending checker."""

import asyncio

from rosseta_stone_script_a.application.orchestrators.foundations_pending_orchestrator import (
    FoundationsPendingOrchestrator,
)
from rosseta_stone_script_a.domain.entities.course_menu import CourseMenu
from rosseta_stone_script_a.domain.entities.lesson import Lesson
from rosseta_stone_script_a.domain.entities.path import Path
from rosseta_stone_script_a.domain.entities.unit import Unit
from rosseta_stone_script_a.infrastructure.state import StateStore, make_path_key


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
