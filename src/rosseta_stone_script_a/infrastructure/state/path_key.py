"""Helper that builds the canonical string key for a completed path."""

from rosseta_stone_script_a.domain.entities.path import Path as RosettaPath


def make_path_key(path: RosettaPath) -> str:
    """
    Return a stable, unique string key for a given path.

    Format: ``<course>|<unit_index>|<lesson_index>|<type>|1``

    The trailing ``|1`` represents occurrence (always 1 as sent to the API).
    """
    return f"{path.course}|{path.unit_index}|{path.curriculum_lesson_index}|{path.type}|1"
