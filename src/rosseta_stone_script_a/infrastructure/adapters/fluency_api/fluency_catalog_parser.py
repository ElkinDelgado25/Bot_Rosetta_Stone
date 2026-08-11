from typing import Any, Dict, List, Optional

from rosseta_stone_script_a.domain.entities.fluency_catalog import FluencyCatalog
from rosseta_stone_script_a.domain.entities.fluency_course import (
    FluencyCourse,
    FluencySequenceRef,
)


class FluencyCatalogParser:
    """Parse a ``getCoursesAndProgress`` GraphQL response into a FluencyCatalog.

    The response has two independent root fields: ``assignedCourses`` (the
    catalog) and ``progress`` (per-lesson percentComplete, keyed by courseId).
    They are joined here by sequence id.
    """

    @staticmethod
    def parse(data: Dict[str, Any], locale: Optional[str] = None) -> FluencyCatalog:
        payload = data.get("data", data) or {}
        assigned = payload.get("assignedCourses", []) or []
        progress = payload.get("progress", []) or []

        progress_by_course = FluencyCatalogParser._index_progress(progress)

        courses: List[FluencyCourse] = []
        for c in assigned:
            course_id = c.get("courseId") or c.get("id")
            percent_by_seq = progress_by_course.get(course_id, {})
            sequences = [
                FluencySequenceRef(
                    sequence_id=s.get("id"),
                    title=FluencyCatalogParser._text(s.get("title")),
                    percent_complete=percent_by_seq.get(s.get("id"), 0.0),
                )
                for s in (c.get("sequences") or [])
            ]
            courses.append(
                FluencyCourse(
                    course_id=course_id,
                    product_id=c.get("productId"),
                    title=FluencyCatalogParser._text(c.get("title")),
                    cefr=c.get("cefr"),
                    topic=FluencyCatalogParser._topic(c.get("topics"), locale),
                    sequences=sequences,
                )
            )

        return FluencyCatalog(courses=courses)

    @staticmethod
    def _index_progress(
        progress: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, float]]:
        """Map courseId -> {sequenceId -> percentComplete}.

        percentComplete is a fraction in [0.0, 1.0], not a 0-100 percentage.
        """
        index: Dict[str, Dict[str, float]] = {}
        for p in progress:
            course_id = p.get("courseId")
            if not course_id:
                continue
            index[course_id] = {
                s.get("id"): s.get("percentComplete", 0.0)
                for s in (p.get("sequences") or [])
                if s.get("id")
            }
        return index

    @staticmethod
    def _text(value: Any) -> Optional[str]:
        """A localized title may arrive as a plain string or a {text: ...} object."""
        if value is None or isinstance(value, str):
            return value
        if isinstance(value, dict):
            return value.get("text")
        return None

    @staticmethod
    def _topic(topics: Any, locale: Optional[str]) -> Optional[str]:
        """Pick the topic label for ``locale`` from its localizations, else the first."""
        if not topics:
            return None
        first = topics[0] if isinstance(topics, list) else topics
        localizations = (first or {}).get("localizations") or []
        if not localizations:
            return None
        if locale:
            for loc in localizations:
                if loc.get("locale") == locale:
                    return loc.get("text")
        return localizations[0].get("text")
