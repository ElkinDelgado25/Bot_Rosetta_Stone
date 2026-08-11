"""Tests for FluencyCatalogParser.

Fixtures mirror the real shapes of getCoursesAndProgress observed in the HAR:
- assignedCourses and progress are independent root fields joined by sequence id;
- title(locale:) resolves server-side to a plain string;
- topics carry per-locale localizations;
- a course may have no progress entry (stays at 0).
"""

from rosseta_stone_script_a.infrastructure.adapters.fluency_api.fluency_catalog_parser import (
    FluencyCatalogParser,
)


def _response():
    return {
        "data": {
            "assignedCourses": [
                {
                    "id": "hexcourse1",
                    "courseId": "hexcourse1",
                    "productId": "product.abc",
                    "learningLanguage": "en-US",
                    "title": "All Skills (B1)",
                    "cefr": "B1",
                    "topics": [
                        {
                            "localizations": [
                                {"locale": "en-US", "text": "Everyday Situations"},
                                {"locale": "es-419", "text": "Situaciones cotidianas"},
                            ]
                        }
                    ],
                    "sequences": [
                        {"id": "seq-a", "title": "Window-Shopping (All Skills)"},
                        {"id": "seq-b", "title": "Desserts (All Skills)"},
                    ],
                },
                {
                    "id": "hexcourse2",
                    "courseId": "hexcourse2",
                    "productId": "product.def",
                    "title": "Manage Your Career (B1)",
                    "cefr": "B1",
                    "topics": [],
                    "sequences": [{"id": "seq-c", "title": "Interviews"}],
                },
            ],
            "progress": [
                {
                    "id": "hexcourse1",
                    "courseId": "hexcourse1",
                    "countOfSequencesInCourse": 2,
                    "sequences": [
                        {"id": "seq-a", "percentComplete": 0.0},
                        {"id": "seq-b", "percentComplete": 1.0},
                    ],
                }
                # hexcourse2 has no progress entry -> everything at 0
            ],
        }
    }


class TestFluencyCatalogParser:
    def test_parses_all_assigned_courses(self):
        catalog = FluencyCatalogParser.parse(_response())
        assert [c.course_id for c in catalog.courses] == ["hexcourse1", "hexcourse2"]

    def test_course_scalar_fields(self):
        catalog = FluencyCatalogParser.parse(_response())
        course = catalog.courses[0]
        assert course.title == "All Skills (B1)"
        assert course.cefr == "B1"
        assert course.product_id == "product.abc"

    def test_joins_progress_by_sequence_id(self):
        catalog = FluencyCatalogParser.parse(_response())
        seqs = {s.sequence_id: s.percent_complete for s in catalog.courses[0].sequences}
        assert seqs == {"seq-a": 0.0, "seq-b": 1.0}

    def test_course_without_progress_defaults_to_zero(self):
        catalog = FluencyCatalogParser.parse(_response())
        career = catalog.courses[1]
        assert career.sequences[0].percent_complete == 0.0

    def test_topic_uses_requested_locale(self):
        catalog = FluencyCatalogParser.parse(_response(), locale="es-419")
        assert catalog.courses[0].topic == "Situaciones cotidianas"

    def test_topic_falls_back_to_first_localization(self):
        catalog = FluencyCatalogParser.parse(_response(), locale="fr-FR")
        assert catalog.courses[0].topic == "Everyday Situations"

    def test_missing_topics_is_none(self):
        catalog = FluencyCatalogParser.parse(_response())
        assert catalog.courses[1].topic is None

    def test_title_object_form_is_unwrapped(self):
        data = {
            "data": {
                "assignedCourses": [
                    {
                        "courseId": "c1",
                        "title": {"text": "Wrapped Title"},
                        "sequences": [{"id": "s1", "title": {"text": "Seq"}}],
                    }
                ],
                "progress": [],
            }
        }
        catalog = FluencyCatalogParser.parse(data)
        assert catalog.courses[0].title == "Wrapped Title"
        assert catalog.courses[0].sequences[0].title == "Seq"

    def test_empty_response_yields_empty_catalog(self):
        assert FluencyCatalogParser.parse({"data": {}}).courses == []
