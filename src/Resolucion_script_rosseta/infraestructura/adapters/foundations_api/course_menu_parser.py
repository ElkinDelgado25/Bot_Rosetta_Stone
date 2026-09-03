from typing import Any, Dict, List

from Resolucion_script_rosseta.dominio.entities.course_menu import CourseMenu
from Resolucion_script_rosseta.dominio.entities.lesson import Lesson
from Resolucion_script_rosseta.dominio.entities.path import Path
from Resolucion_script_rosseta.dominio.entities.unit import Unit


class CourseMenuParser:
    """Parser for converting GraphQL course menu responses to domain entities."""

    @staticmethod
    def parse(data: Dict[str, Any]) -> CourseMenu:
        """
        Parse GraphQL course menu response into CourseMenu entity.

        Args:
            data: GraphQL response data

        Returns:
            CourseMenu entity with units, lessons, and paths
        """
        menu_data = data.get("data", {}).get("courseMenu", {})
        units = CourseMenuParser._parse_units(menu_data.get("units", []))

        return CourseMenu(
            current_course_id=menu_data.get("currentCourseId"), units=units
        )

    @staticmethod
    def _parse_units(units_data: List[Dict[str, Any]]) -> List[Unit]:
        """Parse units from GraphQL data."""
        units = []
        for u in units_data:
            lessons = CourseMenuParser._parse_lessons(u.get("lessons", []))
            units.append(
                Unit(
                    id=u.get("id"),
                    index=u.get("index"),
                    unit_number=u.get("unitNumber"),
                    lessons=lessons,
                )
            )
        return units

    @staticmethod
    def _parse_lessons(lessons_data: List[Dict[str, Any]]) -> List[Lesson]:
        """Parse lessons from GraphQL data."""
        lessons = []
        for l in lessons_data:
            paths = CourseMenuParser._parse_paths(l.get("paths", []))
            lessons.append(
                Lesson(
                    id=l.get("id"),
                    index=l.get("index"),
                    lesson_number=l.get("lessonNumber"),
                    paths=paths,
                )
            )
        return lessons

    @staticmethod
    def _parse_paths(paths_data: List[Dict[str, Any]]) -> List[Path]:
        """Parse paths from GraphQL data."""
        paths = []
        for p in paths_data:
            paths.append(
                Path(
                    unit_index=p.get("unitIndex"),
                    lesson_index=p.get("lessonIndex"),
                    curriculum_lesson_index=p.get("curriculumLessonIndex"),
                    type=p.get("type"),
                    course=p.get("course"),
                    num_challenges=p.get("numChallenges", 0),
                    time_estimate=p.get("timeEstimate", 0),
                    complete=p.get("complete", False),
                    percent_complete=p.get("percentComplete", 0),
                )
            )
        return paths

